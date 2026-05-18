#!/usr/bin/env bash
set -euo pipefail

PROJECT_REF="twurjtmisvohrtozkkzt"

supabase functions deploy generate-embedding --project-ref "${PROJECT_REF}"
supabase functions deploy weekly-digest --project-ref "${PROJECT_REF}"
