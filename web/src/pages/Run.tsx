import { Link } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import { useDetail, useRun, type Entry, type RunFull, type TestRow } from "../api";
import { useRunSheet } from "../RunSheet";
import { Dl, Failed, Glyph, Help, Loading, ReadOnlyNote, Strip, duration, when } from "../ui";
import { ATTENTION, GLYPH, GROUP_NOTE, GROUP_TITLE, LABEL, RESULT_HELP, type Result } from "../vocab";

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function RowAction({ t }: { t: TestRow }) {
  let act: ReactNode = null;
  if (t.result === "fail") act = <button className="btn sm" type="button" disabled title="Comes with gap editing">Add expected gap</button>;
  else if (t.result === "gap_passes") act = <button className="btn sm" type="button" disabled title="Comes with gap editing">Remove gap</button>;
  else if (t.result === "expected_gap") act = <span className="reason" title={t.message}>{t.message}</span>;
  return <>{t.cleanupFailed && t.result !== "cleanup_error" && <span className="warn small">Cleanup failed </span>}{act}</>;
}

type RunRef = { id: string; target: string; live: boolean };

function DetailPanel({ run, t }: { run: RunRef; t: TestRow }) {
  const d = useDetail(run.id, t.key, !run.live);
  if (run.live) {
    return (
      <div className="detail">
        <div className="k">While live</div>
        <div className="v muted">{t.message || "No message yet."} What it checks, what happened and the source come from the JUnit report when the run ends.</div>
      </div>
    );
  }
  if (d.isPending) return <div className="detail"><span className="muted">Loading…</span></div>;
  if (d.error || !d.data) return <div className="detail"><Failed error={d.error} /></div>;
  const x = d.data;
  return (
    <div className="detail">
      <div className="k">What it checks</div>
      <div className="v">{x.purpose ?? <span className="faint">No description in the test</span>}</div>
      {x.happened && <><div className="k">What happened</div><div className="v">{x.happened}</div></>}
      {t.result === "expected_gap" && (
        <>
          <div className="k">Recorded as</div>
          <div className="v">
            {x.recorded ? <>{x.recorded.reason}<br /><span className="faint small">Pattern </span><code>{x.recorded.pattern}</code></> : (
              <>{t.message}<br /><span className="warn small">⚠ Not in the current {run.target}.json: xfail was called inside the test. Gaps belong in the profile.</span></>
            )}
          </div>
        </>
      )}
      {x.hint && (
        <>
          <div className="k">Hint</div>
          <div className="v"><div className="hint"><span>{x.hint.text}</span>{x.hint.action && <button className="btn sm" type="button" disabled>{x.hint.action}</button>}</div></div>
        </>
      )}
      {x.location && (
        <>
          <div className="k">Where</div>
          <div className="v">
            <code>{x.location}</code>
            {x.source.length > 0 && (
              <>
                {" "}<span className="faint small">· source as it is now</span>
                <pre>{x.source.map((l) => <span key={l.n} className={l.hl ? "ln hl" : "ln"}>{`${String(l.n).padStart(4)}  ${l.text}`}</span>)}</pre>
              </>
            )}
          </div>
        </>
      )}
      {x.raw && (
        <>
          <div className="k">Raw detail</div>
          <div className="v"><details><summary>Show the text pytest wrote</summary><pre>{x.raw}</pre></details></div>
        </>
      )}
    </div>
  );
}

function TestItem({ run, t, startOpen }: { run: RunRef; t: TestRow; startOpen: boolean }) {
  const [open, setOpen] = useState(startOpen);
  return (
    <details open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="trow">
        <Glyph r={t.result} />
        <span className="t-main"><span className="t-title">{t.title}</span><span className="t-id mono">{t.name}</span></span>
        <span className="t-track">{t.tag}</span>
        <span className="t-dur">{run.live ? "" : `${t.seconds.toFixed(1)}s`}</span>
        <span className="t-act"><RowAction t={t} /></span>
      </summary>
      {open && <DetailPanel run={run} t={t} />}
    </details>
  );
}

