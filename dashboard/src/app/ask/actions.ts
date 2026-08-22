"use server";

import { isConfigured, llm, MODEL } from "@/lib/llm";
import { supabase } from "@/lib/supabase";

export type AskedOffer = {
  id: string;
  title: string;
  store: string | null;
  price: number | null;
  original_price: number | null;
  discount_percent: number | null;
  image_url: string | null;
  url: string;
  category: string | null;
};

export type AskResult = {
  ok: true;
  question: string;
  keywords: string[];
  answer: string;
  citedOffers: AskedOffer[];
  candidateCount: number;
} | {
  ok: false;
  error: string;
};

const MAX_CANDIDATES = 40;
const MAX_CITATIONS = 12;
const SIMILARITY_CUTOFF = 0.45;

const ANSWER_SYSTEM = `Du bist ein hilfreicher Berater für deutsche Supermarkt-Angebote.

Du bekommst eine Frage und eine Liste passender Angebote (id, title, store, price, original_price, discount_percent, category).
Beantworte die Frage präzise auf Deutsch, in maximal 6 Sätzen oder einer kurzen Liste.

Wenn der Nutzer Angebote vergleichen will:
- Nenne konkrete Preise mit Markt-Name.
- Hebe den günstigsten Preis und den höchsten Rabatt hervor.
- Wenn Daten fehlen, sage das offen.

Wenn keine relevanten Angebote gefunden wurden, sag das ehrlich.

Antworte ausschließlich mit JSON in genau diesem Format:
{
  "answer": "Markdown-Text mit der Antwort. Konkrete Angebote als [Titel](#OFFER_ID) verlinken, damit das Frontend sie hervorheben kann.",
  "cited_offer_ids": ["id1","id2"]
}

Maximal ${MAX_CITATIONS} cited_offer_ids, die wirklich relevant sind.`;

function safeJson<T>(raw: string, fallback: T): T {
  const cleaned = raw
    .trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/i, "");
  try {
    return JSON.parse(cleaned) as T;
  } catch {
    return fallback;
  }
}

async function embedQuery(question: string): Promise<number[] | null> {
  const { data, error } = await supabase.functions.invoke("generate-embedding", {
    body: { text: question },
  });
  if (error) {
    console.error("[ask] generate-embedding failed:", error);
    return null;
  }
  const embedding = (data as { embedding?: number[] } | null)?.embedding;
  if (!Array.isArray(embedding) || embedding.length !== 384) {
    console.error("[ask] unexpected embedding payload:", data);
    return null;
  }
  return embedding;
}

async function semanticSearch(question: string): Promise<AskedOffer[]> {
  const embedding = await embedQuery(question);
  if (!embedding) return [];

  const { data, error } = await supabase.rpc("search_offers", {
    query_embedding: embedding,
    similarity_cutoff: SIMILARITY_CUTOFF,
    max_price_filter: null,
    category_filter: null,
    result_limit: MAX_CANDIDATES,
  });
  if (error) {
    console.error("[ask] search_offers RPC failed:", error);
    return [];
  }

  const rows = (data ?? []) as Array<{
    offer_id: string;
    title: string;
    store: string | null;
    price: number | null;
    original_price: number | null;
    discount_percent: number | null;
    image_url: string | null;
    url: string;
    category: string | null;
  }>;

  return rows.map((r) => ({
    id: r.offer_id,
    title: r.title,
    store: r.store,
    price: r.price,
    original_price: r.original_price,
    discount_percent: r.discount_percent,
    image_url: r.image_url,
    url: r.url,
    category: r.category,
  }));
}

async function answerWithCitations(
  question: string,
  candidates: AskedOffer[],
): Promise<{ answer: string; citedIds: string[] }> {
  const slimmed = candidates.map((o) => ({
    id: o.id,
    title: o.title,
    store: o.store,
    price: o.price,
    original_price: o.original_price,
    discount_percent: o.discount_percent,
    category: o.category,
  }));

  const res = await llm.chat.completions.create({
    model: MODEL,
    temperature: 0.2,
    messages: [
      { role: "system", content: ANSWER_SYSTEM },
      {
        role: "user",
        content: `Frage: ${question}\n\nAngebote (${slimmed.length}):\n${JSON.stringify(slimmed, null, 2)}`,
      },
    ],
    response_format: { type: "json_object" },
  });
  const content = res.choices[0]?.message?.content ?? "{}";
  const parsed = safeJson<{ answer?: string; cited_offer_ids?: string[] }>(content, {});
  return {
    answer: parsed.answer ?? "(keine Antwort)",
    citedIds: (parsed.cited_offer_ids ?? []).slice(0, MAX_CITATIONS),
  };
}

export async function askOffers(question: string): Promise<AskResult> {
  const q = question.trim();
  if (!q) return { ok: false, error: "Bitte eine Frage eingeben." };
  if (!isConfigured()) return { ok: false, error: "GEMINI_API_KEY ist nicht gesetzt." };

  try {
    const candidates = await semanticSearch(q);
    if (candidates.length === 0) {
      return {
        ok: true,
        question: q,
        keywords: ["semantisch"],
        answer: "Keine passenden aktiven Angebote gefunden.",
        citedOffers: [],
        candidateCount: 0,
      };
    }

    const { answer, citedIds } = await answerWithCitations(q, candidates);
    const citedSet = new Set(citedIds);
    const cited = candidates.filter((o) => citedSet.has(o.id));

    return {
      ok: true,
      question: q,
      keywords: ["semantisch"],
      answer,
      citedOffers: cited,
      candidateCount: candidates.length,
    };
  } catch (exc) {
    const msg = exc instanceof Error ? exc.message : String(exc);
    console.error("[ask] failed:", msg);
    return { ok: false, error: msg };
  }
}
