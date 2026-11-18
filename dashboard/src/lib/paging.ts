/**
 * PostgREST caps every response at 1000 rows (`max-rows`), regardless of what
 * `.limit()` asks for — so `.limit(20000)` silently returns the first 1000 and
 * the caller believes it saw everything. Page through with `.range()` instead.
 *
 * Pages go out in parallel batches rather than one at a time: the whole ~6k-row
 * working set comes back in well under a second that way, versus several
 * seconds sequentially.
 *
 * Kept free of the Supabase client so it can be unit-tested without env vars.
 */
export const PAGE_SIZE = 1000;
const BATCH = 8;
export const MAX_PAGES = 24;

type Page<T> = PromiseLike<{ data: T[] | null; error: { message: string } | null }>;

export async function fetchAllRows<T>(
  page: (from: number, to: number) => Page<T>,
): Promise<{ rows: T[]; error: string | null; truncated: boolean }> {
  const rows: T[] = [];

  for (let start = 0; start < MAX_PAGES; start += BATCH) {
    const batch = Array.from({ length: Math.min(BATCH, MAX_PAGES - start) }, (_, i) => {
      const from = (start + i) * PAGE_SIZE;
      return page(from, from + PAGE_SIZE - 1);
    });

    // A rejected promise (network down, fetch aborted) must surface as an
    // error too, not escape as an unhandled exception that blanks the page.
    let settled: Awaited<Page<T>>[];
    try {
      settled = await Promise.all(batch);
    } catch (exc) {
      return { rows, error: exc instanceof Error ? exc.message : String(exc), truncated: false };
    }

    // Surface the failure instead of returning a short list, which reads
    // downstream as "there are only N offers" — that is what rendered zeros.
    const failed = settled.find((r) => r.error);
    if (failed) return { rows, error: failed.error!.message, truncated: false };

    // Stop at the first short page and ignore anything after it: pages past
    // the end are empty, so they must not be read as more data.
    for (const { data } of settled) {
      const n = data?.length ?? 0;
      if (n) rows.push(...data!);
      if (n < PAGE_SIZE) return { rows, error: null, truncated: false };
    }
  }

  return { rows, error: null, truncated: true };
}
