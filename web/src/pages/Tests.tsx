// Tests (design §6.7): the suite as read from tests/poc/test_*.py, as a Track › file › test tree with each target's
// latest result, and the test beside it (split, A2).
import { Link, useNavigate } from "@tanstack/react-router";
import { useMemo, useRef, useState } from "react";
import { useCatalogue, useHistory, type CatalogTest } from "../api";
import { I } from "../icons";
import { useRunSheet } from "../RunSheet";
import { CopyButton, Crumbs, Failed, Help, Loading, MiniStrip, PillBar, StatusIcon, useLocal } from "../ui";
import { LABEL, worst, type Result } from "../vocab";
import { useListKeys } from "./Run";

const keyOf = (t: { module: string; cls: string | null; name: string }) => [t.module, t.cls, t.name].filter(Boolean).join("::");

function needs(t: CatalogTest) {
  const parts: string[] = [];
  if (t.portsNeeded) parts.push(`${t.portsNeeded} port${t.portsNeeded === 1 ? "" : "s"}`);
  if (t.level === "L2 traffic") parts.push("traffic");
  if (t.variants?.length) parts.push(`×${t.variants.length} variants`);
  if (t.scenario) parts.push(`step ${t.step ?? ""} of a scenario`);
  return parts.join(" · ") || "nothing special";
}

function worstOf(t: CatalogTest, targets: string[]): Result | null {
  return worst(targets.map((x) => t.results[x]?.result).filter((r): r is Result => !!r));
}

function HistoryRows({ t, targets }: { t: CatalogTest; targets: string[] }) {
  const h = useHistory(t, true);
  if (h.isPending) return <span className="muted">Loading…</span>;
  if (h.error || !h.data) return <Failed error={h.error} />;
  return (
    <div className="hrows">
      {targets.map((target) => {
        const x = h.data[target];
        const latest = t.results[target];
        const pass = x?.runs.filter((r) => r.result === "pass").length ?? 0;
        const counted = x?.runs.filter((r) => r.result !== "skipped").length ?? 0;
        return (
          <div key={target} className="hrow" style={{ gridTemplateColumns: "20px 110px minmax(0,1fr) auto" }}>
            <StatusIcon r={latest?.result ?? null} />
            <b>{target}</b>
            <span className="row wrap" style={{ gap: 8 }}>
              {x?.runs.length ? <MiniStrip runs={x.runs} /> : <span className="faint">never run</span>}
              {counted > 0 && <span className="faint small">passed {pass} of {counted}</span>}
              {x?.gap && <span className="muted small">· gap: {x.gap.reason}</span>}
            </span>
            {latest?.runId ? (
              <span className="row" style={{ gap: 6 }}>
                {(latest.variants.length ? latest.variants : [{ param: null, result: latest.result ?? "pass", message: "" }]).slice(0, 4).map((v) => (
                  <Link key={v.param ?? "-"} to="/runs/$runId" params={{ runId: latest.runId }} search={{ t: keyOf(t) + (v.param !== null ? `[${v.param}]` : "") }}
                    className="small" title={`Open in ${latest.runId}`}>{v.param ?? "Open"}</Link>
                ))}
              </span>
            ) : <span />}
          </div>
        );
      })}
    </div>
  );
}

