/**
 * Helpers for the keyword search on /stores.
 *
 * People type the way they think: "ariel pods", "milch 1,5%", "Coca-Cola Zero".
 * A single `ilike %query%` only finds titles containing that exact string, so
 * "ariel pods" missed "Ariel 3in1 Pods". We split into words and require every
 * word to appear (AND), in any order.
 */

const MAX_TERMS = 5;

/**
 * Split a free-text query into search terms.
 * - whitespace separated, case-insensitive duplicates removed
 * - 1-character noise ("&", "-", "x") dropped unless it's all the user typed
 * - capped at MAX_TERMS so a pasted paragraph can't build a huge query
 */
export function searchTerms(q: string | null | undefined): string[] {
  const raw = (q ?? "")
    .replace(/[*()",]/g, " ") // PostgREST syntax chars: `*` is a wildcard there
    .split(/\s+/)
    .map((t) => t.trim())
    .filter(Boolean);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const t of raw) {
    const key = t.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(t);
  }
  const meaningful = out.filter((t) => t.length > 1);
  return (meaningful.length > 0 ? meaningful : out).slice(0, MAX_TERMS);
}

/**
 * `%term%` with LIKE wildcards escaped, so "100%" means a literal percent sign
 * and "_" is an underscore, not "any character".
 */
export function ilikePattern(term: string): string {
  return `%${term.replace(/[\\%_]/g, (c) => `\\${c}`)}%`;
}

type Priced = { store: string | null; price: number | null };

/**
 * Group offers by store, cheapest first inside each store, and stores ordered
 * by their cheapest offer. Offers without a price go last (inside a store) and
 * stores without any price go last overall.
 */
export function groupByStore<T extends Priced>(offers: readonly T[]): [string, T[]][] {
  const byStore = new Map<string, T[]>();
  for (const o of offers) {
    const k = o.store?.trim() || "Unbekannt";
    const list = byStore.get(k);
    if (list) list.push(o);
    else byStore.set(k, [o]);
  }
  const price = (o: T | undefined) => (o?.price == null ? Infinity : Number(o.price));
  for (const list of byStore.values()) list.sort((a, b) => price(a) - price(b));
  return [...byStore.entries()].sort(
    (a, b) => price(a[1][0]) - price(b[1][0]) || a[0].localeCompare(b[0], "de"),
  );
}

/** "2026-11-21" → "21.11.2026" without timezone shifts (no Date parsing). */
export function formatDateDe(iso: string | null | undefined): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? "");
  return m ? `${m[3]}.${m[2]}.${m[1]}` : null;
}

/** "1,99 €" — German number format, never "1.9 €" or "NaN €". */
export function formatEuro(v: number | string | null | undefined): string {
  const n = typeof v === "string" ? Number(v) : v;
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;
}
