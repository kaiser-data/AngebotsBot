-- AngebotsBot — Persisted brochure/flyer pages for supermarket review

create table if not exists brochure_pages (
    id                uuid primary key default gen_random_uuid(),
    external_id       text not null unique,
    store             text not null,
    category          text not null default 'prospekt',
    title             text not null,
    brochure_title    text,
    viewer_url        text,
    page_number       int,
    image_url         text not null,
    validity_text     text,
    valid_from        date,
    valid_to          date,
    is_upcoming       boolean not null default false,
    source            text not null default 'kaufda',
    scraped_at        timestamptz not null default now(),
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

create index if not exists brochure_pages_store_idx
    on brochure_pages (store);

create index if not exists brochure_pages_category_idx
    on brochure_pages (category);

create index if not exists brochure_pages_scraped_at_idx
    on brochure_pages (scraped_at desc);

create index if not exists brochure_pages_valid_from_idx
    on brochure_pages (valid_from);

create index if not exists brochure_pages_valid_to_idx
    on brochure_pages (valid_to);

create index if not exists brochure_pages_is_upcoming_idx
    on brochure_pages (is_upcoming);

create trigger brochure_pages_set_updated_at
    before update on brochure_pages
    for each row execute function set_updated_at();

alter table brochure_pages enable row level security;

create policy "brochure_pages_read"
    on brochure_pages for select using (true);

create policy "brochure_pages_insert"
    on brochure_pages for insert with check (true);

create policy "brochure_pages_update"
    on brochure_pages for update using (true);
