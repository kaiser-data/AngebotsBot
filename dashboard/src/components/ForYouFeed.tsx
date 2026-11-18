"use client";

/**
 * Personalized "Für dich" feed.
 *
 * Preferences (stores, category buckets, bargain threshold) live in
 * localStorage — see lib/prefs.ts. Offers are fetched client-side with the
 * same anon Supabase client and freshness/week filters as the server pages,
 * then classified locally via the shared heuristic taxonomy.
 *
 * Two sections:
 *   1. "Deine Angebote"   — preferred buckets (default: Lebensmittel+Getränke)
 *   2. "Schnäppchen-Radar" — everything else, but only above a discount bar
 */

import {
  AlertTriangle,
  Heart,
  Radar,
  RefreshCw,
  SlidersHorizontal,
  TrendingDown,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Badge, Card, EmptyState, OfferRow, PageHeader } from "@/components/ui";
import {
  classifyFeedRow,
  pickBargains,
  pickMine,
  PRICE_LOW_PERCENTILE,
  relativeTime,
  type FeedRow,
} from "@/lib/feed";
import {
  DEFAULT_PREFS,
  isDrugstore,
  isSupermarket,
  loadPrefs,
  savePrefs,
  type Prefs,
} from "@/lib/prefs";
import {
  applyWeekFilter,
  excludeExpired,
  excludeStale,
  fetchAllRows,
  hasColumn,
  supabase,
} from "@/lib/supabase";
import { BUCKETS, type Bucket } from "@/lib/taxonomy";
import { useMounted } from "@/lib/useMounted";
import { parseWeek, weekRange, type WeekRange } from "@/lib/week";

const FIELDS =
  "id, title, store, category, price, original_price, discount_percent, image_url, url, last_seen_at";
const TAXONOMY_FIELDS = "kaufda_category, kaufda_category_path";
/** Refetch when the tab comes back after this long. */
const STALE_MS = 5 * 60_000;

/**
 * Load the feed's candidate offers. Includes kaufDA's taxonomy columns when the
 * schema has them, so the feed classifies offers exactly like /categories.
 */
async function fetchFeed(stores: string[], week: WeekRange | null) {
  const fields = (await hasColumn("offers", "kaufda_category"))
    ? `${FIELDS}, ${TAXONOMY_FIELDS}`
    : FIELDS;
  return fetchAllRows<FeedRow>((from, to) => {
    let q = supabase.from("offers").select(fields).eq("is_active", true);
    q = applyWeekFilter(excludeExpired(excludeStale(q)), week);
    if (stores.length > 0) q = q.in("store", stores);
    return q
      .order("discount_percent", { ascending: false, nullsFirst: false })
      .order("id")
      .range(from, to)
      .returns<FeedRow[]>();
  });
}

type FeedResult = { key: string; rows: FeedRow[]; error: string | null; at: number };

