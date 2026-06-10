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
  Heart,
  Radar,
  RefreshCw,
  SlidersHorizontal,
  TrendingDown,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Badge, Card, EmptyState, OfferRow, PageHeader } from "@/components/ui";
import { classify } from "@/lib/categoryHeuristic";
import { discountTrust } from "@/lib/offerSanity";
import {
  DEFAULT_PREFS,
  isDrugstore,
  isSupermarket,
  loadPrefs,
  savePrefs,
  type Prefs,
} from "@/lib/prefs";
import { applyWeekFilter, excludeExpired, excludeStale, supabase } from "@/lib/supabase";
import { BUCKETS, type Bucket } from "@/lib/taxonomy";
import { parseWeek, weekRange } from "@/lib/week";

type Row = {
  id: string;
  title: string;
  store: string | null;
  category: string | null;
  price: number | null;
  original_price: number | null;
  discount_percent: number | null;
  image_url: string | null;
  url: string;
  last_seen_at: string | null;
};

type ClassifiedRow = Row & {
  bucket: Bucket;
  subcategory: string;
  /** discount with implausible values nulled out */
  eff: number | null;
  trusted: boolean;
};

const FIELDS =
  "id, title, store, category, price, original_price, discount_percent, image_url, url, last_seen_at";

function classifyRow(o: Row): ClassifiedRow {
  const { bucket, subcategory } = classify(o.title, o.category);
  const trust = discountTrust(o.title, o.discount_percent);
  return {
    ...o,
    bucket,
    subcategory,
    eff: trust === "implausible" ? null : o.discount_percent,
    trusted: trust === "trusted",
  };
}

function relativeTime(iso: string | null): string {
  if (!iso) return "unbekannt";
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `vor ${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 36) return `vor ${hours} h`;
  return `vor ${Math.round(hours / 24)} Tagen`;
}

export function ForYouFeed() {
  const searchParams = useSearchParams();
  const weekParam = searchParams.get("week") ?? undefined;
  const week = useMemo(() => weekRange(parseWeek(weekParam)), [weekParam]);

  // null until mounted → no hydration mismatch with localStorage.
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [panelOpen, setPanelOpen] = useState(false);
  const [showAllMine, setShowAllMine] = useState(false);
  const [scores, setScores] = useState<Map<string, number>>(new Map());
  const lastFetch = useRef(0);

  useEffect(() => setPrefs(loadPrefs()), []);

  const storesKey = prefs ? prefs.stores.slice().sort().join("|") : null;
  const prefsLoaded = prefs != null;

  const loadFeed = useCallback(async () => {
    if (!prefs) return;
    setLoading(true);
    let q = supabase.from("offers").select(FIELDS).eq("is_active", true);
    q = applyWeekFilter(excludeExpired(excludeStale(q)), week);
    if (prefs.stores.length > 0) q = q.in("store", prefs.stores);
    // 1000 = PostgREST max-rows cap; ordering by discount keeps the cut-off
    // at the least interesting offers.
    const { data } = await q
      .order("discount_percent", { ascending: false, nullsFirst: false })
      .limit(1000);
    setRows((data as Row[] | null) ?? []);
    lastFetch.current = Date.now();
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storesKey, weekParam, prefsLoaded]);

  useEffect(() => {
    void loadFeed();
  }, [loadFeed]);

  // Refetch when the tab comes back into focus after >5 min.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && Date.now() - lastFetch.current > 5 * 60_000) {
        void loadFeed();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [loadFeed]);

  const classified = useMemo(() => rows.map(classifyRow), [rows]);

  const mine = useMemo(() => {
    if (!prefs) return [];
    return classified
      .filter((o) => prefs.buckets.includes(o.bucket))
      .sort((a, b) => {
        const boost = (o: ClassifiedRow) => {
          const p = scores.get(o.id);
          return (o.eff ?? 0) + (p != null && p <= 20 ? 15 : 0);
        };
        return boost(b) - boost(a);
      })
      .slice(0, 60);
  }, [classified, prefs, scores]);

  const bargains = useMemo(() => {
    if (!prefs || prefs.bargainMinDiscount == null) return [];
    const min = prefs.bargainMinDiscount;
    return classified
      .filter(
        (o) =>
          !prefs.buckets.includes(o.bucket) && o.trusted && o.eff != null && o.eff >= min,
      )
      .sort((a, b) => (b.eff ?? 0) - (a.eff ?? 0))
      .slice(0, 24);
  }, [classified, prefs]);

  // Deal scores (price percentile vs 90-day history) for the visible offers.
  useEffect(() => {
    const ids = [...mine.map((o) => o.id), ...bargains.map((o) => o.id)];
    if (ids.length === 0) return;
    let cancelled = false;
    void (async () => {
      const { data } = await supabase
        .from("offer_deal_score")
        .select("offer_id, price_percentile")
        .in("offer_id", ids.slice(0, 100))
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, storesKey]);

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
    prefs.stores.length === 0 ? "alle Märkte" : `${prefs.stores.length} Märkte`,
    week ? week.label : "alle Wochen",
  ].join(" · ");

  const savePanel = (next: Prefs) => {
    const merged = { ...next, onboarded: true };
    savePrefs(merged);
    setPrefs(merged);
    setPanelOpen(false);
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
            onClick={() => void loadFeed()}
            aria-label="Daten aktualisieren"
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

/** "Preis-Tief" — current price is in the cheapest quintile of its 90-day history. */
function PriceLowBadge({ pct }: { pct: number | undefined }) {
  if (pct == null || pct > 20) return null;
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
      let q = supabase
        .from("offers")
        .select("store")
        .eq("is_active", true)
        .not("store", "is", null);
      q = excludeExpired(excludeStale(q));
      const { data } = await q.limit(8000);
      if (cancelled) return;
      const counts = new Map<string, number>();
      for (const r of (data ?? []) as { store: string }[]) {
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

  const allStores = storeOptions ?? [];
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
