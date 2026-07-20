-- AngebotsBot — dashboard performance + storage retention
--
-- Motivation: the Supabase project blew past the 0.5 GB free-plan cap (111%),
-- which made PostgREST cancel dashboard queries with 57014 (statement timeout)
-- and the pages rendered "0 Angebote". Two root causes:
--   1. No index on last_seen_at, which EVERY dashboard query filters on
--      (excludeStale) → sequential scan over ~85k rows per request.
--   2. Nothing ever removes stale offers or frees their embeddings, so the
--      table (and its 384-dim vectors + HNSW index) grows without bound.
--
-- This migration is idempotent. Run the one-off cleanup (the SELECT that calls
-- deactivate_stale_offers) MANUALLY after reviewing the preview counts — it
-- changes rows.

begin;

-- ── 1. Index the freshness column (+ a composite for the common pair) ────────
create index if not exists offers_last_seen_at_idx
    on offers (last_seen_at desc);

-- Every dashboard list filters is_active AND last_seen_at together.
create index if not exists offers_active_last_seen_idx
    on offers (is_active, last_seen_at desc);

commit;


-- ── 2. Retention helper: deactivate + de-embed long-unseen offers ────────────
-- Deactivating (rather than deleting) keeps price_history intact for the deal
-- score, while nulling the embedding reclaims the bulk of the storage.
create or replace function deactivate_stale_offers(max_age_days int default 21)
returns table(deactivated bigint, embeddings_cleared bigint)
language plpgsql
as $$
declare
    cutoff timestamptz := now() - make_interval(days => max_age_days);
    n_deact bigint;
    n_emb   bigint;
begin
    update offers
       set is_active = false, updated_at = now()
     where is_active = true
       and last_seen_at < cutoff;
    get diagnostics n_deact = row_count;

    update offers
       set embedding = null
     where embedding is not null
       and last_seen_at < cutoff;
    get diagnostics n_emb = row_count;

    return query select n_deact, n_emb;
end;
$$;

-- Preview first (no writes):
--   select count(*) filter (where last_seen_at < now() - interval '21 days') as stale,
--          count(*) filter (where embedding is not null
--                             and last_seen_at < now() - interval '21 days') as reclaimable
--   from offers;
--
-- Then run:
--   select * from deactivate_stale_offers(21);
--
-- Reclaim the freed pages back to the OS afterwards (needs a maintenance window;
-- VACUUM FULL takes an exclusive lock and cannot run inside a transaction):
--   vacuum full analyze offers;
