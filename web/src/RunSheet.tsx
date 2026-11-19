// The run sheet (design §6.3): slides in from the right, pre-filled from where it was opened.
// It only ever sends choices (targets, preset, catalogue keys); the server builds the run_poc.sh command.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  planRun, startRun, useCatalogue, useTargets,
  type CatalogTest, type Catalogue, type Mld, type PlanTarget, type RunRequest, type Target,
} from "./api";
import { Glyph, Help } from "./ui";

const TRACKS: [string, string][] = [["l2", "L2 & VLANs"], ["l3", "L3 routing"], ["acl", "ACL"], ["counters", "Counters"]];

const keyOf = (t: { module: string; cls: string | null; name: string }) => [t.module, t.cls, t.name].filter(Boolean).join("::");

type Prefill = Partial<Pick<RunRequest, "targets" | "what" | "tracks" | "tests">>;
const SheetContext = createContext<(p?: Prefill) => void>(() => {});
export const useRunSheet = () => useContext(SheetContext);

export function RunSheetProvider({ children }: { children: ReactNode }) {
  const [prefill, setPrefill] = useState<Prefill | null>(null);
  return (
    <SheetContext.Provider value={(p) => setPrefill(p ?? {})}>
      {children}
      {prefill && <RunSheet prefill={prefill} onClose={() => setPrefill(null)} />}
    </SheetContext.Provider>
  );
}

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

function minutes(seconds: number) {
  return seconds < 90 ? `${Math.round(seconds)}s` : `${Math.round(seconds / 60)} min`;
}

function TargetChip({ t, on, toggle }: { t: Target; on: boolean; toggle: () => void }) {
  const why = t.blocked;
  const queued = !why && (t.state.kind === "busy" || t.state.kind === "yours" || (t.uiJobs ?? []).length > 0);
  return (
    <button className="chip" type="button" aria-pressed={on && !why} disabled={!!why} onClick={toggle}
      title={why || (queued ? "Busy: the run will queue" : "")}>
      {t.name}{on && !why ? " ✓" : ""}
      {why && <span className="chip-why"> · {why.replace(" (ask the testbed admin)", "")}</span>}
      {queued && <span className="chip-why"> · busy: will queue</span>}
    </button>
  );
}

