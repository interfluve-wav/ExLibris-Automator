# ExLibris Automator (Esploro Bot)

A Python automation suite that streamlines entry of academic citations into the UMassD Esploro research repository. It uses AI-driven parsing (OpenAI GPT-4o-mini) to extract metadata from citations and browser automation (Playwright) to populate web forms automatically.

---

## Features

- **Web UI** — Flask-based control panel for managing citations, controlling the worker, and monitoring status
- **AI Citation Parsing** — Parses unstructured citation text into structured metadata using OpenAI (with regex fallback)
- **Browser Automation** — Playwright fills Esploro web forms for journals, presentations, posters, proceedings, book chapters, abstracts, and technical documentation
- **Citation Matcher** — Fuzzy-match interface to compare and deduplicate citations
- **Discord Integration** — Optional Discord bot for command-driven citation queueing
- **Auto-Restart** — Configurable worker restart policy to keep long sessions stable

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ (for Tailwind CSS builds)
- Playwright browsers installed (`playwright install chromium`)

### Environment Variables

Set these in `.env` or as environment/Replit secrets (never hard-code credentials):

| Variable | Required | Description |
|----------|----------|-------------|
| `ESPLORO_USERNAME` | Yes | Esploro login username |
| `ESPLORO_PASSWORD` | Yes | Esploro login password |
| `OPENAI_API_KEY` | No | Enables AI citation parsing (falls back to regex parser if unset) |
| `OPENAI_MODEL` | No | Model for parsing (default: `gpt-4o-mini`) |
| `DISCORD_BOT_TOKEN` | No | Required for Discord bot mode |
| `CITATION_CHANNEL_ID` | No | Discord channel ID for bot mode |
| `DEFAULT_RESEARCHER` | No | Default researcher name (defaults to "Scarano, Frank J") |
| `DISCORD_GUILD_ID` | No | Discord guild/server ID |
| `BOT_CONFIG_PATH` | No | Path to bot_config.json |
| `LOG_LEVEL` | No | Logging verbosity |

### Running

**Standalone mode** (no Discord bot required):

```bash
python esp_gui_web.py --standalone --port 5000
```

**With Discord bot**:

```bash
./start_all.sh
```

The web UI will be available at `http://localhost:5000` (standalone) or `http://localhost:8765` (start_all.sh).

---

## Project Structure

```
.
├── esp_gui_web.py              # Main Flask web application (1500+ lines)
├── openai_parser.py            # AI-powered citation parser (GPT-4o-mini + regex fallback)
├── discord_bot_batch_smart.py  # Discord bot for batch citation processing
│
├── automation/                 # Playwright browser automation modules
│   ├── worker.py               # Persistent browser worker (login, navigation, form dispatch)
│   ├── journal_impl.py         # Journal article form filling
│   ├── presentations_impl.py   # Presentations form filling
│   ├── poster_impl.py          # Poster form filling
│   ├── proceedings_impl.py     # Conference proceedings form filling
│   ├── book_chapters_impl.py   # Book chapters form filling
│   ├── abstract_impl.py        # Abstract form filling
│   ├── technical_documentation_impl.py  # Technical documentation form filling
│   └── *.py                    # Matching router modules (journal.py, poster.py, etc.)
│
├── utils/                      # Shared helper modules
│   ├── asset_type_utils.py     # Asset type normalization and detection
│   ├── author_automation.py    # Author field automation helpers
│   ├── citation_parser_utils.py # Citation parsing utilities (regex, extraction)
│   ├── config_manager.py       # JSON config file manager with thread safety
│   ├── config_utils.py         # Configuration helpers
│   ├── input_validation.py     # Citation text validation and sanitization
│   ├── ipc_protocol.py         # Inter-process communication protocol
│   └── logging_utils.py        # Structured logging setup
│
├── templates/                  # Flask HTML templates
│   ├── index.html              # Main control panel UI
│   └── matcher.html            # Citation matcher/dedup UI
│
├── static/css/                 # Compiled CSS
│   └── output.css              # Tailwind CSS output (built from src/input.css)
│
├── src/
│   └── input.css               # Tailwind CSS source with custom components
│
├── bot_config.json             # Bot configuration (researchers, asset types)
├── citations_config.json       # Citation processing configuration
├── tailwind.config.js          # Tailwind CSS + Material Tailwind configuration
├── package.json                # Node.js dependencies (Tailwind, PostCSS)
│
├── start_all.sh                # Launch everything (bot + worker + web)
├── start_desktop.sh            # Start Xvfb + VNC for headed browser viewing
├── start_smart_batch.sh        # Start smart batch processing
├── quick_deploy.sh             # Deployment helper script
│
└── test_*.py                   # Test files for parser and automation modules
```

