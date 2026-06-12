# Quickstart Commands

Copy-paste reference for the most common operations. Full setup:
[`GETTING_STARTED.md`](GETTING_STARTED.md) · Recovery:
[`OPERATIONS_RUNBOOK.md`](OPERATIONS_RUNBOOK.md)

## Simplest path (Flask only)

You do **not** need Discord, webhooks, or OpenAI to run the app. The
minimal workflow is:

```bash
./run_standalone.command    # → http://localhost:8765
```

Put only `ESPLORO_USERNAME` and `ESPLORO_PASSWORD` in `.env`. Use the web
UI to paste citations, fill forms, and continue. Discord bot, webhook
logging, and `./start_all.sh` are optional extras.

---

## First-time setup (macOS)

```bash
git clone git@github.com:interfluve-wav/ExLibris-Automator.git
cd ExLibris-Automator
git checkout v7

bash scripts/ensure_python_venv.sh
npm install && npm run build:css
.venv/bin/python -m playwright install chromium

# Create .env — see docs/ENV_EXAMPLE.md
cp docs/ENV_EXAMPLE.md .env
# Edit .env: set ESPLORO_USERNAME and ESPLORO_PASSWORD (required)
```

---

## Run the app

### Standalone Flask web app (recommended — simplest)

This is the default way to run ExLibris Automator. No Discord token, no
webhooks, no bot setup.

```bash
cd /path/to/ExLibris-Automator
./run_standalone.command
```

Open **http://localhost:8765**

### Optional: full stack (Discord + Flask GUI)

Only use this if you want citations queued from Discord **and** the web UI.

```bash
cd /path/to/ExLibris-Automator
./start_all.sh
```

Requires `DISCORD_BOT_TOKEN` in `.env`. UI: **http://localhost:8765**

### Optional: Discord bot only (no Flask UI)

```bash
./start_smart_batch.sh
```

---

## Daily workflow (standalone)

```bash
# 1. Start
./run_standalone.command

# 2. In browser at http://localhost:8765:
#    - Paste citation(s) → Add
#    - Click Fill
#    - Review form in Chromium → Save in Esploro
#    - Click "Saved — Continue" in the web UI

# 3. Stop: Ctrl+C in the terminal
```

---

## Health checks

```bash
# App responding?
curl -sI http://127.0.0.1:8765/ | head -n 1

# Worker status (JSON)
curl -s http://127.0.0.1:8765/api/status | python3 -m json.tool

# Queue empty?
curl -s http://127.0.0.1:8765/api/queue | python3 -m json.tool

# Processes running?
pgrep -fl "esp_gui_web.py|automation.worker|discord_bot_batch_smart"
```

Expected status: `"status": "idle"` or `"processing"`, `"assetMode"` not
`ad_media_mention`.

---

## Recovery

```bash
# Worker has stale code after git pull — restart it:
pkill -f "automation.worker"
# Then click Fill again in the UI (Flask spawns a fresh worker)

# Kill everything manually:
pkill -f "automation.worker"
pkill -f "esp_gui_web.py"
pkill -f "discord_bot_batch_smart.py"

# Rebuild CSS after template changes:
npm run build:css

# Watch CSS during UI edits:
npm run watch:css
```

---

## Git (v7 workflow)

```bash
git checkout v7
git pull origin v7

# after making changes:
git status
git add <files>
git commit -m "type(scope): description"
git push origin v7
```

---

## Smoke tests (no Esploro login required)

```bash
# Python imports
.venv/bin/python -c "import esp_gui_web, automation.worker; print('OK')"

# Manual parser (works without OpenAI)
.venv/bin/python -c "
from automation.journal_impl import parse_citation
print(parse_citation('Smith, J. (2023). A study of fish. Journal of Marine Science.'))
"

# Bytecode compile
.venv/bin/python -m compileall -q automation utils esp_gui_web.py
```

---

## Environment minimum

```bash
# .env — only these are required for standalone:
ESPLORO_USERNAME=your_username
ESPLORO_PASSWORD=your_password

# OPENAI_API_KEY is optional — manual parsers run without it
```
