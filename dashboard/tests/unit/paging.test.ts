import { describe, expect, it } from "vitest";
import { fetchAllRows, MAX_PAGES, PAGE_SIZE } from "@/lib/paging";

/** Fake table of `total` rows served in PostgREST-style pages. */
function table(total: number, failAt?: number) {
  const calls: number[] = [];
  const page = (from: number, to: number) => {
    calls.push(from);
    if (failAt != null && from >= failAt) {
      return Promise.resolve({ data: null, error: { message: "statement timeout" } });
    }
    const end = Math.min(to + 1, total);
    const data = from < total ? Array.from({ length: end - from }, (_, i) => from + i) : [];
    return Promise.resolve({ data, error: null });
  };
  return { page, calls };
}

describe("fetchAllRows", () => {
  it("returns every row past the 1000-row PostgREST cap", async () => {
    const { page } = table(2500);
    const r = await fetchAllRows(page);
    expect(r.rows).toHaveLength(2500);
    expect(new Set(r.rows).size).toBe(2500);
    expect(r).toMatchObject({ error: null, truncated: false });
  });

  it("handles an exact multiple of the page size", async () => {
    const r = await fetchAllRows(table(PAGE_SIZE * 2).page);
    expect(r.rows).toHaveLength(PAGE_SIZE * 2);
    expect(r.truncated).toBe(false);
  });

  it("handles an empty table", async () => {
    expect((await fetchAllRows(table(0).page)).rows).toEqual([]);
  });

  it("reports errors instead of a silently short list", async () => {
    const r = await fetchAllRows(table(5000, 1000).page);
    expect(r.error).toBe("statement timeout");
  });

  it("turns a rejected request into an error", async () => {
    const r = await fetchAllRows(() => Promise.reject(new Error("fetch failed")));
    expect(r.error).toBe("fetch failed");
  });

  it("says when it hit the page cap", async () => {
    const r = await fetchAllRows(table(PAGE_SIZE * MAX_PAGES + 5).page);
    expect(r.truncated).toBe(true);
  });
});
