// The comparison modal (C4, Allure's "Show difference"): expected against actual, unified or side by side, compared
// by lines, words or characters.
import { useEffect, useMemo, useRef, useState } from "react";
import { I } from "../icons";

type Op = { kind: "same" | "del" | "add"; text: string };
type By = "lines" | "words" | "chars";

function tokens(s: string, by: By) {
  if (by === "lines") return s.split("\n").map((l, i, a) => (i < a.length - 1 ? l + "\n" : l));
  if (by === "words") return s.split(/(\s+|[^\w\s])/).filter((x) => x !== "");
  return [...s];
}

/** Longest common subsequence over tokens: fine for the short values tests compare. */
export function diff(a: string, b: string, by: By): Op[] {
  const x = tokens(a, by);
  const y = tokens(b, by);
  if (x.length * y.length > 4_000_000) return [{ kind: "del", text: a }, { kind: "add", text: b }];
  const n = x.length, m = y.length;
  const dp = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = x[i] === y[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out: Op[] = [];
  const push = (kind: Op["kind"], text: string) => {
    const last = out[out.length - 1];
    if (last && last.kind === kind && by !== "lines") last.text += text;
    else out.push({ kind, text });
  };
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) { push("same", x[i]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) push("del", x[i++]);
    else push("add", y[j++]);
  }
  while (i < n) push("del", x[i++]);
  while (j < m) push("add", y[j++]);
  return out;
}

function Inline({ ops, show }: { ops: Op[]; show: ("del" | "add")[] }) {
  return (
    <span className="dl-line">
      {ops.map((o, i) => o.kind === "same" ? <span key={i}>{o.text}</span>
        : show.includes(o.kind) ? (o.kind === "del" ? <del key={i}>{o.text}</del> : <ins key={i}>{o.text}</ins>) : null)}
    </span>
  );
}

function Lines({ ops, show }: { ops: Op[]; show: ("del" | "add")[] }) {
  return (
    <>
      {ops.filter((o) => o.kind === "same" || show.includes(o.kind)).map((o, i) => (
        <span key={i} className={`dl-line${o.kind === "del" ? " del" : o.kind === "add" ? " add" : ""}`}>
          {o.kind === "del" ? "- " : o.kind === "add" ? "+ " : "  "}{o.text.replace(/\n$/, "")}
        </span>
      ))}
    </>
  );
}

export function DiffModal({ expected, actual, onClose }: { expected: string; actual: string; onClose: () => void }) {
  const [mode, setMode] = useState<"unified" | "sbs">("unified");
  const [by, setBy] = useState<By>(expected.includes("\n") || actual.includes("\n") ? "lines" : "words");
  const [full, setFull] = useState(false);
  const ops = useMemo(() => diff(expected, actual, by), [expected, actual, by]);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const View = by === "lines" ? Lines : Inline;
  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`modal${full ? " full" : ""}`} role="dialog" aria-modal="true" aria-labelledby="diff-title">
        <div className="modal-head">
          <h2 id="diff-title">Comparison</h2>
          <span className="spacer" style={{ flex: 1 }} />
          <button className="btn ghost icon" type="button" onClick={() => setFull(!full)} aria-label={full ? "Smaller" : "Full screen"}><I.expand /></button>
          <button ref={closeRef} className="btn ghost icon" type="button" onClick={onClose} aria-label="Close"><I.close /></button>
        </div>
        <div className="modal-controls">
          View mode:
          <span className="seg">
            <button type="button" aria-pressed={mode === "unified"} onClick={() => setMode("unified")}>Unified</button>
            <button type="button" aria-pressed={mode === "sbs"} onClick={() => setMode("sbs")}>Side by side</button>
          </span>
          <span style={{ flex: 1 }} />
          Compare by:
          <span className="seg">
            {(["chars", "words", "lines"] as By[]).map((b) => <button key={b} type="button" aria-pressed={by === b} onClick={() => setBy(b)}>{b}</button>)}
          </span>
        </div>
        {mode === "unified" ? (
          <div className="diffview" aria-label="Expected against actual">
            <span className="dl-line" style={{ color: "var(--text-3)" }}>Expected (the SAI spec): {by !== "lines" && expected}</span>
            {by === "lines" && <Lines ops={[{ kind: "same", text: expected }]} show={[]} />}
            <span className="dl-line" style={{ color: "var(--text-3)", marginTop: 8 }}>Difference to what the target gave:</span>
            <View ops={ops} show={["del", "add"]} />
          </div>
        ) : (
          <div className="diff-sbs">
            <div className="diffview"><div className="cap">Expected (the SAI spec)</div><View ops={ops} show={["del"]} /></div>
            <div className="diffview"><div className="cap">Actual (what the target gave)</div><View ops={ops} show={["add"]} /></div>
          </div>
        )}
      </div>
    </div>
  );
}
