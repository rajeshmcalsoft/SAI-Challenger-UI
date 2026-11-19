// The run's Charts view (E1, E2, E3, E7, E8) and the Compare heat map (E5). Hand-drawn SVG: thin bars with 4 px
// rounded tops anchored to the baseline, 2 px surface gaps between stacked segments, recessive dashed grid, one
// y-axis per chart, a hover tooltip on every mark, and a legend whenever more than one series is drawn.
import { useNavigate } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import type { Charts } from "./api";
import { dur, shortDay, when } from "./ui";
import { LABEL, STACK, type Result } from "./vocab";

const W = 520;
const H = 230;
const PAD = { l: 44, r: 12, t: 14, b: 34 };

type TipState = { x: number; y: number; body: ReactNode } | null;

function useTip() {
  const [tip, setTip] = useState<TipState>(null);
  const show = (e: React.MouseEvent, body: ReactNode) => setTip({ x: e.clientX, y: e.clientY, body });
  const hide = () => setTip(null);
  const el = tip ? (
    <div className="ctip" style={{ left: Math.min(tip.x + 14, window.innerWidth - 300), top: tip.y + 14 }} role="tooltip">{tip.body}</div>
  ) : null;
  return { show, hide, el };
}

/** A round top for the axis and how many gridline steps to draw to it (4 or 5, whichever gives round steps). */
function niceAxis(v: number): { max: number; steps: number } {
  if (v <= 4) return { max: 4, steps: 4 };
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) {
    const max = m * mag;
    if (max < v) continue;
    for (const steps of [4, 5]) {
      const step = max / steps;
      const unit = Math.pow(10, Math.floor(Math.log10(step)));
      if ([1, 2, 2.5, 5].some((k) => Math.abs(step / unit - k) < 1e-9) && (step >= 1 ? Number.isInteger(step) : true)) return { max, steps };
    }
  }
  return { max: 10 * mag, steps: 5 };
}

function niceMax(v: number) {
  return niceAxis(v).max;
}

function topRounded(x: number, y: number, w: number, h: number, r = 4) {
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}L${x},${y + rr}Q${x},${y} ${x + rr},${y}L${x + w - rr},${y}Q${x + w},${y} ${x + w},${y + rr}L${x + w},${y + h}Z`;
}

function Grid({ max, fmt = (v: number) => String(v), plotH, zero = 0 }: { max: number; fmt?: (v: number) => string; plotH: number; zero?: number }) {
  const steps = niceAxis(max).max === max ? niceAxis(max).steps : 4;
  const ticks = Array.from({ length: steps + 1 }, (_, i) => (i / steps) * max);
  return (
    <g>
      <g className="grid">{ticks.map((t) => <line key={t} x1={PAD.l} x2={W - PAD.r} y1={PAD.t + plotH - (t / max) * plotH + zero} y2={PAD.t + plotH - (t / max) * plotH + zero} />)}</g>
      <g className="axis">{ticks.map((t) => <text key={t} x={PAD.l - 6} y={PAD.t + plotH - (t / max) * plotH + zero + 4} textAnchor="end">{fmt(t)}</text>)}</g>
    </g>
  );
}

function xLabels(items: { started: string }[], slot: number, y: number) {
  const every = Math.max(1, Math.ceil(items.length / 7));
  return (
    <g className="axis">
      {items.map((d, i) => (i % every === 0 || i === items.length - 1) && (i === items.length - 1 || items.length - 1 - i >= every / 2)
        ? <text key={i} x={PAD.l + slot * i + slot / 2} y={y} textAnchor="middle">{i === items.length - 1 ? "This run" : shortDay(d.started)}</text>
        : null)}
    </g>
  );
}

export function Legend({ items }: { items: Result[] }) {
  return (
    <div className="legend">
      {items.map((r) => <span key={r}><span className={`sw r-${r}`} />{LABEL[r]}</span>)}
    </div>
  );
}

/** E2: what each run on this target ended with, oldest to this run. */
export function StatusDynamics({ data }: { data: Charts["dynamics"] }) {
  const tip = useTip();
  const navigate = useNavigate();
  const plotH = H - PAD.t - PAD.b;
  const totals = data.map((d) => STACK.reduce((n, r) => n + (d.counts[r] ?? 0), 0));
  const max = niceMax(Math.max(1, ...totals));
  const slot = (W - PAD.l - PAD.r) / Math.max(data.length, 1);
  const bw = Math.min(22, slot * 0.6);
  const used = STACK.filter((r) => data.some((d) => d.counts[r]));
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Results of the last ${data.length} runs on this target`}>
        <Grid max={max} plotH={plotH} />
        {data.map((d, i) => {
          const x = PAD.l + slot * i + (slot - bw) / 2;
          let y = PAD.t + plotH;
          const parts = STACK.filter((r) => d.counts[r]);
          const body = (
            <>
              <div className="ttl">{when(d.started)}{d.current ? " · this run" : ""}</div>
              {parts.map((r) => <div key={r} className="li"><span className={`sw r-${r}`} />{LABEL[r]}<b>{d.counts[r]}</b></div>)}
            </>
          );
          return (
            <g key={d.runId} onMouseMove={(e) => tip.show(e, body)} onMouseLeave={tip.hide} onClick={() => navigate({ to: "/runs/$runId", params: { runId: d.runId } })}>
              {d.current && <rect className="cur-run" x={PAD.l + slot * i + 1} y={PAD.t} width={slot - 2} height={plotH} rx={4} />}
              <rect className="hit" x={PAD.l + slot * i} y={PAD.t} width={slot} height={plotH} />
              {parts.map((r, k) => {
                // Bottom to top; every segment above the first leaves a 2 px surface gap under it.
                const h = (plotH * (d.counts[r] ?? 0)) / max;
                y -= h;
                const segH = Math.max(h - (k > 0 ? 2 : 0), 0.5);
                return k === parts.length - 1
                  ? <path key={r} className={`r-${r}`} d={topRounded(x, y, bw, segH)} style={{ fill: "var(--c)", pointerEvents: "none" }} />
                  : <rect key={r} className={`r-${r}`} x={x} y={y} width={bw} height={segH} style={{ fill: "var(--c)", pointerEvents: "none" }} />;
              })}
            </g>
          );
        })}
        <line className="baseline" x1={PAD.l} x2={W - PAD.r} y1={PAD.t + plotH} y2={PAD.t + plotH} />
        {xLabels(data, slot, H - 12)}
      </svg>
      <Legend items={used} />
      {tip.el}
    </div>
  );
}

