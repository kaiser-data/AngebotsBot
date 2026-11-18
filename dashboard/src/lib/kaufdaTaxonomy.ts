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
  Spielzeug: "Baby & Kind",
  Apotheke: "Drogerie & Kosmetik",
  "Büro- und Schreibwaren": "Sonstiges",
  "Dekoration und Geschenkartikel": "Sonstiges",
  Medien: "Sonstiges",
  Sonstige: "Sonstiges",
};

/** Subcategory implied by an unambiguous top level (where there is one). */
const TOP_LEVEL_SUB: Record<string, string> = {
  Spielzeug: "Spielzeug",
  Apotheke: "Gesundheit & Apotheke",
  "Büro- und Schreibwaren": "Büro & Schreibwaren",
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
  { prefix: "Marken Drogerie", bucket: "Drogerie & Kosmetik" },
  { prefix: "Marken Parfum", bucket: "Drogerie & Kosmetik" },
  { prefix: "Parfümerie", bucket: "Drogerie & Kosmetik" },
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
 * Level-4 path segment ("… > Produkte > Getränke > Bier") → our subcategory.
 * Keyed "<level 3> > <level 4>"; "<level 3> > <level 4> > <level 5>" entries
 * win where level 4 is too broad ("Alkoholische Getränke").
 */
const SUB_BY_PATH: Record<string, string> = {
  // Getränke
  "Getränke > Alkoholische Getränke > Bier": "Bier",
  "Getränke > Alkoholische Getränke > Wein": "Wein & Sekt",
  "Getränke > Alkoholische Getränke > Schaumwein": "Wein & Sekt",
  "Getränke > Alkoholische Getränke > Spirituosen": "Spirituosen",
  "Getränke > Alkoholische Getränke > Likör": "Spirituosen",
  "Getränke > Alkoholische Getränke > Aperitif": "Spirituosen",
  "Getränke > Alkoholische Getränke > Punsch": "Spirituosen",
  "Getränke > Alkoholische Getränke > alkoholische Mixgetränke": "Spirituosen",
  "Getränke > Heißgetränk": "Kaffee & Tee",
  "Getränke > Teegetränk": "Kaffee & Tee",
  "Getränke > Saft": "Wasser & Säfte",
  "Getränke > Wasser": "Wasser & Säfte",
  "Getränke > Softdrinks": "Wasser & Säfte",
  "Getränke > Fitnessgetränke": "Wasser & Säfte",
  "Getränke > Kindergetränke": "Wasser & Säfte",
  "Getränke > Alkoholfreie Getränke": "Wasser & Säfte",
  // Lebensmittel
  "Lebensmittel > Fleisch": "Fleisch & Wurst",
  "Lebensmittel > Wurstwaren": "Fleisch & Wurst",
  "Lebensmittel > Milchprodukte": "Milchprodukte & Käse",
  "Lebensmittel > Fisch": "Fisch",
  "Lebensmittel > Obst": "Obst & Gemüse",
  "Lebensmittel > Gemüse": "Obst & Gemüse",
  "Lebensmittel > Pilze": "Obst & Gemüse",
  "Lebensmittel > Bio Lebensmittel > Bio Obst": "Obst & Gemüse",
  "Lebensmittel > Bio Lebensmittel > Bio Gemüse": "Obst & Gemüse",
  "Lebensmittel > Backwaren": "Brot & Backwaren",
  "Lebensmittel > Süßigkeiten": "Süßwaren & Snacks",
  "Lebensmittel > Knabberzeug": "Süßwaren & Snacks",
  "Lebensmittel > Dessert": "Süßwaren & Snacks",
  "Lebensmittel > Fertiggerichte > Tiefkühlkost": "Tiefkühl",
  "Lebensmittel > Fertiggerichte": "Grundnahrung & Konserven",
  "Lebensmittel > Beilagen": "Grundnahrung & Konserven",
  "Lebensmittel > Saucen": "Grundnahrung & Konserven",
  "Lebensmittel > Brotaufstrich": "Grundnahrung & Konserven",
  "Lebensmittel > Feinkostlebensmittel": "Grundnahrung & Konserven",
  "Lebensmittel > Backzutaten": "Grundnahrung & Konserven",
  "Lebensmittel > Müsli": "Grundnahrung & Konserven",
  "Lebensmittel > Würzmittel": "Grundnahrung & Konserven",
  "Lebensmittel > Konserven": "Grundnahrung & Konserven",
  "Lebensmittel > Dosengericht": "Grundnahrung & Konserven",
  "Lebensmittel > Öl, Essig, Salatdressig": "Grundnahrung & Konserven",
  // Drogerie
  "Drogerie > Körperpflege": "Körperpflege",
  "Drogerie > Kosmetik": "Kosmetik & Make-up",
  "Drogerie > Wellness": "Körperpflege",
  "Parfümerie > Düfte": "Parfum & Düfte",
  // Haushalt
  "Haushalt > Reinigen": "Reinigung",
  "Haushalt > Textilreinigung > Waschmittel": "Waschmittel",
  "Haushalt > Textilreinigung > Weichspüler": "Waschmittel",
  "Haushalt > Aufbewahrung": "Aufbewahrung",
  "Haushalt > Haushaltsartikel > Lebensmittelaufbewahrung": "Aufbewahrung",
  "Haushalt > Haushaltsartikel > Mülleimer": "Aufbewahrung",
};

/**
 * Paths whose bucket differs from their level 3: kaufDA files organic drinks
 * under "Lebensmittel > Bio Lebensmittel > Bio Getränke" (Bionade).
 */
const BUCKET_BY_PATH: Record<string, { bucket: Bucket; subcategory: string }> = {
  "Lebensmittel > Bio Lebensmittel > Bio Getränke": { bucket: "Getränke", subcategory: "Wasser & Säfte" },
};

/** Level 3 that alone fixes the subcategory ("Marken Parfum > Axe"). */
const SUB_BY_LEVEL3: Record<string, string> = {
  Parfümerie: "Parfum & Düfte",
  "Marken Parfum": "Parfum & Düfte",
};

export type KaufdaClassification = { bucket: Bucket; subcategory: string | null };

/**
 * Bucket and, where kaufDA's path is specific enough, subcategory. null when
 * the top level is unknown — the caller falls back to the title heuristic.
 * A null subcategory means "bucket is certain, product type isn't".
 */
export function classifyFromKaufda(
  category: string | null | undefined,
  path: string | null | undefined,
): KaufdaClassification | null {
  const top = (category ?? "").trim();
  if (!top) return null;

  const direct = TOP_LEVEL[top];
  if (direct) return { bucket: direct, subcategory: TOP_LEVEL_SUB[top] ?? null };

  if (!(top in AMBIGUOUS_DEFAULT)) return null;
  const seg = (path ?? "").split(">").map((s) => s.trim());
  const override = BUCKET_BY_PATH[seg.slice(2, 5).join(" > ")];
  if (override) return override;
  const level3 = seg[2] ?? "";
  const match = LEVEL_3.find((m) => level3.startsWith(m.prefix));
  const bucket = match ? match.bucket : AMBIGUOUS_DEFAULT[top];
  const subcategory =
    SUB_BY_PATH[seg.slice(2, 5).join(" > ")] ??
    SUB_BY_PATH[seg.slice(2, 4).join(" > ")] ??
    SUB_BY_LEVEL3[level3] ??
    null;
  return { bucket, subcategory };
}

/** Bucket only — see classifyFromKaufda. */
export function bucketFromKaufda(
  category: string | null | undefined,
  path: string | null | undefined,
): Bucket | null {
  return classifyFromKaufda(category, path)?.bucket ?? null;
}
