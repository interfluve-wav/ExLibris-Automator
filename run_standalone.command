#!/bin/bash
set -e
cd "$(dirname "$0")" || exit 1

# Use config files in the current project directory
PROJECT_DIR="$(pwd)"
export BOT_CONFIG_PATH="${PROJECT_DIR}/bot_config.json"
export CITATIONS_CONFIG_PATH="${PROJECT_DIR}/citations_config.json"
export ESP_STANDALONE="1"

# Determine which Python to use (prefer venv if present)
if [ -f ".venv/bin/python" ]; then
  PYTHON_CMD=".venv/bin/python"
  echo "Using virtual environment Python"
else
  PYTHON_CMD="python3"
  echo "Using system Python"
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
