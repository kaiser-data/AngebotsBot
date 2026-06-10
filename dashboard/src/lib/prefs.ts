/**
 * User preferences for the personalized "Für dich" feed.
 *
 * No auth, no backend — prefs live in localStorage on the device. The feed
 * filters client-side against Supabase (anon key, same as the rest of the app).
 */

import { BUCKETS, type Bucket } from "./taxonomy";

export type Prefs = {
  /** Preferred stores. Empty array = all stores. */
  stores: string[];
  /** Preferred category buckets shown in the main feed. */
  buckets: Bucket[];
  /**
   * Discount threshold (%) above which offers OUTSIDE the preferred buckets
   * still appear, as "Schnäppchen". null = radar off.
   */
  bargainMinDiscount: number | null;
  /** Whether the user has completed (or dismissed) onboarding. */
  onboarded: boolean;
};

/** Grocery-first defaults: food & drinks, bargain radar at 40%. */
export const FOOD_BUCKETS: Bucket[] = ["Lebensmittel", "Getränke"];

export const DEFAULT_PREFS: Prefs = {
  stores: [],
  buckets: FOOD_BUCKETS,
  bargainMinDiscount: 40,
  onboarded: false,
};

/**
 * Chains we consider "Supermarkt/Discounter" for the one-tap preset.
 * Matched against the store name as scraped from kaufDA.
 * NB: "Globus" (SB-Warenhaus) yes, "Globus-Baumarkt" no.
 */
const SUPERMARKET_PATTERNS: RegExp[] = [
  /^lidl/i,
  /^kaufland/i,
  /^netto/i, // Marken-Discount + "mit dem Scottie"
  /^rewe/i,
  /^penny/i,
  /^edeka/i,
  /^e center/i,
  /^aldi/i,
  /^norma\b/i,
  /^globus(?!-baumarkt)/i,
  /^tegut/i,
  /^nahkauf/i,
  /^famila/i,
  /^marktkauf/i,
  /^hit\b/i,
  /^real\b/i,
  /^v-markt/i,
  /^wasgau/i,
  /^feneberg/i,
  /^combi\b/i,
];

const DRUGSTORE_PATTERNS: RegExp[] = [/^dm/i, /^rossmann/i, /^müller\b/i, /^budni/i];

export function isSupermarket(store: string): boolean {
  return SUPERMARKET_PATTERNS.some((p) => p.test(store.trim()));
}

export function isDrugstore(store: string): boolean {
  return DRUGSTORE_PATTERNS.some((p) => p.test(store.trim()));
}

const STORAGE_KEY = "angebotsbot.prefs.v1";

/** Parse + validate whatever is in storage; silently fall back to defaults. */
function sanitize(raw: unknown): Prefs {
  if (typeof raw !== "object" || raw === null) return DEFAULT_PREFS;
  const r = raw as Record<string, unknown>;
  const stores = Array.isArray(r.stores)
    ? r.stores.filter((s): s is string => typeof s === "string")
    : DEFAULT_PREFS.stores;
  const buckets = Array.isArray(r.buckets)
    ? (r.buckets.filter(
        (b): b is Bucket => typeof b === "string" && (BUCKETS as readonly string[]).includes(b),
      ) as Bucket[])
    : DEFAULT_PREFS.buckets;
  const bargainMinDiscount =
    r.bargainMinDiscount === null
      ? null
      : typeof r.bargainMinDiscount === "number" &&
          r.bargainMinDiscount >= 5 &&
          r.bargainMinDiscount <= 95
        ? r.bargainMinDiscount
        : DEFAULT_PREFS.bargainMinDiscount;
  return {
    stores,
    buckets: buckets.length > 0 ? buckets : DEFAULT_PREFS.buckets,
    bargainMinDiscount,
    onboarded: r.onboarded === true,
  };
}

export function loadPrefs(): Prefs {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFS;
    return sanitize(JSON.parse(raw));
  } catch {
    return DEFAULT_PREFS;
  }
}

export function savePrefs(prefs: Prefs): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // Storage full / private mode — feed still works for the session.
  }
}
