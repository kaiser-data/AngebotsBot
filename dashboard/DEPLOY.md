# Deploy the dashboard to Netlify

A walkthrough for putting the dashboard at a public URL your friends can use.

## What gets deployed

Only the Next.js dashboard in `dashboard/`. The Python bot (scraper, categorizer,
Telegram) keeps running on your own machine — Netlify only runs Node, not Python.
The dashboard reads whatever's already in Supabase.

---

## One-time prep

### 1. Tighten Supabase RLS

Run migration `007_tighten_rls_for_public_dashboard.sql` in the Supabase SQL
Editor. This removes anonymous write access to every table and blocks anon reads
of the `users` / `alerts` / `notification_log` tables (which contain Telegram
chat IDs and email addresses).

```bash
# either via the Supabase CLI:
supabase db push

# or paste the migration SQL into the Supabase Dashboard SQL Editor.
```

After this, the Python bot **must** use the `service_role` key (already wired in
config.py — make sure `SUPABASE_SERVICE_ROLE_KEY` is set in your local `.env`).

### 2. Verify the gates locally

```bash
cd dashboard
npm run dev
# → http://localhost:3000 should still work — service_role bypass + anon reads cover everything the dashboard needs.
```

If a page suddenly 404s data, RLS is rejecting an anon query. Either widen the
specific RLS policy for that table or move the query server-side using
service_role.

### 3. Push to GitHub

```bash
git add netlify.toml dashboard/ scripts/ providers/supabase_client.py config.py supabase/migrations/007_*.sql .env.example
git commit -m "feat(dashboard): add Netlify deploy + tighten RLS"
git push origin main
```

---

## Netlify setup (one-time, 3 minutes)

1. Go to https://app.netlify.com → **Add new site** → **Import from Git**
2. Connect GitHub, pick `kaiser-data/AngebotsBot`
3. Netlify reads `netlify.toml` and auto-fills:
   - Base directory: `dashboard`
   - Build command: `npm ci && npm run build`
   - Publish directory: `.next`
4. Click **Show advanced** → **Environment variables**, paste these three:

   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_SUPABASE_URL` | `https://twurjtmisvohrtozkkzt.supabase.co` |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | *(your anon key from Supabase Dashboard → Settings → API)* |
   | `GEMINI_API_KEY` | *(only needed if you want `/ask` to work)* |

   > **Do NOT add `SUPABASE_SERVICE_ROLE_KEY`** to Netlify. The dashboard must never see it.

5. **Deploy site**. First build takes ~2 min.
6. You'll get a `https://random-name.netlify.app` URL. Change it under
   **Site settings → Site information → Change site name**.

---

## After deploy

- Every `git push` to `main` automatically rebuilds and redeploys.
- The dashboard always shows current Supabase data. There's no separate "data
  build step" — refreshing the page is enough.
- To force a fresh build (e.g. after editing the taxonomy), open Netlify →
  **Deploys** → **Trigger deploy → Clear cache and deploy site**.

### Running the scraper / categorizer

These stay on your machine. After they finish writing to Supabase, the next
page-view on the deployed dashboard sees the new data (server pages have a 60s
revalidate; data older than that is refetched).

```bash
# your machine, not Netlify
python -m scripts.categorize_offers --all
```

---

## What's exposed publicly

After migration 007, anyone with the URL can read:

- ✅ `offers` (titles, prices, store, image_url, validity)
- ✅ `offer_analyses` (deal verdict, tags)
- ✅ `price_history` (price trends)
- ✅ `llm_categories` (category + subcategory)
- ✅ `brochure_pages`, `offer_reviews`

And **cannot** read or write:

- 🔒 `users` (telegram_chat_id, email)
- 🔒 `alerts` (saved searches)
- 🔒 `notification_log`
- 🔒 Any write at all to the readable tables

If you ever want to add user-supplied reviews or alerts via the dashboard, those
have to go through a **Server Action with the service_role client** (a new
`supabase-server.ts` that only runs on the Netlify edge, never reaches the
browser) — happy to add that when needed.

---

## Troubleshooting

**`Missing NEXT_PUBLIC_SUPABASE_URL`** during build
→ Env var not set in Netlify → fix in **Site settings → Environment variables**.

**A page shows zero rows even though Supabase has data**
→ Almost always an RLS issue. Open Supabase → **Authentication → Policies**,
find the table, and check the anon role has a `select` policy with `using
(true)`.

**Build fails with `npm ci` cannot resolve lockfile**
→ Commit `dashboard/package-lock.json` (already committed; just confirming).
