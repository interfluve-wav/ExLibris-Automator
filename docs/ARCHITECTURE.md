# Architecture & Tech Stack

This is the authoritative reference for what runs where, which library does
what, and how the pieces talk to each other.

**Working branch:** `v7` · **Default web UI port:** `8765`

If a fact in here disagrees with the README quick-start, this document is
correct — the README is a summary.

---

## 1. Stack at a glance

### Runtime

| Concern | Choice | Version | Source |
|---|---|---|---|
| Language | CPython | `3.12.13` | [`.python-version`](../.python-version) |
| Frontend toolchain | Node.js / npm | 18+ recommended | [`package.json`](../package.json) |
| Virtual env | `.venv` (PEP 405) | bootstrapped by [`scripts/ensure_python_venv.sh`](../scripts/ensure_python_venv.sh) | — |

### Backend

| Library | Version | Role |
|---|---|---|
| `flask` | 3.0.3 | Web server, HTML templates, JSON API |
| `werkzeug` | (bundled with Flask) | WSGI primitives, request parsing |
| `gunicorn` | latest | Optional production WSGI server (see [DEPLOYMENT.md](../deployment/DEPLOYMENT.md)) |
| `python-dotenv` | 1.0.1 | `.env` loading |
| `requests` | 2.32.3 | Light HTTP utility usage |

### Browser automation

| Library | Version | Role |
|---|---|---|
| `playwright` | 1.54.0 | Drives a Chromium instance against Esploro |

The worker is a **separate process** (`python -m automation.worker <channel>`)
so a crash in the Playwright session never takes down the Flask UI.

### LLM / parsing

| Library | Version | Role |
|---|---|---|
| `openai` | 1.58.1 | GPT-4o-mini (default) citation parser |
| `rapidfuzz` | 3.6.1 | Fuzzy citation matching / dedup (Matcher UI) |
| `PyPDF2` | 3.0.1 | PDF text extraction |
| `python-docx` | 1.1.0 | DOCX text extraction |
| `pandas` | 2.2.0 | Tabular intake (XLSX, CSV) |
| `openpyxl` | 3.1.2 | XLSX backend for pandas |
| `xlrd` | 2.0.1 | Legacy XLS backend |

The OpenAI parser falls back to a regex parser
([`openai_parser.py`](../openai_parser.py)) if `OPENAI_API_KEY` is unset.

### Discord (optional)

| Library | Version | Role |
|---|---|---|
| `discord.py` | 2.6.3 | Slash + text command interface |

Discord is **optional**. The standalone Flask UI is the supported alternative.

### Frontend

| Library | Version | Role |
|---|---|---|
| `tailwindcss` | ^3.4.19 | Utility CSS, compiled to `static/css/output.css` |
| `@material-tailwind/html` | ^2.3.2 | Tailwind preset used in `tailwind.config.js` |

There is **no SPA framework** (no React, Vue, Svelte). The UI is plain HTML
templates rendered by Flask + Jinja2, with Tailwind-compiled CSS and a small
amount of inline / templated JavaScript in `templates/index.html`.

---

## 2. Process model

At runtime, three independent processes coordinate via files on disk:

```
┌──────────────────────┐      ┌──────────────────────┐      ┌──────────────────────┐
│  discord_bot_batch_  │      │  esp_gui_web.py      │      │  python -m           │
│  smart.py            │      │  (Flask + Jinja2)    │      │  automation.worker   │
│  (optional)          │◀────▶│  http://…:8765       │◀────▶│  (Playwright +       │
│                      │      │                      │      │   Chromium)          │
└──────────────────────┘      └──────────────────────┘      └──────────────────────┘
            │                            │                              │
            ▼                            ▼                              ▼
   citation_control_*.json       gui_*.json (signals)         Esploro web forms
   citation_status_*.json        bot_config.json (state)
```

| Process | Started by | Purpose |
|---|---|---|
| Flask UI (`esp_gui_web.py`) | [`run_standalone.command`](../run_standalone.command), [`start_all.sh`](../start_all.sh) | Operator UI, REST endpoints, file-watch signals to worker |
| Worker (`automation.worker`) | Forked by Flask / bot manager when first fill is requested | One Chromium session per channel, owns the Esploro form fills |
| Discord bot (`discord_bot_batch_smart.py`) | [`start_smart_batch.sh`](../start_smart_batch.sh) (via [`start_all.sh`](../start_all.sh)) | Slash & text commands, queues citations from a Discord channel |

