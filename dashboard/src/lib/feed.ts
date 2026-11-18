/**
 * Pure selection/ranking logic for the "Für dich" feed, kept out of the React
 * component so it can be unit-tested.
 */

import { discountTrust, effectiveDiscount } from "./offerSanity";
import type { Prefs } from "./prefs";
import { resolveCategory, type CategoryInput } from "./resolveCategory";
import type { Bucket } from "./taxonomy";

export type FeedRow = CategoryInput & {
  id: string;
  title: string;
  store: string | null;
  price: number | null;
  original_price: number | null;
  discount_percent: number | null;
  image_url: string | null;
  url: string;
  last_seen_at: string | null;
};

export type ClassifiedRow = FeedRow & {
  bucket: Bucket;
  subcategory: string;
  /** discount usable for ranking — implausible values nulled out */
  eff: number | null;
  trusted: boolean;
};

export const MINE_LIMIT = 60;
export const BARGAIN_LIMIT = 24;
/** "Preis-Tief": price is in the cheapest 20% of its 90-day history. */
export const PRICE_LOW_PERCENTILE = 20;
const PRICE_LOW_BOOST = 15;

export function classifyFeedRow(o: FeedRow): ClassifiedRow {
  const { bucket, subcategory } = resolveCategory(o);
  // Same number the badge shows (computed from the old price when kaufDA gives no %).
  const discount = effectiveDiscount(o.price, o.original_price, o.discount_percent);
  const trust = discountTrust(o.title, discount);
  return {
    ...o,
    bucket,
    subcategory,
    eff: trust === "implausible" ? null : discount,
    trusted: trust === "trusted",
  };
}

/**
 * Ranking score: trusted discount, plus a boost when the price is at a 90-day
 * low. Suspect discounts (multi-pack unit-price mix-ups) count half, so an
 * "88% off" crate of beer doesn't outrank a real 40% deal.
 */
export function feedScore(o: ClassifiedRow, percentile: number | undefined): number {
  const discount = o.eff ?? 0;
  const base = o.trusted ? discount : discount / 2;
  const low = percentile != null && percentile <= PRICE_LOW_PERCENTILE ? PRICE_LOW_BOOST : 0;
  return base + low;
}

/** Offers in the user's preferred buckets, best first. */
export function pickMine(
  rows: readonly ClassifiedRow[],
  prefs: Prefs,
  scores: ReadonlyMap<string, number> = new Map(),
): ClassifiedRow[] {
  return rows
    .filter((o) => prefs.buckets.includes(o.bucket))
    .map((o) => ({ o, s: feedScore(o, scores.get(o.id)) }))
    .sort((a, b) => b.s - a.s || priceAsc(a.o, b.o))
    .slice(0, MINE_LIMIT)
    .map(({ o }) => o);
}

/** Big, trustworthy discounts OUTSIDE the preferred buckets. */
export function pickBargains(rows: readonly ClassifiedRow[], prefs: Prefs): ClassifiedRow[] {
  const min = prefs.bargainMinDiscount;
  if (min == null) return [];
  return rows
    .filter(
      (o) => !prefs.buckets.includes(o.bucket) && o.trusted && o.eff != null && o.eff >= min,
    )
    .sort((a, b) => (b.eff ?? 0) - (a.eff ?? 0) || priceAsc(a, b))
    .slice(0, BARGAIN_LIMIT);
}

function priceAsc(a: { price: number | null }, b: { price: number | null }): number {
  return (a.price ?? Infinity) - (b.price ?? Infinity);
}

/** "vor 5 min" / "vor 3 h" / "vor 2 Tagen" — German relative time. */
export function relativeTime(iso: string | null, now: number = Date.now()): string {
  if (!iso) return "unbekannt";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "unbekannt";
  const mins = Math.max(0, Math.round((now - t) / 60000));
  if (mins < 1) return "gerade eben";
  if (mins < 60) return `vor ${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 36) return `vor ${hours} h`;
  const days = Math.round(hours / 24);
  return days === 1 ? "vor 1 Tag" : `vor ${days} Tagen`;
}
