"use client";

import { useEffect, useState } from "react";

import { INTENT_LABELS } from "@/components/outcomes";
import { PageHead } from "@/components/staff-shell";
import { Empty, ErrorNote, Loading, Pill, useAction } from "@/components/ui";
import { api, usePoll, useApi } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

type Corpus = { version: string; reference_date: string; count: number; by_language: Record<string, number>; items: { id: string; lang: string; text: string; intents: string[] }[] };
type Run = { id: string; provider: string; model: string; status: string; corpus_version: string; items: number; exact_match: number; fallbacks: number; started_at: string; finished_at: string | null; triggered_by: string };
type Summary = {
  run: Run & { exact_match: number; fallbacks: number };
  by_language: { language_pair: string; n: number; exact: number; exact_rate: number | null; fields_n: number; fields_ok: number; fields_rate: number | null }[];
  by_intent: { intent: string; support: number; tp: number; fp: number; recall: number | null; precision: number | null }[];
  latency_ms: { median: number | null; p90: number | null };
  items: { id: string; lang: string; text: string; expected: string[]; predicted: string[]; exact: boolean; fields_match: boolean | null; expected_fields: Record<string, unknown>; predicted_fields: Record<string, unknown>; error: string; latency_ms: number }[];
};
type Providers = { sarvam_key_present: boolean; openai_key_present: boolean };

const pct = (v: number | null) => (v === null ? "n/a" : `${Math.round(v * 100)}%`);
const LANG_PAIR: Record<string, string> = { "te-en": "Telugu–English", "hi-en": "Hindi–English", en: "English" };

