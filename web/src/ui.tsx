// Shared pieces: status icon and pill, count pills and pill bars, donut, strip, marks, help, crumbs, formatting.
import * as Tooltip from "@radix-ui/react-tooltip";
import { Link } from "@tanstack/react-router";
import { useEffect, useState, type ReactNode } from "react";
import type { Mark, StripCell } from "./api";
import { I } from "./icons";
import { LABEL, STACK, TRANSITION, passRate, type Result } from "./vocab";

const ICON: Record<Result, (p: { className?: string }) => ReactNode> = {
  pass: I.check, fail: I.x, setup_error: I.bang, cleanup_error: I.bang, gap_passes: I.up, expected_gap: I.diamond, skipped: I.minus,
};

/** Filled circle with the result's glyph: colour and shape together (never colour alone). */
export function StatusIcon({ r, lg = false, title }: { r: Result | null; lg?: boolean; title?: string }) {
  if (!r) return <span className="sicon r-none hollow" role="img" aria-label="Not in that run" title={title ?? "Not in that run"} />;
  const Glyph = ICON[r];
  return (
    <span className={`sicon r-${r}${lg ? " lg" : ""}`} role="img" aria-label={LABEL[r]} title={title ?? LABEL[r]}>
      <Glyph />
    </span>
  );
}

/** Older name, used by the matrix, catalogue and run sheet. */
export const Glyph = ({ r }: { r: Result | null }) => <StatusIcon r={r} />;

export function StatusPill({ r, label }: { r: Result; label?: string }) {
  const Glyph = ICON[r];
  return <span className={`spill r-${r}`}><span className="sicon"><Glyph /></span>{label ?? LABEL[r]}</span>;
}

export function CountPill({ r, n }: { r: Result; n: number }) {
  return <span className={`cpill r-${r}`} title={`${n} ${LABEL[r].toLowerCase()}`}>{n}</span>;
}

/** Allure's proportional status bar: one count pill per result, widths in proportion to the counts. */
export function PillBar({ counts, width = 120 }: { counts: Partial<Record<Result, number>>; width?: number }) {
  const parts = STACK.filter((r) => (counts[r] ?? 0) > 0);
  const total = parts.reduce((n, r) => n + (counts[r] ?? 0), 0);
  if (!total) return null;
  const label = parts.map((r) => `${counts[r]} ${LABEL[r].toLowerCase()}`).join(", ");
  return (
    <span className="pillbar" style={{ width }} role="img" aria-label={label} title={label}>
      {parts.map((r) => (
        <span key={r} className={`cpill r-${r}`} style={{ flex: `${counts[r]} 1 0`, minWidth: 20 }}>{counts[r]}</span>
      ))}
    </span>
  );
}

/** Label over a coloured tick and a number, per result (the stats row of Allure's report header). */
export function Ticks({ counts, order = STACK, onPick }: {
  counts: Partial<Record<Result, number>>; order?: Result[]; onPick?: (r: Result) => void;
}) {
  return (
    <>
      {order.filter((r) => counts[r]).map((r) => {
        const body = (<><span className="k">{LABEL[r]}</span><span className="v"><span className={`tick r-${r}`} />{counts[r]}</span></>);
        return onPick
          ? <button key={r} type="button" className="stat" onClick={() => onPick(r)} title={`Show only ${LABEL[r].toLowerCase()}`}>{body}</button>
          : <div key={r} className="stat">{body}</div>;
      })}
    </>
  );
}

