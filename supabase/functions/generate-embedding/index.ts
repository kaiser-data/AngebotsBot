/**
 * generate-embedding — Supabase Edge Function
 *
 * Zwei Verwendungszwecke:
 *
 * 1. Direkt aufgerufen (von Python für Suchanfragen):
 *    POST {"text": "Laptop unter 500 Euro"}
 *    → {"embedding": [...384 Zahlen...]}
 *
 * 2. Via Datenbank-Webhook (automatisch bei INSERT):
 *    POST {"record_id": "uuid", "text": "...", "table": "offers"|"alerts"}
 *    → updated embedding in der DB
 */

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL         = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

// gte-small: 384-dim, schnell, läuft nativ in Supabase Edge Functions
const MODEL = "gte-small";

Deno.serve(async (req: Request): Promise<Response> => {
  try {
    const body = await req.json();
    const text: string       = body.text ?? "";
    const recordId: string   = body.record_id ?? "";
    const table: string      = body.table ?? "";   // "offers" | "alerts"
    const field: string      = body.field ?? "embedding"; // "embedding" | "query_embedding"

    if (!text) {
      return json({ error: "text is required" }, 400);
    }

    // Embedding generieren mit Supabase AI (kein externer API-Aufruf)
    const session = new Supabase.ai.Session(MODEL);
    const embedding: number[] = await session.run(text, {
      mean_pool: true,
      normalize: true,
    });

    // Fall 1: Nur Embedding zurückgeben (für Python-Suchanfragen)
    if (!recordId || !table) {
      return json({ embedding });
    }

    // Fall 2: Embedding direkt in die DB schreiben (Webhook-Aufruf)
    const sb = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);
    const { error } = await sb
      .from(table)
      .update({ [field]: embedding })
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