The Flask UI and the worker do **not** share memory. All cross-process state
flows through:

- **JSON IPC files** documented in [`IPC_PROTOCOL.md`](IPC_PROTOCOL.md)
  (`citation_control_<channel>.json`, `citation_status_<channel>.json`,
  `gui_skip.json`, `gui_continue.json`, `gui_pause.json`,
  `gui_set_restart_policy.json`, etc).
- **Persistent config** in `bot_config.json` (managed with file locking by
  [`utils/config_manager.py`](../utils/config_manager.py)).
- **CSV output** for filled citations (`citationsPresentations.csv`, etc.).

---

## 3. Module map

### Top-level entry points

| File | What it is |
|---|---|
| [`esp_gui_web.py`](../esp_gui_web.py) | Flask app: HTML pages, JSON API, `StandaloneManager` queue/worker controller |
| [`discord_bot_batch_smart.py`](../discord_bot_batch_smart.py) | discord.py bot with `!set type`, `!fill`, `/set_type`, `/add`, etc. |
| [`openai_parser.py`](../openai_parser.py) | GPT-4o-mini parser with regex fallback |

### `automation/` — Playwright worker and per-asset-type modules

| File | Role |
|---|---|
| `worker.py` | Long-running Playwright process per channel; owns the `ASSET_TYPE_HANDLERS` dispatch table and the manual-parse fallback registry |
| `journal_impl.py` | Journal article fill |
| `presentations_impl.py` | Conference presentation fill |
| `poster_impl.py` | Conference poster fill |
| `proceedings_impl.py` | Conference proceedings fill |
| `book_chapters_impl.py` | Book chapter fill |
| `abstract_impl.py` | Conference abstract fill |
| `technical_documentation_impl.py` | Technical report / documentation fill |
| `journal.py`, `presentations.py`, `poster.py`, `proceedings.py`, `book_chapters.py`, `abstract.py`, `technical_documentation.py` | Thin router/re-export modules used by `worker.py` |

Each `_impl.py` exposes the same contract:

```python
parse_any_citation(citation_text: str) -> dict
process_citation(page, parsed: dict, pause_after: bool = False, start_from_home: bool = True)
```

Adding a new asset type means: add an `automation/<type>_impl.py`, add a
router `automation/<type>.py`, and register it in:

1. `automation/worker.py` → `ASSET_TYPE_HANDLERS`
2. `automation/worker.py` → `manual_parse_modules` (fallback map)
3. `utils/asset_type_utils.py` → `VALID_CONFIG_MODES`,
   `ASSET_TYPE_TO_CONFIG_MODE`, `CONFIG_MODE_TO_ASSET_TYPE`,
   `normalize_config_mode` alias map
4. `templates/index.html` → asset-type `<select>` option
5. `discord_bot_batch_smart.py` → asset-type tuples, display branch, slash
   command `Choice(...)` entries

See the `Ad Media Mention` removal in
[CHANGELOG `[0.3.0]`](../CHANGELOG.md) for the inverse of this checklist —
that release is a complete worked example of where every reference lives.

### `utils/` — shared helpers

| File | Role |
|---|---|
| `asset_type_utils.py` | Single source of truth for asset-type sets, normalization, and parser↔config mode mapping |
| `author_automation.py` | Author field automation (auto-add researchers/co-authors) |
| `citation_parser_utils.py` | Regex extraction, citation normalization |
| `config_manager.py` | Thread-safe JSON config manager |
| `config_utils.py` | Config helper functions |
| `input_validation.py` | Citation/researcher name validation, sanitization |
| `ipc_protocol.py` | Constants and helpers for the file-based IPC |
| `logging_utils.py` | Structured logging setup (`LOG.info/warn/error`) |

### Frontend

