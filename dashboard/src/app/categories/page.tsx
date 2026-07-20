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
import { bucketFromKaufda } from "@/lib/kaufdaTaxonomy";
import {
  applyWeekFilter,
  excludeExpired,
  excludeStale,
  fetchAllRows,
  hasColumn,
  supabase,
} from "@/lib/supabase";
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

type Source = "kaufda" | "heuristic";

type LLMCategory = { category: string; subcategory: string | null };

type AggRow = {
  id: string;
  title: string | null;
  category: string | null;
  kaufda_category: string | null;
  kaufda_category_path: string | null;
};

const BASE_FIELDS = "id, title, category";
const TAXONOMY_FIELDS = "kaufda_category, kaufda_category_path";

/**
 * Field list for the offers query, including kaufDA's taxonomy columns only
 * once migration 010 has added them — selecting a missing column fails the
 * whole request with 42703 and blanks the page.
 */
async function offerFields(extra = ""): Promise<string> {
  const withTaxonomy = await hasColumn("offers", "kaufda_category");
  return [BASE_FIELDS, withTaxonomy ? TAXONOMY_FIELDS : "", extra]
    .filter(Boolean)
    .join(", ");
}

/**
 * Bucket for one offer, best source first:
 *   1. kaufDA's own taxonomy (~95% coverage, most reliable)
 *   2. the LLM classification, where one exists
 *   3. the title heuristic
 */
function bucketFor(row: AggRow, llm: Map<string, LLMCategory>): Bucket {
  const fromKaufda = bucketFromKaufda(row.kaufda_category, row.kaufda_category_path);
  if (fromKaufda) return fromKaufda;
  const fromLLM = llm.get(row.id)?.category;
  if (fromLLM && (BUCKETS as readonly string[]).includes(fromLLM)) return fromLLM as Bucket;
  return classify(row.title, row.category).bucket;
}

/**
 * Fetch every active offer for the week, plus the LLM classifications, as two
 * independent queries.
 *
 * They used to be a single query with an embedded
 * `offer_latest_category(...)` join. At the current table size that join makes
 * Postgres exceed the API statement timeout and the request dies with 57014 —
 * which this page then rendered as "0 Angebote" in every bucket. Fetched
 * apart, both are fast.
 */
async function fetchOffers(
  week: WeekRange | null,
): Promise<{ rows: AggRow[]; llm: Map<string, LLMCategory>; error: string | null }> {
  const fields = await offerFields();
  const [offers, categories] = await Promise.all([
    fetchAllRows<AggRow>((from, to) => {
      let q = supabase.from("offers").select(fields).eq("is_active", true);
      q = applyWeekFilter(excludeExpired(excludeStale(q)), week);
      // `fields` is built at runtime, so supabase-js can't infer the row shape.
      return q.range(from, to).returns<AggRow[]>();
    }),
    fetchAllRows<{ offer_id: string | null } & LLMCategory>((from, to) =>
      supabase
        .from("offer_latest_category")
        .select("offer_id, category, subcategory")
        .range(from, to),
    ),
  ]);

  const llm = new Map<string, LLMCategory>();
  for (const c of categories.rows) {
    if (c.offer_id) llm.set(c.offer_id, { category: c.category, subcategory: c.subcategory });
  }

  // Losing the LLM categories is survivable — the heuristic covers it.
  // Losing the offers themselves is not.
  return { rows: offers.rows, llm, error: offers.error };
}

type Aggregates = {
  source: Source;
  bucketCounts: Map<Bucket, number>;
  subCounts: Map<Bucket, Map<string, number>>;
};

/** Subcategory for an offer — the LLM's when valid for the bucket, else the heuristic's. */
function subcategoryFor(row: AggRow, bucket: Bucket, llm: Map<string, LLMCategory>): string {
  const fromLLM = (llm.get(row.id)?.subcategory ?? "").trim();
  if (fromLLM && (SUBCATEGORIES[bucket] as readonly string[]).includes(fromLLM)) return fromLLM;
  return classify(row.title, row.category).subcategory;
}

function aggregate(rows: AggRow[], llmByOffer: Map<string, LLMCategory>): Aggregates {
  const bucketCounts = new Map<Bucket, number>();
  const subCounts = new Map<Bucket, Map<string, number>>();
  for (const b of BUCKETS) {
    bucketCounts.set(b, 0);
    subCounts.set(b, new Map());
  }

  for (const r of rows) {
    if (!r.title && !r.category && !r.kaufda_category) continue;
    const bucket = bucketFor(r, llmByOffer);
    bucketCounts.set(bucket, (bucketCounts.get(bucket) ?? 0) + 1);
    const m = subCounts.get(bucket)!;
    const sub = subcategoryFor(r, bucket, llmByOffer);
    m.set(sub, (m.get(sub) ?? 0) + 1);
  }

  // Which source actually drove the bucket assignments — shown to the user so
  // a fallback classification isn't mistaken for kaufDA's own taxonomy.
  const fromKaufda = rows.filter((r) =>
    bucketFromKaufda(r.kaufda_category, r.kaufda_category_path),
  ).length;
  const source: Source =
    fromKaufda >= rows.length * 0.5 && fromKaufda > 0 ? "kaufda" : "heuristic";

  return { source, bucketCounts, subCounts };
}

