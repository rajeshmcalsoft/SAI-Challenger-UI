"""Tests: the catalogue and, inline, each test's page (design §6.7)."""
from ..core import catalog, profiles
from ..core.compare import worst
from ..core.vocab import LABEL
from .common import TAG, dl, e, glyph, help_, mini_strip, p, tipped


def _needs(ctx, t):
    parts = []
    if t.ports_needed:
        parts.append(f"{t.ports_needed} port" + ("" if t.ports_needed == 1 else "s"))
    if t.level == "L2 traffic":
        parts.append("traffic")
    if t.variants:
        parts.append(f"×{len(t.variants)} variants")
    sc = ctx.cat.scenario_of(t)
    if sc:
        parts.append(f"step {catalog.step_number(t.name) or ''} of a scenario".replace("  ", " "))
    return " · ".join(parts) or "-"


def _result_cell(ctx, t, target, run):
    if run is None:
        return f'<span class="c-res">{glyph(None)}</span>'
    tests = ctx.lookup.results(run).get((t.module, t.cls, t.name), [])
    if not tests:
        return f'<span class="c-res">{tipped(glyph(None), dl([("Run", run.id), ("Result", "not in that run")]))}</span>'
    result = worst(x.result for x in tests)  # a parametrised test shows its worst variant
    pairs = [("Run", run.id)]
    for x in tests:
        label = f"[{x.param}]" if x.param else "Result"
        pairs.append((label, LABEL[x.result] + (f": {x.message.splitlines()[0][:120]}" if x.message else "")))
    return f'<span class="c-res">{tipped(glyph(result), dl(pairs))}</span>'


def _detail(ctx, t, targets):
    hist = []
    for target in targets:
        h = ctx.lookup.history(ctx.index, target, (t.module, t.cls, t.name))
        gaps = ctx.profiles[target].expected_gaps if target in ctx.profiles else {}
        recorded = next((profiles.gap_for(n, gaps) for n in t.names if profiles.gap_for(n, gaps)), None)
        gap = f' <span class="muted small">· gap: {e(recorded[1])}</span>' if recorded else ""
        hist.append(f'<span class="muted">{e(target)}</span><span>{mini_strip(h) if h else "<span class=faint>never run</span>"}'
                    f' <span class="faint small">{len(h)} runs</span>{gap}</span>')
    purpose = e(t.purpose) if t.purpose else '<span class="faint">No description in the test</span>'
    rows = [("What it checks", purpose), ("Where", f"<code>{e(t.module)}.py:{t.line}</code>"),
            ("Markers", e(", ".join(t.markers) or "none")),
            ("Results by target", f'<div class="history">{"".join(hist)}</div>')]
    if t.variants:
        rows.insert(2, ("Variants", " · ".join(f"<code>{e(v)}</code>" for v in t.variants)))
    return '<div class="detail">' + "".join(f'<div class="k">{k}</div><div class="v">{v}</div>' for k, v in rows) + "</div>"


def tests_view(ctx):
    targets = [name for name, run in ctx.latest.items() if run]
    head_cols = "".join(f'<span class="c-res">{e(t)}</span>' for t in targets)
    page_help = help_(
        p("The suite as read from tests/poc/test_*.py: nothing is run or collected, so no lock is taken.")
        + p("Level: L1 checks the control plane only; L2 traffic sends packets and needs --traffic on a target that "
            "forwards them. Kind: a negative test checks that bad input is refused.")
        + p("The last columns are each target's latest result; a parametrised test shows its worst variant. Open a "
            "row for its history on every target."), label="About Tests", left=True)
    chips = ['<button class="chip" type="button" data-filter-track="" aria-pressed="true">All tracks</button>']
    present = list(dict.fromkeys(t.track for t in ctx.cat.tests))
    ordered = [t for t in catalog.TRACK_ORDER if t in present]
    chips += [f'<button class="chip" type="button" data-filter-track="{e(tr)}" aria-pressed="false">{e(tr)}</button>'
              for tr in ordered]
    sections = []
    for track in ordered:
        tests = [t for t in ctx.cat.tests if t.track == track]
        body, module = [], None
        for t in tests:
            if t.module != module:
                body.append(f'<div class="file-head">{e(t.module)}.py</div>')
                module = t.module
            text = f"{t.title} {t.name} {t.module}".lower()
            cells = "".join(_result_cell(ctx, t, target, ctx.latest[target]) for target in targets)
            summary = (f'<summary class="crow" style="--cols:{len(targets)}"><span class="t-main">'
                       f'<span class="t-title">{e(t.title)}</span><span class="t-id mono">{e(t.name)}</span></span>'
                       f'<span class="c-meta">{e(t.level)}</span><span class="c-meta">{e(t.kind)}</span>'
                       f'<span class="c-meta">{e(_needs(ctx, t))}</span>{cells}</summary>')
            body.append(f'<details class="test-row" data-text="{e(text)}">{summary}{_detail(ctx, t, targets)}</details>')
        header = (f'<div class="crow head" style="--cols:{len(targets)}"><span>Test</span><span>Level</span>'
                  f'<span>Kind</span><span>Needs</span>{head_cols}</div>')
        sections.append(f'<section class="group track-group" data-track="{e(track)}"><div class="group-head">'
                        f'<span class="title">{e(track)} <span class="count">{len(tests)}</span></span>'
                        f'<span class="meaning">{TAG.get(track, "")} tests</span></div>'
                        f'<div class="list">{header}{"".join(body)}</div></section>')
    total = len(ctx.cat.tests)
    names = len(ctx.cat.all_names())
    return (f'<section class="section"><div class="page-head"><h1>Tests {page_help}</h1>'
            f'<span style="display:flex;gap:var(--s-2)"><button class="btn sm" type="button">Test data</button>'
            f'<button class="btn sm" type="button">New test</button></span></div>'
            f'<div class="toolbar"><input class="search" id="test-search" type="search" placeholder="Find a test by name or ID" '
            f'aria-label="Find a test">{"".join(chips)}<span class="spacer"></span>'
            f'<span class="small muted" id="test-count">{total} tests · {names} with variants</span></div>'
            f'{"".join(sections)}</section>')