function ScenarioItem({ e }: { e: Extract<Entry, { kind: "scenario" }> }) {
  return (
    <details>
      <summary className="trow">
        <Glyph r={e.result} />
        <span className="t-main">
          <span className="t-title">{e.title} <span className="faint">· {e.steps.length} steps</span></span>
          <span className="t-sub">
            <span className="steps">
              {e.steps.map((s) => <span key={s.key} className={`s ${s.result}`} title={`${LABEL[s.result]}: ${s.title}`}>{s.step ?? "?"} {GLYPH[s.result]}</span>)}
            </span>
            <span className="sentence">{e.sentence}</span>
          </span>
        </span>
        <span className="t-track">{e.tag}</span>
        <span className="t-dur">{e.steps.some((s) => s.seconds > 0) ? `${e.steps.reduce((n, s) => n + s.seconds, 0).toFixed(1)}s` : ""}</span>
        <span className="t-act" />
      </summary>
      <div className="detail" style={{ display: "block" }}>
        <div className="step-list">
          {e.steps.map((s) => [
            <span key={`${s.key}-n`} className="mono small"><Glyph r={s.result} /> {s.step}</span>,
            <span key={`${s.key}-t`}>
              {s.title.split(": ").slice(1).join(": ") || s.title}
              {s.message && s.result !== "pass" && <><br /><span className="muted small">{s.message.split("\n")[0].slice(0, 140)}</span></>}
            </span>,
          ])}
        </div>
      </div>
    </details>
  );
}

function RerunMenu({ run }: { run: RunFull }) {
  const openSheet = useRunSheet();
  const poc = run.groups.flatMap((g) => g.entries).flatMap((e) => (e.kind === "test" ? [e.test] : e.kind === "scenario" ? e.steps : []))
    .filter((t) => !t.upstream && t.name !== "(collection)");
  const keys = (rows: TestRow[]) => rows.map((t) => [t.module, t.cls, t.name].filter(Boolean).join("::"));
  const failing = poc.filter((t) => ATTENTION.includes(t.result));
  return (
    <details className="menu">
      <summary className="btn sm">Rerun ▾</summary>
      <div className="menu-list" role="menu">
        <button type="button" role="menuitem" onClick={() => openSheet({ targets: [run.target], what: "pick", tests: keys(poc) })}
          disabled={!poc.length}>The same {poc.length} tests on {run.target}…</button>
        <button type="button" role="menuitem" onClick={() => openSheet({ targets: [run.target], what: "pick", tests: keys(failing) })}
          disabled={!failing.length}>Only what needs attention ({failing.length})…</button>
        <button type="button" role="menuitem" onClick={() => openSheet({ targets: [run.target], what: "full" })}>Full PoC suite on {run.target}…</button>
      </div>
    </details>
  );
}

function JobMetaLine({ run }: { run: RunFull }) {
  const j = run.job;
  if (!j) return <div className="faint">Commit, command and log aren't recorded for CLI runs.</div>;
  const opts = [j.traffic ? "traffic on" : "traffic off", j.mld !== "auto" ? `MLD filter ${j.mld}` : null].filter(Boolean).join(" · ");
  return (
    <>
      <div className="items">
        <span>Started by {j.who} from the UI</span>
        <span className="mono">{j.commit ? `commit ${j.commit}${j.branch ? ` (${j.branch})` : ""}` : "commit not recorded"}</span>
        {j.dirty.length > 0 && (
          <span className="warn">
            + uncommitted changes{" "}
            <Help label="Uncommitted changes at start">
              <p>Files under tests/poc and scripts/poc that differed from the commit when this run started:</p>
              <p className="mono small">{j.dirty.slice(0, 12).join(", ")}{j.dirty.length > 12 ? ` and ${j.dirty.length - 12} more` : ""}</p>
            </Help>
          </span>
        )}
        <span>{opts}</span>
        {j.setSize > 1 && <span>Run {j.setIndex} of {j.setSize}</span>}
      </div>
      <details className="cmd inline">
        <summary>Command</summary>
        <code>{j.command}</code>
      </details>
    </>
  );
}

