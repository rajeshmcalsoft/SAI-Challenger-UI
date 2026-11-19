"""Core objects to JSON-ready dicts. Results go out as their stable codes (pass, fail, expected_gap, ...)."""
from datetime import datetime
from pathlib import Path

from ..core import (
    catalog,
    causes,
    compare,
    console,
    explain,
    gapnotes,
    gates,
    history,
    jobs,
    profiles,
    reports,
    runview,
    testbed,
)
from ..core.vocab import Result, count_parts


def iso(dt):
    return dt.isoformat(timespec="seconds") if dt else None


def counts(c):
    return {r.value: n for r, n in c.items()}


def strip(cat, tests):
    out, last = [], None
    for t in tests:
        track = runview.track_of(cat, t)
        out.append({"r": t.result.value, "sep": last is not None and track != last,
                    "letter": catalog.TRACK_LETTER.get(track, "?") if track != last else "",
                    "title": catalog.readable(t.name) + (f" · {t.param}" if t.param else "")})
        last = track
    return out


def run_summary(state, run, with_strip=True):
    cat = state.catalogue()
    c = run.counts()
    out = {
        "id": run.id, "target": run.target, "started": iso(run.started), "seconds": round(run.seconds, 3),
        "source": run.source, "headline": run.headline, "counts": counts(c),
        "countParts": [[r.value, text] for r, text in count_parts(c)],
        "attention": any(c[r] for r in runview.ATTENTION), "what": runview.describe(cat, run),
        "upstreamOnly": run.upstream_only,
    }
    if with_strip:
        out["strip"] = strip(cat, run.tests)
    return out


class Ctx:
    """What a test row needs beyond the result itself: marks from history, run order, gap notes."""

    def __init__(self, cat, run=None, marks=None, profile=None, notes=None):
        self.marks = marks or {}
        self.pos = {t.key: i + 1 for i, t in enumerate(run.tests)} if run else {}
        self.target = run.target if run else ""
        self.gaps = profile.expected_gaps if profile else {}
        self.notes = notes or {}
        self.scenario = {(st.module, st.cls, st.name): sc for sc in cat.scenarios for st in sc.steps}


def mark_dict(m):
    if m is None:
        return None
    return {"transition": m.transition, "flaky": m.flaky, "ageRuns": m.age_runs, "ageSince": m.age_since,
            "previous": m.previous.value if m.previous else None}


def gap_dict(ctx, name):
    g = profiles.gap_for(name, ctx.gaps)
    if not g:
        return None
    return {"pattern": g[0], "reason": g[1], "note": gapnotes.as_dict(gapnotes.get(ctx.notes, ctx.target, g[0]))}


def test_row(cat, t, ctx=None):
    track = runview.track_of(cat, t)
    title = f"Collection failed: {t.module}.py" if t.name == "(collection)" else (
        catalog.readable(t.name) + (f" · {t.param}" if t.param else ""))
    row = {
        "key": t.key, "module": t.module, "cls": t.cls, "name": t.name, "title": title, "result": t.result.value,
        "seconds": round(t.seconds, 3), "message": t.message[:500], "track": track,
        "tag": catalog.TRACK_TAG.get(track, track), "cleanupFailed": t.cleanup_failed, "upstream": t.upstream,
    }
    if ctx is not None:
        sc = ctx.scenario.get((t.module, t.cls, t.base))
        row.update(pos=ctx.pos.get(t.key), scenario=sc.title if sc else None,
                   step=catalog.step_number(t.name) if sc else None, mark=mark_dict(ctx.marks.get(t.key)),
                   gap=gap_dict(ctx, t.name) if t.result in (Result.EXPECTED_GAP, Result.GAP_PASSES) and not t.upstream
                   else None)
    return row


def marks_summary(marks):
    out = {"new": 0, "fixed": 0, "regressed": 0, "newError": 0, "flaky": 0}
    for m in marks.values():
        if m.transition == "new_error":
            out["newError"] += 1
        elif m.transition:
            out[m.transition] += 1
        if m.flaky:
            out["flaky"] += 1
    return out


def gate_dict(verdict, note=""):
    return {
        "passed": verdict.passed, "failed": len(verdict.failed), "total": len(verdict.rules), "note": note,
        "rules": [{"id": r.id, "title": r.title, "passed": r.passed, "actual": r.actual, "expected": r.expected,
                   "keys": r.keys[:200], "more": max(0, len(r.keys) - 200)} for r in verdict.rules],
    }


