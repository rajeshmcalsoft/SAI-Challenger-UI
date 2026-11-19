import { Link } from "@tanstack/react-router";
import { useHealth, useMemory, useTargets, type Target } from "../api";
import { useRunSheet } from "../RunSheet";
import { Dl, Failed, Glyph, Help, Loading, ReadOnlyNote, Strip, when } from "../ui";
import { LABEL, LEGEND, MEANING } from "../vocab";

const DOT: Record<Target["state"]["kind"], string> = { ready: "●", busy: "◐", yours: "◐", stopped: "○", unknown: "?" };
const SOURCE = {
  profile: "from the profile",
  ui: "from the UI's target_facts.toml; the profile has no key for it yet",
  unknown: "not recorded anywhere",
};

function kindLine(t: Target) {
  if (t.forwardsTraffic === true) return "Reference · forwards packets · L1 + L2";
  if (t.forwardsTraffic === false) return "Reference · no dataplane · L1 only";
  return "Reference · dataplane not known";
}

function TargetDetails({ t }: { t: Target }) {
  const lock = t.lock.holder
    ? `${t.lock.path} · held by ${t.lock.holder.who} (pid ${t.lock.holder.pid})`
    : `${t.lock.path} · ${t.lock.exists ? "free" : "not created yet"}`;
  return (
    <Dl rows={[
      ["Profile", t.profilePath],
      ["Testbed", t.testbed],
      ["Container", `${t.container.name} · ${t.container.status ?? "not found"}`],
      ["Lock", lock + (t.lock.waiting ? ` · ${t.lock.waiting} waiting` : "")],
      ["Ports", t.ports.join(", ")],
      ["Traffic filters", t.trafficFilters.join(", ") || "none"],
      ["Expected gaps", `${t.expectedGaps}${t.scopeGaps ? ` · ${t.scopeGaps} out of scope` : ""}`],
      ["Forwards packets", `${t.forwardsTraffic === null ? "not known" : t.forwardsTraffic ? "yes" : "no"} (${SOURCE[t.forwardsSource]})`],
      ["History", `${t.runCount} runs in the reports folder`],
    ]} />
  );
}

function TargetRow({ t, canRun }: { t: Target; canRun: boolean }) {
  const uiJobs = t.uiJobs ?? [];  // absent when an older server answers
  const busy = t.state.kind === "busy" || t.state.kind === "yours" || uiJobs.length > 0;
  const openSheet = useRunSheet();
  const live = uiJobs.find((j) => j.state === "running") ?? uiJobs[0];
  return (
    <div className="target has-help">
      <Help corner side="bottom" align="end" label={`Details of ${t.name}`} title={t.name}><TargetDetails t={t} /></Help>
      <div className="who">
        <div className="name-line">
          <span className="name">{t.name}</span>
          {live
            ? <Link className={`pill ${t.state.kind}`} to="/jobs/$jobId" params={{ jobId: live.id }}>{DOT[t.state.kind]} {t.state.text}</Link>
            : <span className={`pill ${t.state.kind}`}>{DOT[t.state.kind]} {t.state.text}</span>}
        </div>
        <div className="kind">{kindLine(t)}</div>
        <div className="identity mono">{t.testbed} · {t.container.name}</div>
        {t.duplicates.length > 0 && <div className="warn">⚠ {t.duplicates.join(", ")} is listed twice in {t.name}.json</div>}
        {t.error && <div className="warn">⚠ {t.error}</div>}
      </div>
      <div className="result">
        {t.latest ? (
          <>
            <div className="line">
              <Link className="headline" to="/runs/$runId" params={{ runId: t.latest.id }}>{t.latest.headline}</Link>
              <span className="when">{when(t.latest.started)}</span>
            </div>
            <div><Strip cells={t.latest.strip} fit /></div>
          </>
        ) : <div className="muted">Never run</div>}
      </div>
      <div className="actions">
        <button className="btn" type="button" disabled={!canRun || !!t.blocked}
          title={t.blocked || (!canRun ? "Runs can be started only in local mode" : busy ? "Busy: a run started now waits its turn" : "")}
          onClick={() => openSheet({ targets: [t.name], what: "full" })}>{busy ? "Queue" : t.latest ? "Run" : "Run full suite"}</button>
        <button className="btn icon" type="button" disabled aria-label={`More actions for ${t.name}`}>⋯</button>
      </div>
    </div>
  );
}

export function TargetsPage() {
  return <><TargetsList /><Legend /></>;
}

function TargetsList() {
  const targets = useTargets();
  const health = useHealth();
  const memory = useMemory();
  const gb = (n: number) => (n / 2 ** 30).toFixed(1);
  return (
    <section className="section">
      <div className="page-head">
        <h1>
          Targets{" "}
          <Help label="About the Targets page">
            <p>One row per target profile in tests/poc/targets. The pill merges container, lock and run state into the
              one that matters most: Container stopped, Busy (with who and since when), or Ready.</p>
            <p>The result is the newest run that ran PoC tests; click it to open the run. The strip has one cell per
              test in suite order, with a gap between tracks. The ? in each row's corner has the target's details.</p>
          </Help>
        </h1>
        {memory.data && (
          <span className={`chip-mem${memory.data.low ? " low" : ""}`}>
            VM: {gb(memory.data.available)} of {gb(memory.data.total)} GB free
            {memory.data.low && " · Low memory: starting another container may fail"}{" "}
            <Help label="About the memory figure" align="end">
              <p>Free memory on this VM (MemAvailable in /proc/meminfo). With all three containers up, the project
                measured a peak of 4.1 GB used. Below 1.5 GB free, starting another container may fail.</p>
            </Help>
          </span>
        )}
      </div>
      <ReadOnlyNote />
      {targets.isPending && <Loading what="targets" />}
      {targets.error && <Failed error={targets.error} />}
      {targets.data && (
        <div className="list">
          {targets.data.dockerError && (
            <div className="add-row">Can't reach Docker. Is your user in the docker group? <code>docker ps</code> said: {targets.data.dockerError}</div>
          )}
          {targets.data.targets.map((t) => <TargetRow key={t.name} t={t} canRun={health.data?.canRun ?? false} />)}
          <div className="add-row">+ <b>Add libSAI</b>: upload a libsai.so and test it against the SAI spec (Phase 3)</div>
        </div>
      )}
    </section>
  );
}

function Legend() {
  return (
    <section className="section">
      <h2>Legend</h2>
      <p className="section-note">The six results, their glyphs and colours. Shape carries the meaning as well as colour,
        so the page still reads in greyscale. Errors are white (near-black in the light theme): an error is not a verdict
        on the target.</p>
      <div className="legend">
        {LEGEND.map((r) => (
          <div key={r} className="item">
            <div className="top">
              <Glyph r={r} /><b>{r === "setup_error" ? "Setup / Cleanup error" : LABEL[r]}</b><span className="spacer" />
              <span className="strip" aria-hidden="true"><span className="cells"><span className={`cell ${r}`} /></span></span>
            </div>
            <div className="small muted">{MEANING[r]}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
