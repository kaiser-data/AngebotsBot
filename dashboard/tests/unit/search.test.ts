import { describe, expect, it } from "vitest";
import { formatDateDe, formatEuro, groupByStore, ilikePattern, searchTerms } from "@/lib/search";

describe("searchTerms", () => {
  it("splits words so word order doesn't matter", () => {
    expect(searchTerms("  ariel   pods ")).toEqual(["ariel", "pods"]);
  });
  it("dedupes case-insensitively and drops 1-char noise", () => {
    expect(searchTerms("Milch milch & x")).toEqual(["Milch"]);
  });
  it("keeps a single short term if that's all there is", () => {
    expect(searchTerms("x")).toEqual(["x"]);
  });
  it("strips PostgREST syntax characters", () => {
    expect(searchTerms('cola*,"zero"')).toEqual(["cola", "zero"]);
  });
  it("caps the number of terms", () => {
    expect(searchTerms("a1 b2 c3 d4 e5 f6 g7")).toHaveLength(5);
  });
  it("handles empty input", () => {
    expect(searchTerms("")).toEqual([]);
    expect(searchTerms(undefined)).toEqual([]);
  });
});

describe("ilikePattern", () => {
  it("escapes LIKE wildcards so they match literally", () => {
    expect(ilikePattern("100%")).toBe("%100\\%%");
    expect(ilikePattern("a_b")).toBe("%a\\_b%");
    expect(ilikePattern("c\\d")).toBe("%c\\\\d%");
  });
});

describe("groupByStore", () => {
  it("orders stores by their cheapest offer, nulls last", () => {
    const groups = groupByStore([
      { store: "REWE", price: 2.49 },
      { store: "Lidl", price: null },
      { store: "Lidl", price: 1.99 },
      { store: null, price: 0.99 },
      { store: "Penny", price: null },
    ]);
    expect(groups.map(([s]) => s)).toEqual(["Unbekannt", "Lidl", "REWE", "Penny"]);
    expect(groups[1][1].map((o) => o.price)).toEqual([1.99, null]);
  });
});

describe("formatting", () => {
  it("formats dates without timezone shifts", () => {
    expect(formatDateDe("2026-11-21")).toBe("21.11.2026");
    expect(formatDateDe(null)).toBeNull();
    expect(formatDateDe("soon")).toBeNull();
  });
  it("formats euros the German way", () => {
    expect(formatEuro(1.9)).toBe("1,90 €");
    expect(formatEuro("2.5")).toBe("2,50 €");
    expect(formatEuro(null)).toBe("—");
    expect(formatEuro(Number.NaN)).toBe("—");
  });
});
