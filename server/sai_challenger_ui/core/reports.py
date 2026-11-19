"""Run history from the reports folder: every <target>-<stamp>.xml run_poc.sh wrote is a run.

CLI runs and (later) UI runs share this folder, so history needs no import step. Files are
re-parsed only when they change. Nothing here writes to the folder.
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import junit
from .vocab import Result, empty_counts, headline

# saivpp-1117-103309 (today), saivpp-1005-1037 (older), saivpp-20261118-140200 (with the year, planned)
_STEM_RE = re.compile(r"^(?P<target>[a-z0-9][a-z0-9_-]*?)-(?P<stamp>(?:\d{8}|\d{4})-\d{4}(?:\d{2})?)$")
_BAD = {Result.FAIL, Result.SETUP_ERROR, Result.CLEANUP_ERROR}
_GOOD = {Result.PASS, Result.EXPECTED_GAP}


@dataclass
class Run:
    id: str  # the file stem, e.g. "saivpp-1117-103309"
    target: str
    started: datetime  # UTC
    seconds: float
    xml: Path
    html: Path | None
    log: Path | None
    hostname: str
    tests: list = field(default_factory=list)  # junit.TestResult, in suite order
    source: str = "CLI"

    def counts(self, poc_only=False):
        c = empty_counts()
        for t in self.tests:
            if not (poc_only and t.upstream):
                c[t.result] += 1
        return c

    @property
    def headline(self):
        return headline(self.counts())

    @property
    def upstream_only(self):
        return bool(self.tests) and all(t.upstream for t in self.tests)

    @property
    def modules(self):
        seen = []
        for t in self.tests:
            if t.module not in seen:
                seen.append(t.module)
        return seen


def parse_stem(stem, known_targets=()):
    """('saivs-thrift', '1117-103055') or None for files that aren't runs (tmpgap, pcaps...)."""
    m = _STEM_RE.match(stem)
    if not m:
        return None
    for name in sorted(known_targets, key=len, reverse=True):  # "saivs-thrift" before "saivs"
        if stem.startswith(name + "-") and _STEM_RE.match("x-" + stem[len(name) + 1 :]):
            return name, stem[len(name) + 1 :]
    return m.group("target"), m.group("stamp")


def stamp_time(stamp, mtime):
    """Old stamps have no year: take it from the file date (a December stamp on a January file is last year)."""
    day, clock = stamp.split("-")
    clock = clock.ljust(6, "0")
    file_date = datetime.fromtimestamp(mtime, UTC)
    if len(day) == 8:
        year, month, dom = int(day[:4]), int(day[4:6]), int(day[6:])
    else:
        month, dom = int(day[:2]), int(day[2:])
        year = file_date.year - (1 if month > file_date.month else 0)
    return datetime(year, month, dom, int(clock[:2]), int(clock[2:4]), int(clock[4:6]), tzinfo=UTC)


class RunIndex:
    def __init__(self, reports_dir, known_targets=()):
        self.dir = Path(reports_dir)
        self.known_targets = tuple(known_targets)
        self._cache = {}  # path -> (mtime, Run)
        self.problems = {}  # file name -> why it couldn't be read

    def refresh(self):
        seen = set()
        for xml in self.dir.glob("*.xml"):
            parsed = parse_stem(xml.stem, self.known_targets)
            if not parsed:
                continue
            seen.add(xml)
            try:
                mtime = xml.stat().st_mtime
            except OSError:
                continue
            cached = self._cache.get(xml)
            if cached and cached[0] == mtime:
                continue
            try:
                report = junit.parse(xml)
            except (ET.ParseError, OSError, ValueError) as exc:  # a half-written or corrupt file must not break history
                self.problems[xml.name] = str(exc)
                self._cache.pop(xml, None)
                continue
            self.problems.pop(xml.name, None)
            target, stamp = parsed
            try:
                started = datetime.fromisoformat(report.timestamp).astimezone(UTC)
            except ValueError:
                started = stamp_time(stamp, mtime)
            html, log = xml.with_suffix(".html"), xml.with_suffix(".log")
            run = Run(
                xml.stem, target, started, report.seconds, xml,
                html if html.exists() else None, log if log.exists() else None,
                report.hostname, report.tests,
            )
            self._cache[xml] = (mtime, run)
        for gone in set(self._cache) - seen:
            del self._cache[gone]
        return self.runs()

    def runs(self, target=None):
        """Newest first."""
        runs = [run for _, run in self._cache.values() if target is None or run.target == target]
        return sorted(runs, key=lambda r: (r.started, r.id), reverse=True)

    def get(self, run_id):
        for _, run in self._cache.values():
            if run.id == run_id:
                return run
        return None

    def latest(self, target, poc=True):
        """Newest run on the target; with poc=True, the newest that ran PoC tests (not only upstream)."""
        for run in self.runs(target):
            if not poc or not run.upstream_only:
                return run
        return None

    def previous(self, run):
        """The newest earlier run on the same target that ran at least one of the same tests."""
        keys = {t.key for t in run.tests}
        for other in self.runs(run.target):
            if other.started < run.started and keys & {t.key for t in other.tests}:
                return other
        return None


@dataclass
class Since:
    previous: Run
    compared: int
    new_failures: list  # keys
    fixed: list

    @property
    def text(self):
        parts = []
        if self.new_failures:
            parts.append(f"{len(self.new_failures)} new failure{'s' if len(self.new_failures) != 1 else ''}")
        if self.fixed:
            parts.append(f"{len(self.fixed)} fixed")
        return " · ".join(parts) or "no changes"


def since(previous, run):
    """'Since previous run': changes over the tests both runs ran (design §6.4)."""
    before = {t.key: t.result for t in previous.tests}
    new, fixed, compared = [], [], 0
    for t in run.tests:
        if t.key not in before:
            continue
        compared += 1
        if t.result in _BAD and before[t.key] not in _BAD:
            new.append(t.key)
        elif before[t.key] in _BAD and t.result in _GOOD:
            fixed.append(t.key)
    return Since(previous, compared, new, fixed)
