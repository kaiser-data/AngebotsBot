-- 007: Tighten RLS so the anon key (which ships in the public dashboard bundle)
-- can ONLY read what the dashboard actually displays — and cannot read or modify
-- anything user-related.
--
-- Writes (scraper inserts, categorizer upserts) keep working because the Python
-- bot uses the SERVICE_ROLE key, which bypasses RLS entirely.
--
-- After applying:  NOTIFY pgrst, 'reload schema';

-- ─── offers ──────────────────────────────────────────────────────────────────
drop policy if exists offers_read   on offers;
drop policy if exists offers_insert on offers;
drop policy if exists offers_update on offers;
create policy "offers_anon_read" on offers
    for select to anon using (true);

-- ─── offer_analyses ──────────────────────────────────────────────────────────
drop policy if exists analyses_read   on offer_analyses;
drop policy if exists analyses_insert on offer_analyses;
drop policy if exists analyses_update on offer_analyses;
create policy "offer_analyses_anon_read" on offer_analyses
    for select to anon using (true);

-- ─── price_history (read-only for anon) ──────────────────────────────────────
drop policy if exists price_history_read   on price_history;
drop policy if exists price_history_insert on price_history;
create policy "price_history_anon_read" on price_history
    for select to anon using (true);

-- ─── llm_categories (read-only for anon) ─────────────────────────────────────
drop policy if exists llm_categories_read   on llm_categories;
drop policy if exists llm_categories_insert on llm_categories;
drop policy if exists llm_categories_update on llm_categories;
create policy "llm_categories_anon_read" on llm_categories
    for select to anon using (true);

-- ─── brochure_pages (read-only for anon) ─────────────────────────────────────
drop policy if exists brochure_pages_read   on brochure_pages;
drop policy if exists brochure_pages_insert on brochure_pages;
drop policy if exists brochure_pages_update on brochure_pages;
create policy "brochure_pages_anon_read" on brochure_pages
    for select to anon using (true);

-- ─── offer_reviews (read-only for anon) ──────────────────────────────────────
drop policy if exists offer_reviews_read   on offer_reviews;
drop policy if exists offer_reviews_insert on offer_reviews;
create policy "offer_reviews_anon_read" on offer_reviews
    for select to anon using (true);

-- ─── users / alerts / notification_log (NO anon access at all) ───────────────
-- These contain telegram_chat_id, email addresses, alert configurations.
-- Drop every existing policy; with RLS enabled and no policy, anon gets nothing.
drop policy if exists users_all              on users;
drop policy if exists alerts_all             on alerts;
drop policy if exists notif_log_insert       on notification_log;
drop policy if exists notif_log_read         on notification_log;

-- Refresh the PostgREST schema cache so the change takes effect immediately.
notify pgrst, 'reload schema';
