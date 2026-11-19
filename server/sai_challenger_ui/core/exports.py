"""Two exports of one run, built from the same data the run page shows:
- agent_markdown: an agent-readable summary (Allure's Agent Mode, G7), for pasting into Claude Code or a review.
- report_html: a single self-contained HTML file in the light theme (Allure's single-file report, G1), for sending
  after review. Fonts are embedded when the web app's font files are found; otherwise system fonts are used.
"""
import base64
import html
import math
from datetime import datetime
from pathlib import Path

ORDER = ("fail", "setup_error", "cleanup_error", "gap_passes", "expected_gap", "skipped", "pass")
LABEL = {"pass": "Pass", "fail": "Fail", "setup_error": "Setup error", "cleanup_error": "Cleanup error",
         "gap_passes": "Gap now passes", "expected_gap": "Expected gap", "skipped": "Skipped"}
WORD = {"pass": "PASS", "fail": "FAIL", "setup_error": "SETUP ERROR", "cleanup_error": "CLEANUP ERROR",
        "gap_passes": "GAP NOW PASSES", "expected_gap": "EXPECTED GAP", "skipped": "SKIPPED"}
ATTENTION = ("fail", "setup_error", "cleanup_error", "gap_passes")
TRANSITION = {"new": "New", "fixed": "Fixed", "regressed": "Regressed", "new_error": "New error"}

# Light theme, the same values as the web app's tokens.css.
FILL = {"pass": "#3bc95d", "fail": "#f43f3b", "setup_error": "#ffd833", "cleanup_error": "#ffd833",
        "gap_passes": "#7c3aed", "expected_gap": "#54a8ed", "skipped": "#a5b7d1"}
TEXT = {"pass": "#15803d", "fail": "#dc2626", "setup_error": "#c2410c", "cleanup_error": "#c2410c",
        "gap_passes": "#6d28d9", "expected_gap": "#0d71b2", "skipped": "#64748b"}
ON = {"pass": "#0d121c", "fail": "#ffffff", "setup_error": "#0d121c", "cleanup_error": "#0d121c",
      "gap_passes": "#ffffff", "expected_gap": "#0d121c", "skipped": "#0d121c"}
GLYPH = {"pass": "✓", "fail": "✕", "setup_error": "!", "cleanup_error": "!", "gap_passes": "↑", "expected_gap": "◆",
         "skipped": "–"}

FONTS = Path(__file__).resolve().parents[3] / "web" / "src" / "fonts"
# Stacked marks, as in the web app: the order the palette validator passed for neighbouring colours.
STACK = ("pass", "expected_gap", "gap_passes", "setup_error", "cleanup_error", "fail", "skipped")


def tile_text(target):
    """'saivs' -> 'VS', 'saivpp' -> 'VPP', 'saivs-thrift' -> 'VST' (the web app's run tile)."""
    core = target.removeprefix("sai").replace("_", "-").split("-")
    return (core[0][:3] + (core[1][:1] if len(core) > 1 else "")).upper()


