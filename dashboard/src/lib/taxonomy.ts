/**
 * Canonical category & subcategory taxonomy.
 *
 * SINGLE SOURCE OF TRUTH: `taxonomy.json` (same file Python loads).
 * Edit the JSON, then bump MODEL_VERSION in `scripts/categorize_offers.py`
 * if existing LLM rows must be re-classified.
 */

import taxonomyJson from "./taxonomy.json";

export const BUCKETS = taxonomyJson.buckets as readonly string[];
export type Bucket = (typeof BUCKETS)[number];

export const SUBCATEGORIES = taxonomyJson.subcategories as Record<
  string,
  readonly string[]
>;

export type SubcategoryFor<B extends Bucket> = (typeof SUBCATEGORIES)[B][number];

/** All allowed (bucket, subcategory) pairs as a flat list, useful for validation. */
export const ALL_SUBCATEGORIES: { bucket: Bucket; subcategory: string }[] =
  BUCKETS.flatMap((b) =>
    (SUBCATEGORIES[b] ?? []).map((s) => ({ bucket: b, subcategory: s })),
  );

export function isValidSubcategory(bucket: Bucket, sub: string): boolean {
  return (SUBCATEGORIES[bucket] ?? []).includes(sub);
}
