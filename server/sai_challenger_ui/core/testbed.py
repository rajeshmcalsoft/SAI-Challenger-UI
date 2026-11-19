"""Read-only view of the testbed: container state, lock holders, host memory.

Nothing here starts, stops or signals anything.
"""
import json
import os
import pwd
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class DockerUnavailable(Exception):
    pass


def container_name(exec_args, sc_root):
    """The container exec.sh would use for these options: <prefix>-<asic>-<target>-run."""
    asic, target, interface = "trident2", "", ""
    args = list(exec_args)
    for i, arg in enumerate(args[:-1]):
        if arg in ("-a", "--asic"):
            asic = args[i + 1]
        elif arg in ("-t", "--target"):
            target = args[i + 1]
        elif arg in ("-s", "--sai_interface"):
            interface = args[i + 1]
    if not target:  # exec.sh takes the first target folder under the ASIC folder
        folders = sorted(p for p in Path(sc_root, "npu").glob(f"**/{asic}") if p.is_dir())
        subs = sorted(d.name for d in folders[0].iterdir() if d.is_dir()) if folders else []
        target = subs[0] if subs else "?"
    prefix = "sc-thrift" if interface == "thrift" else "sc"
    return f"{prefix}-{asic}-{target}-run".lower()


def containers(timeout=5):
    """{name: {"state": "running"|"exited"|..., "status": "Up 3 weeks"}} from docker ps -a."""
    try:
        out = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DockerUnavailable(str(exc)) from exc
    if out.returncode != 0:
        raise DockerUnavailable(out.stderr.strip() or f"docker ps exited {out.returncode}")
    found = {}
    for line in out.stdout.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        for name in row.get("Names", "").split(","):
            found[name] = {"state": row.get("State", ""), "status": row.get("Status", "")}
    return found


@dataclass
class Holder:
    pid: int
    user: str
    since: datetime | None
    command: list
    report: str  # run id from --junitxml=..., when the holder is a run_poc.sh run
    mount_user: str  # "shantanu" from poc_shantanu/reports/...

    @property
    def who(self):
        return self.mount_user or self.user


@dataclass
class LockState:
    path: Path
    exists: bool
    holder: Holder | None
    waiting: int  # processes queued on the same lock


_LOCK_LINE = re.compile(r"^\d+:\s+(->\s+)?FLOCK\s+\S+\s+\S+\s+(\d+)\s+([0-9a-f]+):([0-9a-f]+):(\d+)\s")
_JUNIT_RE = re.compile(r"--junitxml=(?:.*/)?(?:poc_([A-Za-z0-9]+)/)?reports/([^/]+)\.xml$")


def _boot_time():
    for line in Path("/proc/stat").read_text().splitlines():
        if line.startswith("btime "):
            return int(line.split()[1])
    return 0


def _process(pid):
    proc = Path("/proc", str(pid))
    try:
        command = proc.joinpath("cmdline").read_bytes().split(b"\0")
        command = [c.decode(errors="replace") for c in command if c]
        uid = proc.stat().st_uid
        stat = proc.joinpath("stat").read_text()
        start_ticks = int(stat[stat.rindex(")") + 2 :].split()[19])  # field 22 counted from pid
    except (OSError, ValueError, IndexError):
        return None
    try:
        user = pwd.getpwuid(uid).pw_name
    except KeyError:
        user = str(uid)
    since = datetime.fromtimestamp(_boot_time() + start_ticks / os.sysconf("SC_CLK_TCK"), UTC)
    report, mount_user = "", ""
    for arg in command:
        m = _JUNIT_RE.search(arg)
        if m:
            mount_user, report = m.group(1) or "", m.group(2)
    return Holder(pid, user, since, command, report, mount_user)


def lock_state(lock_dir, lock, proc_locks="/proc/locks"):
    """Who holds <lock_dir>/<lock>.lock (as taken by run_poc.sh's flock), and how many wait."""
    path = Path(lock_dir, f"{lock}.lock")
    try:
        st = path.stat()
    except OSError:
        return LockState(path, False, None, 0)
    want = (os.major(st.st_dev), os.minor(st.st_dev), st.st_ino)
    holder, waiting = None, 0
    try:
        lines = Path(proc_locks).read_text().splitlines()
    except OSError:
        lines = []
    for line in lines:
        m = _LOCK_LINE.match(line)
        if not m or (int(m.group(3), 16), int(m.group(4), 16), int(m.group(5))) != want:
            continue
        if m.group(1):
            waiting += 1
        elif holder is None:
            holder = _process(int(m.group(2)))
    return LockState(path, True, holder, waiting)


def memory():
    """(available bytes, total bytes) from /proc/meminfo."""
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, value = line.partition(":")
        info[key] = int(value.split()[0]) * 1024
    return info.get("MemAvailable", 0), info.get("MemTotal", 0)


@dataclass
class TargetState:
    kind: str  # stopped | busy | yours | ready | unknown
    text: str


def target_state(container, lock, docker_error=None, me=None):
    """Container, lock and run state merged into the one state that matters most (design §6.1)."""
    me = me or pwd.getpwuid(os.getuid()).pw_name
    if docker_error:
        return TargetState("unknown", "Can't reach Docker")
    if container is None:
        return TargetState("stopped", "No container (ask the testbed admin)")
    if container["state"] != "running":
        return TargetState("stopped", "Container stopped (ask the testbed admin)")
    if lock.holder:
        when = lock.holder.since.astimezone().strftime("%H:%M") if lock.holder.since else "?"
        queued = f" · {lock.waiting} waiting" if lock.waiting else ""
        if lock.holder.who == me:
            return TargetState("yours", f"Busy: your CLI run since {when}{queued}")
        return TargetState("busy", f"Busy: {lock.holder.who}'s CLI run since {when}{queued}")
    return TargetState("ready", "Ready")
