/**
 * generate-embedding — Supabase Edge Function
 *
 * Modes:
 * 1. Single search query (Python / dashboard Ask):
 *    POST {"text": "Laptop unter 500 Euro"}
 *    → {"embedding": [...384...]}
 *
 * 2. Batch texts (drain / bulk):
 *    POST {"texts": ["a", "b", ...]}
 *    → {"embeddings": [[...], [...], ...]}
 *
 * 3. Legacy DB webhook (record write — kept for compatibility):
 *    POST {"record_id": "uuid", "text": "...", "table": "offers"|"alerts", "field": "..."}
 *    → updates the row
 */

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL         = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const MODEL = "gte-small";

Deno.serve(async (req: Request): Promise<Response> => {
  try {
    const body = await req.json();
    const texts: string[] = Array.isArray(body.texts)
      ? body.texts.map((t: unknown) => String(t ?? "").trim())
      : body.text
      ? [String(body.text).trim()]
      : [];
    const recordId: string = body.record_id ?? "";
    const table: string = body.table ?? "";
    const field: string = body.field ?? "embedding";

    if (!texts.length || texts.every((t) => !t)) {
      return json({ error: "text or texts is required" }, 400);
    }

    const session = new Supabase.ai.Session(MODEL);
    const embeddings: number[][] = [];
    for (const text of texts) {
      if (!text) {
        embeddings.push(new Array(384).fill(0));
        continue;
      }
      const embedding = await session.run(text, {
        mean_pool: true,
        normalize: true,
      }) as number[];
      embeddings.push(embedding);
    }

    // Batch-only response (Python embed_batch / queue drain)
    if (!recordId || !table) {
      if (embeddings.length === 1) {
        return json({ embedding: embeddings[0], embeddings });
      }
      return json({ embeddings });
    }

    // Single-record write (legacy webhook path)
    const sb = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);
    const { error } = await sb
      .from(table)
      .update({ [field]: embeddings[0] })
      .eq("id", recordId);

    if (error) {
      console.error(`DB update failed for ${table}/${recordId}:`, error);
      return json({ error: error.message }, 500);
    }

    return json({ ok: true, record_id: recordId });
  } catch (err) {
    console.error("generate-embedding error:", err);
    return json({ error: String(err) }, 500);
  }
});

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
