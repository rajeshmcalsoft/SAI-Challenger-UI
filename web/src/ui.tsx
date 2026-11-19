// Shared pieces: result glyph, result strip, the circled "?" help, cell tips, formatting.
import * as Tooltip from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";
import type { StripCell } from "./api";
import { GLYPH, LABEL, type Result } from "./vocab";

export function Glyph({ r }: { r: Result | null }) {
  if (!r) return <span className="g faint" aria-label="Not in that run">—</span>;
  return <span className={`g ${r}`} aria-label={LABEL[r]}>{GLYPH[r]}</span>;
}

export function Strip({ cells, letters = false, fit = false }: { cells: StripCell[]; letters?: boolean; fit?: boolean }) {
  return (
    <span className={`strip${fit ? " fit" : ""}`} role="img" aria-label={`Result strip: ${cells.length} tests`}>
      <span className="cells">
        {cells.map((c, i) => (
          <span key={i} className={`cell ${c.r}${c.sep ? " sep" : ""}`} title={`${LABEL[c.r]}: ${c.title}`} />
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
      <span className="cells">{runs.map((r) => <span key={r.id} className={`cell ${r.result}`} title={`${r.id}: ${LABEL[r.result]}`} />)}</span>
    </span>
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
    <dl>
      {rows.map(([k, v]) => [<dt key={`${k}-k`}>{k}</dt>, <dd key={`${k}-v`}>{v}</dd>])}
    </dl>
  );
}

export function duration(seconds: number) {
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(s / 3600)}h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}m`;
}

const whenFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZoneName: "short" });
const dayFmt = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" });
const timeFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

export const when = (iso: string) => whenFmt.format(new Date(iso));
export const day = (iso: string) => dayFmt.format(new Date(iso));
export const clock = (iso: string) => timeFmt.format(new Date(iso));

export function Loading({ what }: { what: string }) {
  return <p className="muted" role="status">Loading {what}…</p>;
}

export function Failed({ error }: { error: unknown }) {
  return <div className="banner">Couldn't load this: {error instanceof Error ? error.message : String(error)}. Is the server running?</div>;
}

export function ReadOnlyNote() {
  return (
    <div className="banner small">
      Expected gaps can't be added or removed from here yet: that writes to the target profiles and comes next.
      Runs started here go through scripts/poc/run_poc.sh, the same as from a terminal.
    </div>
  );
}
