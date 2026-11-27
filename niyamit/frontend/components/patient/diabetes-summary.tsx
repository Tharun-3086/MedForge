"use client";
import { useApi } from "@/lib/api";
type Finding={key:string;label:string;value:string;clinic_reviewed:boolean;explanation:string;report_date:string|null;artifact_id:string;proposal_id:string;source_metadata?:{page?:number};range_comparison?:{status:string;range_as_written:string;limitation:string}|null};
type Summary={findings:Finding[];historical_comparisons:{parameter:string;label:string;direction:string;change:string;unit:string;interpretation:string}[];documents:{artifact_id:string;filename:string;scope:{status:string;reason:string}}[];missing_from_verified_records:string[];limitations:string[];medication_history:{message:string};screening_information:{message:string}};
export function DiabetesSummary({endpoint,staff=false}:{endpoint:string;staff?:boolean}){
 const data=useApi<Summary>(endpoint);
 return <section className="card stack" aria-label="Diabetes monitoring summary">
  <div className="spread"><h2>Diabetes monitoring summary</h2><button className="pt-link" onClick={()=>void data.reload()} disabled={data.loading}>Refresh summary</button></div>
  <p className="small muted">English summary · Source-linked explanations and numerical comparisons. This does not diagnose diabetes or recommend treatment.</p>
  {data.error?<p role="alert">{data.error.message}</p>:!data.data?<p role="status">Loading summary…</p>:<>
   <a className="pt-link" href={`/api${endpoint}?download=true`} download>Download summary (JSON)</a>
   {data.data.findings.map(f=><details key={f.key}><summary>{f.label}: {f.value} · {f.clinic_reviewed?"Clinic-reviewed":"Unverified"}</summary><p>{f.explanation}</p><p className="small">Report date: {f.report_date??"Not established"}{f.source_metadata?.page?` · Page ${f.source_metadata.page}`:""}</p>
    {f.range_comparison?<p className="notice">{f.range_comparison.status.replaceAll("_"," ")} ({f.range_comparison.range_as_written}). {f.range_comparison.limitation}</p>:null}
    <a href={staff?`/reports/${f.proposal_id}`:`/api/v1/p/documents/${f.artifact_id}/file`} target="_blank" rel="noreferrer">Open source report</a></details>)}
   {data.data.historical_comparisons.length?<details><summary>Changes in reviewed results</summary>{data.data.historical_comparisons.map(c=><p key={c.parameter+c.unit}><b>{c.label}</b>: {c.direction} ({c.change} {c.unit}). {c.interpretation}</p>)}</details>:<p className="small">Not enough comparable clinic-reviewed results and dates to describe a change.</p>}
   <details><summary>Document relevance</summary>{data.data.documents.map(d=><p key={d.artifact_id}><b>{d.filename}</b>: {d.scope.status.replaceAll("_"," ")} — {d.scope.reason}</p>)}</details>
   <details><summary>Missing information and limitations</summary><p>Not found in verified records: {data.data.missing_from_verified_records.join(", ")||"None among the supported measurements"}. This does not mean these tests are clinically required.</p><p>{data.data.medication_history.message}</p><p>{data.data.screening_information.message}</p>{data.data.limitations.map(l=><p className="small" key={l}>{l}</p>)}</details>
  </>}
 </section>;
}
