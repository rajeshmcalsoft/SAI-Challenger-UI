"""Core objects to JSON-ready dicts. Results go out as their stable codes (pass, fail, expected_gap, ...)."""
from datetime import datetime
from pathlib import Path

from ..core import catalog, compare, console, jobs, profiles, reports, runview, testbed
from ..core.vocab import count_parts


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


def test_row(cat, t):
    track = runview.track_of(cat, t)
    title = f"Collection failed: {t.module}.py" if t.name == "(collection)" else (
        catalog.readable(t.name) + (f" · {t.param}" if t.param else ""))
    return {
        "key": t.key, "module": t.module, "cls": t.cls, "name": t.name, "title": title, "result": t.result.value,
        "seconds": round(t.seconds, 3), "message": t.message[:500], "track": track,
        "tag": catalog.TRACK_TAG.get(track, track), "cleanupFailed": t.cleanup_failed, "upstream": t.upstream,
    }


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
    return dict(run_summary(state, run), testbed=prof.testbed if prof else None, hostname=run.hostname,
                report=run.xml.name, html=run.html.name if run.html else None, pocTests=poc,
                upstreamTests=len(run.tests) - poc, since=since, groups=groups(state, run, cat, fwd),
                job=job_meta(job) if job else None)


def groups(state, run, cat, fwd):
    out = []
    for g in runview.build_groups(run, cat, state.hints, fwd):
        entries = []
        for x in g.entries:
            if x.kind == "test":
                entries.append({"kind": "test", "test": test_row(cat, x.test)})
            elif x.kind == "scenario":
                entries.append({"kind": "scenario", "title": x.scenario.title, "result": x.result.value,
                                "sentence": x.text, "tag": catalog.TRACK_TAG.get(x.scenario.steps[0].track, ""),
                                "steps": [dict(test_row(cat, t), step=catalog.step_number(t.name)) for t in x.steps]})
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
        "runCount": len(state.index.runs(name)),
        "blocked": state.blocked(name),
        "uiJobs": [{"id": j.id, "state": j.state} for j in active],
    }


def matrix(m):
    return {
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


def gaps(register):
    return {
        "entries": [{
            "pattern": g.pattern, "scope": g.scope, "reasons": g.reasons,
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
