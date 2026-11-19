"""Compare targets and runs: the matrix (the UI form of summarize.py), run diff, gap register, test history.

Standard library only; the preview renders these now and the API will serve them later.
"""
import re
from dataclasses import dataclass, field

from . import catalog
from .profiles import gap_for, gap_statuses
from .vocab import RANK, Result, plural

REFERENCE_ORDER = ("saivs", "saivs-thrift", "saivpp")  # summarize.py's column order
BAD = {Result.FAIL, Result.SETUP_ERROR, Result.CLEANUP_ERROR}
GOOD = {Result.PASS, Result.EXPECTED_GAP}
_STATUS = re.compile(r"SAI_STATUS_[A-Z_]+")


def column_key(target):
    return (REFERENCE_ORDER.index(target) if target in REFERENCE_ORDER else len(REFERENCE_ORDER), target)


def worst(results):
    results = [r for r in results if r is not None]
    return max(results, key=lambda r: RANK[r]) if results else None


def ident(t):
    """A test across runs and variants: (module, class, function)."""
    return t.module, t.cls, t.base


# ---------------------------------------------------------------- matrix

@dataclass
class Cell:
    result: Result | None  # None: not in that run
    message: str = ""
    seconds: float = 0.0
    run_id: str = ""
    gap: tuple | None = None  # (pattern, reason) from the target's profile
    steps: list | None = None  # scenario rows: [(number, Result, message, name)]


@dataclass
class Row:
    key: str
    track: str
    module: str
    title: str
    test_id: str
    scenario: bool
    position: int
    cells: dict = field(default_factory=dict)  # target -> Cell
    badges: list = field(default_factory=list)  # [(kind, target)]: new_gap | not_applied | stale_gap | changed
    recent: dict = field(default_factory=dict)  # target -> [Result] newest first, when it changed

    @property
    def differs(self):
        return len({c.result for c in self.cells.values()}) > 1 or bool(self.recent)


@dataclass
class Matrix:
    columns: list  # Run, in column order
    rows: list
    attention: dict  # target -> [str]

    @property
    def differing(self):
        return [r for r in self.rows if r.differs]


BADGE_TEXT = {
    "new_gap": "New gap",
    "not_applied": "Gap not applied",
    "stale_gap": "Stale gap",
    "changed": "Changed in recent runs",
}


def _scenario_summary(steps):
    bad = next((s for s in steps if s[1] in BAD or s[1] is Result.GAP_PASSES), None)
    if bad:
        first = bad[2].splitlines()[0][:100] if bad[2] else ""
        return f"stopped at step {bad[0]}" + (f": {first}" if first else "")
    skipped = sum(1 for s in steps if s[1] is Result.SKIPPED)
    return f"{skipped} of {len(steps)} steps skipped" if skipped else f"all {len(steps)} steps passed"


def build_matrix(runs, profiles, cat, index=None, recent=3):
    """One column per run (newest PoC run per target, usually), one row per test or step scenario."""
    runs = sorted(runs, key=lambda r: column_key(r.target))
    scenario_of = {(st.module, st.cls, st.name): sc for sc in cat.scenarios for st in sc.steps}
    position = {(t.module, t.cls, t.name): i for i, t in enumerate(cat.tests)}
    rows = {}

    for run in runs:
        gaps = profiles[run.target].expected_gaps if run.target in profiles else {}
        for t in run.tests:
            if t.upstream or t.name == "(collection)":
                continue
            sc = scenario_of.get(ident(t))
            ct = cat.find(*ident(t))
            track = ct.track if ct else catalog.track_for(t.module)
            if sc:
                key = f"scenario::{sc.module}::{sc.cls or ''}"
                pos = min(position.get((s.module, s.cls, s.name), 10**6) for s in sc.steps)
                row = rows.setdefault(key, Row(key, track, sc.module, sc.title, sc.cls or sc.module, True, pos))
                cell = row.cells.setdefault(run.target, Cell(None, run_id=run.id, steps=[]))
                cell.steps.append((catalog.step_number(t.name) or "?", t.result, t.message, t.name))
                cell.seconds += t.seconds
            else:
                title = catalog.readable(t.name) + (f" · {t.param}" if t.param else "")
                pos = position.get(ident(t), 10**6)
                row = rows.setdefault(t.key, Row(t.key, track, t.module, title, t.name, False, pos))
                row.cells[run.target] = Cell(t.result, t.message, t.seconds, run.id, gap_for(t.name, gaps))

    for row in rows.values():
        for run in runs:
            cell = row.cells.setdefault(run.target, Cell(None, run_id=run.id))
            if cell.steps:
                cell.result = worst(s[1] for s in cell.steps)
                cell.message = _scenario_summary(cell.steps)

    _badges(rows.values(), runs, profiles)
    if index is not None:
        _recent_changes(rows.values(), runs, index, recent)

    track_rank = {t: i for i, t in enumerate(catalog.TRACK_ORDER)}
    ordered = sorted(rows.values(), key=lambda r: (track_rank.get(r.track, 99), r.module, r.position, r.key))
    return Matrix(runs, ordered, _attention(ordered, runs, profiles))


