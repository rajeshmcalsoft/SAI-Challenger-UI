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

export const GLYPH: Record<Result, string> = {
  pass: "●",
  fail: "■",
  setup_error: "▲",
  cleanup_error: "▲",
  gap_passes: "◇",
  expected_gap: "◆",
  skipped: "○",
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

export const LEGEND: Result[] = ["pass", "fail", "expected_gap", "gap_passes", "skipped", "setup_error"];
