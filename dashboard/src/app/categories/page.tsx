import {
  Apple,
  Baby,
  CupSoda,
  Dog,
  Info,
  Layers,
  Leaf,
  Package,
  Shirt,
  Smartphone,
  SprayCan,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { Card, EmptyState, OfferRow, PageHeader } from "@/components/ui";
import { classify } from "@/lib/categoryHeuristic";
import { applyWeekFilter, excludeExpired, excludeStale, supabase } from "@/lib/supabase";
import { BUCKETS, SUBCATEGORIES, type Bucket } from "@/lib/taxonomy";
import { parseWeek, weekRange, type WeekRange } from "@/lib/week";

export const revalidate = 60;

type SearchParams = Promise<{ cat?: string; sub?: string; week?: string }>;

const ICONS: Record<Bucket, ReactNode> = {
  "Lebensmittel": <Apple className="h-4 w-4" />,
  "Getränke": <CupSoda className="h-4 w-4" />,
  "Drogerie & Kosmetik": <SprayCan className="h-4 w-4" />,
  "Haushalt & Reinigung": <Sparkles className="h-4 w-4" />,
  "Baby & Kind": <Baby className="h-4 w-4" />,
  "Tier": <Dog className="h-4 w-4" />,
  "Garten & Heimwerken": <Leaf className="h-4 w-4" />,
  "Elektronik & Multimedia": <Smartphone className="h-4 w-4" />,
  "Mode, Sport & Freizeit": <Shirt className="h-4 w-4" />,
  "Sonstiges": <Package className="h-4 w-4" />,
};

type Source = "llm" | "heuristic";

type AggRow = {
  title: string | null;
  category: string | null;
  llm_categories:
    | { category: string; subcategory: string | null }[]
    | { category: string; subcategory: string | null }
    | null;
};

/** Fetch every active offer with its title, raw kaufda category, and LLM classification. */
async function fetchOffers(week: WeekRange | null): Promise<AggRow[]> {
  let q = supabase
    .from("offers")
    .select("id, title, category, llm_categories:offer_latest_category(category, subcategory)")
    .eq("is_active", true);
  q = applyWeekFilter(excludeExpired(excludeStale(q)), week);
  const { data } = await q.limit(20000);
  return (data ?? []) as AggRow[];
}

function pickLLM(row: AggRow) {
  return Array.isArray(row.llm_categories) ? row.llm_categories[0] : row.llm_categories;
}

type Aggregates = {
  source: Source;
  bucketCounts: Map<Bucket, number>;
  subCounts: Map<Bucket, Map<string, number>>;
};

function aggregate(rows: AggRow[]): Aggregates {
  const bucketCounts = new Map<Bucket, number>();
  const subCounts = new Map<Bucket, Map<string, number>>();
  for (const b of BUCKETS) {
    bucketCounts.set(b, 0);
    subCounts.set(b, new Map());
  }

  const llmRows = rows.filter((r) => pickLLM(r));
  if (llmRows.length > 0) {
    for (const r of rows) {
      const llm = pickLLM(r);
      if (!llm || !BUCKETS.includes(llm.category as Bucket)) continue;
      const b = llm.category as Bucket;
      bucketCounts.set(b, (bucketCounts.get(b) ?? 0) + 1);
      const sub = (llm.subcategory ?? "").trim();
      if (sub && (SUBCATEGORIES[b] as readonly string[]).includes(sub)) {
        const m = subCounts.get(b)!;
        m.set(sub, (m.get(sub) ?? 0) + 1);
      }
    }
    return { source: "llm", bucketCounts, subCounts };
  }

  for (const r of rows) {
    if (!r.title && !r.category) continue;
    const { bucket, subcategory } = classify(r.title, r.category);
    bucketCounts.set(bucket, (bucketCounts.get(bucket) ?? 0) + 1);
    const m = subCounts.get(bucket)!;
    m.set(subcategory, (m.get(subcategory) ?? 0) + 1);
  }
  return { source: "heuristic", bucketCounts, subCounts };
}

async function fetchLLMOffersInBucket(cat: Bucket, sub: string | null, week: WeekRange | null) {
  let q = supabase.from("offer_latest_category").select("offer_id").eq("category", cat);
  if (sub) q = q.eq("subcategory", sub);
  const { data: mapped } = await q;
  const ids = (mapped ?? []).map((r) => r.offer_id).filter(Boolean) as string[];
  if (!ids.length) return [];
  let oq = supabase
    .from("offers")
    .select("id, title, store, price, original_price, discount_percent, image_url, url, category")
    .in("id", ids)
    .eq("is_active", true);
  oq = applyWeekFilter(excludeExpired(excludeStale(oq)), week);
  const { data } = await oq
    .order("discount_percent", { ascending: false, nullsFirst: false })
    .limit(60);
  return data ?? [];
}

async function fetchHeuristicOffersInBucket(cat: Bucket, sub: string | null, week: WeekRange | null) {
  let q = supabase
    .from("offers")
    .select("id, title, store, price, original_price, discount_percent, image_url, url, category")
    .eq("is_active", true);
  q = applyWeekFilter(excludeExpired(excludeStale(q)), week);
  const { data } = await q
    .order("discount_percent", { ascending: false, nullsFirst: false })
    .limit(2000);
  return (data ?? [])
    .filter((o) => {
      const c = classify(o.title, o.category);
      if (c.bucket !== cat) return false;
      if (sub && c.subcategory !== sub) return false;
      return true;
    })
    .slice(0, 60);
}

export default async function CategoriesPage({ searchParams }: { searchParams: SearchParams }) {
  const { cat = "", sub = "", week: weekParam } = await searchParams;
  const week = weekRange(parseWeek(weekParam));

  const rows = await fetchOffers(week);
  const { source, bucketCounts, subCounts } = aggregate(rows);

  const selected = (BUCKETS as readonly string[]).includes(cat) ? (cat as Bucket) : "";
  const selectedSub =
    selected && sub && (SUBCATEGORIES[selected] as readonly string[]).includes(sub)
      ? sub
      : null;

  const offers = selected
    ? source === "llm"
      ? await fetchLLMOffersInBucket(selected, selectedSub, week)
      : await fetchHeuristicOffersInBucket(selected, selectedSub, week)
    : [];

  return (
    <div className="space-y-8">
      <PageHeader
        title="Kategorien"
        subtitle={
          week
            ? `${week.label} · ${week.from.toLocaleDateString("de-DE")} – ${week.to.toLocaleDateString("de-DE")}`
            : "Zehn klare Bereiche mit festen Unterkategorien."
        }
      />

      {source === "heuristic" && (
        <div className="flex items-start gap-3 rounded-lg border border-border bg-surface p-4 text-sm">
          <Info className="mt-0.5 h-4 w-4 flex-shrink-0 text-fg-subtle" />
          <div className="space-y-1">
            <div className="font-medium">Heuristische Klassifikation</div>
            <p className="text-fg-muted">
              Schlüsselwort-basiert auf den rohen kaufDA-Kategorien. Für saubere LLM-Klassifikation:
            </p>
            <code className="mt-1 inline-block rounded bg-surface-hover px-2 py-1 text-xs">
              python -m scripts.categorize_offers --all --force
            </code>
          </div>
        </div>
      )}

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {BUCKETS.map((b) => {
          const n = bucketCounts.get(b) ?? 0;
          const active = b === selected;
          const disabled = n === 0;
          return (
            <Link
              key={b}
              href={n > 0 ? `/categories?cat=${encodeURIComponent(b)}` : "#"}
              aria-disabled={disabled}
              className={`group flex items-center gap-3 rounded-xl border p-3 transition ${
                active
                  ? "border-accent bg-accent/10"
                  : disabled
                    ? "cursor-not-allowed border-border bg-surface opacity-50"
                    : "border-border bg-surface hover:border-border-strong hover:bg-surface-hover"
              }`}
            >
              <span
                className={`inline-flex h-9 w-9 items-center justify-center rounded-md ${
                  active ? "bg-accent/20 text-accent" : "bg-surface-hover text-fg-muted"
                }`}
              >
                {ICONS[b]}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{b}</div>
                <div className="text-xs tabular-nums text-fg-muted">
                  {n.toLocaleString("de-DE")} Angebote
                </div>
              </div>
            </Link>
          );
        })}
      </section>

      {selected && (
        <>
          <section className="space-y-2">
            <div className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
              Unterkategorien
            </div>
            <div className="flex flex-wrap gap-2">
              <Link
                href={`/categories?cat=${encodeURIComponent(selected)}${weekParam ? `&week=${weekParam}` : ""}`}
                className={`rounded-full border px-3 py-1 text-sm transition ${
                  !selectedSub
                    ? "border-fg bg-fg text-bg"
                    : "border-border bg-surface text-fg-muted hover:border-border-strong hover:text-fg"
                }`}
              >
                Alle{" "}
                <span className="ml-1 text-xs opacity-70">
                  {(bucketCounts.get(selected) ?? 0).toLocaleString("de-DE")}
                </span>
              </Link>
              {SUBCATEGORIES[selected].map((s) => {
                const count = subCounts.get(selected)?.get(s) ?? 0;
                const active = selectedSub === s;
                const disabled = count === 0;
                const href = disabled
                  ? "#"
                  : `/categories?cat=${encodeURIComponent(selected)}&sub=${encodeURIComponent(s)}${weekParam ? `&week=${weekParam}` : ""}`;
                return (
                  <Link
                    key={s}
                    href={href}
                    aria-disabled={disabled}
                    className={`rounded-full border px-3 py-1 text-sm transition ${
                      active
                        ? "border-fg bg-fg text-bg"
                        : disabled
                          ? "cursor-not-allowed border-border bg-surface text-fg-subtle opacity-50"
                          : "border-border bg-surface text-fg-muted hover:border-border-strong hover:text-fg"
                    }`}
                  >
                    {s}
                    <span className="ml-1 text-xs opacity-70 tabular-nums">{count}</span>
                  </Link>
                );
              })}
            </div>
          </section>

          <section className="space-y-3">
            <div className="flex items-baseline justify-between">
              <h2 className="text-lg font-semibold tracking-tight">
                {selected}
                {selectedSub && (
                  <span className="ml-2 text-base font-normal text-fg-muted">/ {selectedSub}</span>
                )}
              </h2>
              <span className="text-sm text-fg-muted">sortiert nach Rabatt</span>
            </div>
            {offers.length === 0 ? (
              <EmptyState
                icon={<Layers className="h-8 w-8" />}
                title="Keine Angebote in dieser Auswahl"
              />
            ) : (
              <Card className="overflow-hidden">
                <ul className="divide-y divide-border">
                  {offers.map((o) => (
                    <OfferRow
                      key={o.id}
                      title={o.title}
                      store={o.store}
                      url={o.url}
                      imageUrl={o.image_url}
                      price={o.price}
                      originalPrice={o.original_price}
                      discountPercent={o.discount_percent}
                      meta={source === "heuristic" && !selectedSub ? o.category ?? undefined : undefined}
                    />
                  ))}
                </ul>
              </Card>
            )}
          </section>
        </>
      )}
    </div>
  );
}
