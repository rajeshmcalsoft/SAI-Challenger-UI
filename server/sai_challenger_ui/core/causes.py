"""Causes: failures, errors and gaps grouped by why they happened (Allure's Categories, design §4 F2).

Two families, as Allure keeps "product errors" apart from "test errors":
- Target behaviour: Fail, Expected gap and Gap now passes.
- Test or setup problems: setup and cleanup errors.
Inside a family, tests are grouped by cause, taken from the message text in this order: a hints.toml signature, the
SAI status the target returned, a packet that did or didn't arrive, else the message's first line.
"""
import re
from dataclasses import dataclass, field

from .vocab import Result

TARGET = (Result.FAIL, Result.EXPECTED_GAP, Result.GAP_PASSES)
SETUP = (Result.SETUP_ERROR, Result.CLEANUP_ERROR)
FAMILY_TITLE = {"target": "Target behaviour", "setup": "Test or setup problems"}

_STATUS = re.compile(r"SAI_STATUS_[A-Z_]+")
_EQ = re.compile(r"assert '(SAI_STATUS_[A-Z_.]+)' == '(SAI_STATUS_[A-Z_.]+)'")
_NE = re.compile(r"assert '(SAI_STATUS_[A-Z_]+)' != '(SAI_STATUS_[A-Z_]+)'")
_DIFF = re.compile(r"^\s*-\s*(SAI_STATUS_[A-Z_]+)\s*$\n^\s*\+\s*(SAI_STATUS_[A-Z_]+)\s*$", re.MULTILINE)
# Gap reasons name the status without the prefix: "Duplicate VLAN returns INVALID_PARAMETER, expected ..."
_RETURNS = re.compile(r"\breturn(?:s|ed)?\s+(?:SAI_STATUS_)?([A-Z][A-Z_]{3,})")
_ACCEPTS = re.compile(r"(?i)\baccept(?:s|ed)?\b")
_NUM = re.compile(r"\b(0x[0-9a-f]+|\d+)\b", re.IGNORECASE)


@dataclass
class Cause:
    id: str
    title: str
    family: str  # target | setup
    kind: str  # hint | status | packet | message
    keys: list = field(default_factory=list)  # test keys, run order
    counts: dict = field(default_factory=dict)  # Result -> n


def _returned(message, detail):
    text = f"{message}\n{detail}"
    diff = _DIFF.search(text)
    if diff:
        return diff.group(2)
    eq = _EQ.search(text)
    if eq:
        return eq.group(1)
    ne = _NE.search(text)
    if ne:
        return ne.group(1)
    found = set(_STATUS.findall(message))
    if len(found) == 1:
        return found.pop()
    m = _RETURNS.search(message)
    if m:
        return "SAI_STATUS_" + m.group(1).removeprefix("SAI_STATUS_")
    return None


def cause_of(t, hints):
    """(id, title, kind) for one result."""
    hint = hints.match(t.result, t.message, t.detail) if t.result is not Result.GAP_PASSES else None
    if hint:
        return f"hint:{hint.id}", hint.title or hint.text.split(". ")[0].rstrip("."), "hint"
    if "expected not to receive" in t.message or "expected no packets" in t.message:
        return "packet:unexpected", "A packet arrived where none was expected", "packet"
    if "Expected packet was not received" in t.message:
        return "packet:missing", "Expected packet did not arrive", "packet"
    first_line = (t.message.splitlines() or [""])[0]
    if _ACCEPTS.search(first_line) and not _STATUS.search(first_line):
        return "accepts", "Accepts what the spec refuses", "status"
    # The status the message names: sometimes the one returned, sometimes the one the spec wants, so the title is
    # just the status.
    status = _returned(t.message, t.detail)
    if status:
        return f"status:{status}", status, "status"
    if t.result is Result.GAP_PASSES:
        return "gap:passes", "The target now passes what the gap records", "message"
    first = (t.message.splitlines() or [""])[0].strip()
    if not first:
        return "message:none", "No message", "message"
    norm = _NUM.sub("N", first)[:120]
    return f"message:{norm}", first[:120], "message"


def build(run, hints):
    """[Cause], most tests first, target behaviour before setup problems."""
    found = {}
    for t in run.tests:
        if t.upstream or t.result not in TARGET + SETUP:
            continue
        family = "target" if t.result in TARGET else "setup"
        cid, title, kind = cause_of(t, hints)
        c = found.setdefault((family, cid), Cause(cid, title, family, kind))
        c.keys.append(t.key)
        c.counts[t.result] = c.counts.get(t.result, 0) + 1
    order = {"target": 0, "setup": 1}
    return sorted(found.values(), key=lambda c: (order[c.family], -len(c.keys), c.title))
