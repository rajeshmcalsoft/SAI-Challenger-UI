"""Live progress from run_poc.sh's console (pytest -v), until the JUnit file confirms everything at the end.

Today's run_poc.sh writes no event file, so the console is the only live source (build steps, "Adjustments
made on 18 Nov"). Two things in it differ from the plain pytest words:
- The PoC conftest prints an expected gap (strict xfail) as PASSED, with the gap reason in brackets.
- A gap that passes (strict XPASS) is printed as FAILED.
So a PASSED or FAILED on a test the profile records as a gap is read with that in mind.
"""
import re
from dataclasses import dataclass, field

from . import junit, profiles
from .vocab import RANK, Result

_WORDS = "PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS"
# "poc_rajesh/test_poc_l2.py::test_x[0] PASSED (Target accepts VLAN ID 0)                        [ 12%]"
_RESULT_RE = re.compile(
    rf"^(?P<node>[^\s:]\S*::\S+?)(?: <- \S+)?\s+(?P<word>{_WORDS})(?: \((?P<reason>.*)\))?\s*(?:\[\s*\d+%\])?\s*$"
)
# The node ID alone: pytest prints it when the test starts, and the word when it ends.
_START_RE = re.compile(r"^(?P<node>[^\s:]\S*::\S+?)(?: <- \S+)?\s*$")
_COLLECTED_RE = re.compile(r"collected (\d+) items?(?: / (\d+) deselected)?(?: / (\d+) selected)?")
_REPORT_RE = re.compile(r"^report: .*/(?P<id>[^/\s]+)\.\{html,xml\}\s+exit=(?P<rc>-?\d+)\s*$")
_MOUNT_RE = re.compile(r"^poc(_[A-Za-z0-9]+)?$")
_MAP = {
    "PASSED": Result.PASS, "FAILED": Result.FAIL, "SKIPPED": Result.SKIPPED,
    "XFAIL": Result.EXPECTED_GAP, "XPASS": Result.GAP_PASSES,
}


@dataclass
class Progress:
    waiting: bool = False  # run_poc.sh said it is waiting for the lock and pytest hasn't started
    started: bool = False  # pytest's session header was printed
    collected: int | None = None  # tests pytest will run (after deselection)
    tests: list = field(default_factory=list)  # junit.TestResult in the order they finished
    current: str | None = None  # node ID of the test running now
    report: str | None = None  # run id from run_poc.sh's last line
    exit_code: int | None = None
    interrupted: str = ""  # "Interrupted: 1 error during collection"
    profile_line: str = ""  # "poc target profile: saivs | mld filter: off"

    @property
    def done(self):
        return len(self.tests)


def split_node(node):
    """'poc_rajesh/test_poc_acl.py::TestPocAclDrop::test_x[1]' -> (module, cls, name, upstream, mount)."""
    path, *rest = node.split("::")
    parts = [p for p in path.removesuffix(".py").split("/") if p]
    mount = ""
    if parts and _MOUNT_RE.match(parts[0]):
        mount = parts.pop(0)
    name = rest[-1] if rest else "(collection)"
    cls = rest[0] if len(rest) > 1 else None
    return "/".join(parts), cls, name, not mount, mount


def _result(word, reason, name, upstream, gaps):
    """The UI word for one console line, given the profile's expected gaps."""
    gap = None if upstream else profiles.gap_for(name, gaps)
    if word == "PASSED" and (reason or gap):
        return Result.EXPECTED_GAP, reason or gap[1]
    if word == "FAILED" and gap:
        return Result.GAP_PASSES, ""
    return _MAP.get(word, Result.FAIL), reason or ""


def parse(text, gaps=None):
    """Read the whole console text written so far. gaps: the target's expected_gaps (pattern -> reason)."""
    gaps = gaps or {}
    p = Progress()
    by_key = {}
    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        if line.startswith("Waiting for the ") and line.rstrip().endswith("lock..."):
            p.waiting = True
            continue
        if "test session starts" in line:
            p.started, p.waiting = True, False
            continue
        if line.startswith("poc target profile:"):
            p.profile_line = line.strip()
            continue
        m = _COLLECTED_RE.search(line)
        if m and not p.tests:
            collected, deselected, selected = (int(g) if g else None for g in m.groups())
            p.collected = selected if selected is not None else collected - (deselected or 0)
            continue
        m = _REPORT_RE.match(line)
        if m:
            p.report, p.exit_code = m.group("id"), int(m.group("rc"))
            continue
        if line.startswith("!!!") and "Interrupted:" in line:
            p.interrupted = line.strip("! ").strip()
            continue
        m = _RESULT_RE.match(line)
        if m:
            node, word = m.group("node"), m.group("word")
            module, cls, name, upstream, mount = split_node(node)
            key = "::".join(x for x in (module, cls, name) if x)
            result, message = _result(word, m.group("reason"), name, upstream, gaps)
            old = by_key.get(key)
            if old is None:
                if word == "ERROR":
                    result = Result.SETUP_ERROR
                t = junit.TestResult(key, module, cls, name, result, 0.0, message, "", upstream, False, mount)
                by_key[key] = t
                p.tests.append(t)
            elif word == "ERROR":  # a second line for the same test: its teardown failed
                old.cleanup_failed = True
                if RANK[Result.CLEANUP_ERROR] > RANK[old.result]:
                    old.result, old.message = Result.CLEANUP_ERROR, message
            if p.current == node:
                p.current = None
            continue
        m = _START_RE.match(line)
        if m:  # the last line while a test runs: its node ID, and the word comes when it ends
            p.current = m.group("node")
    if p.report or p.interrupted:
        p.current = None
    if p.current:  # a node ID on its own line elsewhere (the warnings summary) for a test that already ended
        module, cls, name, _, _ = split_node(p.current)
        if "::".join(x for x in (module, cls, name) if x) in by_key:
            p.current = None
    return p
