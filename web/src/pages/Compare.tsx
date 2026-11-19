// Compare (design §6.6): pass rate by track and target (E5), the matrix, the run diff and the gap register with gap
// kinds (F1).
import * as Tabs from "@radix-ui/react-tabs";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useDiff, useGaps, useMatrix, type Matrix, type MatrixCell } from "../api";
import { GapNoteEditor } from "../components/GapNote";
import { I } from "../icons";
import { Dl, Failed, Glyph, Help, Loading, StatusIcon, Tip } from "../ui";
import { GLYPH, LABEL, LEGEND, STACK, type Result } from "../vocab";

function Cell({ c }: { c: MatrixCell }) {
  if (!c.result) return <td className="cell"><Glyph r={null} /></td>;
  const rows: [string, string][] = [["Result", LABEL[c.result]]];
  if (c.message) rows.push([c.result === "expected_gap" || c.result === "skipped" ? "Reason" : "Message", c.message]);
  if (c.gap) rows.push(["Gap pattern", c.gap.pattern]);
  if (c.recent) rows.push(["Recent runs", `${c.recent.map((r) => GLYPH[r]).join(" ")}  (newest first)`]);
  rows.push(["Time", `${c.seconds.toFixed(1)}s`], ["Run", c.runId]);
  let sub = "";
  if (c.steps) {
    const bad = c.steps.find((s) => !["pass", "expected_gap", "skipped"].includes(s.result));
    const skipped = c.steps.filter((s) => s.result === "skipped").length;
    sub = bad ? `step ${bad.n}` : skipped ? `${skipped} skipped` : "";
  }
  return (
    <td className="cell">
      <Tip content={<Dl rows={rows} />}><StatusIcon r={c.result} lg /></Tip>
      {sub && <span className="sub">{sub}</span>}
    </td>
  );
}

