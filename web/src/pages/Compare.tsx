import * as Tabs from "@radix-ui/react-tabs";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useDiff, useGaps, useMatrix, type Matrix, type MatrixCell } from "../api";
import { Dl, Failed, Glyph, Help, Loading, Tip } from "../ui";
import { GLYPH, LABEL, LEGEND } from "../vocab";

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
      <Tip content={<Dl rows={rows} />}><Glyph r={c.result} /></Tip>
      {sub && <span className="sub">{sub}</span>}
    </td>
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
      <div className="banner">
        <div className="attention">
          <b>Needs attention</b>
          {Object.entries(m.attention).map(([t, items]) => <span key={t}><b>{t}</b> · {items.length ? items.join(", ") : "nothing to act on"}</span>)}
        </div>
      </div>
      <div className="toolbar">
        <span className="muted">{all ? `Showing all ${m.total} rows` : `Showing the ${m.differing} of ${m.total} rows that differ`}</span>
        <button className="btn sm" type="button" onClick={() => setAll(!all)}>{all ? "Only rows that differ" : "Show all rows"}</button>
        <span className="spacer" />
        <span className="small muted">
          {LEGEND.map((r) => <span key={r} style={{ marginLeft: 10 }}><Glyph r={r} /> {LABEL[r]}</span>)}
          <span style={{ marginLeft: 10 }}><Glyph r={null} /> not in that run</span>
        </span>
      </div>
      <table className={`matrix${all ? "" : " only-diff"}`}>
        <thead>
          <tr>
            <th>Test</th>
            {m.columns.map((c) => (
              <th key={c.id} className="col">{c.target}<Link className="run" to="/runs/$runId" params={{ runId: c.id }}>{c.id.replace(`${c.target}-`, "")}</Link></th>
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
                <td><span className="t-title">{row.title}</span><span className="t-id mono">{row.testId}</span></td>
                {m.columns.map((c) => <Cell key={c.id} c={row.cells[c.target]} />)}
                <td><div className="badges">{row.badges.map((b) => <span key={b.kind + b.target} className={`badge ${b.kind}`}>{b.text} · {b.target}</span>)}</div></td>
              </tr>
            )),
          ])}
        </tbody>
      </table>
    </>
  );
}

