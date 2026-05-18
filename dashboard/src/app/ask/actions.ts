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

const MAX_CANDIDATES = 80;
const MAX_CITATIONS = 12;

const KEYWORD_SYSTEM = `Du extrahierst deutsche Such-Stichwörter aus einer Nutzerfrage über Supermarkt-Angebote.

Antworte ausschließlich mit JSON: {"keywords": ["...","..."]}.

Regeln:
- 1 bis 5 Stichwörter, jeweils ein einzelnes Wort oder ein kurzer Stamm (z. B. "wasser", "joghurt", "bio").
- Keine Stoppwörter ("die", "der", "wo", "günstig", "billig", "vergleich").
- Stamm-Form bevorzugt: "wasser" statt "Wassersorten", "joghurt" statt "Joghurts".
- Bei Markenfragen: Marke direkt, z. B. "ariel", "ferrero".`;

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

async function extractKeywords(question: string): Promise<string[]> {
  const res = await llm.chat.completions.create({
    model: MODEL,
    temperature: 0,
    messages: [
      { role: "system", content: KEYWORD_SYSTEM },
      { role: "user", content: question },
    ],
    response_format: { type: "json_object" },
  });
  const content = res.choices[0]?.message?.content ?? "{}";
  const parsed = safeJson<{ keywords?: string[] }>(content, {});
  return (parsed.keywords ?? [])
    .map((k) => k.trim().toLowerCase())
    .filter((k) => k.length >= 2 && k.length <= 40)
    .slice(0, 5);
}

async function fetchCandidates(keywords: string[]): Promise<AskedOffer[]> {
  if (!keywords.length) return [];
  // ilike OR across all keywords against title.
  const orFilter = keywords
    .map((k) => `title.ilike.%${k.replace(/[%,]/g, "")}%`)
    .join(",");
  const { data, error } = await supabase
    .from("offers")
    .select("id, title, store, price, original_price, discount_percent, image_url, url, category")
    .eq("is_active", true)
    .or(orFilter)
    .order("discount_percent", { ascending: false, nullsFirst: false })
    .limit(MAX_CANDIDATES);
  if (error) {
    console.error("[ask] supabase or-query failed:", error);
    return [];
  }
  return (data ?? []) as AskedOffer[];
}

async function answerWithCitations(
  question: string,
  candidates: AskedOffer[],
): Promise<{ answer: string; citedIds: string[] }> {
  // Slim the payload — long descriptions would burn tokens.
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
    const keywords = await extractKeywords(q);
    const candidates = await fetchCandidates(keywords);
    if (candidates.length === 0) {
      return {
        ok: true,
        question: q,
        keywords,
        answer: keywords.length
          ? `Keine aktiven Angebote zu **${keywords.join(", ")}** gefunden.`
          : "Konnte keine Stichwörter aus der Frage ableiten.",
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
      keywords,
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