function PickTree({ cat, picked, setPicked, targets }: {
  cat: Catalogue; picked: Set<string>; setPicked: (s: Set<string>) => void; targets: string[];
}) {
  const [q, setQ] = useState("");
  const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const match = (t: CatalogTest) => {
    const hay = `${t.scenario ?? ""} ${t.title} ${t.name} ${t.module}`.toLowerCase().replaceAll("_", " ");
    return words.every((w) => hay.includes(w.replaceAll("_", " ")));
  };
  const state = (t: CatalogTest): "all" | "some" | "none" => {
    if (picked.has(keyOf(t))) return "all";
    const prefix = keyOf(t) + "[";
    return [...picked].some((k) => k.startsWith(prefix)) ? "some" : "none";
  };
  const setMany = (tests: CatalogTest[], on: boolean) => {
    const next = new Set(picked);
    for (const t of tests) {
      for (const k of [...next]) if (k === keyOf(t) || k.startsWith(keyOf(t) + "[")) next.delete(k);
      if (on) next.add(keyOf(t));
    }
    setPicked(next);
  };
  return (
    <div className="pick">
      <input className="search" type="search" placeholder="Find a test by title, name or file" value={q}
        onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") e.preventDefault(); }} />
      <div className="pick-list">
        {cat.tracks.map((tr) => {
          const tests = tr.tests.filter(match);
          if (!tests.length) return null;
          const files = [...new Set(tests.map((t) => t.module))];
          const allOn = tests.every((t) => state(t) === "all");
          return (
            <div key={tr.track} className="pick-track">
              <label className="pick-head">
                <input type="checkbox" checked={allOn} ref={(el) => { if (el) el.indeterminate = !allOn && tests.some((t) => state(t) !== "none"); }}
                  onChange={() => setMany(tests, !allOn)} />
                <b>{tr.track}</b> <span className="faint">· {tests.length}</span>
              </label>
              {files.map((m) => {
                const inFile = tests.filter((t) => t.module === m);
                const fileOn = inFile.every((t) => state(t) === "all");
                return (
                  <div key={m}>
                    <label className="pick-file mono">
                      <input type="checkbox" checked={fileOn} ref={(el) => { if (el) el.indeterminate = !fileOn && inFile.some((t) => state(t) !== "none"); }}
                        onChange={() => setMany(inFile, !fileOn)} />
                      {m}.py
                    </label>
                    {inFile.map((t) => {
                      const s = state(t);
                      return (
                        <label key={keyOf(t)} className="pick-test">
                          <input type="checkbox" checked={s === "all"} ref={(el) => { if (el) el.indeterminate = s === "some"; }}
                            onChange={() => setMany([t], s !== "all")} />
                          <span className="t-main">
                            <span className="t-title">{t.scenario && t.step ? `${t.scenario} · ` : ""}{t.title}</span>
                            <span className="t-id mono">{t.name}</span>
                          </span>
                          <span className="pick-badges">
                            {t.markers.includes("traffic") && <span className="badge">traffic</span>}
                            {t.portsNeeded && t.portsNeeded > 2 && <span className="badge">{t.portsNeeded} ports</span>}
                            {t.variants && t.variants.length > 1 && <span className="badge">×{t.variants.length}</span>}
                          </span>
                          <span className="pick-res">
                            {targets.map((name) => <Glyph key={name} r={t.results[name]?.result ?? null} />)}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Preview({ plan, repeat }: { plan: PlanTarget[]; repeat: number }) {
  const runnable = plan.filter((p) => !p.blocked);
  if (!runnable.length) return <div className="preview muted">Nothing can run with these choices.</div>;
  const counts = runnable.map((p, i) => `${p.count} test${p.count === 1 ? "" : "s"}${i === 0 ? " on" : ""} ${p.target}`).join(", ");
  const gaps = runnable.map((p) => p.gaps).filter((n) => n > 0);
  const est = runnable.map((p) => p.estimate).filter((x): x is number => x !== null);
  return (
    <div className="preview">
      {counts}
      {gaps.length > 0 && <> · {gaps.join(" + ")} expected gap{gaps.reduce((a, b) => a + b, 0) === 1 ? "" : "s"}</>}
      {est.length > 0 && <> · about {minutes(Math.max(...est) * repeat)}{" "}
        <Help label="How the time is estimated" side="top">
          <p>The sum of each selected test's time in its newest run on that target, plus about 15 seconds to start.
            Runs on different targets run side by side; repeats run one after another.</p>
        </Help></>}
      {repeat > 1 && <> · {repeat} runs each</>}
    </div>
  );
}

function RunSheet({ prefill, onClose }: { prefill: Prefill; onClose: () => void }) {
  const targets = useTargets();
  const cat = useCatalogue();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [req, setReq] = useState<RunRequest>(() => ({
    targets: prefill.targets ?? [], what: prefill.what ?? "full", tracks: prefill.tracks ?? ["l2"],
    tests: prefill.tests ?? [], traffic: true, mld: "auto", repeat: 1, notify: false, retries: 0,
  }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (patch: Partial<RunRequest>) => setReq((r) => ({ ...r, ...patch }));

  // Default target: the first one that can run, once the list is in.
  useEffect(() => {
    if (req.targets.length || !targets.data) return;
    const first = targets.data.targets.find((t) => !t.blocked);
    if (first) set({ targets: [first.name] });
  }, [targets.data, req.targets.length]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const asked = useDebounced(req, 200);
  const ready = asked.targets.length > 0 && (asked.what !== "pick" || asked.tests.length > 0) && (asked.what !== "tracks" || asked.tracks.length > 0);
  const plan = useQuery({
    queryKey: ["plan", JSON.stringify({ ...asked, notify: false })],
    queryFn: () => planRun(asked),
    enabled: ready,
    placeholderData: (prev) => prev,
    retry: false,
  });

  const picked = useMemo(() => new Set(req.tests), [req.tests]);
  const byName = new Map((targets.data?.targets ?? []).map((t) => [t.name, t]));
  const chosen = req.targets.filter((n) => byName.get(n) && !byName.get(n)!.blocked);
  const forwarding = chosen.filter((n) => byName.get(n)?.forwardsTraffic === true);
  const p = ready ? plan.data?.targets ?? [] : [];
  const runnable = p.filter((x) => !x.blocked);
  const mldShown = p.some((x) => x.mldRelevant) || (req.mld !== "auto" && forwarding.length > 0 && req.traffic);
  const allQueue = runnable.length > 0 && runnable.every((x) => x.queue);
  const total = runnable.reduce((n, x) => n + x.count, 0);
  const verb = allQueue ? "Queue" : "Run";
  const label = runnable.length === 0 ? "Run"
    : runnable.length === 1 ? `${verb} ${runnable[0].count} test${runnable[0].count === 1 ? "" : "s"} on ${runnable[0].target}${req.repeat > 1 ? ` ${req.repeat}×` : ""}`
      : `${verb} on ${runnable.length} targets${req.repeat > 1 ? ` ${req.repeat}×` : ""}`;
  const failuresOf = (name: string) => {
    const latest = byName.get(name)?.latest;
    if (!latest) return null;
    return ["fail", "setup_error", "cleanup_error", "gap_passes"].reduce((n, r) => n + (latest.counts[r as keyof typeof latest.counts] ?? 0), 0);
  };
  const profileMld = forwarding.map((n) => byName.get(n)?.trafficFilters.includes("mld") ? "on" : "off");

  async function submit() {
    if (!ready || !runnable.length || busy || plan.isFetching) return;
    setBusy(true);
    setError("");
    try {
      if (req.notify && "Notification" in window && Notification.permission === "default") await Notification.requestPermission();
      const res = await startRun(req);
      await qc.invalidateQueries({ queryKey: ["jobs"] });
      await qc.invalidateQueries({ queryKey: ["targets"] });
      onClose();
      navigate({ to: "/jobs/$jobId", params: { jobId: res.jobs[0] } });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="sheet-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title"
        onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <div className="sheet-head">
          <h2 id="sheet-title" style={{ fontSize: "var(--fs-xl)" }}>Run tests</h2>
          <Help label="About the run sheet" align="end">
            <p>Each target gets its own run of scripts/poc/run_poc.sh, queued on its own lock. Show command has the
              exact line, which works the same from a terminal in the checkout.</p>
            <p>Tests always run in file order, whatever order they were picked in, and scenario steps a picked step
              needs are added.</p>
          </Help>
          <span className="spacer" />
          <button ref={closeRef} className="btn ghost icon" type="button" aria-label="Close" onClick={onClose}>✕</button>
        </div>
        <div className="sheet-body">
          <div className="field">
            <div className="k">Where</div>
            <div className="v chips">
              {(targets.data?.targets ?? []).map((t) => (
                <TargetChip key={t.name} t={t} on={req.targets.includes(t.name)}
                  toggle={() => set({ targets: req.targets.includes(t.name) ? req.targets.filter((x) => x !== t.name) : [...req.targets, t.name] })} />
              ))}
              {targets.isPending && <span className="muted">Loading targets…</span>}
            </div>
          </div>

          <div className="field">
            <div className="k">What</div>
            <div className="v options" role="radiogroup" aria-label="What to run">
              <label><input type="radio" name="what" checked={req.what === "full"} onChange={() => set({ what: "full" })} />
                Full PoC suite{cat.data && <span className="faint"> · {cat.data.names} tests</span>}</label>
              <label><input type="radio" name="what" checked={req.what === "tracks"} onChange={() => set({ what: "tracks" })} />Tracks</label>
              {req.what === "tracks" && (
                <div className="chips indent">
                  {TRACKS.map(([m, text]) => (
                    <button key={m} type="button" className="chip" aria-pressed={req.tracks.includes(m)}
                      onClick={() => set({ tracks: req.tracks.includes(m) ? req.tracks.filter((x) => x !== m) : [...req.tracks, m] })}>{text}</button>
                  ))}
                  <span className="faint small">pytest -m with the track markers</span>
                </div>
              )}
              <label><input type="radio" name="what" checked={req.what === "failures"} onChange={() => set({ what: "failures" })} />
                Last run's failures
                <span className="faint"> · {chosen.map((n) => { const f = failuresOf(n); return f === null ? `no run on ${n}` : `${f} on ${n}`; }).join(", ") || "pick a target"}</span>
              </label>
              <label><input type="radio" name="what" checked={req.what === "pick"} onChange={() => set({ what: "pick" })} />
                Pick tests…{req.tests.length > 0 && <span className="faint"> · {req.tests.length} picked</span>}</label>
              {req.what === "pick" && cat.data && (
                <PickTree cat={cat.data} picked={picked} setPicked={(s) => set({ tests: [...s] })} targets={chosen} />
              )}
              <label className="disabled" title="The Week 1 upstream sets come later">
                <input type="radio" name="what" disabled /> Upstream baseline <span className="faint">· comes later</span>
              </label>
            </div>
          </div>

          <div className="field">
            <div className="k">Traffic</div>
            <div className="v">
              {forwarding.length > 0 && (
                <label className="toggle">
                  <input type="checkbox" checked={req.traffic} onChange={(e) => set({ traffic: e.target.checked })} />
                  {req.traffic ? "On" : "Off"}<span className="muted"> · Level 2 tests on {forwarding.join(" and ")}</span>
                </label>
              )}
              {p.filter((x) => x.trafficNote && !(x.forwards === true)).map((x) => <div key={x.target} className="muted">{x.trafficNote}</div>)}
              {forwarding.length === 0 && !p.some((x) => x.trafficNote) && <div className="muted">None of the chosen targets forwards packets.</div>}
            </div>
          </div>

          {mldShown && (
            <div className="field">
              <div className="k">MLD filter</div>
              <div className="v">
                <div className="chips">
                  {(["auto", "on", "off"] as Mld[]).map((m) => (
                    <button key={m} type="button" className="chip" aria-pressed={req.mld === m} onClick={() => set({ mld: m })}>
                      {m === "auto" ? `Profile: ${[...new Set(profileMld)].join("/") || "?"}` : m === "on" ? "On" : "Off"}
                    </button>
                  ))}
                </div>
                <div className="muted small">Off is for diagnosis: VPP's own MLD frames make traffic checks fail now and then.</div>
              </div>
            </div>
          )}

          <div className="field">
            <div className="k">Repeat</div>
            <div className="v">
              <div className="chips">
                {[1, 2, 3].map((n) => (
                  <button key={n} type="button" className="chip" aria-pressed={req.repeat === n} onClick={() => set({ repeat: n })}>{n}×</button>
                ))}
              </div>
              <div className="muted small">2× shows results are stable; traffic tests need 3× for the definition of done.</div>
              <div className="chips" style={{ marginTop: "var(--s-3)" }}>
                <span className="muted small" style={{ minWidth: 96 }}>Retry failures</span>
                {[0, 1, 2, 3].map((n) => (
                  <button key={n} type="button" className="chip" aria-pressed={req.retries === n} onClick={() => set({ retries: n })}>{n ? `${n}×` : "Off"}</button>
                ))}
              </div>
              <div className="muted small">
                After the run, only what failed (Fail, setup or cleanup error) runs again, up to this many times, as new runs.
                Tests that pass on a retry are marked Retried: treat them as possibly unstable, not as fixed.
              </div>
              <label className="toggle" style={{ marginTop: "var(--s-3)" }}>
                <input type="checkbox" checked={req.notify} onChange={(e) => set({ notify: e.target.checked })} /> Notify me when done
              </label>
            </div>
          </div>
        </div>

        <div className="sheet-foot">
          {ready && plan.data && <Preview plan={p} repeat={req.repeat} />}
          {ready && plan.error && <div className="warn">{plan.error instanceof Error ? plan.error.message : String(plan.error)}</div>}
          {!ready && <div className="preview muted">{req.targets.length === 0 ? "Pick a target." : req.what === "tracks" ? "Pick a track." : "Pick at least one test."}</div>}
          {runnable.map((x) => x.queue && <div key={`q-${x.target}`} className="muted small">{x.target}: {x.queue}</div>)}
          {p.filter((x) => x.blocked).map((x) => <div key={`b-${x.target}`} className="warn small">{x.target}: {x.blocked}. It won't run.</div>)}
          {runnable.flatMap((x) => x.warnings.map((w) => <div key={`${x.target}-${w}`} className="warn small">⚠ {runnable.length > 1 ? `${x.target}: ` : ""}{w}</div>))}
          {runnable.length > 0 && (
            <details className="cmd">
              <summary>Show command</summary>
              {runnable.map((x) => (
                <div key={x.target} className="cmd-line">
                  <code>{x.command}</code>
                  <button className="btn sm" type="button" onClick={() => navigator.clipboard?.writeText(x.command)}>Copy</button>
                </div>
              ))}
              <div className="faint small">From the checkout root. Expected gaps come from the profile when the run starts.</div>
            </details>
          )}
          {error && <div className="banner warn">Couldn't start: {error}</div>}
          <div className="sheet-actions">
            <span className="faint small">{total > 0 && req.repeat > 1 ? `${total * req.repeat} test runs in all` : ""}</span>
            <button className="btn primary" type="submit" disabled={!ready || !runnable.length || busy || plan.isFetching}>
              {busy ? "Starting…" : label}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
