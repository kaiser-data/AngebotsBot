/**
 * Server-side Gemini client via the OpenAI-compatible endpoint.
 * Reuses the same GEMINI_API_KEY / GEMINI_BASE_URL / TEXT_MODEL the Python bot uses.
 *
 * IMPORTANT: never imported from client components — these env vars are server-only.
 */

import "server-only";
import OpenAI from "openai";

const apiKey = process.env.GEMINI_API_KEY;
const baseURL =
  process.env.GEMINI_BASE_URL ??
  "https://generativelanguage.googleapis.com/v1beta/openai/";

if (!apiKey) {
  // Allow the dashboard to boot without Gemini; the /ask page will surface the missing key.
  console.warn("[llm] GEMINI_API_KEY not set — /ask will return an error");
}

export const llm = new OpenAI({
  apiKey: apiKey ?? "missing",
  baseURL,
});

export const MODEL = process.env.TEXT_MODEL || "gemini-2.5-flash";

export function isConfigured(): boolean {
  return Boolean(apiKey);
}
