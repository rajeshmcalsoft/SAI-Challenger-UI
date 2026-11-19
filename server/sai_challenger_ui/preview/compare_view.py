"""Compare (design §6.6): Matrix · Run diff · Gaps."""
from ..core import compare, profiles
from ..core.vocab import GLYPH, LABEL
from .common import R, dl, e, glyph, help_, p, tipped

BADGE_HELP = (
    p("New gap: fails, and the target's profile records no expected gap for it.")
    + p("Stale gap: recorded as an expected gap, but it passed. Remove the gap.")
    + p("Gap not applied: a gap is recorded but the test still reports Fail, e.g. a pattern that doesn't match.")
    + p("Changed in recent runs: different results in the last three runs on that target. It may be flaky, or the "
        "test or the target changed.")
)


def _cell(row, run):
    cell = row.cells[run.target]
    if cell.result is None:
        return '<td class="cell">' + glyph(None) + "</td>"
    pairs = [("Result", LABEL[cell.result])]
    if cell.message:
        pairs.append(("Message" if cell.result not in (R.EXPECTED_GAP, R.SKIPPED) else "Reason", cell.message[:300]))
    if cell.gap:
        pairs.append(("Gap pattern", cell.gap[0]))
    if row.recent.get(run.target):
        pairs.append(("Recent runs", " ".join(GLYPH[r] for r in row.recent[run.target]) + "  (newest first)"))
    pairs += [("Time", f"{cell.seconds:.1f}s"), ("Run", run.id)]
    sub = ""
    if cell.steps:
        bad = next((s for s in cell.steps if s[1] not in (R.PASS, R.EXPECTED_GAP, R.SKIPPED)), None)
        skipped = sum(1 for s in cell.steps if s[1] is R.SKIPPED)
        sub = f'<span class="sub">step {bad[0]}</span>' if bad else (f'<span class="sub">{skipped} skipped</span>' if skipped else "")
    return f'<td class="cell">{tipped(glyph(cell.result), dl(pairs))}{sub}</td>'


def matrix_panel(ctx, runs):
    m = compare.build_matrix(runs, ctx.profiles, ctx.cat, ctx.index)
    differing = len(m.differing)
    cols = "".join(
        f'<th class="col">{e(r.target)}<a class="run" href="#run/{e(r.id)}">{e(r.id.removeprefix(r.target + "-"))}</a></th>'
        for r in m.columns)
    badge_help = help_(BADGE_HELP, label="What the notes mean")
    head = f'<thead><tr><th>Test</th>{cols}<th style="text-align:right">Notes {badge_help}</th></tr></thead>'
    body = []
    groups = {}
    for row in m.rows:
        groups.setdefault((row.track, row.module), []).append(row)
    for (track, module), rows in groups.items():
        same_group = "" if any(r.differs for r in rows) else " same-group"
        body.append(f'<tr class="track{same_group}"><th colspan="{len(m.columns) + 2}">{e(track)}'
                    f'<span class="file">{e(module)}.py</span></th></tr>')
        for row in rows:
            badges = "".join(f'<span class="badge {kind}">{compare.BADGE_TEXT[kind]} · {e(target)}</span>'
                             for kind, target in row.badges)
            body.append(
                f'<tr class="{"diff" if row.differs else "same"}"><td><span class="t-title">{e(row.title)}</span>'
                f'<span class="t-id mono">{e(row.test_id)}</span></td>'
                f'{"".join(_cell(row, r) for r in m.columns)}<td><div class="badges">{badges}</div></td></tr>')
    attention = "".join(
        f'<span><b>{e(t)}</b> · {e(", ".join(items) if items else "nothing to act on")}</span>'
        for t, items in m.attention.items())
    legend = " ".join(f'{glyph(r)} {LABEL[r]}' for r in (R.PASS, R.FAIL, R.EXPECTED_GAP, R.GAP_PASSES, R.SKIPPED,
                                                       R.SETUP_ERROR)) + f' {glyph(None)} not in that run'
    return (f'<div class="banner"><div class="attention"><b>Needs attention</b>{attention}</div></div>'
            f'<div class="toolbar"><span class="muted" id="diff-count" data-differing="{differing}" '
            f'data-total="{len(m.rows)}">Showing the {differing} of {len(m.rows)} rows that differ</span>'
            f'<button class="btn sm" type="button" id="show-all">Show all rows</button>'
            f'<span class="spacer"></span><span class="small muted">{legend}</span></div>'
            f'<table class="matrix only-diff" id="matrix">{head}<tbody>{"".join(body)}</tbody></table>')