export function ForYouFeed() {
  const searchParams = useSearchParams();
  const weekParam = searchParams.get("week") ?? undefined;
  const week = useMemo(() => weekRange(parseWeek(weekParam)), [weekParam]);

  // Prefs live in localStorage → only readable after mount (no hydration mismatch).
  const mounted = useMounted();
  const [savedPrefs, setSavedPrefs] = useState<Prefs | null>(null);
  const prefs = useMemo(
    () => savedPrefs ?? (mounted ? loadPrefs() : null),
    [savedPrefs, mounted],
  );

  const [panelOpen, setPanelOpen] = useState(false);
  const [showAllMine, setShowAllMine] = useState(false);
  const [scores, setScores] = useState<Map<string, number>>(new Map());
  const [nonce, setNonce] = useState(0);
  const [result, setResult] = useState<FeedResult | null>(null);

  const storesKey = prefs ? [...prefs.stores].sort().join("|") : null;
  // Everything that should trigger a refetch. A response is only shown if it
  // belongs to the CURRENT key — a slow answer for last week's filter can't
  // overwrite this week's rows.
  const requestKey = prefs ? `${storesKey}§${weekParam ?? ""}§${nonce}` : null;
  const loading = requestKey != null && result?.key !== requestKey;

  useEffect(() => {
    if (!requestKey || !prefs) return;
    let cancelled = false;
    void fetchFeed(prefs.stores, week).then(({ rows, error }) => {
      if (!cancelled) setResult({ key: requestKey, rows, error, at: Date.now() });
    });
    return () => {
      cancelled = true;
    };
    // prefs.stores and week are encoded in requestKey.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  const refresh = () => setNonce((n) => n + 1);

  // Refetch when the tab comes back into focus after a while.
  const fetchedAt = result?.at ?? 0;
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && Date.now() - fetchedAt > STALE_MS) {
        setNonce((n) => n + 1);
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [fetchedAt]);

  const rows = useMemo(() => (loading || !result ? [] : result.rows), [loading, result]);
  const loadError = loading ? null : (result?.error ?? null);
  const classified = useMemo(() => rows.map(classifyFeedRow), [rows]);

  const mine = useMemo(
    () => (prefs ? pickMine(classified, prefs, scores) : []),
    [classified, prefs, scores],
  );
  const bargains = useMemo(
    () => (prefs ? pickBargains(classified, prefs) : []),
    [classified, prefs],
  );

  // Deal scores (price percentile vs 90-day history) for the candidate offers.
  // Ranked by trusted discount (no scores needed) so the id list is stable.
  const scoreIds = useMemo(() => {
    if (!prefs) return "";
    const top = pickMine(classified, prefs).map((o) => o.id);
    return [...top, ...bargains.map((o) => o.id)].slice(0, 100).join(",");
  }, [classified, prefs, bargains]);

  useEffect(() => {
    if (!scoreIds) return;
    let cancelled = false;
    void (async () => {
      const { data } = await supabase
        .from("offer_deal_score")
        .select("offer_id, price_percentile")
        .in("offer_id", scoreIds.split(","))
        .not("price_percentile", "is", null);
      if (cancelled || !data) return;
      setScores((prev) => {
        const next = new Map(prev);
        for (const r of data) next.set(r.offer_id as string, r.price_percentile as number);
        return next;
      });
    })();
    return () => {
      cancelled = true;
    };
  }, [scoreIds]);

  const lastSeen = useMemo(() => {
    let max: string | null = null;
    for (const r of rows) {
      if (r.last_seen_at && (!max || r.last_seen_at > max)) max = r.last_seen_at;
    }
    return max;
  }, [rows]);

  if (!prefs) {
    return (
      <div className="space-y-8">
        <PageHeader title="Für dich" />
        <FeedSkeleton />
      </div>
    );
  }

  const summary = [
    prefs.buckets.length === BUCKETS.length ? "Alle Kategorien" : prefs.buckets.join(", "),
    prefs.stores.length === 0
      ? "alle Märkte"
      : prefs.stores.length === 1
        ? prefs.stores[0]
        : `${prefs.stores.length} Märkte`,
    week ? week.label : "alle Wochen",
  ].join(" · ");

  const savePanel = (next: Prefs) => {
    const merged = { ...next, onboarded: true };
    savePrefs(merged);
    setSavedPrefs(merged);
    setPanelOpen(false);
    setShowAllMine(false);
  };

  const mineVisible = showAllMine ? mine : mine.slice(0, 30);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader title="Für dich" subtitle={summary} />
        <div className="flex items-center gap-2">
          <span className="text-xs text-fg-subtle" title="Letzter Daten-Crawl">
            Stand: {loading ? "…" : relativeTime(lastSeen)}
          </span>
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            aria-label="Daten aktualisieren"
            title="Daten aktualisieren"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-surface text-fg-muted hover:border-border-strong hover:text-fg"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button
            type="button"
            onClick={() => setPanelOpen((v) => !v)}
            className="inline-flex h-8 items-center gap-2 rounded-md border border-border bg-surface px-3 text-sm text-fg-muted hover:border-border-strong hover:text-fg"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Präferenzen
          </button>
        </div>
      </div>

      {(!prefs.onboarded || panelOpen) && (
        <PrefsPanel
          prefs={prefs}
          firstRun={!prefs.onboarded}
          onSave={savePanel}
          onCancel={prefs.onboarded ? () => setPanelOpen(false) : undefined}
        />
      )}

      {loadError && !loading && mine.length > 0 && (
        <p className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg-muted">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Nicht alle Angebote konnten geladen werden — die Liste ist evtl. unvollständig.
          <button type="button" onClick={refresh} className="ml-auto font-medium text-fg hover:underline">
            Erneut versuchen
          </button>
        </p>
      )}

      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <Heart className="h-4 w-4 text-accent" />
            Deine Angebote
          </h2>
          <span className="text-sm text-fg-muted">beste Rabatte zuerst</span>
        </div>
        {loading ? (
          // Also covers filter changes: never show rows from the previous
          // store selection while the refetch is in flight.
          <FeedSkeleton />
        ) : loadError && mine.length === 0 ? (
          <LoadError message={loadError} onRetry={refresh} />
        ) : mine.length === 0 ? (
          <EmptyState
            icon={<Heart className="h-8 w-8" />}
            title="Keine Angebote in deiner Auswahl"
            body="Erweitere deine Kategorien oder Märkte über „Präferenzen“ — oder wechsle die Woche."
          />
        ) : (
          <>
            <Card className="overflow-hidden">
              <ul className="divide-y divide-border">
                {mineVisible.map((o) => (
                  <OfferRow
                    key={o.id}
                    title={o.title}
                    store={o.store}
                    url={o.url}
                    imageUrl={o.image_url}
                    price={o.price}
                    originalPrice={o.original_price}
                    discountPercent={o.discount_percent}
                    meta={o.subcategory}
                    trailing={<PriceLowBadge pct={scores.get(o.id)} />}
                  />
                ))}
              </ul>
            </Card>
            {mine.length > mineVisible.length && (
              <button
                type="button"
                onClick={() => setShowAllMine(true)}
                className="w-full rounded-lg border border-border bg-surface py-2 text-sm text-fg-muted transition hover:border-border-strong hover:text-fg"
              >
                {mine.length - mineVisible.length} weitere anzeigen
              </button>
            )}
          </>
        )}
      </section>

      {!loading && prefs.bargainMinDiscount != null && bargains.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-baseline justify-between">
            <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
              <Radar className="h-4 w-4 text-accent" />
              Schnäppchen-Radar
            </h2>
            <span className="text-sm text-fg-muted">
              andere Kategorien, ab {prefs.bargainMinDiscount}% Rabatt
            </span>
          </div>
          <Card className="overflow-hidden">
            <ul className="divide-y divide-border">
              {bargains.map((o) => (
                <OfferRow
                  key={o.id}
                  title={o.title}
                  store={o.store}
                  url={o.url}
                  imageUrl={o.image_url}
                  price={o.price}
                  originalPrice={o.original_price}
                  discountPercent={o.discount_percent}
                  meta={`${o.bucket} · ${o.subcategory}`}
                  trailing={<PriceLowBadge pct={scores.get(o.id)} />}
                />
              ))}
            </ul>
          </Card>
        </section>
      )}

      <nav className="flex flex-wrap gap-x-5 gap-y-1 border-t border-border pt-4 text-sm text-fg-muted">
        <Link href="/stores" className="hover:text-fg">Märkte vergleichen →</Link>
        <Link href="/categories" className="hover:text-fg">Alle Kategorien →</Link>
        <Link href="/deals" className="hover:text-fg">Preisverlauf & Deal score →</Link>
      </nav>
    </div>
  );
}

