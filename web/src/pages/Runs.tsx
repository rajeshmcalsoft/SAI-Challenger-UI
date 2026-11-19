// Runs (design §6.5): every run_poc.sh report, newest first, grouped by day with a status bar per day.
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useJobs, useRuns, type RunSummary } from "../api";
import { I } from "../icons";
import { Failed, Help, Loading, PillBar, StatusIcon, Strip, clock, day, duration } from "../ui";
import { ATTENTION, worst, type Result } from "../vocab";

function statusOf(r: RunSummary): Result {
  const bad = worst(ATTENTION.filter((x) => r.counts[x]));
  if (bad) return bad;
  if (r.counts.expected_gap) return "expected_gap";
  if (r.counts.pass) return "pass";
  return "skipped";
}

export function RunsPage() {
  const [target, setTarget] = useState("");
  const [attention, setAttention] = useState(false);
  const [limit, setLimit] = useState(30);
  const runs = useRuns(target, attention, limit);
  const jobs = useJobs();
  const active = (jobs.data?.active ?? []).filter((j) => !target || j.target === target);

  const byDay: [string, RunSummary[]][] = [];
  for (const r of runs.data?.runs ?? []) {
    const d = day(r.started);
    if (byDay.length && byDay[byDay.length - 1][0] === d) byDay[byDay.length - 1][1].push(r);
    else byDay.push([d, [r]]);
  }
  const sum = (list: RunSummary[]) => {
    const c: Partial<Record<Result, number>> = {};
    for (const r of list) {
      const s = statusOf(r);
      c[s] = (c[s] ?? 0) + 1;
    }
    return c;
  };

  return (
    <>
      <div className="page-head">
        <h1>Runs</h1>
        <Help label="About the Runs page">
          <p>Every run_poc.sh run is a run here: the UI reads each &lt;target&gt;-&lt;stamp&gt;.xml in tests/poc/reports, so CLI runs
            appear without any import step. The list refreshes on its own.</p>
          <p>The bar next to each day counts runs by their worst result. Nothing here is ever deleted: reports are evidence.</p>
        </Help>
      </div>
      <div className="card">
        <div className="toolbar">
          <span className="seg" role="group" aria-label="Target">
            <button type="button" aria-pressed={target === ""} onClick={() => setTarget("")}>All targets</button>
            {(runs.data?.targets ?? []).map((t) => <button key={t} type="button" aria-pressed={target === t} onClick={() => setTarget(t)}>{t}</button>)}
          </span>
          <button className="btn ghost" type="button" aria-pressed={attention} onClick={() => setAttention(!attention)}><I.bug />Needs attention</button>
          <span className="spacer" />
          {runs.data && <span className="faint small">{runs.data.matching} matching runs · {runs.data.total} in all</span>}
        </div>
        {active.length > 0 && (
          <>
            <div className="dayhead">Running and queued <span className="count">{active.length}</span></div>
            {active.map((j) => (
              <Link key={j.id} className="rrow" to="/jobs/$jobId" params={{ jobId: j.id }}>
                <span className="spinner" aria-hidden="true" />
                <span className="time">{clock(j.started ?? j.created)}</span>
                <span className="tgt">{j.target}</span>
                <span className="what">{j.what}{j.setSize > 1 ? ` · run ${j.setIndex} of ${j.setSize}` : ""}</span>
                <span className="res">
                  <span className="hl">{j.state === "running" ? `Running · ${j.done} of ${j.total}` : "Queued"}</span>
                  {j.current && <span className="faint small">{j.current}</span>}
                </span>
                <span className="origin">UI</span>
                <span className="dur">{j.state === "running" ? duration(j.seconds) : ""}</span>
              </Link>
            ))}
          </>
        )}
        {runs.isPending && <Loading what="runs" />}
        {runs.error && <Failed error={runs.error} />}
        {byDay.map(([d, list]) => (
          <div key={d}>
            <div className="dayhead">{d} <span className="faint">{list.length} run{list.length === 1 ? "" : "s"}</span><span className="spacer" /><PillBar counts={sum(list)} width={140} /></div>
            {list.map((r) => (
              <Link key={r.id} className="rrow" to="/runs/$runId" params={{ runId: r.id }} search={{}}>
                <StatusIcon r={statusOf(r)} />
                <span className="time">{clock(r.started)}</span>
                <span className="tgt">{r.target}</span>
                <span className="what">{r.what}</span>
                <span className="res"><span className="hl">{r.headline}</span><Strip cells={r.strip} fit /></span>
                <span className="origin">{r.source}</span>
                <span className="dur">{duration(r.seconds)}</span>
              </Link>
            ))}
          </div>
        ))}
        {runs.data && runs.data.runs.length < runs.data.matching && (
          <div className="row" style={{ justifyContent: "center", marginTop: 16 }}>
            <span className="faint small">Showing {runs.data.runs.length} of {runs.data.matching}</span>
            <button className="btn sm" type="button" onClick={() => setLimit(limit + 50)}>Show 50 more</button>
          </div>
        )}
      </div>
    </>
  );
}
