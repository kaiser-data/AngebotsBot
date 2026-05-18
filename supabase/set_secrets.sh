#!/usr/bin/env bash
set -euo pipefail

# Supabase secrets setup for AngebotsBot
# Loads required values from the repo .env file.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ ! -f "${ROOT_DIR}/.env" ]; then
  echo ".env not found at ${ROOT_DIR}/.env" >&2
  exit 1
fi

set -a
. "${ROOT_DIR}/.env"
set +a

: "${SUPABASE_URL:?SUPABASE_URL is required in .env}"
: "${SUPABASE_SERVICE_ROLE_KEY:?SUPABASE_SERVICE_ROLE_KEY is required in .env}"
: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is required in .env}"
: "${RESEND_API_KEY:?RESEND_API_KEY is required in .env}"
: "${RESEND_FROM_EMAIL:?RESEND_FROM_EMAIL is required in .env}"

supabase secrets set \
  APP_SUPABASE_URL="${SUPABASE_URL}" \
  APP_SUPABASE_SERVICE_ROLE_KEY="${SUPABASE_SERVICE_ROLE_KEY}" \
  TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN}" \
  RESEND_API_KEY="${RESEND_API_KEY}" \
  RESEND_FROM_EMAIL="${RESEND_FROM_EMAIL}" \
  --project-ref twurjtmisvohrtozkkzt