def diff_panel(ctx, runs):
    by_target = {r.target: r for r in runs}
    a, b = (by_target.get("saivs"), by_target.get("saivs-thrift"))
    if not (a and b):
        if len(runs) < 2:
            return '<p class="muted">Two runs are needed to compare.</p>'
        a, b = runs[0], runs[1]
    d = compare.run_diff(a, b)
    sections = []
    for title, pairs in d.sections.items():
        if not pairs:
            continue
        rows = "".join(
            f'<div class="trow" style="grid-template-columns:52px minmax(0,1fr) minmax(0,1.2fr)">'
            f'<span>{glyph(ta.result)} → {glyph(tb.result)}</span>'
            f'<span class="t-main"><span class="t-title">{e(ta.name)}</span></span>'
            f'<span class="muted small">{e((tb.message or ta.message).splitlines()[0][:140] if (tb.message or ta.message) else "")}</span></div>'
            for ta, tb in pairs)
        sections.append(f'<section class="group"><div class="group-head"><span class="title">{e(title)} '
                        f'<span class="count">{len(pairs)}</span></span></div><div class="list">{rows}</div></section>')
    diff_help = help_(
        p("The same tests in two runs, B against A. Runs on different targets can be compared.")
        + p("saivs against saivs-thrift is the saithrift validation (Track B): both run libsaivs, so any "
            "difference comes from the thrift path, not the library."), label="About the run diff", left=True)
    return (f'<div class="page-head" style="margin-bottom:var(--s-3)"><h2>{e(d.headline)} {diff_help}</h2></div>'
            f'<p class="muted">A <a class="mono" href="#run/{e(a.id)}">{e(a.id)}</a> · B '
            f'<a class="mono" href="#run/{e(b.id)}">{e(b.id)}</a> · {d.compared} tests in both · {d.only_a} only in A · '
            f'{d.only_b} only in B</p>{"".join(sections) or "<p class=muted>Same results.</p>"}')


def gaps_panel(ctx):
    register = compare.gap_register(ctx.profiles, ctx.latest, ctx.cat.all_names())
    rows, scope = [], []
    for g in register:
        if g.scope:
            targets = ", ".join(g.reasons)
            reason = "; ".join(r for r in g.reasons.values() if r)
            scope.append(f'<tr><td>{e(g.pattern)}</td><td>{e(targets)}</td><td class="muted">{e(reason)}</td></tr>')
            continue
        chips = "".join(
            f'<span class="badge">{e(t)} · {e(profiles.STATUS_TEXT.get(g.status.get(t, "not_run"), "Not run"))}</span>'
            for t in g.reasons)
        reasons = list(dict.fromkeys(g.reasons.values()))
        returned = ", ".join(dict.fromkeys(v for v in g.returned.values() if v)) or "-"
        flags = "".join(f'<div class="warn small">⚠ {e(f)}</div>' for f in g.flags)
        rows.append(f'<tr><td>{"<br>".join(e(r) for r in reasons)}{flags}</td><td><code>{e(g.pattern)}</code></td>'
                    f'<td><div class="badges" style="justify-content:flex-start">{chips}</div></td>'
                    f'<td class="mono small">{e(returned)}</td></tr>')
    table_md = compare.runbook_table(register)
    gaps_help = help_(
        p("Every expected gap in every profile, with its status in each target's latest run. It replaces "
          "gap_table.py and feeds the coverage report.")
        + p("Copy as RUNBOOK table gives the §9 columns: Gap, Target, Test, What the target does, Expected, Evidence."),
        label="About the gap register", left=True)
    scope_html = (f'<h2 style="margin-top:var(--s-7)">Not tested on these targets (out of scope)</h2>'
                  f'<table class="matrix"><thead><tr><th>Item</th><th>Targets</th><th>Reason</th></tr></thead>'
                  f'<tbody>{"".join(scope)}</tbody></table>') if scope else (
        '<p class="section-note" style="margin-top:var(--s-6)">No out-of-scope items are recorded in the profiles '
        '(scope_gaps).</p>')
    return (f'<div class="toolbar"><h2 style="margin:0">Expected gaps <span class="count muted">{len(rows)}</span> '
            f'{gaps_help}</h2><span class="spacer"></span>'
            f'<button class="btn sm" type="button" data-copy="{e(table_md)}">Copy as RUNBOOK table</button></div>'
            f'<table class="matrix"><thead><tr><th>Gap (profile reason)</th><th>Test or pattern</th><th>Targets</th>'
            f'<th>Status named</th></tr></thead><tbody>{"".join(rows)}</tbody></table>{scope_html}')


def compare_view(ctx):
    runs = [r for r in ctx.latest.values() if r]
    page_help = help_(
        p("Where do targets or runs disagree, and which gaps exist? The matrix is the UI form of summarize.py: "
          "each column is the newest run of a target that ran PoC tests, and a step scenario is one row.")
        + p("“Only rows that differ” is on by default, because disagreement is the question. Hover any cell for its "
            "result, reason and run."), label="About Compare", left=True)
    tabs = "".join(f'<a href="#compare/{k}" data-tablink="{k}">{v}</a>'
                   for k, v in (("matrix", "Matrix"), ("diff", "Run diff"), ("gaps", "Gaps")))
    return (f'<section class="section"><div class="page-head"><h1>Compare {page_help}</h1></div>'
            f'<nav class="tabs">{tabs}</nav>'
            f'<div data-tab="matrix">{matrix_panel(ctx, runs)}</div>'
            f'<div data-tab="diff" hidden>{diff_panel(ctx, runs)}</div>'
            f'<div data-tab="gaps" hidden>{gaps_panel(ctx)}</div></section>')

