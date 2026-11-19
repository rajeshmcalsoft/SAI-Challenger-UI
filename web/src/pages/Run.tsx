// A finished run (design §6.4), laid out like Allure Report 3's report page: header with the donut, a Report switch
// (Results / Charts, A6), tabs with counts (Results · Causes · Gates · Run log), a stats row, search, filters,
// sorting and the test tree; a test opens beside the list (split, A2) or in its place (full).
import * as Tabs from "@radix-ui/react-tabs";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useCharts, useRun, type RunFull, type TestRow } from "../api";
import { DurationHistogram, RunTimes, Stability, StatusDynamics, Transitions } from "../charts";
import { NO_FILTERS, TestTree, buildTree, flatLeaves, matches, statusOf, type Filters, type GroupBy, type MarkFilter, type SortBy, type StatusFilter } from "../components/TestTree";
import { TestDetail } from "../components/TestDetail";
import { I } from "../icons";
import { useRunSheet } from "../RunSheet";
import { CopyButton, Crumbs, Donut, Empty, Failed, Help, Loading, StatusIcon, Strip, Ticks, duration, useLocal, whenLong, type Crumb } from "../ui";
import { ATTENTION, GROUP_ORDER, passRate, type Result } from "../vocab";

export type RunSearch = { t?: string; view?: "results" | "charts"; tab?: "results" | "causes" | "gates" | "log" };

export function tileText(target: string) {
  const core = target.replace(/^sai/, "").split(/[-_]/);
  return (core[0].slice(0, 3) + (core[1] ? core[1][0] : "")).toUpperCase();
}

const STATUS_CHIPS: { id: StatusFilter; label: string; results: Result[] }[] = [
  { id: "fail", label: "Fail", results: ["fail"] },
  { id: "error", label: "Error", results: ["setup_error", "cleanup_error"] },
  { id: "gap_passes", label: "Gap now passes", results: ["gap_passes"] },
  { id: "expected_gap", label: "Expected gap", results: ["expected_gap"] },
  { id: "skipped", label: "Skipped", results: ["skipped"] },
  { id: "pass", label: "Pass", results: ["pass"] },
];

export function StatusChips({ tests, value, onChange }: { tests: TestRow[]; value: StatusFilter; onChange: (v: StatusFilter) => void }) {
  const n = (rs: Result[]) => tests.filter((t) => rs.includes(t.result)).length;
  return (
    <span className="seg" role="group" aria-label="Show tests with this result">
      <button type="button" aria-pressed={value === "all"} onClick={() => onChange("all")}>Total <span className="count">{tests.length}</span></button>
      {STATUS_CHIPS.map((c) => {
        const count = n(c.results);
        if (!count && value !== c.id) return null;
        const r = c.results[0];
        return (
          <button key={c.id} type="button" aria-pressed={value === c.id} onClick={() => onChange(value === c.id ? "all" : c.id)}>
            {c.label} <span className={`cpill r-${r}`}>{count}</span>
          </button>
        );
      })}
    </span>
  );
}

const MARKS: { id: MarkFilter; label: string; icon: ReactNode; help: string }[] = [
  { id: "regressed", label: "Regressed", icon: <I.regressed />, help: "Fail now, and not Fail in the last run on this target that ran it" },
  { id: "new_error", label: "New error", icon: <I.regressed />, help: "A setup or cleanup error now, and not before" },
  { id: "fixed", label: "Fixed", icon: <I.fixed />, help: "Pass now, after a fail, error or expected gap" },
  { id: "new", label: "New", icon: <I.plusCircle />, help: "First time on this target" },
];

function MenuButton({ label, children, active = false, right = false }: { label: ReactNode; children: ReactNode; active?: boolean; right?: boolean }) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) ref.current.open = false; };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  return (
    <details className="menu" ref={ref}>
      <summary className="btn ghost" aria-pressed={active}>{label}<I.chevron /></summary>
      <div className={`menu-list${right ? " right" : ""}`} role="menu" onClick={(e) => { if ((e.target as HTMLElement).closest("button,a")) ref.current!.open = false; }}>
        {children}
      </div>
    </details>
  );
}

