# Deploy the dashboard (Vercel)

Live: **https://angebotsbot.vercel.app** — Vercel project `angebotsbot`
(Hobby plan, root directory `dashboard`).

## What gets deployed

Only the Next.js dashboard in `dashboard/`. Scraping, categorizing and database
cleanup run in the daily GitHub Action (`.github/workflows/scrape.yml`), not on
Vercel. The dashboard just reads whatever is in Supabase.

Why Vercel and not Cloudflare: Cloudflare Workers' free plan allows ~10 ms of
CPU per request, and `/categories` classifies thousands of offers per render.
Vercel runs Next.js natively, no adapter.

---

## Environment variables

Set in Vercel → Project → Settings → Environment Variables (Production + Preview):

| Key | Value | Notes |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | `https://twurjtmisvohrtozkkzt.supabase.co` | |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase → Settings → API → anon key | type **config** (public by design; RLS from migration 007 protects the data) |
| `GEMINI_API_KEY` | Google AI key | server-only, for `/ask` |
| `GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | |
| `TEXT_MODEL` | `gemini-2.5-flash` | |

> **Never add `SUPABASE_SERVICE_ROLE_KEY`** to Vercel. The dashboard must never see it.

From the CLI (in `dashboard/`, after `vercel link --project angebotsbot`):

```bash
printf '%s' "$VALUE" | vercel env add GEMINI_API_KEY production --force
printf '%s' "$ANON"  | vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY production --type config --yes --force
```

---

## Deploying

- **Automatic (once GitHub is connected):** every push to `main` deploys to
  production; every other branch / PR gets a preview URL.
  One-time setup: Vercel → Account Settings → Authentication → connect GitHub,
  then Project → Settings → Git → connect `kaiser-data/AngebotsBot`.
- **Manual:** from the repo root, `vercel deploy --prod`.

Server pages revalidate every 60 s, so new scrape data shows up without a deploy.

---

## Before going public: Supabase RLS

Migration `007_tighten_rls_for_public_dashboard.sql` must be applied. After it,
anyone with the URL can read offers, price history, categories and analyses —
and **cannot** read `users`, `alerts`, `notification_log`, or write anything.
The Python side uses the `service_role` key (GitHub secret
`SUPABASE_SERVICE_ROLE_KEY`).

---

## Troubleshooting

**`Missing NEXT_PUBLIC_SUPABASE_URL`** during build → env var not set for that
environment (Production vs Preview).

**Pages say "konnte nicht geladen werden"** → Supabase is down or paused. Free
projects pause after ~7 days without activity; the daily scrape prevents that as
long as the workflow is enabled (`gh workflow list --all`).

**A page shows zero rows although Supabase has data** → RLS: the table needs an
anon `select` policy with `using (true)`.

**Database near 500 MB** → see the table sizes at the end of the daily Action
log ("Prune archived rows + log table sizes"). Old rows are archived to the
`data-archive` branch and deleted automatically (`scripts/retention.py`).
