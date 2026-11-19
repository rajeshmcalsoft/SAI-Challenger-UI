"""What a run sheet asks for, turned into run_poc.sh arguments (design §6.3). Pure: nothing is started here.

Only values the server knows are used: targets from the profiles, markers from a fixed set, and tests from the
catalogue. Nothing a request carries goes into the command line unchecked, and no shell is ever involved.
"""
import shlex
from dataclasses import dataclass, field

from . import catalog, profiles
from .runview import ATTENTION

TRACK_MARKERS = ("l2", "l3", "acl", "counters")  # pytest -m, never free text
MLD_MODES = ("auto", "on", "off")
PRESETS = ("full", "tracks", "failures", "pick")
MAX_REPEAT = 5
MAX_RETRIES = 3
RUN_POC = "scripts/poc/run_poc.sh"


class BadRequest(ValueError):
    """A request the sheet should never send: unknown target, test or option."""


@dataclass
class Request:
    targets: list
    what: str = "full"
    tracks: list = field(default_factory=list)
    tests: list = field(default_factory=list)  # catalogue keys: module::cls::name, name with or without [param]
    traffic: bool = True
    mld: str = "auto"
    repeat: int = 1
    notify: bool = False
    retries: int = 0  # rerun what fails (Fail, setup or cleanup error) up to this many times, only those tests

    @classmethod
    def from_json(cls, body):
        if not isinstance(body, dict):
            raise BadRequest("expected a JSON object")

        def strings(key):
            value = body.get(key, [])
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise BadRequest(f"{key} must be a list of strings")
            return list(dict.fromkeys(value))

        what = body.get("what", "full")
        mld = body.get("mld", "auto")
        repeat = body.get("repeat", 1)
        if what not in PRESETS:
            raise BadRequest(f"what must be one of {', '.join(PRESETS)}")
        if mld not in MLD_MODES:
            raise BadRequest(f"mld must be one of {', '.join(MLD_MODES)}")
        if not isinstance(repeat, int) or isinstance(repeat, bool) or not 1 <= repeat <= MAX_REPEAT:
            raise BadRequest(f"repeat must be 1 to {MAX_REPEAT}")
        retries = body.get("retries", 0)
        if not isinstance(retries, int) or isinstance(retries, bool) or not 0 <= retries <= MAX_RETRIES:
            raise BadRequest(f"retries must be 0 to {MAX_RETRIES}")
        tracks = strings("tracks")
        bad = [t for t in tracks if t not in TRACK_MARKERS]
        if bad:
            raise BadRequest(f"unknown track {bad[0]}")
        return cls(strings("targets"), what, tracks, strings("tests"), bool(body.get("traffic", True)), mld, repeat,
                   bool(body.get("notify", False)), retries)


@dataclass
class Planned:
    """One target's part of a request: the command and what it will run."""
    target: str
    args: list  # run_poc.sh arguments after the profile name
    command: str  # what "Show command" prints; the same line works from the checkout in a terminal
    what: str  # "Full PoC suite", "Tracks: L2 + L3", "Last run's failures", "4 picked tests"
    expected: list  # test keys in run order; a name without [param] stands for all its variants
    count: int  # tests (with parameter variants) the run should report
    gaps: int  # of those, how many the profile records as expected gaps
    traffic: bool  # --traffic is passed
    traffic_tests: int  # selected tests marked traffic
    traffic_note: str  # the sentence shown instead of a toggle, or ""
    mld: str  # auto | on | off, as passed
    mld_relevant: bool  # traffic is on and traffic tests are selected: the MLD choice matters
    estimate: float | None  # seconds, from the newest run of each selected test on this target
    warnings: list = field(default_factory=list)
    blocked: str = ""  # why this target can't run now (container stopped); empty when it can


def mount_name(user):
    """The folder name tests/poc has inside the containers: poc_<user>, as in run_poc.sh."""
    return f"poc_{user}"


def _variant_names(t):
    if t.variants:
        return [f"{t.name}[{v}]" for v in t.variants]
    return [t.name]  # not parametrised, or variants unknown until a report names them


def _key(t, name):
    return "::".join(p for p in (t.module, t.cls, name) if p)