export function FilterRow({ run, filters, setFilters, groupBy, setGroupBy, sortBy, setSortBy, allowCause = true }: {
  run: Pick<RunFull, "tests" | "marks" | "causes" | "retries">; filters: Filters; setFilters: (f: Filters) => void;
  groupBy: GroupBy; setGroupBy: (g: GroupBy) => void; sortBy: SortBy; setSortBy: (s: SortBy) => void; allowCause?: boolean;
}) {
  const toggleMark = (m: MarkFilter) => setFilters({ ...filters, marks: filters.marks.includes(m) ? filters.marks.filter((x) => x !== m) : [...filters.marks, m] });
  const transitions = filters.marks.filter((m) => m !== "flaky" && m !== "retried");
  const retried = Object.keys(run.retries?.tests ?? {}).length;
  const kinds = new Set(run.tests.map((t) => t.gap?.note.state === "overdue" ? "overdue" : t.gap?.note.recorded ? t.gap.note.kind : null).filter(Boolean));
  return (
    <div className="filters">
      {retried > 0 && (
        <button type="button" className="btn ghost" aria-pressed={filters.marks.includes("retried")} onClick={() => toggleMark("retried")}
          title="Tests that were run again by Retry failures"><I.retry />Retried <span className="count">{retried}</span></button>
      )}
      <button type="button" className="btn ghost" aria-pressed={filters.marks.includes("flaky")} onClick={() => toggleMark("flaky")}
        title="Their outcome changed at least twice in their last results on this target (Allure's rule)">
        <I.flaky />Flaky <span className="count">{run.marks.flaky}</span>
      </button>
      <MenuButton label={<>Transition{transitions.length ? ` · ${transitions.length}` : ""}</>} active={transitions.length > 0}>
        <div className="mh">Against the last run that ran each test</div>
        {MARKS.map((m) => {
          const n = m.id === "new_error" ? run.marks.newError : run.marks[m.id as "new" | "fixed" | "regressed"];
          return (
            <button key={m.id} type="button" role="menuitemcheckbox" aria-checked={filters.marks.includes(m.id)} onClick={() => toggleMark(m.id)} title={m.help}>
              {m.icon}{m.label}<span className="count">{n}</span>
            </button>
          );
        })}
      </MenuButton>
      {allowCause && run.causes.length > 0 && (
        <MenuButton label={<>Cause{filters.cause ? " · 1" : ""}</>} active={!!filters.cause}>
          <button type="button" role="menuitemradio" aria-checked={!filters.cause} onClick={() => setFilters({ ...filters, cause: null })}>Any cause</button>
          <hr />
          {run.causes.map((c) => (
            <button key={c.id} type="button" role="menuitemradio" aria-checked={filters.cause === c.id} onClick={() => setFilters({ ...filters, cause: c.id })}>
              <span className="ellipsis" style={{ maxWidth: 320 }}>{c.title}</span><span className="count">{c.keys.length}</span>
            </button>
          ))}
        </MenuButton>
      )}
      {kinds.size > 0 && (
        <MenuButton label={<>Gap kind{filters.kind ? " · 1" : ""}</>} active={!!filters.kind}>
          <button type="button" role="menuitemradio" aria-checked={!filters.kind} onClick={() => setFilters({ ...filters, kind: null })}>Any kind</button>
          <hr />
          {(["limitation", "bug", "temporary", "overdue"] as const).map((k) => (
            <button key={k} type="button" role="menuitemradio" aria-checked={filters.kind === k} onClick={() => setFilters({ ...filters, kind: k })}>
              {{ limitation: "Limitation", bug: "Known bug", temporary: "Temporary", overdue: "Overdue for review" }[k]}
            </button>
          ))}
        </MenuButton>
      )}
      <span className="spacer" />
      <label className="sortby">Group{" "}
        <select value={groupBy} onChange={(e) => setGroupBy(e.target.value as GroupBy)}>
          <option value="result">Result</option><option value="track">Track</option><option value="file">File</option>
        </select>
      </label>
      <label className="sortby">Sort{" "}
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortBy)}>
          <option value="order">Order run</option><option value="status">Status</option><option value="duration">Duration</option><option value="name">Name</option>
        </select>
      </label>
    </div>
  );
}

