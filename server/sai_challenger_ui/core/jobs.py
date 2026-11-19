"""Runs started from the UI: a queue per target lock, run_poc.sh as the only way to a target.

- run_poc.sh is started with a list of arguments (no shell) from the checkout, exactly as a person would run it.
  It takes the lock itself; the UI only waits its turn first, so a run waiting for someone else's CLI run can
  still be taken off the queue.
- Its output goes to a file in the UI's own state folder, never into SAI-Challenger, and it runs in its own
  session: stopping the UI server (Ctrl+C) doesn't interrupt a test run, and a restarted server picks it up again.
- The JUnit file run_poc.sh writes is the result. The console only gives progress while the run is live.

There is no Cancel for a run that has started: how to stop one safely inside the container is the open
Cancel spike (build step 0.10).
"""
import asyncio
import fcntl
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path

from . import console, testbed

ACTIVE = ("queued", "running")
_JUNIT_ARG_RE = re.compile(r"--junitxml=(?:.*/)?reports/([^/]+)\.xml$")


def now_iso():
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    target: str
    lock: str
    args: list  # run_poc.sh arguments after the profile name
    command: str  # as "Show command" printed it
    what: str
    expected: list  # test keys in run order
    count: int
    traffic: bool
    mld: str
    who: str
    created: str
    commit: str = ""
    branch: str = ""
    dirty: list = field(default_factory=list)  # changed files under tests/poc and scripts/poc
    state: str = "queued"  # queued | running | done | removed
    started: str | None = None
    ended: str | None = None
    pid: int | None = None
    exit_code: int | None = None
    run_id: str | None = None  # the report's file stem, once known
    set_id: str | None = None  # repeat: runs of one request on one target share it
    set_index: int = 1
    set_size: int = 1
    notify: bool = False
    note: str = ""  # why a run ended without a report, or was taken off the queue
    retry: int = 0  # "Retry failures": how many reruns of what fails are allowed
    attempt: int = 1  # 1 for the run asked for, 2 for its first retry, ...
    retry_of: str | None = None  # the job id of attempt 1

    @classmethod
    def from_dict(cls, data):
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


class Store:
    """One JSON file and one console log per job in <state dir>/jobs."""

    def __init__(self, folder):
        self.dir = Path(folder)

    def log_path(self, job_id):
        return self.dir / f"{job_id}.log"

    def save(self, job):
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f".{job.id}.json.tmp"
        tmp.write_text(json.dumps(asdict(job), indent=1))
        tmp.replace(self.dir / f"{job.id}.json")

    def load_all(self):
        jobs = []
        for path in sorted(self.dir.glob("*.json")):
            try:
                jobs.append(Job.from_dict(json.loads(path.read_text())))
            except (OSError, ValueError, TypeError):
                continue
        return jobs


def git_state(root, timeout=5):
    """(short commit, branch, changed files under tests/poc and scripts/poc). Read-only: no index refresh."""
    def git(*args):
        try:
            out = subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args],
                                 capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return out.stdout if out.returncode == 0 else ""

    commit = git("rev-parse", "--short", "HEAD").strip()
    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    status = git("status", "--porcelain", "--untracked-files=all", "--",
                 "tests/poc", "scripts/poc", ":(exclude)tests/poc/reports")
    dirty = [line[3:] for line in status.splitlines() if len(line) > 3]
    return commit, branch, dirty


def _children(pid):
    out = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            stat = proc.joinpath("stat").read_text()
            if int(stat[stat.rindex(")") + 2:].split()[1]) == pid:
                out.append(int(proc.name))
        except (OSError, ValueError, IndexError):
            continue
    return out


