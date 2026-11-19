"""Conformance gate: rules a run must meet (Allure's quality gate, design §4 F3).

The rules are checked by the UI on each run; nothing changes how run_poc.sh exits. The defaults below can be
replaced with a gates.toml in the UI's config folder (~/.config/sai-challenger-ui/gates.toml), same shape:

    [[rule]]
    id = "no-fail"
    type = "max_results"   # max_results | full_suite | all_tracks | gaps_in_profile | max_test_seconds | min_pass_rate
    results = ["fail"]     # for max_results
    max = 0                # for max_results and max_test_seconds
    min = 0.9              # for min_pass_rate (Pass divided by tests that ran, skipped left out)
    title = "No test fails"
"""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import catalog, profiles
from .vocab import LABEL, Result

DEFAULT_RULES = [
    {"id": "no-fail", "type": "max_results", "results": ["fail"], "max": 0, "title": "No test fails"},
    {"id": "no-stale-gap", "type": "max_results", "results": ["gap_passes"], "max": 0,
     "title": "No expected gap passes (stale gaps removed)"},
    {"id": "no-errors", "type": "max_results", "results": ["setup_error", "cleanup_error"], "max": 0,
     "title": "No setup or cleanup errors"},
    {"id": "full-suite", "type": "full_suite", "title": "The full PoC suite ran"},
    {"id": "gaps-in-profile", "type": "gaps_in_profile", "title": "Every expected gap is recorded in the profile"},
    {"id": "max-duration", "type": "max_test_seconds", "max": 120, "title": "No test takes longer than 120 s"},
]
TYPES = ("max_results", "full_suite", "all_tracks", "gaps_in_profile", "max_test_seconds", "min_pass_rate")


@dataclass
class RuleResult:
    id: str
    title: str
    passed: bool
    actual: str
    expected: str
    keys: list = field(default_factory=list)  # the tests that break the rule


@dataclass
class Verdict:
    rules: list

    @property
    def passed(self):
        return all(r.passed for r in self.rules)

    @property
    def failed(self):
        return [r for r in self.rules if not r.passed]


def load_rules(config_dir):
    """The rules from <config_dir>/gates.toml, or the defaults. A file that can't be read falls back to the defaults
    and says why."""
    path = Path(config_dir) / "gates.toml"
    if not path.is_file():
        return DEFAULT_RULES, ""
    try:
        with open(path, "rb") as f:
            rules = tomllib.load(f).get("rule", [])
        rules = [r for r in rules if isinstance(r, dict) and r.get("type") in TYPES and r.get("id")]
        return (rules or DEFAULT_RULES), ("" if rules else f"{path} has no usable rules: using the defaults")
    except (OSError, ValueError) as exc:
        return DEFAULT_RULES, f"{path} can't be read ({exc}): using the defaults"


def check(run, cat, profile, rules):
    poc = [t for t in run.tests if not t.upstream and t.name != "(collection)"]
    out = []
    for rule in rules:
        kind, title = rule["type"], rule.get("title") or rule["id"]
        if kind == "max_results":
            wanted = [Result(r) for r in rule.get("results", []) if r in Result._value2member_map_]
            hit = [t.key for t in poc if t.result in wanted]
            limit = int(rule.get("max", 0))
            words = " or ".join(LABEL[r].lower() if i else LABEL[r] for i, r in enumerate(wanted))
            out.append(RuleResult(rule["id"], title, len(hit) <= limit, f"{len(hit)}", f"at most {limit} {words}", hit))
        elif kind == "full_suite":
            names = {(ct.module, ct.cls, n) for ct in cat.tests for n in ct.names}
            ran = {(t.module, t.cls, t.name) for t in poc}
            missing = sorted(names - ran)
            out.append(RuleResult(rule["id"], title, not missing, f"{len(names) - len(missing)} of {len(names)} ran",
                                  f"all {len(names)}", ["::".join(p for p in m if p) for m in missing][:200]))
        elif kind == "all_tracks":
            want = [catalog.TRACKS[m] for m in ("l2", "l3", "acl", "counters")]
            have = set()
            for t in poc:
                ct = cat.find(t.module, t.cls, t.base)
                have.add(ct.track if ct else catalog.track_for(t.module))
            missing = [catalog.TRACK_TAG[w] for w in want if w not in have]
            out.append(RuleResult(rule["id"], title, not missing,
                                  "all ran" if not missing else f"{', '.join(missing)} didn't run", "L2, L3, ACL, Counters"))
        elif kind == "gaps_in_profile":
            bad = [t.key for t in profiles.unrecorded_gaps(profile, poc)] if profile else []
            out.append(RuleResult(rule["id"], title, not bad, f"{len(bad)} not in the profile", "none", bad))
        elif kind == "max_test_seconds":
            limit = float(rule.get("max", 120))
            slow = [t.key for t in poc if t.seconds > limit]
            longest = max((t.seconds for t in poc), default=0.0)
            out.append(RuleResult(rule["id"], title, not slow, f"longest {longest:.1f} s", f"at most {limit:g} s", slow))
        elif kind == "min_pass_rate":
            ran = [t for t in poc if t.result is not Result.SKIPPED]
            rate = sum(1 for t in ran if t.result is Result.PASS) / len(ran) if ran else 0.0
            want = float(rule.get("min", 0.9))
            out.append(RuleResult(rule["id"], title, rate >= want, f"{rate:.0%}", f"at least {want:.0%}"))
    return Verdict(out)
