#!/usr/bin/env python3
"""Generate one SQL file for Supabase Vault secrets, schema setup, and verification."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    supabase_dir = repo_root / "supabase"
    load_dotenv(repo_root / ".env")

    supabase_url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_role_key:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")

    full_setup = (supabase_dir / "full_setup.sql").read_text(encoding="utf-8").strip()
    test_queries = (supabase_dir / "test_queries.sql").read_text(encoding="utf-8").strip()

    vault_sql = f"""-- Vault secrets generated from .env
delete from vault.secrets
where name in ('APP_SUPABASE_URL', 'APP_SUPABASE_SERVICE_ROLE_KEY');

select vault.create_secret(
  {sql_literal(supabase_url)},
  'APP_SUPABASE_URL',
  'Project URL for DB embedding trigger'
);

select vault.create_secret(
  {sql_literal(service_role_key)},
  'APP_SUPABASE_SERVICE_ROLE_KEY',
  'Service role key for DB embedding trigger'
);
"""

    one_shot = f"""-- AngebotsBot one-shot Supabase setup
-- Set the Supabase SQL editor row limit to "No limit".
-- Run the vault section first, then the setup section, then the test section.

-- ============================================================================
-- 1. Vault secrets
-- ============================================================================

{vault_sql}

-- ============================================================================
-- 2. Full setup
-- ============================================================================

{full_setup}

-- ============================================================================
-- 3. Verification queries
-- ============================================================================

{test_queries}
"""

    output_path = supabase_dir / "one_shot_setup.sql"
    output_path.write_text(one_shot, encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
