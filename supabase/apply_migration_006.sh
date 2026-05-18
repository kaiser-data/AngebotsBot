#!/usr/bin/env bash
#
# Apply migration 006 (price_history + llm_categories) to the linked Supabase project.
#
# Prerequisites:
#   - supabase CLI installed and logged in (`supabase login`)
#   - Project linked (`supabase link --project-ref twurjtmisvohrtozkkzt`)
#   - Migrations 001-005 already present in the remote schema (applied manually)
#
# You will be prompted for the remote DB password during `db push`.

set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Step 1/4: Mark 001-005 as already applied on remote"
supabase migration repair --status applied 001 002 003 004 005

echo
echo "==> Step 2/4: Verify ledger state (Local and Remote should both show 001-005)"
supabase migration list --linked

echo
read -r -p "Ledger looks correct? Press ENTER to push 006, or Ctrl-C to abort. " _

echo
echo "==> Step 3/4: Push migration 006"
supabase db push

echo
echo "==> Step 4/4: PostgREST schema cache"
echo "  Run this in Supabase Dashboard -> SQL Editor so REST sees the new tables:"
echo "      NOTIFY pgrst, 'reload schema';"
echo "  (PostgREST also auto-reloads every ~10 minutes, so this is optional.)"

echo
echo "==> Done. Verify with:"
echo "    supabase migration list --linked"
echo "    # 006 should now appear in the Remote column"
