import { describe, expect, it } from "vitest";
import { classify } from "@/lib/categoryHeuristic";
import { ALL_SUBCATEGORIES } from "@/lib/taxonomy";

const cases: [title: string, bucket: string, sub: string][] = [
  // Brands
  ["Ariel Universal Waschpulver 80 WL", "Haushalt & Reinigung", "Waschmittel"],
  ["Apple iPhone 15 128 GB", "Elektronik & Multimedia", "Smartphone & Tablet"],
  ["Kinder Schokolade 300g", "Lebensmittel", "Süßwaren & Snacks"],
  ["Whiskas Katzenfutter 12x85g", "Tier", "Katze"],
  // German compounds: the head noun is LAST
  ["Tomatenketchup 500ml", "Lebensmittel", "Grundnahrung & Konserven"],
  ["Kartoffelchips Paprika", "Lebensmittel", "Süßwaren & Snacks"],
  ["Blumenkohl Stück", "Lebensmittel", "Obst & Gemüse"],
  ["Grillwürstchen 400g", "Lebensmittel", "Fleisch & Wurst"],
  ["Grillkäse 2 Stück", "Lebensmittel", "Milchprodukte & Käse"],
  ["Pflanzenöl 1 l", "Lebensmittel", "Grundnahrung & Konserven"],
  ["Zitronentee 20 Beutel", "Getränke", "Kaffee & Tee"],
  ["Apfelsaft naturtrüb", "Getränke", "Wasser & Säfte"],
  ["Basmatireis 1 kg", "Lebensmittel", "Grundnahrung & Konserven"],
  ["Wildschwein Gulasch", "Lebensmittel", "Fleisch & Wurst"],
  ["Weizenbier 0,5 l", "Getränke", "Bier"],
  ["Sonnenmilch LSF 30", "Drogerie & Kosmetik", "Körperpflege"],
  // Whole word beats substring
  ["Fleckensalz Oxi", "Haushalt & Reinigung", "Waschmittel"],
  ["Reis 1kg", "Lebensmittel", "Grundnahrung & Konserven"],
  ["Eiscreme Vanille", "Lebensmittel", "Süßwaren & Snacks"],
  // Previously misfiled ("Tabletten" ≠ tablet computer, "Orangensaft" ≠ fruit)
  ["Vitamin D3 Tabletten", "Drogerie & Kosmetik", "Gesundheit & Apotheke"],
  ["Magnesium Brausetabletten", "Drogerie & Kosmetik", "Gesundheit & Apotheke"],
  ["Hohes C Orangensaft", "Getränke", "Wasser & Säfte"],
  ["Sonnenblumenöl 1 l", "Lebensmittel", "Grundnahrung & Konserven"],
  ["Leberkäse", "Lebensmittel", "Fleisch & Wurst"],
  ["Fleischkäse", "Lebensmittel", "Fleisch & Wurst"],
  ["Blumenerde 40 l", "Garten & Heimwerken", "Pflanzen & Garten"],
  // Everyday items that used to fall through to "Sonstiges"
  ["Weihenstephaner Hefeweißbier", "Getränke", "Bier"],
  ["Jacobs Krönung 500g", "Getränke", "Kaffee & Tee"],
  ["Toilettenpapier 3-lagig 10 Rollen", "Haushalt & Reinigung", "Reinigung"],
  ["Spülmaschinen Tabs", "Haushalt & Reinigung", "Reinigung"],
  ["Pizza Margherita tiefgefroren", "Lebensmittel", "Tiefkühl"],
  ["Wiener Würstchen", "Lebensmittel", "Fleisch & Wurst"],
  ["Bio Eier 10 Stück", "Lebensmittel", "Milchprodukte & Käse"],
  // Umlauts / ASCII spellings
  ["Rasenmäher Benzin", "Garten & Heimwerken", "Gartenwerkzeug"],
  ["Rasenmaeher Benzin", "Garten & Heimwerken", "Gartenwerkzeug"],
];

describe("classify — typical German offer titles", () => {
  it.each(cases)("%s → %s / %s", (title, bucket, sub) => {
    expect(classify(title)).toEqual({ bucket, subcategory: sub });
  });
});

describe("classify — false-positive traps", () => {
  it("'Kinder' alone is not Ferrero candy", () => {
    expect(classify("Kinder-Fahrrad 20 Zoll").bucket).not.toBe("Lebensmittel");
    expect(classify("Kinderschuhe Gr. 30").bucket).not.toBe("Lebensmittel");
  });
  it("'Gourmet' alone is not cat food", () => {
    expect(classify("Gourmet Burger 4 Stück").bucket).not.toBe("Tier");
    expect(classify("Gourmet Gold Katzennahrung").bucket).toBe("Tier");
  });
  it("'Schalotten' are vegetables, not a scarf", () => {
    expect(classify("Schalotten 500g").bucket).not.toBe("Mode, Sport & Freizeit");
  });
  it("'Blume ' is whole-word only", () => {
    expect(classify("Blume im Topf").subcategory).toBe("Pflanzen & Garten");
  });
  it("'Aktionspreis' does not make something rice", () => {
    expect(classify("Aktionspreis Gartenstuhl").subcategory).toBe("Gartenmöbel");
  });
});

describe("classify — robustness", () => {
  it("handles empty / null input", () => {
    expect(classify(null)).toEqual({ bucket: "Sonstiges", subcategory: "Sonstige" });
    expect(classify("")).toEqual({ bucket: "Sonstiges", subcategory: "Sonstige" });
    expect(classify("   ")).toEqual({ bucket: "Sonstiges", subcategory: "Sonstige" });
  });
  it("is case-insensitive", () => {
    expect(classify("TOMATENKETCHUP")).toEqual(classify("tomatenketchup"));
  });
  it("uses the kaufDA keyword when the title says nothing", () => {
    expect(classify("Aktion der Woche", "fischstaebchen").bucket).toBe("Lebensmittel");
  });
  it("only ever returns pairs that exist in taxonomy.json", () => {
    const valid = new Set(ALL_SUBCATEGORIES.map((p) => `${p.bucket}|${p.subcategory}`));
    for (const [t] of cases) {
      const c = classify(t);
      expect(valid.has(`${c.bucket}|${c.subcategory}`), `${t}: ${c.bucket}|${c.subcategory}`).toBe(true);
    }
  });
});