def _duration(seconds):
    s = round(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s // 3600}h {(s % 3600) // 60:02d}m"


def _when(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y, %H:%M UTC")
    except (TypeError, ValueError):
        return iso or ""


def pass_rate(counts):
    """(pass, ran): Pass over tests that ran (Skipped left out), as the donut shows it."""
    ran = sum(n for r, n in counts.items() if r != "skipped")
    return counts.get("pass", 0), ran


def _attention_tests(model):
    return [t for t in model["tests"] if t["result"] in ATTENTION and not t["upstream"]]


# ---------------------------------------------------------------------------------------------- Markdown


def agent_markdown(model, pages):
    m = model
    c = m["counts"]
    p, ran = pass_rate(c)
    lines = [f"# Run {m['id']} on {m['target']}", ""]
    lines.append(f"- **Result:** {m['headline']}")
    lines.append("- **Counts:** " + " · ".join(text for _, text in m["countParts"]))
    lines.append(f"- **Pass rate:** {p} of {ran} tests that ran ({(p / ran if ran else 0):.0%}); skipped tests left out")
    lines.append(f"- **Started:** {_when(m['started'])} · took {_duration(m['seconds'])} · {m['source']} run"
                 + (f" · testbed {m['testbed']}" if m.get("testbed") else ""))
    if m.get("job"):
        j = m["job"]
        lines.append(f"- **Command:** `{j['command']}`" + (f" · commit {j['commit']}" if j.get("commit") else ""))
    g = m["gate"]
    verdict = "passed" if g["passed"] else "failed ({} of {} rules)".format(g["failed"], g["total"])
    lines.append(f"- **Conformance gate:** {verdict}")
    for rule in g["rules"]:
        lines.append(f"  - {'PASS' if rule['passed'] else 'FAIL'} {rule['title']}: {rule['actual']} (wanted {rule['expected']})")
    mk = m["marks"]
    lines.append(f"- **Against earlier runs on {m['target']}:** {mk['regressed']} regressed · {mk['newError']} new error · "
                 f"{mk['fixed']} fixed · {mk['new']} new · {mk['flaky']} flaky")
    lines.append(f"- **Report file:** tests/poc/reports/{m['report']}")
    lines.append("")

    attention = _attention_tests(m)
    lines.append(f"## Needs attention ({len(attention)})")
    lines.append("")
    if not attention:
        lines.append("Nothing: no failures, errors or gaps that now pass.")
        lines.append("")
    for t in attention:
        page = pages.get(t["key"], {})
        lines.append(f"### {WORD[t['result']]}: {t['title']}")
        lines.append(f"- ID: `{t['key']}`")
        mark = t.get("mark") or {}
        notes = [TRANSITION[mark["transition"]]] if mark.get("transition") else []
        if mark.get("flaky"):
            notes.append("Flaky")
        if mark.get("ageRuns", 1) > 1:
            notes.append(f"same result for {mark['ageRuns']} runs in a row")
        if notes:
            lines.append(f"- Marks: {', '.join(notes)}")
        if page.get("purpose"):
            lines.append(f"- What it checks: {page['purpose'].splitlines()[0]}")
        if page.get("happened"):
            lines.append(f"- What happened: {page['happened']}")
        if page.get("diff"):
            lines.append(f"- Expected: `{page['diff']['expected']}` · actual: `{page['diff']['actual']}`")
        if page.get("hint"):
            lines.append(f"- Hint: {page['hint']['text']}")
        if page.get("location"):
            lines.append(f"- Where: {page['location']}")
        h = page.get("history")
        if h and h["counted"]:
            seq = " ".join(LABEL[r["result"]] for r in h["rows"][:10])
            lines.append(f"- History on {m['target']}: passed {h['passed']} of {h['counted']} (newest first: {seq})")
        others = [x for x in page.get("targets", []) if not x["current"] and x["result"]]
        if others:
            lines.append("- Other targets: " + ", ".join(f"{x['target']} {LABEL[x['result']]}" for x in others))
        if t["message"]:
            lines += ["- Message:", "", "```text", t["message"].strip()[:1500], "```"]
        lines.append("")

    if m["causes"]:
        lines.append("## Causes")
        lines.append("")
        for cause in m["causes"]:
            parts = ", ".join(f"{LABEL[r]} {n}" for r, n in cause["counts"].items())
            lines.append(f"- {cause['familyTitle']} · {cause['title']}: {parts}")
        lines.append("")

    gaps = [t for t in m["tests"] if t["result"] == "expected_gap"]
    if gaps:
        lines.append(f"## Expected gaps ({len(gaps)})")
        lines.append("")
        lines.append("| Test | Reason | Kind |")
        lines.append("|---|---|---|")
        for t in gaps:
            note = (t.get("gap") or {}).get("note") or {}
            kind = note.get("kindText", "Limitation") + (f" until {note['until']}" if note.get("until") else "")
            lines.append(f"| `{t['name']}` | {t['message'].replace('|', '/')} | {kind} |")
        lines.append("")

    skipped = {}
    for t in m["tests"]:
        if t["result"] == "skipped":
            skipped[t["message"] or "no reason given"] = skipped.get(t["message"] or "no reason given", 0) + 1
    if skipped:
        lines.append(f"## Skipped ({sum(skipped.values())}), by reason")
        lines.append("")
        lines += [f"- {n} · {reason}" for reason, n in sorted(skipped.items(), key=lambda kv: -kv[1])]
        lines.append("")
    lines.append("Results come from the JUnit report written by scripts/poc/run_poc.sh. Expected gaps are recorded "
                 "in tests/poc/targets/<target>.json as strict xfail.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------------------------- HTML


def _font_face():
    out = []
    for family, file in (("PT Root UI", "pt-root-ui_vf.woff2"), ("JetBrains Mono", "JetBrainsMono_vf.woff2")):
        path = FONTS / file
        if path.is_file():
            data = base64.b64encode(path.read_bytes()).decode()
            weight = "300 700" if family == "PT Root UI" else "100 800"
            out.append(f"@font-face{{font-family:'{family}';font-weight:{weight};font-display:swap;"
                       f"src:url(data:font/woff2;base64,{data}) format('woff2')}}")
    return "\n".join(out)


def donut_svg(counts, size=112, stroke=11):
    p, ran = pass_rate(counts)
    r = (size - stroke) / 2
    circ = 2 * math.pi * r
    total = sum(counts.get(x, 0) for x in ORDER)
    parts, offset = [], 0.0
    gap = 3 if sum(1 for x in ORDER if counts.get(x)) > 1 else 0
    for res in STACK:
        n = counts.get(res, 0)
        if not n or not total:
            continue
        length = circ * n / total
        dash = max(length - gap, 1)
        parts.append(f'<circle cx="{size / 2}" cy="{size / 2}" r="{r:.2f}" fill="none" stroke="{FILL[res]}" '
                     f'stroke-width="{stroke}" stroke-dasharray="{dash:.2f} {circ - dash:.2f}" '
                     f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {size / 2} {size / 2})"/>')
        offset += length
    pct = f"{(p / ran if ran else 0):.0%}"
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" '
            f'aria-label="{p} of {ran} tests that ran pass">{"".join(parts)}'
            f'<text x="50%" y="50%" text-anchor="middle" dominant-baseline="central" '
            f'style="font:700 20px var(--sans);fill:#0b1220">{pct}</text></svg>')


def _icon(res):
    return (f'<span class="ico" style="background:{FILL[res]};color:{ON[res]}" '
            f'aria-label="{LABEL[res]}">{GLYPH[res]}</span>')


def _trend_svg(dynamics, width=560, height=120):
    if len(dynamics) < 2:
        return ""
    top = max(sum(d["counts"].values()) for d in dynamics) or 1
    bw = width / len(dynamics)
    bars = []
    for i, d in enumerate(dynamics):
        y = height
        for res in ("pass", "expected_gap", "gap_passes", "skipped", "cleanup_error", "setup_error", "fail"):
            n = d["counts"].get(res, 0)
            if not n:
                continue
            h = (height - 4) * n / top
            y -= h
            bars.append(f'<rect x="{i * bw + bw * 0.2:.1f}" y="{y:.1f}" width="{bw * 0.6:.1f}" height="{h:.1f}" '
                        f'fill="{FILL[res]}"><title>{html.escape(d["runId"])}: {n} {LABEL[res].lower()}</title></rect>')
    return (f'<svg width="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="none" style="height:{height}px" '
            f'role="img" aria-label="Results of the last {len(dynamics)} runs">{"".join(bars)}</svg>')


CSS = """
:root{--sans:'PT Root UI',system-ui,-apple-system,'Segoe UI',sans-serif;--mono:'JetBrains Mono',ui-monospace,Menlo,Consolas,monospace;
--canvas:#f1f5f7;--card:#fff;--text:rgba(1,10,24,.83);--text2:rgba(1,18,40,.68);--text3:rgba(2,19,44,.6);
--line:rgba(29,79,129,.08);--line2:rgba(11,48,86,.16);--accent:#7e22ce}
*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--text);font:14px/1.5 var(--sans);-webkit-font-smoothing:antialiased}
.wrap{max-width:1040px;margin:0 auto;padding:32px 24px 48px}
.card{background:var(--card);border-radius:16px;box-shadow:0 2px 10px rgba(48,57,64,.08);padding:24px;margin-bottom:16px}
.head{display:flex;gap:16px;align-items:center}.tile{width:48px;height:48px;border-radius:12px;background:#f1f5f7;display:grid;place-items:center;font:700 15px var(--sans);color:var(--accent)}
h1{font-size:20px;margin:0}h2{font-size:16px;margin:0 0 12px}.sub{color:var(--text2)}.grow{flex:1}
.ticks{display:flex;gap:20px;flex-wrap:wrap;margin-top:16px;padding-top:16px;border-top:1px solid var(--line2)}
.tick{display:flex;flex-direction:column;gap:2px}.tick .k{font-size:12px;color:var(--text3)}.tick .v{display:flex;align-items:center;gap:6px;font-weight:700;font-size:16px}
.tick .bar{width:3px;height:14px;border-radius:2px}
table{width:100%;border-collapse:collapse}td,th{padding:8px 6px;border-top:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:12px;color:var(--text3);font-weight:600;border-top:0}.mono{font-family:var(--mono);font-size:12px;color:var(--text3)}
.ico{display:inline-grid;place-items:center;width:16px;height:16px;border-radius:50%;font:700 10px/1 var(--sans);vertical-align:-3px}
.pill{display:inline-flex;align-items:center;gap:6px;padding:2px 10px 2px 3px;border-radius:999px;font-size:13px;font-weight:600}
.err{background:rgba(255,100,100,.08);border-radius:8px;padding:12px 16px;margin:8px 0}.err b{color:#dc2626}
pre{font:12px/1.55 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere;margin:6px 0 0;color:var(--text2)}
.ok{color:#15803d;font-weight:600}.no{color:#dc2626;font-weight:600}.small{font-size:12px}.muted{color:var(--text2)}
.foot{color:var(--text3);font-size:12px;text-align:center;margin-top:24px}
pre,code,.mono{font-variant-ligatures:none;font-feature-settings:"liga" 0,"calt" 0}
"""


def report_html(model, pages, charts, version=""):
    m = model
    e = html.escape
    c = m["counts"]
    p, ran = pass_rate(c)
    gate = m["gate"]
    out = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
           "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
           f"<title>Conformance report: {e(m['target'])} · {e(m['id'])}</title>",
           f"<style>{_font_face()}{CSS}</style></head><body><div class=\"wrap\">"]
    status = next((r for r in ORDER if c.get(r) and r in ATTENTION), "pass")
    out.append('<div class="card"><div class="head">')
    out.append(f'<div class="tile">{e(tile_text(m["target"]))}</div><div class="grow">')
    out.append(f'<div class="mono">Conformance report · {e(m["id"])}</div><h1>{e(m["target"])}: {e(m["headline"])}</h1>')
    out.append(f'<div class="sub">{e(_when(m["started"]))} ({e(_duration(m["seconds"]))}) · {e(m["source"])} run'
               + (f' · testbed {e(m["testbed"])}' if m.get("testbed") else "") + "</div>")
    out.append(f'<div style="margin-top:8px"><span class="pill" style="background:{FILL[status]};color:{ON[status]}">'
               f'{_icon(status)} {e(LABEL[status] if status != "pass" else "Pass")}</span> '
               f'<span class="muted small">{p} of {ran} tests that ran pass</span></div></div>')
    out.append(donut_svg(c) + "</div>")
    out.append('<div class="ticks">' + f'<div class="tick"><span class="k">Total</span><span class="v">{sum(c.values())}</span></div>')
    for r in ("pass", "expected_gap", "gap_passes", "fail", "setup_error", "cleanup_error", "skipped"):
        if c.get(r):
            out.append(f'<div class="tick"><span class="k">{LABEL[r]}</span><span class="v">'
                       f'<span class="bar" style="background:{FILL[r]}"></span>{c[r]}</span></div>')
    out.append("</div></div>")

    out.append('<div class="card"><h2>Conformance gate: '
               + ('<span class="ok">passed</span>' if gate["passed"]
                  else f'<span class="no">failed ({gate["failed"]} of {gate["total"]} rules)</span>') + "</h2><table>")
    out.append("<tr><th></th><th>Rule</th><th>This run</th><th>Wanted</th></tr>")
    for rule in gate["rules"]:
        mark = _icon("pass") if rule["passed"] else _icon("fail")
        out.append(f"<tr><td>{mark}</td><td>{e(rule['title'])}</td><td>{e(rule['actual'])}</td>"
                   f"<td class=\"muted\">{e(rule['expected'])}</td></tr>")
    out.append("</table></div>")

    attention = _attention_tests(m)
    if attention:
        out.append(f'<div class="card"><h2>Needs attention ({len(attention)})</h2>')
        for t in attention:
            page = pages.get(t["key"], {})
            out.append(f'<div style="margin:14px 0">{_icon(t["result"])} <b>{e(t["title"])}</b> '
                       f'<span class="mono">{e(t["key"])}</span>')
            if page.get("purpose"):
                out.append(f'<div class="muted small" style="margin-top:4px">{e(page["purpose"].splitlines()[0])}</div>')
            out.append('<div class="err">' + (f'<b>{e(page["happened"])}</b>' if page.get("happened") else "<b>Error</b>"))
            if page.get("diff"):
                out.append(f'<div class="small">Expected <code>{e(page["diff"]["expected"])}</code>, '
                           f'actual <code>{e(page["diff"]["actual"])}</code></div>')
            out.append(f"<pre>{e(t['message'][:1500])}</pre></div>")
            if page.get("hint"):
                out.append(f'<div class="small">Hint: {e(page["hint"]["text"])}</div>')
            if page.get("location"):
                out.append(f'<div class="mono">{e(page["location"])}</div>')
            out.append("</div>")
        out.append("</div>")

    if m["causes"]:
        out.append('<div class="card"><h2>Causes</h2><table><tr><th>Family</th><th>Cause</th><th>Tests</th></tr>')
        for cause in m["causes"]:
            parts = " ".join(f'{_icon(r)} {n}' for r, n in cause["counts"].items())
            out.append(f"<tr><td class=\"muted\">{e(cause['familyTitle'])}</td><td>{e(cause['title'])}</td><td>{parts}</td></tr>")
        out.append("</table></div>")

    trend = _trend_svg(charts.get("dynamics", []))
    if trend:
        out.append(f'<div class="card"><h2>Last {len(charts["dynamics"])} runs on {e(m["target"])}</h2>{trend}</div>')

    out.append('<div class="card"><h2>All tests</h2><table><tr><th></th><th>Test</th><th>Track</th><th>Time</th>'
               "<th>Reason or message</th></tr>")
    rank = {r: i for i, r in enumerate(ORDER)}
    for t in sorted((t for t in m["tests"] if not t["upstream"]), key=lambda t: (rank[t["result"]], t.get("pos") or 0)):
        msg = (t["message"].splitlines() or [""])[0][:160] if t["result"] != "pass" else ""
        out.append(f"<tr><td>{_icon(t['result'])}</td><td>{e(t['title'])}<div class=\"mono\">{e(t['name'])}</div></td>"
                   f"<td class=\"muted\">{e(t['tag'])}</td><td class=\"mono\">{t['seconds']:.1f}s</td>"
                   f"<td class=\"muted small\">{e(msg)}</td></tr>")
    out.append("</table></div>")
    out.append(f'<div class="foot">Generated by SAI Conformance UI {e(version)} from tests/poc/reports/{e(m["report"])}. '
               "Draft: to be reviewed by the accountable owner before it is sent.</div>")
    out.append("</div></body></html>")
    return "".join(out)
