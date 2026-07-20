/**
 * Map kaufDA's own category tree onto our 10 buckets.
 *
 * kaufDA ships a real taxonomy with every offer (`categoryPaths`), stored by
 * the scraper as `kaufda_category` (top level) and `kaufda_category_path`
 * ("A > B > C"). It covers ~95% of offers and is far more reliable than either
 * the search keyword or the title heuristic.
 *
 * Two top-level names each cover two of our buckets:
 *   "Lebensmittel und Getränke" → Lebensmittel | Getränke
 *   "Drogerie und Haushalt"     → Drogerie & Kosmetik | Haushalt & Reinigung
 * Level 3 of the path disambiguates them ("… > Produkte > Getränke > …"), so
 * we consult it before falling back to the top level.
 */

import type { Bucket } from "./taxonomy";

/** Unambiguous top-level kaufDA categories. */
const TOP_LEVEL: Record<string, Bucket> = {
  "Elektronik und Technik": "Elektronik & Multimedia",
  "Computer und Software": "Elektronik & Multimedia",
  "Möbel und Wohnen": "Garten & Heimwerken",
  "Heimwerken und Garten": "Garten & Heimwerken",
  "Baby und Kinder": "Baby & Kind",
  "Tierbedarf und Tierfutter": "Tier",
  "Mode und Accessoires": "Mode, Sport & Freizeit",
  "Sport und Freizeit": "Mode, Sport & Freizeit",
  "Saison und Events": "Sonstiges",
  Dienstleistungen: "Sonstiges",
};

/**
 * Level-3 path segments that resolve an ambiguous top level. Matched as a
 * prefix so "Marken Lebensmittel" resolves the same as "Lebensmittel".
 * Checked longest-first so a longer label is never shadowed by a shorter one.
 */
const LEVEL_3: readonly { prefix: string; bucket: Bucket }[] = [
  // Longest prefixes first — "Marken Lebensmittel" must not be shadowed by
  // "Lebensmittel".
  { prefix: "Marken Lebensmittel", bucket: "Lebensmittel" },
  { prefix: "Marken Haushalt", bucket: "Haushalt & Reinigung" },
  { prefix: "Getränke", bucket: "Getränke" },
  { prefix: "Lebensmittel", bucket: "Lebensmittel" },
  { prefix: "Drogerie", bucket: "Drogerie & Kosmetik" },
  { prefix: "Haushalt", bucket: "Haushalt & Reinigung" },
];

/** Fallback when the path has no usable level 3. */
const AMBIGUOUS_DEFAULT: Record<string, Bucket> = {
  "Lebensmittel und Getränke": "Lebensmittel",
  "Drogerie und Haushalt": "Haushalt & Reinigung",
};

/**
 * Resolve a bucket from kaufDA's taxonomy, or null when it can't be
 * determined — the caller should fall back to the title heuristic.
 */
export function bucketFromKaufda(
  category: string | null | undefined,
  path: string | null | undefined,
): Bucket | null {
  const top = (category ?? "").trim();
  if (!top) return null;

  const direct = TOP_LEVEL[top];
  if (direct) return direct;

  if (top in AMBIGUOUS_DEFAULT) {
    const segments = (path ?? "").split(">").map((s) => s.trim());
    const level3 = segments[2] ?? "";
    const match = LEVEL_3.find((m) => level3.startsWith(m.prefix));
    return match ? match.bucket : AMBIGUOUS_DEFAULT[top];
  }

  return null;
}
