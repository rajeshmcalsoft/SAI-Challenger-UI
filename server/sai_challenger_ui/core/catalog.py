"""Test catalogue built by reading tests/poc/test_*.py with ast: nothing is imported or run.

Gives each test a track, level, kind, readable title, parameter variants and, for step scenarios,
the steps and what each one needs. Parameter IDs that can't be worked out from the source (values
taken from a data file) are filled in from report history by merge_history().
"""
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

TRACKS = {
    "l2": "A · L2 & VLANs",
    "l3": "B · L3 routing",
    "acl": "C · ACL",
    "counters": "C · Counters",
}
FRAMEWORK = "Framework"
TRACK_ORDER = (TRACKS["l2"], TRACKS["l3"], TRACKS["acl"], TRACKS["counters"], FRAMEWORK, "Other")
TRACK_LETTER = {TRACKS["l2"]: "A", TRACKS["l3"]: "B", TRACKS["acl"]: "C", TRACKS["counters"]: "C", FRAMEWORK: "F",
                "Upstream": "U", "Other": "?"}
TRACK_TAG = {TRACKS["l2"]: "L2", TRACKS["l3"]: "L3", TRACKS["acl"]: "ACL", TRACKS["counters"]: "Counters",
             FRAMEWORK: "Framework", "Upstream": "Upstream", "Other": "Other"}

# Unit tests of the PoC's own helpers, not of a target (design §6.7).
_FRAMEWORK_MODULES = {"test_poc_mld_filter"}

_WORDS = {
    "acl": "ACL", "arp": "ARP", "dst": "destination", "fdb": "FDB", "fwd": "forward", "icmp": "ICMP",
    "id": "ID", "ip": "IP", "ipv4": "IPv4", "ipv6": "IPv6", "l2": "L2", "l3": "L3", "lag": "LAG",
    "attr": "attribute", "mac": "MAC", "mld": "MLD", "mtu": "MTU", "nh": "next hop", "nhg": "next-hop group",
    "oid": "OID", "pvid": "PVID",
    "exp": "experiment", "readback": "read back", "rif": "RIF", "sai": "SAI", "src": "source", "stp": "STP", "tcp": "TCP",
    "ttl": "TTL", "udp": "UDP", "vlan": "VLAN", "vrf": "VRF",
}
# "l2"/"l3" say nothing a reader needs; "acl"/"counters" are the subject, so they stay.
_PREFIX_RE = re.compile(r"^test_(?:poc_)?(?:(?:l2|l3)_)?")
_JOIN = ((" create remove", " create and remove"), (" create read back", " create and read back"))
_STEP_RE = re.compile(r"^test_(?:poc_\w+?_)?(\d{2})_")


def _phrase(snake):
    text = " ".join(_WORDS.get(w.lower(), w) for w in snake.split("_") if w)
    for old, new in _JOIN:
        text = text.replace(old, new)
    return text


def _capital(text):
    return text[:1].upper() + text[1:]


def readable(name):
    """'test_poc_l3_vrf_create_readback' -> 'VRF create read back'; 'test_07_drop_port' -> 'Step 07: drop port'."""
    base = name.split("[", 1)[0]
    step = _STEP_RE.match(base)
    if step:
        return f"Step {step.group(1)}: {_phrase(base[step.end():]) or base}"
    return _capital(_phrase(_PREFIX_RE.sub("", base)) or base)


@dataclass
class CatalogTest:
    module: str
    cls: str | None
    name: str  # function name, no parameters
    line: int
    markers: list
    track: str
    doc: str | None
    variants: list | None = None  # parameter IDs, or None when the test isn't parametrised
    step: dict | None = None  # {"name": ..., "needs": [...]} for @step(...) scenario tests
    ports_needed: int | None = None  # largest n in poc_ports(n)

    @property
    def title(self):
        return readable(self.name)

    @property
    def purpose(self):
        return self.doc.strip() if self.doc else None

    @property
    def level(self):
        return "L2 traffic" if "traffic" in self.markers else "L1"

    @property
    def kind(self):
        return "negative" if "negative" in self.markers else "positive"

    @property
    def names(self):
        """pytest item names this test produces: what expected_gaps patterns are matched against."""
        if self.variants is None:
            return [self.name]
        return [f"{self.name}[{v}]" for v in self.variants]


@dataclass
class Scenario:
    """Tests that run as ordered steps sharing state; shown as one row (design §6.4)."""
    module: str
    cls: str | None
    title: str
    doc: str | None
    steps: list = field(default_factory=list)  # CatalogTest, in file order


@dataclass
class Catalogue:
    tests: list = field(default_factory=list)
    scenarios: list = field(default_factory=list)
    problems: list = field(default_factory=list)  # files that couldn't be parsed

    def find(self, module, cls, base):
        for t in self.tests:
            if t.module == module and t.cls == cls and t.name == base:
                return t
        return None

    def all_names(self):
        return [n for t in self.tests for n in t.names]

    def scenario_of(self, test):
        for s in self.scenarios:
            if test in s.steps:
                return s
        return None


