// The UI's one fixed vocabulary (design doc §3) and the help texts behind the "?" icons.

export type Result = "pass" | "fail" | "setup_error" | "cleanup_error" | "gap_passes" | "expected_gap" | "skipped";

export const LABEL: Record<Result, string> = {
  pass: "Pass",
  fail: "Fail",
  setup_error: "Setup error",
  cleanup_error: "Cleanup error",
  gap_passes: "Gap now passes",
  expected_gap: "Expected gap",
  skipped: "Skipped",
};

/** Short labels for filter chips and chart legends. */
export const SHORT: Record<Result, string> = {
  pass: "Pass",
  fail: "Fail",
  setup_error: "Error",
  cleanup_error: "Cleanup",
  gap_passes: "Gap passes",
  expected_gap: "Gap",
  skipped: "Skipped",
};

/** Text glyphs, for places where an icon can't go (tooltips, plain text). */
export const GLYPH: Record<Result, string> = {
  pass: "✓",
  fail: "✕",
  setup_error: "!",
  cleanup_error: "!",
  gap_passes: "↑",
  expected_gap: "◆",
  skipped: "–",
};

export const MEANING: Record<Result, string> = {
  pass: "The target did what the SAI spec says.",
  fail: "The target did not do what the spec says, and no expected gap is recorded for it.",
  setup_error: "The test couldn't finish. Not a pass or fail of the target.",
  cleanup_error: "The test couldn't clean up. The next run may fail with “already exists”.",
  gap_passes: "An expected gap passed. Remove the gap.",
  expected_gap: "Fails as recorded in the target's profile.",
  skipped: "Not run on purpose.",
};

export const ATTENTION: Result[] = ["fail", "setup_error", "cleanup_error", "gap_passes"];

/** Attention first: the Run page's groups and the status chips. */
export const GROUP_ORDER: Result[] = ["fail", "setup_error", "cleanup_error", "gap_passes", "expected_gap", "skipped", "pass"];

/** Stacked marks (donut, bars, pill bars): the order the palette validator passed for adjacent colours. */
export const STACK: Result[] = ["pass", "expected_gap", "gap_passes", "setup_error", "cleanup_error", "fail", "skipped"];

/** Worst first, for "the status of a group". */
export const RANK: Record<Result, number> = {
  pass: 0, expected_gap: 1, skipped: 2, cleanup_error: 3, gap_passes: 4, setup_error: 5, fail: 6,
};

export const GROUP_TITLE: Record<Result, string> = {
  fail: "Fail",
  setup_error: "Setup errors",
  cleanup_error: "Cleanup errors",
  gap_passes: "Gap now passes",
  expected_gap: "Expected gaps",
  skipped: "Skipped",
  pass: "Pass",
};

export const GROUP_NOTE: Partial<Record<Result, string>> = {
  setup_error: "Not a pass or fail of the target",
  cleanup_error: "The next run may fail with “already exists”",
  gap_passes: "The target now passes these: remove the gaps",
  expected_gap: "Each row shows its reason",
  skipped: "Grouped by reason",
};

export const RESULT_HELP: Record<Result, string> = {
  fail:
    "The target did not do what the SAI spec says, and its profile records no expected gap for this test. If the " +
    "target is at fault, add an expected gap with the returned status as the reason. If the test is wrong, fix the " +
    "test instead: expected results follow the spec, never a target.",
  setup_error:
    "The test could not get going: a fixture or its setup raised an error before the check ran. It says nothing " +
    "about the target. Fix the cause and rerun.",
  cleanup_error:
    "The check finished but its cleanup failed. Objects may be left on the switch, so the next run can fail with " +
    "“already exists”. A container restart clears them.",
  gap_passes:
    "Recorded as expected gaps, but they passed (pytest's strict XPASS). The target was fixed or the gap is wrong: " +
    "remove the gap so the test counts as a pass again.",
  expected_gap:
    "Known deviations from the SAI spec, recorded in the target's profile (tests/poc/targets/<target>.json) as " +
    "strict xfail. They fail as recorded. If one starts passing, it moves to “Gap now passes”.",
  skipped:
    "Not run on purpose, and the reason is always shown. Traffic tests skip on targets that don't forward packets; " +
    "scenario steps skip when a step they need did not pass.",
  pass: "The target did what the SAI spec says.",
};

export const LEGEND: Result[] = ["pass", "expected_gap", "gap_passes", "setup_error", "fail", "skipped"];

export const TRANSITION: Record<string, string> = { new: "New", fixed: "Fixed", regressed: "Regressed", new_error: "New error" };

export const KIND_HELP: Record<string, string> = {
  limitation: "The target can't or won't do this. Not expected to change.",
  bug: "A known bug in the target, tracked somewhere: add the link.",
  temporary: "Expected to be fixed by a date. After it, the gap shows as overdue for review.",
};

/** Pass over tests that ran (Skipped left out): what the donut's centre shows (decision E8). */
export function passRate(counts: Partial<Record<Result, number>>) {
  const ran = (Object.keys(counts) as Result[]).filter((r) => r !== "skipped").reduce((n, r) => n + (counts[r] ?? 0), 0);
  return { pass: counts.pass ?? 0, ran, pct: ran ? Math.round(((counts.pass ?? 0) / ran) * 100) : null };
}

export function worst(results: Result[]): Result | null {
  let w: Result | null = null;
  for (const r of results) if (w === null || RANK[r] > RANK[w]) w = r;
  return w;
}
