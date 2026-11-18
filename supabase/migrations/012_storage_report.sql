-- 012: storage_report() — table sizes for the daily retention log.
--
-- The free plan caps the database at 500 MB, and going over it paused the
-- project. scripts/retention.py logs this after every prune so growth is
-- visible in the GitHub Actions log long before the limit is hit.
--
-- Read-only, service_role only. Safe to run in the SQL Editor.

create or replace function storage_report()
returns table(relation text, total_bytes bigint, row_estimate bigint)
language sql
stable
security definer
set search_path = public, pg_catalog
as $$
    select 'database (total)'::text, pg_database_size(current_database()), null::bigint
    union all
    select c.relname::text,
           pg_total_relation_size(c.oid),
           greatest(c.reltuples, 0)::bigint
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public'
       and c.relkind = 'r'
     order by 2 desc;
$$;

revoke all on function storage_report() from public, anon, authenticated;
grant execute on function storage_report() to service_role;

notify pgrst, 'reload schema';
