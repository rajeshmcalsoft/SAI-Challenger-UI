"""Plain words for a result: what happened, and the hint for a known failure signature."""
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .vocab import Result

_STATUS = r"(SAI_STATUS_[A-Z_]+)"
_EQ = re.compile(r"assert '(SAI_STATUS_[A-Z_.]+)' == '(SAI_STATUS_[A-Z_.]+)'")
_NE = re.compile(r"assert '(SAI_STATUS_[A-Z_]+)' != '(SAI_STATUS_[A-Z_]+)'")
# pytest's diff under an == assertion: "- expected" then "+ actual", untruncated.
_DIFF = re.compile(r"^\s*-\s*(SAI_STATUS_[A-Z_]+)\s*$\n^\s*\+\s*(SAI_STATUS_[A-Z_]+)\s*$", re.MULTILINE)


def what_happened(result, message, detail=""):
    """One sentence in plain words, or None when the message has nothing to say plainly."""
    if result is Result.GAP_PASSES:
        return f"The test passed, but it is recorded as an expected gap: {message}" if message else "The test passed."
    if result not in (Result.FAIL, Result.SETUP_ERROR, Result.CLEANUP_ERROR):
        return None
    text = f"{message}\n{detail}"
    diff = _DIFF.search(text)
    eq = _EQ.search(text)
    if diff or eq:
        expected, actual = (diff.group(1), diff.group(2)) if diff else (eq.group(2), eq.group(1))
        return f"The target returned {actual}. The SAI spec expects {expected}."
    ne = _NE.search(text)
    if ne:
        return f"The target returned {ne.group(1)}, which the test must not get here."
    if "expected no packets" in message:
        port = re.search(r"port (\d+)", message)
        return f"A packet arrived on port {port.group(1) if port else '?'} where none was expected."
    if "Expected packet was not received" in message:
        port = re.search(r"port (\d+)", message)
        return f"The expected packet did not arrive on port {port.group(1) if port else '?'}."
    statuses = re.findall(_STATUS, message)
    if len(set(statuses)) == 1:
        return f"The target returned {statuses[0]}."
    return None


_E_LINE = re.compile(r"^E\s{1,12}(.*)$")
_ASSERT_EQ = re.compile(r"assert '((?:[^'\\]|\\.)*)' == '((?:[^'\\]|\\.)*)'")
_RETURNS_EXPECTED = re.compile(r"returns? (?:SAI_STATUS_)?([A-Z][A-Z_]{3,}),? expected (?:SAI_STATUS_)?([A-Z][A-Z_]{3,})")


def expected_actual(message, detail=""):
    """(expected, actual) when the text says both, for the diff viewer; else None.

    pytest writes an == assertion as "assert actual == expected" and, below it, a diff where "- " lines are the
    expected value and "+ " lines the actual one. Gap reasons say "returns X, expected Y"."""
    e_lines = [m.group(1) for m in map(_E_LINE.match, detail.splitlines()) if m]
    lines = e_lines or detail.splitlines()
    starts = [i for i, line in enumerate(lines) if "assert " in line and " == " in line]
    if not starts and "assert " in message and " == " in message:
        starts = [-1]  # the assertion is in the message; the diff lines follow in the detail
    for i in starts:
        minus, plus = [], []
        for follow in lines[i + 1:]:
            text = follow.strip()
            if text.startswith("- "):
                minus.append(text[2:])
            elif text.startswith("+ "):
                plus.append(text[2:])
            elif text and not text.startswith(("?", "Full diff", "At index", "Use -v", "Omitting", "...")) and (minus or plus):
                break
        if minus and plus:
            return "\n".join(minus), "\n".join(plus)
    eq = _ASSERT_EQ.search(message)
    if eq and "..." not in eq.group(0):
        return eq.group(2), eq.group(1)
    ret = _RETURNS_EXPECTED.search(message)
    if ret:
        return "SAI_STATUS_" + ret.group(2), "SAI_STATUS_" + ret.group(1)
    return None


@dataclass
class Hint:
    id: str
    text: str
    action: str
    title: str = ""  # a few words, used as the cause name on the Causes tab


class Hints:
    def __init__(self, path=None):
        path = Path(path) if path else Path(__file__).resolve().parent.parent / "hints.toml"
        with open(path, "rb") as f:
            entries = tomllib.load(f).get("hint", [])
        self.entries = [
            (re.compile(e["pattern"]), {Result(r) for r in e["results"]},
             Hint(e["id"], e["text"], e.get("action", ""), e.get("title", "")))
            for e in entries
        ]

    def match(self, result, message, detail=""):
        text = f"{message}\n{detail}"
        for pattern, results, hint in self.entries:
            if result in results and pattern.search(text):
                return hint
        return None