function RerunMenu({ run }: { run: RunFull }) {
  const openSheet = useRunSheet();
  const poc = run.tests.filter((t) => !t.upstream && t.name !== "(collection)");
  const keys = (rows: TestRow[]) => rows.map((t) => [t.module, t.cls, t.name].filter(Boolean).join("::"));
  const failing = poc.filter((t) => ATTENTION.includes(t.result) && t.result !== "gap_passes");
  const attention = poc.filter((t) => ATTENTION.includes(t.result));
  return (
    <MenuButton label={<><I.retry />Rerun</>}>
      <button type="button" onClick={() => openSheet({ targets: [run.target], what: "pick", tests: keys(failing) })} disabled={!failing.length}>
        Failed only ({failing.length})…</button>
      <button type="button" onClick={() => openSheet({ targets: [run.target], what: "pick", tests: keys(attention) })} disabled={!attention.length}>
        Everything that needs attention ({attention.length})…</button>
      <button type="button" onClick={() => openSheet({ targets: [run.target], what: "pick", tests: keys(poc) })} disabled={!poc.length}>
        The same {poc.length} tests on {run.target}…</button>
      <button type="button" onClick={() => openSheet({ targets: [run.target], what: "full" })}>Full PoC suite on {run.target}…</button>
    </MenuButton>
  );
}

function ExportMenu({ run }: { run: RunFull }) {
  const [copied, setCopied] = useState("");
  const base = `/api/runs/${encodeURIComponent(run.id)}`;
  async function copySummary() {
    try {
      const text = await (await fetch(`${base}/summary.md`)).text();
      await navigator.clipboard.writeText(text);
      setCopied("Copied");
    } catch { setCopied("Copy blocked: open it instead"); }
    setTimeout(() => setCopied(""), 2000);
  }
  return (
    <MenuButton label={<><I.download />{copied || "Export"}</>} right>
      <div className="mh">Reports</div>
      <a href={`${base}/export.html`} target="_blank" rel="noreferrer"><I.file />Conformance report (one HTML file)</a>
      <a href={`${base}/export.html?download=true`}><I.download />Download the conformance report</a>
      <hr />
      <div className="mh">For Claude Code or a review</div>
      <button type="button" onClick={copySummary}><I.robot />Copy the summary (Markdown)</button>
      <a href={`${base}/summary.md`} target="_blank" rel="noreferrer"><I.file />Open the summary</a>
      <hr />
      <div className="mh">Files run_poc.sh wrote</div>
      {run.html && <a href={`${base}/report/html`} target="_blank" rel="noreferrer"><I.external />pytest HTML report</a>}
      <a href={`${base}/report/xml`} target="_blank" rel="noreferrer"><I.external />JUnit XML</a>
      {run.job && <a href={`/api/jobs/${encodeURIComponent(run.job.jobId)}/console.txt`} target="_blank" rel="noreferrer"><I.external />Console log</a>}
    </MenuButton>
  );
}

function RunHeader({ run, view, setView }: { run: RunFull; view: "results" | "charts"; setView: (v: "results" | "charts") => void }) {
  const j = run.job;
  return (
    <>
      <div className="rhead">
        <div className="rtile" aria-hidden="true">{tileText(run.target)}</div>
        <div className="ttl">
          <div className="eyebrow row" style={{ gap: 4 }}>Run on {run.target} · {run.id} <CopyButton text={run.id} label="Copy the run ID" /></div>
          <h1>{run.headline}</h1>
          <div className="sub">
            <span>{whenLong(run.started)} ({duration(run.seconds)})</span>
            <span>{run.source} run</span>
            {run.testbed && <span className="mono">{run.testbed}</span>}
            <Help label="About this run">
              <dl className="dl">
                <dt>Report</dt><dd>{run.report}</dd><dt>Container</dt><dd>{run.hostname || "not recorded"}</dd>
                <dt>Tests</dt><dd>{run.pocTests} PoC · {run.upstreamTests} upstream</dd>
                <dt>Compared with</dt><dd>{run.since?.previous ?? "nothing earlier on this target"}</dd>
              </dl>
              <p>The donut shows Pass out of the tests that ran (skipped tests left out). Expected gaps are not passes.</p>
            </Help>
          </div>
        </div>
        <Donut counts={run.counts} size={104} />
      </div>
      <div className="ractions">
        <span className="seg" role="group" aria-label="Report view">
          <button type="button" aria-pressed={view === "results"} onClick={() => setView("results")}><I.list style={{ width: 14, height: 14 }} />Results</button>
          <button type="button" aria-pressed={view === "charts"} onClick={() => setView("charts")}><I.chart style={{ width: 14, height: 14 }} />Charts</button>
        </span>
        <span className={`gate-chip r-${run.gate.passed ? "pass" : "fail"}`} title={run.gate.rules.filter((r) => !r.passed).map((r) => r.title).join("; ") || "Every rule passed"}>
          <StatusIcon r={run.gate.passed ? "pass" : "fail"} />Gate {run.gate.passed ? "passed" : `failed · ${run.gate.failed} of ${run.gate.total}`}
        </span>
        <span className="spacer" style={{ flex: 1 }} />
        <RerunMenu run={run} />
        <Link className="btn ghost" to="/compare" search={{ tab: "matrix" }} title="Compare targets"><I.compare /></Link>
        <ExportMenu run={run} />
      </div>
      {j && (
        <div className="jobmeta">
          <span>Started by {j.who} from the UI</span>
          <span className="mono">{j.commit ? `commit ${j.commit}${j.branch ? ` (${j.branch})` : ""}` : "commit not recorded"}</span>
          {j.dirty.length > 0 && <span className="warn" title={j.dirty.join(", ")}>+ uncommitted changes in {j.dirty.length} file{j.dirty.length === 1 ? "" : "s"}</span>}
          <span>{j.traffic ? "traffic on" : "traffic off"}{j.mld !== "auto" ? ` · MLD filter ${j.mld}` : ""}</span>
          {j.setSize > 1 && <span>Run {j.setIndex} of {j.setSize}</span>}
          {j.retry > 0 && <span>Retry failures: up to {j.retry}× · this is attempt {j.attempt}</span>}
        </div>
      )}
    </>
  );
}

