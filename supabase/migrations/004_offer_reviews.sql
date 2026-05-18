-- AngebotsBot — Human review decisions for catalog extraction

create table if not exists offer_reviews (
    id                  uuid primary key default gen_random_uuid(),
    review_session_id   text,
    reviewer_user_id    uuid references users(id) on delete set null,
    external_id         text not null,
    offer_url           text,
    image_url           text,
    scraped_title       text,
    scraped_store       text,
    scraped_price       numeric(10, 2),
    validity_text       text,
    vision_product_name text,
    vision_brand        text,
    vision_condition    text,
    vision_key_features text[],
    vision_verdict      text,
    decision            text not null check (decision in ('approved', 'rejected', 'flagged')),
    created_at          timestamptz not null default now()
);

create index if not exists offer_reviews_external_id_idx
    on offer_reviews (external_id);

create index if not exists offer_reviews_decision_idx
    on offer_reviews (decision);

create index if not exists offer_reviews_created_at_idx
    on offer_reviews (created_at desc);

create index if not exists offer_reviews_session_idx
    on offer_reviews (review_session_id);

alter table offer_reviews enable row level security;

create policy "offer_reviews_read"
    on offer_reviews for select using (true);

create policy "offer_reviews_insert"
    on offer_reviews for insert with check (true);
