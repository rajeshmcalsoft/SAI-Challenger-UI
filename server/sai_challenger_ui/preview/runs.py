"""Runs history (design §6.5) and the Run page (§6.4), rendered from core.runview."""
from ..core import catalog, reports, runview
from ..core.vocab import GLYPH, LABEL, count_parts, plural
from .common import ATTENTION, RESULT_HELP, TAG, R, dl, duration, e, glyph, help_, p, strip, title_of, track_of, when

GROUP_TITLE = {
    R.FAIL: "Fail", R.SETUP_ERROR: "Setup errors", R.CLEANUP_ERROR: "Cleanup errors",
    R.GAP_PASSES: "Gap now passes", R.EXPECTED_GAP: "Expected gaps", R.SKIPPED: "Skipped", R.PASS: "Pass",
}
GROUP_NOTE = {
    R.SETUP_ERROR: "Not a pass or fail of the target",
    R.CLEANUP_ERROR: "The next run may fail with “already exists”",
    R.GAP_PASSES: "The target now passes these: remove the gaps",
    R.EXPECTED_GAP: "Each row shows its reason",
    R.SKIPPED: "Grouped by reason",
}


# ---------------------------------------------------------------- runs history

def describe(ctx, run):
    """'L2 + L3 + ACL · 69 tests', 'Upstream: test_l2_basic · 12 tests'."""
    poc = [t for t in run.tests if not t.upstream]
    upstream = [t for t in run.tests if t.upstream]
    parts = []
    if poc:
        tracks = {track_of(ctx, t) for t in poc}
        order = {tr: i for i, tr in enumerate(catalog.TRACK_ORDER)}
        tags = [TAG.get(tr, "?") for tr in sorted(tracks, key=lambda tr: order.get(tr, 99))]
        parts.append(" + ".join(tags) + f" · {plural(len(poc), 'test', 'tests')}")
    if upstream:
        mods = list(dict.fromkeys(t.module.rsplit("/", 1)[-1] for t in upstream))
        more = f" +{len(mods) - 2}" if len(mods) > 2 else ""
        parts.append(f"Upstream: {', '.join(mods[:2])}{more} · {plural(len(upstream), 'test', 'tests')}")
    return " · ".join(parts) or "no tests"


def runs_view(ctx, runs, total):
    targets = sorted({r.target for r in runs})
    chips = ['<button class="chip" type="button" data-filter-target="" aria-pressed="true">All targets</button>']
    chips += [f'<button class="chip" type="button" data-filter-target="{e(t)}" aria-pressed="false">{e(t)}</button>'
              for t in targets]
    chips.append('<button class="chip" type="button" data-filter-attn aria-pressed="false">Needs attention</button>')
    page_help = help_(
        p("Every run_poc.sh run is a run here: the UI reads each <target>-<stamp>.xml in tests/poc/reports, so "
          "CLI runs appear without any import step. Nothing here is ever deleted: reports are evidence.")
        + p("Select two runs in the app to compare them; this preview links each run to its page."),
        label="About the Runs page", left=True)
    body, day = [], None
    for run in runs:
        d = run.started.astimezone().strftime("%A %d %B")
        if d != day:
            if day is not None:
                body.append("</div>")
            body.append(f'<div class="day">{e(d)}</div><div class="list">')
            day = d
        attn = any(run.counts()[r] for r in ATTENTION)
        body.append(
            f'<a class="run-row" href="#run/{e(run.id)}" data-target="{e(run.target)}" data-attn="{int(attn)}">'
            f'<span class="time">{run.started.astimezone().strftime("%H:%M")}</span>'
            f'<span class="target">{e(run.target)}</span><span class="what">{e(describe(ctx, run))}</span>'
            f'<span class="res"><span>{e(run.headline)}</span>{strip(ctx, run.tests)}</span>'
            f'<span class="src">{e(run.source)}</span><span class="dur">{duration(run.seconds)}</span></a>'
        )
    if day is not None:
        body.append("</div>")
    note = (f'<p class="section-note" style="margin-top:var(--s-5)">Showing the {len(runs)} newest of {total} runs. '
            f'The app lists them all.</p>')
    return (f'<section class="section"><div class="page-head"><h1>Runs {page_help}</h1></div>'
            f'<div class="toolbar">{"".join(chips)}</div><div id="run-list">{"".join(body)}</div>{note}</section>')


# ---------------------------------------------------------------- run page

