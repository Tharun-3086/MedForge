"use client";
import type { Lang } from "@/lib/i18n";
export type CareDestination = "home" | "passport" | "report" | "family" | "message";
const labels = {
  home: { en: "Home", hi: "होम", te: "హోమ్" },
  passport: { en: "My records", hi: "मेरे रिकॉर्ड", te: "నా రికార్డులు" },
  report: { en: "Scan a report", hi: "रिपोर्ट स्कैन करें", te: "రిపోర్ట్ స్కాన్" },
  family: { en: "Family access", hi: "परिवार की पहुँच", te: "కుటుంబ యాక్సెస్" },
  message: { en: "Message clinic", hi: "क्लिनिक को संदेश", te: "క్లినిక్‌కు సందేశం" },
};
const paths: Record<CareDestination, string> = {
  home: "m3 10 9-7 9 7v10H3Z M9 20v-7h6v7",
  passport: "M6 3h12v18H6Z M9 8h6 M9 12h6 M9 16h4",
  report: "M8 5l2-2h4l2 2h5v15H3V5Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  family: "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M2 21v-3a7 7 0 0 1 14 0v3 M17 4a4 4 0 0 1 0 8 M18 15a5 5 0 0 1 4 5",
  message: "M3 3h18v14H9l-6 4Z M7 8h10 M7 12h7",
};
function Icon({ kind }: { kind: CareDestination }) {
  return <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[kind]} /></svg>;
}
export function CareActions({ lang, onSelect }: { lang: Lang; onSelect: (view: CareDestination) => void }) {
  return <div className="care-actions">{(["report", "message", "passport", "family"] as const).map((key) => <button type="button" className={`care-action care-action--${key}`} key={key} onClick={() => onSelect(key)}><span className="care-icon"><Icon kind={key} /></span><span>{labels[key][lang]}</span><span aria-hidden="true">↗</span></button>)}</div>;
}
export function CareNavigation({ lang, current, onSelect }: { lang: Lang; current: string; onSelect: (view: CareDestination) => void }) {
  return <nav className="care-navigation" aria-label="Patient navigation">{(["home", "passport", "report", "family"] as const).map((key) => <button type="button" key={key} aria-current={current === key ? "page" : undefined} onClick={() => onSelect(key)}><Icon kind={key} /><span>{labels[key][lang]}</span></button>)}</nav>;
}
