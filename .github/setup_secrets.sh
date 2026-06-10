#!/usr/bin/env bash
#
# Push the secrets that the scrape workflow needs from your local .env to
# this repo's GitHub Actions secret store.
#
# Reads values from .env at the repo root (NEVER prints them). Uses `gh`
# under the hood, so you must be logged in (`gh auth status` should be green).
#
# Usage:
#   ./.github/setup_secrets.sh              # interactive (prompts for confirmation)
#   ./.github/setup_secrets.sh --yes        # skip confirmation
#   ./.github/setup_secrets.sh --dry-run    # show what would be set, write nothing
#
# Idempotent — running it again just overwrites the existing values.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

ENV_FILE=".env"
REQUIRED=( SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY GEMINI_API_KEY )
OPTIONAL=( GEMINI_BASE_URL TEXT_MODEL )

YES=false
DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --yes|-y) YES=true ;;
        --dry-run|-n) DRY_RUN=true ;;
        --help|-h)
            sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "unknown flag: $arg" >&2; exit 2 ;;
    esac
done

command -v gh >/dev/null || {
    echo "❌ gh CLI not installed. Install with: brew install gh" >&2
    exit 1
}
gh auth status -h github.com >/dev/null 2>&1 || {
    echo "❌ Not logged in to GitHub. Run: gh auth login" >&2
    exit 1
}
[ -f "$ENV_FILE" ] || {
    echo "❌ $ENV_FILE not found at $(pwd)" >&2
    exit 1
}

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) || {
    echo "❌ Could not detect a GitHub repo. Run inside a cloned repo." >&2
    exit 1
}

# Parse a single value from .env without exporting it to the environment.
# Strips surrounding quotes; preserves everything else verbatim (including =).
read_env() {
    local key=$1
    grep -E "^${key}=" "$ENV_FILE" \
        | head -1 \
        | sed -E "s/^${key}=//; s/^'(.*)'$/\1/; s/^\"(.*)\"\$/\\1/"
}

set_secret() {
    local name=$1 optional=${2:-no} value len
    value=$(read_env "$name" || true)
    if [ -z "${value:-}" ]; then
        if [ "$optional" = "yes" ]; then
            printf "  · %-30s skipped (not in .env)\n" "$name"
            return 0
        fi
        printf "  ✗ %-30s NOT FOUND in .env\n" "$name" >&2
        return 1
    fi
    len=${#value}
    if $DRY_RUN; then
        printf "  · %-30s would set (%d chars)\n" "$name" "$len"
        return 0
    fi
    # Pipe via stdin so the value never appears in the process list (ps).
    printf '%s' "$value" | gh secret set "$name" --repo "$REPO" >/dev/null
    printf "  ✓ %-30s set (%d chars)\n" "$name" "$len"
}

echo "Target repo:  $REPO"
echo "Source file:  $ENV_FILE"
$DRY_RUN && echo "Mode:         dry-run (no writes)"
echo

if ! $YES && ! $DRY_RUN; then
    read -r -p "Push secrets to $REPO ? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || { echo "aborted."; exit 0; }
    echo
fi

failed=0
for name in "${REQUIRED[@]}"; do
    set_secret "$name" no || failed=1
done
for name in "${OPTIONAL[@]}"; do
    set_secret "$name" yes || true
done

echo
if [ $failed -ne 0 ]; then
    echo "❌ One or more required secrets failed. Fix .env and rerun." >&2
    exit 1
fi
$DRY_RUN || echo "Done. Verify with: gh secret list --repo $REPO"
