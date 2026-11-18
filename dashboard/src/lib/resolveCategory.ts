/**
 * One place that decides an offer's (bucket, subcategory).
 *
 * Used by both the "Für dich" feed and the categories page, so a user who picks
 * "Getränke" in their preferences sees exactly what the Getränke category shows.
 *
 * Source priority:
 *   1. kaufDA's own taxonomy (~95% coverage, most reliable)
 *   2. the LLM classification, where one exists
 *   3. the title heuristic
 *
 * The subcategory is ALWAYS valid for the chosen bucket. Mixing sources used to
 * produce pairs like "Getränke · Fleisch & Wurst" when kaufDA and the heuristic
 * disagreed on the bucket.
 */

import { classify, type Classification } from "./categoryHeuristic";
import { bucketFromKaufda } from "./kaufdaTaxonomy";
import taxonomyJson from "./taxonomy.json";
import { BUCKETS, SUBCATEGORIES, type Bucket } from "./taxonomy";

export type CategoryInput = {
  title: string | null | undefined;
  category: string | null | undefined;
  kaufda_category?: string | null;
  kaufda_category_path?: string | null;
};

export type LLMCategory = { category: string | null; subcategory: string | null };

export type CategorySource = "kaufda" | "llm" | "heuristic";

export type ResolvedCategory = Classification & { source: CategorySource };

const FALLBACK_SUB = taxonomyJson.fallback_subcategory as Record<string, string>;

function isBucket(v: string | null | undefined): v is Bucket {
  return !!v && (BUCKETS as readonly string[]).includes(v);
}

function validSub(bucket: Bucket, sub: string | null | undefined): string | null {
  const s = (sub ?? "").trim();
  return s && (SUBCATEGORIES[bucket] ?? []).includes(s) ? s : null;
}

export function resolveCategory(row: CategoryInput, llm?: LLMCategory | null): ResolvedCategory {
  const heuristic = classify(row.title, row.category);
  const llmBucket = isBucket(llm?.category) ? llm!.category as Bucket : null;

  let bucket: Bucket;
  let source: CategorySource;
  const fromKaufda = bucketFromKaufda(row.kaufda_category, row.kaufda_category_path);
  if (fromKaufda) {
    bucket = fromKaufda;
    source = "kaufda";
  } else if (llmBucket) {
    bucket = llmBucket;
    source = "llm";
  } else {
    bucket = heuristic.bucket;
    source = "heuristic";
  }

  const subcategory =
    (llmBucket === bucket ? validSub(bucket, llm?.subcategory) : null) ??
    (heuristic.bucket === bucket ? validSub(bucket, heuristic.subcategory) : null) ??
    FALLBACK_SUB[bucket] ??
    "Sonstige";

  return { bucket, subcategory, source };
}