/** The status ring with the pass rate in the middle (E1). Segments in stack order with small gaps. */
export function Donut({ counts, size = 96, stroke = 10, label }: {
  counts: Partial<Record<Result, number>>; size?: number; stroke?: number; label?: string;
}) {
  const [hover, setHover] = useState<Result | null>(null);
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const parts = STACK.filter((x) => (counts[x] ?? 0) > 0);
  const total = parts.reduce((n, x) => n + (counts[x] ?? 0), 0);
  const gap = parts.length > 1 ? Math.min(4, circ / 60) : 0;
  const { pass, ran, pct } = passRate(counts);
  let offset = 0;
  const desc = `${pass} of ${ran} tests that ran pass` + (counts.skipped ? `, ${counts.skipped} skipped` : "");
  return (
    <svg className="donut" width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label ?? desc}>
      <title>{desc}</title>
      {total === 0 && <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--control)" strokeWidth={stroke} />}
      {parts.map((x) => {
        const len = (circ * (counts[x] ?? 0)) / total;
        const dash = Math.max(len - gap, 1.5);
        const el = (
          <circle key={x} className={`r-${x}`} cx={size / 2} cy={size / 2} r={r} fill="none"
            strokeWidth={hover === x ? stroke + 3 : stroke} strokeDasharray={`${dash} ${circ - dash}`} strokeDashoffset={-offset}
            transform={`rotate(-90 ${size / 2} ${size / 2})`} style={{ stroke: "var(--c)", transition: "stroke-width 100ms" }}
            onMouseEnter={() => setHover(x)} onMouseLeave={() => setHover(null)}>
            <title>{`${counts[x]} ${LABEL[x].toLowerCase()}`}</title>
          </circle>
        );
        offset += len;
        return el;
      })}
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" style={{ font: `700 ${Math.round(size / 5.2)}px var(--font-sans)` }}>
        {hover ? counts[hover] : pct === null ? "–" : `${pct}%`}
      </text>
      {size >= 120 && (
        <text x="50%" y={size / 2 + size / 7} textAnchor="middle" dominantBaseline="central" style={{ font: `400 12px var(--font-sans)`, fill: "var(--text-3)" }}>
          {hover ? LABEL[hover].toLowerCase() : `of ${ran}`}
        </text>
      )}
    </svg>
  );
}

export function Strip({ cells, letters = false, fit = false, onPick }: {
  cells: StripCell[]; letters?: boolean; fit?: boolean; onPick?: (i: number) => void;
}) {
  return (
    <span className={`strip${fit ? " fit" : ""}`} role="img" aria-label={`Result strip: ${cells.length} tests`}>
      <span className="cells">
        {cells.map((c, i) => (
          <span key={i} className={`cell r-${c.r}${c.sep ? " sep" : ""}`} title={`${LABEL[c.r]}: ${c.title}`}
            onClick={onPick ? () => onPick(i) : undefined} style={onPick ? { cursor: "pointer" } : undefined} />
        ))}
      </span>
      {letters && (
        <span className="letters" aria-hidden="true">
          {cells.map((c, i) => <span key={i} className={c.sep ? "sep" : ""}>{c.letter}</span>)}
        </span>
      )}
    </span>
  );
}

export function MiniStrip({ runs }: { runs: { id: string; result: Result }[] }) {
  return (
    <span className="strip" role="img" aria-label={`${runs.length} runs`}>
      <span className="cells">{runs.map((r) => <span key={r.id} className={`cell r-${r.result}`} title={`${r.id}: ${LABEL[r.result]}`} />)}</span>
    </span>
  );
}

/** Small stacked bars of the last runs (the Targets card trend). */
export function MiniBars({ runs, height = 40 }: { runs: { id: string; started: string; counts: Partial<Record<Result, number>> }[]; height?: number }) {
  const top = Math.max(1, ...runs.map((x) => STACK.reduce((n, r) => n + (x.counts[r] ?? 0), 0)));
  return (
    <span className="minibars" style={{ height }} role="img" aria-label={`Results of the last ${runs.length} runs`}>
      {runs.map((x) => {
        const total = STACK.reduce((n, r) => n + (x.counts[r] ?? 0), 0);
        const title = `${when(x.started)}: ` + STACK.filter((r) => x.counts[r]).map((r) => `${x.counts[r]} ${LABEL[r].toLowerCase()}`).join(", ");
        return (
          <Link key={x.id} to="/runs/$runId" params={{ runId: x.id }} title={title} style={{ height: `${(100 * total) / top}%` }}>
            {STACK.filter((r) => x.counts[r]).map((r) => <i key={r} className={`r-${r}`} style={{ flex: `${x.counts[r]} 1 0` }} />)}
          </Link>
        );
      })}
    </span>
  );
}

export function MarkChips({ mark, retried }: { mark?: Mark | null; retried?: string | null }) {
  if (!mark && !retried) return null;
  return (
    <>
      {mark?.transition && mark.transition !== "new" && (
        <span className={`mark ${mark.transition}`} title={`${TRANSITION[mark.transition]} since the last run on this target that ran it`}>
          {mark.transition === "fixed" ? <I.fixed /> : <I.regressed />}{TRANSITION[mark.transition]}
        </span>
      )}
      {mark?.transition === "new" && <span className="mark new" title="First time this test ran on this target"><I.plusCircle />New</span>}
      {mark?.flaky && (
        <span className="mark flaky" title="Its outcome changed at least twice in its last results on this target (Allure's rule)">
          <I.flaky />Flaky
        </span>
      )}
      {retried && <span className="mark retried" title={retried}><I.retry />Retried</span>}
    </>
  );
}

type Side = "top" | "bottom" | "left" | "right";