def _badges(rows, runs, profiles):
    for row in rows:
        for run in runs:
            cell = row.cells[run.target]
            gaps = profiles[run.target].expected_gaps if run.target in profiles else {}
            if row.scenario and cell.steps:
                for _, result, _, name in cell.steps:
                    if result is Result.FAIL:
                        row.badges.append(("not_applied" if gap_for(name, gaps) else "new_gap", run.target))
                        break
                if any(s[1] is Result.GAP_PASSES for s in cell.steps):
                    row.badges.append(("stale_gap", run.target))
                continue
            if cell.result is Result.FAIL:
                row.badges.append(("not_applied" if cell.gap else "new_gap", run.target))
            elif cell.result is Result.GAP_PASSES:
                row.badges.append(("stale_gap", run.target))


def _recent_changes(rows, runs, index, n):
    """'Changed in recent runs': the test's result differs across the last n runs on that target that ran it."""
    lookups = {}
    for run in runs:
        history = [r for r in index.runs(run.target) if r.started <= run.started and not r.upstream_only][:15]
        lookups[run.target] = [{t.key: t.result for t in r.tests} for r in history]
    for row in rows:
        if row.scenario:
            continue
        for run in runs:
            seen = [d[row.key] for d in lookups[run.target] if row.key in d][:n]
            if len(set(seen)) > 1:
                row.recent[run.target] = seen
                row.badges.append(("changed", run.target))


def _attention(rows, runs, profiles):
    out = {}
    for run in runs:
        items = []
        prof = profiles.get(run.target)
        if prof is None:
            items.append("no profile found")
        new = sum(1 for r in rows if ("new_gap", run.target) in r.badges)
        stale = sum(1 for r in rows if ("stale_gap", run.target) in r.badges)
        not_applied = sum(1 for r in rows if ("not_applied", run.target) in r.badges)
        if new:
            items.append(plural(new, "new gap", "new gaps"))
        if stale:
            items.append(plural(stale, "stale gap", "stale gaps"))
        if not_applied:
            items.append(plural(not_applied, "gap not applied", "gaps not applied"))
        if prof and prof.duplicates:
            items.append(f"{plural(len(prof.duplicates), 'key', 'keys')} listed twice in {run.target}.json")
        out[run.target] = items
    return out


# ---------------------------------------------------------------- run diff

DIFF_SECTIONS = (
    "New failures", "Fixed", "Gap now passes", "New expected gaps", "Gaps removed",
    "Became skipped", "No longer skipped", "Reason changed",
)


def _diff_kind(a, b):
    ra, rb = a.result, b.result
    if rb in BAD and ra not in BAD:
        return "New failures"
    if rb is Result.GAP_PASSES and ra is not Result.GAP_PASSES:
        return "Gap now passes"
    if rb is Result.EXPECTED_GAP and ra is not Result.EXPECTED_GAP:
        return "New expected gaps"
    if ra in BAD and rb in GOOD:
        return "Fixed"
    if ra is Result.EXPECTED_GAP and rb is not Result.EXPECTED_GAP:
        return "Gaps removed"
    if rb is Result.SKIPPED and ra is not Result.SKIPPED:
        return "Became skipped"
    if ra is Result.SKIPPED and rb is not Result.SKIPPED:
        return "No longer skipped"
    if ra == rb and ra in (Result.EXPECTED_GAP, Result.SKIPPED) and a.message != b.message:
        return "Reason changed"
    if ra != rb:
        return "Fixed" if rb is Result.PASS else "New failures"
    return None


@dataclass
class Diff:
    a: object
    b: object
    sections: dict  # title -> [(a TestResult, b TestResult)]
    only_a: int
    only_b: int
    compared: int

    @property
    def headline(self):
        parts = [plural(len(v), *_DIFF_WORDS[k]) for k, v in self.sections.items() if v]
        return f"{self.b.target} against {self.a.target}: " + (", ".join(parts) if parts else "same results")


_DIFF_WORDS = {
    "New failures": ("new failure", "new failures"),
    "Fixed": ("fixed", "fixed"),
    "Gap now passes": ("gap now passes", "gaps now pass"),
    "New expected gaps": ("new expected gap", "new expected gaps"),
    "Gaps removed": ("gap removed", "gaps removed"),
    "Became skipped": ("became skipped", "became skipped"),
    "No longer skipped": ("no longer skipped", "no longer skipped"),
    "Reason changed": ("reason changed", "reasons changed"),
}


