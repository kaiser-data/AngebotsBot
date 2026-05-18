import { ArrowRight, Layers, ChartLine, Store } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { Card, OfferRow, PageHeader, Stat } from "@/components/ui";
import { applyWeekFilter, excludeExpired, excludeStale, supabase } from "@/lib/supabase";
import { parseWeek, weekRange, type WeekRange } from "@/lib/week";

export const revalidate = 60;

type SearchParams = Promise<{ week?: string }>;

async function getStats(week: WeekRange | null) {
  let countQ = supabase.from("offers").select("id", { count: "exact", head: true }).eq("is_active", true);
  countQ = applyWeekFilter(excludeExpired(excludeStale(countQ)), week);

  let storeQ = supabase.from("offers").select("store").eq("is_active", true).not("store", "is", null);
  storeQ = applyWeekFilter(excludeExpired(excludeStale(storeQ)), week);

  let recentQ = supabase
    .from("offers")
    .select("id, title, store, price, original_price, discount_percent, image_url, url, scraped_at")
    .eq("is_active", true);
  recentQ = applyWeekFilter(excludeExpired(excludeStale(recentQ)), week);

  const [offersRes, storesRes, recentRes, scoredRes] = await Promise.all([
    countQ,
    storeQ,
    recentQ.order("scraped_at", { ascending: false }).limit(8),
    supabase
      .from("offer_deal_score")
      .select("offer_id", { count: "exact", head: true })
      .not("price_percentile", "is", null),
  ]);

  const storeSet = new Set((storesRes.data ?? []).map((r) => r.store));

  return {
    activeOffers: offersRes.count ?? 0,
    storeCount: storeSet.size,
    scoredOffers: scoredRes.count ?? 0,
    recent: recentRes.data ?? [],
  };
}

export default async function HomePage({ searchParams }: { searchParams: SearchParams }) {
  const { week: weekParam } = await searchParams;
  const week = weekRange(parseWeek(weekParam));
  const { activeOffers, storeCount, scoredOffers, recent } = await getStats(week);

  return (
    <div className="space-y-10">
      <PageHeader
        title="Übersicht"
        subtitle={
          week
            ? `${week.label} · ${week.from.toLocaleDateString("de-DE")} – ${week.to.toLocaleDateString("de-DE")}`
            : "Aktuelle Angebote, Trends und Preisvergleiche aus deinen kaufDA-Crawls."
        }
      />

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="Aktive Angebote" value={activeOffers.toLocaleString("de-DE")} />
        <Stat label="Märkte" value={storeCount.toLocaleString("de-DE")} />
        <Stat
          label="Mit Deal-Score"
          value={scoredOffers.toLocaleString("de-DE")}
          hint={scoredOffers === 0 ? "wächst mit jedem Scrape" : undefined}
        />
      </section>

      <section className="grid gap-3 sm:grid-cols-3">
        <NavCard
          href="/stores"
          icon={<Store className="h-5 w-5" />}
          title="Märkte vergleichen"
          body="Suche ein Produkt und sieh den Preis bei jedem Markt."
        />
        <NavCard
          href="/categories"
          icon={<Layers className="h-5 w-5" />}
          title="Nach Kategorie"
          body="Zehn klare Bereiche. Wöchentlich neu klassifiziert."
        />
        <NavCard
          href="/deals"
          icon={<ChartLine className="h-5 w-5" />}
          title="Deal score"
          body="Wo ist es gerade besonders günstig — verglichen mit der Historie?"
        />
      </section>

      <section>
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-lg font-semibold tracking-tight">Zuletzt gesehen</h2>
          <Link href="/stores" className="text-sm text-fg-muted hover:text-fg">
            alle ansehen →
          </Link>
        </div>
        <Card className="overflow-hidden">
          <ul className="divide-y divide-border">
            {recent.map((o) => (
              <OfferRow
                key={o.id}
                title={o.title}
                store={o.store}
                url={o.url}
                imageUrl={o.image_url}
                price={o.price}
                originalPrice={o.original_price}
                discountPercent={o.discount_percent}
              />
            ))}
          </ul>
        </Card>
      </section>
    </div>
  );
}

function NavCard({
  href,
  icon,
  title,
  body,
}: {
  href: string;
  icon: ReactNode;
  title: string;
  body: string;
}) {
  return (
    <Link
      href={href}
      className="group block rounded-xl border border-border bg-surface p-5 transition hover:border-border-strong hover:bg-surface-hover"
    >
      <div className="flex items-center justify-between">
        <span className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-accent/15 text-accent">
          {icon}
        </span>
        <ArrowRight className="h-4 w-4 text-fg-subtle transition group-hover:translate-x-0.5 group-hover:text-fg" />
      </div>
      <div className="mt-4 text-base font-semibold">{title}</div>
      <p className="mt-1 text-sm text-fg-muted">{body}</p>
    </Link>
  );
}
