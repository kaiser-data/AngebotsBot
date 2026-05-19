/**
 * ISO-week helpers, anchored to Europe/Berlin so the result is correct no
 * matter what timezone the server (Netlify, GHA, …) is running in.
 *
 * The returned `WeekRange.from` and `WeekRange.to` are Date objects pinned to
 * UTC midnight of the Berlin calendar date — that way both
 *   .toISOString().slice(0, 10)   → "2026-05-18"   (for Supabase date filters)
 *   .toLocaleDateString("de-DE")  → "18.5.2026"    (for the page subtitle)
 * round-trip to the same calendar day on any host.
 */

export type WeekKey = "current" | "next" | "all";

export const WEEK_KEYS: readonly WeekKey[] = ["current", "next", "all"];

export const WEEK_LABELS: Record<WeekKey, string> = {
  current: "Diese Woche",
  next: "Nächste Woche",
  all: "Alle",
};

export function parseWeek(v: string | undefined | null): WeekKey {
  return (WEEK_KEYS as readonly string[]).includes(v ?? "")
    ? (v as WeekKey)
    : "current";
}

const TZ = "Europe/Berlin";

/** Today's calendar date in Berlin, formatted YYYY-MM-DD. */
function berlinDate(d: Date): string {
  // en-CA conveniently formats as YYYY-MM-DD.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

/** ISO weekday in Berlin: 1 = Mon … 7 = Sun. */
function berlinWeekday(d: Date): number {
  const name = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    weekday: "short",
  }).format(d);
  const map: Record<string, number> = {
    Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7,
  };
  return map[name] ?? 1;
}

/** Calendar-date arithmetic: add N days to a YYYY-MM-DD string. */
function addDays(iso: string, n: number): string {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export type WeekRange = { from: Date; to: Date; label: string };

export function weekRange(key: WeekKey, now: Date = new Date()): WeekRange | null {
  if (key === "all") return null;
  const today = berlinDate(now);          // YYYY-MM-DD in Berlin
  const weekday = berlinWeekday(now);     // 1..7
  let fromIso = addDays(today, -(weekday - 1));
  if (key === "next") fromIso = addDays(fromIso, 7);
  const toIso = addDays(fromIso, 6);
  return {
    // UTC-midnight materialization keeps the calendar date stable across
    // server timezones. Don't change to `new Date(fromIso)` — that's local-tz.
    from: new Date(`${fromIso}T00:00:00Z`),
    to: new Date(`${toIso}T00:00:00Z`),
    label: WEEK_LABELS[key],
  };
}

/** YYYY-MM-DD form of a UTC-midnight Date — safe for Supabase date columns. */
export function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}
