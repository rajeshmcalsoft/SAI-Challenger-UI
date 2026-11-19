// A run started from the UI, while it is queued or live (design §6.4). When run_poc.sh has written the JUnit
// report, the page hands over to the finished run page, which reads that report.
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { getConsole, removeJob, useJob, type JobFull } from "../api";
import { Dl, Failed, Help, Loading, Strip, duration, when } from "../ui";
import { Group } from "./Run";

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
    <section className="group" id="grp-still">
      <div className="group-head">
        <span className="title">Still to run <span className="count">{Math.max(j.total - j.done, j.still.length)}</span></span>
        <Help label="About Still to run"><p>Tests not finished yet, in the order they run. Each one moves into its result group when it ends.</p></Help>
      </div>
      <div className="list">
        {now && (
          <div className="trow still now">
            <span className="g spinner" aria-hidden="true">◌</span>
            <span className="t-main"><span className="t-title">Now running: {now.title}</span><span className="t-id mono">{now.name}</span></span>
            <span className="t-track" />
            <span className="t-dur">{Math.round(secs)}s</span>
            <span className="t-act" />
          </div>
        )}
        {rest.slice(0, 200).map((s) => (
          <div key={s.key} className="trow still">
            <span className="g faint" aria-hidden="true">·</span>
            <span className="t-main"><span className="t-title">{s.title}</span><span className="t-id mono">{s.name}</span></span>
            <span className="t-track" /><span className="t-dur" /><span className="t-act" />
          </div>
        ))}
        {rest.length > 200 && <div className="note">and {rest.length - 200} more</div>}
        {unknown > 0 && <div className="note">{unknown} more that pytest collected (parameter variants the catalogue doesn't list yet)</div>}
      </div>
    </section>
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
    <div className={`drawer${open ? " open" : ""}`}>
      <div className="drawer-head">
        <button className="btn sm" type="button" aria-expanded={open} onClick={() => setOpen(!open)}>Console {open ? "▾" : "▴"}</button>
        {open && (
          <>
            <input className="search sm" type="search" placeholder="Search the output" value={q} onChange={(e) => setQ(e.target.value)} />
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
  const j = q.data;

  useEffect(() => {
    if (j?.state === "done" && j.runId) {
      qc.invalidateQueries({ queryKey: ["runs"] });
      qc.invalidateQueries({ queryKey: ["targets"] });
      navigate({ to: "/runs/$runId", params: { runId: j.runId }, replace: true });
    }
  }, [j?.state, j?.runId, navigate, qc]);

  if (q.isPending) return <section className="section"><Loading what="the run" /></section>;
  if (q.error || !j) return <section className="section"><Failed error={q.error} /></section>;
  const live = j.state === "queued" || j.state === "running";
  const ref = { id: j.id, target: j.target, live: true };
  const opts = [j.traffic ? "traffic on" : "traffic off", j.mld !== "auto" ? `MLD filter ${j.mld}` : null].filter(Boolean).join(" · ");

  async function takeOff() {
    setRemoving(true);
    try { await removeJob(j!.id); } finally { setRemoving(false); qc.invalidateQueries({ queryKey: ["job", j!.id] }); qc.invalidateQueries({ queryKey: ["jobs"] }); }
  }

  return (
    <section className="section with-drawer">
      <div className="eyebrow">
        UI run on {j.target} · <span className="mono">{j.id}</span>{" "}
        <Help label="About this run">
          <Dl rows={[
            ["What", `${j.what} · ${j.count} tests planned`],
            ["Queued", when(j.created)],
            ["Started", j.started ? when(j.started) : "not yet"],
            ["Report", j.runId ?? "written by run_poc.sh when the run ends"],
            ["pytest", j.profileLine || "not started"],
          ]} />
          <p>Progress comes from the console while the run is live. The JUnit report confirms every result when it ends,
            and this page then opens the finished run.</p>
        </Help>
      </div>
      <div className="run-head" aria-live="polite">
        <div className="headline">{headline(j)}</div>
        <div className="actions">
          {j.state === "queued" && (
            <button className="btn sm" type="button" onClick={takeOff} disabled={removing}>Take off the queue</button>
          )}
          {j.state === "running" && (
            <button className="btn sm" type="button" disabled
              title="Not yet: how to stop a run safely inside the container is still to be checked (build step 0.10). The run continues even if you close this page or stop the UI server.">
              Cancel
            </button>
          )}
        </div>
        {j.done > 0 && (
          <div className="counts">
            {j.countParts.map(([r, text], i) => (
              <span key={r}>{i > 0 && <span className="sepdot">·</span>}<a href={`#grp-${r}`}>{text}</a></span>
            ))}
          </div>
        )}
        {j.strip.length > 0 && <div className="strip-wrap"><Strip cells={j.strip} letters /></div>}
        <div className="meta">
          <div className="items">
            <span><b>{j.target}</b> · {j.testbed}</span>
            <span>{j.what}</span>
            <span>{opts}</span>
            <span>by {j.who}</span>
            {j.commit && <span className="mono">commit {j.commit}{j.branch ? ` (${j.branch})` : ""}</span>}
            {j.dirty.length > 0 && <span className="warn">+ uncommitted changes</span>}
            {j.setSize > 1 && (
              <span>Run {j.setIndex} of {j.setSize}:{" "}
                {j.set.map((s) => (
                  <span key={s.id}>{" "}{s.id === j.id ? <b>{s.index}</b> : s.runId
                    ? <Link to="/runs/$runId" params={{ runId: s.runId }}>{s.index}</Link>
                    : <Link to="/jobs/$jobId" params={{ jobId: s.id }}>{s.index}</Link>}</span>
                ))}
              </span>
            )}
          </div>
          <details className="cmd inline"><summary>Command</summary><code>{j.command}</code></details>
        </div>
      </div>

      {j.waiting && j.waiting.kind !== "starting" && (
        <div className="banner wait">
          {j.waiting.text}{" "}
          {j.waiting.jobId && <Link to="/jobs/$jobId" params={{ jobId: j.waiting.jobId }}>Open that run</Link>}
        </div>
      )}
      {j.note && <div className="banner">{j.note}</div>}
      {j.interrupted && <div className="banner warn">pytest: {j.interrupted}</div>}
      {j.state === "done" && !j.runId && !j.reportPending && (
        <div className="banner">run_poc.sh exited with {j.exitCode ?? "an unknown status"}. Open the console below to see why.</div>
      )}

      {j.groups.map((g) => <Group key={g.result} run={ref} result={g.result} count={g.count} entries={g.entries} openKey={null} />)}
      {live && <StillToRun j={j} />}
      <ConsoleDrawer jobId={j.id} active={live} />
    </section>
  );
}
