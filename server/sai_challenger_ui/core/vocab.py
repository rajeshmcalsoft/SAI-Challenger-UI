"""The UI's one fixed vocabulary for results (design doc §3).

Raw pytest words (xfail, xpass, strict) never leave this layer except in raw-detail views.
"""
from enum import Enum


class Result(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SETUP_ERROR = "setup_error"
    CLEANUP_ERROR = "cleanup_error"
    GAP_PASSES = "gap_passes"
    EXPECTED_GAP = "expected_gap"
    SKIPPED = "skipped"


LABEL = {
    Result.PASS: "Pass",
    Result.FAIL: "Fail",
    Result.SETUP_ERROR: "Setup error",
    Result.CLEANUP_ERROR: "Cleanup error",
    Result.GAP_PASSES: "Gap now passes",
    Result.EXPECTED_GAP: "Expected gap",
    Result.SKIPPED: "Skipped",
}

# Shape tells the family, colour tells the urgency.
GLYPH = {
    Result.PASS: "●",
    Result.FAIL: "■",
    Result.SETUP_ERROR: "▲",
    Result.CLEANUP_ERROR: "▲",
    Result.GAP_PASSES: "◇",
    Result.EXPECTED_GAP: "◆",
    Result.SKIPPED: "○",
}

MEANING = {
    Result.PASS: "The target did what the SAI spec says.",
    Result.FAIL: "The target did not do what the spec says, and no expected gap is recorded for it.",
    Result.SETUP_ERROR: "The test couldn't finish. Not a pass or fail of the target.",
    Result.CLEANUP_ERROR: "The test couldn't clean up. The next run may fail with 'already exists'.",
    Result.GAP_PASSES: "An expected gap passed. Remove the gap.",
    Result.EXPECTED_GAP: "Fails as recorded in the target's profile.",
    Result.SKIPPED: "Not run on purpose.",
}

# Run page groups, attention first (design §6.4).
GROUP_ORDER = (
    Result.FAIL,
    Result.SETUP_ERROR,
    Result.CLEANUP_ERROR,
    Result.GAP_PASSES,
    Result.EXPECTED_GAP,
    Result.SKIPPED,
    Result.PASS,
)

# Worst wins when one test appears twice in a report.
RANK = {
    Result.PASS: 0,
    Result.EXPECTED_GAP: 1,
    Result.SKIPPED: 2,
    Result.CLEANUP_ERROR: 3,
    Result.GAP_PASSES: 4,
    Result.SETUP_ERROR: 5,
    Result.FAIL: 6,
}

# The outcome summarize.py would give the same test. Used only for parity checks:
# summarize.py has no separate error result.
SUMMARIZE_OUTCOME = {
    Result.PASS: "passed",
    Result.FAIL: "failed",
    Result.SETUP_ERROR: "failed",
    Result.CLEANUP_ERROR: "failed",
    Result.GAP_PASSES: "xpass",
    Result.EXPECTED_GAP: "xfail",
    Result.SKIPPED: "skipped",
}

_COUNT_WORDS = (
    (Result.PASS, "pass", "pass"),
    (Result.EXPECTED_GAP, "expected gap", "expected gaps"),
    (Result.GAP_PASSES, "gap now passes", "gaps now pass"),
    (Result.FAIL, "fail", "fail"),
    (Result.SETUP_ERROR, "setup error", "setup errors"),
    (Result.CLEANUP_ERROR, "cleanup error", "cleanup errors"),
    (Result.SKIPPED, "skipped", "skipped"),
)


def empty_counts():
    return {r: 0 for r in Result}


def plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def headline(counts):
    """One sentence: what needs attention, in a fixed order; otherwise how clean it is."""
    total = sum(counts.values())
    if total == 0:
        return "No tests ran"
    attention = []
    if counts[Result.FAIL]:
        attention.append(plural(counts[Result.FAIL], "test fails", "tests fail"))
    if counts[Result.SETUP_ERROR]:
        attention.append(plural(counts[Result.SETUP_ERROR], "setup error", "setup errors"))
    if counts[Result.CLEANUP_ERROR]:
        attention.append(plural(counts[Result.CLEANUP_ERROR], "cleanup error", "cleanup errors"))
    if counts[Result.GAP_PASSES]:
        attention.append(plural(counts[Result.GAP_PASSES], "expected gap now passes", "expected gaps now pass"))
    if attention:
        return " · ".join(attention)
    if total == counts[Result.SKIPPED]:
        return f"Nothing ran · {counts[Result.SKIPPED]} skipped"
    if counts[Result.EXPECTED_GAP]:
        return "Pass except " + plural(counts[Result.EXPECTED_GAP], "expected gap", "expected gaps")
    return "Pass"


def count_parts(counts):
    """[(result, "41 pass"), ...] for the count line; each part becomes a link. Zeros are left out."""
    return [
        (result, plural(counts[result], one, many))
        for result, one, many in _COUNT_WORDS
        if counts[result] or result is Result.PASS
    ]


def count_line(counts):
    return " · ".join(text for _, text in count_parts(counts))
