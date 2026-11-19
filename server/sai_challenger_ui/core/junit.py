"""Read one pytest JUnit XML report (as written by run_poc.sh) into UI results.

Unlike summarize.py, a setup or teardown error is kept apart from a failure: a broken fixture
is not a target gap (design doc §3).
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .vocab import RANK, Result, empty_counts

# First classname segment of a PoC test: the mount, e.g. "poc_rajesh" (or plain "poc").
_MOUNT_RE = re.compile(r"^poc(_[A-Za-z0-9]+)?$")
_XPASS_RE = re.compile(r"^\[XPASS\(strict\)\]\s*")
_PHASE_RE = re.compile(r'^failed on (setup|teardown) with "(.*)"$', re.DOTALL)


@dataclass
class TestResult:
    __test__ = False  # not a pytest test class, despite the name

    key: str  # "test_poc_acl::TestPocAclDrop::test_x[4095]", unique within a run
    module: str  # "test_poc_l2"; upstream tests keep their folder: "ut/test_vlan_ut"
    cls: str | None
    name: str  # pytest item name, parameters included: what expected_gaps patterns match
    result: Result
    seconds: float
    message: str = ""  # failure message, skip reason or expected-gap reason
    detail: str = ""  # full text pytest wrote (traceback); raw-detail view only
    upstream: bool = False  # not from tests/poc: expected gaps never apply
    cleanup_failed: bool = False  # a teardown error on top of the main result
    mount: str = ""

    @property
    def base(self):
        return self.name.split("[", 1)[0]

    @property
    def param(self):
        return self.name[len(self.base) + 1 : -1] if "[" in self.name else None


@dataclass
class Report:
    path: str
    timestamp: str  # ISO 8601 from <testsuite>, with the year and the zone
    seconds: float
    hostname: str
    tests: list[TestResult] = field(default_factory=list)

    def counts(self):
        c = empty_counts()
        for t in self.tests:
            c[t.result] += 1
        return c


def split_classname(classname):
    """'poc_rajesh.test_poc_acl.TestPocAclDrop' -> ('test_poc_acl', 'TestPocAclDrop', False, 'poc_rajesh')."""
    parts = [p for p in classname.split(".") if p]
    mount = ""
    if parts and _MOUNT_RE.match(parts[0]):
        mount = parts.pop(0)
    cls = parts.pop() if parts and parts[-1][:1].isupper() else None
    return "/".join(parts), cls, not mount, mount


def _texts(el):
    return (el.get("message") or "").strip(), (el.text or "").strip()


def classify(testcase):
    """Return (result, message, detail, cleanup_failed) for one <testcase>."""
    failure = testcase.find("failure")
    error = testcase.find("error")
    skipped = testcase.find("skipped")
    teardown_error = error is not None and (error.get("message") or "").startswith("failed on teardown")

    if failure is not None:
        message, detail = _texts(failure)
        if "XPASS(strict)" in message:
            return Result.GAP_PASSES, _XPASS_RE.sub("", message), detail, teardown_error
        return Result.FAIL, message, detail, teardown_error

    if error is not None:
        message, detail = _texts(error)
        if "XPASS(strict)" in message:  # summarize.py treats it the same way
            return Result.GAP_PASSES, _XPASS_RE.sub("", message), detail, False
        phase = _PHASE_RE.match(message)
        if phase:
            message = phase.group(2)
        if teardown_error:
            return Result.CLEANUP_ERROR, message, detail, True
        return Result.SETUP_ERROR, message, detail, False

    if skipped is not None:
        message, detail = _texts(skipped)
        if "xfail" in (skipped.get("type") or "").lower():
            return Result.EXPECTED_GAP, message, detail, False
        return Result.SKIPPED, message, detail, False

    return Result.PASS, "", "", False


def parse(path):
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    report = Report(path=str(path), timestamp="", seconds=0.0, hostname="")
    by_key = {}

    for suite in suites:
        report.timestamp = report.timestamp or suite.get("timestamp", "")
        report.hostname = report.hostname or suite.get("hostname", "")
        report.seconds += _float(suite.get("time"))

        for tc in suite.iter("testcase"):
            classname, name = tc.get("classname", ""), tc.get("name", "?")
            if not classname and tc.find("error") is not None:
                # Collection failure: pytest puts the module in the name.
                module, cls, upstream, mount = split_classname(name)
                name, cls = "(collection)", None
            else:
                module, cls, upstream, mount = split_classname(classname)
            result, message, detail, cleanup_failed = classify(tc)
            if name == "(collection)":
                message = message or "collection failure"
            key = "::".join(p for p in (module, cls, name) if p)
            seconds = _float(tc.get("time"))

            old = by_key.get(key)
            if old is None:
                by_key[key] = TestResult(
                    key, module, cls, name, result, seconds, message, detail, upstream, cleanup_failed, mount
                )
                continue
            # Same test written twice (a test plus a teardown error): keep the worst, add the time.
            old.seconds += seconds
            old.cleanup_failed = old.cleanup_failed or cleanup_failed or result is Result.CLEANUP_ERROR
            if RANK[result] > RANK[old.result]:
                old.result, old.message, old.detail = result, message, detail

    report.tests = list(by_key.values())
    return report


def _float(value):
    try:
        return float(value or 0)
    except ValueError:
        return 0.0
