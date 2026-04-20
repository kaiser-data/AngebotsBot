"""Central configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()


# ─── Featherless / LLM ────────────────────────────────────────────────────────
FEATHERLESS_API_KEY: str = os.environ["FEATHERLESS_API_KEY"]
FEATHERLESS_BASE_URL: str = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
VISION_MODEL: str = os.getenv("VISION_MODEL", "Qwen/Qwen2.5-VL-32B-Instruct")
TEXT_MODEL: str = os.getenv("TEXT_MODEL", "") or VISION_MODEL  # fallback to vision model

# ─── Supabase ─────────────────────────────────────────────────────────────────
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY: str = os.environ["SUPABASE_ANON_KEY"]

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
