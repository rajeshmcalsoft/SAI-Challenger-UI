// The test tree (B1): groups with proportional status bars, leaves with status, order number, title, marks and time.
// Grouping (result, track, file, cause), filters (status, marks, cause, search) and sorting all happen here, so the
// finished run page and the live run page share one list.
import { useMemo, useState, type ReactNode } from "react";
import type { Cause, Retries, TestRow } from "../api";
import { I } from "../icons";
import { MarkChips, PillBar, StatusIcon, dur } from "../ui";
import { GROUP_ORDER, GROUP_TITLE, LABEL, RANK, type Result } from "../vocab";

export type GroupBy = "result" | "track" | "file" | "cause";
export type SortBy = "order" | "name" | "duration" | "status";
export type MarkFilter = "new" | "fixed" | "regressed" | "new_error" | "flaky" | "retried";
export type StatusFilter = "all" | "fail" | "error" | "gap_passes" | "expected_gap" | "skipped" | "pass";

export interface Filters {
  status: StatusFilter;
  marks: MarkFilter[];
  cause: string | null;
  kind: string | null; // gap kind: limitation | bug | temporary | overdue
  q: string;
}

export const NO_FILTERS: Filters = { status: "all", marks: [], cause: null, kind: null, q: "" };

export function statusOf(r: Result): StatusFilter {
  return r === "setup_error" || r === "cleanup_error" ? "error" : r;
}

type Leaf = { type: "leaf"; id: string; depth: number; test: TestRow };
type Node = {
  type: "node"; id: string; depth: number; title: string; meta?: string; sub?: boolean;
  children: (Node | Leaf)[]; open: boolean; counts: Partial<Record<Result, number>>; size: number;
};
type Row = Node | Leaf | { type: "note"; id: string; depth: number; text: string };

function retriedText(retries: Retries | null | undefined, key: string) {
  const att = retries?.tests[key];
  if (!att || att.length < 2) return null;
  return att.map((a) => `attempt ${a.attempt}: ${LABEL[a.result]}`).join(" · ");
}

export function matches(t: TestRow, f: Filters, causes: Cause[] | undefined, retries?: Retries | null) {
  if (f.status !== "all" && statusOf(t.result) !== f.status) return false;
  if (f.marks.length) {
    const ok = f.marks.some((m) => m === "flaky" ? t.mark?.flaky : m === "retried" ? !!retriedText(retries, t.key) : t.mark?.transition === m);
    if (!ok) return false;
  }
  if (f.cause && !causes?.find((c) => c.id === f.cause)?.keys.includes(t.key)) return false;
  if (f.kind) {
    const note = t.gap?.note;
    if (!note) return false;
    if (f.kind === "overdue" ? note.state !== "overdue" : note.kind !== f.kind) return false;
  }
  const words = f.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length) {
    const hay = `${t.title} ${t.key} ${t.message} ${t.tag} ${t.scenario ?? ""}`.toLowerCase().replaceAll("_", " ");
    if (!words.every((w) => hay.includes(w.replaceAll("_", " ")))) return false;
  }
  return true;
}

function sorter(by: SortBy) {
  const pos = (t: TestRow) => t.pos ?? 0;
  if (by === "name") return (a: TestRow, b: TestRow) => a.title.localeCompare(b.title) || pos(a) - pos(b);
  if (by === "duration") return (a: TestRow, b: TestRow) => b.seconds - a.seconds || pos(a) - pos(b);
  if (by === "status") return (a: TestRow, b: TestRow) => RANK[b.result] - RANK[a.result] || pos(a) - pos(b);
  return (a: TestRow, b: TestRow) => pos(a) - pos(b);
}

function node(id: string, depth: number, title: string, children: (Node | Leaf)[], open: boolean, extra: Partial<Node> = {}): Node {
  const counts: Partial<Record<Result, number>> = {};
  let size = 0;
  const walk = (xs: (Node | Leaf)[]) => {
    for (const x of xs) {
      if (x.type === "leaf") { counts[x.test.result] = (counts[x.test.result] ?? 0) + 1; size++; }
      else walk(x.children);
    }
  };
  walk(children);
  return { type: "node", id, depth, title, children, open, counts, size, ...extra };
}

const leaves = (tests: TestRow[], depth: number): Leaf[] => tests.map((t) => ({ type: "leaf", id: t.key, depth, test: t }));
const attention = (tests: TestRow[]) => tests.some((t) => ["fail", "setup_error", "cleanup_error", "gap_passes"].includes(t.result));

