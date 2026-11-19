// A run started from the UI, while it is queued or live (design §6.4). When run_poc.sh has written the JUnit
// report, the page hands over to the finished run page, which reads that report.
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { getConsole, removeJob, useJob, type JobFull, type TestRow } from "../api";
import { NO_FILTERS, TestTree, type Filters } from "../components/TestTree";
import { TestDetail } from "../components/TestDetail";
import { I } from "../icons";
import { Crumbs, Dl, Donut, Failed, Help, Loading, Strip, Ticks, duration, when } from "../ui";
import { StatusChips, tileText } from "./Run";

function headline(j: JobFull) {
  if (j.state === "queued") return j.waiting?.kind === "starting" ? "Starting…" : "Queued";
  if (j.state === "running") {
    if (j.waiting) return "Waiting for the lock";
    if (!j.done && !j.profileLine) return "Starting…";
    return `Running · ${j.done} of ${j.total} · ${duration(j.seconds)}`;
  }
  if (j.state === "removed") return "Not run";
  if (j.reportPending) return "Finished · reading the report…";
  return "Ended without a report";
}

function useSince(key: string | null) {
  // When the current test started, as seen by this page (the console has no timestamps).
  const [since, setSince] = useState<{ key: string | null; at: number }>({ key, at: Date.now() });
  const [, tick] = useState(0);
  if (since.key !== key) setSince({ key, at: Date.now() });
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);
  return Math.max(0, (Date.now() - since.at) / 1000);
}

function StillToRun({ j }: { j: JobFull }) {
  const now = j.still.find((s) => s.now);
  const secs = useSince(now?.key ?? null);
  const rest = j.still.filter((s) => !s.now);
  const unknown = Math.max(0, j.total - j.done - j.still.length);
  if (!j.still.length && !unknown) return null;
  return (
    <div className="tree" style={{ marginTop: 8 }}>
      <div className="tnode" style={{ ["--depth" as string]: 0, cursor: "default" }}>
        <I.clock className="chev" /><span>Still to run<span className="gcount">{Math.max(j.total - j.done, j.still.length)}</span></span><span />
      </div>
      {now && (
        <div className="tleaf still-now" style={{ ["--depth" as string]: 1, gridTemplateColumns: "16px minmax(0,1fr) 64px", cursor: "default" }}>
          <span className="spinner" aria-hidden="true" />
          <span className="ttl"><span className="name"><b>Now running:</b> {now.title}</span><span className="id">{now.name}</span></span>
          <span className="dur">{Math.round(secs)}s</span>
        </div>
      )}
      {rest.slice(0, 200).map((s) => (
        <div key={s.key} className="tleaf" style={{ ["--depth" as string]: 1, gridTemplateColumns: "16px minmax(0,1fr) 64px", cursor: "default", color: "var(--text-3)" }}>
          <span className="sicon r-none hollow" aria-hidden="true" />
          <span className="ttl"><span className="name">{s.title}</span><span className="id">{s.name}</span></span>
          <span />
        </div>
      ))}
      {rest.length > 200 && <div className="tnote">and {rest.length - 200} more</div>}
      {unknown > 0 && <div className="tnote">{unknown} more that pytest collected (parameter variants the catalogue doesn't list yet)</div>}
    </div>
  );
}

function ConsoleDrawer({ jobId, active }: { jobId: string; active: boolean }) {
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem("sai-challenger-ui-console") === "open"; } catch { return false; }
  });
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const offset = useRef(0);
  const pre = useRef<HTMLPreElement>(null);
  const atBottom = useRef(true);

  useEffect(() => {
    try { localStorage.setItem("sai-challenger-ui-console", open ? "open" : "closed"); } catch { /* not remembered */ }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let stop = false;
    async function pull() {
      try {
        for (let i = 0; i < 20 && !stop; i++) {  // catch up in chunks, then wait
          const c = await getConsole(jobId, offset.current);
          if (stop) return;
          if (c.text) setText((t) => t + c.text);
          offset.current = c.offset;
          if (c.offset >= c.size) break;
        }
      } catch { /* try again on the next tick */ }
    }
    pull();
    const id = active ? setInterval(pull, 1000) : undefined;
    return () => { stop = true; if (id) clearInterval(id); };
  }, [open, jobId, active]);

  useLayoutEffect(() => {
    if (pre.current && atBottom.current && !q) pre.current.scrollTop = pre.current.scrollHeight;
  }, [text, q, open]);

  const lines = q ? text.split("\n").filter((l) => l.toLowerCase().includes(q.toLowerCase())) : null;
  return (
    <div className="drawer">
      <div className="drawer-head">
        <button className="btn ghost sm" type="button" aria-expanded={open} onClick={() => setOpen(!open)}>Console {open ? <I.chevron /> : <I.chevronUp />}</button>
        {open && (
          <>
            <input className="search plain" type="search" placeholder="Search the output" value={q} onChange={(e) => setQ(e.target.value)} />
            {lines && <span className="faint small">{lines.length} matching lines</span>}
            <span className="spacer" />
            <a className="small" href={`/api/jobs/${encodeURIComponent(jobId)}/console.txt`} target="_blank" rel="noreferrer">Open as text</a>
          </>
        )}
      </div>
      {open && (
        <pre ref={pre} className="drawer-body" onScroll={(e) => {
          const el = e.currentTarget;
          atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
        }}>{lines ? lines.join("\n") : text || "No output yet."}</pre>
      )}
    </div>
  );
}

