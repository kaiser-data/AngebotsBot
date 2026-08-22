"use client";

import { Loader2, Sparkles, MessageCircleQuestion } from "lucide-react";
import { useState, useTransition } from "react";
import { Badge, Card, EmptyState, OfferRow, PageHeader } from "@/components/ui";
import { askOffers, type AskResult } from "./actions";

const SAMPLES = [
  "Vergleiche aktuelle Wasserangebote",
  "Wo ist Ariel diese Woche am günstigsten?",
  "Gib mir die besten Rabatte auf Joghurt",
  "Welche Marken sind im Sortiment für Hundefutter?",
];

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [pending, startTransition] = useTransition();

  function submit(q?: string) {
    const value = (q ?? question).trim();
    if (!value) return;
    setQuestion(value);
    startTransition(async () => {
      const r = await askOffers(value);
      setResult(r);
    });
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="LLM-Suche"
        subtitle="Stell eine Frage zu den aktuellen Angeboten. Die Antwort verweist auf konkrete Treffer aus der Datenbank."
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="relative"
      >
        <MessageCircleQuestion className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle" />
        <input
          name="q"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Z. B. „Vergleiche aktuelle Wasserangebote“"
          className="w-full rounded-lg border border-border bg-surface py-2.5 pl-9 pr-28 text-sm placeholder:text-fg-subtle focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          disabled={pending || !question.trim()}
          className="absolute right-1.5 top-1/2 inline-flex -translate-y-1/2 items-center gap-1.5 rounded-md bg-fg px-3 py-1.5 text-xs font-medium text-bg transition disabled:opacity-50"
        >
          {pending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          Fragen
        </button>
      </form>

      {!result && !pending && (
        <Card className="p-5">
          <div className="mb-3 text-sm font-medium text-fg-muted">Beispiele</div>
          <div className="flex flex-wrap gap-2">
            {SAMPLES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => submit(s)}
                className="rounded-full border border-border bg-surface px-3 py-1 text-sm transition hover:border-border-strong hover:bg-surface-hover"
              >
                {s}
              </button>
            ))}
          </div>
        </Card>
      )}

      {pending && (
        <Card className="flex items-center justify-center gap-3 p-10 text-sm text-fg-muted">
          <Loader2 className="h-4 w-4 animate-spin" />
          Sucht und vergleicht…
        </Card>
      )}

      {result && !pending && !result.ok && (
        <EmptyState
          icon={<MessageCircleQuestion className="h-8 w-8" />}
          title="Konnte nicht antworten"
          body={result.error}
        />
      )}

      {result?.ok && !pending && (
        <ResultView result={result} />
      )}
    </div>
  );
}

function ResultView({ result }: { result: Extract<AskResult, { ok: true }> }) {
  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-fg-muted">
          <span>Modus:</span>
          {result.keywords.length === 0 ? (
            <Badge tone="neutral">—</Badge>
          ) : (
            result.keywords.map((k) => (
              <Badge key={k} tone="accent">
                {k}
              </Badge>
            ))
          )}
          <span className="ml-auto">{result.candidateCount} Treffer geprüft</span>
        </div>
        <div className="prose-sm whitespace-pre-wrap text-sm leading-relaxed text-fg">
          {result.answer}
        </div>
      </Card>

      {result.citedOffers.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-medium text-fg-muted">
            Referenzierte Angebote ({result.citedOffers.length})
          </h2>
          <Card className="overflow-hidden">
            <ul className="divide-y divide-border">
              {result.citedOffers.map((o) => (
                <OfferRow
                  key={o.id}
                  title={o.title}
                  store={o.store}
                  url={o.url}
                  imageUrl={o.image_url}
                  price={o.price}
                  originalPrice={o.original_price}
                  discountPercent={o.discount_percent}
                  meta={o.category ?? undefined}
                />
              ))}
            </ul>
          </Card>
        </section>
      )}
    </div>
  );
}