| Path | Role |
|---|---|
| [`templates/index.html`](../templates/index.html) | Main control panel (queue, status, controls, asset-type selector) |
| `templates/matcher.html` | Citation matcher / dedup UI |
| [`src/input.css`](../src/input.css) | Tailwind source + custom component utilities |
| [`tailwind.config.js`](../tailwind.config.js) | Theme, dark mode (`class`), keyframes, Material Tailwind preset via `withMT(...)` |
| `static/css/output.css` | Compiled, gitignored-ish — rebuilt by `npm run build:css` |

### Launchers / orchestration

| Script | Use |
|---|---|
| [`run_standalone.command`](../run_standalone.command) | macOS double-click entrypoint, GUI-only (no Discord) |
| [`run_esp_app.command`](../run_esp_app.command) | macOS double-click, delegates to `start_all.sh` |
| [`start_all.sh`](../start_all.sh) | Bot + worker + Flask, full local stack |
| [`start_smart_batch.sh`](../start_smart_batch.sh) | Smart-batch Discord bot only |
| [`start_desktop.sh`](../start_desktop.sh) | Xvfb + x11vnc for headed browser viewing (Linux) |
| [`scripts/ensure_python_venv.sh`](../scripts/ensure_python_venv.sh) | Idempotent `.venv` bootstrap used by every launcher |
| [`scripts/cleanup_project.sh`](../scripts/cleanup_project.sh) | Remove generated artifacts |
| [`scripts/update_dependencies.sh`](../scripts/update_dependencies.sh) | Refresh pinned versions |
| [`quick_deploy.sh`](../quick_deploy.sh) | Deployment helper |

---

## 4. Data flow: one citation, end-to-end

```
User                  Flask UI            StandaloneManager      Worker (subprocess)        Esploro
 │                      │                       │                       │                      │
 │  POST /api/add       │                       │                       │                      │
 ├─────────────────────▶│  split_citation_blocks│                       │                      │
 │                      │  validate + sanitize  │                       │                      │
 │                      │  add_citation(text)  ─┼──▶ enqueue            │                      │
 │  POST /api/fill      │                       │                       │                      │
 ├─────────────────────▶│  trigger_fill()       │                       │                      │
 │                      │                       │  write citation_      │                      │
 │                      │                       │  control_<ch>.json    │                      │
 │                      │                       │ ─────────────────────▶│  detect file change  │
 │                      │                       │                       │  parse_any_citation()│
 │                      │                       │                       │   (GPT-4o-mini or    │
 │                      │                       │                       │    regex fallback)   │
 │                      │                       │                       │  process_citation()  │
 │                      │                       │                       │ ────────────────────▶│
 │                      │                       │                       │  Playwright fills    │
 │                      │                       │                       │  form, waits for     │
 │                      │                       │                       │  human "save"        │
 │  click "Saved"       │                       │                       │                      │
 ├─────────────────────▶│  /api/continue        │                       │                      │
 │                      │                       │  write gui_continue   │                      │
 │                      │                       │ ─────────────────────▶│  next citation       │
 │                      │                       │                       │  navigate home,      │
 │                      │                       │                       │  pull next from      │
 │                      │                       │                       │  control file        │
```

The worker writes back to `citation_status_<ch>.json` after each
`processing` / `completed` / `failed` transition. The Flask UI polls
`/api/status` and reads that file for live state.

---

## 5. Configuration & state

### Environment variables

See [`docs/ENV_EXAMPLE.md`](ENV_EXAMPLE.md) for the full list. The README has
the quick-reference table. Key ones:

| Variable | Required | Notes |
|---|---|---|
| `ESPLORO_USERNAME`, `ESPLORO_PASSWORD` | yes | Used by the worker to log into Esploro |
| `OPENAI_API_KEY` | no | Without it, the parser silently falls back to regex |
| `OPENAI_MODEL` | no | Defaults to `gpt-4o-mini` |
| `DISCORD_BOT_TOKEN`, `CITATION_CHANNEL_ID`, `DISCORD_GUILD_ID` | only for bot mode | — |
| `DEFAULT_RESEARCHER` | no | UI/bot default; overridable per request |
| `BOT_CONFIG_PATH` | no | Override path to `bot_config.json` |
| `LOG_LEVEL` | no | `DEBUG` / `INFO` / `WARN` |
| `HEADLESS` | no | `1` / `true` to run Chromium headless |
| `ESP_STANDALONE` | no | Set to `1` by `run_standalone.command` to bypass the Discord requirement |