function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card className="flex flex-col items-center gap-3 p-10 text-center">
      <AlertTriangle className="h-8 w-8 text-fg-subtle" />
      <div className="text-sm font-medium text-fg">Angebote konnten nicht geladen werden</div>
      <div className="max-w-sm text-sm text-fg-muted">
        Die Datenbank antwortet gerade nicht. Das ist meist nach kurzer Zeit behoben.
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-md bg-fg px-4 py-2 text-sm font-medium text-bg hover:opacity-90"
      >
        Erneut versuchen
      </button>
      <details className="text-xs text-fg-subtle">
        <summary className="cursor-pointer">Technische Details</summary>
        {message}
      </details>
    </Card>
  );
}

/** "Preis-Tief" — current price is in the cheapest quintile of its 90-day history. */
function PriceLowBadge({ pct }: { pct: number | undefined }) {
  if (pct == null || pct > PRICE_LOW_PERCENTILE) return null;
  return (
    <Badge tone="positive" className="hidden gap-1 sm:inline-flex" title={`Günstiger als ${(100 - pct).toFixed(0)}% der letzten 90 Tage`}>
      <TrendingDown className="h-3 w-3" />
      Preis-Tief
    </Badge>
  );
}

function FeedSkeleton() {
  return (
    <Card className="divide-y divide-border overflow-hidden">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex animate-pulse items-center gap-3 px-4 py-3">
          <div className="h-10 w-10 rounded-md bg-surface-hover" />
          <div className="flex-1 space-y-2">
            <div className="h-3 w-2/3 rounded bg-surface-hover" />
            <div className="h-2.5 w-1/3 rounded bg-surface-hover" />
          </div>
          <div className="h-3 w-14 rounded bg-surface-hover" />
        </div>
      ))}
    </Card>
  );
}

