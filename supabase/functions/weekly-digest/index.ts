/**
 * AngebotsBot — Weekly Digest Edge Function
 *
 * Triggered by the Python APScheduler via supabase.functions.invoke("weekly-digest")
 * OR directly on a Supabase cron schedule:
 *   supabase functions schedule weekly-digest --cron "0 9 * * 1"
 *
 * Flow:
 *   1. Fetch all active alerts
 *   2. Group by user
 *   3. For each alert: call search_offers_since RPC (last 7 days)
 *   4. Send digest via Telegram (primary) or Resend email (secondary)
 *   5. Log results to notification_log
 *   6. Update alerts.last_triggered_at
 */

import { createClient } from "@supabase/supabase-js";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Alert {
  id: string;
  user_id: string;
  name: string;
  query_text: string;
  max_price: number | null;
  min_discount: number | null;
  categories: string[] | null;
  query_embedding: number[];
  similarity_threshold: number;
}

interface User {
  id: string;
  telegram_chat_id: string | null;
  email: string | null;
  notification_channel: "telegram" | "email" | "both";
}

interface MatchedOffer {
  offer_id: string;
  title: string;
  price: number;
  original_price: number;
  discount_percent: number;
  store: string;
  url: string;
  image_url: string;
  deal_verdict: string;
  quality_score: number;
  similarity: number;
}

// ── Env vars ──────────────────────────────────────────────────────────────────

const SUPABASE_URL            = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_KEY    = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const TELEGRAM_BOT_TOKEN      = Deno.env.get("TELEGRAM_BOT_TOKEN")!;
const RESEND_API_KEY          = Deno.env.get("RESEND_API_KEY") ?? "";
const RESEND_FROM             = Deno.env.get("RESEND_FROM_EMAIL") ?? "AngebotsBot <noreply@example.de>";

const ONE_WEEK_AGO = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

// ── Supabase client (service role — full access) ──────────────────────────────

const sb = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

// ── Entry point ───────────────────────────────────────────────────────────────

Deno.serve(async (_req: Request): Promise<Response> => {
  try {
    // 1. Load all active alerts
    const { data: alerts, error: alertsErr } = await sb
      .from("alerts")
      .select("*")
      .eq("is_active", true);

    if (alertsErr) throw new Error(`Failed to load alerts: ${alertsErr.message}`);
    if (!alerts || alerts.length === 0) {
      return json({ message: "No active alerts — nothing to send" });
    }

    // 2. Group alerts by user_id
    const byUser = new Map<string, Alert[]>();
    for (const alert of alerts as Alert[]) {
      const list = byUser.get(alert.user_id) ?? [];
      list.push(alert);
      byUser.set(alert.user_id, list);
    }

    // Batch-load users (avoid N+1 .single() per user)
    const userIds = [...byUser.keys()];
    const { data: usersData, error: usersErr } = await sb
      .from("users")
      .select("*")
      .in("id", userIds);
    if (usersErr) throw new Error(`Failed to load users: ${usersErr.message}`);
    const usersById = new Map<string, User>();
    for (const u of (usersData ?? []) as User[]) {
      usersById.set(u.id, u);
    }

    const summary: Record<string, unknown> = {};

    // 3. Process each user
    for (const [userId, userAlerts] of byUser) {
      const user = usersById.get(userId) ?? null;
      if (!user) continue;
      if (!user.telegram_chat_id && !user.email) continue;

      // 4. Find matching offers for each alert
      const digestSections: { alertName: string; offers: MatchedOffer[] }[] = [];
      const allOfferIds: string[] = [];

      for (const alert of userAlerts) {
        const offers = await findMatchingOffers(alert);
        if (offers.length === 0) continue;

        allOfferIds.push(...offers.map((o) => o.offer_id));
        digestSections.push({ alertName: alert.name, offers });
      }

      if (digestSections.length === 0) {
        summary[userId] = "no matching offers";
        continue;
      }

      const channel = user.notification_channel;
      let sent = false;

      // 5a. Telegram
      if ((channel === "telegram" || channel === "both") && user.telegram_chat_id) {
        const html = buildTelegramMessage(digestSections);
        const ok   = await sendTelegram(user.telegram_chat_id, html);
        await logNotification(userId, userAlerts[0].id, "telegram",
          ok ? "sent" : "failed", allOfferIds, ok ? undefined : "sendTelegram returned false");
        if (ok) sent = true;
      }

      // 5b. Email (Resend)
      if ((channel === "email" || channel === "both") && user.email && RESEND_API_KEY) {
        const html = buildEmailHtml(digestSections);
        const ok   = await sendEmail(user.email, html);
        await logNotification(userId, userAlerts[0].id, "email",
          ok ? "sent" : "failed", allOfferIds, ok ? undefined : "sendEmail returned false");
        if (ok) sent = true;
      }

      // 6. Update last_triggered_at for all user's alerts
      await sb
        .from("alerts")
        .update({ last_triggered_at: new Date().toISOString() })
        .in("id", userAlerts.map((a) => a.id));

      summary[userId] = sent
        ? `sent ${digestSections.length} sections`
        : "failed to send";
    }

    return json({ ok: true, summary });

  } catch (err) {
    console.error("weekly-digest error:", err);
    return json({ error: String(err) }, 500);
  }
});