/** E3: tests fixed (up) and regressed or newly erroring (down) in each run, against the run before it. */
export function Transitions({ data }: { data: Charts["dynamics"] }) {
  const tip = useTip();
  const rows = data.filter((d) => d.compared);
  const plotH = H - PAD.t - PAD.b;
  const max = niceMax(Math.max(1, ...rows.map((d) => Math.max(d.fixed, d.regressed))));
  const half = plotH / 2;
  const zeroY = PAD.t + half;
  const slot = (W - PAD.l - PAD.r) / Math.max(rows.length, 1);
  const bw = Math.min(18, slot * 0.5);
  const ticks = [-max, -max / 2, 0, max / 2, max];
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Fixed and regressed tests per run">
        <g className="grid">{ticks.map((t) => <line key={t} x1={PAD.l} x2={W - PAD.r} y1={zeroY - (t / max) * half} y2={zeroY - (t / max) * half} />)}</g>
        <g className="axis">{ticks.map((t) => <text key={t} x={PAD.l - 6} y={zeroY - (t / max) * half + 4} textAnchor="end">{Math.abs(t)}</text>)}</g>
        {rows.map((d, i) => {
          const x = PAD.l + slot * i + (slot - bw) / 2;
          const up = (d.fixed / max) * half;
          const down = (d.regressed / max) * half;
          const body = (
            <>
              <div className="ttl">{when(d.started)}{d.current ? " · this run" : ""}</div>
              <div className="li"><span className="sw r-pass" />Fixed<b>{d.fixed}</b></div>
              <div className="li"><span className="sw r-fail" />Regressed or new error<b>{d.regressed}</b></div>
            </>
          );
          return (
            <g key={d.runId} onMouseMove={(e) => tip.show(e, body)} onMouseLeave={tip.hide}>
              {d.current && <rect className="cur-run" x={PAD.l + slot * i + 1} y={PAD.t} width={slot - 2} height={plotH} rx={4} />}
              <rect className="hit" x={PAD.l + slot * i} y={PAD.t} width={slot} height={plotH} />
              {d.fixed > 0 && <path className="r-pass" d={topRounded(x, zeroY - up, bw, up - 1)} style={{ fill: "var(--c)", pointerEvents: "none" }} />}
              {d.regressed > 0 && (
                // Drawn like an upward bar, then turned over so the rounded end points down.
                <path className="r-fail" d={topRounded(x, zeroY + 1, bw, down - 1)} transform={`rotate(180 ${x + bw / 2} ${zeroY + 1 + (down - 1) / 2})`}
                  style={{ fill: "var(--c)", pointerEvents: "none" }} />
              )}
            </g>
          );
        })}
        <line className="baseline" x1={PAD.l} x2={W - PAD.r} y1={zeroY} y2={zeroY} />
        {xLabels(rows, slot, H - 12)}
      </svg>
      <div className="legend"><span><span className="sw r-pass" />Fixed</span><span><span className="sw r-fail" />Regressed or new error</span></div>
      {tip.el}
    </div>
  );
}

