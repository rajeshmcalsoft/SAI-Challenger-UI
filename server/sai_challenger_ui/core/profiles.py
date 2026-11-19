"""Target profiles (tests/poc/targets/<name>.json): read them and match expected gaps.

Read-only for now. Writing profiles alters the SAI-Challenger checkout, so it comes later and
only with the owner's go-ahead.
"""
import fnmatch
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .vocab import Result

# Keys summarize.py accepts for the two kinds of gap; the conftest reads only "expected_gaps".
_SCOPE_KEYS = ("scope_gaps", "not_in_scope", "out_of_scope")


def gap_matches(test_name, pattern):
    """The conftest rule, exactly: '[' is literal (name[4095]); '*' and '?' stay wildcards."""
    return fnmatch.fnmatchcase(test_name, pattern.replace("[", "[[]"))


def gap_for(test_name, gaps):
    """First pattern in file order that matches, as (pattern, reason); the conftest stops there too."""
    for pattern, reason in gaps.items():
        if gap_matches(test_name, pattern):
            return pattern, reason
    return None


@dataclass
class Profile:
    name: str
    path: Path
    data: dict
    duplicates: list = field(default_factory=list)  # keys listed twice: only the last survives a load
    sha256: str = ""
    error: str = ""  # set when the file can't be read

    @property
    def testbed(self):
        return self.data.get("testbed", "")

    @property
    def lock(self):
        return self.data.get("lock", self.name)

    @property
    def exec_args(self):
        return list(self.data.get("exec_args", []))

    @property
    def ports(self):
        return list(self.data.get("ports", range(8)))  # the conftest's DEFAULT_PORTS

    @property
    def traffic_filters(self):
        return list(self.data.get("traffic_filters", []))

    @property
    def expected_gaps(self):
        gaps = self.data.get("expected_gaps", {})
        return gaps if isinstance(gaps, dict) else {}

    @property
    def scope_gaps(self):
        for key in _SCOPE_KEYS:
            value = self.data.get(key)
            if isinstance(value, dict):
                return dict(value)
            if isinstance(value, list):
                return {str(item): "" for item in value}
        return {}

    @property
    def forwards_traffic(self):
        """None when the profile doesn't say (the key isn't in SAI-Challenger yet)."""
        value = self.data.get("forwards_traffic")
        return value if isinstance(value, bool) else None


def load_profile(path):
    path = Path(path)
    duplicates = []

    def pairs_hook(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                duplicates.append(key)
            seen[key] = value
        return seen

    try:
        raw = path.read_bytes()
        data = json.loads(raw, object_pairs_hook=pairs_hook)
    except (OSError, ValueError) as exc:
        return Profile(path.stem, path, {}, error=f"can't read {path.name}: {exc}")
    return Profile(path.stem, path, data, duplicates, hashlib.sha256(raw).hexdigest())


def load_all(targets_dir):
    """All profiles by name, in name order."""
    return {p.stem: load_profile(p) for p in sorted(Path(targets_dir).glob("*.json"))}


@dataclass
class GapStatus:
    pattern: str
    reason: str
    status: str  # still_fails | now_passes | not_run | not_applied | mixed
    matched: list = field(default_factory=list)  # [(test name, Result)] in the run
    matches_no_test: bool = False  # nothing in the catalogue matches
    listed_twice: bool = False


STATUS_TEXT = {
    "still_fails": "Still fails",
    "now_passes": "Now passes",
    "not_run": "Not run in this run",
    "not_applied": "Recorded but reported as Fail",
    "mixed": "Mixed results",
}


def unrecorded_gaps(profile, run_tests):
    """Expected gaps in a run that no profile pattern explains: xfail called inside a test, which
    the PoC rules forbid (gaps belong in profiles). Shown as a warning, never hidden."""
    return [
        t for t in run_tests
        if t.result in (Result.EXPECTED_GAP, Result.GAP_PASSES) and not t.upstream
        and gap_for(t.name, profile.expected_gaps) is None
    ]


def gap_statuses(profile, run_tests, catalogue_names=None):
    """Each expected gap against one run's PoC tests (and the catalogue, when given)."""
    out = []
    poc = [t for t in run_tests if not t.upstream]
    for pattern, reason in profile.expected_gaps.items():
        matched = [(t.name, t.result) for t in poc if gap_matches(t.name, pattern)]
        results = {r for _, r in matched}
        if not matched:
            status = "not_run"
        elif results <= {Result.EXPECTED_GAP}:
            status = "still_fails"
        elif Result.GAP_PASSES in results and results <= {Result.GAP_PASSES, Result.EXPECTED_GAP}:
            status = "now_passes"
        elif results <= {Result.FAIL}:
            status = "not_applied"
        else:
            status = "mixed"
        no_test = catalogue_names is not None and not any(gap_matches(n, pattern) for n in catalogue_names)
        out.append(GapStatus(pattern, reason, status, matched, no_test, pattern in profile.duplicates))
    return out