// ── Helpers ───────────────────────────────────────────────────────────────────

async function findMatchingOffers(alert: Alert): Promise<MatchedOffer[]> {
  const { data, error } = await sb.rpc("search_offers_since", {
    query_embedding:   alert.query_embedding,
    since_timestamp:   ONE_WEEK_AGO,
    similarity_cutoff: alert.similarity_threshold,
    max_price_filter:  alert.max_price,
    category_filter:   alert.categories?.[0] ?? null,
    result_limit:      8,
  });

  if (error) {
    console.error(`search_offers_since failed for alert ${alert.id}:`, error);
    return [];
  }
  return (data ?? []) as MatchedOffer[];
}

function buildTelegramMessage(
  sections: { alertName: string; offers: MatchedOffer[] }[]
): string {
  const parts = ["🛍️ <b>Dein wöchentlicher Angebots-Digest</b>\n"];

  for (const { alertName, offers } of sections) {
    parts.push(`\n📌 <b>${esc(alertName)}</b>`);
    offers.slice(0, 5).forEach((o, i) => {
      const price = o.price ? `€${o.price.toFixed(2)}` : "?";
      const disc  = o.discount_percent ? ` -${o.discount_percent.toFixed(0)}%` : "";
      parts.push(
        `${i + 1}. <a href="${o.url}"><b>${esc(o.title.slice(0, 55))}</b></a>\n` +
        `   💰 ${price}${disc}  |  🏪 ${esc(o.store ?? "?")}  |  ${o.deal_verdict ?? ""}`
      );
    });
    parts.push("─".repeat(20));
  }

  return parts.join("\n");
}

function buildEmailHtml(
  sections: { alertName: string; offers: MatchedOffer[] }[]
): string {
  const rows = sections
    .map(({ alertName, offers }) => {
      const offerRows = offers
        .slice(0, 5)
        .map((o) => {
          const price = o.price ? `€${o.price.toFixed(2)}` : "?";
          const disc  = o.discount_percent ? `-${o.discount_percent.toFixed(0)}%` : "";
          return `<tr>
            <td style="padding:8px;border-bottom:1px solid #eee">
              <a href="${o.url}" style="color:#6366f1;font-weight:bold">${htmlEnc(o.title.slice(0, 60))}</a><br>
              <small>${htmlEnc(o.store ?? "")}</small>
            </td>
            <td style="padding:8px;border-bottom:1px solid #eee;white-space:nowrap">
              <b>${price}</b> ${disc}
            </td>
            <td style="padding:8px;border-bottom:1px solid #eee">${o.deal_verdict ?? ""}</td>
          </tr>`;
        })
        .join("");

      return `<h3 style="color:#6366f1;margin-top:24px">${htmlEnc(alertName)}</h3>
        <table width="100%" style="border-collapse:collapse;font-size:14px">
          <tr style="background:#f9fafb">
            <th style="padding:8px;text-align:left">Produkt</th>
            <th style="padding:8px;text-align:left">Preis</th>
            <th style="padding:8px;text-align:left">Bewertung</th>
          </tr>
          ${offerRows}
        </table>`;
    })
    .join("");

  return `<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:auto;padding:20px;color:#111">
    <h2 style="color:#6366f1">🛍️ Dein wöchentlicher Angebots-Digest</h2>
    <p>Die besten neuen Deals für deine gespeicherten Suchen:</p>
    ${rows}
    <hr style="margin-top:32px;border:none;border-top:1px solid #eee">
    <p style="color:#888;font-size:12px">AngebotsBot — Daten von kaufda.de, analysiert mit Qwen VL 32B</p>
  </body></html>`;
}

async function sendTelegram(chatId: string, html: string): Promise<boolean> {
  const text = html.length > 4000 ? html.slice(0, 3990) + "\n…" : html;
  try {
    const res = await fetch(
      `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId, text, parse_mode: "HTML" }),
      }
    );
    return res.ok;
  } catch {
    return false;
  }
}

async function sendEmail(to: string, html: string): Promise<boolean> {
  if (!RESEND_API_KEY) return false;
  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from:    RESEND_FROM,
        to:      [to],
        subject: "🛍️ Deine wöchentlichen Angebote",
        html,
      }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

async function logNotification(
  userId: string,
  alertId: string | null,
  channel: string,
  status: string,
  offerIds: string[],
  errorMessage?: string
): Promise<void> {
  await sb.from("notification_log").insert({
    user_id:       userId,
    alert_id:      alertId,
    channel,
    status,
    offer_ids:     offerIds,
    error_message: errorMessage ?? null,
    sent_at:       new Date().toISOString(),
  });
}

function esc(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function htmlEnc(text: string): string {
  return esc(text).replace(/"/g, "&quot;");
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