def _resolve(cat, keys):
    """Catalogue keys -> {(catalogue index, variant index or -1): (test, name)}. Unknown keys raise BadRequest."""
    index = {_key(t, t.name): (i, t) for i, t in enumerate(cat.tests)}
    chosen, unknown_variant = {}, 10_000
    for key in keys:
        base, _, rest = key.partition("[")
        found = index.get(base)
        if found is None:
            raise BadRequest(f"no test {key} in the catalogue")
        i, t = found
        if not rest:
            chosen[(i, -1)] = (t, t.name)
            continue
        param = rest[:-1] if rest.endswith("]") else None
        if param is None or t.variants is None or (t.variants and param not in t.variants):
            raise BadRequest(f"no variant {key} in the catalogue")
        if t.variants:
            j = t.variants.index(param)
        else:  # parametrised, IDs not known from source or history: keep the order given
            j, unknown_variant = unknown_variant, unknown_variant + 1
        chosen[(i, j)] = (t, f"{t.name}[{param}]")
    # A whole test wins over single variants of it.
    whole = {i for (i, j) in chosen if j == -1}
    return {k: v for k, v in chosen.items() if k[1] == -1 or k[0] not in whole}


def _with_needs(cat, chosen):
    """Add the scenario steps that picked steps need (@step(..., needs=[...])), recursively."""
    added = []
    position = {id(t): i for i, t in enumerate(cat.tests)}
    for sc in cat.scenarios:
        by_step = {t.step["name"]: t for t in sc.steps if t.step}
        picked = [t for t, _ in chosen.values() if t in sc.steps]
        todo = [n for t in picked if t.step for n in t.step["needs"]]
        seen = set()
        while todo:
            need = todo.pop()
            if need in seen or need not in by_step:
                continue
            seen.add(need)
            t = by_step[need]
            key = (position[id(t)], -1)
            if not any(k[0] == key[0] for k in chosen):
                chosen[key] = (t, t.name)
                added.append((sc, t))
            todo += t.step["needs"]
    return added


def _node(mount, t, name):
    return "::".join(p for p in (f"{mount}/{t.module}.py", t.cls, name) if p)


def _arguments(cat, mount, chosen):
    """Node IDs in file order, folded into a file (or the whole folder) where every test of it is chosen."""
    picked = sorted(chosen)
    modules = list(dict.fromkeys(t.module for t in cat.tests))
    whole_tests = {i for i, j in picked if j == -1}
    full_modules = [m for m in modules
                    if all(i in whole_tests for i, t in enumerate(cat.tests) if t.module == m)]
    if modules and len(full_modules) == len(modules) and not cat.problems:
        return [mount]
    args, done_modules = [], set()
    for i, j in picked:
        t, name = chosen[(i, j)]
        if t.module in full_modules:
            if t.module not in done_modules:
                args.append(f"{mount}/{t.module}.py")
                done_modules.add(t.module)
            continue
        args.append(_node(mount, t, name))
    return args


def _expected(chosen):
    out = []
    for key in sorted(chosen):
        t, name = chosen[key]
        if name == t.name:
            out += [_key(t, n) for n in _variant_names(t)]
        else:
            out.append(_key(t, name))
    return out


def _count_names(chosen):
    return [k.rsplit("::", 1)[-1] for k in _expected(chosen)]


def _durations(runs, target):
    """{test key: seconds} from the newest run of each test on the target."""
    out = {}
    for run in runs:
        if run.target != target:
            continue
        for t in run.tests:
            out.setdefault(t.key, t.seconds)
    return out


