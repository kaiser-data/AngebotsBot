# AngebotsBot

AI-powered deal scanner for kaufda.de — scrapes offers weekly, analyses product images with a Qwen 32B vision model, stores everything in Supabase, and lets you search, compare, and get alerted via a Chainlit web UI or a fully interactive Telegram bot.

## Features

- **Weekly auto-scrape** — APScheduler runs every Monday 08:00 (Europe/Berlin); trigger on-demand via chat
- **Vision AI analysis** — Gemini 2.5 Flash (via Google AI API) analyses each product image and extracts brand, condition, key features, quality score, and deal verdict
- **Semantic search** — pgvector + gte-small embeddings (Supabase Edge Function) for natural-language offer queries
- **Comparison** — side-by-side Markdown table with LLM verdict
- **Alerts** — save search criteria; Supabase Edge Function sends weekly digests via Telegram or email (Resend)
- **Telegram bot** — fully interactive: `/suche`, `/vergleiche`, `/alert`, `/meinalerts`, `/neuerangebote`
- **Chainlit web UI** — streaming steps, inline offer images, settings panel

## Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph `StateGraph` + LangChain |
| Vision + text LLM | Gemini 2.5 Flash via [Google AI](https://ai.google.dev) |
| Embeddings | Supabase Edge Function — `gte-small` (384-dim, no GPU) |
| Database | Supabase (PostgreSQL + pgvector) |
| Web UI | Chainlit 1.3.2 |
| Telegram | python-telegram-bot v21 |
| Email | Resend |
| Scraping | Playwright (async Chromium headless) |
| Scheduling | APScheduler `AsyncIOScheduler` |
| Weekly digest | Supabase Edge Function (Deno/TypeScript) |

## Project Structure

```
AngebotsBot/
├── app.py                    # chainlit run app.py  ← entrypoint
├── config.py                 # env var loading
├── requirements.txt
├── .env.example
│
├── workflow/                 # LangGraph state machine
│   ├── state.py              # AgentState TypedDict
│   └── graph.py              # StateGraph nodes + conditional routing
│
├── agents/                   # one file per graph node
│   ├── router.py             # intent classifier
│   ├── scraper_node.py       # Playwright scraper
│   ├── vision_node.py        # Qwen VL image analysis
│   ├── store_node.py         # Supabase upsert
│   ├── query_node.py         # semantic search + RAG
│   ├── comparison_node.py    # offer comparison table
│   ├── alert_node.py         # alert CRUD
│   └── response_node.py      # final answer formatting
│
├── providers/                # shared clients (singletons)
│   ├── llm.py                # Gemini text model
│   ├── vision.py             # Gemini vision
│   ├── embeddings.py         # Supabase generate-embedding Edge Function
│   └── supabase_client.py    # Supabase singleton
│
├── scraper/                  # Playwright scraping
│   ├── kaufda.py             # KaufdaScraper class
│   ├── models.py             # Pydantic scraped-data models
│   └── utils.py              # URL fingerprinting, dedup
│
├── tools/                    # LangChain tools
│   ├── search_tool.py        # semantic_search() + @tool wrapper
│   ├── offer_tool.py         # fetch_offer_by_id, list_categories
│   └── alert_tool.py         # create/list/delete alerts + user CRUD
│
├── bot/                      # Telegram bot
│   ├── telegram_bot.py       # Application setup, long-polling
│   ├── handlers.py           # /start, /suche, /vergleiche, /alert, …
│   └── formatters.py         # Telegram HTML card formatting
│
├── notifications/
│   ├── telegram_notifier.py  # send_telegram_message()
│   └── email_notifier.py     # send_resend_email()
│
├── scheduler/
│   └── jobs.py               # APScheduler weekly cron
│
├── supabase/
│   ├── migrations/
│   │   ├── 001_initial_schema.sql   # tables, indexes, RPCs, RLS
│   │   └── 002_embedding_triggers.sql  # pg_net triggers for auto-embedding
│   └── functions/
│       ├── generate-embedding/index.ts  # gte-small embeddings
│       └── weekly-digest/index.ts       # weekly alert digest
│
└── tests/
    ├── test_scraper.py
    ├── test_vision.py
    └── test_workflow.py
```

## Quick Start

### 1. Clone and create venv

```bash
git clone <repo-url> AngebotsBot
cd AngebotsBot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# fill in: GEMINI_API_KEY, SUPABASE_URL (.supabase.co), SUPABASE_ANON_KEY,
#          SUPABASE_SERVICE_ROLE_KEY, TELEGRAM_BOT_TOKEN, RESEND_API_KEY
```

### 3. Set up Supabase

1. Create a project at [supabase.com](https://supabase.com)
2. Run migrations in the SQL editor:
   - `supabase/migrations/001_initial_schema.sql`
   - `supabase/migrations/002_embedding_triggers.sql`
3. Enable the **pg_net** extension (Database → Extensions)
4. Store secrets (used by the trigger):
   ```bash
   supabase secrets set SUPABASE_URL=https://xxx.supabase.co \
     SUPABASE_SERVICE_ROLE_KEY=eyJ...  \
     --project-ref <your-ref>
   ```
5. Deploy Edge Functions:
   ```bash
   supabase functions deploy generate-embedding --project-ref <your-ref>
   supabase functions deploy weekly-digest      --project-ref <your-ref>
   ```

### 4. Run

```bash
chainlit run app.py
# → http://localhost:8000
```

The Telegram bot and APScheduler start automatically in the background when the first chat session opens.

## LangGraph Flow

```
START → router_node
  ├─(scrape)──→ scraper_node → vision_node → store_node → response_node → END
  ├─(query)───→ query_node ──────────────────────────────→ response_node → END
  ├─(compare)─→ comparison_node ────────────────────────→ response_node → END
  ├─(alert*)──→ alert_node ──────────────────────────────→ response_node → END
  └─(unknown)─→ response_node → END
```

## Telegram Commands

| Command | Action |
|---|---|
| `/start` | Register user, show help |
| `/suche <query>` | Search offers semantically |
| `/vergleiche <query>` | Side-by-side comparison table |
| `/alert <name> <query>` | Create a saved alert |
| `/meinalerts` | List your active alerts |
| `/neuerangebote` | Trigger a manual scrape |

## Environment Variables

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google AI API key |
| `GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `VISION_MODEL` | `gemini-2.5-flash` |
| `TEXT_MODEL` | Optional cheaper text model |
| `SUPABASE_URL` | `https://xxx.supabase.co` (always `.co`) |
| `SUPABASE_ANON_KEY` | Supabase anon JWT |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role JWT |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `RESEND_API_KEY` | Resend.com API key |
| `RESEND_FROM_EMAIL` | Sender address |
| `CHAINLIT_AUTH_SECRET` | Long random string |
| `KAUFDA_MAX_PAGES_PER_CATEGORY` | Default: 3 |
| `KAUFDA_MAX_OFFERS_PER_RUN` | Default: 200 |
| `SCRAPE_CRON_DAY_OF_WEEK` | Default: `mon` |
| `SCRAPE_CRON_HOUR` | Default: `8` |

## License

MIT
