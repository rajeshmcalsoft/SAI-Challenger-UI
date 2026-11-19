"""Top bar and the Targets page (design §5, §6.1), plus the look-check legend."""
from ..core import testbed
from ..core.vocab import LABEL, MEANING
from .common import R, dl, e, glyph, help_, p, strip, when

STATE_DOT = {"ready": "●", "busy": "◐", "yours": "◐", "stopped": "○"}
FACT_SOURCE = {
    "profile": "from the profile",
    "ui": "from the UI's target_facts.toml; the profile has no key for it yet",
    "unknown": "not recorded anywhere",
}


def topbar(ctx):
    held = [n for n, prof in ctx.profiles.items() if testbed.lock_state(ctx.s.lock_dir, prof.lock).holder]
    activity = f'<span class="small muted">◷ {len(held)} running</span>' if held else ""
    nav = "".join(f'<a href="#{x.lower()}">{x}</a>' for x in ("Targets", "Runs", "Compare", "Tests"))
    return (f'<header class="topbar"><span class="brand">SAI Conformance</span><nav class="nav">{nav}</nav>'
            f'<span class="spacer"></span><div class="tools">{activity}<span class="kbd">⌘K</span>'
            f'<button class="btn sm" id="theme" type="button">Light</button></div></header>')


def _target_help(ctx, name, prof, cname, container, lock, fwd, source):
    if lock.holder:
        lock_text = f"{lock.path} · held by {lock.holder.who} (pid {lock.holder.pid})"
    else:
        lock_text = f"{lock.path} · {'free' if lock.exists else 'not created yet'}"
    if lock.waiting:
        lock_text += f" · {lock.waiting} waiting"
    scope = prof.scope_gaps
    gaps = f"{len(prof.expected_gaps)}" + (f" · {len(scope)} out of scope" if scope else "")
    forwards = {True: "yes", False: "no"}.get(fwd, "not known")
    return dl([
        ("Profile", f"tests/poc/targets/{name}.json"),
        ("Testbed", prof.testbed),
        ("Container", f"{cname} · {container['status'] if container else 'not found'}"),
        ("Lock", lock_text),
        ("Ports", ", ".join(map(str, prof.ports))),
        ("Traffic filters", ", ".join(prof.traffic_filters) or "none"),
        ("Expected gaps", gaps),
        ("Forwards packets", f"{forwards} ({FACT_SOURCE[source]})"),
        ("History", f"{len(ctx.index.runs(name))} runs in the reports folder"),
    ])


def targets_view(ctx):
    avail, total = testbed.memory()
    low = avail < 1.5 * 2**30
    mem_help = help_(
        p("Free memory on this VM (MemAvailable in /proc/meminfo). With all three containers up, the project "
          "measured a peak of 4.1 GB used. Below 1.5 GB free, starting another container may fail."),
        label="About the memory figure")
    mem = (f'<span class="chip-mem{" low" if low else ""}">VM: {avail / 2**30:.1f} of {total / 2**30:.1f} GB free'
           f'{" · Low memory: starting another container may fail" if low else ""}</span> {mem_help}')
    page_help = help_(
        p("One row per target profile in tests/poc/targets. The pill merges container, lock and run state into "
          "the one that matters most: Container stopped, Busy (with who and since when), or Ready.")
        + p("The result is the newest run that ran PoC tests; click it to open the run. The strip has one cell per "
            "test in suite order, with a gap between tracks. The ? in each row's corner has the target's details."),
        label="About the Targets page", left=True)
    rows = []
    if ctx.docker_error:
        rows.append(f'<div class="add-row">Can\'t reach Docker. Is your user in the docker group? '
                    f'<code>docker ps</code> said: {e(ctx.docker_error)}</div>')
    for name, prof in ctx.profiles.items():
        cname = testbed.container_name(prof.exec_args, ctx.s.sc_root)
        container = ctx.containers.get(cname)
        lock = testbed.lock_state(ctx.s.lock_dir, prof.lock)
        state = testbed.target_state(container, lock, ctx.docker_error)
        fwd, source = ctx.s.forwards_traffic(prof)
        kind = "Reference · " + {True: "forwards packets · L1 + L2", False: "no dataplane · L1 only"}.get(
            fwd, "dataplane not known")
        run = ctx.latest.get(name)
        if run:
            result = (f'<div class="line"><a class="headline" href="#run/{e(run.id)}">{e(run.headline)}</a>'
                      f'<span class="when">{when(run.started)}</span></div><div>{strip(ctx, run.tests)}</div>')
        else:
            result = '<div class="muted">Never run</div>'
        warn = (f'<div class="warn">⚠ {e(", ".join(prof.duplicates))} is listed twice in {name}.json</div>'
                if prof.duplicates else "")
        button = "Queue" if state.kind in ("busy", "yours") else ("Run full suite" if not run else "Run")
        disabled = " disabled" if state.kind in ("stopped", "unknown") else ""
        corner = help_(_target_help(ctx, name, prof, cname, container, lock, fwd, source),
                       label=f"Details of {name}", corner=True, title=name)
        rows.append(
            f'<div class="target has-help">{corner}<div class="who">'
            f'<div class="name-line"><span class="name">{e(name)}</span>'
            f'<span class="pill {state.kind}">{STATE_DOT.get(state.kind, "?")} {e(state.text)}</span></div>'
            f'<div class="kind">{e(kind)}</div>'
            f'<div class="identity mono">{e(prof.testbed)} · {e(cname)}</div>{warn}</div>'
            f'<div class="result">{result}</div>'
            f'<div class="actions"><button class="btn"{disabled} type="button">{button}</button>'
            f'<button class="btn icon" type="button" aria-label="More actions for {e(name)}">⋯</button></div></div>'
        )
    rows.append('<div class="add-row">+ <b>Add libSAI</b>: upload a libsai.so and test it against the SAI spec</div>')
    return (f'<section class="section"><div class="page-head"><h1>Targets {page_help}</h1><span>{mem}</span></div>'
            f'<div class="list">{"".join(rows)}</div></section>{legend()}')


def legend():
    items = []
    for r in (R.PASS, R.FAIL, R.EXPECTED_GAP, R.GAP_PASSES, R.SKIPPED, R.SETUP_ERROR):
        label = "Setup / Cleanup error" if r is R.SETUP_ERROR else LABEL[r]
        items.append(f'<div class="item"><div class="top">{glyph(r)}<b>{label}</b><span class="spacer"></span>'
                     f'<span class="strip"><span class="cells"><span class="cell {r.value}"></span></span></span></div>'
                     f'<div class="small muted">{e(MEANING[r])}</div></div>')
    return (f'<section class="section"><h2>Look check (CP5)</h2><p class="section-note">The six results, their glyphs '
            f'and colours. Shape carries the meaning as well as colour, so the page still reads in greyscale. Errors '
            f'are white (near-black in the light theme): an error is not a verdict on the target.</p>'
            f'<div class="legend">{"".join(items)}</div></section>')
