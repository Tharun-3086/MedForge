"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageHead } from "@/components/staff-shell";
import { ErrorNote, Loading, Pill, useAction } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import { useStaff } from "@/lib/staff-context";

type Status = { demo_mode: boolean; tasks_mode: string; faults: { key: string; label: string; enabled: boolean }[]; scenarios: { name: string; title: string }[] };
type Result = { name: string; title: string; passed: boolean; steps: { check: string; passed: boolean; detail: string }[]; ran_in: string; ran_at: string };

export default function TestPanelPage() {
  const router = useRouter();
  const { me } = useStaff();
  const { data, error, loading, setData } = useApi<Status>("/v1/demo/status");
  const { busy, run } = useAction();
  const [results, setResults] = useState<Record<string, Result>>({});
  const [running, setRunning] = useState<string | null>(null);
  const [tick, setTick] = useState<Record<string, number> | null>(null);

  async function runScenario(name: string) {
    setRunning(name);
    try {
      const r = await api<Result>(`/v1/demo/scenarios/${name}`, { method: "POST" });
      setResults((prev) => ({ ...prev, [name]: r }));
    } catch (e) {
      setResults((prev) => ({ ...prev, [name]: { name, title: name, passed: false, ran_in: "", ran_at: new Date().toISOString(),
        steps: [{ check: "Scenario could not run", passed: false, detail: e instanceof Error ? e.message : String(e) }] } }));
    } finally {
      setRunning(null);
    }
  }

  async function runAll() {
    for (const s of data?.scenarios ?? []) await runScenario(s.name);
  }

  async function toggle(key: string, enabled: boolean) {
    const r = await run(() => api<Status>("/v1/demo/faults", { body: { key, enabled } }), enabled ? "Fault switched on." : "Fault switched off.");
    if (r) setData(r);
  }

  async function reset() {
    if (!window.confirm("Wipe all demo data and load the original synthetic clinics again? Everyone will need to sign in again.")) return;
    const r = await run(() => api("/v1/demo/reset", { method: "POST" }), "Demo data reset. Sign in again.");
    if (r) router.replace("/login");
  }

  const done = Object.values(results);
  const passed = done.filter((r) => r.passed).length;

  return (
    <>
      <PageHead title="Test panel"
        lede="Run the failure cases the PRD requires and see each check the system made. Scenarios use a separate synthetic sandbox clinic, so they never change your worklist."
        actions={<>
          <button className="btn" disabled={Boolean(running) || !data} onClick={runAll}>Run all scenarios</button>
          {me.user.role === "ADMIN" ? <button className="btn btn--danger" disabled={busy} onClick={reset}>Reset demo data</button> : null}
        </>} />
      <ErrorNote error={error} />
      {loading && !data ? <Loading /> : null}
      {done.length > 0 ? (
        <p className={`notice ${passed === done.length ? "notice--ok" : "notice--fail"}`} style={{ marginBottom: 16 }} aria-live="polite">
          {passed} of {done.length} scenarios passed in this session{done.length < (data?.scenarios.length ?? 0) ? " so far" : ""}.
        </p>
      ) : null}

      <div className="cols-2">
        <section className="panel panel--flush">
          {data?.scenarios.map((s) => {
            const r = results[s.name];
            return (
              <div key={s.name} className="stack" style={{ padding: "14px 18px", borderTop: "1px solid var(--rule)", gap: 8 }}>
                <div className="spread">
                  <b>{s.title}</b>
                  <div className="row">
                    {r ? <Pill tone={r.passed ? "done" : "fail"}>{r.passed ? "Passed" : "Failed"}</Pill> : null}
                    <button className="btn btn--quiet btn--small" disabled={Boolean(running)} onClick={() => runScenario(s.name)}>
                      {running === s.name ? "Running…" : r ? "Run again" : "Run"}
                    </button>
                  </div>
                </div>
                {r ? (
                  <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", display: "grid", gap: 4 }}>
                    {r.steps.map((step, i) => (
                      <li key={i} className="small" style={{ display: "grid", gridTemplateColumns: "18px 1fr", gap: 6 }}>
                        <span aria-label={step.passed ? "passed" : "failed"} style={{ color: step.passed ? "var(--approve)" : "var(--alarm)", fontWeight: 600 }}>{step.passed ? "✓" : "✗"}</span>
                        <span>{step.check}{step.detail ? <span className="muted">: {step.detail}</span> : null}</span>
                      </li>
                    ))}
                    <li className="small muted">Ran at {fmtTime(r.ran_at)} in “{r.ran_in}”.</li>
                  </ul>
                ) : null}
              </div>
            );
          })}
        </section>

        <div className="stack-l">
          <section className="panel stack">
            <h2 style={{ fontSize: 19 }}>Fault switches</h2>
            <p className="small muted">Make a dependency fail on purpose, then use the patient phone or app to see the safe fallback. Switch them off afterwards.</p>
            {data?.faults.map((f) => (
              <label key={f.key} className="check">
                <input type="checkbox" checked={f.enabled} disabled={busy} onChange={(e) => toggle(f.key, e.target.checked)} />
                <span>{f.label}{f.enabled ? <b style={{ color: "var(--alarm)" }}> (on)</b> : null}</span>
              </label>
            ))}
          </section>
          <section className="panel stack">
            <h2 style={{ fontSize: 19 }}>Scheduler</h2>
            <p className="small muted">The scheduler runs every 15 seconds: it sends due reminders, retries stuck jobs, opens tasks for long-overdue follow-ups and escalates unowned tasks. Run one round now:</p>
            <button className="btn btn--quiet" style={{ justifySelf: "start" }} disabled={busy}
              onClick={async () => { const r = await run(() => api<Record<string, number>>("/v1/demo/run-scheduler", { method: "POST" }), "Scheduler round finished."); if (r) setTick(r); }}>
              Run scheduler now
            </button>
            {tick ? <p className="small">{Object.entries(tick).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join("; ")}</p> : null}
            <p className="small muted">Background jobs: {data?.tasks_mode === "celery" ? "Celery worker" : "run inline"}.</p>
          </section>
        </div>
      </div>
    </>
  );
}