/** Tests of a scenario sit in one node; elsewhere each test is a leaf. Keeps file order of the first step. */
function withScenarios(tests: TestRow[], depth: number, idp: string, sort: (a: TestRow, b: TestRow) => number) {
  const out: (Node | Leaf)[] = [];
  const seen = new Map<string, TestRow[]>();
  for (const t of tests) {
    if (t.scenario) {
      if (!seen.has(t.scenario)) { seen.set(t.scenario, []); out.push({ type: "leaf", id: `__sc__${t.scenario}`, depth, test: t }); }
      seen.get(t.scenario)!.push(t);
    } else out.push({ type: "leaf", id: t.key, depth, test: t });
  }
  const sorted = out.sort((a, b) => sort((a as Leaf).test, (b as Leaf).test));
  return sorted.map((x) => {
    const l = x as Leaf;
    if (!l.id.startsWith("__sc__")) return l;
    const steps = seen.get(l.test.scenario!)!;
    return node(`${idp}/sc:${l.test.scenario}`, depth, l.test.scenario!, leaves(steps.sort((a, b) => (a.pos ?? 0) - (b.pos ?? 0)), depth + 1),
      attention(steps), { sub: true, meta: `${steps.length} steps` });
  });
}

export function buildTree(tests: TestRow[], by: GroupBy, sort: SortBy, causes?: Cause[]): Node[] {
  const s = sorter(sort);
  if (by === "result") {
    // A scenario sits with its worst step, as on the server's run page.
    const scWorst = new Map<string, Result>();
    for (const t of tests) if (t.scenario) {
      const w = scWorst.get(t.scenario);
      if (!w || RANK[t.result] > RANK[w]) scWorst.set(t.scenario, t.result);
    }
    const out: Node[] = [];
    for (const r of GROUP_ORDER) {
      const own = tests.filter((t) => (t.scenario ? scWorst.get(t.scenario) === r : t.result === r));
      if (!own.length) continue;
      let children: (Node | Leaf)[];
      if (r === "skipped") {
        const sc = own.filter((t) => t.scenario);
        const plain = own.filter((t) => !t.scenario);
        const reasons = new Map<string, TestRow[]>();
        for (const t of plain) {
          const why = t.message || "No reason given";
          if (!reasons.has(why)) reasons.set(why, []);
          reasons.get(why)!.push(t);
        }
        children = [
          ...withScenarios(sc, 1, "r:skipped", s),
          ...[...reasons.entries()].map(([why, ts]) => node(`r:skipped/why:${why}`, 1, why, leaves(ts.sort(s), 2), false, { sub: true })),
        ];
      } else children = withScenarios(own, 1, `r:${r}`, s);
      out.push(node(`r:${r}`, 0, GROUP_TITLE[r], children, r !== "pass" && r !== "skipped"));
    }
    return out;
  }
  if (by === "cause" && causes) {
    const byKey = new Map(tests.map((t) => [t.key, t]));
    const fams = new Map<string, Node[]>();
    for (const c of causes) {
      const ts = c.keys.map((k) => byKey.get(k)).filter((t): t is TestRow => !!t);
      if (!ts.length) continue;
      if (!fams.has(c.familyTitle)) fams.set(c.familyTitle, []);
      fams.get(c.familyTitle)!.push(node(`c:${c.id}`, 1, c.title, leaves(ts.sort(s), 2), attention(ts), { sub: true }));
    }
    return [...fams.entries()].map(([fam, kids]) => node(`f:${fam}`, 0, fam, kids, true));
  }
  // track or file
  const groups = new Map<string, TestRow[]>();
  for (const t of [...tests].sort((a, b) => (a.pos ?? 0) - (b.pos ?? 0))) {
    const k = by === "track" ? t.track : `${t.module}.py`;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(t);
  }
  return [...groups.entries()].map(([k, ts]) => {
    if (by === "file") return node(`file:${k}`, 0, k, withScenarios(ts, 1, `file:${k}`, s), true, { meta: ts[0].tag });
    const files = new Map<string, TestRow[]>();
    for (const t of ts) {
      if (!files.has(t.module)) files.set(t.module, []);
      files.get(t.module)!.push(t);
    }
    return node(`track:${k}`, 0, k, [...files.entries()].map(([m, fs]) =>
      node(`track:${k}/file:${m}`, 1, `${m}.py`, withScenarios(fs, 2, `track:${k}/file:${m}`, s), true, { sub: true })), true);
  });
}

/** Leaves in tree order (collapsed nodes included): what prev/next and j/k move through. */
export function flatLeaves(nodes: Node[]): TestRow[] {
  const out: TestRow[] = [];
  const walk = (xs: (Node | Leaf)[]) => { for (const x of xs) x.type === "leaf" ? out.push(x.test) : walk(x.children); };
  walk(nodes);
  return out;
}

function why(t: TestRow) {
  if (t.result === "pass") return "";
  if (t.result === "expected_gap") return t.message;
  return (t.message.split("\n")[0] ?? "").replace(/^AssertionError: /, "").slice(0, 160);
}

