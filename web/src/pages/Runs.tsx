import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useJobs, useRuns, type RunSummary } from "../api";
import { Failed, Help, Loading, Strip, clock, day, duration } from "../ui";

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

  return (
    <section className="section">
      <div className="page-head">
        <h1>
          Runs{" "}
          <Help label="About the Runs page">
            <p>Every run_poc.sh run is a run here: the UI reads each &lt;target&gt;-&lt;stamp&gt;.xml in tests/poc/reports,
              so CLI runs appear without any import step. The list refreshes on its own.</p>
            <p>Nothing here is ever deleted: reports are evidence.</p>
          </Help>
        </h1>
      </div>
      <div className="toolbar">
        <button className="chip" type="button" aria-pressed={target === ""} onClick={() => setTarget("")}>All targets</button>
        {(runs.data?.targets ?? []).map((t) => (
          <button key={t} className="chip" type="button" aria-pressed={target === t} onClick={() => setTarget(t)}>{t}</button>
        ))}
        <button className="chip" type="button" aria-pressed={attention} onClick={() => setAttention(!attention)}>Needs attention</button>
      </div>
      {active.length > 0 && (
        <div>
          <div className="day">Running and queued</div>
          <div className="list">
            {active.map((j) => (
              <Link key={j.id} className="run-row" to="/jobs/$jobId" params={{ jobId: j.id }}>
                <span className="time">{clock(j.started ?? j.created)}</span>
                <span className="target">{j.target}</span>
                <span className="what">{j.what}{j.setSize > 1 ? ` · run ${j.setIndex} of ${j.setSize}` : ""}</span>
                <span className="res">
                  <span>{j.state === "running" ? `Running · ${j.done} of ${j.total}` : "Queued"}</span>
                  {j.current && <span className="faint small">{j.current}</span>}
                </span>
                <span className="src">UI</span>
                <span className="dur">{j.state === "running" ? duration(j.seconds) : ""}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
      {runs.isPending && <Loading what="runs" />}
      {runs.error && <Failed error={runs.error} />}
      {byDay.map(([d, list]) => (
        <div key={d}>
          <div className="day">{d}</div>
          <div className="list">
            {list.map((r) => (
              <Link key={r.id} className="run-row" to="/runs/$runId" params={{ runId: r.id }}>
                <span className="time">{clock(r.started)}</span>
                <span className="target">{r.target}</span>
                <span className="what">{r.what}</span>
                <span className="res"><span>{r.headline}</span><Strip cells={r.strip} fit /></span>
                <span className="src">{r.source}</span>
                <span className="dur">{duration(r.seconds)}</span>
              </Link>
            ))}
          </div>
        </div>
      ))}
      {runs.data && (
        <p className="section-note" style={{ marginTop: "var(--s-5)" }}>
          Showing {runs.data.runs.length} of {runs.data.matching} matching runs ({runs.data.total} in all).{" "}
          {runs.data.runs.length < runs.data.matching && (
            <button className="btn sm" type="button" onClick={() => setLimit(limit + 50)}>Show 50 more</button>
          )}
        </p>
      )}
    </section>
  );
}