function SinceBar({ run, setFilters, filters }: { run: RunFull; filters: Filters; setFilters: (f: Filters) => void }) {
  const m = run.marks;
  const items: [MarkFilter, string, number][] = [["regressed", "regressed", m.regressed], ["new_error", "new error", m.newError],
    ["fixed", "fixed", m.fixed], ["flaky", "flaky", m.flaky], ["new", "new", m.new]];
  const shown = items.filter(([, , n]) => n > 0);
  return (
    <div className="sincebar">
      <span>Against earlier runs on {run.target}:</span>
      {shown.length === 0 && <span className="faint">no changes</span>}
      {shown.map(([id, word, n]) => (
        <button key={id} type="button" className="chip" aria-pressed={filters.marks.length === 1 && filters.marks[0] === id}
          onClick={() => setFilters({ ...NO_FILTERS, marks: filters.marks.length === 1 && filters.marks[0] === id ? [] : [id] })}>
          {n} {word}
        </button>
      ))}
    </div>
  );
}

function RetriesBanner({ run }: { run: RunFull }) {
  const r = run.retries;
  if (!r) return null;
  const tests = Object.values(r.tests);
  const passedLater = tests.filter((a) => a[a.length - 1].result === "pass" && a[0].result !== "pass").length;
  return (
    <div className="banner info" style={{ marginTop: 12 }}>
      <b>Retry failures ({r.allowed}×):</b>{" "}
      {r.attempts.map((a, i) => (
        <span key={a.jobId}>{i > 0 && " → "}
          {a.current ? <b>attempt {a.attempt}</b> : a.runId
            ? <Link to="/runs/$runId" params={{ runId: a.runId }}>attempt {a.attempt}</Link>
            : <Link to="/jobs/$jobId" params={{ jobId: a.jobId }}>attempt {a.attempt} ({a.state})</Link>}
        </span>
      ))}
      {tests.length > 0 && <> · {tests.length} test{tests.length === 1 ? "" : "s"} retried, {passedLater} passed on a later attempt (marked Retried: check them for instability)</>}
    </div>
  );
}