def _mark_name(node):
    """'pytest.mark.l2' or 'pytest.mark.parametrize(...)' -> 'l2' / 'parametrize'."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) and node.value.attr == "mark":
        return node.attr
    return None


def _module_marks(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            values = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
            return [m for m in (_mark_name(v) for v in values) if m]
    return []


def _param_id(value, argname, index):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return str(value)
    return f"{argname}{index}"


def _variants(call):
    """IDs pytest would give a literal @pytest.mark.parametrize, or None if they can't be known statically."""
    if len(call.args) < 2:
        return None
    try:
        argnames = ast.literal_eval(call.args[0])
    except ValueError:
        return None
    names = [a.strip() for a in argnames.split(",")] if isinstance(argnames, str) else list(argnames)
    for kw in call.keywords:
        if kw.arg == "ids":
            try:
                return [str(i) for i in ast.literal_eval(kw.value)]
            except ValueError:
                return None
    if not isinstance(call.args[1], (ast.List, ast.Tuple)):
        return None
    ids = []
    for index, element in enumerate(call.args[1].elts):
        if isinstance(element, ast.Call) and getattr(element.func, "attr", "") == "param":
            given = [kw.value for kw in element.keywords if kw.arg == "id"]
            if given and isinstance(given[0], ast.Constant):
                ids.append(str(given[0].value))
                continue
            element = ast.Tuple(element.args) if len(names) > 1 else (element.args[0] if element.args else element)
        try:
            value = ast.literal_eval(element)
        except ValueError:
            value = object()
        if len(names) > 1 and isinstance(value, (tuple, list)):
            ids.append("-".join(_param_id(v, n, index) for v, n in zip(value, names)))
        else:
            ids.append(_param_id(value, names[0], index))
    return ids


def _step(decorator):
    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == "step":
        try:
            name = ast.literal_eval(decorator.args[0]) if decorator.args else ""
            needs = next((ast.literal_eval(k.value) for k in decorator.keywords if k.arg == "needs"), [])
            if not needs and len(decorator.args) > 1:
                needs = ast.literal_eval(decorator.args[1])
            return {"name": name, "needs": list(needs)}
        except ValueError:
            return {"name": "?", "needs": []}
    return None


def _ports_needed(func):
    sizes = [
        n.args[0].value
        for n in ast.walk(func)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "poc_ports"
        and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, int)
    ]
    return max(sizes) if sizes else None


def step_number(name):
    """'test_poc_acl_drop_06_drop_port_is_dropped' -> '06', or None."""
    m = _STEP_RE.match(name)
    return m.group(1) if m else None


def track_for(module, markers=()):
    return _track(module, list(markers))


def _track(module, markers):
    if module in _FRAMEWORK_MODULES:
        return FRAMEWORK
    for marker in markers:
        if marker in TRACKS:
            return TRACKS[marker]
    for key, track in TRACKS.items():  # files without markers, e.g. test_acl_drop_exp.py
        if f"_{key}" in module:
            return track
    return "Other"


def _test(module, cls, func, inherited):
    markers = list(inherited)
    variants, step = None, None
    for d in func.decorator_list:
        name = _mark_name(d)
        if name == "parametrize" and isinstance(d, ast.Call):
            v = _variants(d)
            variants = v if v is not None else []  # [] = parametrised, IDs unknown until history fills them
        elif name:
            markers.append(name)
        step = step or _step(d)
    return CatalogTest(
        module, cls, func.name, func.lineno, markers, _track(module, markers),
        ast.get_docstring(func), variants, step, _ports_needed(func),
    )


def build(poc_dir):
    """Read every tests/poc/test_*.py in file order."""
    cat = Catalogue()
    for path in sorted(Path(poc_dir).glob("test_*.py")):
        module = path.stem
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except (OSError, SyntaxError) as exc:
            cat.problems.append(f"{path.name}: {exc}")
            continue
        marks = _module_marks(tree)
        loose = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                t = _test(module, None, node, marks)
                cat.tests.append(t)
                loose.append(t)
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                class_marks = marks + [m for m in (_mark_name(d) for d in node.decorator_list) if m]
                steps = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_"):
                        t = _test(module, node.name, item, class_marks)
                        cat.tests.append(t)
                        steps.append(t)
                if steps and any(t.step for t in steps):
                    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", node.name[4:]).lower().removeprefix("poc_")
                    title = _capital(_phrase(snake)) + " scenario"  # TestPocAclDrop -> "ACL drop scenario"
                    cat.scenarios.append(Scenario(module, node.name, title, ast.get_docstring(node), steps))
        numbered = [t for t in loose if _STEP_RE.match(t.name)]
        if len(numbered) >= 3 and len(numbered) == len(loose):  # e.g. test_acl_drop_exp.py: test_01_ ... test_14_
            title = _capital(_phrase(module.removeprefix("test_").removeprefix("poc_")))  # "ACL drop experiment"
            cat.scenarios.append(Scenario(module, None, title, ast.get_docstring(tree), numbered))
    return cat


def merge_history(cat, runs):
    """Fill in parameter IDs that only reports know (values from data files), newest run first."""
    for t in cat.tests:
        if t.variants != []:
            continue
        seen = []
        for run in runs:
            for r in run.tests:
                same = not r.upstream and r.module == t.module and r.cls == t.cls and r.base == t.name
                if same and r.param and r.param not in seen:
                    seen.append(r.param)
            if seen:
                break
        t.variants = seen
