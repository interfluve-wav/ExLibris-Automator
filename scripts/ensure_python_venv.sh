#!/usr/bin/env bash
# Ensure project .venv exists with requirements installed. Does not require .env.
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

# #region agent log
_AGENT_LOG="$ROOT/.cursor/debug-6ce199.log"
_agent_log() {
  mkdir -p "$(dirname "$_AGENT_LOG")" 2>/dev/null || true
  printf '{"sessionId":"6ce199","timestamp":%s,"location":"ensure_python_venv.sh","message":"%s","data":%s,"hypothesisId":"%s"}\n' \
    "$(($(date +%s) * 1000))" "$1" "$2" "$3" >> "$_AGENT_LOG" 2>/dev/null || true
}
# #endregion

PY=""
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "❌ Python is not installed (python3/python)." >&2
  exit 1
fi

bootstrap() {
  echo "🔧 Creating virtual environment (.venv)…"
  "$PY" -m venv .venv || { echo "❌ Failed to create venv" >&2; exit 1; }
  # shellcheck disable=SC1091
  . .venv/bin/activate
  pip install -U pip >/dev/null 2>&1 || true
  echo "📦 Installing requirements…"
  pip install -r requirements.txt || { echo "❌ pip install failed" >&2; exit 1; }
  echo "🧭 Installing Playwright Chromium…"
  python3 -m playwright install chromium || true
}

if [ ! -d ".venv" ]; then
  bootstrap
  # #region agent log
  _agent_log "venv_bootstrapped" '{"had_venv":false}' "H-venv"
  # #endregion
elif [ ! -f ".venv/bin/activate" ]; then
  echo "❌ .venv exists but activate script not found. Delete .venv and retry." >&2
  exit 1
elif [ "${REINSTALL_DEPS:-0}" = "1" ]; then
  # shellcheck disable=SC1091
  . .venv/bin/activate
  pip install -U pip >/dev/null 2>&1 || true
  echo "🔁 Reinstalling dependencies (requirements + Playwright)…"
  pip install -r requirements.txt || { echo "❌ pip install failed" >&2; exit 1; }
  python3 -m playwright install chromium || true
  # #region agent log
  _agent_log "venv_reinstall" '{"reinstall":true}' "H-venv"
  # #endregion
else
  # #region agent log
  _agent_log "venv_ok" '{"had_venv":true,"reinstall":false}' "H-venv"
  # #endregion
  :
fi
