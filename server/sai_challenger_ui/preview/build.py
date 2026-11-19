"""Assemble the static preview: one self-contained HTML file with a page per top-bar item.

    python3 -m sai_challenger_ui.preview [--runs N] [--out PATH]
"""
import argparse
from pathlib import Path

from .common import ROOT, STYLES, e, load
from .compare_view import compare_view
from .runs import run_view, runs_view
from .targets import targets_view, topbar
from .tests_view import tests_view

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500'
    '&family=IBM+Plex+Sans:wght@400;500;600&display=swap">'
)  # preview only: the app bundles the font files
EXTRA_CSS = ".group, .section { scroll-margin-top: 72px; }"

SCRIPT = r"""
(() => {
  const root = document.documentElement, themeBtn = document.getElementById('theme');
  function setTheme(t) {
    root.dataset.theme = t; themeBtn.textContent = t === 'dark' ? 'Light' : 'Dark';
    try { localStorage.setItem('sai-challenger-ui-theme', t); } catch (e) {}
  }
  let saved = null; try { saved = localStorage.getItem('sai-challenger-ui-theme'); } catch (e) {}
  setTheme(saved === 'light' ? 'light' : 'dark');
  themeBtn.addEventListener('click', () => setTheme(root.dataset.theme === 'dark' ? 'light' : 'dark'));

  const mark = (el, on) => on ? el.setAttribute('aria-current', 'page') : el.removeAttribute('aria-current');
  const views = [...document.querySelectorAll('[data-view]')];
  function route() {
    const [name = 'targets', id = '', part = ''] = (location.hash.slice(1) || 'targets').split('/');
    const want = name === 'run' ? 'run/' + id : name;
    const shown = views.find(v => v.dataset.view === want) || views.find(v => v.dataset.view === 'targets');
    views.forEach(v => { v.hidden = v !== shown; });
    const section = shown.dataset.view.startsWith('run/') ? 'runs' : shown.dataset.view;
    document.querySelectorAll('.nav a').forEach(a => mark(a, a.getAttribute('href') === '#' + section));
    if (section === 'compare') {
      const tab = ['matrix', 'diff', 'gaps'].includes(id) ? id : 'matrix';
      shown.querySelectorAll('[data-tab]').forEach(p => { p.hidden = p.dataset.tab !== tab; });
      shown.querySelectorAll('[data-tablink]').forEach(a => mark(a, a.dataset.tablink === tab));
    }
    const group = name === 'run' && part ? document.getElementById(`grp-${id}-${part}`) : null;
    if (group) group.scrollIntoView({ block: 'start' }); else window.scrollTo(0, 0);
    document.title = (shown.dataset.title || 'Targets') + ' · SAI Conformance';
  }
  addEventListener('hashchange', route);
  route();

  // Compare: only rows that differ / all rows
  const matrix = document.getElementById('matrix'), showAll = document.getElementById('show-all');
  const count = document.getElementById('diff-count');
  showAll?.addEventListener('click', () => {
    const only = matrix.classList.toggle('only-diff');
    showAll.textContent = only ? 'Show all rows' : 'Only rows that differ';
    count.textContent = only ? `Showing the ${count.dataset.differing} of ${count.dataset.total} rows that differ`
                             : `Showing all ${count.dataset.total} rows`;
  });

  const press = (group, btn) => group.forEach(b => b.setAttribute('aria-pressed', String(b === btn)));

  // Runs: filter by target and by "needs attention"
  const tChips = [...document.querySelectorAll('[data-filter-target]')];
  const attnChip = document.querySelector('[data-filter-attn]');
  let tFilter = '', attnOnly = false;
  function filterRuns() {
    document.querySelectorAll('#run-list .run-row').forEach(r => {
      r.hidden = (tFilter && r.dataset.target !== tFilter) || (attnOnly && r.dataset.attn !== '1');
    });
    document.querySelectorAll('#run-list .list').forEach(l => {
      const any = [...l.children].some(c => !c.hidden);
      l.hidden = !any; l.previousElementSibling.hidden = !any;
    });
  }
  tChips.forEach(b => b.addEventListener('click', () => { tFilter = b.dataset.filterTarget; press(tChips, b); filterRuns(); }));
  attnChip?.addEventListener('click', () => {
    attnOnly = !attnOnly; attnChip.setAttribute('aria-pressed', String(attnOnly)); filterRuns();
  });

  // Tests: search and track filter
  const search = document.getElementById('test-search'), tc = document.getElementById('test-count');
  const trChips = [...document.querySelectorAll('[data-filter-track]')];
  let trFilter = '';
  if (tc) tc.dataset.all = tc.textContent;
  function filterTests() {
    const q = (search.value || '').trim().toLowerCase();
    let n = 0;
    document.querySelectorAll('.track-group').forEach(g => {
      const trackOk = !trFilter || g.dataset.track === trFilter;
      let any = false;
      g.querySelectorAll('.test-row').forEach(r => {
        const ok = trackOk && (!q || r.dataset.text.includes(q));
        r.hidden = !ok; if (ok) { any = true; n++; }
      });
      g.querySelectorAll('.file-head').forEach(h => {
        let s = h.nextElementSibling, visible = false;
        while (s && !s.classList.contains('file-head')) { if (!s.hidden) visible = true; s = s.nextElementSibling; }
        h.hidden = !visible;
      });
      g.hidden = !any;
    });
    tc.textContent = (q || trFilter) ? `${n} matching tests` : tc.dataset.all;
  }
  search?.addEventListener('input', filterTests);
  trChips.forEach(b => b.addEventListener('click', () => { trFilter = b.dataset.filterTrack; press(trChips, b); filterTests(); }));

  // Copy buttons
  document.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', async () => {
    const label = b.textContent;
    try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = 'Copied'; }
    catch (err) { b.textContent = 'Copy needs http://127.0.0.1, not a file:// page'; }
    setTimeout(() => { b.textContent = label; }, 2000);
  }));
})();
"""


def page(ctx, newest):
    total = len(ctx.index.runs())
    rendered = list({r.id: r for r in newest + [r for r in ctx.latest.values() if r]}.values())  # Run isn't hashable
    latest_ids = {r.id for r in ctx.latest.values() if r}
    views = [
        ("targets", "Targets", targets_view(ctx)),
        ("runs", "Runs", runs_view(ctx, newest, total)),
        ("compare", "Compare", compare_view(ctx)),
        ("tests", "Tests", tests_view(ctx)),
    ]
    for run in rendered:
        label = f"Latest run on {run.target}" if run.id in latest_ids else f"Run on {run.target}"
        views.append((f"run/{run.id}", run.id, run_view(ctx, run, label)))
    body = "".join(f'<div data-view="{e(v)}" data-title="{e(t)}"{"" if v == "targets" else " hidden"}>{html}</div>'
                   for v, t, html in views)
    css = (STYLES / "tokens.css").read_text() + (STYLES / "look.css").read_text() + EXTRA_CSS
    return (f'<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>SAI Conformance</title>'
            f'{FONTS}<style>{css}</style></head><body>{topbar(ctx)}<main class="page">{body}</main>'
            f'<script>{SCRIPT}</script></body></html>')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=15, help="how many of the newest runs get a page (default 15)")
    ap.add_argument("--out", default=str(ROOT / "look" / "preview.html"))
    args = ap.parse_args(argv)
    ctx = load()
    newest = ctx.index.runs()[: args.runs]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(ctx, newest))
    print(f"wrote {out} ({out.stat().st_size // 1024} KB) · {len(newest)} newest runs plus the latest per target")
