-- AngebotsBot — Automatische Embeddings via Datenbank-Webhooks
--
-- Voraussetzung: pg_net Extension (in Supabase standardmäßig aktiv)
-- Die generate-embedding Edge Function muss deployed sein:
--   supabase functions deploy generate-embedding

-- ─────────────────────────────────────────────────────────────────────────────
-- Hilfsfunktion: ruft die generate-embedding Edge Function via HTTP auf
-- ─────────────────────────────────────────────────────────────────────────────
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
declare
    v_url     text;
    v_key     text;
    v_payload jsonb;
begin
    -- Supabase-Projektdaten aus den Vault-Secrets lesen
    -- (einmalig setzen: supabase secrets set SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=...)
    select decrypted_secret into v_url
        from vault.decrypted_secrets where name = 'SUPABASE_URL';

    select decrypted_secret into v_key
        from vault.decrypted_secrets where name = 'SUPABASE_SERVICE_ROLE_KEY';

    v_url := v_url || '/functions/v1/generate-embedding';

    v_payload := jsonb_build_object(
        'record_id', p_record_id::text,
        'text',      p_text,
        'table',     p_table,
        'field',     p_field
    );

    -- Async HTTP POST via pg_net (non-blocking)
    perform net.http_post(
        url     := v_url,
        headers := jsonb_build_object(
            'Content-Type',  'application/json',
            'Authorization', 'Bearer ' || v_key
        ),
        body    := v_payload
    );
end;
$$;


-- ─────────────────────────────────────────────────────────────────────────────
-- Trigger: offers — Embedding bei INSERT
-- Text = "title category store"
-- ─────────────────────────────────────────────────────────────────────────────
create or replace function embed_offer_on_insert()
returns trigger
language plpgsql
security definer
as $$
declare
    v_text text;
begin
    v_text := coalesce(new.title, '')
           || ' ' || coalesce(new.category, '')
           || ' ' || coalesce(new.store, '');

    -- Leerzeichen normalisieren
    v_text := trim(regexp_replace(v_text, '\s+', ' ', 'g'));

    perform trigger_generate_embedding(new.id, v_text, 'offers', 'embedding');
    return new;
end;
$$;

drop trigger if exists offers_embed_on_insert on offers;
create trigger offers_embed_on_insert
    after insert on offers
    for each row
    execute function embed_offer_on_insert();


-- ─────────────────────────────────────────────────────────────────────────────
-- Trigger: alerts — query_embedding bei INSERT
-- ─────────────────────────────────────────────────────────────────────────────
create or replace function embed_alert_on_insert()
returns trigger
language plpgsql
security definer
as $$
begin
    perform trigger_generate_embedding(
        new.id,
        new.query_text,
        'alerts',
        'query_embedding'
    );
    return new;
end;
$$;

drop trigger if exists alerts_embed_on_insert on alerts;
create trigger alerts_embed_on_insert
    after insert on alerts
    for each row
    execute function embed_alert_on_insert();
