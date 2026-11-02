// Dates are shown in the clinic's time zone (Asia/Kolkata for the demo clinics).
export const CLINIC_TZ = "Asia/Kolkata";

const LOCALE: Record<string, string> = { en: "en-IN", hi: "hi-IN", te: "te-IN" };

function toDate(value: string | Date): Date {
  if (value instanceof Date) return value;
  // A bare YYYY-MM-DD is a calendar date: anchor it at noon so no time zone can move it to another day.
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T12:00:00+05:30`) : new Date(value);
}

export function fmtDate(value: string | null | undefined, lang = "en"): string {
  if (!value) return "";
  return new Intl.DateTimeFormat(LOCALE[lang] ?? "en-IN", {
    weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: CLINIC_TZ,
  }).format(toDate(value));
}

export function fmtLongDay(value: string | null | undefined, lang = "en"): string {
  if (!value) return "";
  const parts = new Intl.DateTimeFormat(LOCALE[lang] ?? "en-IN", {
    weekday: "long", day: "numeric", month: "long", timeZone: CLINIC_TZ,
  }).formatToParts(toDate(value));
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return lang === "en" ? `${get("weekday")} ${get("day")} ${get("month")}` : parts.map((p) => p.value).join("");
}

export function fmtShortDate(value: string | null | undefined, lang = "en"): string {
  if (!value) return "";
  return new Intl.DateTimeFormat(LOCALE[lang] ?? "en-IN", { day: "numeric", month: "short", timeZone: CLINIC_TZ })
    .format(toDate(value));
}

export function fmtDateTime(value: string | null | undefined, lang = "en"): string {
  if (!value) return "";
  return new Intl.DateTimeFormat(LOCALE[lang] ?? "en-IN", {
    day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: CLINIC_TZ,
  }).format(toDate(value));
}

export function fmtTime(value: string | null | undefined, lang = "en"): string {
  if (!value) return "";
  return new Intl.DateTimeFormat(LOCALE[lang] ?? "en-IN", { hour: "numeric", minute: "2-digit", timeZone: CLINIC_TZ })
    .format(toDate(value));
}

export function leafParts(value: string, lang = "en"): { weekday: string; day: string; month: string } {
  const d = toDate(value);
  const part = (o: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(LOCALE[lang] ?? "en-IN", { ...o, timeZone: CLINIC_TZ }).format(d);
  return { weekday: part({ weekday: "long" }), day: part({ day: "numeric" }), month: part({ month: "long" }) };
}

/** "3 hours ago" style age for task lists. */
export function age(value: string | null | undefined): string {
  if (!value) return "";
  const minutes = Math.round((Date.now() - new Date(value).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

export function dueIn(value: string | null | undefined): string {
  if (!value) return "";
  const minutes = Math.round((new Date(value).getTime() - Date.now()) / 60000);
  if (minutes < 0) {
    const late = -minutes;
    return late < 120 ? `${late} min overdue` : late < 2880 ? `${Math.round(late / 60)} h overdue` : `${Math.round(late / 1440)} days overdue`;
  }
  return minutes < 120 ? `due in ${minutes} min` : minutes < 2880 ? `due in ${Math.round(minutes / 60)} h` : `due in ${Math.round(minutes / 1440)} days`;
}

export const LANGUAGE_NAME: Record<string, string> = { en: "English", hi: "Hindi", te: "Telugu" };

export function titleCase(code: string): string {
  return code.toLowerCase().replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