function CatalogDetail({ t, targets, nav }: { t: CatalogTest; targets: string[]; nav: { index: number; total: number; prev: (() => void) | null; next: (() => void) | null } }) {
  const openSheet = useRunSheet();
  const key = keyOf(t);
  const labels: [string, string][] = [
    ["Track", t.markers.find((m) => ["l2", "l3", "acl", "counters"].includes(m))?.toUpperCase() ?? "—"],
    ["File", `${t.module}.py:${t.line}`], ["Level", t.level], ["Kind", t.kind], ["Markers", t.markers.join(", ") || "none"],
    ["Needs", needs(t)],
  ];
  if (t.cls) labels.splice(2, 0, ["Class", t.cls]);
  if (t.variants?.length) labels.push(["Variants", t.variants.join(", ")]);
  if (t.scenario) labels.push(["Scenario", `${t.scenario} · step ${t.step ?? "?"}`]);
  const w = worstOf(t, targets);
  return (
    <div>
      <div className="t-idline">
        <CopyButton text={key} label="Copy the full test ID" />
        <span className="full" title={key}>{key}</span>
        <button type="button" className="btn ghost icon sm" disabled={!nav.prev} onClick={nav.prev ?? undefined} aria-label="Previous test (k)"><I.chevronUp /></button>
        <span className="pos">{nav.index + 1}/{nav.total}</span>
        <button type="button" className="btn ghost icon sm" disabled={!nav.next} onClick={nav.next ?? undefined} aria-label="Next test (j)"><I.chevron /></button>
      </div>
      <h2 className="t-head-title">{t.scenario && t.step ? `${t.scenario} · ` : ""}{t.title}</h2>
      <div className="metaline">
        {w ? <span className="row" style={{ gap: 6 }}>Worst latest result <StatusIcon r={w} /> {LABEL[w]}</span> : <span>Not run yet</span>}
        <span>{t.level} · {t.kind}</span>
        <button type="button" className="btn sm ghost" style={{ marginLeft: "auto" }} onClick={() => openSheet({ what: "pick", tests: [key] })}><I.play />Run this test…</button>
      </div>
      <div className="section" style={{ marginTop: 0 }}>
        <div className="sh"><h3>What it checks</h3></div>
        <div className="purpose">{t.purpose ?? <span className="faint">No description in the test.</span>}</div>
      </div>
      <div className="section">
        <div className="sh"><h3>Labels</h3><span className="count">{labels.length}</span></div>
        <div className="labels">
          {labels.map(([k, v]) => [<span key={`${k}-k`} className="k">{k}</span>, <span key={`${k}-v`} className="v"><span className={`tag${k === "File" || k === "Class" ? " mono" : ""}`} title={v}>{v}</span></span>])}
        </div>
      </div>
      <div className="section">
        <div className="sh"><h3>Results by target</h3><span className="faint small">last 20 runs that ran it, oldest first</span></div>
        <HistoryRows t={t} targets={targets} />
      </div>
    </div>
  );
}