function GatesTab({ run, onPick }: { run: RunFull; onPick: (key: string) => void }) {
  const byKey = new Map(run.tests.map((t) => [t.key, t]));
  return (
    <>
      <p className="section-note">
        Rules this run should meet to count as conforming. They're checked by the UI and change nothing in run_poc.sh.
        The rules come from <code>~/.config/sai-challenger-ui/gates.toml</code> when it exists, else the defaults.
      </p>
      {run.gate.note && <div className="banner warn">{run.gate.note}</div>}
      <div className="gates">
        {run.gate.rules.map((r) => (
          <div key={r.id}>
            <div className="gate">
              <StatusIcon r={r.passed ? "pass" : "fail"} />
              <span>{r.title}</span>
              <span className="actual">{r.actual}</span>
              <span className="want">wanted {r.expected}</span>
            </div>
            {!r.passed && r.keys.length > 0 && (
              <div className="gate-tests" style={{ paddingLeft: 32 }}>
                {r.keys.slice(0, 40).map((k) => {
                  const t = byKey.get(k);
                  return t ? <button key={k} type="button" className="chip" onClick={() => onPick(k)}><StatusIcon r={t.result} />{t.title}</button>
                    : <span key={k} className="tag mono">{k}</span>;
                })}
                {r.keys.length > 40 && <span className="faint small">and {r.keys.length - 40 + r.more} more</span>}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

function LogTab({ jobId }: { jobId: string }) {
  const q = useQuery({ queryKey: ["console", jobId], queryFn: async () => (await fetch(`/api/jobs/${encodeURIComponent(jobId)}/console.txt`)).text() });
  const [s, setS] = useState("");
  if (q.isPending) return <Loading what="the console log" />;
  if (q.error) return <Failed error={q.error} />;
  const lines = s ? (q.data ?? "").split("\n").filter((l) => l.toLowerCase().includes(s.toLowerCase())) : null;
  return (
    <>
      <div className="toolbar">
        <div className="searchbox" style={{ width: 320 }}><I.search /><input className="search" type="search" placeholder="Search the output" value={s} onChange={(e) => setS(e.target.value)} /></div>
        {lines && <span className="faint small">{lines.length} matching lines</span>}
        <span className="spacer" />
        <a className="btn ghost" href={`/api/jobs/${encodeURIComponent(jobId)}/console.txt`} target="_blank" rel="noreferrer"><I.external />Open as text</a>
      </div>
      <pre className="logbox">{lines ? lines.join("\n") : q.data || "No output."}</pre>
    </>
  );
}

function ChartsView({ run }: { run: RunFull }) {
  const q = useCharts(run.id);
  if (q.isPending) return <Loading what="the charts" />;
  if (q.error || !q.data) return <Failed error={q.error} />;
  const c = q.data;
  const { pass, ran } = passRate(run.counts);
  return (
    <div className="charts">
      <div className="chart-card">
        <h2>Current status <span className="sub">this run</span></h2>
        <div className="row" style={{ justifyContent: "center", padding: "8px 0 16px" }}>
          <Donut counts={run.counts} size={188} stroke={18} />
        </div>
        <div className="stats" style={{ justifyContent: "center", border: 0, margin: 0, paddingBottom: 8 }}>
          <Ticks counts={run.counts} />
        </div>
        <p className="faint small" style={{ margin: 0, textAlign: "center" }}>{pass} of {ran} tests that ran pass{run.counts.skipped ? ` · ${run.counts.skipped} skipped` : ""}</p>
      </div>
      <div className="chart-card">
        <h2>Status dynamics <span className="sub">last {c.dynamics.length} PoC runs on {run.target}</span></h2>
        <StatusDynamics data={c.dynamics} />
      </div>
      <div className="chart-card">
        <h2>Status transitions <span className="sub">each run against the one before</span></h2>
        {c.dynamics.filter((d) => d.compared).length ? <Transitions data={c.dynamics} /> : <Empty>No earlier run to compare with.</Empty>}
      </div>
      <div className="chart-card">
        <h2>Stability by track <span className="sub">same result in the last 10 runs</span></h2>
        {c.stability.length ? <Stability data={c.stability} /> : <Empty>Nothing ran.</Empty>}
      </div>
      <div className="chart-card">
        <h2>Run time <span className="sub">each run on {run.target}</span></h2>
        <RunTimes data={c.dynamics} />
      </div>
      <div className="chart-card">
        <h2>Test durations <span className="sub">this run, skipped left out</span></h2>
        {c.durations.length ? <DurationHistogram seconds={c.durations} /> : <Empty>No durations.</Empty>}
      </div>
    </div>
  );
}

export function useListKeys(enabled: boolean, keys: string[], selected: string | null, select: (k: string) => void, searchRef: React.RefObject<HTMLInputElement | null>) {
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.closest("input, textarea, select, [contenteditable]") || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "/") { e.preventDefault(); searchRef.current?.focus(); return; }
      if (e.key !== "j" && e.key !== "k") return;
      const i = selected ? keys.indexOf(selected) : -1;
      const next = e.key === "j" ? Math.min(keys.length - 1, i + 1) : Math.max(0, i - 1);
      if (keys[next] && keys[next] !== selected) {
        e.preventDefault();
        select(keys[next]);
        requestAnimationFrame(() => document.querySelector(`[data-key="${CSS.escape(keys[next])}"]`)?.scrollIntoView({ block: "nearest" }));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled, keys, selected, select, searchRef]);
}

export function RunPage({ runId, search }: { runId: string; search: RunSearch }) {
  const q = useRun(runId);
  const navigate = useNavigate();
  const [layout, setLayout] = useLocal<"split" | "full">("layout", "split", ["split", "full"]);
  const [groupBy, setGroupBy] = useLocal<GroupBy>("groupby", "result", ["result", "track", "file"]);
  const [sortBy, setSortBy] = useLocal<SortBy>("sortby", "order", ["order", "name", "duration", "status"]);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const searchRef = useRef<HTMLInputElement>(null);
  const view = search.view ?? "results";
  const tab = search.tab ?? "results";
  const selected = search.t ?? null;
  const go = (patch: RunSearch, replace = true) => navigate({ to: "/runs/$runId", params: { runId }, search: { ...search, ...patch }, replace });
  const select = (key: string | null) => go({ t: key ?? undefined, view: "results" }, false);

  const run = q.data;
  const tests = run?.tests ?? [];
  const tree = useMemo(() => (run ? buildTree(tests.filter((t) => !t.upstream || filters.q).filter((t) => matches(t, filters, run.causes, run.retries)),
    tab === "causes" ? "cause" : groupBy, sortBy, run.causes) : []), [run, tests, filters, groupBy, sortBy, tab]);
  const order = useMemo(() => flatLeaves(tree).map((t) => t.key), [tree]);
  useListKeys(!!run && view === "results", order, selected, (k) => go({ t: k }), searchRef);

  // A selected test always shows: open the first one that needs attention when the page opens in split view.
  useEffect(() => {
    if (!run || selected || layout !== "split" || view !== "results") return;
    const first = run.tests.find((t) => ATTENTION.includes(t.result)) ?? run.tests.find((t) => t.result === "expected_gap");
    if (first) go({ t: first.key });
  }, [run?.id, layout]); // eslint-disable-line react-hooks/exhaustive-deps

  if (q.isPending) return <div className="card"><Loading what="the run" /></div>;
  if (q.error || !run) return <div className="card"><Failed error={q.error} /></div>;
  const row = selected ? tests.find((t) => t.key === selected) : undefined;
  const idx = selected ? order.indexOf(selected) : -1;
  const nav = {
    index: Math.max(idx, 0), total: order.length,
    prev: idx > 0 ? () => go({ t: order[idx - 1] }) : null,
    next: idx >= 0 && idx < order.length - 1 ? () => go({ t: order[idx + 1] }) : null,
  };
  const attentionCount = tests.filter((t) => ATTENTION.includes(t.result)).length;
  const pocTests = tests.filter((t) => !t.upstream);
  const showDetail = !!selected && !!row && view === "results";

  const crumbs: Crumb[] = [{ label: "Runs", to: "/runs" }, { label: `${run.target} · ${whenLong(run.started)}`, to: "/runs/$runId", params: { runId }, search: {} }];
  if (showDetail && row) crumbs.push({ label: row.tag }, { label: row.title });

  const list = (
    <>
      <div className="stats">
        <div className="stat"><span className="k">Total</span><span className="v">{pocTests.length}</span></div>
        <div className="stat"><span className="k">New tests</span><span className="v"><I.plusCircle />{run.marks.new}</span></div>
        <span className="spacer" />
        <Ticks counts={run.counts} order={GROUP_ORDER}
          onPick={(r) => setFilters({ ...filters, status: statusOf(r) })} />
      </div>
      <div className="rstrip"><Strip cells={run.strip} letters onPick={(i) => { const t = tests[i]; if (t) go({ t: t.key }); }} /></div>
      <SinceBar run={run} filters={filters} setFilters={setFilters} />
      <div className="searchbox"><I.search />
        <input ref={searchRef} className="search" type="search" placeholder="Search tests by title, ID or message  ( / )" value={filters.q}
          onChange={(e) => setFilters({ ...filters, q: e.target.value })} aria-label="Search tests" />
      </div>
      <FilterRow run={run} filters={filters} setFilters={setFilters} groupBy={groupBy} setGroupBy={setGroupBy} sortBy={sortBy} setSortBy={setSortBy} />
      <div className="row wrap" style={{ marginBottom: 12, gap: 8 }}>
        <StatusChips tests={pocTests} value={filters.status} onChange={(status) => setFilters({ ...filters, status })} />
        {(filters !== NO_FILTERS && JSON.stringify(filters) !== JSON.stringify(NO_FILTERS)) && (
          <button type="button" className="linkbtn small" onClick={() => setFilters(NO_FILTERS)}>Clear filters</button>
        )}
      </div>
      <TestTree tests={tests} groupBy={groupBy} sortBy={sortBy} filters={filters} causes={run.causes} retries={run.retries}
        selected={selected} onSelect={(k) => go({ t: k }, false)} />
    </>
  );

  const causesList = (
    <>
      <p className="section-note">Failures, errors and gaps grouped by why they happened: a known signature from hints.toml, the SAI status
        the message names, a packet that did or didn't arrive, else the message itself.</p>
      {run.causes.length === 0 ? <Empty icon={<I.check />}>Nothing failed, errored or was recorded as a gap.</Empty> : (
        <TestTree tests={tests} groupBy="cause" sortBy={sortBy} filters={filters} causes={run.causes} retries={run.retries}
          selected={selected} onSelect={(k) => go({ t: k }, false)} />
      )}
    </>
  );

  const main = (
    <div className="card">
      <RunHeader run={run} view={view} setView={(v) => go({ view: v, t: v === "charts" ? undefined : selected ?? undefined })} />
      <RetriesBanner run={run} />
      <div style={{ marginTop: 20 }} />
      {view === "charts" ? null : (
        <Tabs.Root value={tab} onValueChange={(v) => go({ tab: v as RunSearch["tab"] })}>
          <Tabs.List className="tabs" aria-label="Run views">
            <Tabs.Trigger value="results">Results <span className={`count${attentionCount ? " bad" : ""}`}>{pocTests.length}</span></Tabs.Trigger>
            <Tabs.Trigger value="causes">Causes <span className="count">{run.causes.length}</span></Tabs.Trigger>
            <Tabs.Trigger value="gates">Gates <span className={`count ${run.gate.passed ? "good" : "bad"}`}>{run.gate.total - run.gate.failed}/{run.gate.total}</span></Tabs.Trigger>
            {run.job && <Tabs.Trigger value="log">Run log</Tabs.Trigger>}
          </Tabs.List>
          <Tabs.Content value="results">{list}</Tabs.Content>
          <Tabs.Content value="causes">{causesList}</Tabs.Content>
          <Tabs.Content value="gates"><GatesTab run={run} onPick={(k) => go({ t: k, tab: "results" }, false)} /></Tabs.Content>
          {run.job && <Tabs.Content value="log"><LogTab jobId={run.job.jobId} /></Tabs.Content>}
        </Tabs.Root>
      )}
    </div>
  );

  const detail = showDetail && row ? (
    <TestDetail runId={run.id} target={run.target} testKey={row.key} row={row} nav={nav} retries={run.retries} onOpen={(k) => go({ t: k }, false)} />
  ) : null;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <Crumbs items={crumbs} />
        <span className="row" style={{ gap: 4 }}>
          <span className="faint small">Layout</span>
          <span className="seg" role="group" aria-label="Layout">
            <button type="button" aria-pressed={layout === "split"} onClick={() => setLayout("split")} title="List and test side by side"><I.split style={{ width: 14, height: 14 }} /></button>
            <button type="button" aria-pressed={layout === "full"} onClick={() => setLayout("full")} title="One at a time, full width"><I.full style={{ width: 14, height: 14 }} /></button>
          </span>
        </span>
      </div>
      {view === "charts" ? (
        <>{main}<div style={{ marginTop: 16 }}><ChartsView run={run} /></div></>
      ) : layout === "split" ? (
        <div className="split">
          {main}
          <div className="card pane" aria-live="polite">
            {detail ?? <div className="pane-empty"><div><I.list style={{ width: 24, height: 24 }} /><div>Pick a test to see what happened.</div><div className="xs">j / k move through the list</div></div></div>}
          </div>
        </div>
      ) : detail ? (
        <div className="card">
          <button type="button" className="btn ghost sm" onClick={() => select(null)} style={{ marginBottom: 12 }}><I.chevronRight style={{ transform: "rotate(180deg)" }} />Back to the list</button>
          {detail}
        </div>
      ) : main}
    </>
  );
}