def gate_of(state, run, cat=None, prof=None):
    rules, note = state.gate_rules()
    return gate_dict(gates.check(run, cat or state.catalogue(), prof or state.profiles().get(run.target), rules), note)


def causes_list(state, run):
    return [{"id": c.id, "title": c.title, "family": c.family, "familyTitle": causes.FAMILY_TITLE[c.family],
             "kind": c.kind, "keys": c.keys, "counts": {r.value: n for r, n in c.counts.items()}}
            for c in causes.build(run, state.hints)]


def retries_of(state, run):
    """The attempts of a run started with "Retry failures" (G5): this run and its retries, in order."""
    runner = state.runner
    job = runner.by_run(run.id) if runner else None
    if job is None:
        return None
    root = job.retry_of or job.id
    chain = sorted((j for j in runner.jobs.values() if (j.retry_of or j.id) == root), key=lambda j: j.attempt)
    if len(chain) < 2 and not job.retry:
        return None
    attempts, tests = [], {}
    for j in chain:
        r = state.run(j.run_id) if j.run_id and j.state == "done" else None
        attempts.append({"attempt": j.attempt, "jobId": j.id, "runId": r.id if r else None, "state": j.state,
                         "current": j.id == job.id})
        if r is not None:
            for t in r.tests:
                if not t.upstream:
                    tests.setdefault(t.key, []).append({"attempt": j.attempt, "runId": r.id, "result": t.result.value})
    retried = {k: v for k, v in tests.items() if len(v) > 1}
    return {"attempt": job.attempt, "allowed": job.retry, "attempts": attempts, "tests": retried}


def run_full(state, run):
    cat = state.catalogue()
    prof = state.profiles().get(run.target)
    fwd = state.s.forwards_traffic(prof)[0] if prof else None
    prev = state.index.previous(run)
    since = None
    if prev:
        d = reports.since(prev, run)
        since = {"previous": prev.id, "previousStarted": iso(prev.started), "text": d.text,
                 "newFailures": d.new_failures, "fixed": d.fixed, "changed": bool(d.new_failures or d.fixed)}
    poc = sum(1 for t in run.tests if not t.upstream)
    job = state.runner.by_run(run.id) if state.runner else None
    marks = history.marks(state.index, state.results, run)
    ctx = Ctx(cat, run, marks, prof, state.gap_notes())
    return dict(run_summary(state, run), testbed=prof.testbed if prof else None, hostname=run.hostname,
                report=run.xml.name, html=run.html.name if run.html else None, pocTests=poc,
                upstreamTests=len(run.tests) - poc, since=since, groups=groups(state, run, cat, fwd, ctx),
                tests=[test_row(cat, t, ctx) for t in run.tests], marks=marks_summary(marks),
                causes=causes_list(state, run), gate=gate_of(state, run, cat, prof), retries=retries_of(state, run),
                job=job_meta(job) if job else None)


def groups(state, run, cat, fwd, ctx=None):
    ctx = ctx or Ctx(cat)
    out = []
    for g in runview.build_groups(run, cat, state.hints, fwd):
        entries = []
        for x in g.entries:
            if x.kind == "test":
                entries.append({"kind": "test", "test": test_row(cat, x.test, ctx)})
            elif x.kind == "scenario":
                entries.append({"kind": "scenario", "title": x.scenario.title, "result": x.result.value,
                                "sentence": x.text, "tag": catalog.TRACK_TAG.get(x.scenario.steps[0].track, ""),
                                "steps": [dict(test_row(cat, t, ctx), step=catalog.step_number(t.name)) for t in x.steps]})
            else:
                entries.append({"kind": x.kind, "text": x.text})
        out.append({"result": g.result.value, "count": g.count, "entries": entries})
    return out


def detail(d):
    return {
        "purpose": d.purpose, "happened": d.happened,
        "recorded": {"pattern": d.recorded[0], "reason": d.recorded[1]} if d.recorded else None,
        "unrecordedGap": d.unrecorded_gap,
        "hint": {"id": d.hint.id, "text": d.hint.text, "action": d.hint.action} if d.hint else None,
        "location": d.location, "source": [{"n": n, "text": text, "hl": hl} for n, text, hl in d.source],
        "raw": d.raw[:20000],
    }


