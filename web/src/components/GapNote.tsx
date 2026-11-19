// What kind of gap an expected gap is (F1, Allure's resolutions): Limitation, Known bug (with a link) or Temporary
// (with a date). Saved in the UI's own config folder; the target profile is never written.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { saveGapNote, useHealth, type GapNote } from "../api";
import { I } from "../icons";
import { KIND_HELP } from "../vocab";

export function KindLabel({ note }: { note: GapNote }) {
  if (note.state === "overdue") return <span className="kind overdue"><I.hourglass />Temporary · overdue since {note.until}</span>;
  if (note.kind === "bug") {
    return (
      <span className="kind bug"><I.bug />Known bug
        {note.link && <> · <a href={note.link} target="_blank" rel="noreferrer noopener">{note.link.replace(/^https?:\/\//, "").slice(0, 48)}</a></>}
      </span>
    );
  }
  if (note.kind === "temporary") return <span className="kind temporary"><I.hourglass />Temporary{note.until ? ` until ${note.until}` : " · no date set"}</span>;
  return <span className="kind limitation" title={note.recorded ? "" : "Not classified yet: shown as the default"}><I.diamond />Limitation{note.recorded ? "" : " (default)"}</span>;
}

export function GapNoteEditor({ target, pattern, note, compact = false }: { target: string; pattern: string; note: GapNote; compact?: boolean }) {
  const qc = useQueryClient();
  const health = useHealth();
  const [editing, setEditing] = useState(false);
  const [kind, setKind] = useState(note.kind);
  const [link, setLink] = useState(note.link);
  const [until, setUntil] = useState(note.until);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const canEdit = health.data?.mode === "local";
  async function save() {
    setBusy(true);
    setError("");
    try {
      await saveGapNote({ target, pattern, kind, link, until });
      await Promise.all([qc.invalidateQueries({ queryKey: ["gaps"] }), qc.invalidateQueries({ queryKey: ["run"] }),
        qc.invalidateQueries({ queryKey: ["detail"] })]);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  if (!editing) {
    return (
      <span className="row wrap" style={{ gap: 8 }}>
        <KindLabel note={note} />
        {canEdit && <button type="button" className="linkbtn small" onClick={() => setEditing(true)}>{compact ? "Edit" : "Change kind"}</button>}
      </span>
    );
  }
  return (
    <div>
      <div className="noteform">
        <select value={kind} onChange={(e) => setKind(e.target.value as GapNote["kind"])} aria-label="Kind of gap">
          <option value="limitation">Limitation</option>
          <option value="bug">Known bug</option>
          <option value="temporary">Temporary</option>
        </select>
        {kind !== "limitation" && (
          <input type="url" placeholder="https://… (issue or ticket, optional)" value={link} onChange={(e) => setLink(e.target.value)} aria-label="Link" />
        )}
        {kind === "temporary" && <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} aria-label="Review by" />}
        <button type="button" className="btn sm primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        <button type="button" className="btn sm ghost" onClick={() => { setEditing(false); setError(""); }}>Cancel</button>
      </div>
      <div className="faint xs" style={{ marginTop: 4 }}>{KIND_HELP[kind]} Saved in the UI's config folder, not in {target}.json.</div>
      {error && <div className="warn small">{error}</div>}
    </div>
  );
}
