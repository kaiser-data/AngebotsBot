/**
 * Canonical category & subcategory taxonomy.
 *
 * SINGLE SOURCE OF TRUTH — mirrored in `scripts/categorize_offers.py`.
 * If you change anything here, update the Python file too and bump the
 * MODEL_VERSION there so existing rows get re-classified.
 *
 * Design goals: 10 broad buckets, 4-8 stable subcategories each (~45 total).
 * Short, German, plural-or-singular-consistent. No brand names. No "Bio-X"
 * variants (Bio belongs in the offer's tags, not its category).
 */

export const BUCKETS = [
  "Lebensmittel",
  "Getränke",
  "Drogerie & Kosmetik",
  "Haushalt & Reinigung",
  "Baby & Kind",
  "Tier",
  "Garten & Heimwerken",
  "Elektronik & Multimedia",
  "Mode, Sport & Freizeit",
  "Sonstiges",
] as const;

export type Bucket = (typeof BUCKETS)[number];

export const SUBCATEGORIES: Record<Bucket, readonly string[]> = {
  "Lebensmittel": [
    "Obst & Gemüse",
    "Fleisch & Wurst",
    "Fisch",
    "Milchprodukte & Käse",
    "Brot & Backwaren",
    "Süßwaren & Snacks",
    "Tiefkühl",
    "Grundnahrung & Konserven",
  ],
  "Getränke": [
    "Wasser & Säfte",
    "Bier",
    "Wein & Sekt",
    "Spirituosen",
    "Kaffee & Tee",
  ],
  "Drogerie & Kosmetik": [
    "Körperpflege",
    "Kosmetik & Make-up",
    "Gesundheit & Apotheke",
    "Parfum & Düfte",
  ],
  "Haushalt & Reinigung": [
    "Waschmittel",
    "Reinigung",
    "Küchenbedarf",
    "Aufbewahrung",
  ],
  "Baby & Kind": [
    "Windeln & Pflege",
    "Baby-Nahrung",
    "Spielzeug",
  ],
  "Tier": [
    "Hund",
    "Katze",
    "Sonstige Tiere",
  ],
  "Garten & Heimwerken": [
    "Pflanzen & Garten",
    "Gartenwerkzeug",
    "Werkzeug & Heimwerken",
    "Farbe & Bauchemie",
    "Gartenmöbel",
  ],
  "Elektronik & Multimedia": [
    "Smartphone & Tablet",
    "Computer & Drucker",
    "TV & Audio",
    "Haushaltsgeräte",
    "Sonstige Elektronik",
  ],
  "Mode, Sport & Freizeit": [
    "Kleidung & Schuhe",
    "Sport & Fitness",
    "Outdoor",
    "Spielzeug & Hobby",
  ],
  "Sonstiges": [
    "Auto & Mobilität",
    "Büro & Schreibwaren",
    "Sonstige",
  ],
} as const;

export type SubcategoryFor<B extends Bucket> = (typeof SUBCATEGORIES)[B][number];

/** All allowed (bucket, subcategory) pairs as a flat list, useful for validation. */
export const ALL_SUBCATEGORIES: { bucket: Bucket; subcategory: string }[] =
  (BUCKETS as readonly Bucket[]).flatMap((b) =>
    SUBCATEGORIES[b].map((s) => ({ bucket: b, subcategory: s })),
  );

export function isValidSubcategory(bucket: Bucket, sub: string): boolean {
  return (SUBCATEGORIES[bucket] as readonly string[]).includes(sub);
}
