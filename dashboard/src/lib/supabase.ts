import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

if (!url || !key) {
  throw new Error(
    "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY — copy .env.local.example to .env.local",
  );
}

export const supabase = createClient(url, key, {
  auth: { persistSession: false },
});

/**
 * Apply a week-range filter to a Supabase select query against the `offers` table.
 * Matches offers whose validity window overlaps the given range.
 * Treats NULL valid_from/valid_to as "always valid" so rows without dates aren't lost.
 *
 * Typed as a generic with an `.or` constraint so it works against any
 * PostgrestFilterBuilder chain without depending on its private generic shape
 * (which changes between supabase-js versions).
 */
import type { WeekRange } from "./week";
import { isoDate } from "./week";
import { freshnessThresholdIso, todayIso } from "./offerSanity";

type WithOr = { or: (filter: string) => WithOr };

export function applyWeekFilter<Q>(q: Q, range: WeekRange | null): Q {
  if (!range) return q;
  const builder = q as unknown as WithOr;
  const from = isoDate(range.from);
  const to = isoDate(range.to);
  // valid_from <= to (or null), AND valid_to >= from (or null)
  return builder
    .or(`valid_from.is.null,valid_from.lte.${to}`)
    .or(`valid_to.is.null,valid_to.gte.${from}`) as unknown as Q;
}

/**
 * Drop offers whose validity has already passed — their kaufDA links go stale
 * within days of `valid_to` and the dashboard ends up with broken outbound URLs.
 * NULL valid_to is kept (evergreen listings).
 */
export function excludeExpired<Q>(q: Q): Q {
  const builder = q as unknown as WithOr;
  return builder.or(`valid_to.is.null,valid_to.gte.${todayIso()}`) as unknown as Q;
}

/**
 * Drop offers not re-scraped in the last FRESHNESS_DAYS days.
 *
 * `valid_to` catches offers that report a hard expiry. This catches everything
 * else: if kaufDA dropped the offer (link rotted, brochure rolled over), the
 * scraper stops touching it on subsequent runs and `last_seen_at` falls behind.
 */
type WithGte = { gte: (column: string, value: string) => WithGte };
export function excludeStale<Q>(q: Q): Q {
  const builder = q as unknown as WithGte;
  return builder.gte("last_seen_at", freshnessThresholdIso()) as unknown as Q;
}

export { fetchAllRows, PAGE_SIZE } from "./paging";

/**
 * Is `column` present on `table` right now?
 *
 * The kaufDA taxonomy columns arrive with migration 010, which is applied by
 * hand. Selecting them before that exists fails the whole query with 42703
 * ("column does not exist") and takes the page down. Probing lets the
 * dashboard run against both schema versions and pick the richer one up
 * automatically once the migration lands.
 *
 * Memoized per process: a negative result is re-checked after RETRY_MS so a
 * freshly-applied migration is noticed without a redeploy; a positive result
 * is cached for the process lifetime (columns don't disappear).
 */
const RETRY_MS = 60_000;
const columnProbes = new Map<string, { at: number; present: Promise<boolean> }>();

export function hasColumn(table: string, column: string): Promise<boolean> {
  const key = `${table}.${column}`;
  const cached = columnProbes.get(key);
  if (cached && Date.now() - cached.at < RETRY_MS) return cached.present;

  const present = Promise.resolve(supabase.from(table).select(column).limit(1)).then(
    ({ error }) => !error,
    () => false,
  );

  columnProbes.set(key, { at: Date.now(), present });
  // Keep a confirmed-present result cached indefinitely.
  void present.then((ok: boolean) => {
    if (ok) columnProbes.set(key, { at: Number.MAX_SAFE_INTEGER, present });
  });
  return present;
}

export type Offer = {
  id: string;
  external_id: string;
  title: string;
  url: string;
  image_url: string | null;
  price: number | null;
  original_price: number | null;
  discount_percent: number | null;
  store: string | null;
  category: string | null;
  validity_text: string | null;
  valid_from: string | null;
  valid_to: string | null;
  is_upcoming: boolean;
  is_active: boolean;
  scraped_at: string;
};

export type DealScore = {
  offer_id: string;
  external_id: string;
  title: string;
  store: string | null;
  category: string | null;
  current_price: number | null;
  original_price: number | null;
  discount_percent: number | null;
  avg_price_90d: number | null;
  min_price_90d: number | null;
  max_price_90d: number | null;
  observation_count: number | null;
  pct_below_avg: number | null;
  price_percentile: number | null;
};

export type PricePoint = {
  observed_at: string;
  price: number | null;
  loyalty_price: number | null;
};
