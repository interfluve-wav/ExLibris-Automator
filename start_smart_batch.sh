#!/bin/bash
echo "🚀 Starting Discord Citation Bot (SMART BATCH MODE)..."
echo "📋 You control navigation, bot fills citation data!"
echo ""
echo "Commands:"
echo "  !f (or !fill)  - Fill next citation"
echo "  !queue         - Show queued citations"
echo "  !close         - Close the browser"
echo "  !clear         - Clear all queued citations"
echo "  !skip          - Skip current citation"
echo "  !help          - Show help message"
echo ""
echo "Workflow:"
echo "  1. Send all your citations (they get queued)"
echo "  2. Type !f → browser opens and logs in"
echo "  3. YOU manually click 'Deposit Asset', select researcher/type, click 'Next'"
echo "  4. Form auto-fills with citation data!"
echo "  5. Review and submit"
echo "  6. YOU manually click 'Deposit Asset' for next one"
echo "  7. Type !f → fills next citation"
echo "  8. Repeat until done"
echo "  9. Type !close to close browser"
echo ""
echo "If slash commands are missing: set DISCORD_GUILD_ID in .env, then use !resync (see docs/DISCORD_SETUP.md)"
echo "Press Ctrl+C to stop the bot"
echo ""

# Resolve repo root so .env, requirements.txt, and Python imports work from any cwd
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# --- .env handling ----------------------------------------------------------
if [ ! -f ".env" ]; then
  if [ "$INIT_ENV" -eq 1 ]; then
    if [ -f "docs/ENV_EXAMPLE.md" ]; then
      cp docs/ENV_EXAMPLE.md .env
      echo "🆕 Created .env from docs/ENV_EXAMPLE.md. Please review and set values."
    else
      echo "❌ docs/ENV_EXAMPLE.md not found; cannot initialize .env"
      exit 1
    fi
  else
    echo "❌ .env not found. Create one (see docs/ENV_EXAMPLE.md) or run with --init-env"
    exit 1
  fi
fi

# Export variables from .env
set +u 2>/dev/null
set -a
. .env
set +a

# Validate required environment
missing=()
[ -z "${OPENAI_API_KEY:-}" ] && missing+=(OPENAI_API_KEY)
[ -z "${ESPLORO_USERNAME:-}" ] && missing+=(ESPLORO_USERNAME)
[ -z "${ESPLORO_PASSWORD:-}" ] && missing+=(ESPLORO_PASSWORD)
[ -z "${DISCORD_BOT_TOKEN:-}" ] && missing+=(DISCORD_BOT_TOKEN)

if [ ${#missing[@]} -gt 0 ]; then
  echo "❌ Missing required .env values: ${missing[*]}"
  echo "   Edit .env and set these, then re-run."
  exit 1
fi

# Ensure parser is OpenAI by default
if [ -z "${CITATION_PARSER:-}" ]; then
  export CITATION_PARSER=openai
elif [ "${CITATION_PARSER}" != "openai" ]; then
  echo "⚠️  CITATION_PARSER='${CITATION_PARSER}' detected; only 'openai' is supported. Forcing 'openai'."
  export CITATION_PARSER=openai
fi

echo "🔑 OpenAI key: set"
echo "🤖 Parser: ${CITATION_PARSER}"
[ -n "${OPENAI_MODEL:-}" ] && echo "🧠 Model: ${OPENAI_MODEL}"
[ -n "${DISCORD_GUILD_ID:-}" ] && echo "🏷  Discord Guild ID: ${DISCORD_GUILD_ID}"
[ -n "${CITATION_CHANNEL_ID:-}" ] && echo "#️⃣ Channel ID: ${CITATION_CHANNEL_ID}"

# Ensure logs directory exists
mkdir -p logs

# Auto-bootstrap virtualenv if missing
if [ ! -d ".venv" ]; then
  # Prefer python3, fallback to python
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  elif command -v python >/dev/null 2>&1; then
    PY=python
  else
    echo "❌ Python is not installed (python3/python)."
    echo "   On Ubuntu/Gitpod: sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip"
    exit 1
  fi
  echo "🔧 Creating virtual environment (.venv)…"
  $PY -m venv .venv || { echo "❌ Failed to create venv"; exit 1; }
  # Activate and install deps
  . .venv/bin/activate
  pip install -U pip >/dev/null 2>&1 || true
  echo "📦 Installing requirements…"
  pip install -r requirements.txt || { echo "❌ pip install failed"; exit 1; }
  echo "🧭 Installing Playwright Chromium…"
  $PY -m playwright install chromium || true
else
  # Activate existing venv
  if [ -f ".venv/bin/activate" ]; then
    . .venv/bin/activate
  else
    echo "❌ .venv exists but activate script not found. Delete .venv and retry."
    exit 1
  fi
fi

# Optionally reinstall deps on demand
if [ "$REINSTALL" -eq 1 ]; then
  echo "🔁 Reinstalling dependencies (requirements + Playwright)…"
  pip install -U pip >/dev/null 2>&1 || true
  pip install -r requirements.txt || { echo "❌ pip install failed"; exit 1; }
  $PY -m playwright install chromium || true
fi

# Prefer python3 in the venv
if command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi

# Python version check (require 3.10+)
REQ_PY_MINOR=10
PY_VER=$($PY -c 'import sys; print("%d.%d" % (sys.version_info[0], sys.version_info[1]))' 2>/dev/null || echo "0.0")
PY_MAJ=${PY_VER%%.*}
PY_MIN=${PY_VER#*.}
if [ "$PY_MAJ" -lt 3 ] || { [ "$PY_MAJ" -eq 3 ] && [ "$PY_MIN" -lt $REQ_PY_MINOR ]; }; then
  echo "❌ Python $PY_VER detected. Python 3.10+ is required."
  exit 1
fi

# Ensure Playwright is available; install chromium if needed
if ! $PY -c 'import playwright' >/dev/null 2>&1; then
  echo "🧭 Installing Playwright (module) …"
  pip install playwright || { echo "❌ Failed to install playwright"; exit 1; }
fi
$PY -m playwright install chromium >/dev/null 2>&1 || true

if [ "$CHECK_ONLY" -eq 1 ]; then
  echo "✅ Environment check passed. Exiting due to --check."
  exit 0
fi

# Graceful shutdown message
trap 'echo "\n🛑 Stopping bot (Ctrl+C). Goodbye!"' INT

$PY discord_bot_batch_smart.py
