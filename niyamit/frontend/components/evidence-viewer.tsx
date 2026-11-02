"use client";

import { useEffect, useState } from "react";

import type { Field, Proposal } from "@/lib/types";

/** The original document page with every proposed field outlined where it was read. */
export function EvidenceViewer({ proposal, activeField, onPick }: {
  proposal: Proposal; activeField: string | null; onPick: (fieldId: string) => void;
}) {
  const art = proposal.artifact;
  const pages = art?.mime_type === "application/pdf" ? art.page_count : 1;
  const active = proposal.fields.find((f) => f.id === activeField);
  const [page, setPage] = useState(active?.evidence.page ?? 1);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (active?.evidence.page) setPage(active.evidence.page);
  }, [active?.evidence.page]);

  if (!art) return null;
  if (!art.mime_type.startsWith("image/") && art.mime_type !== "application/pdf") {
    return (
      <div className="panel stack">
        <p>Spreadsheet rows are shown as text evidence next to each field.</p>
        <a href={`/api${art.content_url}`} target="_blank" rel="noreferrer">Download the original file</a>
      </div>
    );
  }
  const boxes = proposal.fields.flatMap((f: Field) =>
    (f.evidence.bboxes ?? []).filter((b) => b.page === page).map((b, i) => ({ field: f, bbox: b.bbox, key: `${f.id}-${i}` })),
  );
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="spread">
        <span className="small muted">Original document. Outlines show where each value was read.</span>
        <div className="row">
          {pages > 1 ? (
            <>
              <button className="btn btn--quiet btn--small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous page</button>
              <span className="small">Page {page} of {pages}</span>
              <button className="btn btn--quiet btn--small" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next page</button>
            </>
          ) : null}
          <a className="btn btn--ghost btn--small" href={`/api${art.content_url}`} target="_blank" rel="noreferrer">Open original</a>
        </div>
      </div>
      <div className="doc-view">
        {failed ? (
          <p className="notice notice--warn" style={{ margin: 16 }}>The page preview could not be loaded. Use “Open original”.</p>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={`/api${art.page_url.replace("{page}", String(page))}`} alt={`Page ${page} of ${art.filename}`} onError={() => setFailed(true)} />
        )}
        {!failed && boxes.map(({ field, bbox, key }) => (
          <span key={key} className={`bbox${field.id === activeField ? " bbox--active" : ""}`}
            style={{ left: `${bbox[0] * 100}%`, top: `${bbox[1] * 100}%`, width: `${(bbox[2] - bbox[0]) * 100}%`, height: `${(bbox[3] - bbox[1]) * 100}%` }}
            title={field.label} />
        ))}
      </div>
      <div className="row small">
        {proposal.fields.filter((f) => f.evidence.page === page).map((f) => (
          <button key={f.id} className="filter" aria-pressed={f.id === activeField} onClick={() => onPick(f.id)}>{f.label}</button>
        ))}
      </div>
    </div>
  );
}
