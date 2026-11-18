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

describe("subcategory from kaufDA's path (real paths, Nov 2026)", () => {
  const LG = "Lebensmittel und Getränke";
  const DH = "Drogerie und Haushalt";
  const at = (top: string, tail: string, title = "Aktion") =>
    resolveCategory({ title, category: null, kaufda_category: top, kaufda_category_path: `${top} > Produkte > ${tail}` });

  it.each([
    [LG, "Getränke > Alkoholische Getränke > Bier > Pils", "Hasseröder", "Getränke", "Bier"],
    [LG, "Getränke > Alkoholische Getränke > Wein > Rotwein", "Bordeaux in Holzkiste", "Getränke", "Wein & Sekt"],
    [LG, "Getränke > Alkoholische Getränke > Schaumwein", "Rotkäppchen", "Getränke", "Wein & Sekt"],
    [LG, "Getränke > Heißgetränk > Kaffee", "Krönung", "Getränke", "Kaffee & Tee"],
    [LG, "Lebensmittel > Milchprodukte > Käse > Frischkäse", "Philadelphia", "Lebensmittel", "Milchprodukte & Käse"],
    [LG, "Lebensmittel > Fertiggerichte > Tiefkühlkost", "Steinofen", "Lebensmittel", "Tiefkühl"],
    [LG, "Lebensmittel > Bio Lebensmittel > Bio Obst", "Bio Äpfel", "Lebensmittel", "Obst & Gemüse"],
    [DH, "Parfümerie > Düfte > Eau de Toilette", "Hugo Boss", "Drogerie & Kosmetik", "Parfum & Düfte"],
    [DH, "Haushalt > Textilreinigung > Weichspüler", "Lenor", "Haushalt & Reinigung", "Waschmittel"],
    [LG, "Lebensmittel > Bio Lebensmittel > Bio Getränke > Bio Limonade > Bionade", "BIONADE", "Getränke", "Wasser & Säfte"],
    [LG, "Getränke > Alkoholische Getränke > Punsch", "Glühpunsch", "Getränke", "Spirituosen"],
  ])("%s > %s (%s)", (top, tail, title, bucket, sub) => {
    expect(at(top, tail, title)).toMatchObject({ bucket, subcategory: sub, source: "kaufda" });
  });

  it("perfume is no longer filed under Haushalt", () => {
    expect(at(DH, "Marken Parfum > Axe").bucket).toBe("Drogerie & Kosmetik");
    expect(at(DH, "Marken Drogerie > Nivea").bucket).toBe("Drogerie & Kosmetik");
  });

  it("maps the top levels the dashboard used to miss", () => {
    const top = (t: string) => resolveCategory({ title: "x", category: null, kaufda_category: t });
    expect(top("Spielzeug")).toMatchObject({ bucket: "Baby & Kind", subcategory: "Spielzeug" });
    expect(top("Apotheke")).toMatchObject({ bucket: "Drogerie & Kosmetik", subcategory: "Gesundheit & Apotheke" });
    expect(top("Büro- und Schreibwaren")).toMatchObject({ bucket: "Sonstiges", subcategory: "Büro & Schreibwaren" });
  });

  it("falls back to the title when the path is too vague", () => {
    // "Marken Lebensmittel > Ferrero" says nothing about the product type.
    expect(at(LG, "Marken Lebensmittel > Ferrero", "Kinder Schokolade 300g").subcategory).toBe("Süßwaren & Snacks");
  });
});
