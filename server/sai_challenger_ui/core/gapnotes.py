"""What kind of gap each expected gap is (Allure's resolutions, design §4 F1), kept in the UI's own config folder.

The profiles in SAI-Challenger stay as they are: the conftest reads only `expected_gaps` (pattern -> reason). These
notes add, per target and pattern:
- kind: limitation (the target can't or won't do it: the default), bug (a known bug, with a link to it) or
  temporary (expected to be fixed by a date; after it, the gap shows as overdue for review);
- link: an http(s) address (issue, vendor ticket), optional;
- until: YYYY-MM-DD, for temporary gaps.
Moving them into the profiles later would be a change to SAI-Challenger, and waits for the owner's request.
"""
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

KINDS = ("limitation", "bug", "temporary")
KIND_TEXT = {"limitation": "Limitation", "bug": "Known bug", "temporary": "Temporary"}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_URL = re.compile(r"^https?://[^\s<>\"']{1,500}$")


@dataclass
class Note:
    kind: str = "limitation"
    link: str = ""
    until: str = ""
    by: str = ""
    at: str = ""
    recorded: bool = False  # False: no note yet, the default kind is shown

    def state(self, today=None):
        """ok | overdue (a temporary gap past its date) | no_date (temporary without one)."""
        if self.kind != "temporary":
            return "ok"
        if not self.until:
            return "no_date"
        return "overdue" if date.fromisoformat(self.until) < (today or date.today()) else "ok"


class BadNote(ValueError):
    pass


def _path(config_dir):
    return Path(config_dir) / "gap_notes.json"


def load(config_dir):
    try:
        data = json.loads(_path(config_dir).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def get(notes, target, pattern):
    raw = (notes.get(target) or {}).get(pattern)
    if not isinstance(raw, dict):
        return Note()
    kind = raw.get("kind") if raw.get("kind") in KINDS else "limitation"
    until = raw.get("until") if isinstance(raw.get("until"), str) and _DATE.match(raw.get("until")) else ""
    link = raw.get("link") if isinstance(raw.get("link"), str) and _URL.match(raw.get("link")) else ""
    return Note(kind, link, until, str(raw.get("by", "")), str(raw.get("at", "")), True)


def save(config_dir, target, pattern, kind, link="", until="", by=""):
    if kind not in KINDS:
        raise BadNote(f"kind must be one of {', '.join(KINDS)}")
    link = (link or "").strip()
    if link and not _URL.match(link):
        raise BadNote("the link must start with http:// or https://")
    until = (until or "").strip()
    if until:
        if not _DATE.match(until):
            raise BadNote("the date must be YYYY-MM-DD")
        try:
            date.fromisoformat(until)
        except ValueError as exc:
            raise BadNote(f"not a date: {until}") from exc
    notes = load(config_dir)
    note = Note(kind, link, until if kind == "temporary" else "", by, datetime.now(UTC).isoformat(timespec="seconds"),
                True)
    entry = {k: v for k, v in asdict(note).items() if k != "recorded"}
    notes.setdefault(target, {})[pattern] = entry
    path = _path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(notes, indent=1, sort_keys=True))
    os.replace(tmp, path)
    return note


def as_dict(note, today=None):
    return {"kind": note.kind, "kindText": KIND_TEXT[note.kind], "link": note.link, "until": note.until,
            "by": note.by, "at": note.at, "recorded": note.recorded, "state": note.state(today)}
