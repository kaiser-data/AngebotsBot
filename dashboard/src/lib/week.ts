/**
 * ISO-week helpers. Used to translate `?week=current|next|all` into the
 * date range that filters offers (against valid_from / valid_to).
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

/** Monday of the given date's ISO week (00:00 local). */
function isoMonday(d: Date): Date {
  const day = d.getDay() || 7; // Sun=0 → 7
  const m = new Date(d);
  m.setHours(0, 0, 0, 0);
  m.setDate(d.getDate() - (day - 1));
  return m;
}

/** Sunday end-of-day of the given date's ISO week. */
function isoSunday(d: Date): Date {
  const s = isoMonday(d);
  s.setDate(s.getDate() + 6);
  s.setHours(23, 59, 59, 999);
  return s;
}

export type WeekRange = { from: Date; to: Date; label: string };

export function weekRange(key: WeekKey, now: Date = new Date()): WeekRange | null {
  if (key === "all") return null;
  const ref = new Date(now);
  if (key === "next") ref.setDate(ref.getDate() + 7);
  return {
    from: isoMonday(ref),
    to: isoSunday(ref),
    label: WEEK_LABELS[key],
  };
}

/** ISO date (YYYY-MM-DD) for use with Supabase's date column comparators. */
export function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}