### JSON state files

| File | Owner | Purpose |
|---|---|---|
| `bot_config.json` | Flask + bot | Default researcher, asset mode, paused flag, stats, restart interval, known researchers, additional topics |
| `citations_config.json` | parser / worker | Citation processing rules, keyword mappings, type detection patterns |
| `citation_control_<channel>.json` | Flask / bot → worker | Next citation payload + control flags |
| `citation_status_<channel>.json` | worker → Flask / bot | Last processed id, state, csv path, summary path |
| `gui_skip.json`, `gui_continue.json`, `gui_pause.json`, `gui_go_home.json`, `gui_set_restart_policy.json` | Flask → worker | One-shot signal files (worker deletes on consume) |

`utils/config_manager.py` does the locking for `bot_config.json`.

---

## 6. Reliability & operator model

The system is designed around the **operator-in-the-loop** pattern: the
worker fills the form, the human reviews & saves, then clicks
"Saved — Continue" to advance the queue. This intentionally avoids
fully-automated submits against a live research repository.

Reliability mechanisms:

- **Auto-restart policy** — every N citations the worker process is restarted
  to recycle memory and recover from latent Playwright session issues
  (`auto_restart_interval` in `bot_config.json`, default 7).
- **Worker fallback parser chain** — OpenAI → asset-specific manual parser →
  minimal generic parser. See `_try_parse_with_fallback` in
  [`automation/worker.py`](../automation/worker.py).
- **Single-instance guard** — `start_all.sh` kills any stale
  `discord_bot_batch_smart.py`, `esp_gui_web.py`, or `automation.worker`
  processes before starting fresh ones, so duplicate Chromium sessions never
  fight over the same Esploro login.

---

## 7. Deployment options

| Target | Files | Notes |
|---|---|---|
| **Local macOS** (primary) | `run_standalone.command`, `run_esp_app.command`, `start_all.sh` | The supported daily-driver workflow per project preferences |
| **systemd (Linux)** | [`deployment/esploro-bot.service`](../deployment/esploro-bot.service), [`deployment/validate_env.py`](../deployment/validate_env.py) | See [`deployment/DEPLOYMENT.md`](../deployment/DEPLOYMENT.md) |
| **Replit** (legacy) | [`replit.nix`](../replit.nix), [`replit.md`](../replit.md) | Kept for parity; not the recommended path |

There is intentionally **no Docker image** in the repo today — the worker
needs a real Chromium and the Esploro login flow is operator-supervised, so
the containerization story is not a priority.

---

## 8. Testing

| File | Scope |
|---|---|
| `test_citations.py` | Citation parser accuracy across asset types |
| `test_parser_simple.py` | Smoke tests for the regex fallback parser |
| `test_book_chapter.py`, `test_proceedings.py`, `test_proceedings_automation.py` | Per-asset-type parser/automation sanity |
| `test_tech_doc_parser.py` | Technical documentation parser |
| `tests/performance_tests.py` | Throughput benchmarks |

There is no `pytest` config — tests are run as scripts: `python <file>.py`.
This is intentional given the heavy I/O and Playwright surface; introduce a
proper `pytest` config only if you also add Playwright fixtures.

---

## 9. Where to look next

- **Setup & ops:** [`OPERATIONS_RUNBOOK.md`](OPERATIONS_RUNBOOK.md)
- **Daily workflow:** [`SMART_BATCH_GUIDE.md`](SMART_BATCH_GUIDE.md)
- **All commands:** [`COMMANDS_REFERENCE.md`](COMMANDS_REFERENCE.md)
- **IPC contract:** [`IPC_PROTOCOL.md`](IPC_PROTOCOL.md)
- **Discord setup:** [`DISCORD_SETUP.md`](DISCORD_SETUP.md)
- **Env vars:** [`ENV_EXAMPLE.md`](ENV_EXAMPLE.md)
- **Release history:** [`../CHANGELOG.md`](../CHANGELOG.md)
- **Security:** [`../SECURITY.md`](../SECURITY.md)
- **Contributing:** [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
