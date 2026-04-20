#!/usr/bin/env bash
# AngebotsBot — einmaliges Setup mit venv
set -e

VENV_DIR=".venv"

echo "→ Python-Version prüfen..."
python3 --version

echo "→ Virtuelle Umgebung erstellen ($VENV_DIR)..."
python3 -m venv "$VENV_DIR"

echo "→ Aktiviere venv..."
source "$VENV_DIR/bin/activate"

echo "→ pip upgraden..."
pip install --upgrade pip

echo "→ Abhängigkeiten installieren..."
pip install -r requirements.txt

echo "→ Playwright Chromium installieren..."
playwright install chromium

echo "→ .env anlegen (falls noch nicht vorhanden)..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   ⚠️  Bitte .env ausfüllen (FEATHERLESS_API_KEY, SUPABASE_URL, TELEGRAM_BOT_TOKEN, ...)"
else
    echo "   .env existiert bereits — übersprungen."
fi

echo ""
echo "✅ Setup abgeschlossen!"
echo ""
echo "Nächste Schritte:"
echo "  1. .env ausfüllen"
echo "  2. SQL-Schema in Supabase ausführen: supabase/migrations/001_initial_schema.sql"
echo "  3. App starten:"
echo ""
echo "     source $VENV_DIR/bin/activate"
echo "     chainlit run app.py"