def run_diff(a, b):
    """B against A, over the PoC tests both ran (runs on different targets are allowed)."""
    before = {t.key: t for t in a.tests if not t.upstream}
    after = {t.key: t for t in b.tests if not t.upstream}
    sections = {s: [] for s in DIFF_SECTIONS}
    for key, tb in after.items():
        ta = before.get(key)
        if ta is None:
            continue
        kind = _diff_kind(ta, tb)
        if kind:
            sections[kind].append((ta, tb))
    both = before.keys() & after.keys()
    return Diff(a, b, sections, len(before.keys() - both), len(after.keys() - both), len(both))


# ---------------------------------------------------------------- gap register

@dataclass
class GapEntry:
    pattern: str
    scope: bool = False  # an out-of-scope item ("Not tested on this target")
    reasons: dict = field(default_factory=dict)  # target -> reason
    status: dict = field(default_factory=dict)  # target -> still_fails | now_passes | not_run | ...
    returned: dict = field(default_factory=dict)  # target -> SAI_STATUS_* named in the reason
    evidence: dict = field(default_factory=dict)  # target -> run id
    flags: list = field(default_factory=list)  # "matches no test", "listed twice in saivpp.json"


def gap_register(profiles, latest, catalogue_names):
    """Every expected gap and out-of-scope item across profiles; latest = {target: Run or None}."""
    entries = {}
    for target in sorted(profiles, key=column_key):
        prof = profiles[target]
        run = latest.get(target)
        statuses = {g.pattern: g for g in gap_statuses(prof, run.tests if run else [], catalogue_names)}
        for pattern, reason in prof.expected_gaps.items():
            e = entries.setdefault(("gap", pattern), GapEntry(pattern))
            g = statuses[pattern]
            e.reasons[target] = reason
            e.status[target] = g.status if run else "not_run"
            m = _STATUS.search(reason)
            e.returned[target] = m.group(0) if m else ""
            if run:
                e.evidence[target] = run.id
            if g.matches_no_test and "matches no test" not in e.flags:
                e.flags.append("matches no test")
            if g.listed_twice:
                e.flags.append(f"listed twice in {target}.json")
        for item, reason in prof.scope_gaps.items():
            e = entries.setdefault(("scope", item), GapEntry(item, scope=True))
            e.reasons[target] = reason
    return list(entries.values())


_EXPECTED = re.compile(r"expected (SAI_STATUS_[A-Z_]+|[A-Z][A-Z_]{3,})")
_EVIDENCE_WORD = {"still_fails": "xfail", "now_passes": "XPASS(strict)", "not_applied": "failed", "mixed": "mixed"}


def runbook_table(register):
    """The RUNBOOK §9 gap table as Markdown: one row per gap and target, in its exact columns."""
    lines = ["| Gap | Target | Test | What the target does (profile reason) | Expected | Evidence |",
             "|---|---|---|---|---|---|"]
    for g in register:
        if g.scope:
            continue
        for target, reason in g.reasons.items():
            short = re.split(r"[,;(]", reason, maxsplit=1)[0].strip()
            m = _EXPECTED.search(reason)
            expected = (m.group(1) if m.group(1).startswith("SAI_STATUS_") else "SAI_STATUS_" + m.group(1)) if m else "-"
            run_id = g.evidence.get(target)
            status = g.status.get(target, "not_run")
            if run_id and status in _EVIDENCE_WORD:
                evidence = f"{run_id}.xml ({_EVIDENCE_WORD[status]})"
            elif run_id:
                evidence = f"{run_id}.xml (not in that run)"
            else:
                evidence = "no report yet (-)"
            cell = reason.replace("|", "\\|")
            lines.append(f"| {short} | {target} | `{g.pattern}` | {cell} | {expected} | {evidence} |")
    return "\n".join(lines)


# ---------------------------------------------------------------- per-test results and history

class Lookup:
    """Worst result per test (all variants) in each run, computed once per run."""

    def __init__(self):
        self._cache = {}

    def results(self, run):
        table = self._cache.get(run.id)
        if table is None:
            table = {}
            for t in run.tests:
                if not t.upstream:
                    table.setdefault(ident(t), []).append(t)
            self._cache[run.id] = table
        return table

    def worst_in(self, run, key):
        tests = self.results(run).get(key)
        return worst(t.result for t in tests) if tests else None

    def history(self, index, target, key, n=20):
        """[(run id, worst result)] oldest first, for the last n runs on the target that ran the test."""
        out = []
        for run in index.runs(target):
            r = self.worst_in(run, key)
            if r is not None:
                out.append((run.id, r))
                if len(out) == n:
                    break
        return out[::-1]