/** E7: share of each track's tests whose result didn't change in their last 10 results on this target. */
export function Stability({ data }: { data: Charts["stability"] }) {
  const tip = useTip();
  const plotH = H - PAD.t - PAD.b;
  const slot = (W - PAD.l - PAD.r) / Math.max(data.length, 1);
  const bw = Math.min(40, slot * 0.5);
  const line = PAD.t + plotH - 0.9 * plotH;
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Stable tests per track">
        <Grid max={100} plotH={plotH} fmt={(v) => `${v}%`} />
        <line x1={PAD.l} x2={W - PAD.r} y1={line} y2={line} stroke="var(--text-3)" strokeDasharray="6 4" />
        <text className="lbl" x={W - PAD.r} y={line - 4} textAnchor="end">90%</text>
        {data.map((d, i) => {
          const share = d.total ? d.stable / d.total : 0;
          const h = share * plotH;
          const x = PAD.l + slot * i + (slot - bw) / 2;
          const body = (<><div className="ttl">{d.track}</div><div>{d.stable} of {d.total} tests kept the same result ({Math.round(share * 100)}%)</div></>);
          return (
            <g key={d.track} onMouseMove={(e) => tip.show(e, body)} onMouseLeave={tip.hide}>
              <rect className="hit" x={PAD.l + slot * i} y={PAD.t} width={slot} height={plotH} />
              <path d={topRounded(x, PAD.t + plotH - h, bw, h)} style={{ fill: "var(--accent)", pointerEvents: "none" }} />
              <text className="lbl" x={x + bw / 2} y={PAD.t + plotH - h - 6} textAnchor="middle" style={{ fill: "var(--text-2)" }}>{Math.round(share * 100)}%</text>
            </g>
          );
        })}
        <line className="baseline" x1={PAD.l} x2={W - PAD.r} y1={PAD.t + plotH} y2={PAD.t + plotH} />
        <g className="axis">{data.map((d, i) => <text key={d.track} x={PAD.l + slot * i + slot / 2} y={H - 12} textAnchor="middle">{d.tag}</text>)}</g>
      </svg>
      {tip.el}
    </div>
  );
}

/** E8 (a): how long each run took, oldest to this run. */
export function RunTimes({ data }: { data: Charts["dynamics"] }) {
  const tip = useTip();
  const plotH = H - PAD.t - PAD.b;
  const max = niceMax(Math.max(1, ...data.map((d) => d.seconds)));
  const slot = (W - PAD.l - PAD.r) / Math.max(data.length, 1);
  const bw = Math.min(22, slot * 0.6);
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Run time of each run">
        <Grid max={max} plotH={plotH} fmt={(v) => dur(v)} />
        {data.map((d, i) => {
          const h = (d.seconds / max) * plotH;
          const x = PAD.l + slot * i + (slot - bw) / 2;
          const n = STACK.reduce((s, r) => s + (d.counts[r] ?? 0), 0);
          const body = (<><div className="ttl">{when(d.started)}{d.current ? " · this run" : ""}</div><div>{dur(d.seconds)} for {n} tests</div></>);
          return (
            <g key={d.runId} onMouseMove={(e) => tip.show(e, body)} onMouseLeave={tip.hide}>
              {d.current && <rect className="cur-run" x={PAD.l + slot * i + 1} y={PAD.t} width={slot - 2} height={plotH} rx={4} />}
              <rect className="hit" x={PAD.l + slot * i} y={PAD.t} width={slot} height={plotH} />
              <path d={topRounded(x, PAD.t + plotH - h, bw, h)} style={{ fill: "var(--accent)", pointerEvents: "none" }} />
            </g>
          );
        })}
        <line className="baseline" x1={PAD.l} x2={W - PAD.r} y1={PAD.t + plotH} y2={PAD.t + plotH} />
        {xLabels(data, slot, H - 12)}
      </svg>
      {tip.el}
    </div>
  );
}

/** E8 (b): this run's tests by how long they took. */
export function DurationHistogram({ seconds }: { seconds: number[] }) {
  const tip = useTip();
  const edges = [0, 0.1, 0.5, 1, 2, 5, 10, 30, Infinity];
  const names = ["<0.1s", "0.1–0.5s", "0.5–1s", "1–2s", "2–5s", "5–10s", "10–30s", "≥30s"];
  const counts = names.map((_, i) => seconds.filter((s) => s >= edges[i] && s < edges[i + 1]).length);
  const plotH = H - PAD.t - PAD.b;
  const max = niceMax(Math.max(1, ...counts));
  const slot = (W - PAD.l - PAD.r) / names.length;
  const bw = Math.min(34, slot * 0.6);
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Tests by duration">
        <Grid max={max} plotH={plotH} />
        {counts.map((n, i) => {
          const h = (n / max) * plotH;
          const x = PAD.l + slot * i + (slot - bw) / 2;
          return (
            <g key={i} onMouseMove={(e) => tip.show(e, <><div className="ttl">{names[i]}</div><div>{n} tests</div></>)} onMouseLeave={tip.hide}>
              <rect className="hit" x={PAD.l + slot * i} y={PAD.t} width={slot} height={plotH} />
              {n > 0 && <path d={topRounded(x, PAD.t + plotH - h, bw, h)} style={{ fill: "var(--accent)", pointerEvents: "none" }} />}
            </g>
          );
        })}
        <line className="baseline" x1={PAD.l} x2={W - PAD.r} y1={PAD.t + plotH} y2={PAD.t + plotH} />
        <g className="axis">{names.map((n, i) => <text key={n} x={PAD.l + slot * i + slot / 2} y={H - 12} textAnchor="middle">{n}</text>)}</g>
      </svg>
      {tip.el}
    </div>
  );
}
