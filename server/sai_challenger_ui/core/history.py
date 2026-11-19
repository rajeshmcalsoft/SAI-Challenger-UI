"""Per-test history on one target: marks (New, Fixed, Regressed, New error, Flaky), status age, and the rows of a
test's History and Targets tabs. The marks follow Allure Report 3's definitions (docs: test-stability), with one
difference: runs that didn't select a test are skipped rather than treated as "missing", because PoC runs often pick
a track or a few tests.

Standard library only. Runs are read from the reports index; nothing is written.
"""
from dataclasses import dataclass
from itertools import pairwise

from .vocab import Result

ERRORS = {Result.SETUP_ERROR, Result.CLEANUP_ERROR}
BAD = {Result.FAIL} | ERRORS

# The behaviour of the target, as Allure compares it: passes (P), fails (F) or the test broke (B). An expected gap
# fails as recorded and a gap that now passes passes. Skipped results say nothing and are left out.
OUTCOME = {
    Result.PASS: "P", Result.GAP_PASSES: "P",
    Result.FAIL: "F", Result.EXPECTED_GAP: "F",
    Result.SETUP_ERROR: "B", Result.CLEANUP_ERROR: "B",
}

FLAKY_WINDOW = 10  # previous results looked at (Allure 3 default)
FLAKY_RESET = 5  # identical outcomes in a row: changes before them no longer count (Allure 3 default)

TRANSITION_TEXT = {"new": "New", "fixed": "Fixed", "regressed": "Regressed", "new_error": "New error"}


class Results:
    """{test key: Result} per run, computed once per run object (the index swaps the object when a file changes)."""

    def __init__(self):
        self._cache = {}

    def of(self, run):
        hit = self._cache.get(run.id)
        if hit is None or hit[0] is not run:
            hit = (run, {t.key: t for t in run.tests if not t.upstream})
            self._cache[run.id] = hit
        return hit[1]


@dataclass
class Mark:
    transition: str | None  # new | fixed | regressed | new_error | None
    flaky: bool
    age_runs: int  # runs in a row on this target with this exact result, this one included
    age_since: str  # ISO start of the first of them
    previous: Result | None  # the result in the newest earlier run that ran the test


def earlier_runs(index, run):
    """Runs on the same target that started before this one, newest first."""
    return [r for r in index.runs(run.target) if r.started < run.started or (r.started == run.started and r.id < run.id)]


def transition(now, before):
    """Allure's transition marks, in our results. before: the newest earlier result that isn't Skipped, or None."""
    if before is None:
        return "new"
    if now is Result.FAIL and before is not Result.FAIL:
        return "regressed"
    if now in ERRORS and before not in ERRORS:
        return "new_error"
    if now is Result.PASS and before in BAD | {Result.EXPECTED_GAP}:
        return "fixed"
    return None


def flaky(now, history):
    """history: earlier results on the target, newest first (skipped and not-run left out)."""
    if OUTCOME.get(now) not in ("F", "B"):
        return False
    seq = [OUTCOME[r] for r in reversed(history[:FLAKY_WINDOW]) if r in OUTCOME] + [OUTCOME[now]]
    # A run of FLAKY_RESET identical outcomes: what came before it no longer counts.
    start, streak = 0, 1
    for i in range(1, len(seq)):
        streak = streak + 1 if seq[i] == seq[i - 1] else 1
        if streak >= FLAKY_RESET:
            start = i - streak + 1
    seq = seq[start:]
    changes = sum(1 for a, b in pairwise(seq) if a != b)
    return changes >= 2


def marks(index, results, run):
    """{test key: Mark} for every PoC test in the run."""
    earlier = earlier_runs(index, run)
    tables = [(r, results.of(r)) for r in earlier]
    out = {}
    for key, t in results.of(run).items():
        seen = [(r, table[key]) for r, table in tables if key in table]
        ran = [x for x in seen if x[1].result is not Result.SKIPPED]
        before = ran[0][1].result if ran else None
        if t.result is Result.SKIPPED:
            trans = None
        else:
            trans = transition(t.result, before) if seen else "new"
            if trans == "new" and seen:  # it ran before, only ever skipped
                trans = None
        age, since = 1, run.started
        for r, x in seen:
            if x.result is not t.result:
                break
            age, since = age + 1, r.started
        out[key] = Mark(trans, flaky(t.result, [x.result for _, x in ran]), age, since.isoformat(timespec="seconds"),
                        seen[0][1].result if seen else None)
    return out


@dataclass
class HistoryRow:
    run_id: str
    started: str
    result: Result
    seconds: float
    message: str


def test_history(index, results, run, key, n=30):
    """This test in this run and the runs before it on the same target, newest first."""
    rows = []
    for r in [run, *earlier_runs(index, run)]:
        t = results.of(r).get(key)
        if t is None:
            continue
        rows.append(HistoryRow(r.id, r.started.isoformat(timespec="seconds"), t.result, t.seconds,
                               (t.message.splitlines() or [""])[0][:200]))
        if len(rows) == n:
            break
    return rows


def success_rate(rows):
    """(passed, counted): Pass and Expected gap count as the target doing what is known; Skipped is left out.
    Here "passed" means the test passed, so an expected gap is counted but not passed."""
    counted = [r for r in rows if r.result is not Result.SKIPPED]
    return sum(1 for r in counted if r.result is Result.PASS), len(counted)


def across_targets(index, results, key, targets):
    """{target: (run, TestResult)} from the newest run on each target that ran this exact test."""
    out = {}
    for target in targets:
        for r in index.runs(target):
            t = results.of(r).get(key)
            if t is not None:
                out[target] = (r, t)
                break
    return out


def dynamics(index, results, run, n=20):
    """The run and up to n-1 earlier PoC runs on its target, oldest first: what the trend charts draw."""
    runs = [run, *[r for r in earlier_runs(index, run) if not r.upstream_only]][:n]
    out = []
    for i, r in enumerate(reversed(runs)):
        prev = runs[len(runs) - i] if len(runs) - i < len(runs) else None
        counts = r.counts(poc_only=True)
        fixed = regressed = 0
        if prev is not None:
            before = results.of(prev)
            for key, t in results.of(r).items():
                b = before.get(key)
                if b is None:
                    continue
                kind = transition(t.result, b.result) if b.result is not Result.SKIPPED else None
                if kind == "fixed":
                    fixed += 1
                elif kind in ("regressed", "new_error"):
                    regressed += 1
        out.append({"run": r, "counts": counts, "fixed": fixed, "regressed": regressed,
                    "seconds": r.seconds, "compared": prev is not None})
    return out


def stability(index, results, run, cat, track_of, n=FLAKY_WINDOW):
    """{track: (stable, total)}: tests whose result didn't change over their last n results on this target."""
    earlier = [results.of(r) for r in earlier_runs(index, run)]
    out = {}
    for key, t in results.of(run).items():
        if t.result is Result.SKIPPED:
            continue
        seq = [t.result] + [table[key].result for table in earlier if key in table
                            and table[key].result is not Result.SKIPPED][: n - 1]
        track = track_of(cat, t)
        stable, total = out.get(track, (0, 0))
        out[track] = (stable + (1 if len(set(seq)) == 1 else 0), total + 1)
    return out