/** The circled "?" with detail on hover or keyboard focus. */
export function Help({ children, label = "More about this", corner = false, side = "bottom", align = "start", title }: {
  children: ReactNode; label?: string; corner?: boolean; side?: Side; align?: "start" | "center" | "end"; title?: string;
}) {
  return (
    <Tooltip.Root delayDuration={120}>
      <Tooltip.Trigger asChild>
        <button type="button" className={`help-btn${corner ? " corner" : ""}`} aria-label={label}>
          <span className="help-icon" aria-hidden="true">?</span>
        </button>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="tip" side={side} align={align} sideOffset={8} collisionPadding={16}>
          {title && <div className="tip-title">{title}</div>}
          {children}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

/** Any small element (a matrix glyph) that shows detail on hover or focus. */
export function Tip({ children, content }: { children: ReactNode; content: ReactNode }) {
  return (
    <Tooltip.Root delayDuration={80}>
      <Tooltip.Trigger asChild><button type="button" className="cell-btn">{children}</button></Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="tip" side="bottom" sideOffset={6} collisionPadding={16}>{content}</Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export function Dl({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="dl">
      {rows.map(([k, v]) => [<dt key={`${k}-k`}>{k}</dt>, <dd key={`${k}-v`}>{v}</dd>])}
    </dl>
  );
}

export function CopyButton({ text, label = "Copy", sm = true }: { text: string; label?: string; sm?: boolean }) {
  const [done, setDone] = useState("");
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setDone("Copied"); }
    catch { setDone("Blocked"); }
    setTimeout(() => setDone(""), 1500);
  };
  return (
    <button type="button" className={`btn ghost icon${sm ? " sm" : ""}`} onClick={copy} aria-label={done || label} title={done || label}>
      {done ? <I.check /> : <I.copy />}
    </button>
  );
}

export type Crumb = { label: string; to?: string; params?: Record<string, string>; search?: Record<string, unknown> };

export function Crumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="crumbs" aria-label="Breadcrumbs">
      <Link to="/targets" aria-label="Home"><I.home style={{ width: 14, height: 14, verticalAlign: -2 }} /></Link>
      {items.map((c, i) => (
        <span key={i} style={{ display: "contents" }}>
          <span className="sep" aria-hidden="true">›</span>
          {c.to && i < items.length - 1
            ? <Link to={c.to as never} params={c.params as never} search={c.search as never}>{c.label}</Link>
            : <span className={i === items.length - 1 ? "here" : ""}>{c.label}</span>}
        </span>
      ))}
    </nav>
  );
}

export function Empty({ children, icon = <I.chart /> }: { children: ReactNode; icon?: ReactNode }) {
  return <div className="empty">{icon}<div>{children}</div></div>;
}

/** localStorage-backed state for per-viewer conveniences (layout, grouping): works without storage too. */
export function useLocal<T extends string>(key: string, fallback: T, allowed?: readonly T[]): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try {
      const got = localStorage.getItem(`sai-challenger-ui-${key}`) as T | null;
      return got !== null && (!allowed || allowed.includes(got)) ? got : fallback;
    } catch { return fallback; }
  });
  useEffect(() => {
    try { localStorage.setItem(`sai-challenger-ui-${key}`, v); } catch { /* not remembered */ }
  }, [key, v]);
  return [v, setV];
}

export function duration(seconds: number) {
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(s / 3600)}h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}m`;
}

/** A test's time, as Allure writes it: 5ms, 1.2s, 21s, 1m 05s. */
export function dur(seconds: number) {
  if (seconds < 0.001) return "0s";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  return duration(seconds);
}

const whenFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZoneName: "short" });
const dayFmt = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" });
const shortFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
const timeFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });
const longFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short" });

export const when = (iso: string) => whenFmt.format(new Date(iso));
export const whenLong = (iso: string) => longFmt.format(new Date(iso));
export const day = (iso: string) => dayFmt.format(new Date(iso));
export const shortDay = (iso: string) => shortFmt.format(new Date(iso));
export const clock = (iso: string) => timeFmt.format(new Date(iso));

export function Loading({ what }: { what: string }) {
  return <p className="muted" role="status">Loading {what}…</p>;
}

export function Failed({ error }: { error: unknown }) {
  return <div className="banner warn">Couldn't load this: {error instanceof Error ? error.message : String(error)}. Is the server running?</div>;
}

export function ReadOnlyNote() {
  return (
    <div className="banner">
      Expected gaps can't be added or removed from here yet: that writes to the target profiles and comes next.
      Runs started here go through scripts/poc/run_poc.sh, the same as from a terminal.
    </div>
  );
}
