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
  if (discountPercent > 95) return "implausible";
  if (discountPercent > 85) return "suspect";
  if (discountPercent > 70) {
    const t = (title ?? "").toLowerCase();
    if (PACK_PATTERNS.some((p) => p.test(t))) return "suspect";
  }
  return "trusted";
}

/**
 * Is this offer's validity window in the past? (links go stale shortly after.)
 * NULL valid_to = treat as fresh — kaufDA omits dates for evergreen listings.
 */
export function isExpired(validTo: string | null | undefined, today: Date = new Date()): boolean {
  if (!validTo) return false;
  // valid_to is a date column (YYYY-MM-DD). Compare lexicographically.
  const todayIso = today.toISOString().slice(0, 10);
  return validTo < todayIso;
}

/** ISO date used by Supabase date-column filters. */
export function todayIso(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

/** Anything not re-scraped in the last N days has almost certainly rotted on kaufDA. */
export const FRESHNESS_DAYS = 8;

/** ISO timestamp for `FRESHNESS_DAYS` days ago. Used to filter `last_seen_at`. */
export function freshnessThresholdIso(now: Date = new Date()): string {
  const t = new Date(now);
  t.setDate(t.getDate() - FRESHNESS_DAYS);
  return t.toISOString();
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
