// Targets (design §6.1, A8): one Allure-style summary card per target profile.
import { Link } from "@tanstack/react-router";
import { useHealth, useMemory, useTargets, type Target } from "../api";
import { I } from "../icons";
import { useRunSheet } from "../RunSheet";
import { Dl, Donut, Failed, Help, Loading, MiniBars, StatusIcon, StatusPill, Strip, Ticks, duration, whenLong } from "../ui";
import { ATTENTION, LABEL, MEANING, worst, type Result } from "../vocab";

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

function runStatus(counts: Record<Result, number>): Result {
  const bad = ATTENTION.find((r) => counts[r]);
  if (bad) return worst(ATTENTION.filter((r) => counts[r])) ?? bad;
  if (counts.expected_gap) return "expected_gap";
  if (counts.pass) return "pass";
  return "skipped";
}

function TargetCard({ t, canRun }: { t: Target; canRun: boolean }) {
  const uiJobs = t.uiJobs ?? [];
  const busy = t.state.kind === "busy" || t.state.kind === "yours" || uiJobs.length > 0;
  const openSheet = useRunSheet();
  const live = uiJobs.find((j) => j.state === "running") ?? uiJobs[0];
  const latest = t.latest;
  const status = latest ? runStatus(latest.counts) : null;
  const total = latest ? Object.values(latest.counts).reduce((a, b) => a + b, 0) : 0;
  const statePill = (
    <><span className="dot" />{t.state.text}</>
  );
  return (
    <div className="card tcard">
      <Help corner side="bottom" align="end" label={`Details of ${t.name}`} title={t.name}><TargetDetails t={t} /></Help>
      <div>
        <div className="tkind">{kindLine(t)}</div>
        <div className="name">
          <h2>{latest ? <Link to="/runs/$runId" params={{ runId: latest.id }} search={{}}>{t.name}</Link> : t.name}</h2>
          {live
            ? <Link className={`state-pill ${t.state.kind}`} to="/jobs/$jobId" params={{ jobId: live.id }}>{statePill}</Link>
            : <span className={`state-pill ${t.state.kind}`}>{statePill}</span>}
        </div>
        <div className="when">{latest ? whenLong(latest.started) : "Never run"}</div>
        {latest && status && (
          <div className="status">
            <StatusPill r={status} label={status === "pass" ? "Pass" : status === "expected_gap" ? "Pass except gaps" : LABEL[status]} />
            <span className="in">in {duration(latest.seconds)}</span>
            <Link className="small" to="/runs/$runId" params={{ runId: latest.id }} search={{}}>{latest.headline}</Link>
          </div>
        )}
        <div className="icons">
          <span title="Tests in the last run"><I.tests />{total || "–"}</span>
          <span title="Runs in the reports folder"><I.play />{t.runCount}</span>
          <span title="Expected gaps in the profile"><I.diamond />{t.expectedGaps}</span>
          <span title="Ports in the profile"><I.ports />{t.ports.length}</span>
          {t.gate && (
            <span title={t.gate.rules.filter((r) => !r.passed).map((r) => r.title).join("; ") || "Every rule passed"}>
              <I.shield />{t.gate.passed ? "Gate passed" : `Gate: ${t.gate.failed} of ${t.gate.total} rules fail`}
            </span>
          )}
        </div>
        {t.duplicates.length > 0 && <div className="warn small" style={{ marginTop: 8 }}>⚠ {t.duplicates.join(", ")} is listed twice in {t.name}.json</div>}
        {t.error && <div className="warn small" style={{ marginTop: 8 }}>⚠ {t.error}</div>}
      </div>
      <div className="side">{latest ? <Donut counts={latest.counts} size={96} /> : <Donut counts={{}} size={96} />}</div>
      {latest && (
        <div className="ticks">
          <div className="stat"><span className="k">Total</span><span className="v">{total}</span></div>
          <Ticks counts={latest.counts} />
        </div>
      )}
      {latest && <div className="stripline"><Strip cells={latest.strip} fit /></div>}
      {t.trend.length > 1 && (
        <div className="trend">
          <div><div className="faint xs" style={{ marginBottom: 4 }}>Last {t.trend.length} PoC runs</div><MiniBars runs={t.trend} /></div>
        </div>
      )}
      <div className="bottom">
        <span className="ident" title={`${t.testbed} · ${t.container.name}`}>{t.testbed} · {t.container.name}</span>
        {latest && <Link className="btn ghost sm" to="/runs/$runId" params={{ runId: latest.id }} search={{ view: "charts" }}><I.chart />Charts</Link>}
        <Link className="btn ghost sm" to="/runs" search={{}}><I.list />History</Link>
        <button className="btn primary sm" type="button" disabled={!canRun || !!t.blocked}
          title={t.blocked || (!canRun ? "Runs can be started only in local mode" : busy ? "Busy: a run started now waits its turn" : "")}
          onClick={() => openSheet({ targets: [t.name], what: "full" })}><I.play />{busy ? "Queue" : t.latest ? "Run" : "Run full suite"}</button>
      </div>
    </div>
  );
}

export function TargetsPage() {
  const targets = useTargets();
  const health = useHealth();
  const memory = useMemory();
  const gb = (n: number) => (n / 2 ** 30).toFixed(1);
  return (
    <>
      <div className="page-head">
        <h1>Targets</h1>
        <Help label="About the Targets page">
          <p>One card per target profile in tests/poc/targets. The pill merges container, lock and run state into the one that
            matters most: Container stopped, Busy (with who and since when), or Ready.</p>
          <p>The card shows the newest run that ran PoC tests: its result, the donut (Pass out of tests that ran), the result strip
            (one cell per test in suite order) and the last runs as small bars. The ? in each card has the target's details.</p>
        </Help>
        <span className="spacer" />
        {memory.data && (
          <span className={`memchip${memory.data.low ? " low" : ""}`}>
            VM: {gb(memory.data.available)} of {gb(memory.data.total)} GB free
            {memory.data.low && " · Low memory: starting another container may fail"}
            <Help label="About the memory figure" align="end">
              <p>Free memory on this VM (MemAvailable in /proc/meminfo). With all three containers up, the project measured a peak of
                4.1 GB used. Below 1.5 GB free, starting another container may fail.</p>
            </Help>
          </span>
        )}
      </div>
      {targets.isPending && <div className="card"><Loading what="targets" /></div>}
      {targets.error && <Failed error={targets.error} />}
      {targets.data && (
        <>
          {targets.data.dockerError && (
            <div className="banner warn" style={{ marginBottom: 16 }}>Can't reach Docker. Is your user in the docker group? <code>docker ps</code> said: {targets.data.dockerError}</div>
          )}
          <div className="tcards">
            {targets.data.targets.map((t) => <TargetCard key={t.name} t={t} canRun={health.data?.canRun ?? false} />)}
            <div className="card add-card"><I.plusCircle style={{ width: 22, height: 22 }} /><div><b>Add libSAI</b><div className="small">Upload a libsai.so and test it against the SAI spec (Phase 3)</div></div></div>
          </div>
        </>
      )}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title"><h2>Results and what they mean</h2></div>
        <div className="row wrap" style={{ gap: 24 }}>
          {(["pass", "expected_gap", "gap_passes", "setup_error", "fail", "skipped"] as Result[]).map((r) => (
            <div key={r} className="row" style={{ gap: 8, alignItems: "flex-start", maxWidth: 260 }}>
              <StatusIcon r={r} />
              <div><b>{r === "setup_error" ? "Setup / Cleanup error" : LABEL[r]}</b><div className="small muted">{MEANING[r]}</div></div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
