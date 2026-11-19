// One test in one run (C1–C6): header with the full ID and prev/next (A5), result block with the diff viewer (C4),
// labels (C5), the scenario's steps (C6), and History (C2) and Targets (C3) tabs.
import * as Tabs from "@radix-ui/react-tabs";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTestPage, type Retries, type TestPage, type TestRow } from "../api";
import { I } from "../icons";
import { useRunSheet } from "../RunSheet";
import { CopyButton, Failed, MarkChips, MiniStrip, StatusIcon, StatusPill, dur, when } from "../ui";
import { ATTENTION, LABEL, RESULT_HELP } from "../vocab";
import { DiffModal } from "./DiffModal";
import { GapNoteEditor } from "./GapNote";

export type Nav = { index: number; total: number; prev: (() => void) | null; next: (() => void) | null };

function ResultBlock({ p, target, onDiff }: { p: TestPage; target: string; onDiff: () => void }) {
  const t = p.test;
  const [raw, setRaw] = useState(false);
  if (t.result === "pass") return null;
  if (t.result === "expected_gap") {
    return (
      <div className="block r-expected_gap">
        <div className="bt">Expected gap: recorded in {target}.json</div>
        <div className="bt-sub">{p.recorded?.reason ?? t.message}</div>
        {p.recorded && <div className="faint small" style={{ marginTop: 4 }}>Pattern <code>{p.recorded.pattern}</code></div>}
        {!p.recorded && <div className="warn small" style={{ marginTop: 4 }}>Not in the current {target}.json: xfail was called inside the test. Gaps belong in the profile.</div>}
        {t.gap && <div style={{ marginTop: 8 }}><GapNoteEditor target={target} pattern={t.gap.pattern} note={t.gap.note} /></div>}
        <div className="actions">{p.diff && <button type="button" className="btn sm flat" onClick={onDiff}>Show difference</button>}</div>
      </div>
    );
  }
  if (t.result === "skipped") {
    return (
      <div className="block r-skipped">
        <div className="bt">Skipped</div>
        <div className="bt-sub">{t.message || "No reason given"}</div>
      </div>
    );
  }
  const title = p.happened ?? (t.message.split("\n")[0] || LABEL[t.result]);
  return (
    <div className={`block r-${t.result}`}>
      <div className="bt">{title}</div>
      {t.message && <pre>{t.message}</pre>}
      <span className="copy"><CopyButton text={t.message || title} label="Copy the message" /></span>
      <div className="actions">
        {p.diff && <button type="button" className="btn sm flat" onClick={onDiff}>Show difference</button>}
        {p.raw && <button type="button" className="btn sm ghost" onClick={() => setRaw(!raw)}>{raw ? "Hide" : "Show"} the full text pytest wrote</button>}
      </div>
      {raw && <div className="raw"><pre>{p.raw}</pre></div>}
      {t.result === "gap_passes" && t.gap && <div style={{ marginTop: 8 }} className="small">Recorded as: {t.gap.reason} <code>{t.gap.pattern}</code></div>}
    </div>
  );
}