type OfferRowData = AggRow & {
  store: string | null;
  price: number | null;
  original_price: number | null;
  discount_percent: number | null;
  image_url: string | null;
  url: string;
};

const DETAIL_EXTRA = "store, price, original_price, discount_percent, image_url, url";

const MAX_OFFERS_SHOWN = 60;

/**
 * Offers inside one bucket (optionally one subcategory).
 *
 * Bucketing happens in JS — it draws on kaufDA's taxonomy, the LLM table and
 * the title heuristic — so the filter cannot be pushed into SQL and every
 * candidate row has to come back. `.limit(2000)` used to look like it did that,
 * but PostgREST caps responses at 1000, so lower-discount offers in a bucket
 * silently never appeared.
 */
async function fetchOffersInBucket(
  cat: Bucket,
  sub: string | null,
  week: WeekRange | null,
  llm: Map<string, LLMCategory>,
) {
  const fields = await offerFields(DETAIL_EXTRA);
  const { rows } = await fetchAllRows<OfferRowData>((from, to) => {
    let q = supabase.from("offers").select(fields).eq("is_active", true);
    q = applyWeekFilter(excludeExpired(excludeStale(q)), week);
    return q
      .order("discount_percent", { ascending: false, nullsFirst: false })
      .range(from, to)
      .returns<OfferRowData[]>();
  });

  return rows
    .filter((o) => {
      if (bucketFor(o, llm) !== cat) return false;
      if (sub && subcategoryFor(o, cat, llm) !== sub) return false;
      return true;
    })
    .slice(0, MAX_OFFERS_SHOWN);
}

export default async function CategoriesPage({ searchParams }: { searchParams: SearchParams }) {
  const { cat = "", sub = "", week: weekParam } = await searchParams;
  const week = weekRange(parseWeek(weekParam));

  const { rows, llm, error } = await fetchOffers(week);
  const { source, bucketCounts, subCounts } = aggregate(rows, llm);

  const selected = (BUCKETS as readonly string[]).includes(cat) ? (cat as Bucket) : "";
  const selectedSub =
    selected && sub && (SUBCATEGORIES[selected] as readonly string[]).includes(sub)
      ? sub
      : null;

  const offers = selected ? await fetchOffersInBucket(selected, selectedSub, week, llm) : [];

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

      {error && (
        <EmptyState
          icon={<Layers className="h-8 w-8" />}
          title="Angebote konnten nicht geladen werden"
          body={
            <>
              Die Datenbank hat die Abfrage abgebrochen. Das ist ein Ladefehler — es heißt
              nicht, dass es keine Angebote gibt. Lade die Seite in ein paar Sekunden neu.
            </>
          }
        />
      )}

      {!error && source === "heuristic" && (
        <div className="flex items-start gap-3 rounded-lg border border-border bg-surface p-4 text-sm">
          <Info className="mt-0.5 h-4 w-4 flex-shrink-0 text-fg-subtle" />
          <div className="space-y-1">
            <div className="font-medium">Heuristische Klassifikation</div>
            <p className="text-fg-muted">
              Diese Angebote tragen noch keine kaufDA-Kategorie, daher wird aus dem Titel
              geraten. Die echte Kategorie kommt automatisch mit dem nächsten Scrape — sofern
              die Migration angewandt ist:
            </p>
            <code className="mt-1 inline-block rounded bg-surface-hover px-2 py-1 text-xs">
              supabase/migrations/010_kaufda_taxonomy.sql
            </code>
          </div>
        </div>
      )}

      <section className={`grid gap-3 sm:grid-cols-2 lg:grid-cols-5 ${error ? "hidden" : ""}`}>
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
                  {offers.map((o) => {
                    // Show OUR subcategory, never the raw `category` column —
                    // that is just the keyword the scraper found the offer
                    // under, and kaufDA's search cross-returns across keywords.
                    const meta = selectedSub ? undefined : subcategoryFor(o, selected, llm);
                    return (
                      <OfferRow
                        key={o.id}
                        title={o.title ?? "(ohne Titel)"}
                        store={o.store}
                        url={o.url}
                        imageUrl={o.image_url}
                        price={o.price}
                        originalPrice={o.original_price}
                        discountPercent={o.discount_percent}
                        meta={meta}
                      />
                    );
                  })}
                </ul>
              </Card>
            )}
          </section>
        </>
      )}
    </div>
  );
}
