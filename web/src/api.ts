// Types for the Python API (sai_challenger_ui/api/serialize.py) and the query hooks that fetch them.
import { useQuery } from "@tanstack/react-query";
import type { Result } from "./vocab";

export interface StripCell { r: Result; sep: boolean; letter: string; title: string }

export interface RunSummary {
  id: string;
  target: string;
  started: string;
  seconds: number;
  source: string;
  headline: string;
  counts: Record<Result, number>;
  countParts: [Result, string][];
  attention: boolean;
  what: string;
  upstreamOnly: boolean;
  strip: StripCell[];
}

export interface Mark { transition: "new" | "fixed" | "regressed" | "new_error" | null; flaky: boolean; ageRuns: number; ageSince: string; previous: Result | null }

export interface GapNote { kind: "limitation" | "bug" | "temporary"; kindText: string; link: string; until: string; by: string; at: string; recorded: boolean; state: "ok" | "overdue" | "no_date" }

export interface TestGap { pattern: string; reason: string; note: GapNote }

export interface TestRow {
  key: string;
  module: string;
  cls: string | null;
  name: string;
  title: string;
  result: Result;
  seconds: number;
  message: string;
  track: string;
  tag: string;
  cleanupFailed: boolean;
  upstream: boolean;
  step?: string | null;
  pos?: number | null;
  scenario?: string | null;
  mark?: Mark | null;
  gap?: TestGap | null;
}

export type Entry =
  | { kind: "test"; test: TestRow }
  | { kind: "scenario"; title: string; result: Result; sentence: string; tag: string; steps: TestRow[] }
  | { kind: "note" | "subhead"; text: string };

export interface JobMeta {
  jobId: string;
  command: string;
  who: string;
  commit: string;
  branch: string;
  dirty: string[];
  traffic: boolean;
  mld: string;
  what: string;
  setId: string | null;
  setIndex: number;
  setSize: number;
  retry: number;
  attempt: number;
  retryOf: string | null;
}

export interface GateRule { id: string; title: string; passed: boolean; actual: string; expected: string; keys: string[]; more: number }
export interface Gate { passed: boolean; failed: number; total: number; note: string; rules: GateRule[] }
export interface Cause { id: string; title: string; family: "target" | "setup"; familyTitle: string; kind: string; keys: string[]; counts: Partial<Record<Result, number>> }
export interface Retries {
  attempt: number;
  allowed: number;
  attempts: { attempt: number; jobId: string; runId: string | null; state: JobState; current: boolean }[];
  tests: Record<string, { attempt: number; runId: string; result: Result }[]>;
}

export interface RunFull extends RunSummary {
  job: JobMeta | null;
  testbed: string | null;
  hostname: string;
  report: string;
  html: string | null;
  pocTests: number;
  upstreamTests: number;
  since: { previous: string; previousStarted: string; text: string; changed: boolean } | null;
  groups: { result: Result; count: number; entries: Entry[] }[];
  tests: TestRow[];
  marks: { new: number; fixed: number; regressed: number; newError: number; flaky: number };
  causes: Cause[];
  gate: Gate;
  retries: Retries | null;
}

export interface Detail {
  purpose: string | null;
  happened: string | null;
  recorded: { pattern: string; reason: string } | null;
  unrecordedGap: boolean;
  hint: { id: string; text: string; action: string } | null;
  location: string | null;
  source: { n: number; text: string; hl: boolean }[];
  raw: string;
}

export interface TestPage extends Detail {
  test: TestRow;
  diff: { expected: string; actual: string } | null;
  labels: [string, string][];
  history: { rows: { runId: string; started: string; result: Result; seconds: number; message: string }[]; passed: number; counted: number };
  targets: { target: string; runId: string | null; started: string | null; result: Result | null; seconds: number; message: string; gap: TestGap | null; current: boolean }[];
  steps: (TestRow & { needs: string[]; stepName: string; happened: string | null })[] | null;
  scenario: string | null;
}

export interface Charts {
  dynamics: { runId: string; started: string; counts: Record<Result, number>; fixed: number; regressed: number; seconds: number; compared: boolean; current: boolean }[];
  stability: { track: string; tag: string; stable: number; total: number }[];
  durations: number[];
}

