/**
 * Heuristics for spotting unreliable offer data:
 *
 * 1. Discount trust — kaufDA frequently shows the unit price as "sale" against
 *    a multi-pack regular price (or vice-versa), producing ridiculous 90-99%
 *    discounts on beer/water/soda packs. We detect pack hints in the title and
 *    downgrade trust accordingly.
 *
 * 2. Freshness — `valid_to` is the offer's last day. After that, the kaufDA
 *    brochure link rots within a few days. We filter expired offers out of
 *    dashboard queries by default.
 */

import { berlinDate } from "./week";

// Pack/multi-unit indicators that strongly suggest a multi-pack listing where
// the headline discount % can't be trusted at face value.
const PACK_PATTERNS: RegExp[] = [
  /\b\d+\s*er[-\s]*pack(?:ung)?/i,        // 12er Pack, 24er-Packung
  /\b\d+\s*[x×]\s*[\d.,]+\s*(?:l|ml|cl|g|kg|stk|st\.)/i, // 24x500ml, 6 x 1,5l
  /\bkasten\b/i,
  /\btray\b/i,
  /\bpalette\b/i,
  /\bgebinde\b/i,
  /\bharass(en)?\b/i,                     // Swiss "Harass" = crate
  /\b\d+\s*(flaschen?|dosen?|büchsen?|gläser)\b/i,
  /\bsixpack\b/i,
  /\bmehrweg-?kasten\b/i,
  /\b\d+\s*[+]\s*\d+\b/i,                 // "12+2 gratis"
];

export type DiscountTrust = "trusted" | "suspect" | "implausible";

/**
 * Score whether a displayed discount is believable.
 * - "implausible": >95% — physically nonsense, almost always a data error
 * - "suspect":    >70% AND title has pack hint, OR >85% always
 * - "trusted":    everything else
 */
export function discountTrust(
  title: string | null | undefined,
  discountPercent: number | null | undefined,
): DiscountTrust {
  if (discountPercent == null) return "trusted";
  // Negative / NaN = price above the "regular" price — a parsing error.
  if (!Number.isFinite(discountPercent) || discountPercent < 0) return "implausible";
  if (discountPercent > 95) return "implausible";
  if (discountPercent > 85) return "suspect";
  if (discountPercent > 70) {
    const t = (title ?? "").toLowerCase();
    if (PACK_PATTERNS.some((p) => p.test(t))) return "suspect";
  }
  return "trusted";
}

/**
 * The discount to show, as a whole percent. kaufDA often gives an old price
 * but no percentage (Senseo pads: 1,99 € instead of 3,99 €, no badge), and the
 * AI answer must quote the same number as the badge next to it ("42 %" next to
 * "−43%" looked like an error). One rounding rule for both.
 */
export function effectiveDiscount(
  price: number | string | null | undefined,
  original: number | string | null | undefined,
  discountPercent: number | string | null | undefined,
): number | null {
  const d = discountPercent == null ? NaN : Number(discountPercent);
  if (Number.isFinite(d)) return Math.round(d);
  const p = price == null ? NaN : Number(price);
  const o = original == null ? NaN : Number(original);
  if (!Number.isFinite(p) || !Number.isFinite(o) || o <= 0 || p >= o || p < 0) return null;
  return Math.round((1 - p / o) * 100);
}

/**
 * Is this offer's validity window in the past? (links go stale shortly after.)
 * NULL valid_to = treat as fresh — kaufDA omits dates for evergreen listings.
 *
 * "Today" is the Berlin calendar day: between midnight and 01:00/02:00 Berlin
 * the UTC date is still yesterday, so a UTC comparison kept showing offers
 * that had already ended.
 */
export function isExpired(validTo: string | null | undefined, today: Date = new Date()): boolean {
  if (!validTo) return false;
  // valid_to is a date column (YYYY-MM-DD). Compare lexicographically.
  return validTo.slice(0, 10) < todayIso(today);
}

/** Today's Berlin calendar date (YYYY-MM-DD), for Supabase date-column filters. */
export function todayIso(now: Date = new Date()): string {
  return berlinDate(now);
}

/** Anything not re-scraped in the last N days has almost certainly rotted on kaufDA. */
export const FRESHNESS_DAYS = 8;

/** ISO timestamp for `FRESHNESS_DAYS` days ago. Used to filter `last_seen_at`. */
export function freshnessThresholdIso(now: Date = new Date()): string {
  return new Date(now.getTime() - FRESHNESS_DAYS * 86_400_000).toISOString();
}

/** Kaufda search-URL fallback for offers whose direct brochure URL is missing or dead. */
export function offerLink(
  url: string | null | undefined,
  title: string | null | undefined,
): string {
  if (url && url.trim()) return url;
  const q = (title ?? "").trim();
  if (!q) return "https://www.kaufda.de";
  return `https://www.kaufda.de/Angebote/${encodeURIComponent(q)}`;
}
