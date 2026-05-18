import { Search, SearchX } from "lucide-react";
import { Card, EmptyState, OfferRow, PageHeader } from "@/components/ui";
import { applyWeekFilter, excludeExpired, excludeStale, supabase } from "@/lib/supabase";
import { parseWeek, weekRange } from "@/lib/week";

export const revalidate = 60;

type SearchParams = Promise<{ q?: string; week?: string }>;

async function searchOffers(q: string, week: ReturnType<typeof weekRange>) {
  if (!q.trim()) return [];
  let query = supabase
    .from("offers")
    .select("id, title, store, price, original_price, discount_percent, image_url, url, valid_to")
    .eq("is_active", true)
    .ilike("title", `%${q.trim()}%`);
  query = applyWeekFilter(excludeExpired(excludeStale(query)), week);
  const { data } = await query
    .order("price", { ascending: true, nullsFirst: false })
    .limit(100);
  return data ?? [];
}

export default async function StoresPage({ searchParams }: { searchParams: SearchParams }) {
  const { q = "", week: weekParam } = await searchParams;
  const week = weekRange(parseWeek(weekParam));
  const offers = await searchOffers(q, week);

  const byStore = new Map<string, typeof offers>();
  for (const o of offers) {
    const k = o.store ?? "Unbekannt";
    if (!byStore.has(k)) byStore.set(k, []);
    byStore.get(k)!.push(o);
  }
  const stores = [...byStore.entries()].sort((a, b) => {
    const minA = a[1][0]?.price ?? Infinity;
    const minB = b[1][0]?.price ?? Infinity;
    return minA - minB;
  });

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
          placeholder="Suchbegriff…"
          autoFocus
          className="w-full rounded-lg border border-border bg-surface py-2.5 pl-9 pr-3 text-sm placeholder:text-fg-subtle focus:border-accent focus:outline-none"
        />
        {weekParam && <input type="hidden" name="week" value={weekParam} />}
      </form>

      {q && (
        <p className="text-sm text-fg-muted">
          <span className="font-medium text-fg">{offers.length}</span> Treffer in{" "}
          <span className="font-medium text-fg">{stores.length}</span> Märkten
        </p>
      )}

      {!q ? (
        <EmptyState
          icon={<Search className="h-8 w-8" />}
          title="Tippe einen Suchbegriff"
          body="Z. B. „Ariel“ oder „Joghurt“. Die Suche durchsucht die Titel aller aktiven Angebote."
        />
      ) : stores.length === 0 ? (
        <EmptyState
          icon={<SearchX className="h-8 w-8" />}
          title={`Keine Treffer für „${q}“`}
          body="Versuche einen anderen Begriff oder eine generischere Schreibweise."
        />
      ) : (
        <div className="space-y-4">
          {stores.map(([store, items]) => (
            <Card key={store} className="overflow-hidden">
              <header className="flex items-baseline justify-between border-b border-border px-4 py-3">
                <h2 className="font-semibold">{store}</h2>
                <span className="text-sm text-fg-muted">
                  {items.length} Angebote · ab{" "}
                  <span className="font-medium tabular-nums text-fg">
                    {items[0]?.price != null ? `${items[0].price.toFixed(2)} €` : "—"}
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
                    meta={o.valid_to ? `gültig bis ${o.valid_to}` : undefined}
                  />
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