function Steps({ p, onOpen }: { p: TestPage; onOpen: (key: string) => void }) {
  const steps = p.steps ?? [];
  const [open, setOpen] = useState<Record<string, boolean>>({});
  if (!steps.length) return null;
  const total = steps.reduce((n, s) => n + s.seconds, 0);
  return (
    <div className="section">
      <div className="sh"><I.play style={{ width: 14, height: 14 }} /><h3>{p.scenario}</h3><span className="count">{steps.length}</span>
        <span className="spacer" /><span className="faint small">{dur(total)}</span></div>
      <div className="steptree">
        {steps.map((s) => {
          const bad = ATTENTION.includes(s.result) || (s.result === "skipped" && !!s.message);
          const isOpen = open[s.key] ?? ATTENTION.includes(s.result);
          return (
            <div key={s.key}>
              <div className={`step${s.key === p.test.key ? " current" : ""}`} aria-expanded={isOpen} role="button" tabIndex={0}
                onClick={() => setOpen({ ...open, [s.key]: !isOpen })}
                onKeyDown={(e) => { if (e.key === "Enter") setOpen({ ...open, [s.key]: !isOpen }); }}>
                {bad ? <I.chevron className="chev" /> : <span />}
                <StatusIcon r={s.result} />
                <span className="n">{s.step}</span>
                <span className="ellipsis">{s.title.replace(/^Step \d+: /, "")}{s.needs.length > 0 && <span className="needs"> · needs {s.needs.join(", ")}</span>}</span>
                <span>{s.key !== p.test.key && <button type="button" className="linkbtn xs step-open" onClick={(e) => { e.stopPropagation(); onOpen(s.key); }}>Open</button>}</span>
                <span className="dur">{dur(s.seconds)}</span>
              </div>
              {isOpen && bad && (
                <div className="step-body small">
                  {s.happened && <div style={{ fontWeight: 700 }}>{s.happened}</div>}
                  <div className="muted" style={{ whiteSpace: "pre-wrap" }}>{s.message.split("\n").slice(0, 6).join("\n")}</div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Overview({ p, target, retries, onOpen }: { p: TestPage; target: string; retries?: Retries | null; onOpen: (key: string) => void }) {
  const [diffOpen, setDiffOpen] = useState(false);
  const attempts = retries?.tests[p.test.key];
  return (
    <>
      <ResultBlock p={p} target={target} onDiff={() => setDiffOpen(true)} />
      {p.hint && (
        <div className="section">
          <div className="hint"><span><b>Hint:</b> {p.hint.text}</span>{p.hint.action && <button className="btn sm" type="button" disabled title="Comes with the action buttons">{p.hint.action}</button>}</div>
        </div>
      )}
      {attempts && attempts.length > 1 && (
        <div className="section">
          <div className="sh"><I.retry style={{ width: 14, height: 14 }} /><h3>Retries</h3><span className="count">{attempts.length}</span></div>
          <div className="hrows">
            {attempts.map((a) => (
              <div key={a.attempt} className="hrow" style={{ gridTemplateColumns: "100px 1fr auto" }}>
                <span className="row"><StatusIcon r={a.result} /> Attempt {a.attempt}</span>
                <span className="muted small">{LABEL[a.result]}</span>
                <Link to="/runs/$runId" params={{ runId: a.runId }} search={{ t: p.test.key }} className="small">Open run</Link>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="section">
        <div className="sh"><h3>What it checks</h3></div>
        <div className="purpose">{p.purpose ?? <span className="faint">No description in the test.</span>}</div>
      </div>
      <div className="section">
        <div className="sh"><h3>Labels</h3><span className="count">{p.labels.length}</span></div>
        <div className="labels">
          {p.labels.map(([k, v]) => [
            <span key={`${k}-k`} className="k">{k}</span>,
            <span key={`${k}-v`} className="v">{(k === "Markers" ? v.split(", ") : [v]).map((x) => <span key={x} className={`tag${["File", "Class", "Gap pattern", "Run", "Parameter"].includes(k) ? " mono" : ""}`} title={x}>{x}</span>)}</span>,
          ])}
        </div>
      </div>
      <Steps p={p} onOpen={onOpen} />
      {p.location && (
        <div className="section">
          <div className="sh"><h3>Where</h3><code className="faint">{p.location}</code>{p.source.length > 0 && <span className="faint small">· source as it is now</span>}</div>
          {p.source.length > 0 && <pre className="src">{p.source.map((l) => <span key={l.n} className={l.hl ? "ln hl" : "ln"}>{`${String(l.n).padStart(4)}  ${l.text}`}</span>)}</pre>}
        </div>
      )}
      {diffOpen && p.diff && <DiffModal expected={p.diff.expected} actual={p.diff.actual} onClose={() => setDiffOpen(false)} />}
    </>
  );
}

function HistoryTab({ p, target, runId }: { p: TestPage; target: string; runId: string }) {
  const rows = p.history.rows;
  if (rows.length <= 1) return <div className="empty"><I.clock /><div>No earlier runs of this test on {target}.</div></div>;
  return (
    <>
      <div className="rate">
        <b>{p.history.counted ? Math.round((100 * p.history.passed) / p.history.counted) : 0}%</b>
        <span className="muted">passed {p.history.passed} of {p.history.counted} on {target} (skipped left out; an expected gap isn't a pass)</span>
        <span className="spacer" />
        <MiniStrip runs={[...rows].reverse().map((r) => ({ id: r.runId, result: r.result }))} />
      </div>
      <div className="hrows">
        {rows.map((r) => (
          <div key={r.runId} className={`hrow${r.runId === runId ? " cur" : ""}`}>
            <span className="row"><StatusPill r={r.result} /></span>
            <span className="when">{r.runId === runId ? "This run" : <Link to="/runs/$runId" params={{ runId: r.runId }} search={{ t: p.test.key }}>{when(r.started)}</Link>}</span>
            <span className="msg ellipsis" title={r.message}>{r.message}</span>
            <span className="dur">{dur(r.seconds)}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function TargetsTab({ p }: { p: TestPage }) {
  return (
    <div className="hrows">
      {p.targets.map((x) => (
        <div key={x.target} className={`hrow${x.current ? " cur" : ""}`} style={{ gridTemplateColumns: "20px 120px 140px minmax(0,1fr) 56px 24px" }}>
          <StatusIcon r={x.result} />
          <b>{x.target}</b>
          <span className="when">{x.started ? when(x.started) : "never ran this test"}</span>
          <span className="msg ellipsis" title={x.gap?.reason ?? x.message}>{x.gap ? `Gap: ${x.gap.reason}` : x.message}</span>
          <span className="dur">{x.runId ? dur(x.seconds) : ""}</span>
          {x.runId && !x.current
            ? <Link to="/runs/$runId" params={{ runId: x.runId }} search={{ t: p.test.key }} aria-label={`Open on ${x.target}`}><I.external style={{ width: 15, height: 15 }} /></Link>
            : <span />}
        </div>
      ))}
    </div>
  );
}

export function TestDetail({ runId, target, testKey, row, nav, retries, onOpen, live = false }: {
  runId: string; target: string; testKey: string; row?: TestRow; nav: Nav; retries?: Retries | null;
  onOpen: (key: string) => void; live?: boolean;
}) {
  const q = useTestPage(runId, testKey, !live);
  const openSheet = useRunSheet();
  const [tab, setTab] = useState("overview");
  const p = q.data && q.data.test.key === testKey ? q.data : null;
  const t = p?.test ?? row;
  if (!t) return q.error ? <Failed error={q.error} /> : <div className="pane-empty">Loading…</div>;
  const level = p?.labels.find(([k]) => k === "Level")?.[1];
  const kind = p?.labels.find(([k]) => k === "Kind")?.[1];
  const key = [t.module, t.cls, t.name].filter(Boolean).join("::");
  return (
    <div>
      <div className="t-idline">
        <CopyButton text={key} label="Copy the full test ID" />
        <span className="full" title={key}>{key}</span>
        <button type="button" className="btn ghost icon sm" disabled={!nav.prev} onClick={nav.prev ?? undefined} aria-label="Previous test (k)"><I.chevronUp /></button>
        <span className="pos">{nav.index + 1}/{nav.total}</span>
        <button type="button" className="btn ghost icon sm" disabled={!nav.next} onClick={nav.next ?? undefined} aria-label="Next test (j)"><I.chevron /></button>
      </div>
      <h2 className="t-head-title">{t.title}</h2>
      <div className="metaline">
        <StatusPill r={t.result} />
        <span>{t.tag}</span>
        {level && <span>{level}{kind ? ` · ${kind}` : ""}</span>}
        {t.seconds > 0 && <b>{dur(t.seconds)}</b>}
        {t.mark && t.mark.ageRuns > 1 && <span title={`Same result since ${when(t.mark.ageSince)}`}>{LABEL[t.result]} for {t.mark.ageRuns} runs</span>}
        <MarkChips mark={t.mark} />
        {!live && !t.upstream && (
          <button type="button" className="btn sm ghost" style={{ marginLeft: "auto" }} onClick={() => openSheet({ targets: [target], what: "pick", tests: [key] })}>
            <I.retry />Rerun this test…
          </button>
        )}
      </div>
      {live ? (
        <div className="block r-none"><div className="bt">While the run is live</div><div className="bt-sub muted">{t.message || "No message yet."} The details come from the JUnit report when the run ends.</div></div>
      ) : !p ? (q.error ? <Failed error={q.error} /> : <div className="pane-empty">Loading…</div>) : (
        <Tabs.Root value={tab} onValueChange={setTab}>
          <Tabs.List className="tabs" aria-label="About this test">
            <Tabs.Trigger value="overview">Overview</Tabs.Trigger>
            <Tabs.Trigger value="history">History <span className="count">{p.history.rows.length}</span></Tabs.Trigger>
            <Tabs.Trigger value="targets">Targets <span className="count">{p.targets.filter((x) => x.result).length}</span></Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="overview"><Overview p={p} target={target} retries={retries} onOpen={onOpen} /></Tabs.Content>
          <Tabs.Content value="history"><HistoryTab p={p} target={target} runId={runId} /></Tabs.Content>
          <Tabs.Content value="targets"><TargetsTab p={p} /></Tabs.Content>
        </Tabs.Root>
      )}
      {!live && t.result !== "pass" && <p className="faint xs" style={{ marginTop: 16 }}>{RESULT_HELP[t.result]}</p>}
    </div>
  );
}