export interface Target {
  name: string;
  testbed: string;
  profilePath: string;
  error: string | null;
  duplicates: string[];
  ports: number[];
  trafficFilters: string[];
  expectedGaps: number;
  scopeGaps: number;
  forwardsTraffic: boolean | null;
  forwardsSource: "profile" | "ui" | "unknown";
  container: { name: string; state: string | null; status: string | null };
  lock: { path: string; exists: boolean; holder: { who: string; pid: number; since: string | null } | null; waiting: number };
  state: { kind: "ready" | "busy" | "yours" | "stopped" | "unknown"; text: string };
  latest: RunSummary | null;
  gate: Gate | null;
  trend: { id: string; started: string; counts: Record<Result, number> }[];
  runCount: number;
  blocked: string;
  uiJobs: { id: string; state: JobState }[];
}

export type JobState = "queued" | "running" | "done" | "removed";
export type Mld = "auto" | "on" | "off";
export type Preset = "full" | "tracks" | "failures" | "pick";

export interface RunRequest {
  targets: string[];
  what: Preset;
  tracks: string[];
  tests: string[];
  traffic: boolean;
  mld: Mld;
  repeat: number;
  notify: boolean;
  retries: number;
}

export interface PlanTarget {
  target: string;
  args: string[];
  command: string;
  what: string;
  count: number;
  gaps: number;
  traffic: boolean;
  trafficTests: number;
  trafficNote: string;
  mld: Mld;
  mldRelevant: boolean;
  estimate: number | null;
  warnings: string[];
  blocked: string;
  queue: string;
  forwards: boolean | null;
  trafficFilters: string[];
}

export interface JobSummary {
  id: string;
  target: string;
  state: JobState;
  what: string;
  count: number;
  created: string;
  started: string | null;
  ended: string | null;
  seconds: number;
  runId: string | null;
  reportPending: boolean;
  exitCode: number | null;
  note: string;
  notify: boolean;
  setId: string | null;
  setIndex: number;
  setSize: number;
  retry: number;
  attempt: number;
  retryOf: string | null;
  done: number;
  total: number;
  headline: string | null;
  current: string | null;
}

export interface JobFull extends JobSummary, Omit<JobMeta, "what" | "setId" | "setIndex" | "setSize"> {
  counts: Record<Result, number>;
  countParts: [Result, string][];
  strip: StripCell[];
  groups: { result: Result; count: number; entries: Entry[] }[];
  still: { key: string; title: string; name: string; now: boolean }[];
  waiting: { kind: "lock" | "ui" | "starting"; jobId: string | null; text: string } | null;
  profileLine: string;
  interrupted: string;
  set: { id: string; state: JobState; index: number; runId: string | null }[];
  testbed: string | null;
}

export interface MatrixCell {
  result: Result | null;
  message: string;
  seconds: number;
  runId: string;
  gap: { pattern: string; reason: string } | null;
  steps: { n: string; result: Result; message: string; name: string }[] | null;
  recent: Result[] | null;
}

export interface Matrix {
  byTrack: { track: string; tag: string; targets: Record<string, Record<Result, number>> }[];
  columns: { id: string; target: string; started: string }[];
  rows: {
    key: string;
    track: string;
    module: string;
    title: string;
    testId: string;
    scenario: boolean;
    differs: boolean;
    badges: { kind: string; target: string; text: string }[];
    cells: Record<string, MatrixCell>;
  }[];
  attention: Record<string, string[]>;
  differing: number;
  total: number;
}

export interface Diff {
  a: { id: string; target: string };
  b: { id: string; target: string };
  headline: string;
  compared: number;
  onlyA: number;
  onlyB: number;
  sections: { title: string; items: { name: string; title: string; a: Result; b: Result; message: string }[] }[];
}

export interface Gaps {
  entries: {
    pattern: string;
    scope: boolean;
    reasons: Record<string, string>;
    notes: Record<string, GapNote>;
    status: Record<string, { code: string; text: string }>;
    returned: Record<string, string>;
    evidence: Record<string, string>;
    flags: string[];
  }[];
  runbookMarkdown: string;
}

export interface CatalogTest {
  module: string;
  cls: string | null;
  name: string;
  title: string;
  line: number;
  level: string;
  kind: string;
  markers: string[];
  variants: string[] | null;
  portsNeeded: number | null;
  purpose: string | null;
  step: string | null;
  scenario: string | null;
  results: Record<string, { result: Result | null; variants: { param: string | null; result: Result; message: string }[]; runId: string }>;
}

export interface Catalogue {
  targets: string[];
  tracks: { track: string; tag: string; tests: CatalogTest[] }[];
  total: number;
  names: number;
}

