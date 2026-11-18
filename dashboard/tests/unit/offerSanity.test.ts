import { describe, expect, it } from "vitest";
import {
  discountTrust,
  FRESHNESS_DAYS,
  freshnessThresholdIso,
  isExpired,
  offerLink,
  todayIso,
} from "@/lib/offerSanity";

describe("discountTrust", () => {
  it("trusts normal discounts and missing ones", () => {
    expect(discountTrust("Milka Schokolade", 30)).toBe("trusted");
    expect(discountTrust("Milka Schokolade", null)).toBe("trusted");
    expect(discountTrust(null, 0)).toBe("trusted");
  });

  it("flags multi-pack unit-price mix-ups", () => {
    expect(discountTrust("Krombacher Pils 20 x 0,5 l Kasten", 75)).toBe("suspect");
    expect(discountTrust("Cola 6x1,5l", 72)).toBe("suspect");
    expect(discountTrust("Wasser 12er Pack", 80)).toBe("suspect");
    // same discount without pack hint is fine
    expect(discountTrust("Bio Äpfel", 75)).toBe("trusted");
  });

  it("treats >85% as suspect and >95% as implausible", () => {
    expect(discountTrust("Bio Äpfel", 90)).toBe("suspect");
    expect(discountTrust("Bio Äpfel", 99)).toBe("implausible");
  });

  it("treats negative or NaN discounts as data errors", () => {
    expect(discountTrust("Butter", -20)).toBe("implausible");
    expect(discountTrust("Butter", Number.NaN)).toBe("implausible");
  });
});

describe("isExpired", () => {
  const noon = new Date("2026-11-18T12:00:00Z");
  it("keeps offers valid today and evergreen offers", () => {
    expect(isExpired("2026-11-18", noon)).toBe(false);
    expect(isExpired("2026-11-30", noon)).toBe(false);
    expect(isExpired(null, noon)).toBe(false);
    expect(isExpired("", noon)).toBe(false);
  });

  it("drops offers that ended yesterday", () => {
    expect(isExpired("2026-11-17", noon)).toBe(true);
  });

  it("uses the Berlin calendar day right after midnight", () => {
    // 00:30 in Berlin on the 19th, still the 18th in UTC: an offer valid
    // until the 18th has ended for a German shopper.
    expect(isExpired("2026-11-18", new Date("2026-11-18T23:30:00Z"))).toBe(true);
    expect(todayIso(new Date("2026-11-18T23:30:00Z"))).toBe("2026-11-19");
  });

  it("accepts full timestamps as valid_to", () => {
    expect(isExpired("2026-11-18T00:00:00+00:00", noon)).toBe(false);
  });
});

describe("freshnessThresholdIso", () => {
  it("is exactly FRESHNESS_DAYS earlier regardless of DST", () => {
    const now = new Date("2026-10-30T12:00:00Z"); // DST ended 5 days earlier
    const t = new Date(freshnessThresholdIso(now));
    expect(now.getTime() - t.getTime()).toBe(FRESHNESS_DAYS * 86_400_000);
  });
});

describe("offerLink", () => {
  it("prefers the real URL", () => {
    expect(offerLink("https://www.kaufda.de/x", "Butter")).toBe("https://www.kaufda.de/x");
  });
  it("falls back to an encoded kaufDA search", () => {
    expect(offerLink("  ", "Käse & Wein")).toBe(
      "https://www.kaufda.de/Angebote/K%C3%A4se%20%26%20Wein",
    );
    expect(offerLink(null, null)).toBe("https://www.kaufda.de");
  });
});
