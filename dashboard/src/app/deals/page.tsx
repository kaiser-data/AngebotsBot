import { ArrowLeft, TrendingDown } from "lucide-react";
import Link from "next/link";
import { Badge, Card, EmptyState, PageHeader, Stat } from "@/components/ui";
import { supabase } from "@/lib/supabase";
import { PriceSparkline } from "./PriceSparkline";

export const revalidate = 60;

type SearchParams = Promise<{ offer?: string }>;

async function getTopDeals() {
  const { data } = await supabase
    .from("offer_deal_score")
    .select("offer_id, external_id, title, store, category, current_price, avg_price_90d, price_percentile, observation_count")
    .not("price_percentile", "is", null)
    .order("price_percentile", { ascending: true, nullsFirst: false })
    .limit(30);
  return data ?? [];
}

async function getOfferDetail(offerId: string) {
  const [{ data: score }, { data: history }] = await Promise.all([
    supabase.from("offer_deal_score").select("*").eq("offer_id", offerId).maybeSingle(),
    supabase
      .from("price_history")
      .select("observed_at, price, loyalty_price")
      .eq("offer_id", offerId)
      .order("observed_at", { ascending: true })
      .limit(500),
  ]);
  return { score, history: history ?? [] };
}

function pctTone(p: number | null | undefined) {
  if (p == null) return "neutral" as const;
  if (p <= 15) return "positive" as const;
  if (p <= 35) return "accent" as const;
  if (p <= 65) return "warning" as const;
  return "neutral" as const;
}

function fmtEUR(v: number | null | undefined) {
  return v != null ? `${Number(v).toFixed(2)} €` : "—";
}

export default async function DealsPage({ searchParams }: { searchParams: SearchParams }) {
  const { offer = "" } = await searchParams;

  if (offer) {
    const { score, history } = await getOfferDetail(offer);
    return (
      <div className="space-y-8">
        <Link
          href="/deals"
          className="inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg"
        >
          <ArrowLeft className="h-4 w-4" />
          Zurück zur Bestenliste
        </Link>

        <PageHeader
          title={score?.title ?? "Offer"}
          subtitle={`${score?.store ?? "—"} · ${score?.category ?? "ohne Kategorie"}`}
        />

        <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Aktuell" value={fmtEUR(score?.current_price)} />
          <Stat label="Ø 90 Tage" value={fmtEUR(score?.avg_price_90d)} />
          <Stat
            label="Percentil"
            value={
              score?.price_percentile != null
                ? `${score.price_percentile.toFixed(0)}%`
                : "—"
            }
            hint="niedriger = besser"
          />
          <Stat
            label="Datenpunkte"
            value={score?.observation_count?.toString() ?? "0"}
            hint="letzte 90 Tage"
          />
        </section>

        <Card className="p-5">
          <h2 className="mb-4 text-sm font-medium text-fg-muted">Preisverlauf</h2>
          {history.length >= 2 ? (
            <PriceSparkline data={history} />
          ) : (
            <p className="text-sm text-fg-muted">
              Noch nicht genug Datenpunkte ({history.length}). Mit jedem Scrape kommt einer dazu.
            </p>
          )}
        </Card>
      </div>
    );
  }

  const deals = await getTopDeals();

  return (
    <div className="space-y-8">
      <PageHeader
        title="Deal score"
        subtitle="Angebote, die aktuell günstiger sind als der Schnitt der letzten 90 Tage. Niedrigeres Percentil = besseres Schnäppchen."
      />

      {deals.length === 0 ? (
        <EmptyState
          icon={<TrendingDown className="h-8 w-8" />}
          title="Noch keine Deal-Scores"
          body={
            <>
              Die <code className="rounded bg-surface-hover px-1 py-0.5">price_history</code>{" "}
              muss erst gefüllt werden — mindestens 3 Beobachtungen pro Angebot. Lass den Scraper
              ein paar Mal laufen.
            </>
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <ul className="divide-y divide-border">
            {deals.map((d) => (
              <li key={d.offer_id}>
                <Link
                  href={`/deals?offer=${d.offer_id}`}
                  className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-surface-hover"
                >
                  <div className="w-14 flex-shrink-0">
                    <Badge tone={pctTone(d.price_percentile)}>
                      {d.price_percentile != null ? `${d.price_percentile.toFixed(0)}%` : "—"}
                    </Badge>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{d.title}</div>
                    <div className="mt-0.5 text-xs text-fg-muted">
                      {d.store ?? "—"} · {d.category ?? "ohne Kategorie"} · {d.observation_count}{" "}
                      Datenpunkte
                    </div>
                  </div>
                  <div className="text-right tabular-nums">
                    <div className="text-sm font-semibold">{fmtEUR(d.current_price)}</div>
                    <div className="text-xs text-fg-subtle">Ø {fmtEUR(d.avg_price_90d)}</div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
