# GitHub Actions workflows

## `scrape.yml` — Daily scrape + categorize

Runs every day at 03:17 UTC. Scrapes kaufDA via the httpx JSON scraper (no
Playwright, no browser), upserts into Supabase, appends `price_history`, then
runs the LLM categorizer over new offers.

### One-time setup

Go to **Settings → Secrets and variables → Actions → New repository secret**
and add:

| Secret | Where to find it |
|---|---|
| `SUPABASE_URL` | Supabase Dashboard → Project Settings → API |
| `SUPABASE_ANON_KEY` | same page (anon public key) |
| `SUPABASE_SERVICE_ROLE_KEY` | same page (service_role — keep it secret) |
| `GEMINI_API_KEY` | Google AI Studio |
| `GEMINI_BASE_URL` | usually `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `TEXT_MODEL` | e.g. `gemini-2.5-flash` |

That's it — the workflow handles everything else.

### Manual run

**Actions → Daily scrape + categorize → Run workflow.** You can pass
`keywords=20` for a quick smoke test, or `categorize=false` to skip the LLM step.

### What it produces

Every successful run:
- Upserts current offers into `offers`
- Appends one row per offer to `price_history` (powers deal score)
- Refreshes `last_seen_at` for everything seen (powers the dashboard's
  freshness filter — offers not seen in 8 days drop off the dashboard)
- Adds LLM categorizations for new external_ids

If the run fails, the cron just tries again tomorrow — every run is idempotent.
