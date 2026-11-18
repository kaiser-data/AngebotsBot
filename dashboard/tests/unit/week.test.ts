import { describe, expect, it } from "vitest";
import { berlinDate, isoDate, parseWeek, weekRange } from "@/lib/week";

describe("parseWeek", () => {
  it("accepts known keys and falls back to current for junk", () => {
    expect(parseWeek("next")).toBe("next");
    expect(parseWeek("all")).toBe("all");
    expect(parseWeek("NEXT")).toBe("current");
    expect(parseWeek("../etc")).toBe("current");
    expect(parseWeek(undefined)).toBe("current");
    expect(parseWeek(null)).toBe("current");
  });
});

describe("weekRange", () => {
  it("returns Monday–Sunday of the current Berlin week", () => {
    const r = weekRange("current", new Date("2026-11-18T12:00:00Z"))!; // Wednesday
    expect(isoDate(r.from)).toBe("2026-11-16");
    expect(isoDate(r.to)).toBe("2026-11-22");
  });

  it("uses the Berlin day, not UTC, late on Sunday night", () => {
    // Sun 23:30 UTC = Mon 00:30 in Berlin (CET) → already the NEXT week.
    const r = weekRange("current", new Date("2026-11-22T23:30:00Z"))!;
    expect(isoDate(r.from)).toBe("2026-11-23");
  });

  it("handles the DST switch week (last Sunday of October)", () => {
    const r = weekRange("current", new Date("2026-10-25T10:00:00Z"))!; // Sunday, DST ends
    expect(isoDate(r.from)).toBe("2026-10-19");
    expect(isoDate(r.to)).toBe("2026-10-25");
  });

  it("next week crosses month and year boundaries correctly", () => {
    const r = weekRange("next", new Date("2026-12-30T12:00:00Z"))!; // Wednesday
    expect(isoDate(r.from)).toBe("2027-01-04");
    expect(isoDate(r.to)).toBe("2027-01-10");
  });

  it("'all' means no date filter", () => {
    expect(weekRange("all")).toBeNull();
  });
});

describe("berlinDate", () => {
  it("is a day ahead of UTC just after Berlin midnight", () => {
    expect(berlinDate(new Date("2026-07-14T22:30:00Z"))).toBe("2026-07-15"); // CEST
  });
});