def labels(cat, t, run, ctx):
    """The labels grid of a test page (C5): [[name, value]]."""
    ct = cat.find(t.module, t.cls, t.base)
    track = runview.track_of(cat, t)
    out = [["Track", track]]
    out.append(["File", f"{t.module}.py:{ct.line}" if ct else f"{t.module}.py"])
    if t.cls:
        out.append(["Class", t.cls])
    if ct:
        out += [["Level", ct.level], ["Kind", ct.kind], ["Markers", ", ".join(ct.markers) or "none"]]
        if ct.ports_needed:
            out.append(["Ports needed", str(ct.ports_needed)])
        if ct.variants:
            out.append(["Variants", f"{len(ct.variants)}: {', '.join(ct.variants[:12])}{' …' if len(ct.variants) > 12 else ''}"])
    if t.param is not None:
        out.append(["Parameter", t.param])
    sc = ctx.scenario.get((t.module, t.cls, t.base))
    if sc and ct and ct.step:
        needs = ", ".join(ct.step["needs"]) or "nothing"
        out.append(["Scenario", f"{sc.title} · step {catalog.step_number(t.name) or '?'} ({ct.step['name']}, needs {needs})"])
    g = profiles.gap_for(t.name, ctx.gaps) if not t.upstream else None
    if g:
        out.append(["Gap pattern", g[0]])
    out += [["Target", run.target], ["Run", run.id]]
    return out


def test_page(state, run, t):
    """Everything the test detail shows (C1–C6): detail, diff, labels, history, other targets, steps, marks."""
    cat = state.catalogue()
    prof = state.profiles().get(run.target)
    d = runview.detail(run, t, cat, prof, state.hints, state.s.poc_dir)
    marks = history.marks(state.index, state.results, run)
    ctx = Ctx(cat, run, marks, prof, state.gap_notes())
    rows = history.test_history(state.index, state.results, run, t.key)
    passed, counted = history.success_rate(rows)
    others = history.across_targets(state.index, state.results, t.key, list(state.profiles()))
    notes = state.gap_notes()
    targets = []
    for name, (r, x) in others.items():
        p = state.profiles().get(name)
        g = profiles.gap_for(x.name, p.expected_gaps) if p else None
        targets.append({"target": name, "runId": r.id, "started": iso(r.started), "result": x.result.value,
                        "seconds": round(x.seconds, 3), "message": (x.message.splitlines() or [""])[0][:200],
                        "gap": {"pattern": g[0], "reason": g[1], "note": gapnotes.as_dict(gapnotes.get(notes, name, g[0]))}
                        if g else None, "current": r.id == run.id})
    for name in state.profiles():
        if name not in others:
            targets.append({"target": name, "runId": None, "started": None, "result": None, "seconds": 0,
                            "message": "", "gap": None, "current": False})
    sc = ctx.scenario.get((t.module, t.cls, t.base))
    steps = None
    if sc:
        idents = {(st.module, st.cls, st.name): st for st in sc.steps}
        steps = []
        for x in run.tests:
            st = idents.get((x.module, x.cls, x.base))
            if st is None:
                continue
            steps.append(dict(test_row(cat, x, ctx), needs=st.step["needs"] if st.step else [],
                              stepName=st.step["name"] if st.step else "",
                              happened=explain.what_happened(x.result, x.message, x.detail)))
    diff = explain.expected_actual(t.message, t.detail) if t.result is not Result.PASS else None
    return dict(
        detail(d), test=test_row(cat, t, ctx),
        diff={"expected": diff[0], "actual": diff[1]} if diff else None,
        labels=labels(cat, t, run, ctx),
        history={"rows": [{"runId": h.run_id, "started": h.started, "result": h.result.value,
                           "seconds": round(h.seconds, 3), "message": h.message} for h in rows],
                 "passed": passed, "counted": counted},
        targets=targets, steps=steps, scenario=sc.title if sc else None,
    )


def charts(state, run):
    """Data for the run's Charts view (E1, E2, E3, E7, E8): history up to this run on its target."""
    cat = state.catalogue()
    dyn = history.dynamics(state.index, state.results, run)
    stab = history.stability(state.index, state.results, run, cat, runview.track_of)
    order = {t: i for i, t in enumerate(catalog.TRACK_ORDER)}
    secs = sorted(t.seconds for t in run.tests if not t.upstream and t.result is not Result.SKIPPED)
    return {
        "dynamics": [{"runId": x["run"].id, "started": iso(x["run"].started), "counts": counts(x["counts"]),
                      "fixed": x["fixed"], "regressed": x["regressed"], "seconds": round(x["seconds"], 1),
                      "compared": x["compared"], "current": x["run"].id == run.id} for x in dyn],
        "stability": [{"track": tr, "tag": catalog.TRACK_TAG.get(tr, tr), "stable": s, "total": n}
                      for tr, (s, n) in sorted(stab.items(), key=lambda kv: order.get(kv[0], 99))],
        "durations": secs,
    }


