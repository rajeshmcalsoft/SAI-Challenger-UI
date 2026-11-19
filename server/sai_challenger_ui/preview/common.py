"""Shared pieces of the static preview: loading, helpers, the help component and help texts."""
import html
import itertools
import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import settings as settings_mod
from ..core import catalog, compare, explain, profiles, reports, testbed
from ..core.vocab import GLYPH, LABEL, Result

ROOT = Path(__file__).resolve().parents[3]  # ~/SAI-Challenger-UI
STYLES = ROOT / "web" / "src" / "styles"
e = html.escape
R = Result
ATTENTION = (R.FAIL, R.SETUP_ERROR, R.CLEANUP_ERROR, R.GAP_PASSES)
TAG = {
    catalog.TRACKS["l2"]: "L2", catalog.TRACKS["l3"]: "L3", catalog.TRACKS["acl"]: "ACL",
    catalog.TRACKS["counters"]: "Counters", catalog.FRAMEWORK: "Framework", "Upstream": "Upstream", "Other": "Other",
}
LETTER = dict(catalog.TRACK_LETTER, Upstream="U", Other="?")
_ids = itertools.count(1)

# What each result means and what to do about it: the detail behind the "?" on each group.
RESULT_HELP = {
    R.FAIL: "The target did not do what the SAI spec says, and its profile records no expected gap for this test. "
            "If the target is at fault, add an expected gap with the returned status as the reason. If the test "
            "is wrong, fix the test instead: expected results follow the spec, never a target.",
    R.SETUP_ERROR: "The test could not get going: a fixture or its setup raised an error before the check ran. "
                   "It says nothing about the target. Fix the cause and rerun.",
    R.CLEANUP_ERROR: "The check finished but its cleanup failed. Objects may be left on the switch, so the next run "
                     "can fail with “already exists”. A container restart clears them.",
    R.GAP_PASSES: "Recorded as expected gaps, but they passed (pytest's strict XPASS). The target was fixed or the "
                  "gap is wrong: remove the gap so the test counts as a pass again.",
    R.EXPECTED_GAP: "Known deviations from the SAI spec, recorded in the target's profile "
                    "(tests/poc/targets/<target>.json) as strict xfail. They fail as recorded. If one starts "
                    "passing, it moves to “Gap now passes”.",
    R.SKIPPED: "Not run on purpose, and the reason is always shown. Traffic tests skip on targets that don't "
               "forward packets; scenario steps skip when a step they need did not pass.",
    R.PASS: "The target did what the SAI spec says.",
}


@dataclass
class Ctx:
    s: settings_mod.Settings
    profiles: dict
    index: reports.RunIndex
    cat: catalog.Catalogue
    hints: explain.Hints
    containers: dict
    docker_error: str | None
    latest: dict  # target -> newest run that ran PoC tests, or None
    lookup: compare.Lookup = field(default_factory=compare.Lookup)
    opened: set = field(default_factory=set)  # per run page: only the first row needing attention starts open


def load():
    s = settings_mod.load()
    profs = profiles.load_all(s.targets_dir)
    index = reports.RunIndex(s.reports_dir, profs)
    runs = index.refresh()
    cat = catalog.build(s.poc_dir)
    catalog.merge_history(cat, runs)
    try:
        containers, docker_error = testbed.containers(), None
    except testbed.DockerUnavailable as exc:
        containers, docker_error = {}, str(exc)
    latest = {name: index.latest(name) for name in sorted(profs, key=compare.column_key)}
    return Ctx(s, profs, index, cat, explain.Hints(), containers, docker_error, latest)


# ---------------------------------------------------------------- formatting

def duration(seconds):
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m"


def when(dt):
    return dt.astimezone().strftime("%d %b %H:%M %Z").lstrip("0")


def track_of(ctx, t):
    if t.upstream:
        return "Upstream"
    ct = ctx.cat.find(t.module, t.cls, t.base)
    return ct.track if ct else catalog.track_for(t.module)


def title_of(t):
    if t.name == "(collection)":
        return f"Collection failed: {t.module}.py"
    title = catalog.readable(t.name)
    return f"{title} · {t.param}" if t.param else title


def glyph(result):
    if result is None:
        return '<span class="g faint" aria-label="Not in that run">—</span>'
    return f'<span class="g {result.value}" aria-label="{LABEL[result]}">{GLYPH[result]}</span>'


def strip(ctx, tests, letters=False):
    """One cell per test in suite order, a gap between tracks; track letters only where asked."""
    cells, marks, last = [], [], None
    for t in tests:
        track = track_of(ctx, t)
        sep = " sep" if last is not None and track != last else ""
        cells.append(f'<span class="cell {t.result.value}{sep}" title="{e(LABEL[t.result])}: {e(title_of(t))}"></span>')
        marks.append(f'<span class="{sep.strip()}">{LETTER.get(track, "?") if track != last else ""}</span>')
        last = track
    under = f'<span class="letters" aria-hidden="true">{"".join(marks)}</span>' if letters else ""
    return (f'<span class="strip" role="img" aria-label="Result strip: {len(tests)} tests">'
            f'<span class="cells">{"".join(cells)}</span>{under}</span>')


def mini_strip(results):
    cells = "".join(f'<span class="cell {r.value}" title="{e(rid)}: {e(LABEL[r])}"></span>' for rid, r in results)
    return f'<span class="strip" role="img" aria-label="{len(results)} runs"><span class="cells">{cells}</span></span>'


def where(ctx, t):
    """(file:line, five source lines with the line highlighted) from the traceback, else the def line."""
    path = ctx.s.poc_dir / f"{t.module}.py"
    line = None
    for m in re.finditer(r"(test_[A-Za-z0-9_]+)\.py:(\d+)", t.detail):
        if m.group(1) == t.module:
            line = int(m.group(2))
    if line is None:
        ct = ctx.cat.find(t.module, t.cls, t.base)
        line = ct.line if ct else None
    if line is None or not path.is_file():
        return None, ""
    src = path.read_text().splitlines()
    out = []
    for n in range(max(line - 3, 0), min(line + 2, len(src))):
        text = e(f"{n + 1:>4}  {src[n]}")
        out.append(f'<span class="hl">{text}</span>' if n + 1 == line else text)
    return f"{t.module}.py:{line}", "\n".join(out)


# ---------------------------------------------------------------- help: a circled ? with detail on hover or focus

def p(text):
    return f"<p>{e(text)}</p>"


def dl(pairs):
    return "<dl>" + "".join(f"<dt>{e(k)}</dt><dd>{e(str(v))}</dd>" for k, v in pairs) + "</dl>"


def help_(body, *, label="More about this", left=False, corner=False, title=None):
    """body is HTML built with p()/dl(); everything inside is already escaped."""
    tip_id = f"tip{next(_ids)}"
    cls = "help" + (" left" if left else "") + (" corner" if corner else "")
    head = f'<div class="tip-title">{e(title)}</div>' if title else ""
    return (f'<span class="{cls}" tabindex="0" aria-label="{e(label)}" aria-describedby="{tip_id}">'
            f'<span class="help-icon" aria-hidden="true">?</span>'
            f'<span class="help-tip" role="tooltip" id="{tip_id}">{head}{body}</span></span>')


def tipped(trigger, body, *, left=False):
    """Any element (a matrix glyph) that shows a tip on hover or focus."""
    tip_id = f"tip{next(_ids)}"
    return (f'<span class="help tipped{" left" if left else ""}" tabindex="0" aria-describedby="{tip_id}">{trigger}'
            f'<span class="help-tip" role="tooltip" id="{tip_id}">{body}</span></span>')
