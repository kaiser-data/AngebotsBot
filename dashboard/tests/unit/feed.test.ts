import { describe, expect, it } from "vitest";
import { classifyFeedRow, pickBargains, pickMine, relativeTime, type FeedRow } from "@/lib/feed";
import { DEFAULT_PREFS, type Prefs } from "@/lib/prefs";

let n = 0;
function row(title: string, discount: number | null, extra: Partial<FeedRow> = {}): FeedRow {
  n += 1;
  return {
    id: `o${n}`, title, store: "Lidl", category: null, price: 1.99, original_price: null,
    discount_percent: discount, image_url: null, url: "", last_seen_at: null, ...extra,
  };
}

const prefs: Prefs = { ...DEFAULT_PREFS, buckets: ["Lebensmittel", "Getränke"], bargainMinDiscount: 40, onboarded: true };

describe("pickMine", () => {
  it("keeps only preferred buckets, best discount first", () => {
    const rows = [row("Butter 250g", 20), row("Bohrmaschine", 50), row("Apfelsaft 1l", 35)].map(classifyFeedRow);
    expect(pickMine(rows, prefs).map((o) => o.title)).toEqual(["Apfelsaft 1l", "Butter 250g"]);
  });

  it("does not let a multi-pack unit-price glitch outrank a real deal", () => {
    const rows = [row("Mineralwasser 12x1,5l Kasten", 80), row("Bio Joghurt 500g", 45)].map(classifyFeedRow);
    expect(pickMine(rows, prefs)[0].title).toBe("Bio Joghurt 500g");
  });

  it("drops implausible discounts to the bottom", () => {
    const rows = [row("Butter 250g", 99), row("Käse Gouda", 10)].map(classifyFeedRow);
    expect(pickMine(rows, prefs).map((o) => o.title)).toEqual(["Käse Gouda", "Butter 250g"]);
  });

  it("boosts offers at a 90-day price low", () => {
    const a = classifyFeedRow(row("Butter 250g", 30));
    const b = classifyFeedRow(row("Käse Gouda", 20));
    expect(pickMine([a, b], prefs, new Map([[b.id, 5]]))[0].id).toBe(b.id);
  });

  it("uses kaufDA's taxonomy, so the feed matches the categories page", () => {
    const r = classifyFeedRow(row("Aktion der Woche", 30, {
      kaufda_category: "Lebensmittel und Getränke",
      kaufda_category_path: "Lebensmittel und Getränke > Produkte > Getränke > Saft",
    }));
    expect(r.bucket).toBe("Getränke");
    expect(pickMine([r], prefs)).toHaveLength(1);
  });
});

describe("pickBargains", () => {
  it("shows only big, trusted discounts outside the user's buckets", () => {
    const rows = [
      row("Bohrmaschine", 50),            // yes
      row("Akkuschrauber", 30),           // below threshold
      row("Butter 250g", 70),             // own bucket → not a "bargain"
      row("Staubsauger", 99),             // implausible
    ].map(classifyFeedRow);
    expect(pickBargains(rows, prefs).map((o) => o.title)).toEqual(["Bohrmaschine"]);
  });
  it("is off when the radar is off", () => {
    expect(pickBargains([classifyFeedRow(row("Bohrmaschine", 60))], { ...prefs, bargainMinDiscount: null })).toEqual([]);
  });
});

describe("relativeTime", () => {
  const now = Date.parse("2026-11-18T12:00:00Z");
  it("formats in German", () => {
    expect(relativeTime(null, now)).toBe("unbekannt");
    expect(relativeTime("garbage", now)).toBe("unbekannt");
    expect(relativeTime("2026-11-18T11:59:50Z", now)).toBe("gerade eben");
    expect(relativeTime("2026-11-18T11:15:00Z", now)).toBe("vor 45 min");
    expect(relativeTime("2026-11-18T07:00:00Z", now)).toBe("vor 5 h");
    expect(relativeTime("2026-11-15T12:00:00Z", now)).toBe("vor 3 Tagen");
  });
  it("never shows negative times for clocks slightly ahead", () => {
    expect(relativeTime("2026-11-18T12:05:00Z", now)).toBe("gerade eben");
  });
});

describe("offers with only an old price", () => {
  it("rank by the discount the badge shows", () => {
    const r = classifyFeedRow(row("Senseo Kaffeepads", null, { price: 1.99, original_price: 3.99 }));
    expect(r.eff).toBe(50);
  });
});