function DiffTab() {
  const d = useDiff();
  if (d.isPending) return <Loading what="the diff" />;
  if (d.error || !d.data) return <Failed error={d.error} />;
  const x = d.data;
  return (
    <>
      <div className="page-head" style={{ marginBottom: "var(--s-3)" }}>
        <h2>
          {x.headline}{" "}
          <Help label="About the run diff">
            <p>The same tests in two runs, B against A. Runs on different targets can be compared.</p>
            <p>saivs against saivs-thrift is the saithrift validation (Track B): both run libsaivs, so any difference comes from the thrift path, not the library.</p>
          </Help>
        </h2>
      </div>
      <p className="muted">
        A <Link className="mono" to="/runs/$runId" params={{ runId: x.a.id }}>{x.a.id}</Link> · B{" "}
        <Link className="mono" to="/runs/$runId" params={{ runId: x.b.id }}>{x.b.id}</Link> · {x.compared} tests in both · {x.onlyA} only in A · {x.onlyB} only in B
      </p>
      {x.sections.length === 0 && <p className="muted">Same results.</p>}
      {x.sections.map((s) => (
        <section key={s.title} className="group">
          <div className="group-head"><span className="title">{s.title} <span className="count">{s.items.length}</span></span></div>
          <div className="list">
            {s.items.map((it) => (
              <div key={it.name} className="trow" style={{ gridTemplateColumns: "60px minmax(0,1fr) minmax(0,1.2fr)" }}>
                <span><Glyph r={it.a} /> → <Glyph r={it.b} /></span>
                <span className="t-main"><span className="t-title">{it.title}</span><span className="t-id mono">{it.name}</span></span>
                <span className="muted small">{it.message}</span>
              </div>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}

function GapsTab() {
  const g = useGaps();
  const [copied, setCopied] = useState("");
  if (g.isPending) return <Loading what="the gap register" />;
  if (g.error || !g.data) return <Failed error={g.error} />;
  const gaps = g.data.entries.filter((e) => !e.scope);
  const scope = g.data.entries.filter((e) => e.scope);
  const copy = async () => {
    try { await navigator.clipboard.writeText(g.data.runbookMarkdown); setCopied("Copied"); }
    catch { setCopied("Copy failed: the browser blocked the clipboard"); }
    setTimeout(() => setCopied(""), 2000);
  };
  return (
    <>
      <div className="toolbar">
        <h2 style={{ margin: 0 }}>
          Expected gaps <span className="count muted">{gaps.length}</span>{" "}
          <Help label="About the gap register">
            <p>Every expected gap in every profile, with its status in each target's latest run. It replaces gap_table.py and feeds the coverage report.</p>
            <p>Copy as RUNBOOK table gives the §9 columns: Gap, Target, Test, What the target does, Expected, Evidence.</p>
          </Help>
        </h2>
        <span className="spacer" />
        <button className="btn sm" type="button" onClick={copy}>{copied || "Copy as RUNBOOK table"}</button>
      </div>
      <table className="matrix">
        <thead><tr><th>Gap (profile reason)</th><th>Test or pattern</th><th>Targets</th><th>Status named</th></tr></thead>
        <tbody>
          {gaps.map((e) => (
            <tr key={e.pattern}>
              <td>
                {[...new Set(Object.values(e.reasons))].map((r) => <div key={r}>{r}</div>)}
                {e.flags.map((f) => <div key={f} className="warn small">⚠ {f}</div>)}
              </td>
              <td><code>{e.pattern}</code></td>
              <td><div className="badges" style={{ justifyContent: "flex-start" }}>{Object.keys(e.reasons).map((t) => <span key={t} className="badge">{t} · {e.status[t]?.text ?? "Not run"}</span>)}</div></td>
              <td className="mono small">{[...new Set(Object.values(e.returned).filter(Boolean))].join(", ") || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {scope.length > 0 ? (
        <>
          <h2 style={{ marginTop: "var(--s-7)" }}>Not tested on these targets (out of scope)</h2>
          <table className="matrix">
            <thead><tr><th>Item</th><th>Targets</th><th>Reason</th></tr></thead>
            <tbody>{scope.map((e) => <tr key={e.pattern}><td>{e.pattern}</td><td>{Object.keys(e.reasons).join(", ")}</td><td className="muted">{Object.values(e.reasons).filter(Boolean).join("; ")}</td></tr>)}</tbody>
          </table>
        </>
      ) : <p className="section-note" style={{ marginTop: "var(--s-6)" }}>No out-of-scope items are recorded in the profiles (scope_gaps).</p>}
    </>
  );
}

export function ComparePage({ tab }: { tab: string }) {
  const navigate = useNavigate();
  const m = useMatrix();
  return (
    <section className="section">
      <div className="page-head">
        <h1>
          Compare{" "}
          <Help label="About Compare">
            <p>Where do targets or runs disagree, and which gaps exist? The matrix is the UI form of summarize.py: each column is the newest run of a target that ran PoC tests, and a step scenario is one row.</p>
            <p>“Only rows that differ” is on by default, because disagreement is the question. Hover any cell for its result, reason and run.</p>
          </Help>
        </h1>
      </div>
      <Tabs.Root value={tab} onValueChange={(v) => navigate({ to: "/compare", search: { tab: v } })}>
        <Tabs.List className="tabs" aria-label="Compare views">
          <Tabs.Trigger value="matrix">Matrix</Tabs.Trigger>
          <Tabs.Trigger value="diff">Run diff</Tabs.Trigger>
          <Tabs.Trigger value="gaps">Gaps</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="matrix">
          {m.isPending && <Loading what="the matrix" />}
          {m.error && <Failed error={m.error} />}
          {m.data && <MatrixTab m={m.data} />}
        </Tabs.Content>
        <Tabs.Content value="diff"><DiffTab /></Tabs.Content>
        <Tabs.Content value="gaps"><GapsTab /></Tabs.Content>
      </Tabs.Root>
    </section>
  );
}
