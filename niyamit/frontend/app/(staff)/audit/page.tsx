"use client";

import Link from "next/link";
import { useState } from "react";

import { PageHead } from "@/components/staff-shell";
import { ErrorNote, Loading, Pill } from "@/components/ui";
import { useApi } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

type Event = {
  id: string; at: string; action: string; outcome: string; actor_type: string; actor_role: string; actor: string;
  object_type: string; object_id: string; patient_id: string | null; correlation_id: string; detail: Record<string, unknown>;
};

const FILTERS: [string, string][] = [
  ["", "Everything"], ["ACCESS_DENIED", "Denied access"], ["VIEW_PATIENT", "Record views"], ["VIEW_ORIGINAL_FILE", "File views"],
  ["PLAN_APPROVED", "Plan approvals"], ["BOOKING_COMMITTED", "Bookings"], ["LOGIN_FAILED", "Failed sign-ins"],
];

export default function AuditPage() {
  const [action, setAction] = useState("");
  const { data, error, loading } = useApi<{ masked: boolean; events: Event[] }>(`/v1/audit-events?limit=300${action ? `&action=${action}` : ""}`);
  return (
    <>
      <PageHead title="Audit log" lede="Who did what, when, with the request id that links it to the logs. Patient content is never stored here." />
      <div className="filters" role="group" aria-label="Filter events">
        {FILTERS.map(([k, label]) => <button key={k} className="filter" aria-pressed={action === k} onClick={() => setAction(k)}>{label}</button>)}
      </div>
      {data?.masked ? <p className="notice small" style={{ marginBottom: 12 }}>Platform support view: record ids and details are hidden.</p> : null}
      <ErrorNote error={error} />
      {loading && !data ? <Loading /> : null}
      {data ? (
        <div className="panel panel--flush">
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Record</th><th>Request id</th></tr></thead>
              <tbody>
                {data.events.map((e) => (
                  <tr key={e.id} className={e.outcome === "DENIED" ? "is-bad" : undefined}>
                    <td className="small nowrap">{fmtDateTime(e.at)}</td>
                    <td className="small">{e.actor}{e.actor_role ? <span className="muted" style={{ display: "block" }}>{e.actor_role.toLowerCase()}</span> : null}</td>
                    <td className="small">
                      {e.action.toLowerCase().replace(/_/g, " ")} {e.outcome === "DENIED" ? <Pill tone="fail">denied</Pill> : null}
                      {Object.keys(e.detail).length ? <span className="muted" style={{ display: "block" }}>{JSON.stringify(e.detail).slice(0, 140)}</span> : null}
                    </td>
                    <td className="small">
                      {e.object_type.replace(/_/g, " ")}
                      {e.patient_id ? <> <Link href={`/patients/${e.patient_id}`}>patient</Link></> : null}
                    </td>
                    <td className="small muted">{e.correlation_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </>
  );
}