export function TestsPage({ selected }: { selected: string | null }) {
  const q = useCatalogue();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [track, setTrack] = useState("");
  const [layout, setLayout] = useLocal<"split" | "full">("layout", "split", ["split", "full"]);
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const searchRef = useRef<HTMLInputElement>(null);
  const targets = q.data?.targets ?? [];
  const filtered = useMemo(() => {
    const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return (q.data?.tracks ?? [])
      .filter((g) => !track || g.track === track)
      .map((g) => ({ ...g, tests: g.tests.filter((t) => {
        const hay = `${t.title} ${t.name} ${t.module} ${t.scenario ?? ""} ${t.purpose ?? ""}`.toLowerCase().replaceAll("_", " ");
        return words.every((w) => hay.includes(w.replaceAll("_", " ")));
      }) }))
      .filter((g) => g.tests.length);
  }, [q.data, search, track]);
  const order = filtered.flatMap((g) => g.tests.map(keyOf));
  const select = (k: string | null) => navigate({ to: "/tests", search: { t: k ?? undefined }, replace: true });
  useListKeys(!!q.data, order, selected, (k) => select(k), searchRef);
  const all = (q.data?.tracks ?? []).flatMap((g) => g.tests);
  const sel = selected ? all.find((t) => keyOf(t) === selected) : undefined;
  const idx = selected ? order.indexOf(selected) : -1;
  const nav = {
    index: Math.max(idx, 0), total: order.length,
    prev: idx > 0 ? () => select(order[idx - 1]) : null,
    next: idx >= 0 && idx < order.length - 1 ? () => select(order[idx + 1]) : null,
  };
  const counts = (tests: CatalogTest[]) => {
    const c: Partial<Record<Result, number>> = {};
    for (const t of tests) { const w = worstOf(t, targets); if (w) c[w] = (c[w] ?? 0) + 1; }
    return c;
  };

  const list = q.data && (
    <div className="card">
      <div className="card-title">
        <h2>Tests</h2><span className="count">{q.data.total}</span>
        <Help label="About Tests">
          <p>The suite as read from tests/poc/test_*.py: nothing is run or collected, so no lock is taken.</p>
          <p>Level: L1 checks the control plane only; L2 traffic sends packets and needs --traffic on a target that forwards them. Kind: a negative test checks that bad input is refused.</p>
          <p>The icons on the right are each target's latest result ({targets.join(", ")}); a parametrised test shows its worst variant. The bars count tests by their worst result on any target.</p>
        </Help>
        <span className="spacer" style={{ flex: 1 }} />
        <span className="faint small">{search || track ? `${order.length} matching` : `${q.data.names} with variants`}</span>
      </div>
      <div className="searchbox"><I.search />
        <input ref={searchRef} className="search" type="search" placeholder="Find a test by title, ID, file or what it checks  ( / )" aria-label="Find a test" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <div className="filters">
        <span className="seg" role="group" aria-label="Track">
          <button type="button" aria-pressed={track === ""} onClick={() => setTrack("")}>All tracks</button>
          {q.data.tracks.map((g) => <button key={g.track} type="button" aria-pressed={track === g.track} onClick={() => setTrack(g.track)}>{g.tag}</button>)}
        </span>
        <span className="spacer" />
        <span className="faint small row" style={{ gap: 6 }}>{targets.map((t) => <span key={t} className="tag">{t}</span>)}</span>
      </div>
      <div className="tree" role="tree" aria-label="Tests">
        {filtered.map((g) => {
          const files = [...new Set(g.tests.map((t) => t.module))];
          const gid = `track:${g.track}`;
          const gOpen = !closed[gid];
          return [
            <div key={gid} className="tnode" role="treeitem" aria-expanded={gOpen} style={{ ["--depth" as string]: 0 }} onClick={() => setClosed({ ...closed, [gid]: gOpen })}>
              <I.chevron className="chev" /><span>{g.track}<span className="gcount">{g.tests.length}</span></span><PillBar counts={counts(g.tests)} width={132} />
            </div>,
            ...(gOpen ? files.flatMap((m) => {
              const ts = g.tests.filter((t) => t.module === m);
              const fid = `${gid}/${m}`;
              const fOpen = !closed[fid];
              return [
                <div key={fid} className="tnode sub" role="treeitem" aria-expanded={fOpen} style={{ ["--depth" as string]: 1 }} onClick={() => setClosed({ ...closed, [fid]: fOpen })}>
                  <I.chevron className="chev" /><span className="mono">{m}.py<span className="gcount">{ts.length}</span></span><PillBar counts={counts(ts)} width={108} />
                </div>,
                ...(fOpen ? ts.map((t) => {
                  const k = keyOf(t);
                  return (
                    <div key={k} className="tleaf" role="treeitem" aria-selected={k === selected} data-key={k} style={{ ["--depth" as string]: 2, gridTemplateColumns: "16px minmax(0,1fr) auto" }}
                      onClick={() => select(k)}>
                      <StatusIcon r={worstOf(t, targets)} />
                      <span className="ttl">
                        <span className="name">{t.scenario && t.step ? `${t.step} · ` : ""}{t.title}</span>
                        <span className="why">{[t.level === "L2 traffic" ? "traffic" : "", t.kind === "negative" ? "negative" : "", t.variants?.length ? `×${t.variants.length}` : ""].filter(Boolean).join(" · ")}</span>
                      </span>
                      <span className="cres">{targets.map((x) => <StatusIcon key={x} r={t.results[x]?.result ?? null} title={`${x}: ${t.results[x]?.result ? LABEL[t.results[x].result!] : "not in its latest run"}`} />)}</span>
                    </div>
                  );
                }) : []),
              ];
            }) : []),
          ];
        })}
        {!filtered.length && <div className="tree-empty">No tests match.</div>}
      </div>
    </div>
  );

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <Crumbs items={sel ? [{ label: "Tests", to: "/tests", search: {} }, { label: sel.title }] : [{ label: "Tests" }]} />
        <span className="row" style={{ gap: 4 }}>
          <span className="faint small">Layout</span>
          <span className="seg" role="group" aria-label="Layout">
            <button type="button" aria-pressed={layout === "split"} onClick={() => setLayout("split")} title="List and test side by side"><I.split style={{ width: 14, height: 14 }} /></button>
            <button type="button" aria-pressed={layout === "full"} onClick={() => setLayout("full")} title="One at a time, full width"><I.full style={{ width: 14, height: 14 }} /></button>
          </span>
        </span>
      </div>
      {q.isPending && <div className="card"><Loading what="the catalogue" /></div>}
      {q.error && <Failed error={q.error} />}
      {q.data && (layout === "split" ? (
        <div className="split">
          {list}
          <div className="card pane">
            {sel ? <CatalogDetail t={sel} targets={targets} nav={nav} /> : <div className="pane-empty"><div><I.tests style={{ width: 24, height: 24 }} /><div>Pick a test to see what it checks and how it did on each target.</div></div></div>}
          </div>
        </div>
      ) : sel ? (
        <div className="card">
          <button type="button" className="btn ghost sm" onClick={() => select(null)} style={{ marginBottom: 12 }}>Back to the list</button>
          <CatalogDetail t={sel} targets={targets} nav={nav} />
        </div>
      ) : list)}
    </>
  );
}