def report_of(pid):
    """The report stem run_poc.sh chose, read from its flock child's --junitxml=... argument."""
    for child in _children(pid):
        try:
            args = Path("/proc", str(child), "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        for arg in args:
            m = _JUNIT_ARG_RE.search(arg.decode(errors="replace"))
            if m:
                return m.group(1)
    return None


def holder_is_ours(holder, pid):
    """True when the lock holder is the flock that our run_poc.sh (pid) started."""
    if holder is None or pid is None:
        return False
    return holder.pid == pid or holder.pid in _children(pid)


def alive(pid, script):
    """The process exists and is still our run_poc.sh (pids are reused)."""
    try:
        cmd = Path("/proc", str(pid), "cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    return any(c.decode(errors="replace").endswith(script) for c in cmd)


class Runner:
    def __init__(self, settings, profile_lock, store=None, on_change=None, lock_state=testbed.lock_state,
                 on_finish=None):
        """profile_lock(target) -> lock name from the current profile. on_change() runs after a job changes state.
        on_finish(job) runs when a run this server watched ends (not for runs found ended after a restart)."""
        self.s = settings
        self.script = settings.sc_root / "scripts" / "poc" / "run_poc.sh"
        self.store = store or Store(settings.state_dir / "jobs")
        self.profile_lock = profile_lock
        self.on_change = on_change or (lambda: None)
        self.on_finish = on_finish or (lambda job: None)
        self.lock_state = lock_state
        self.jobs = {}
        self._wake = None
        self._task = None
        self._watchers = set()
        self._seq = 0
        self.waiting_on = {}  # lock -> testbed.Holder while a queued job waits for someone else's run
        self.owner = False  # this server manages runs; a second server on the same state folder only shows them
        self._owner_fd = None

    # ------------------------------------------------------------------ ids and lookup

    def new_id(self, target):
        self._seq += 1
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        job_id = f"{target}-{stamp}-ui{self._seq}"
        while job_id in self.jobs:
            self._seq += 1
            job_id = f"{target}-{stamp}-ui{self._seq}"
        return job_id

    def by_run(self, run_id):
        for job in self.jobs.values():
            if job.run_id == run_id:
                return job
        return None

    def active(self):
        return sorted((j for j in self.jobs.values() if j.state in ACTIVE), key=lambda j: (j.created, j.set_index))

    def recent(self, n=20):
        done = [j for j in self.jobs.values() if j.state not in ACTIVE]
        return sorted(done, key=lambda j: j.ended or j.created, reverse=True)[:n]

    def ahead_of(self, job):
        """Jobs on the same lock that run before this one."""
        return [j for j in self.active() if j.lock == job.lock and j is not job
                and (j.state == "running" or (j.created, j.set_index) < (job.created, job.set_index))]

    def console_text(self, job, offset=0, limit=None):
        path = self.store.log_path(job.id)
        try:
            with open(path, "rb") as f:
                f.seek(offset)
                data = f.read() if limit is None else f.read(limit)
        except OSError:
            return "", offset
        return data.decode(errors="replace"), offset + len(data)

    # ------------------------------------------------------------------ lifecycle

    def _claim(self):
        """Only one sai-challenger-ui server per state folder may start or track runs."""
        self.store.dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.store.dir / "runner.lock", os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        self._owner_fd = fd
        return True

    def reload(self):
        """A server that doesn't own the runs re-reads them from disk to show them."""
        if not self.owner:
            self.jobs = {job.id: job for job in self.store.load_all()}

    async def start(self):
        self._wake = asyncio.Event()
        self.owner = self._claim()
        if not self.owner:
            print(f"sai-challenger-ui: another sai-challenger-ui server manages runs in {self.store.dir}; this one only shows them.",
                  flush=True)
            self.reload()
            return
        for job in self.store.load_all():
            self.jobs[job.id] = job
            self._seq = max(self._seq, _seq_of(job.id))
        for job in list(self.jobs.values()):
            if job.state == "queued":  # never start a run nobody is watching for after a restart
                self._finish(job, None, note="The UI server stopped before this run started. Nothing was run.",
                             state="removed")
            elif job.state == "running":
                if job.pid and alive(job.pid, str(self.script)):
                    self._track(asyncio.ensure_future(self._watch_pid(job)))
                else:
                    self._finish(job, None)
        self._task = asyncio.ensure_future(self._loop())

    async def stop(self):
        """Stop scheduling. Running tests are left alone: they finish and write their report."""
        if self._task:
            self._task.cancel()
        for w in list(self._watchers):
            w.cancel()
        if self._owner_fd is not None:
            os.close(self._owner_fd)  # releases the claim
            self._owner_fd = None

    def _track(self, task):
        self._watchers.add(task)
        task.add_done_callback(self._watchers.discard)

    def submit(self, jobs):
        if not self.owner:
            raise RuntimeError("another sai-challenger-ui server manages runs")
        for job in jobs:
            job.state = "queued"
            self.jobs[job.id] = job
            self.store.save(job)
        self.on_change()
        self._kick()

    def remove(self, job_id):
        """Take a run off the queue. Only before run_poc.sh started: there's nothing to stop yet."""
        job = self.jobs.get(job_id)
        if not self.owner or job is None or job.state != "queued":
            return False
        self._finish(job, None, note="Taken off the queue before it started. Nothing was run.", state="removed")
        self._kick()
        return True

    def _kick(self):
        if self._wake:
            self._wake.set()

    async def _loop(self):
        while True:
            try:
                await self.schedule()
            except Exception as exc:  # noqa: BLE001 - keep the queue alive; the next pass tries again
                print(f"sai-challenger-ui: scheduler error: {exc!r}", flush=True)
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=2.0)
            except TimeoutError:
                pass
            self._wake.clear()

    async def schedule(self):
        """Start the oldest queued run on every lock that no UI run is using and nobody else holds."""
        self.waiting_on = {}
        for job in self.active():
            if job.state == "running" and not job.run_id and job.pid:
                job.run_id = report_of(job.pid)
                if job.run_id:
                    self.store.save(job)
        busy = {j.lock for j in self.active() if j.state == "running"}
        for job in self.active():
            if job.state != "queued" or job.lock in busy:
                continue
            busy.add(job.lock)
            lock = self.lock_state(self.s.lock_dir, job.lock)
            if lock.holder is not None:
                self.waiting_on[job.lock] = lock.holder
                continue
            await self._launch(job)

    async def _launch(self, job):
        if self.profile_lock(job.target) != job.lock:
            self._finish(job, None, state="removed",
                         note="The target's profile changed its lock while this run was queued. Nothing was run.")
            return
        self.store.dir.mkdir(parents=True, exist_ok=True)
        log = os.open(self.store.log_path(job.id), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            proc = await asyncio.create_subprocess_exec(
                str(self.script), job.target, *job.args,
                cwd=str(self.s.sc_root), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            self._finish(job, None, note=f"run_poc.sh could not be started: {exc}")
            return
        finally:
            os.close(log)  # the child has its own copy
        job.state, job.pid, job.started = "running", proc.pid, now_iso()
        self.store.save(job)
        self.on_change()
        self._track(asyncio.ensure_future(self._watch(job, proc)))

    async def _watch(self, job, proc):
        rc = await proc.wait()
        self._finish(job, rc)
        self._ended(job)
        self._kick()

    async def _watch_pid(self, job):
        """A run started by an earlier server process: not our child, so poll it."""
        while alive(job.pid, str(self.script)):
            if not job.run_id:
                job.run_id = report_of(job.pid)
            await asyncio.sleep(2.0)
        self._finish(job, None)
        self._ended(job)
        self._kick()

    def _ended(self, job):
        try:
            self.on_finish(job)
        except Exception as exc:  # noqa: BLE001 - a failing hook must not stop the queue
            print(f"sai-challenger-ui: after-run step failed for {job.id}: {exc!r}", flush=True)

    def _finish(self, job, rc, note="", state="done"):
        text, _ = self.console_text(job)
        progress = console.parse(text)
        if progress.report:
            job.run_id = progress.report
        if progress.exit_code is not None:
            rc = progress.exit_code
        job.exit_code = rc
        job.state, job.ended = state, now_iso()
        if note:
            job.note = note
        elif state == "done":
            xml = self.s.reports_dir / f"{job.run_id}.xml" if job.run_id else None
            if xml is None or not xml.is_file():
                job.note = ("No report was written: pytest stopped before running tests, or run_poc.sh was "
                            "interrupted. The console shows why.")
        self.store.save(job)
        self.on_change()


def _seq_of(job_id):
    m = re.search(r"-ui(\d+)$", job_id)
    return int(m.group(1)) if m else 0


def elapsed(job):
    if not job.started:
        return 0.0
    start = datetime.fromisoformat(job.started).timestamp()
    end = datetime.fromisoformat(job.ended).timestamp() if job.ended else time.time()
    return max(0.0, end - start)

