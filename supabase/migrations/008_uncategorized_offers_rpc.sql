-- 008: Push the "which offers still need an LLM category?" diff into Postgres.
--
-- Before this, scripts/categorize_offers.py paged EVERY active offer plus EVERY
-- llm_categories row for the current model_version into Python and diffed them in
-- a set comprehension on every run — O(total offers) network traffic daily, even
-- when only a handful of offers were new. This RPC returns just the offers that
-- lack a category for p_model_version, already limited, newest first.
--
-- Called only by the bot (service_role key), which bypasses RLS.
--
-- After applying:  NOTIFY pgrst, 'reload schema';

create or replace function fetch_uncategorized_offers(
    p_model_version text,
    p_limit         int     default null,
    p_force         boolean default false
)
returns table (
    id          uuid,
    external_id text,
    title       text,
    store       text,
    category    text,
    image_url   text
)
language sql
stable
as $$
    select o.id, o.external_id, o.title, o.store, o.category, o.image_url
    from   offers o
    where  o.is_active = true
      and  (
            p_force
            or not exists (
                select 1
                from   llm_categories lc
                where  lc.external_id   = o.external_id
                  and  lc.model_version = p_model_version
            )
           )
    order  by o.scraped_at desc
    limit  p_limit;        -- LIMIT NULL = no limit
$$;

-- Refresh the PostgREST schema cache so the RPC is callable immediately.
notify pgrst, 'reload schema';
