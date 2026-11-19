"""The HTTP API and static serving of the React build.

The only action is starting runs through run_poc.sh (core.jobs), and taking a run off the queue before it
starts. Nothing here edits SAI-Challenger or touches a container. Run ids, job ids and test keys are looked
up in what the server knows; nothing from a request is used as a path or passed to a shell.
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from .. import settings as settings_mod
from ..core import compare, jobs, runview, selection, testbed
from . import serialize
from .state import AppState

DEFAULT_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
_LOCAL = {"127.0.0.1", "localhost", "::1"}


def _host(value):
    try:
        return (urlsplit(value if "//" in value else f"//{value}").hostname or "").lower()
    except ValueError:
        return ""


def create_app(settings=None, dist=DEFAULT_DIST):
    state = AppState(settings or settings_mod.load())
    runner = jobs.Runner(state.s, lambda name: state.profiles()[name].lock if name in state.profiles() else None,
                         on_change=state.invalidate_runs)
    state.runner = runner

    @asynccontextmanager
    async def lifespan(app):
        await runner.start()
        yield
        await runner.stop()

    app = FastAPI(title="SAI Conformance UI", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json",
                  lifespan=lifespan)
    app.state.ui = state

    def guard(request):
        """Actions only from this machine's browser tab: a page on another site can't send this header without
        a CORS preflight, which the server never answers, and a DNS-rebound name fails the Host check."""
        if state.s.mode != "local":
            raise HTTPException(403, "Starting runs is only available in local mode")
        if not runner.owner:
            raise HTTPException(409, "Another sai-challenger-ui server on this machine manages runs: start them there")
        if request.headers.get("x-sai-challenger-ui") != "1":
            raise HTTPException(403, "Missing X-SAI-Challenger-UI header")
        if _host(request.headers.get("host", "")) not in _LOCAL:
            raise HTTPException(403, "Runs can only be started from this machine (localhost)")
        origin = request.headers.get("origin")
        if origin and _host(origin) not in _LOCAL:
            raise HTTPException(403, "Runs can only be started from this machine (localhost)")

    async def body_of(request):
        if not request.headers.get("content-type", "").startswith("application/json"):
            raise HTTPException(415, "Send JSON")
        try:
            return selection.Request.from_json(await request.json())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    def job_or_404(job_id):
        if job_id not in runner.jobs:
            runner.reload()
        job = runner.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, f"no UI run {job_id}")
        return job

    def run_or_404(run_id):
        run = state.run(run_id)
        if run is None:
            raise HTTPException(404, f"no run {run_id}")
        return run

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__, "mode": state.s.mode, "scRoot": str(state.s.sc_root),
                "canRun": state.s.mode == "local" and runner.owner, "ownsRuns": runner.owner, "user": state.s.user,
                "runs": len(state.runs())}

    @app.get("/api/memory")
    def memory():
        avail, total = testbed.memory()
        return {"available": avail, "total": total, "low": avail < 1.5 * 2**30}

    @app.get("/api/targets")
    def targets():
        containers, error = state.docker()
        return {"dockerError": error,
                "targets": [serialize.target(state, name, prof, containers, error)
                            for name, prof in sorted(state.profiles().items(), key=lambda kv: kv[0])]}

    @app.get("/api/runs")
    def runs(target: str | None = None, attention: bool = False, limit: int = Query(50, ge=1, le=1000)):
        found = [r for r in state.runs() if (target is None or r.target == target)]
        if attention:
            found = [r for r in found if any(r.counts()[x] for x in runview.ATTENTION)]
        return {"total": len(state.runs()), "matching": len(found),
                "targets": sorted({r.target for r in state.runs()}),
                "runs": [serialize.run_summary(state, r) for r in found[:limit]]}

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        return serialize.run_full(state, run_or_404(run_id))

    @app.get("/api/runs/{run_id}/detail")
    def run_detail(run_id: str, key: str):
        r = run_or_404(run_id)
        t = next((x for x in r.tests if x.key == key), None)
        if t is None:
            raise HTTPException(404, f"no test {key} in {run_id}")
        d = runview.detail(r, t, state.catalogue(), state.profiles().get(r.target), state.hints, state.s.poc_dir)
        return serialize.detail(d)

    @app.get("/api/runs/{run_id}/report/{kind}")
    def report_file(run_id: str, kind: str):
        r = run_or_404(run_id)
        path = {"xml": r.xml, "html": r.html}.get(kind)
        if path is None or not path.is_file():
            raise HTTPException(404, f"no {kind} report for {run_id}")
        return FileResponse(path)

    def pick(ids):
        latest = [r for r in state.latest().values() if r]
        if not ids:
            return latest
        chosen = [run_or_404(i) for i in ids.split(",") if i]
        return chosen

    @app.get("/api/compare/matrix")
    def matrix(runs: str | None = None):
        m = compare.build_matrix(pick(runs), state.profiles(), state.catalogue(), state.index)
        return serialize.matrix(m)

    @app.get("/api/compare/diff")
    def diff(a: str | None = None, b: str | None = None):
        latest = state.latest()
        ra = run_or_404(a) if a else latest.get("saivs")
        rb = run_or_404(b) if b else latest.get("saivs-thrift")
        if ra is None or rb is None:
            raise HTTPException(404, "two runs are needed: pass a= and b=")
        return serialize.diff(compare.run_diff(ra, rb))

    @app.get("/api/compare/gaps")
    def gaps():
        register = compare.gap_register(state.profiles(), state.latest(), state.catalogue().all_names())
        return serialize.gaps(register)

    @app.get("/api/tests")
    def tests():
        return serialize.catalogue(state, state.catalogue(), state.latest())

    @app.get("/api/tests/history")
    def test_history(module: str, name: str, cls: str | None = None, n: int = Query(20, ge=1, le=200)):
        cat = state.catalogue()
        t = cat.find(module, cls, name)
        if t is None:
            raise HTTPException(404, f"no test {module}::{cls or ''}::{name}")
        out = {}
        for target, prof in state.profiles().items():
            hist = state.lookup.history(state.index, target, (module, cls, name), n)
            gap = next((g for g in (serialize.profiles.gap_for(v, prof.expected_gaps) for v in t.names) if g), None)
            out[target] = {"runs": [{"id": rid, "result": r.value} for rid, r in hist],
                           "gap": {"pattern": gap[0], "reason": gap[1]} if gap else None}
        return out

    # ------------------------------------------------------------------ runs from the UI

    @app.post("/api/plan")
    async def plan(request: Request):
        """What a run sheet would start: commands, counts, warnings. Starts nothing."""
        req = await body_of(request)
        try:
            planned = await asyncio.to_thread(state.plan, req)
        except selection.BadRequest as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"targets": await asyncio.to_thread(serialize.plan, state, planned), "repeat": req.repeat}

    @app.post("/api/jobs")
    async def start_jobs(request: Request):
        guard(request)
        req = await body_of(request)
        try:
            planned = await asyncio.to_thread(state.plan, req)
        except selection.BadRequest as exc:
            raise HTTPException(400, str(exc)) from exc
        runnable = [p for p in planned if not p.blocked]
        if not runnable:
            raise HTTPException(409, "; ".join(f"{p.target}: {p.blocked}" for p in planned))
        commit, branch, dirty = await asyncio.to_thread(jobs.git_state, state.s.sc_root)
        created, new = jobs.now_iso(), []
        for p in runnable:
            set_id = None
            for i in range(req.repeat):
                job = jobs.Job(
                    id=runner.new_id(p.target), target=p.target, lock=state.profiles()[p.target].lock, args=p.args,
                    command=p.command, what=p.what, expected=p.expected, count=p.count, traffic=p.traffic, mld=p.mld,
                    who=state.s.user, created=created, commit=commit, branch=branch, dirty=dirty,
                    set_index=i + 1, set_size=req.repeat, notify=req.notify,
                )
                set_id = set_id or (job.id if req.repeat > 1 else None)
                job.set_id = set_id
                new.append(job)
        runner.submit(new)
        return {"jobs": [j.id for j in new], "skipped": [{"target": p.target, "why": p.blocked}
                                                         for p in planned if p.blocked]}

    @app.get("/api/jobs")
    async def list_jobs():
        runner.reload()
        return {"active": [serialize.job_summary(state, j) for j in runner.active()],
                "recent": [serialize.job_summary(state, j) for j in runner.recent()]}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        return await asyncio.to_thread(serialize.job_full, state, job_or_404(job_id))

    @app.get("/api/jobs/{job_id}/console")
    async def job_console(job_id: str, offset: int = Query(0, ge=0), limit: int = Query(262144, ge=1, le=4194304)):
        job = job_or_404(job_id)
        text, end = runner.console_text(job, offset, limit)
        try:
            size = runner.store.log_path(job.id).stat().st_size
        except OSError:
            size = 0
        return {"text": text, "offset": end, "size": size, "active": job.state in jobs.ACTIVE}

    @app.get("/api/jobs/{job_id}/console.txt")
    async def job_console_file(job_id: str):
        job = job_or_404(job_id)
        text, _ = runner.console_text(job)
        return PlainTextResponse(text, headers={"Content-Disposition": f'inline; filename="{job.id}.log"'})

    @app.delete("/api/jobs/{job_id}")
    async def remove_job(job_id: str, request: Request):
        guard(request)
        job = job_or_404(job_id)
        if not runner.remove(job.id):
            raise HTTPException(409, "Only a run that hasn't started can be taken off the queue")
        return {"removed": job.id}

    @app.exception_handler(404)
    async def not_found(request, exc):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": getattr(exc, "detail", "not found")}, status_code=404)
        index = Path(dist) / "index.html"
        if index.is_file():  # client-side routes: /targets, /runs/<id>, ... all load the app
            return FileResponse(index)
        return JSONResponse({"detail": "web build not found; run npm run build in web/"}, status_code=404)

    if (Path(dist) / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=Path(dist) / "assets"), name="assets")

    @app.get("/")
    def root():
        index = Path(dist) / "index.html"
        if index.is_file():
            return FileResponse(index)
        return {"detail": "web build not found; run npm run build in web/", "api": "/api/docs"}

    return app