def target(state, name, prof, containers, docker_error):
    cname = testbed.container_name(prof.exec_args, state.s.sc_root)
    container = containers.get(cname)
    lock = testbed.lock_state(state.s.lock_dir, prof.lock)
    st = testbed.target_state(container, lock, docker_error)
    active = [j for j in state.runner.active() if j.lock == prof.lock] if state.runner else []
    running = next((j for j in active if j.state == "running"), None)
    queued = sum(1 for j in active if j.state == "queued")
    if running and st.kind in ("yours", "ready") and running.target == name:
        p = state.progress(running)
        total = p.collected or running.count
        st = testbed.TargetState("yours", f"Running: your UI run · {p.done} of {total}")
    elif running and st.kind in ("yours", "ready"):
        st = testbed.TargetState("yours", f"Busy: your UI run on {running.target} (same lock)")
    if queued:
        st = testbed.TargetState(st.kind, f"{st.text} · {queued} queued in the UI")
    fwd, source = state.s.forwards_traffic(prof)
    run = state.latest().get(name)
    holder = None
    if lock.holder:
        h = lock.holder
        holder = {"who": h.who, "user": h.user, "pid": h.pid, "since": iso(h.since), "report": h.report}
    return {
        "name": name, "testbed": prof.testbed, "profilePath": f"tests/poc/targets/{name}.json",
        "error": prof.error or None, "duplicates": prof.duplicates, "ports": prof.ports,
        "trafficFilters": prof.traffic_filters, "expectedGaps": len(prof.expected_gaps), "scopeGaps": len(prof.scope_gaps),
        "forwardsTraffic": fwd, "forwardsSource": source,
        "container": {"name": cname, "state": container["state"] if container else None,
                      "status": container["status"] if container else None},
        "lock": {"path": str(lock.path), "exists": lock.exists, "holder": holder, "waiting": lock.waiting},
        "state": {"kind": st.kind, "text": st.text},
        "latest": run_summary(state, run) if run else None,
        "gate": gate_of(state, run, prof=prof) if run else None,
        "trend": [{"id": r.id, "started": iso(r.started), "counts": counts(r.counts(poc_only=True))}
                  for r in [r for r in state.index.runs(name) if not r.upstream_only][:12][::-1]],
        "runCount": len(state.index.runs(name)),
        "blocked": state.blocked(name),
        "uiJobs": [{"id": j.id, "state": j.state} for j in active],
    }


def by_track(cat, runs):
    """{track: {target: counts}} over the PoC tests of each column's run (the heat map, E5)."""
    out = {}
    for run in runs:
        for t in run.tests:
            if t.upstream or t.name == "(collection)":
                continue
            c = out.setdefault(runview.track_of(cat, t), {}).setdefault(run.target, {r.value: 0 for r in Result})
            c[t.result.value] += 1
    order = {t: i for i, t in enumerate(catalog.TRACK_ORDER)}
    return [{"track": tr, "tag": catalog.TRACK_TAG.get(tr, tr), "targets": v}
            for tr, v in sorted(out.items(), key=lambda kv: order.get(kv[0], 99))]


def matrix(m, cat=None):
    return {
        "byTrack": by_track(cat, m.columns) if cat else [],
        "columns": [{"id": r.id, "target": r.target, "started": iso(r.started)} for r in m.columns],
        "rows": [{
            "key": row.key, "track": row.track, "module": row.module, "title": row.title, "testId": row.test_id,
            "scenario": row.scenario, "differs": row.differs,
            "badges": [{"kind": k, "target": t, "text": compare.BADGE_TEXT[k]} for k, t in row.badges],
            "cells": {target: {
                "result": c.result.value if c.result else None, "message": c.message[:300], "seconds": round(c.seconds, 3),
                "runId": c.run_id, "gap": {"pattern": c.gap[0], "reason": c.gap[1]} if c.gap else None,
                "steps": [{"n": n, "result": r.value, "message": msg[:200], "name": name}
                          for n, r, msg, name in c.steps] if c.steps else None,
                "recent": [r.value for r in row.recent[target]] if target in row.recent else None,
            } for target, c in row.cells.items()},
        } for row in m.rows],
        "attention": m.attention, "differing": len(m.differing), "total": len(m.rows),
    }