def _row_action(t):
    act = ""
    if t.result is R.FAIL:
        act = '<button class="btn sm" type="button">Add expected gap</button>'
    elif t.result is R.GAP_PASSES:
        act = '<button class="btn sm" type="button">Remove gap</button>'
    elif t.result is R.EXPECTED_GAP:
        act = f'<span class="reason" title="{e(t.message)}">{e(t.message)}</span>'
    if t.cleanup_failed and t.result is not R.CLEANUP_ERROR:
        act = '<span class="warn small">Cleanup failed</span> ' + act
    return act


def row(ctx, run, t, prof):
    track = track_of(ctx, t)
    open_ = t.result in ATTENTION and not ctx.opened
    if open_:
        ctx.opened.add(t.key)
    summary = (f'<summary class="trow">{glyph(t.result)}'
               f'<span class="t-main"><span class="t-title">{e(title_of(t))}</span>'
               f'<span class="t-id mono">{e(t.name)}</span></span>'
               f'<span class="t-track">{TAG.get(track, track)}</span><span class="t-dur">{t.seconds:.1f}s</span>'
               f'<span class="t-act">{_row_action(t)}</span></summary>')
    d = runview.detail(run, t, ctx.cat, prof, ctx.hints, ctx.s.poc_dir)
    parts = [("What it checks", e(d.purpose) if d.purpose else '<span class="faint">No description in the test</span>')]
    if d.happened:
        parts.append(("What happened", e(d.happened)))
    if t.result is R.EXPECTED_GAP:
        if d.recorded:
            recorded = f'{e(d.recorded[1])}<br><span class="faint small">Pattern </span><code>{e(d.recorded[0])}</code>'
            parts.append(("Recorded as", recorded))
        else:
            warning = (f'{e(t.message)}<br><span class="warn small">⚠ Not in the current {e(run.target)}.json: '
                       f'xfail was called inside the test. Gaps belong in the profile.</span>')
            parts.append(("Recorded as", warning))
    if d.hint:
        button = f'<button class="btn sm" type="button">{e(d.hint.action)}</button>' if d.hint.action else ""
        parts.append(("Hint", f'<div class="hint"><span>{e(d.hint.text)}</span>{button}</div>'))
    if d.location and d.source:
        src = "\n".join(f'<span class="hl">{e(f"{n:>4}  {text}")}</span>' if hl else e(f"{n:>4}  {text}")
                        for n, text, hl in d.source)
        where = f'<code>{e(d.location)}</code> <span class="faint small">· source as it is now</span><pre>{src}</pre>'
        parts.append(("Where", where))
    elif d.location:
        parts.append(("Where", f'<code>{e(d.location)}</code>'))
    if d.raw:
        parts.append(("Raw detail", f'<details><summary>Show the text pytest wrote</summary><pre>{e(d.raw)}</pre></details>'))
    body = "".join(f'<div class="k">{k}</div><div class="v">{v}</div>' for k, v in parts)
    return f'<details{" open" if open_ else ""}>{summary}<div class="detail">{body}</div></details>'


def scenario_row(entry):
    sc, steps, result = entry.scenario, entry.steps, entry.result
    chips = "".join(
        f'<span class="s {t.result.value}" title="{e(LABEL[t.result])}: {e(catalog.readable(t.name))}">'
        f'{catalog.step_number(t.name) or "?"} {GLYPH[t.result]}</span>'
        for t in steps
    )
    summary = (f'<summary class="trow">{glyph(result)}'
               f'<span class="t-main"><span class="t-title">{e(sc.title)} <span class="faint">· {len(steps)} steps</span></span>'
               f'<span class="t-sub"><span class="steps">{chips}</span>'
               f'<span class="sentence">{e(entry.text)}</span></span></span>'
               f'<span class="t-track">{TAG.get(sc.steps[0].track, "")}</span>'
               f'<span class="t-dur">{sum(t.seconds for t in steps):.1f}s</span><span class="t-act"></span></summary>')

    def step_line(t):
        why = f'<br><span class="muted small">{e(t.message.splitlines()[0][:140])}</span>' if t.message and t.result is not R.PASS else ""
        return (f'<span class="mono small">{glyph(t.result)} {catalog.step_number(t.name) or ""}</span>'
                f'<span>{e(catalog.readable(t.name).split(": ", 1)[-1])}{why}</span>')

    lines = "".join(step_line(t) for t in steps)
    return f'<details>{summary}<div class="detail" style="display:block"><div class="step-list">{lines}</div></div></details>'


