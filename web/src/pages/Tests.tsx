import { useMemo, useState } from "react";
import { useCatalogue, useHistory, type CatalogTest } from "../api";
import { Dl, Failed, Glyph, Help, Loading, MiniStrip, Tip } from "../ui";
import { LABEL } from "../vocab";

function needs(t: CatalogTest) {
  const parts: string[] = [];
  if (t.portsNeeded) parts.push(`${t.portsNeeded} port${t.portsNeeded === 1 ? "" : "s"}`);
  if (t.level === "L2 traffic") parts.push("traffic");
  if (t.variants?.length) parts.push(`×${t.variants.length} variants`);
  if (t.scenario) parts.push(`step ${t.step ?? ""} of a scenario`);
  return parts.join(" · ") || "-";
}

function HistoryRows({ t, targets }: { t: CatalogTest; targets: string[] }) {
  const h = useHistory(t, true);
  if (h.isPending) return <span className="muted">Loading…</span>;
  if (h.error || !h.data) return <Failed error={h.error} />;
  return (
    <div className="history">
      {targets.map((target) => {
        const x = h.data[target];
        return [
          <span key={`${target}-n`} className="muted">{target}</span>,
          <span key={`${target}-v`}>
            {x?.runs.length ? <MiniStrip runs={x.runs} /> : <span className="faint">never run</span>}{" "}
            <span className="faint small">{x?.runs.length ?? 0} runs</span>
            {x?.gap && <span className="muted small"> · gap: {x.gap.reason}</span>}
          </span>,
        ];
      })}
    </div>
  );
}

function TestItem({ t, targets }: { t: CatalogTest; targets: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <details onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="crow" style={{ ["--cols" as string]: targets.length }}>
        <span className="t-main"><span className="t-title">{t.title}</span><span className="t-id mono">{t.name}</span></span>
        <span className="c-meta">{t.level}</span>
        <span className="c-meta">{t.kind}</span>
        <span className="c-meta">{needs(t)}</span>
        {targets.map((target) => {
          const r = t.results[target];
          const rows: [string, string][] = [["Run", r?.runId ?? "-"]];
          for (const v of r?.variants ?? []) rows.push([v.param ? `[${v.param}]` : "Result", LABEL[v.result] + (v.message ? `: ${v.message.split("\n")[0]}` : "")]);
          if (!r?.variants.length) rows.push(["Result", "not in that run"]);
          return <span key={target} className="c-res"><Tip content={<Dl rows={rows} />}><Glyph r={r?.result ?? null} /></Tip></span>;
        })}
      </summary>
      {open && (
        <div className="detail">
          <div className="k">What it checks</div><div className="v">{t.purpose ?? <span className="faint">No description in the test</span>}</div>
          <div className="k">Where</div><div className="v"><code>{t.module}.py:{t.line}</code></div>
          {t.variants?.length ? <><div className="k">Variants</div><div className="v">{t.variants.map((v) => <code key={v} style={{ marginRight: 8 }}>{v}</code>)}</div></> : null}
          <div className="k">Markers</div><div className="v">{t.markers.join(", ") || "none"}</div>
          <div className="k">Results by target</div><div className="v"><HistoryRows t={t} targets={targets} /></div>
        </div>
      )}
    </details>
  );
}

export function TestsPage() {
  const q = useCatalogue();
  const [search, setSearch] = useState("");
  const [track, setTrack] = useState("");
  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    return (q.data?.tracks ?? [])
      .filter((g) => !track || g.track === track)
      .map((g) => ({ ...g, tests: g.tests.filter((t) => !s || `${t.title} ${t.name} ${t.module}`.toLowerCase().includes(s)) }))
      .filter((g) => g.tests.length);
  }, [q.data, search, track]);
  const shown = filtered.reduce((n, g) => n + g.tests.length, 0);

  return (
    <section className="section">
      <div className="page-head">
        <h1>
          Tests{" "}
          <Help label="About Tests">
            <p>The suite as read from tests/poc/test_*.py: nothing is run or collected, so no lock is taken.</p>
            <p>Level: L1 checks the control plane only; L2 traffic sends packets and needs --traffic on a target that forwards them. Kind: a negative test checks that bad input is refused.</p>
            <p>The last columns are each target's latest result; a parametrised test shows its worst variant. Open a row for its history on every target.</p>
          </Help>
        </h1>
      </div>
      {q.isPending && <Loading what="the catalogue" />}
      {q.error && <Failed error={q.error} />}
      {q.data && (
        <>
          <div className="toolbar">
            <input className="search" type="search" placeholder="Find a test by name or ID" aria-label="Find a test" value={search} onChange={(e) => setSearch(e.target.value)} />
            <button className="chip" type="button" aria-pressed={track === ""} onClick={() => setTrack("")}>All tracks</button>
            {q.data.tracks.map((g) => <button key={g.track} className="chip" type="button" aria-pressed={track === g.track} onClick={() => setTrack(g.track)}>{g.track}</button>)}
            <span className="spacer" />
            <span className="small muted">{search || track ? `${shown} matching tests` : `${q.data.total} tests · ${q.data.names} with variants`}</span>
          </div>
          {filtered.map((g) => {
            const modules: string[] = [];
            return (
              <section key={g.track} className="group">
                <div className="group-head"><span className="title">{g.track} <span className="count">{g.tests.length}</span></span></div>
                <div className="list">
                  <div className="crow head" style={{ ["--cols" as string]: q.data.targets.length }}>
                    <span>Test</span><span>Level</span><span>Kind</span><span>Needs</span>
                    {q.data.targets.map((t) => <span key={t} className="c-res">{t}</span>)}
                  </div>
                  {g.tests.map((t) => {
                    const head = !modules.includes(t.module);
                    if (head) modules.push(t.module);
                    return [
                      head && <div key={`${t.module}-h`} className="file-head">{t.module}.py</div>,
                      <TestItem key={`${t.module}-${t.cls}-${t.name}`} t={t} targets={q.data.targets} />,
                    ];
                  })}
                </div>
              </section>
            );
          })}
        </>
      )}
    </section>
  );
}