def diff(d):
    return {
        "a": {"id": d.a.id, "target": d.a.target}, "b": {"id": d.b.id, "target": d.b.target},
        "headline": d.headline, "compared": d.compared, "onlyA": d.only_a, "onlyB": d.only_b,
        "sections": [{"title": title, "items": [{
            "name": tb.name, "title": catalog.readable(tb.name) + (f" · {tb.param}" if tb.param else ""),
            "a": ta.result.value, "b": tb.result.value,
            "message": ((tb.message or ta.message).splitlines() or [""])[0][:200],
        } for ta, tb in pairs]} for title, pairs in d.sections.items() if pairs],
    }


def gaps(register, notes=None):
    notes = notes or {}
    return {
        "entries": [{
            "pattern": g.pattern, "scope": g.scope, "reasons": g.reasons,
            "notes": {} if g.scope else {t: gapnotes.as_dict(gapnotes.get(notes, t, g.pattern)) for t in g.reasons},
            "status": {t: {"code": s, "text": profiles.STATUS_TEXT.get(s, "Not run")} for t, s in g.status.items()},
            "returned": g.returned, "evidence": g.evidence, "flags": g.flags,
        } for g in register],
        "runbookMarkdown": compare.runbook_table(register),
    }


def catalogue(state, cat, latest):
    lookup = state.lookup
    targets = [t for t, r in latest.items() if r]
    tracks = []
    for track in catalog.TRACK_ORDER:
        tests = [t for t in cat.tests if t.track == track]
        if not tests:
            continue
        rows = []
        for t in tests:
            results = {}
            for target in targets:
                found = lookup.results(latest[target]).get((t.module, t.cls, t.name), [])
                results[target] = {
                    "result": compare.worst(x.result for x in found).value if found else None,
                    "variants": [{"param": x.param, "result": x.result.value, "message": x.message[:200]} for x in found],
                    "runId": latest[target].id,
                }
            sc = cat.scenario_of(t)
            rows.append({
                "module": t.module, "cls": t.cls, "name": t.name, "title": t.title, "line": t.line, "level": t.level,
                "kind": t.kind, "markers": t.markers, "variants": t.variants, "portsNeeded": t.ports_needed,
                "purpose": t.purpose, "step": catalog.step_number(t.name) if sc else None,
                "scenario": sc.title if sc else None, "results": results,
            })
        tracks.append({"track": track, "tag": catalog.TRACK_TAG.get(track, track), "tests": rows})
    return {"targets": targets, "tracks": tracks, "total": len(cat.tests), "names": len(cat.all_names())}


# ---------------------------------------------------------------------------------------------- runs from the UI

def plan(state, planned):
    out = []
    for p in planned:
        prof = state.profiles()[p.target]
        lock = testbed.lock_state(state.s.lock_dir, prof.lock)
        ahead = [j for j in state.runner.active() if j.lock == prof.lock] if state.runner else []
        queue = ""
        if lock.holder:
            when = lock.holder.since.astimezone().strftime("%H:%M") if lock.holder.since else "?"
            queue = f"Busy: {lock.holder.who}'s run holds the lock (since {when}). This run will queue."
        elif ahead:
            queue = f"Busy: {len(ahead)} UI run{'s' if len(ahead) != 1 else ''} ahead on this lock. This run will queue."
        out.append({
            "target": p.target, "args": p.args, "command": p.command, "what": p.what, "count": p.count, "gaps": p.gaps,
            "traffic": p.traffic, "trafficTests": p.traffic_tests, "trafficNote": p.traffic_note, "mld": p.mld,
            "mldRelevant": p.mld_relevant, "estimate": p.estimate, "warnings": p.warnings, "blocked": p.blocked,
            "queue": queue, "forwards": state.s.forwards_traffic(prof)[0], "trafficFilters": prof.traffic_filters,
        })
    return out


def job_meta(job):
    return {
        "jobId": job.id, "command": job.command, "who": job.who, "commit": job.commit, "branch": job.branch,
        "dirty": job.dirty, "traffic": job.traffic, "mld": job.mld, "what": job.what,
        "setId": job.set_id, "setIndex": job.set_index, "setSize": job.set_size,
        "retry": job.retry, "attempt": job.attempt, "retryOf": job.retry_of,
    }