function KindIcon({ t }: { t: TestRow }) {
  const n = t.gap?.note;
  if (!n || !n.recorded || n.kind === "limitation") return null;
  if (n.state === "overdue") return <span className="kind overdue" title={`Temporary gap, overdue for review since ${n.until}`}><I.hourglass /></span>;
  if (n.kind === "bug") return <span className="kind bug" title="Known bug"><I.bug /></span>;
  return <span className="kind temporary" title={`Temporary until ${n.until || "no date"}`}><I.hourglass /></span>;
}

export function LeafRow({ t, depth, selected, onSelect, retries, showWhy }: {
  t: TestRow; depth: number; selected: boolean; onSelect: (key: string) => void; retries?: Retries | null; showWhy: boolean;
}) {
  const reason = showWhy ? why(t) : "";
  return (
    <div className="tleaf" role="treeitem" aria-selected={selected} tabIndex={selected ? 0 : -1} style={{ ["--depth" as string]: depth }}
      onClick={() => onSelect(t.key)} onKeyDown={(e) => { if (e.key === "Enter") onSelect(t.key); }} data-key={t.key}>
      <StatusIcon r={t.result} />
      <span className="num">{t.pos ?? ""}</span>
      <span className="ttl">
        <span className="name">{t.title}</span>
        {reason ? <span className="why" title={reason}>{reason}</span> : <span className="id">{t.name !== t.title ? t.name : ""}</span>}
      </span>
      <span className="marks"><KindIcon t={t} /><MarkChips mark={t.mark} retried={retriedText(retries, t.key)} /></span>
      <span className="dur">{t.seconds ? dur(t.seconds) : ""}</span>
    </div>
  );
}

export function TestTree({ tests, groupBy, sortBy, filters, causes, retries, selected, onSelect, empty }: {
  tests: TestRow[]; groupBy: GroupBy; sortBy: SortBy; filters: Filters; causes?: Cause[]; retries?: Retries | null;
  selected: string | null; onSelect: (key: string) => void; empty?: ReactNode;
}) {
  const shown = useMemo(() => tests.filter((t) => !t.upstream || filters.q).filter((t) => matches(t, filters, causes, retries)),
    [tests, filters, causes, retries]);
  const nodes = useMemo(() => buildTree(shown, groupBy, sortBy, causes), [shown, groupBy, sortBy, causes]);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const filtering = filters.status !== "all" || filters.marks.length > 0 || !!filters.cause || !!filters.kind || !!filters.q.trim();
  const selectedPath = useMemo(() => {
    const path = new Set<string>();
    const walk = (xs: (Node | Leaf)[], trail: string[]): boolean => {
      for (const x of xs) {
        if (x.type === "leaf") { if (x.id === selected) { trail.forEach((id) => path.add(id)); return true; } }
        else if (walk(x.children, [...trail, x.id])) return true;
      }
      return false;
    };
    walk(nodes, []);
    return path;
  }, [nodes, selected]);

  const rows: Row[] = [];
  const push = (xs: (Node | Leaf)[]) => {
    for (const x of xs) {
      rows.push(x);
      if (x.type === "node" && (open[x.id] ?? (filtering || x.open || selectedPath.has(x.id)))) push(x.children);
    }
  };
  push(nodes);
  if (!shown.length) return <div className="tree-empty">{empty ?? "No tests match these filters."}</div>;
  return (
    <div className="tree" role="tree" aria-label="Tests">
      {rows.map((x) => {
        if (x.type === "leaf") {
          return <LeafRow key={x.id} t={x.test} depth={x.depth} selected={x.id === selected} onSelect={onSelect} retries={retries}
            showWhy={groupBy !== "result" || !["skipped"].includes(x.test.result)} />;
        }
        if (x.type === "note") return <div key={x.id} className="tnote" style={{ ["--depth" as string]: x.depth }}>{x.text}</div>;
        const isOpen = open[x.id] ?? (filtering || x.open || selectedPath.has(x.id));
        return (
          <div key={x.id} className={`tnode${x.sub ? " sub" : ""}`} role="treeitem" aria-expanded={isOpen} tabIndex={-1}
            style={{ ["--depth" as string]: x.depth }} onClick={() => setOpen({ ...open, [x.id]: !isOpen })}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen({ ...open, [x.id]: !isOpen }); } }}>
            <I.chevron className="chev" />
            <span className="ellipsis">{x.title}<span className="gcount">{x.size}</span>{x.meta && <span className="meta">{x.meta}</span>}</span>
            <PillBar counts={x.counts} width={x.depth === 0 ? 132 : 108} />
          </div>
        );
      })}
    </div>
  );
}