def _entry(ctx, run, entry, prof):
    if entry.kind == "note":
        return f'<div class="note">{e(entry.text)}</div>'
    if entry.kind == "subhead":
        return f'<div class="subhead">{e(entry.text)}</div>'
    if entry.kind == "scenario":
        return scenario_row(entry)
    return row(ctx, run, entry.test, prof)


def _run_head(ctx, run, prof):
    links = '<span class="sepdot">·</span>'.join(
        f'<a href="#run/{e(run.id)}/{r.value}">{e(text)}</a>' for r, text in count_parts(run.counts()))
    items = [f"<span><b>{e(run.target)}</b> · {e(prof.testbed) if prof else ''}</span>",
             f"<span>Started {when(run.started)}</span>", f"<span>Took {duration(run.seconds)}</span>", "<span>CLI run</span>"]
    html_report = f' Full output: pytest HTML <code>{e(run.html.name)}</code>.' if run.html else ""
    strip_help = help_(
        p("One cell per test, in the order the suite ran them. A gap separates tracks, and the letter under each "
          "block names it: A L2 & VLANs, B L3 routing, C ACL and counters, F framework. Hover a cell for its test.")
        + p("Colour and fill: green pass, red fail, amber expected gap, violet gap now passes, white error, hollow "
            "skipped."), label="How to read the strip", left=True)
    return (f'<div class="run-head"><div class="headline">{e(run.headline)}</div>'
            f'<div class="actions"><button class="btn sm" type="button">Rerun ▾</button>'
            f'<button class="btn sm" type="button">Compare…</button><button class="btn sm" type="button">Export ▾</button></div>'
            f'<div class="counts">{links}</div>'
            f'<div class="strip-wrap">{strip(ctx, run.tests, letters=True)} {strip_help}</div>'
            f'<div class="meta"><div class="items">{"".join(items)}</div>'
            f'<div class="faint">Commit, command and log aren\'t recorded for CLI runs.{html_report}</div></div></div>')


def run_view(ctx, run, label):
    ctx.opened = set()
    prof = ctx.profiles.get(run.target)
    prev = ctx.index.previous(run)
    since = ""
    if prev:
        diff = reports.since(prev, run)
        if diff.new_failures or diff.fixed:  # hidden when nothing changed (design §6.2)
            since = (f'<p class="since">Since previous run on {e(run.target)} ({when(prev.started)}): '
                     f'<a href="#run/{e(prev.id)}">{e(diff.text)}</a></p>')
    poc = sum(1 for t in run.tests if not t.upstream)
    run_help = help_(dl([
        ("Report", run.xml.name),
        ("Started", run.started.isoformat(timespec="seconds")),
        ("Container", run.hostname or "not recorded"),
        ("Tests", f"{poc} PoC · {len(run.tests) - poc} upstream"),
        ("Compared with", prev.id if prev else "nothing earlier on this target"),
    ]) + p("The headline lists what needs attention first: failures, then errors, then gaps that now pass. Each "
           "count below it jumps to its group."), label="About this run", left=True)
    fwd = ctx.s.forwards_traffic(prof)[0] if prof else None
    groups = []
    for g in runview.build_groups(run, ctx.cat, ctx.hints, fwd, GROUP_TITLE):
        block = f'<div class="list">{"".join(_entry(ctx, run, x, prof) for x in g.entries)}</div>'
        if g.result is R.PASS:
            block = f'<details><summary class="show-more">Show {g.count} passing tests</summary>{block}</details>'
        act = ""
        if g.result in (R.FAIL, R.SETUP_ERROR, R.CLEANUP_ERROR):
            act = '<button class="btn sm act" type="button">Rerun these</button>'
        elif g.result is R.GAP_PASSES:
            act = f'<button class="btn sm act" type="button">Remove all {g.count} gaps</button>'
        note = f'<span class="meaning">{GROUP_NOTE[g.result]}</span>' if g.result in GROUP_NOTE else ""
        group_help = help_(p(RESULT_HELP[g.result]), label=f"About {GROUP_TITLE[g.result]}", left=True)
        groups.append(f'<section class="group" id="grp-{e(run.id)}-{g.result.value}"><div class="group-head">'
                      f'<span class="title">{GROUP_TITLE[g.result]} <span class="count">{g.count}</span></span>{group_help}'
                      f'{note}{act}</div>{block}</section>')
    return (f'<section class="section"><div class="eyebrow">{e(label)} · <span class="mono">{e(run.id)}</span> '
            f'{run_help}</div>{_run_head(ctx, run, prof)}{since}{"".join(groups)}</section>')
