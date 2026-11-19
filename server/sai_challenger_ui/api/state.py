"""What the server knows, reloaded only when the files behind it change.

Read-only towards SAI-Challenger: runs are started only by core.jobs.Runner, through run_poc.sh.
"""
import threading
import time

from ..core import catalog, compare, console, explain, profiles, reports, selection, testbed


class AppState:
    def __init__(self, settings):
        self.s = settings
        self.hints = explain.Hints()
        self.lookup = compare.Lookup()
        self.index = reports.RunIndex(settings.reports_dir)
        self._lock = threading.RLock()
        self._profiles, self._profiles_sig = {}, None
        self._cat, self._cat_sig = None, None
        self._runs_at = 0.0
        self._docker = (0.0, {}, None)
        self.runner = None  # core.jobs.Runner, set by the app
        self._progress = {}  # job id -> (log size, console.Progress)

    @staticmethod
    def _signature(paths):
        out = []
        for path in sorted(paths):
            try:
                out.append((path.name, path.stat().st_mtime_ns))
            except OSError:
                pass
        return tuple(out)

    def profiles(self):
        with self._lock:
            sig = self._signature(self.s.targets_dir.glob("*.json"))
            if sig != self._profiles_sig:
                self._profiles = profiles.load_all(self.s.targets_dir)
                self._profiles_sig = sig
                self.index.known_targets = tuple(self._profiles)
            return self._profiles

    def runs(self):
        """Newest first. The reports folder is rescanned at most once a second."""
        with self._lock:
            self.profiles()
            if time.monotonic() - self._runs_at > 1.0:
                self.index.refresh()
                self._runs_at = time.monotonic()
                ui = {j.run_id for j in self.runner.jobs.values() if j.run_id} if self.runner else set()
                for run in self.index.runs():
                    run.source = "UI" if run.id in ui else "CLI"
            return self.index.runs()

    def invalidate_runs(self):
        """A UI run ended: rescan the reports folder on the next request."""
        with self._lock:
            self._runs_at = 0.0

    def catalogue(self):
        with self._lock:
            runs = self.runs()
            sig = (self._signature(self.s.poc_dir.glob("test_*.py")), len(runs))
            if sig != self._cat_sig:
                self._cat = catalog.build(self.s.poc_dir)
                catalog.merge_history(self._cat, runs)
                self._cat_sig = sig
            return self._cat

    def latest(self):
        """{target: newest run that ran PoC tests, or None}, in reference column order."""
        self.runs()
        return {name: self.index.latest(name) for name in sorted(self.profiles(), key=compare.column_key)}

    def run(self, run_id):
        self.runs()
        return self.index.get(run_id)

    def blocked(self, name):
        """Why a target can't take a run now, or ''. A busy lock is not a block: the run queues."""
        prof = self.profiles().get(name)
        if prof is None:
            return "No profile"
        if prof.error:
            return f"Profile can't be read: {prof.error}"
        containers, error = self.docker()
        if error:
            return "Can't reach Docker"
        container = containers.get(testbed.container_name(prof.exec_args, self.s.sc_root))
        if container is None:
            return "No container (ask the testbed admin)"
        if container["state"] != "running":
            return "Container stopped (ask the testbed admin)"
        return ""

    def plan(self, req):
        profs = self.profiles()

        def forwards(name):
            return self.s.forwards_traffic(profs[name])[0]

        return selection.plan(req, self.catalogue(), profs, forwards, self.index.latest, self.runs(), self.s.user,
                              self.blocked)

    def progress(self, job):
        """console.Progress for a UI run, re-read only when its log grew."""
        path = self.runner.store.log_path(job.id)
        try:
            size = path.stat().st_size
        except OSError:
            size = -1
        cached = self._progress.get(job.id)
        if cached and cached[0] == size:
            return cached[1]
        text, _ = self.runner.console_text(job)
        prof = self.profiles().get(job.target)
        p = console.parse(text, prof.expected_gaps if prof else {})
        self._progress[job.id] = (size, p)
        return p

    def docker(self):
        """(containers, error); docker ps is called at most every 3 seconds."""
        with self._lock:
            at, found, error = self._docker
            if time.monotonic() - at > 3.0:
                try:
                    found, error = testbed.containers(), None
                except testbed.DockerUnavailable as exc:
                    found, error = {}, str(exc)
                self._docker = (time.monotonic(), found, error)
            return found, error