export function RunPage({ runId }: { runId: string }) {
  const q = useRun(runId);
  if (q.isPending) return <section className="section"><Loading what="the run" /></section>;
  if (q.error || !q.data) return <section className="section"><Failed error={q.error} /></section>;
  const run = q.data;
  const ref = { id: run.id, target: run.target, live: false };
  const firstAttention = run.groups.flatMap((g) => g.entries).find((e) => e.kind === "test" && ATTENTION.includes(e.test.result));
  const openKey = firstAttention?.kind === "test" ? firstAttention.test.key : null;

  return (
    <section className="section">
      <div className="eyebrow">
        Run on {run.target} · <span className="mono">{run.id}</span>{" "}
        <Help label="About this run">
          <Dl rows={[
            ["Report", run.report],
            ["Started", run.started],
            ["Container", run.hostname || "not recorded"],
            ["Tests", `${run.pocTests} PoC · ${run.upstreamTests} upstream`],
            ["Compared with", run.since?.previous ?? "nothing earlier on this target"],
          ]} />
          <p>The headline lists what needs attention first: failures, then errors, then gaps that now pass. Each count below it jumps to its group.</p>
        </Help>
      </div>
      <div className="run-head">
        <div className="headline">{run.headline}</div>
        <div className="actions">
          <RerunMenu run={run} />
          <Link className="btn sm" to="/compare" search={{ tab: "matrix" }} style={{ display: "inline-flex", alignItems: "center" }}>Compare…</Link>
          {run.html && <a className="btn sm" href={`/api/runs/${encodeURIComponent(run.id)}/report/html`} target="_blank" rel="noreferrer" style={{ display: "inline-flex", alignItems: "center" }}>pytest HTML</a>}
          {run.job && <a className="btn sm" href={`/api/jobs/${encodeURIComponent(run.job.jobId)}/console.txt`} target="_blank" rel="noreferrer" style={{ display: "inline-flex", alignItems: "center" }}>Console log</a>}
        </div>
        <div className="counts">
          {run.countParts.map(([r, text], i) => (
            <span key={r}>
              {i > 0 && <span className="sepdot">·</span>}
              <a href={`#grp-${r}`} onClick={(ev) => { ev.preventDefault(); scrollTo(`grp-${r}`); }}>{text}</a>
            </span>
          ))}
        </div>
        <div className="strip-wrap">
          <Strip cells={run.strip} letters />{" "}
          <Help label="How to read the strip">
            <p>One cell per test, in the order the suite ran them. A gap separates tracks, and the letter under each block names it: A L2 &amp; VLANs, B L3 routing, C ACL and counters, F framework. Hover a cell for its test.</p>
            <p>Colour and fill: green pass, red fail, amber expected gap, violet gap now passes, white error, hollow skipped.</p>
          </Help>
        </div>
        <div className="meta">
          <div className="items">
            <span><b>{run.target}</b> · {run.testbed}</span>
            <span>Started {when(run.started)}</span>
            <span>Took {duration(run.seconds)}</span>
            <span>{run.source} run</span>
          </div>
          <JobMetaLine run={run} />
        </div>
      </div>
      {run.since?.changed && (
        <p className="since">
          Since previous run on {run.target} ({when(run.since.previousStarted)}):{" "}
          <Link to="/runs/$runId" params={{ runId: run.since.previous }}>{run.since.text}</Link>
        </p>
      )}
      <div style={{ marginTop: "var(--s-5)" }}><ReadOnlyNote /></div>
      {run.groups.map((g) => <Group key={g.result} run={ref} result={g.result} count={g.count} entries={g.entries} openKey={openKey} />)}
    </section>
  );
}

export function Group({ run, result, count, entries, openKey }: { run: RunRef; result: Result; count: number; entries: Entry[]; openKey: string | null }) {
  const list = (
    <div className="list">
      {entries.map((e, i) => {
        if (e.kind === "test") return <TestItem key={e.test.key} run={run} t={e.test} startOpen={e.test.key === openKey} />;
        if (e.kind === "scenario") return <ScenarioItem key={`sc-${i}`} e={e} />;
        return <div key={`${e.kind}-${i}`} className={e.kind === "note" ? "note" : "subhead"}>{e.text}</div>;
      })}
    </div>
  );
  return (
    <section className="group" id={`grp-${result}`}>
      <div className="group-head">
        <span className="title">{GROUP_TITLE[result]} <span className="count">{count}</span></span>
        <Help label={`About ${GROUP_TITLE[result]}`}><p>{RESULT_HELP[result]}</p></Help>
        {GROUP_NOTE[result] && <span className="meaning">{GROUP_NOTE[result]}</span>}
      </div>
      {result === "pass" ? <details><summary className="show-more">Show {count} passing tests</summary>{list}</details> : list}
    </section>
  );
}
