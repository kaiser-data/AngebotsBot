-- AngebotsBot — Offer validity metadata

alter table offers
    add column if not exists validity_text text,
    add column if not exists valid_from date,
    add column if not exists valid_to date,
    add column if not exists is_upcoming boolean not null default false;

create index if not exists offers_valid_from_idx on offers (valid_from);
create index if not exists offers_valid_to_idx   on offers (valid_to);
create index if not exists offers_upcoming_idx   on offers (is_upcoming);


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
    validity_text    text,
    valid_from       date,
    valid_to         date,
    is_upcoming      boolean,
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
        o.validity_text,
        o.valid_from,
        o.valid_to,
        o.is_upcoming,
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
    validity_text    text,
    valid_from       date,
    valid_to         date,
    is_upcoming      boolean,
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
        o.validity_text,
        o.valid_from,
        o.valid_to,
        o.is_upcoming,
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
