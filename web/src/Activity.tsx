// The activity chip (design §5): shown only while UI runs are running or queued, plus a quiet toast, an optional
// browser notification and a screen-reader announcement when one ends.
import { Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useJobs, type JobSummary } from "./api";

type Toast = { id: string; text: string; to: { runId?: string; jobId?: string } };

function ended(j: JobSummary): Toast {
  const what = j.headline ?? (j.state === "removed" ? "not run" : "ended without a report");
  const set = j.setSize > 1 ? ` (run ${j.setIndex} of ${j.setSize})` : "";
  return { id: j.id, text: `${j.target}${set} finished: ${what}`, to: j.runId ? { runId: j.runId } : { jobId: j.id } };
}

export function Activity() {
  const jobs = useJobs();
  const seenActive = useRef(new Set<string>());
  const told = useRef(new Set<string>());
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    if (!jobs.data) return;
    for (const j of jobs.data.active) seenActive.current.add(j.id);
    for (const j of jobs.data.recent) {
      // Only runs this tab saw live, and only once the report is read (or there is none).
      if (!seenActive.current.has(j.id) || told.current.has(j.id) || j.reportPending || j.state === "removed") continue;
      told.current.add(j.id);
      const t = ended(j);
      setToasts((ts) => [...ts.filter((x) => x.id !== t.id), t]);
      setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== t.id)), 12000);
      if (j.notify && "Notification" in window && Notification.permission === "granted") {
        try { new Notification("SAI Conformance", { body: t.text, tag: j.id }); } catch { /* not supported here */ }
      }
    }
  }, [jobs.data]);

  const active = jobs.data?.active ?? [];
  const running = active.filter((j) => j.state === "running").length;
  const queued = active.length - running;
  return (
    <>
      {active.length > 0 && (
        <details className="menu activity">
          <summary className="chip">◷ {[running && `${running} running`, queued && `${queued} queued`].filter(Boolean).join(" · ")}</summary>
          <div className="menu-list right">
            {active.map((j) => (
              <Link key={j.id} to="/jobs/$jobId" params={{ jobId: j.id }} className="menu-item">
                <b>{j.target}</b> · {j.what}
                <span className="faint small"> · {j.state === "running" ? `${j.done} of ${j.total}${j.current ? ` · ${j.current}` : ""}` : "queued"}</span>
              </Link>
            ))}
          </div>
        </details>
      )}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="toast">
            <span>{t.text}</span>
            {t.to.runId
              ? <Link to="/runs/$runId" params={{ runId: t.to.runId }} onClick={() => setToasts((ts) => ts.filter((x) => x.id !== t.id))}>Open</Link>
              : <Link to="/jobs/$jobId" params={{ jobId: t.to.jobId! }} onClick={() => setToasts((ts) => ts.filter((x) => x.id !== t.id))}>Open</Link>}
            <button type="button" className="btn sm icon" aria-label="Dismiss" onClick={() => setToasts((ts) => ts.filter((x) => x.id !== t.id))}>✕</button>
          </div>
        ))}
      </div>
    </>
  );
}