export default function EvaluationPage() {
  const corpus = useApi<Corpus>("/v1/evals/corpus");
  const runs = useApi<{ runs: Run[] }>("/v1/evals/runs");
  const { data: providers } = useApi<Providers>("/v1/providers");
  const { busy, run } = useAction();
  const [provider, setProvider] = useState("rules");
  const [selected, setSelected] = useState<string | null>(null);
  const summary = useApi<Summary>(selected ? `/v1/evals/runs/${selected}` : null);
  const [onlyMisses, setOnlyMisses] = useState(true);
  const runningNow = runs.data?.runs.some((r) => r.status === "RUNNING") ?? false;
  usePoll(runningNow, runs.reload, 2000);
  usePoll(summary.data?.run.status === "RUNNING", summary.reload, 2000);

  useEffect(() => {
    if (!selected && runs.data?.runs[0]) setSelected(runs.data.runs[0].id);
  }, [runs.data, selected]);

  async function start() {
    const r = await run(() => api<{ id: string }>("/v1/evals/runs", { body: { provider } }), "Evaluation started.");
    if (r) {
      setSelected(r.id);
      await runs.reload();
    }
  }

  const s = summary.data;
  return (
    <>
      <PageHead title="Language evaluation"
        lede="How well replies are understood, measured on a fixed, versioned set of synthetic test messages. Numbers here come only from runs stored below; they describe this test set, not real-world accuracy." />
      <div className="cols-2" style={{ marginBottom: 20 }}>
        <section className="panel stack">
          <h2 style={{ fontSize: 19 }}>Test set</h2>
          <ErrorNote error={corpus.error} />
          {corpus.data ? (
            <>
              <p>Version <b>{corpus.data.version}</b>: {corpus.data.count} labelled messages, written for this demo (dates are read as if today were {corpus.data.reference_date}).</p>
              <p className="small muted">The offline rules were written alongside this test set, so their score is optimistic. Sarvam and OpenAI never see the labels.</p>
              <div className="row">
                {Object.entries(corpus.data.by_language).map(([k, v]) => <Pill key={k}>{LANG_PAIR[k] ?? k}: {v}</Pill>)}
              </div>
              <details>
                <summary className="small" style={{ cursor: "pointer" }}>See the messages</summary>
                <ul className="small" style={{ maxHeight: 260, overflowY: "auto" }}>
                  {corpus.data.items.map((i) => <li key={i.id}><span className="muted">{i.id}</span> {i.text} <span className="muted">({i.intents.map((x) => INTENT_LABELS[x] ?? x).join(", ")})</span></li>)}
                </ul>
              </details>
            </>
          ) : <Loading />}
        </section>
        <section className="panel stack">
          <h2 style={{ fontSize: 19 }}>Run an evaluation</h2>
          <label className="field"><span>Understood by</span>
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              <option value="rules">Offline rules (no AI, always available)</option>
              <option value="sarvam" disabled={!providers?.sarvam_key_present}>Sarvam AI {providers?.sarvam_key_present ? "" : "(add SARVAM_API_KEY first)"}</option>
              <option value="openai" disabled={!providers?.openai_key_present}>OpenAI {providers?.openai_key_present ? "" : "(add OPENAI_API_KEY first)"}</option>
            </select>
          </label>
          <button className="btn" style={{ justifySelf: "start" }} disabled={busy || runningNow} onClick={start}>{runningNow ? "A run is in progress…" : "Start run"}</button>
          <p className="small muted">An AI run sends each test message to the provider and takes a minute or two. Fallbacks to rules are counted as misses, never as matches.</p>
        </section>
      </div>

      <section className="panel panel--flush" style={{ marginBottom: 20 }}>
        {runs.data && runs.data.runs.length === 0 ? <Empty title="No runs yet">Start a run above. Results appear here and stay stored.</Empty> : null}
        {runs.data && runs.data.runs.length > 0 ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Run</th><th>Status</th><th>Exact intent match</th><th>Fell back to rules</th><th>Started</th><th /></tr></thead>
              <tbody>
                {runs.data.runs.map((r) => (
                  <tr key={r.id} style={selected === r.id ? { background: "var(--teal-wash)" } : undefined}>
                    <td>{r.provider === "rules" ? "Offline rules" : r.provider}<span className="small muted" style={{ display: "block" }}>{r.model}, set {r.corpus_version}</span></td>
                    <td><Pill tone={r.status === "DONE" ? "done" : "info"}>{r.status === "DONE" ? "Finished" : "Running"}</Pill></td>
                    <td>{r.status === "DONE" ? `${r.exact_match} of ${r.items} (${pct(r.items ? r.exact_match / r.items : null)})` : "…"}</td>
                    <td>{r.provider === "rules" ? "n/a" : r.fallbacks}</td>
                    <td className="small">{fmtDateTime(r.started_at)}<span className="muted" style={{ display: "block" }}>{r.triggered_by}</span></td>
                    <td><button className="btn btn--quiet btn--small" onClick={() => setSelected(r.id)}>Details</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      {s && s.run.status === "DONE" ? (
        <div className="stack-l">
          <div className="cols-2">
            <section className="panel">
              <h2 style={{ fontSize: 19, marginBottom: 10 }}>By language pair</h2>
              <table className="table">
                <thead><tr><th>Language</th><th>Messages</th><th>Exact intents</th><th>Day and barrier fields</th></tr></thead>
                <tbody>
                  {s.by_language.map((l) => (
                    <tr key={l.language_pair}>
                      <td>{LANG_PAIR[l.language_pair] ?? l.language_pair}</td>
                      <td>{l.n}</td>
                      <td>{l.exact} ({pct(l.exact_rate)})</td>
                      <td>{l.fields_n ? `${l.fields_ok} of ${l.fields_n} (${pct(l.fields_rate)})` : "none labelled"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="small muted" style={{ marginTop: 8 }}>Median time per message {s.latency_ms.median ?? "n/a"} ms, 90th percentile {s.latency_ms.p90 ?? "n/a"} ms.</p>
            </section>
            <section className="panel">
              <h2 style={{ fontSize: 19, marginBottom: 10 }}>By intent</h2>
              <table className="table">
                <thead><tr><th>Intent</th><th>In set</th><th>Found</th><th>Recall</th><th>Precision</th></tr></thead>
                <tbody>
                  {s.by_intent.map((i) => (
                    <tr key={i.intent}><td>{INTENT_LABELS[i.intent] ?? i.intent}</td><td>{i.support}</td><td>{i.tp}</td><td>{pct(i.recall)}</td><td>{pct(i.precision)}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
          <section className="panel panel--flush">
            <div className="spread" style={{ padding: "14px 18px" }}>
              <h2 style={{ fontSize: 19 }}>Messages</h2>
              <label className="check small"><input type="checkbox" checked={onlyMisses} onChange={(e) => setOnlyMisses(e.target.checked)} /><span>Only show misses</span></label>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Message</th><th>Expected</th><th>Predicted</th><th>Fields</th></tr></thead>
                <tbody>
                  {s.items.filter((i) => !onlyMisses || !i.exact || i.fields_match === false).map((i) => (
                    <tr key={i.id} className={i.exact ? undefined : "is-bad"}>
                      <td><span className="small muted">{i.id}, {LANG_PAIR[i.lang] ?? i.lang}</span><span style={{ display: "block" }}>{i.text}</span>{i.error ? <span className="small" style={{ color: "var(--alarm)" }}>{i.error}</span> : null}</td>
                      <td className="small">{i.expected.map((x) => INTENT_LABELS[x] ?? x).join(", ")}</td>
                      <td className="small">{i.predicted.map((x) => INTENT_LABELS[x] ?? x).join(", ")}</td>
                      <td className="small">{i.fields_match === null ? "not labelled" : i.fields_match ? "match" : `expected ${JSON.stringify(i.expected_fields)}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      ) : selected && summary.loading ? <Loading /> : null}
    </>
  );
}
