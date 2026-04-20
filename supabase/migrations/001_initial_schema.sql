-- AngebotsBot — Initial Database Schema

create extension if not exists vector;

-- ─── offers ──────────────────────────────────────────────────────────────────
create table if not exists offers (
    id                uuid primary key default gen_random_uuid(),
    external_id       text not null unique,
    title             text not null,
    url               text not null,
    image_url         text,
    price             numeric(10, 2),
    original_price    numeric(10, 2),
    discount_percent  numeric(5, 2),
    store             text,
    category          text,
    is_active         boolean not null default true,
    first_seen_at     timestamptz not null default now(),
    last_seen_at      timestamptz not null default now(),
    scraped_at        timestamptz not null default now(),
    embedding         vector(384),
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

-- hnsw funktioniert auf leeren Tabellen (ivfflat nicht)
create index if not exists offers_embedding_idx
    on offers using hnsw (embedding vector_cosine_ops);

create index if not exists offers_category_idx    on offers (category);
create index if not exists offers_store_idx       on offers (store);
create index if not exists offers_price_idx       on offers (price);
create index if not exists offers_is_active_idx   on offers (is_active);
create index if not exists offers_scraped_at_idx  on offers (scraped_at desc);
create index if not exists offers_discount_idx    on offers (discount_percent desc nulls last);


-- ─── offer_analyses ──────────────────────────────────────────────────────────
create table if not exists offer_analyses (
    id                uuid primary key default gen_random_uuid(),
    offer_id          uuid not null references offers(id) on delete cascade,
    product_name      text,
    brand             text,
    condition         text check (condition in ('neu', 'gebraucht', 'refurbished', 'unbekannt')),
    key_features      text[],
    quality_score     numeric(3, 2) check (quality_score between 0 and 1),
    deal_verdict      text check (deal_verdict in ('Sehr gut', 'Gut', 'Durchschnittlich', 'Schlecht')),
    tags              text[],
    raw_llm_response  text,
    model_used        text not null default 'Qwen2.5-VL-32B-Instruct',
    analyzed_at       timestamptz not null default now(),
    created_at        timestamptz not null default now()
);

create unique index if not exists offer_analyses_offer_id_idx on offer_analyses (offer_id);
create index if not exists offer_analyses_verdict_idx on offer_analyses (deal_verdict);
create index if not exists offer_analyses_quality_idx on offer_analyses (quality_score desc);


-- ─── users ───────────────────────────────────────────────────────────────────
create table if not exists users (
    id                    uuid primary key default gen_random_uuid(),
    telegram_chat_id      text unique,
    email                 text unique,
    notification_channel  text not null default 'telegram'
                              check (notification_channel in ('telegram', 'email', 'both')),
    is_active             boolean not null default true,
    timezone              text not null default 'Europe/Berlin',
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now(),
    constraint users_contact_check
        check (telegram_chat_id is not null or email is not null)
);

create index if not exists users_telegram_idx on users (telegram_chat_id) where telegram_chat_id is not null;
create index if not exists users_email_idx    on users (email) where email is not null;


-- ─── alerts ──────────────────────────────────────────────────────────────────
create table if not exists alerts (
    id                   uuid primary key default gen_random_uuid(),
    user_id              uuid not null references users(id) on delete cascade,
    name                 text not null,
    query_text           text not null,
    max_price            numeric(10, 2),
    min_discount         numeric(5, 2),
    categories           text[],
    stores               text[],
    query_embedding      vector(384),
    similarity_threshold numeric(3, 2) not null default 0.70,
    is_active            boolean not null default true,
    last_triggered_at    timestamptz,
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now()
);

create index if not exists alerts_user_id_idx   on alerts (user_id);
create index if not exists alerts_is_active_idx on alerts (is_active);
create index if not exists alerts_query_emb_idx
    on alerts using hnsw (query_embedding vector_cosine_ops);


-- ─── notification_log ────────────────────────────────────────────────────────
create table if not exists notification_log (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references users(id) on delete cascade,
    alert_id        uuid references alerts(id) on delete set null,
    channel         text not null check (channel in ('telegram', 'email')),
    status          text not null check (status in ('sent', 'failed', 'skipped')),
    offer_ids       uuid[],
    payload_summary text,
    error_message   text,
    sent_at         timestamptz not null default now()
);

create index if not exists notification_log_user_idx    on notification_log (user_id);
create index if not exists notification_log_alert_idx   on notification_log (alert_id);
create index if not exists notification_log_sent_at_idx on notification_log (sent_at desc);


-- ─── RPC: search_offers ──────────────────────────────────────────────────────
create or replace function search_offers(
    query_embedding   vector(384),
    similarity_cutoff numeric  default 0.6,
    max_price_filter  numeric  default null,
    category_filter   text     default null,
    result_limit      int      default 20
)
returns table (
    offer_id         uuid,
    title            text,
    price            numeric,
    original_price   numeric,
    discount_percent numeric,
    store            text,
    category         text,
    url              text,
    image_url        text,
    deal_verdict     text,
    quality_score    numeric,
    tags             text[],
    key_features     text[],
    similarity       double precision
)
language sql stable
as $$
    select
        o.id,
        o.title,
        o.price,
        o.original_price,
        o.discount_percent,
        o.store,
        o.category,
        o.url,
        o.image_url,
        a.deal_verdict,
        a.quality_score,
        a.tags,
        a.key_features,
        1 - (o.embedding <=> query_embedding) as similarity
    from   offers o
    left   join offer_analyses a on a.offer_id = o.id
    where  o.is_active = true
      and  o.embedding is not null
      and  1 - (o.embedding <=> query_embedding) >= similarity_cutoff
      and  (max_price_filter is null or o.price <= max_price_filter)
      and  (category_filter  is null or o.category ilike '%' || category_filter || '%')
    order  by similarity desc
    limit  result_limit;
$$;


-- ─── RPC: search_offers_since ─────────────────────────────────────────────────
create or replace function search_offers_since(
    query_embedding   vector(384),
    since_timestamp   timestamptz,
    similarity_cutoff numeric  default 0.6,
    max_price_filter  numeric  default null,
    category_filter   text     default null,
    result_limit      int      default 10
)
returns table (
    offer_id         uuid,
    title            text,
    price            numeric,
    original_price   numeric,
    discount_percent numeric,
    store            text,
    category         text,
    url              text,
    image_url        text,
    deal_verdict     text,
    quality_score    numeric,
    similarity       double precision
)
language sql stable
as $$
    select
        o.id,
        o.title,
        o.price,
        o.original_price,
        o.discount_percent,
        o.store,
        o.category,
        o.url,
        o.image_url,
        a.deal_verdict,
        a.quality_score,
        1 - (o.embedding <=> query_embedding) as similarity
    from   offers o
    left   join offer_analyses a on a.offer_id = o.id
    where  o.is_active = true
      and  o.embedding is not null
      and  o.scraped_at >= since_timestamp
      and  1 - (o.embedding <=> query_embedding) >= similarity_cutoff
      and  (max_price_filter is null or o.price <= max_price_filter)
      and  (category_filter  is null or o.category ilike '%' || category_filter || '%')
    order  by similarity desc
    limit  result_limit;
$$;


-- ─── updated_at triggers ─────────────────────────────────────────────────────
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger offers_set_updated_at
    before update on offers
    for each row execute function set_updated_at();

create trigger users_set_updated_at
    before update on users
    for each row execute function set_updated_at();

create trigger alerts_set_updated_at
    before update on alerts
    for each row execute function set_updated_at();


-- ─── RLS ─────────────────────────────────────────────────────────────────────
alter table offers enable row level security;
create policy "offers_read"   on offers for select using (true);
create policy "offers_insert" on offers for insert with check (true);
create policy "offers_update" on offers for update using (true);

alter table offer_analyses enable row level security;
create policy "analyses_read"   on offer_analyses for select using (true);
create policy "analyses_insert" on offer_analyses for insert with check (true);
create policy "analyses_update" on offer_analyses for update using (true);

alter table users enable row level security;
create policy "users_all" on users using (true) with check (true);

alter table alerts enable row level security;
create policy "alerts_all" on alerts using (true) with check (true);

alter table notification_log enable row level security;
create policy "notif_log_insert" on notification_log for insert with check (true);
create policy "notif_log_read"   on notification_log for select using (true);
