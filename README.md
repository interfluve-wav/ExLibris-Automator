# ExLibris Automator

ExLibris Automator is a Python automation tool that parses academic citations and fills Esploro forms using a persistent Playwright worker. It is operated primarily through Discord commands and a local web control panel.

## Quick Start

```bash
# 1) Create environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

# 2) Configure secrets and runtime settings
cp docs/ENV_EXAMPLE.md .env
# Then edit .env with required values

# 3) Run the full local stack (recommended)
./start_all.sh
```

Open the web UI at [http://localhost:8765](http://localhost:8765).

## Required Environment Variables

Set these in `.env` (never hard-code credentials in source files):

- `OPENAI_API_KEY`
- `CITATION_PARSER=openai`
- `ESPLORO_USERNAME`
- `ESPLORO_PASSWORD`
- `DISCORD_BOT_TOKEN`

Common optional variables:

- `OPENAI_MODEL` (default: `gpt-4o-mini`)
- `DEFAULT_RESEARCHER`
- `CITATION_CHANNEL_ID`
- `DISCORD_GUILD_ID`
- `BOT_CONFIG_PATH`
- `LOG_LEVEL`

## Primary Run Modes

- `./start_all.sh`  
  Starts both:
  - Discord bot (`discord_bot_batch_smart.py`)
  - Flask control panel (`esp_gui_web.py`)

- `./start_smart_batch.sh`  
  Runs the Discord bot stack directly.

- `run_esp_app.command`  
  macOS launcher for local interactive usage.

## How It Works

1. Citations are added to a queue (Discord or web UI).
2. Bot writes `citation_control_<channel>.json`.
3. Worker (`automation/worker.py`) picks up the control payload.
4. Worker parses citation + runs Playwright fill flow.
5. Worker writes `citation_status_<channel>.json` with explicit state:
   - `processing`
   - `completed`
   - `failed`
6. Bot/UI poll status and update queue + feedback.

## Architecture Overview

- `discord_bot_batch_smart.py`  
  Command handling, queueing, worker orchestration, and bot-facing status.

- `esp_gui_web.py`  
  Flask UI/API for queue control, status display, and local operations.

- `automation/worker.py`  
  Persistent Playwright session that processes one citation at a time.

- `automation/*_impl.py`  
  Asset-type-specific parsing and Esploro field automation logic.

- `openai_parser.py`  
  OpenAI-based parsing and normalization helpers.

- `utils/ipc_protocol.py`  
  Protocol definitions for file-based IPC payloads.

## Operator Notes

- Queue display in the UI reflects current-run remaining citations.
- App branding is `ExLibris Automator`.
- For UI-only requests, keep backend behavior unchanged.

## Development and Validation

```bash
# parser checks
python test_citations.py
python test_parser_simple.py

# benchmark suite
python tests/performance_tests.py
```

## Documentation Map

- `docs/INDEX.md` — Documentation entry point
- `docs/SMART_BATCH_GUIDE.md` — Daily operator workflow
- `docs/COMMANDS_REFERENCE.md` — Bot and UI command reference
- `docs/IPC_PROTOCOL.md` — IPC payload contracts
- `docs/DISCORD_SETUP.md` — Discord bot setup
- `docs/OPERATIONS_RUNBOOK.md` — Startup, health checks, and recovery

## Security and Secrets

- Do not commit `.env` or any credential files.
- Use environment variables for all secrets.
- If a secret is exposed, rotate it immediately.

## License

For educational and research use at UMass Dartmouth.