def _estimate(keys, durations):
    known = [durations[k] for k in keys if k in durations]
    if not known:
        return None
    typical = sorted(known)[len(known) // 2]
    return sum(durations.get(k, typical) for k in keys) + 15.0  # container exec and session setup


def known_keys(cat, keys):
    """The keys the catalogue still knows (a test may have been renamed since the run)."""
    out = []
    for k in keys:
        try:
            _resolve(cat, [k])
            out.append(k)
        except BadRequest:
            pass
    return out


def _failures(latest):
    if latest is None:
        return []
    return [t.key for t in latest.tests if t.result in ATTENTION and not t.upstream]


def _choose(req, cat, latest):
    """{position: (test, name)}, the 'what' text and extra pytest arguments for one target."""
    if req.what == "full":
        return {(i, -1): (t, t.name) for i, t in enumerate(cat.tests)}, "Full PoC suite", []
    if req.what == "tracks":
        if not req.tracks:
            raise BadRequest("pick at least one track")
        marks = [m for m in TRACK_MARKERS if m in req.tracks]
        chosen = {(i, -1): (t, t.name) for i, t in enumerate(cat.tests) if set(t.markers) & set(marks)}
        label = " + ".join(catalog.TRACK_TAG[catalog.TRACKS[m]] for m in marks)
        return chosen, f"Tracks: {label}", ["-m", " or ".join(marks)]
    if req.what == "failures":
        keys = [k for k in _failures(latest) if not k.endswith("::(collection)")]
        known = []
        for k in keys:
            try:
                _resolve(cat, [k])
                known.append(k)
            except BadRequest:  # the test was renamed or removed since that run
                pass
        return _resolve(cat, known), "Last run's failures", []
    if not req.tests:
        raise BadRequest("pick at least one test")
    chosen = _resolve(cat, req.tests)
    return chosen, "", []


def plan(req, cat, profs, forwards, latest, runs, user, blocked=None):
    """[Planned] per target, in the order given. forwards(name) -> True/False/None; latest(name) -> Run or None;
    blocked(name) -> reason or ''."""
    if not req.targets:
        raise BadRequest("pick at least one target")
    unknown = [t for t in req.targets if t not in profs]
    if unknown:
        raise BadRequest(f"no target profile {unknown[0]}")
    mount = mount_name(user)
    out = []
    for name in req.targets:
        prof = profs[name]
        chosen, what, extra = _choose(req, cat, latest(name))
        warnings = []
        if req.what == "failures" and not chosen:
            warnings.append(f"The last run on {name} has no failures to rerun.")
        added = _with_needs(cat, chosen) if req.what in ("pick", "failures") else []
        if added:
            by_sc = {}
            for sc, t in added:
                by_sc.setdefault(sc.title, []).append(catalog.step_number(t.name) or t.name)
            for title, steps in by_sc.items():
                steps = sorted(steps)
                listed = ", ".join(steps[:-1]) + f" and {steps[-1]}" if len(steps) > 1 else steps[0]
                warnings.append(f"{title}: added step{'s' if len(steps) > 1 else ''} {listed}, which the picked "
                                "steps need.")
        names = _count_names(chosen)
        traffic_tests = sum(len(_variant_names(t)) if n == t.name else 1
                            for t, n in chosen.values() if "traffic" in t.markers)
        fwd = forwards(name)
        traffic = bool(req.traffic) and fwd is True
        note = ""
        if traffic_tests and fwd is False:
            note = f"{name} doesn't forward packets: its {traffic_tests} traffic test{'s' if traffic_tests != 1 else ''} will be skipped."
        elif traffic_tests and fwd is None:
            note = f"Not known whether {name} forwards packets, so traffic stays off: {traffic_tests} traffic tests will be skipped."
        elif traffic_tests and not traffic:
            note = f"Traffic off: {traffic_tests} traffic test{'s' if traffic_tests != 1 else ''} will be skipped."
        mld_relevant = traffic and traffic_tests > 0
        mld = req.mld if mld_relevant else "auto"

        if req.what == "pick" or req.what == "failures":
            args = _arguments(cat, mount, chosen) if chosen else []
        else:
            args = [mount]
        args += extra
        if traffic:
            args.append("--traffic")
        if mld != "auto":
            args += ["--mld-filter", mld]
        if not what:
            n = len(names)
            what = f"{n} picked test{'s' if n != 1 else ''}"
        keys = _expected(chosen)
        gaps = sum(1 for n in names if profiles.gap_for(n, prof.expected_gaps))
        out.append(Planned(
            target=name, args=args, command=shlex.join([RUN_POC, name, *args]), what=what, expected=keys,
            count=len(names), gaps=gaps, traffic=traffic, traffic_tests=traffic_tests, traffic_note=note, mld=mld,
            mld_relevant=mld_relevant, estimate=_estimate(keys, _durations(runs, name)), warnings=warnings,
            blocked=(blocked(name) if blocked else "") or ("" if chosen else "Nothing to run"),
        ))
    return out