/** E5: per track and target, Pass out of the tests that ran; the cell darkens with the share that didn't pass. */
function Heat({ m }: { m: Matrix }) {
  const targets = m.columns.map((c) => c.target);
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-title">
        <h2>Pass rate by track</h2>
        <span className="faint small">newest PoC run of each target · skipped tests left out</span>
        <Help label="About the heat map" align="end">
          <p>Each cell is Pass out of the tests that ran in that track on that target. The redder the cell, the bigger the share that
            didn't pass (fail, error, expected gap or gap now passes). Hover a cell for the counts.</p>
        </Help>
      </div>
      <table className="heat">
        <thead><tr><th />{targets.map((t) => <th key={t}>{t}</th>)}</tr></thead>
        <tbody>
          {m.byTrack.map((row) => (
            <tr key={row.track}>
              <th>{row.track}</th>
              {targets.map((t) => {
                const c = row.targets[t];
                const ran = c ? STACK.filter((r) => r !== "skipped").reduce((n, r) => n + (c[r] ?? 0), 0) : 0;
                if (!c || !ran) return <td key={t} className="empty-cell">{c?.skipped ? `${c.skipped} skipped` : "not run"}</td>;
                const share = 1 - (c.pass ?? 0) / ran;
                const parts = STACK.filter((r) => c[r]).map((r) => `${c[r]} ${LABEL[r].toLowerCase()}`);
                const bad = (["fail", "setup_error", "cleanup_error", "gap_passes", "expected_gap"] as Result[]).filter((r) => c[r]);
                return (
                  <td key={t} style={{ ["--heat" as string]: share ? `color-mix(in srgb, var(--fail) ${Math.round(12 + share * 70)}%, var(--surface))` : "var(--control)" }}
                    title={parts.join(", ")}>
                    <span className="pct">{Math.round((100 * (c.pass ?? 0)) / ran)}%</span>
                    <span className="bd">{bad.length ? bad.map((r) => `${c[r]} ${LABEL[r].toLowerCase()}`).join(" · ") : `${c.pass} pass`}</span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="scale"><span>All pass</span><span className="ramp" /><span>None pass</span></div>
    </div>
  );
}

function MatrixTab({ m }: { m: Matrix }) {
  const [all, setAll] = useState(false);
  const groups: [string, Matrix["rows"]][] = [];
  for (const row of m.rows) {
    const key = `${row.track}|${row.module}`;
    if (groups.length && groups[groups.length - 1][0] === key) groups[groups.length - 1][1].push(row);
    else groups.push([key, [row]]);
  }
  return (
    <>
      <Heat m={m} />
      <div className="card">
        <div className="banner info" style={{ marginBottom: 12 }}>
          <div className="attention">
            <b>Needs attention</b>
            {Object.entries(m.attention).map(([t, items]) => <span key={t}><b>{t}</b> · {items.length ? items.join(", ") : "nothing to act on"}</span>)}
          </div>
        </div>
        <div className="toolbar">
          <span className="seg">
            <button type="button" aria-pressed={!all} onClick={() => setAll(false)}>Rows that differ <span className="count">{m.differing}</span></button>
            <button type="button" aria-pressed={all} onClick={() => setAll(true)}>All rows <span className="count">{m.total}</span></button>
          </span>
          <span className="spacer" />
          <span className="row wrap small muted" style={{ gap: 12 }}>
            {LEGEND.map((r) => <span key={r} className="row" style={{ gap: 4 }}><StatusIcon r={r} /> {LABEL[r]}</span>)}
            <span className="row" style={{ gap: 4 }}><StatusIcon r={null} /> not in that run</span>
          </span>
        </div>
        <table className={`matrix${all ? "" : " only-diff"}`}>
          <thead>
            <tr>
              <th>Test</th>
              {m.columns.map((c) => (
                <th key={c.id} className="col">{c.target}<Link className="run" to="/runs/$runId" params={{ runId: c.id }} search={{}}>{c.id.replace(`${c.target}-`, "")}</Link></th>
              ))}
              <th style={{ textAlign: "right" }}>
                Notes{" "}
                <Help label="What the notes mean" align="end">
                  <p>New gap: fails, and the target's profile records no expected gap for it.</p>
                  <p>Stale gap: recorded as an expected gap, but it passed. Remove the gap.</p>
                  <p>Gap not applied: a gap is recorded but the test still reports Fail, e.g. a pattern that doesn't match.</p>
                  <p>Changed in recent runs: different results in the last three runs on that target. It may be flaky, or the test or the target changed.</p>
                </Help>
              </th>
            </tr>
          </thead>
          <tbody>
            {groups.map(([key, rows]) => [
              <tr key={key} className={`track${rows.some((r) => r.differs) ? "" : " same-group"}`}>
                <th colSpan={m.columns.length + 2}>{rows[0].track}<span className="file">{rows[0].module}.py</span></th>
              </tr>,
              ...rows.map((row) => (
                <tr key={row.key} className={row.differs ? "diff" : "same"}>
                  <td><span className="t-title">{row.title}</span><span className="t-id">{row.testId}</span></td>
                  {m.columns.map((c) => <Cell key={c.id} c={row.cells[c.target]} />)}
                  <td><div className="badges">{row.badges.map((b) => <span key={b.kind + b.target} className={`badge ${b.kind}`}>{b.text} · {b.target}</span>)}</div></td>
                </tr>
              )),
            ])}
          </tbody>
        </table>
      </div>
    </>
  );
}

function DiffTab() {
  const d = useDiff();
  if (d.isPending) return <div className="card"><Loading what="the diff" /></div>;
  if (d.error || !d.data) return <Failed error={d.error} />;
  const x = d.data;
  return (
    <div className="card">
      <div className="card-title">
        <h2>{x.headline}</h2>
        <Help label="About the run diff">
          <p>The same tests in two runs, B against A. Runs on different targets can be compared.</p>
          <p>saivs against saivs-thrift is the saithrift validation (Track B): both run libsaivs, so any difference comes from the thrift path, not the library.</p>
        </Help>
      </div>
      <p className="muted">
        A <Link className="mono" to="/runs/$runId" params={{ runId: x.a.id }} search={{}}>{x.a.id}</Link> · B{" "}
        <Link className="mono" to="/runs/$runId" params={{ runId: x.b.id }} search={{}}>{x.b.id}</Link> · {x.compared} tests in both · {x.onlyA} only in A · {x.onlyB} only in B
      </p>
      {x.sections.length === 0 && <p className="muted">Same results.</p>}
      {x.sections.map((s) => (
        <div key={s.title} style={{ marginTop: 16 }}>
          <div className="dayhead">{s.title} <span className="count">{s.items.length}</span></div>
          {s.items.map((it) => (
            <div key={it.name} className="hrow" style={{ gridTemplateColumns: "64px minmax(0,1fr) minmax(0,1.2fr)" }}>
              <span className="row" style={{ gap: 4 }}><StatusIcon r={it.a} /><I.chevronRight style={{ width: 12, height: 12 }} /><StatusIcon r={it.b} /></span>
              <span><span>{it.title}</span><br /><span className="mono faint xs">{it.name}</span></span>
              <span className="muted small">{it.message}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function GapsTab() {
  const g = useGaps();
  const [copied, setCopied] = useState("");
  if (g.isPending) return <div className="card"><Loading what="the gap register" /></div>;
  if (g.error || !g.data) return <Failed error={g.error} />;
  const gaps = g.data.entries.filter((e) => !e.scope);
  const scope = g.data.entries.filter((e) => e.scope);
  const copy = async () => {
    try { await navigator.clipboard.writeText(g.data.runbookMarkdown); setCopied("Copied"); }
    catch { setCopied("Copy failed: the browser blocked the clipboard"); }
    setTimeout(() => setCopied(""), 2000);
  };
  return (
    <div className="card">
      <div className="card-title">
        <h2>Expected gaps</h2><span className="count">{gaps.length}</span>
        <Help label="About the gap register">
          <p>Every expected gap in every profile, with its status in each target's latest run. It replaces gap_table.py and feeds the coverage report.</p>
          <p>Each gap has a kind: Limitation (the default), Known bug (with a link) or Temporary (with a review date). Kinds are kept in
            the UI's config folder; the profiles aren't changed.</p>
          <p>Copy as RUNBOOK table gives the §9 columns: Gap, Target, Test, What the target does, Expected, Evidence.</p>
        </Help>
        <span className="spacer" style={{ flex: 1 }} />
        <button className="btn sm" type="button" onClick={copy}><I.copy />{copied || "Copy as RUNBOOK table"}</button>
      </div>
      <div className="gaprow faint small" style={{ borderTop: 0, fontWeight: 700 }}><span>Gap (profile reason)</span><span>Test or pattern</span><span>Targets · latest status · kind</span></div>
      {gaps.map((e) => (
        <div key={e.pattern} className="gaprow">
          <div>
            {[...new Set(Object.values(e.reasons))].map((r) => <div key={r}>{r}</div>)}
            {e.flags.map((f) => <div key={f} className="warn small">⚠ {f}</div>)}
            {[...new Set(Object.values(e.returned).filter(Boolean))].length > 0 && <div className="mono faint xs">{[...new Set(Object.values(e.returned).filter(Boolean))].join(", ")}</div>}
          </div>
          <div className="pattern"><code>{e.pattern}</code></div>
          <div className="gapkinds">
            {Object.keys(e.reasons).map((t) => (
              <div key={t} className="gapkind">
                <span><b>{t}</b><br /><span className="faint xs">{e.status[t]?.text ?? "Not run"}</span></span>
                {e.notes[t] ? <GapNoteEditor target={t} pattern={e.pattern} note={e.notes[t]} compact /> : null}
              </div>
            ))}
          </div>
        </div>
      ))}
      {scope.length > 0 ? (
        <>
          <h2 style={{ marginTop: 32 }}>Not tested on these targets (out of scope)</h2>
          {scope.map((e) => <div key={e.pattern} className="gaprow"><span>{e.pattern}</span><span>{Object.keys(e.reasons).join(", ")}</span><span className="muted">{Object.values(e.reasons).filter(Boolean).join("; ")}</span></div>)}
        </>
      ) : <p className="section-note" style={{ marginTop: 24 }}>No out-of-scope items are recorded in the profiles (scope_gaps).</p>}
    </div>
  );
}

export function ComparePage({ tab }: { tab: string }) {
  const navigate = useNavigate();
  const m = useMatrix();
  return (
    <>
      <div className="page-head">
        <h1>Compare</h1>
        <Help label="About Compare">
          <p>Where do targets or runs disagree, and which gaps exist? The matrix is the UI form of summarize.py: each column is the newest run of a target that ran PoC tests, and a step scenario is one row.</p>
          <p>“Rows that differ” is on by default, because disagreement is the question. Hover any cell for its result, reason and run.</p>
        </Help>
      </div>
      <Tabs.Root value={tab} onValueChange={(v) => navigate({ to: "/compare", search: { tab: v } })}>
        <Tabs.List className="tabs" aria-label="Compare views">
          <Tabs.Trigger value="matrix">Matrix {m.data && <span className="count">{m.data.differing}</span>}</Tabs.Trigger>
          <Tabs.Trigger value="diff">Run diff</Tabs.Trigger>
          <Tabs.Trigger value="gaps">Gaps</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="matrix">
          {m.isPending && <div className="card"><Loading what="the matrix" /></div>}
          {m.error && <Failed error={m.error} />}
          {m.data && <MatrixTab m={m.data} />}
        </Tabs.Content>
        <Tabs.Content value="diff"><DiffTab /></Tabs.Content>
        <Tabs.Content value="gaps"><GapsTab /></Tabs.Content>
      </Tabs.Root>
    </>
  );
}
