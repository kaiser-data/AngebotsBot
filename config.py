"""Central configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()


# ─── Google Gemini / LLM ──────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.environ["GEMINI_API_KEY"]
GEMINI_BASE_URL: str = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)
VISION_MODEL: str = os.getenv("VISION_MODEL", "gemini-2.5-flash")
TEXT_MODEL: str = os.getenv("TEXT_MODEL", "") or "gemini-2.5-flash"

# ─── Supabase ─────────────────────────────────────────────────────────────────
# The Python bot ALWAYS uses the service_role key because it inserts/updates,
# which the public-dashboard RLS policies forbid for the anon key (migration 007).
# anon key stays available for any client-side use.
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY: str = os.environ["SUPABASE_ANON_KEY"]
SUPABASE_SERVICE_ROLE_KEY: str = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_ANON_KEY"]
)

# ─── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]

# ─── Resend ───────────────────────────────────────────────────────────────────
RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL: str = os.getenv("RESEND_FROM_EMAIL", "AngebotsBot <noreply@example.de>")

# Embeddings werden von der Supabase generate-embedding Edge Function übernommen
# (gte-small, 384-dim) — kein lokales Modell nötig
EMBEDDING_DIM: int = 384

# ─── Scraper ──────────────────────────────────────────────────────────────────
KAUFDA_MAX_PAGES_PER_CATEGORY: int = int(
    os.getenv("KAUFDA_MAX_PAGES_PER_CATEGORY", "3")
)
KAUFDA_MAX_OFFERS_PER_RUN: int = int(os.getenv("KAUFDA_MAX_OFFERS_PER_RUN", "200"))
SCRAPER_INTER_PAGE_DELAY_MIN: float = float(
    os.getenv("SCRAPER_INTER_PAGE_DELAY_MIN", "1.5")
)
SCRAPER_INTER_PAGE_DELAY_MAX: float = float(
    os.getenv("SCRAPER_INTER_PAGE_DELAY_MAX", "3.0")
)

# ─── Scheduler ────────────────────────────────────────────────────────────────
SCRAPE_CRON_DAY_OF_WEEK: str = os.getenv("SCRAPE_CRON_DAY_OF_WEEK", "mon")
SCRAPE_CRON_HOUR: int = int(os.getenv("SCRAPE_CRON_HOUR", "8"))

# ─── App ──────────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
APP_TIMEZONE: str = os.getenv("APP_TIMEZONE", "Europe/Berlin")
