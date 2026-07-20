-- AngebotsBot — store kaufDA's own product taxonomy
--
-- Every offer in kaufDA's __NEXT_DATA__ carries `categoryPaths`: a real
-- category tree (present on ~95% of sampled offers), e.g.
--
--   [[{"name": "Möbel und Wohnen"}, {"name": "Produkte"}, … {"name": "Ecksofa"}]]
--
-- The top level has ~12 stable values ("Lebensmittel und Getränke",
-- "Elektronik und Technik", "Drogerie und Haushalt", …) that map cleanly onto
-- the dashboard's 10 buckets. We were throwing this away and paying Gemini to
-- reconstruct it — a spend that has been failing nightly with HTTP 429
-- ("monthly spending cap exceeded"), leaving most offers uncategorized.
--
-- Two columns, both nullable so the scraper can populate them incrementally:
--   kaufda_category      — top-level bucket, used for filtering/aggregation
--   kaufda_category_path — full leaf path, kept for drill-down + debugging

begin;

alter table offers add column if not exists kaufda_category      text;
alter table offers add column if not exists kaufda_category_path text;

-- The dashboard groups by this column, so index it.
create index if not exists offers_kaufda_category_idx
    on offers (kaufda_category);

commit;

-- Backfill note: existing rows stay NULL until their next scrape refreshes
-- them (the daily run upserts on external_id, so coverage climbs on its own).
-- Check progress with:
--   select kaufda_category, count(*) from offers group by 1 order by 2 desc;
