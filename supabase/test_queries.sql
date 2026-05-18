-- AngebotsBot Supabase verification queries
-- Run these sections separately in the Supabase SQL editor.
-- Set the SQL editor row limit to "No limit".

-- 1. Check that the Vault secrets exist
select
  name,
  decrypted_secret is not null as has_value
from vault.decrypted_secrets
where name in ('APP_SUPABASE_URL', 'APP_SUPABASE_SERVICE_ROLE_KEY')
order by name;


-- 2. Refresh the trigger function to read the Vault secret names
create or replace function trigger_generate_embedding(
    p_record_id uuid,
    p_text text,
    p_table text,
    p_field text default 'embedding'
)
returns void
language plpgsql
security definer
as $$
declare
    v_url text;
    v_key text;
    v_payload jsonb;
begin
    select decrypted_secret into v_url
    from vault.decrypted_secrets
    where name = 'APP_SUPABASE_URL';

    select decrypted_secret into v_key
    from vault.decrypted_secrets
    where name = 'APP_SUPABASE_SERVICE_ROLE_KEY';

    v_url := v_url || '/functions/v1/generate-embedding';

    v_payload := jsonb_build_object(
        'record_id', p_record_id::text,
        'text', p_text,
        'table', p_table,
        'field', p_field
    );

    perform net.http_post(
        url := v_url,
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'Authorization', 'Bearer ' || v_key
        ),
        body := v_payload
    );
end;
$$;


-- 3. Insert or update a test offer, which should trigger embedding generation
insert into offers (
  external_id,
  title,
  url,
  store,
  category,
  price,
  is_active
) values (
  'test-offer-1',
  'Test Angebot',
  'https://example.com/test-offer-1',
  'Test Store',
  'test',
  9.99,
  true
)
on conflict (external_id) do update
set
  title = excluded.title,
  url = excluded.url,
  store = excluded.store,
  category = excluded.category,
  price = excluded.price,
  is_active = excluded.is_active,
  last_seen_at = now(),
  scraped_at = now();

select
  external_id,
  title,
  embedding is not null as has_embedding,
  created_at,
  updated_at
from offers
where external_id = 'test-offer-1';


-- 4. Poll later to see if the async trigger has filled the embedding
select
  external_id,
  title,
  embedding is not null as has_embedding
from offers
where external_id = 'test-offer-1';
