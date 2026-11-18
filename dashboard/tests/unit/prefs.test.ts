import { describe, expect, it } from "vitest";
import { DEFAULT_PREFS, isDrugstore, isSupermarket, sanitizePrefs } from "@/lib/prefs";

describe("sanitizePrefs (localStorage can contain anything)", () => {
  it("falls back to defaults for garbage", () => {
    expect(sanitizePrefs(null)).toEqual(DEFAULT_PREFS);
    expect(sanitizePrefs("hello")).toEqual(DEFAULT_PREFS);
    expect(sanitizePrefs(42)).toEqual(DEFAULT_PREFS);
  });

  it("drops unknown buckets and non-string stores, dedupes", () => {
    const p = sanitizePrefs({
      stores: ["Lidl", 3, null, "Lidl", "", "REWE"],
      buckets: ["Getränke", "Nope", "Getränke"],
      bargainMinDiscount: 25,
      onboarded: true,
    });
    expect(p.stores).toEqual(["Lidl", "REWE"]);
    expect(p.buckets).toEqual(["Getränke"]);
    expect(p.bargainMinDiscount).toBe(25);
    expect(p.onboarded).toBe(true);
  });

  it("never leaves the user with zero categories (empty feed forever)", () => {
    expect(sanitizePrefs({ buckets: [] }).buckets).toEqual(DEFAULT_PREFS.buckets);
    expect(sanitizePrefs({ buckets: ["x"] }).buckets).toEqual(DEFAULT_PREFS.buckets);
  });

  it("keeps an explicit 'radar off' but rejects out-of-range thresholds", () => {
    expect(sanitizePrefs({ bargainMinDiscount: null }).bargainMinDiscount).toBeNull();
    expect(sanitizePrefs({ bargainMinDiscount: 0 }).bargainMinDiscount).toBe(40);
    expect(sanitizePrefs({ bargainMinDiscount: 150 }).bargainMinDiscount).toBe(40);
    expect(sanitizePrefs({ bargainMinDiscount: "40" }).bargainMinDiscount).toBe(40);
  });

  it("only a literal true counts as onboarded", () => {
    expect(sanitizePrefs({ onboarded: "true" }).onboarded).toBe(false);
  });
});

describe("store presets", () => {
  it("recognises supermarkets", () => {
    for (const s of ["Lidl", "REWE", "Netto Marken-Discount", "ALDI SÜD", "E center", "Globus", " Kaufland "]) {
      expect(isSupermarket(s), s).toBe(true);
    }
  });
  it("does not match lookalikes", () => {
    expect(isSupermarket("Globus-Baumarkt")).toBe(false);
    expect(isSupermarket("Realkauf Möbel")).toBe(false);
    expect(isSupermarket("Hitachi Store")).toBe(false);
  });
  it("recognises drugstores without catching other 'dm…' names", () => {
    expect(isDrugstore("dm-drogerie markt")).toBe(true);
    expect(isDrugstore("Rossmann")).toBe(true);
    expect(isDrugstore("DMAX Shop")).toBe(false);
  });
});
