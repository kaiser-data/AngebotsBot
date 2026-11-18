import { describe, expect, it } from "vitest";
import { bucketFromKaufda } from "@/lib/kaufdaTaxonomy";
import { resolveCategory } from "@/lib/resolveCategory";
import { SUBCATEGORIES } from "@/lib/taxonomy";

describe("bucketFromKaufda", () => {
  it("maps unambiguous top levels", () => {
    expect(bucketFromKaufda("Tierbedarf und Tierfutter", null)).toBe("Tier");
  });
  it("splits ambiguous top levels via level 3", () => {
    const top = "Lebensmittel und Getränke";
    expect(bucketFromKaufda(top, `${top} > Produkte > Getränke > Bier`)).toBe("Getränke");
    expect(bucketFromKaufda(top, `${top} > Produkte > Marken Lebensmittel > X`)).toBe("Lebensmittel");
    expect(bucketFromKaufda(top, null)).toBe("Lebensmittel");
    expect(bucketFromKaufda("Drogerie und Haushalt", "Drogerie und Haushalt > P > Drogerie > Deo")).toBe(
      "Drogerie & Kosmetik",
    );
  });
  it("tolerates whitespace and returns null for unknown/empty", () => {
    expect(bucketFromKaufda("  Baby und Kinder ", null)).toBe("Baby & Kind");
    expect(bucketFromKaufda("Irgendwas Neues", null)).toBeNull();
    expect(bucketFromKaufda("", null)).toBeNull();
    expect(bucketFromKaufda(null, null)).toBeNull();
  });
});

describe("resolveCategory", () => {
  it("prefers kaufDA over LLM over heuristic", () => {
    const row = { title: "Krombacher Pils", category: null, kaufda_category: "Lebensmittel und Getränke", kaufda_category_path: "Lebensmittel und Getränke > P > Getränke > Bier" };
    expect(resolveCategory(row, { category: "Lebensmittel", subcategory: "Fisch" })).toMatchObject({
      bucket: "Getränke",
      subcategory: "Bier",
      source: "kaufda",
    });
    expect(resolveCategory({ title: "Krombacher Pils", category: null }, { category: "Getränke", subcategory: "Bier" }).source).toBe("llm");
    expect(resolveCategory({ title: "Krombacher Pils", category: null }).source).toBe("heuristic");
  });

  it("never pairs a bucket with another bucket's subcategory", () => {
    // kaufDA says Getränke, the title heuristic says Fleisch & Wurst.
    const r = resolveCategory({
      title: "Bierschinken 200g",
      category: null,
      kaufda_category: "Lebensmittel und Getränke",
      kaufda_category_path: "Lebensmittel und Getränke > P > Getränke > Bier",
    });
    expect(r.bucket).toBe("Getränke");
    expect(SUBCATEGORIES["Getränke"]).toContain(r.subcategory);
  });

  it("ignores an LLM answer that isn't in the taxonomy", () => {
    const r = resolveCategory({ title: "Apfelsaft", category: null }, { category: "Food", subcategory: "Juice" });
    expect(r).toMatchObject({ bucket: "Getränke", subcategory: "Wasser & Säfte", source: "heuristic" });
  });

  it("drops an LLM subcategory that belongs to a different bucket", () => {
    const r = resolveCategory({ title: "x", category: null }, { category: "Tier", subcategory: "Bier" });
    expect(r.bucket).toBe("Tier");
    expect(SUBCATEGORIES["Tier"]).toContain(r.subcategory);
  });
});