export type History = Record<string, { runs: { id: string; result: Result }[]; gap: { pattern: string; reason: string } | null }>;

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function send<T>(method: "POST" | "DELETE", path: string, body?: unknown): Promise<T> {
  // X-SAI-Challenger-UI marks requests from this app; the server refuses actions without it (no cross-site requests).
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", "X-SAI-Challenger-UI": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data.detail ?? res.statusText);
  return data as T;
}

export const planRun = (req: RunRequest) => send<{ targets: PlanTarget[]; repeat: number }>("POST", "/api/plan", req);
export const startRun = (req: RunRequest) => send<{ jobs: string[]; skipped: { target: string; why: string }[] }>("POST", "/api/jobs", req);
export const saveGapNote = (note: { target: string; pattern: string; kind: string; link: string; until: string }) =>
  send<GapNote>("POST", "/api/gaps/note", note);
export const removeJob = (id: string) => send<{ removed: string }>("DELETE", `/api/jobs/${encodeURIComponent(id)}`);

export async function getConsole(id: string, offset: number) {
  return get<{ text: string; offset: number; size: number; active: boolean }>(`/api/jobs/${encodeURIComponent(id)}/console`, { offset });
}

async function get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const url = new URL(path, window.location.origin);
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${(await res.json().catch(() => ({}))).detail ?? res.statusText}`);
  return res.json() as Promise<T>;
}

export const useTargets = () =>
  useQuery({ queryKey: ["targets"], queryFn: () => get<{ dockerError: string | null; targets: Target[] }>("/api/targets"), refetchInterval: 5000 });

export const useMemory = () =>
  useQuery({ queryKey: ["memory"], queryFn: () => get<{ available: number; total: number; low: boolean }>("/api/memory"), refetchInterval: 10000 });

export const useRuns = (target: string, attention: boolean, limit: number) =>
  useQuery({
    queryKey: ["runs", target, attention, limit],
    queryFn: () => get<{ total: number; matching: number; targets: string[]; runs: RunSummary[] }>("/api/runs", { target, attention, limit }),
    refetchInterval: 10000,
  });

export const useRun = (id: string) => useQuery({ queryKey: ["run", id], queryFn: () => get<RunFull>(`/api/runs/${encodeURIComponent(id)}`) });

export const useTestPage = (runId: string, key: string | null, enabled = true) =>
  useQuery({
    queryKey: ["detail", runId, key],
    queryFn: () => get<TestPage>(`/api/runs/${encodeURIComponent(runId)}/detail`, { key: key ?? "" }),
    enabled: enabled && !!key,
    placeholderData: (prev) => prev,
  });

export const useCharts = (runId: string, enabled = true) =>
  useQuery({ queryKey: ["charts", runId], queryFn: () => get<Charts>(`/api/runs/${encodeURIComponent(runId)}/charts`), enabled });

export const useMatrix = () => useQuery({ queryKey: ["matrix"], queryFn: () => get<Matrix>("/api/compare/matrix") });
export const useDiff = () => useQuery({ queryKey: ["diff"], queryFn: () => get<Diff>("/api/compare/diff") });
export const useGaps = () => useQuery({ queryKey: ["gaps"], queryFn: () => get<Gaps>("/api/compare/gaps") });
export const useCatalogue = () => useQuery({ queryKey: ["tests"], queryFn: () => get<Catalogue>("/api/tests") });

export const useHistory = (t: { module: string; cls: string | null; name: string }, enabled: boolean) =>
  useQuery({
    queryKey: ["history", t.module, t.cls, t.name],
    queryFn: () => get<History>("/api/tests/history", { module: t.module, cls: t.cls ?? undefined, name: t.name }),
    enabled,
  });

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: () => get<{ canRun: boolean; user: string; mode: string; scRoot: string }>("/api/health"), staleTime: 60000 });

export const useJobs = () =>
  useQuery({
    queryKey: ["jobs"],
    queryFn: () => get<{ active: JobSummary[]; recent: JobSummary[] }>("/api/jobs"),
    refetchInterval: (q) => ((q.state.data?.active.length ?? 0) > 0 ? 1500 : 5000),
  });

export const useJob = (id: string) =>
  useQuery({
    queryKey: ["job", id],
    queryFn: () => get<JobFull>(`/api/jobs/${encodeURIComponent(id)}`),
    refetchInterval: (q) => (q.state.data && !["queued", "running"].includes(q.state.data.state) ? false : 1000),
  });
