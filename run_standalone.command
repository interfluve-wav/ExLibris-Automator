#!/bin/bash
set -e
cd "$(dirname "$0")" || exit 1

# Use config files in the current project directory
PROJECT_DIR="$(pwd)"
export BOT_CONFIG_PATH="${PROJECT_DIR}/bot_config.json"
export CITATIONS_CONFIG_PATH="${PROJECT_DIR}/citations_config.json"
export ESP_STANDALONE="1"

export REINSTALL_DEPS=0
bash "${PROJECT_DIR}/scripts/ensure_python_venv.sh"

if [ ! -f "static/css/output.css" ] && [ -f "package.json" ] && command -v npm >/dev/null 2>&1; then
  echo "🎨 Building Tailwind CSS (output.css missing)..."
  ( npm install --no-audit --no-fund 2>/dev/null || npm install )
  npm run build:css || echo "⚠️  npm run build:css failed; UI may be unstyled."
fi

# Determine which Python to use (venv required for Flask deps)
if [ -x ".venv/bin/python3" ]; then
  PYTHON_CMD=".venv/bin/python3"
  echo "Using virtual environment Python (.venv/bin/python3)"
elif [ -x ".venv/bin/python" ]; then
  PYTHON_CMD=".venv/bin/python"
  echo "Using virtual environment Python (.venv/bin/python)"
else
  echo "❌ No Python interpreter in .venv after bootstrap."
  exit 1
fi

# Cleanup function
cleanup() {
  echo "🧹 Cleaning up..."
  # Kill any worker processes
  pkill -TERM -f "automation.worker" 2>/dev/null || true
  sleep 1
  pkill -KILL -f "automation.worker" 2>/dev/null || true
}
trap cleanup EXIT

echo "🚀 Starting ESP Citation App (Standalone Mode)..."
echo "No Discord bot required."

# Launch the GUI in standalone mode
"${PYTHON_CMD}" "esp_gui_web.py" --standalone

exit 0