---

## Architecture

### Components

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────────┐
│   Web UI (Flask) │────▶│ StandaloneManager │────▶│ Worker (Playwright) │
│   Port 5000      │     │  Citation Queue   │     │ Browser Automation  │
└─────────────────┘     └──────────────────┘     └────────────────────┘
        │                        │                         │
        │                        ▼                         ▼
        │               ┌──────────────┐          ┌──────────────────┐
        │               │ OpenAI Parser │          │ Esploro Web Forms │
        │               │ (GPT-4o-mini) │          │ (UMassD Library)  │
        │               └──────────────┘          └──────────────────┘
        │
        ▼
┌─────────────────┐
│  Discord Bot     │  (optional, alternative input)
│  (batch mode)    │
└─────────────────┘
```

### How It Works

1. **Add citations** — Paste citation text into the web UI (or send via Discord). Multiple citations are split by blank lines.
2. **Parse** — Each citation is parsed by OpenAI GPT-4o-mini into structured metadata (title, authors, year, DOI, conference name, etc.). Falls back to regex-based parsing if no API key is set.
3. **Queue** — Parsed citations are added to an in-memory queue managed by `StandaloneManager`.
4. **Fill** — The Playwright worker picks the next citation, navigates Esploro, selects the correct asset type, and fills all form fields automatically.
5. **Review & Save** — The user reviews the filled form in the browser, then clicks "Saved — Continue" in the web UI.
6. **Repeat** — The worker navigates home and processes the next citation.

### Inter-Process Communication

The Flask app and the Playwright worker communicate via JSON control files in the project root:

| File | Purpose |
|------|---------|
| `gui_skip.json` | Skip the current citation |
| `gui_go_home.json` | Navigate to UMassD Libraries home |
| `gui_continue.json` | Signal that the user saved and is ready to continue |
| `gui_pause.json` | Pause the worker loop |
| `gui_set_restart_policy.json` | Configure auto-restart interval |
| `citation_control_<channel>.json` | Worker control payload (written by bot/standalone manager) |
| `citation_status_<channel>.json` | Worker status feedback (processing/completed/failed) |

---

## API Reference

All endpoints are served from the Flask app.

### Pages

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Main control panel |
| `/matcher` | GET | Citation matcher/dedup interface |

### Status & Logs

| Route | Method | Description |
|-------|--------|-------------|
| `/api/status` | GET | Current worker status (state, queue size, researcher, etc.) |
| `/api/queue` | GET | List all queued citations |
| `/api/logs` | GET | Tail recent log lines |

### Citation Management

| Route | Method | Body | Description |
|-------|--------|------|-------------|
| `/api/add` | POST | `{ "text": "..." }` | Add citation(s) to the queue |
| `/api/fill` | POST | — | Trigger the worker to process the next citation |
| `/api/clear` | POST | — | Clear all queued citations |
| `/api/match_citations` | POST | `{ "citations": [...], "reference": [...] }` | Fuzzy-match citations against a reference list |

### Worker Control

| Route | Method | Description |
|-------|--------|-------------|
| `/api/pause` | POST | Pause the worker loop |
| `/api/resume` | POST | Resume the worker loop |
| `/api/skip` | POST | Skip the currently processing citation |
| `/api/continue` | POST | Signal that the form was saved, continue to next |
| `/api/go_home` | POST | Navigate the browser to the Esploro home page |
| `/api/close` | POST | Shut down the worker and Flask app |

### Configuration

| Route | Method | Body | Description |
|-------|--------|------|-------------|
| `/api/set_researcher` | POST | `{ "name": "..." }` | Set the active researcher |
| `/api/set_asset_type` | POST | `{ "type": "..." }` | Set asset type mode (auto, journal, presentation, etc.) |
| `/api/set_restart_policy` | POST | `{ "enabled": bool, "interval": int }` | Configure auto-restart policy |
| `/api/set_author_add_delay` | POST | `{ "delay": int }` | Set delay between author additions (ms) |
| `/api/toggle_auto_fill_authors` | POST | — | Toggle automatic author field filling |

### Topics

| Route | Method | Description |
|-------|--------|-------------|
| `/api/add_topic` | POST | Add a research topic |
| `/api/remove_topic` | POST | Remove a research topic |
| `/api/clear_topics` | POST | Clear all additional topics |

---

## Supported Asset Types

| Type | Module | Description |
|------|--------|-------------|
| Journal Article | `automation/journal_impl.py` | Peer-reviewed journal publications |
| Presentation | `automation/presentations_impl.py` | Conference presentations and talks |
| Poster | `automation/poster_impl.py` | Conference posters |
| Conference Proceedings | `automation/proceedings_impl.py` | Published proceedings papers |
| Book Chapter | `automation/book_chapters_impl.py` | Chapters in edited books |
| Abstract | `automation/abstract_impl.py` | Conference abstracts |
| Technical Documentation | `automation/technical_documentation_impl.py` | Technical reports and docs |

---

## Frontend

The UI uses Tailwind CSS v3 with Material Tailwind HTML v2.

- **Color scheme**: Neutral/charcoal palette with dark mode support
- **Build CSS**: `npm run build:css`
- **Watch CSS**: `npm run watch:css` (auto-rebuild on changes)
- **Source**: `src/input.css` (Tailwind directives + custom component styles)
- **Output**: `static/css/output.css` (compiled, linked in both templates)

After modifying templates or `src/input.css`, run `npm run build:css` to rebuild.

---

## VNC Desktop

For debugging or monitoring the browser automation visually, the VNC Desktop workflow starts:
- **Xvfb** on display `:99` (virtual framebuffer)
- **x11vnc** for remote viewing

The Playwright worker runs in headed mode on this display, so you can watch it fill forms in real time.

---

## Testing

```bash
python test_citations.py              # Citation parsing tests
python test_parser_simple.py          # Simple parser tests
python test_book_chapter.py           # Book chapter automation tests
python test_proceedings.py            # Proceedings tests
python test_proceedings_automation.py  # Proceedings automation tests
python test_tech_doc_parser.py        # Technical documentation parser tests
```

---

## Configuration Files

### `bot_config.json`

Stores runtime configuration: default researcher, asset mode, pause state, auto-restart interval, stats, and additional topics. Managed by `ConfigManager` with thread-safe read/write.

### `citations_config.json`

Citation processing rules: keyword mappings, asset type detection patterns, and parsing configuration.

---

## Security

- Do not commit `.env` or any credential files
- Use environment variables or Replit secrets for all credentials
- If a secret is exposed, rotate it immediately

---

## Documentation Map

- `docs/INDEX.md` — Documentation entry point
- `docs/SMART_BATCH_GUIDE.md` — Daily operator workflow
- `docs/COMMANDS_REFERENCE.md` — Bot and UI command reference
- `docs/IPC_PROTOCOL.md` — IPC payload contracts
- `docs/DISCORD_SETUP.md` — Discord bot setup
- `docs/OPERATIONS_RUNBOOK.md` — Startup, health checks, and recovery

---

## License

For educational and research use at UMass Dartmouth.
