import { AlertTriangle, Search, SearchX } from "lucide-react";
import { Card, EmptyState, OfferRow, PageHeader } from "@/components/ui";
import { applyWeekFilter, excludeExpired, excludeStale, supabase } from "@/lib/supabase";
import { formatDateDe, formatEuro, groupByStore, ilikePattern, searchTerms } from "@/lib/search";
import { parseWeek, weekRange } from "@/lib/week";

export const revalidate = 60;

type SearchParams = Promise<{ q?: string; week?: string }>;

const MAX_RESULTS = 200;

/**
 * Every word must appear in the title, in any order: "ariel pods" finds
 * "Ariel 3in1 Pods". Errors are returned, not swallowed — otherwise a database
 * hiccup reads as "Keine Treffer".
 */
async function searchOffers(q: string, week: ReturnType<typeof weekRange>) {
  const terms = searchTerms(q);
  if (terms.length === 0) return { offers: [], error: null, terms };
  let query = supabase
    .from("offers")
    .select("id, title, store, price, original_price, discount_percent, image_url, url, valid_to")
    .eq("is_active", true);
  for (const t of terms) query = query.ilike("title", ilikePattern(t));
  query = applyWeekFilter(excludeExpired(excludeStale(query)), week);
  const { data, error } = await query
    .order("price", { ascending: true, nullsFirst: false })
    .limit(MAX_RESULTS);
  return { offers: data ?? [], error: error?.message ?? null, terms };
}

export default async function StoresPage({ searchParams }: { searchParams: SearchParams }) {
  const { q = "", week: weekParam } = await searchParams;
  const week = weekRange(parseWeek(weekParam));
  const { offers, error, terms } = await searchOffers(q, week);
  const stores = groupByStore(offers);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Märkte vergleichen"
        subtitle={
          week
            ? `Gültig in ${week.label.toLowerCase()} (${week.from.toLocaleDateString("de-DE")} – ${week.to.toLocaleDateString("de-DE")}). Suche per Stichwort.`
            : "Über alle aktiven Angebote hinweg. Suche per Stichwort."
        }
      />

      <form action="/stores" method="get" className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle" />
        <input
          name="q"
          defaultValue={q}
          type="search"
          enterKeyHint="search"
          aria-label="Produkt suchen"
          placeholder="Produkt suchen, z. B. „Ariel Pods“ oder „Butter“…"
          autoFocus={!q}
          className="w-full rounded-lg border border-border bg-surface py-2.5 pl-9 pr-3 text-sm placeholder:text-fg-subtle focus:border-accent focus:outline-none"
        />
        {weekParam && <input type="hidden" name="week" value={weekParam} />}
      </form>

      {terms.length > 0 && !error && (
        <p className="text-sm text-fg-muted">
          <span className="font-medium text-fg">
            {offers.length >= MAX_RESULTS ? `${MAX_RESULTS}+` : offers.length}
          </span>{" "}
          Treffer in <span className="font-medium text-fg">{stores.length}</span>{" "}
          {stores.length === 1 ? "Markt" : "Märkten"}
          {offers.length >= MAX_RESULTS && " — die günstigsten werden angezeigt, verfeinere die Suche für mehr"}
        </p>
      )}

      {error ? (
        <EmptyState
          icon={<AlertTriangle className="h-8 w-8" />}
          title="Suche gerade nicht möglich"
          body="Die Datenbank antwortet nicht. Bitte in einem Moment erneut versuchen."
        />
      ) : terms.length === 0 ? (
        <EmptyState
          icon={<Search className="h-8 w-8" />}
          title="Tippe einen Suchbegriff"
          body="Z. B. „Ariel“ oder „Joghurt“. Die Suche durchsucht die Titel aller aktiven Angebote."
        />
      ) : stores.length === 0 ? (
        <EmptyState
          icon={<SearchX className="h-8 w-8" />}
          title={`Keine Treffer für „${q}“`}
          body={
            terms.length > 1
              ? "Alle Wörter müssen im Titel vorkommen — versuche es mit weniger Wörtern oder nur dem Markennamen."
              : week
                ? "Versuche einen anderen Begriff, oder suche unter „Alle“ Wochen."
                : "Versuche einen anderen Begriff oder eine allgemeinere Schreibweise."
          }
        />
      ) : (
        <div className="space-y-4">
          {stores.map(([store, items]) => (
            <Card key={store} className="overflow-hidden">
              <header className="flex items-baseline justify-between border-b border-border px-4 py-3">
                <h2 className="font-semibold">{store}</h2>
                <span className="text-sm text-fg-muted">
                  {items.length} {items.length === 1 ? "Angebot" : "Angebote"} · ab{" "}
                  <span className="font-medium tabular-nums text-fg">
                    {formatEuro(items[0]?.price)}
                  </span>
                </span>
              </header>
              <ul className="divide-y divide-border">
                {items.slice(0, 8).map((o) => (
                  <OfferRow
                    key={o.id}
                    title={o.title}
                    store={null}
                    url={o.url}
                    imageUrl={o.image_url}
                    price={o.price}
                    originalPrice={o.original_price}
                    discountPercent={o.discount_percent}
                    meta={o.valid_to ? `gültig bis ${formatDateDe(o.valid_to)}` : undefined}
                  />
                ))}
              </ul>
              {items.length > 8 && (
                <p className="border-t border-border px-4 py-2 text-xs text-fg-subtle">
                  + {items.length - 8} weitere bei {store} — Suche verfeinern, um sie zu sehen
                </p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