export function JobPage({ jobId }: { jobId: string }) {
  const q = useJob(jobId);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [removing, setRemoving] = useState(false);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [selected, setSelected] = useState<string | null>(null);
  const j = q.data;

  useEffect(() => {
    if (j?.state === "done" && j.runId) {
      qc.invalidateQueries({ queryKey: ["runs"] });
      qc.invalidateQueries({ queryKey: ["targets"] });
      navigate({ to: "/runs/$runId", params: { runId: j.runId }, search: {}, replace: true });
    }
  }, [j?.state, j?.runId, navigate, qc]);

  const tests = useMemo(() => {
    const out: TestRow[] = [];
    for (const g of j?.groups ?? []) for (const e of g.entries) {
      if (e.kind === "test") out.push(e.test);
      else if (e.kind === "scenario") out.push(...e.steps.map((s) => ({ ...s, scenario: e.title })));
    }
    return out.map((t, i) => ({ ...t, pos: t.pos ?? i + 1 }));
  }, [j?.groups]);

  if (q.isPending) return <div className="card"><Loading what="the run" /></div>;
  if (q.error || !j) return <div className="card"><Failed error={q.error} /></div>;
  const live = j.state === "queued" || j.state === "running";
  const opts = [j.traffic ? "traffic on" : "traffic off", j.mld !== "auto" ? `MLD filter ${j.mld}` : null].filter(Boolean).join(" · ");
  const row = selected ? tests.find((t) => t.key === selected) : undefined;

  async function takeOff() {
    setRemoving(true);
    try { await removeJob(j!.id); } finally { setRemoving(false); qc.invalidateQueries({ queryKey: ["job", j!.id] }); qc.invalidateQueries({ queryKey: ["jobs"] }); }
  }

  const main = (
    <div className="card" aria-live="polite">
      <div className="rhead">
        <div className="rtile" aria-hidden="true">{tileText(j.target)}</div>
        <div className="ttl">
          <div className="eyebrow">UI run on {j.target} · {j.id}{" "}
            <Help label="About this run">
              <Dl rows={[
                ["What", `${j.what} · ${j.count} tests planned`], ["Queued", when(j.created)],
                ["Started", j.started ? when(j.started) : "not yet"], ["Report", j.runId ?? "written by run_poc.sh when the run ends"],
                ["pytest", j.profileLine || "not started"],
              ]} />
              <p>Progress comes from the console while the run is live. The JUnit report confirms every result when it ends, and this page then opens the finished run.</p>
            </Help>
          </div>
          <h1>{headline(j)}</h1>
          <div className="sub"><span>{j.what}</span><span>{opts}</span><span>by {j.who}</span>
            {j.commit && <span className="mono">commit {j.commit}{j.branch ? ` (${j.branch})` : ""}</span>}
            {j.dirty.length > 0 && <span className="warn">+ uncommitted changes</span>}
            {j.retry > 0 && <span>Retry failures up to {j.retry}× · attempt {j.attempt}</span>}
          </div>
        </div>
        <Donut counts={j.counts} size={88} />
      </div>
      {j.state === "running" && j.total > 0 && <div className="progress" role="progressbar" aria-valuenow={j.done} aria-valuemax={j.total}><i style={{ width: `${(100 * j.done) / j.total}%` }} /></div>}
      <div className="ractions">
        {j.state === "queued" && <button className="btn" type="button" onClick={takeOff} disabled={removing}>Take off the queue</button>}
        {j.state === "running" && (
          <button className="btn" type="button" disabled
            title="Not yet: how to stop a run safely inside the container is still to be checked (build step 0.10). The run continues even if you close this page or stop the UI server.">
            Cancel
          </button>
        )}
        {j.setSize > 1 && (
          <span className="small muted">Run {j.setIndex} of {j.setSize}:{" "}
            {j.set.map((s) => (
              <span key={s.id}>{" "}{s.id === j.id ? <b>{s.index}</b> : s.runId
                ? <Link to="/runs/$runId" params={{ runId: s.runId }} search={{}}>{s.index}</Link>
                : <Link to="/jobs/$jobId" params={{ jobId: s.id }}>{s.index}</Link>}</span>
            ))}
          </span>
        )}
        <span className="spacer" style={{ flex: 1 }} />
        <details className="cmd"><summary>Command</summary><div className="cmdline"><code>{j.command}</code></div></details>
      </div>
      {j.waiting && j.waiting.kind !== "starting" && (
        <div className="banner info" style={{ marginTop: 12 }}>{j.waiting.text}{" "}{j.waiting.jobId && <Link to="/jobs/$jobId" params={{ jobId: j.waiting.jobId }}>Open that run</Link>}</div>
      )}
      {j.note && <div className="banner" style={{ marginTop: 12 }}>{j.note}</div>}
      {j.interrupted && <div className="banner warn" style={{ marginTop: 12 }}>pytest: {j.interrupted}</div>}
      {j.state === "done" && !j.runId && !j.reportPending && (
        <div className="banner warn" style={{ marginTop: 12 }}>run_poc.sh exited with {j.exitCode ?? "an unknown status"}. Open the console below to see why.</div>
      )}
      <div style={{ marginTop: 20 }} />
      {j.done > 0 && (
        <>
          <div className="stats">
            <div className="stat"><span className="k">Done</span><span className="v">{j.done} of {j.total}</span></div>
            <span className="spacer" />
            <Ticks counts={j.counts} />
          </div>
          {j.strip.length > 0 && <div className="rstrip"><Strip cells={j.strip} letters /></div>}
          <div className="row wrap" style={{ marginBottom: 12, gap: 8 }}>
            <StatusChips tests={tests} value={filters.status} onChange={(status) => setFilters({ ...filters, status })} />
          </div>
          <TestTree tests={tests} groupBy="result" sortBy="order" filters={filters} selected={selected} onSelect={setSelected} />
        </>
      )}
      {live && <StillToRun j={j} />}
    </div>
  );

  return (
    <section className="with-drawer">
      <Crumbs items={[{ label: "Runs", to: "/runs" }, { label: `${j.target} · live` }]} />
      {row ? (
        <div className="split">
          {main}
          <div className="card pane">
            <TestDetail runId={j.id} target={j.target} testKey={row.key} row={row} live
              nav={{ index: Math.max(0, tests.indexOf(row)), total: tests.length, prev: null, next: null }} onOpen={setSelected} />
          </div>
        </div>
      ) : main}
      <ConsoleDrawer jobId={j.id} active={live} />
    </section>
  );
}
