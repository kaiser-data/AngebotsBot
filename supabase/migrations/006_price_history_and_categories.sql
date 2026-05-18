-- AngebotsBot — Price history + LLM category versioning
--
-- Adds two append-only tables that the dashboard needs:
--   1. price_history    — one row per scrape per offer, enables trends + percentile deal score
--   2. llm_categories   — versioned LLM category assignments, re-runnable without losing history
-- Plus a view (offer_deal_score) that computes the rolling 90-day price percentile per offer.

-- ─── price_history ───────────────────────────────────────────────────────────
create table if not exists price_history (
    id               bigserial primary key,
    offer_id         uuid references offers(id) on delete cascade,
    external_id      text not null,
    price            numeric(10, 2),
    loyalty_price    numeric(10, 2),
    original_price   numeric(10, 2),
    discount_percent numeric(5, 2),
    store            text,
    category         text,
    observed_at      timestamptz not null default now()
);

create index if not exists price_history_offer_observed_idx
    on price_history (offer_id, observed_at desc);
create index if not exists price_history_external_observed_idx
    on price_history (external_id, observed_at desc);
create index if not exists price_history_observed_idx
    on price_history (observed_at desc);

alter table price_history enable row level security;
create policy "price_history_read"   on price_history for select using (true);
create policy "price_history_insert" on price_history for insert with check (true);


-- ─── llm_categories ──────────────────────────────────────────────────────────
-- Versioned: each (external_id, model_version) pair is unique, so re-categorizing
-- with a newer model appends rather than overwrites. Latest version wins via view.
create table if not exists llm_categories (
    id               bigserial primary key,
    external_id      text not null,
    offer_id         uuid references offers(id) on delete cascade,
    category         text not null,
    subcategory      text,
    confidence       numeric(3, 2) check (confidence between 0 and 1),
    model            text not null,
    model_version    text not null,
    reasoning        text,
    classified_at    timestamptz not null default now(),
    unique (external_id, model_version)
);

create index if not exists llm_categories_external_idx on llm_categories (external_id);
create index if not exists llm_categories_offer_idx    on llm_categories (offer_id);
create index if not exists llm_categories_category_idx on llm_categories (category);
create index if not exists llm_categories_classified_idx on llm_categories (classified_at desc);

alter table llm_categories enable row level security;
create policy "llm_categories_read"   on llm_categories for select using (true);
create policy "llm_categories_insert" on llm_categories for insert with check (true);
create policy "llm_categories_update" on llm_categories for update using (true);


-- ─── view: latest LLM category per offer ─────────────────────────────────────
create or replace view offer_latest_category as
select distinct on (external_id)
    external_id,
    offer_id,
    category,
    subcategory,
    confidence,
    model,
    model_version,
    classified_at
from   llm_categories
order  by external_id, classified_at desc;


-- ─── view: deal score (rolling 90-day percentile per offer) ──────────────────
create or replace view offer_deal_score as
with hist as (
    select
        external_id,
        price,
        observed_at
    from price_history
    where observed_at >= now() - interval '90 days'
      and price is not null
),
stats as (
    select
        external_id,
        avg(price)::numeric(10, 2)    as avg_price_90d,
        min(price)::numeric(10, 2)    as min_price_90d,
        max(price)::numeric(10, 2)    as max_price_90d,
        count(*)                      as observation_count
    from hist
    group by external_id
)
select
    o.id              as offer_id,
    o.external_id,
    o.title,
    o.store,
    o.category,
    o.price           as current_price,
    o.original_price,
    o.discount_percent,
    s.avg_price_90d,
    s.min_price_90d,
    s.max_price_90d,
    s.observation_count,
    case
        when s.observation_count is null or s.observation_count < 3 then null
        when s.avg_price_90d = 0 then null
        else round(((s.avg_price_90d - o.price) / s.avg_price_90d * 100)::numeric, 1)
    end as pct_below_avg,
    case
        when s.observation_count is null or s.observation_count < 3 then null
        else (
            select round(
                (count(*) filter (where ph.price <= o.price))::numeric
                / nullif(count(*), 0) * 100, 1)
            from price_history ph
            where ph.external_id = o.external_id
              and ph.observed_at >= now() - interval '90 days'
              and ph.price is not null
        )
    end as price_percentile
from   offers o
left   join stats s on s.external_id = o.external_id
where  o.is_active = true;