def _started(job):
    return datetime.fromisoformat(job.started or job.created)


def job_summary(state, job):
    p = state.progress(job)
    total = p.collected if p.collected is not None else job.count
    run = state.run(job.run_id) if job.run_id and job.state == "done" else None
    return {
        "id": job.id, "target": job.target, "state": job.state, "what": job.what, "count": job.count,
        "created": job.created, "started": job.started, "ended": job.ended, "seconds": round(jobs.elapsed(job), 1),
        "runId": job.run_id if run else None, "reportPending": bool(job.run_id and job.state == "done" and not run),
        "exitCode": job.exit_code, "note": job.note, "notify": job.notify,
        "setId": job.set_id, "setIndex": job.set_index, "setSize": job.set_size,
        "retry": job.retry, "attempt": job.attempt, "retryOf": job.retry_of,
        "done": p.done, "total": total, "headline": run.headline if run else None,
        "current": _title_of(p.current) if p.current else None,
    }


def _title_of(node_or_key):
    name = node_or_key.rsplit("::", 1)[-1]
    base, _, rest = name.partition("[")
    return catalog.readable(base) + (f" · {rest[:-1]}" if rest else "")


def _waiting(state, job, p):
    """The queued sentence (design §6.4), or None when the run isn't waiting for anyone."""
    runner = state.runner
    if job.state == "queued":
        ahead = runner.ahead_of(job)
        if ahead:
            first = ahead[0]
            if first.state == "running":
                fp = state.progress(first)
                total = fp.collected if fp.collected is not None else first.count
                return {"kind": "ui", "jobId": first.id,
                        "text": f"Waiting for {job.lock}: your UI run on {first.target} is running ({fp.done} of "
                                f"{total}). This run starts when it ends."}
            return {"kind": "ui", "jobId": first.id,
                    "text": f"Waiting for {job.lock}: {len(ahead)} UI run{'s' if len(ahead) != 1 else ''} ahead of this one."}
        holder = runner.waiting_on.get(job.lock)
        if holder is None:
            return {"kind": "starting", "jobId": None, "text": "Starting…"}
    elif job.state == "running" and p.waiting:
        lock = testbed.lock_state(state.s.lock_dir, job.lock)
        holder = lock.holder if not jobs.holder_is_ours(lock.holder, job.pid) else None
        if holder is None:
            return None
    else:
        return None
    when = holder.since.astimezone().strftime("%H:%M") if holder.since else "?"
    run = f" ({holder.report})" if holder.report else ""
    return {"kind": "lock", "jobId": None,
            "text": f"Waiting for {job.lock}: {holder.who}'s run{run} holds the lock (since {when}). Your run starts "
                    "when it ends. Don't stop their run."}


def job_full(state, job):
    cat = state.catalogue()
    prof = state.profiles().get(job.target)
    fwd = state.s.forwards_traffic(prof)[0] if prof else None
    p = state.progress(job)
    live = reports.Run(job.id, job.target, _started(job), jobs.elapsed(job), Path(job.id), None, None, "",
                       list(p.tests), source="UI")
    c = live.counts()
    done_keys = {t.key for t in p.tests}
    done_bases = {t.key.split("[", 1)[0] for t in p.tests}
    still = []
    current_key = None
    if p.current:
        module, cls, name, _, _ = console.split_node(p.current)
        current_key = "::".join(x for x in (module, cls, name) if x)
    if job.state in ("queued", "running"):
        for key in job.expected:
            if key in done_keys or ("[" not in key and key in done_bases):
                continue
            still.append({"key": key, "title": _title_of(key), "name": key.rsplit("::", 1)[-1],
                          "now": key == current_key or (current_key or "").split("[", 1)[0] == key})
        still.sort(key=lambda x: not x["now"])
    set_jobs = sorted((j for j in state.runner.jobs.values() if job.set_id and j.set_id == job.set_id),
                      key=lambda j: j.set_index) if job.set_id else []
    return dict(
        job_summary(state, job), **job_meta(job),
        counts=counts(c), countParts=[[r.value, text] for r, text in count_parts(c)],
        strip=strip(cat, live.tests), groups=groups(state, live, cat, fwd), still=still,
        waiting=_waiting(state, job, p), profileLine=p.profile_line, interrupted=p.interrupted,
        set=[{"id": j.id, "state": j.state, "index": j.set_index, "runId": j.run_id} for j in set_jobs],
        testbed=prof.testbed if prof else None,
    )