/* ────────────────────────────── Preferences panel ───────────────────────── */

const BARGAIN_OPTIONS: { label: string; value: number | null }[] = [
  { label: "aus", value: null },
  { label: "ab 25%", value: 25 },
  { label: "ab 40%", value: 40 },
  { label: "ab 60%", value: 60 },
];

function PrefsPanel({
  prefs,
  firstRun,
  onSave,
  onCancel,
}: {
  prefs: Prefs;
  firstRun: boolean;
  onSave: (p: Prefs) => void;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState<Prefs>(prefs);
  const [storeOptions, setStoreOptions] = useState<{ store: string; n: number }[] | null>(null);

  // Available stores (with offer counts), fetched once when the panel opens.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      // fetchAllRows: a plain .limit(8000) is silently capped at 1000 rows by
      // PostgREST, which hid most stores and under-counted the rest.
      const { rows: data } = await fetchAllRows<{ store: string }>((from, to) => {
        let q = supabase
          .from("offers")
          .select("store")
          .eq("is_active", true)
          .not("store", "is", null);
        q = excludeExpired(excludeStale(q));
        return q.order("id").range(from, to).returns<{ store: string }[]>();
      });
      if (cancelled) return;
      const counts = new Map<string, number>();
      for (const r of data) {
        counts.set(r.store, (counts.get(r.store) ?? 0) + 1);
      }
      setStoreOptions(
        [...counts.entries()]
          .map(([store, n]) => ({ store, n }))
          .sort((a, b) => b.n - a.n),
      );
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleBucket = (b: Bucket) =>
    setDraft((d) => ({
      ...d,
      buckets: d.buckets.includes(b)
        ? d.buckets.filter((x) => x !== b)
        : [...d.buckets, b],
    }));

  const toggleStore = (s: string) =>
    setDraft((d) => ({
      ...d,
      stores: d.stores.includes(s) ? d.stores.filter((x) => x !== s) : [...d.stores, s],
    }));

  // A previously chosen store with no current offers must stay visible, or it
  // keeps filtering the feed with no way to deselect it.
  const allStores = useMemo(() => {
    const opts = storeOptions ?? [];
    const known = new Set(opts.map((o) => o.store));
    const missing = prefs.stores.filter((s) => !known.has(s)).map((store) => ({ store, n: 0 }));
    return [...opts, ...missing];
  }, [storeOptions, prefs.stores]);
  const supermarkets = allStores.filter((s) => isSupermarket(s.store));
  const drugstores = allStores.filter((s) => isDrugstore(s.store));
  const others = allStores.filter((s) => !isSupermarket(s.store) && !isDrugstore(s.store));

  const presetSupermarkets = () =>
    setDraft((d) => ({ ...d, stores: supermarkets.map((s) => s.store) }));
  const presetSupermarketsDrug = () =>
    setDraft((d) => ({
      ...d,
      stores: [...supermarkets, ...drugstores].map((s) => s.store),
    }));
  const presetAll = () => setDraft((d) => ({ ...d, stores: [] }));

  return (
    <Card className="space-y-6 p-5">
      {firstRun && (
        <div>
          <h2 className="text-base font-semibold">Willkommen! Was interessiert dich?</h2>
          <p className="mt-1 text-sm text-fg-muted">
            Deine Auswahl wird nur auf diesem Gerät gespeichert und bestimmt, was du auf der
            Startseite siehst. Du kannst sie jederzeit über „Präferenzen“ ändern.
          </p>
        </div>
      )}

      <div className="space-y-2">
        <div className="text-xs font-medium uppercase tracking-wide text-fg-subtle">Märkte</div>
        <div className="flex flex-wrap gap-2">
          <PresetChip
            label="Alle Märkte"
            active={draft.stores.length === 0}
            onClick={presetAll}
          />
          <PresetChip
            label="Nur Supermärkte"
            active={
              draft.stores.length > 0 &&
              draft.stores.length === supermarkets.length &&
              draft.stores.every((s) => isSupermarket(s))
            }
            onClick={presetSupermarkets}
            disabled={supermarkets.length === 0}
          />
          <PresetChip
            label="Supermärkte + Drogerien"
            active={
              draft.stores.length > 0 &&
              draft.stores.length === supermarkets.length + drugstores.length &&
              draft.stores.every((s) => isSupermarket(s) || isDrugstore(s))
            }
            onClick={presetSupermarketsDrug}
            disabled={supermarkets.length === 0}
          />
        </div>
        {storeOptions === null ? (
          <p className="text-xs text-fg-subtle">Lade Märkte…</p>
        ) : (
          <div className="max-h-48 space-y-2 overflow-y-auto pr-1">
            {[
              ["Supermärkte & Discounter", supermarkets] as const,
              ["Drogerien", drugstores] as const,
              ["Weitere Märkte", others] as const,
            ].map(([label, group]) =>
              group.length === 0 ? null : (
                <div key={label}>
                  <div className="mb-1 text-[11px] text-fg-subtle">{label}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {group.map(({ store, n }) => (
                      <Chip
                        key={store}
                        active={draft.stores.includes(store)}
                        onClick={() => toggleStore(store)}
                      >
                        {store} <span className="opacity-60">{n}</span>
                      </Chip>
                    ))}
                  </div>
                </div>
              ),
            )}
          </div>
        )}
        <p className="text-xs text-fg-subtle">
          Keine Auswahl = alle Märkte. Zahlen = aktive Angebote.
        </p>
      </div>

      <div className="space-y-2">
        <div className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
          Kategorien für deinen Feed
        </div>
        <div className="flex flex-wrap gap-1.5">
          {BUCKETS.map((b) => (
            <Chip key={b} active={draft.buckets.includes(b)} onClick={() => toggleBucket(b)}>
              {b}
            </Chip>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <div className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
          Schnäppchen-Radar
        </div>
        <p className="text-sm text-fg-muted">
          Zeige Angebote außerhalb deiner Kategorien, wenn der Rabatt groß genug ist.
        </p>
        <div className="flex flex-wrap gap-1.5">
          {BARGAIN_OPTIONS.map((opt) => (
            <Chip
              key={opt.label}
              active={draft.bargainMinDiscount === opt.value}
              onClick={() => setDraft((d) => ({ ...d, bargainMinDiscount: opt.value }))}
            >
              {opt.label}
            </Chip>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onSave(draft)}
          disabled={draft.buckets.length === 0}
          className="rounded-md bg-fg px-4 py-2 text-sm font-medium text-bg transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {firstRun ? "Los geht's" : "Speichern"}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-border px-4 py-2 text-sm text-fg-muted hover:border-border-strong hover:text-fg"
          >
            Abbrechen
          </button>
        )}
        {draft.buckets.length === 0 && (
          <span className="text-xs text-fg-subtle">Wähle mindestens eine Kategorie.</span>
        )}
        {!firstRun && (
          <button
            type="button"
            onClick={() => setDraft({ ...DEFAULT_PREFS, onboarded: true })}
            className="ml-auto text-xs text-fg-subtle hover:text-fg"
          >
            Zurücksetzen
          </button>
        )}
      </div>
    </Card>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-sm transition ${
        active
          ? "border-fg bg-fg text-bg"
          : "border-border bg-surface text-fg-muted hover:border-border-strong hover:text-fg"
      }`}
    >
      {children}
    </button>
  );
}

function PresetChip({
  label,
  active,
  onClick,
  disabled,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md border px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
        active
          ? "border-accent bg-accent/10 text-accent"
          : "border-border bg-surface text-fg-muted hover:border-border-strong hover:text-fg"
      }`}
    >
      {label}
    </button>
  );
}
