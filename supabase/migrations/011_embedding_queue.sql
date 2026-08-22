-- 011: Queue embeddings instead of one pg_net HTTP call per INSERT.
--
-- Bulk scrapes were storming the generate-embedding Edge Function (one
-- cold-ish invoke per new offer). Triggers now enqueue work; the scrape
-- worker (and optionally a cron) drains the queue in batches via
-- providers.embeddings.drain_embedding_queue().

create table if not exists embedding_queue (
    id          bigserial primary key,
    table_name  text not null check (table_name in ('offers', 'alerts')),
    record_id   uuid not null,
    field       text not null default 'embedding',
    text        text not null,
    created_at  timestamptz not null default now()
);

create index if not exists embedding_queue_created_idx
    on embedding_queue (created_at, id);

-- No anon access — service_role bypasses RLS.
alter table embedding_queue enable row level security;

-- ─── Replace HTTP helper body: enqueue only ──────────────────────────────────
create or replace function trigger_generate_embedding(
    p_record_id   uuid,
    p_text        text,
    p_table       text,
    p_field       text default 'embedding'
)
returns void
language plpgsql
security definer
as $$
begin
    if p_text is null or length(trim(p_text)) = 0 then
        return;
    end if;

    insert into embedding_queue (table_name, record_id, field, text)
    values (p_table, p_record_id, p_field, trim(p_text));
end;
$$;

-- Offer trigger body unchanged (still calls trigger_generate_embedding).
-- Alert trigger body unchanged.

notify pgrst, 'reload schema';
