"""The Run page model (design §6.4): result groups in attention order, step scenarios as one row, row detail.

Data only; wording of titles and help lives in the screens. Shared by the preview and the API.
"""
import re
from dataclasses import dataclass, field

from . import catalog, explain, profiles
from .vocab import GROUP_ORDER, RANK, Result

ATTENTION = (Result.FAIL, Result.SETUP_ERROR, Result.CLEANUP_ERROR, Result.GAP_PASSES)


@dataclass
class Entry:
    kind: str  # test | scenario | note | subhead
    result: Result | None = None
    test: object = None  # junit.TestResult, for kind == "test"
    scenario: object = None  # catalog.Scenario, for kind == "scenario"
    steps: list = field(default_factory=list)  # junit.TestResult, for kind == "scenario"
    text: str = ""  # scenario sentence, note or subhead text


@dataclass
class Group:
    result: Result
    count: int  # tests with this result: matches the count line
    entries: list


def track_of(cat, t):
    """The track of one result: from the catalogue, else from the module name; upstream tests are 'Upstream'."""
    if t.upstream:
        return "Upstream"
    ct = cat.find(t.module, t.cls, t.base)
    return ct.track if ct else catalog.track_for(t.module)


def describe(cat, run):
    """'L2 + L3 + ACL · 69 tests', 'Upstream: test_l2_basic · 12 tests'."""
    poc = [t for t in run.tests if not t.upstream]
    upstream = [t for t in run.tests if t.upstream]
    parts = []
    if poc:
        order = {tr: i for i, tr in enumerate(catalog.TRACK_ORDER)}
        tracks = sorted({track_of(cat, t) for t in poc}, key=lambda tr: order.get(tr, 99))
        n = len(poc)
        parts.append(" + ".join(catalog.TRACK_TAG.get(tr, "?") for tr in tracks) + f" · {n} test{'s' if n != 1 else ''}")
    if upstream:
        mods = list(dict.fromkeys(t.module.rsplit("/", 1)[-1] for t in upstream))
        more = f" +{len(mods) - 2}" if len(mods) > 2 else ""
        n = len(upstream)
        parts.append(f"Upstream: {', '.join(mods[:2])}{more} · {n} test{'s' if n != 1 else ''}")
    return " · ".join(parts) or "no tests"


def scenario_items(cat, tests):
    """[(Scenario, [TestResult in step order])] for scenarios present in the run."""
    out = []
    for sc in cat.scenarios:
        steps = [t for st in sc.steps for t in tests if t.module == st.module and t.cls == st.cls and t.base == st.name]
        if steps:
            out.append((sc, steps))
    return out


def scenario_sentence(steps):
    bad = next((t for t in steps if t.result in ATTENTION), None)
    skipped = [t for t in steps if t.result is Result.SKIPPED]
    reasons = {}
    for t in skipped:
        reasons[t.message] = reasons.get(t.message, 0) + 1
    why_skipped = "; ".join(f"{n} × {reason}" for reason, n in reasons.items())
    if bad:
        why = explain.what_happened(bad.result, bad.message, bad.detail) or (bad.message.splitlines() or [""])[0][:120]
        text = f"Stopped at step {catalog.step_number(bad.name) or '?'}: {why.rstrip('.')}."
        return text + (f" {len(skipped)} of {len(steps)} steps skipped ({why_skipped})." if skipped else "")
    if skipped:
        return f"{len(skipped)} of {len(steps)} steps skipped ({why_skipped}). The rest passed."
    return f"All {len(steps)} steps passed."


def build_groups(run, cat, hints, forwards=None, group_title=None):
    """Groups in attention order. forwards: does the target forward packets (for the skipped-reason line)."""
    group_title = group_title or {r: r.value for r in Result}
    counts = run.counts()
    items = {r: [] for r in GROUP_ORDER}
    in_scenario = set()
    for sc, steps in scenario_items(cat, run.tests):
        worst = max((t.result for t in steps), key=lambda r: RANK[r])  # a scenario sits with its worst step
        items[worst].append(Entry("scenario", worst, scenario=sc, steps=steps, text=scenario_sentence(steps)))
        in_scenario.update(t.key for t in steps)
    for t in run.tests:
        if t.key not in in_scenario:
            items[t.result].append(Entry("test", t.result, test=t))

    elsewhere = {r: [] for r in GROUP_ORDER}
    for result in GROUP_ORDER:
        for entry in items[result]:
            if entry.kind == "scenario":
                for r in {t.result for t in entry.steps} - {result}:
                    elsewhere[r].append((entry.scenario.title, result))

    groups = []
    for result in GROUP_ORDER:
        if not counts[result]:
            continue
        entries = items[result]
        if result is Result.SKIPPED:
            by_reason = {}
            for x in entries:
                key = x.test.message if x.kind == "test" else "Scenarios with skipped steps"
                by_reason.setdefault(key, []).append(x)
            entries = []
            for reason, xs in by_reason.items():
                hint = hints.match(Result.SKIPPED, reason)
                if hint and hint.id == "needs-traffic" and forwards is False:
                    text = f"{len(xs)} need traffic: {run.target} doesn't forward packets"
                else:
                    text = f"{len(xs)} · {reason or 'no reason given'}"
                entries.append(Entry("subhead", text=text))
                entries += xs
        if elsewhere[result]:
            places = " and ".join(f"“{title}” (under {group_title[r]})" for title, r in elsewhere[result])
            entries = entries + [Entry("note", text=f"Also counted here: steps inside {places}.")]
        groups.append(Group(result, counts[result], entries))
    return groups


@dataclass
class Detail:
    purpose: str | None
    happened: str | None
    recorded: tuple | None  # (pattern, reason) when the profile records a gap for this test
    unrecorded_gap: bool  # an expected gap that no profile pattern explains (xfail inside the test)
    hint: object  # explain.Hint or None
    location: str | None  # "test_poc_l2.py:63"
    source: list  # [(line number, text, is the failing line)]
    raw: str


def detail(run, t, cat, profile, hints, poc_dir):
    ct = cat.find(t.module, t.cls, t.base)
    happened = explain.what_happened(t.result, t.message, t.detail)
    if not happened and t.message and t.result is not Result.EXPECTED_GAP:
        happened = t.message.splitlines()[0][:200]
    recorded = profiles.gap_for(t.name, profile.expected_gaps) if profile else None
    unrecorded = t.result in (Result.EXPECTED_GAP, Result.GAP_PASSES) and not t.upstream and recorded is None
    hint = hints.match(t.result, t.message, t.detail) if t.result is not Result.SKIPPED else None

    line = None
    for m in re.finditer(r"(test_[A-Za-z0-9_]+)\.py:(\d+)", t.detail):
        if m.group(1) == t.module:
            line = int(m.group(2))
    if line is None and ct:
        line = ct.line
    source, location = [], None
    path = poc_dir / f"{t.module}.py"
    if line is not None and path.is_file():
        location = f"{t.module}.py:{line}"
        if t.result in ATTENTION:
            src = path.read_text().splitlines()
            source = [(n + 1, src[n], n + 1 == line) for n in range(max(line - 3, 0), min(line + 2, len(src)))]
    raw = (t.message + "\n\n" + t.detail).strip()
    return Detail(ct.purpose if ct else None, happened, recorded, unrecorded, hint, location, source, raw)
