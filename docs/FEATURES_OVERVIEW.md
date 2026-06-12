# Features Overview

Feature catalog across Discord bot, Flask UI, citation parsing, Playwright
automation, and supporting utilities.

---

## Core workflow

1. Operator adds citations (web UI paste, Discord `/add`, or channel paste).
2. Citations queue per channel (in-memory in standalone; persisted via bot in
   Discord mode).
3. Operator triggers fill — worker subprocess starts (or reuses) a Chromium
   session logged into Esploro.
4. Parser extracts metadata → asset-type module fills the form.
5. Operator reviews and saves in the browser, then signals continue.
6. Worker advances to the next citation.

---

## Flask web UI

- Control panel at `templates/index.html` with Tailwind CSS dark mode
- REST API for queue, fill, skip, continue, configuration, and status
- `StandaloneManager` for GUI-only operation (no Discord dependency)
- Bulk citation splitting: blank lines or substantial per-line pastes
- File upload intake: PDF, DOCX, XLSX
- Citation matcher UI with rapidfuzz scoring
- Keyboard-triggered fill actions

---

## Discord bot

- `discord_bot_batch_smart.py` — slash + text command interface
- Modular `_cmd_*` handlers with dispatch table
- Per-channel deques with pause/resume
- Post-fill summary messages to the channel
- Watches `fill_next_signal` / `shutdown_signal` for Mac launcher integration
- Persists config via `bot_config.json` (researcher, asset mode, stats, topics)

---

## Citation parsing

| Layer | Module | When used |
|---|---|---|
| OpenAI | `openai_parser.py` | `OPENAI_API_KEY` set and quota available |
| Manual | `automation/*_impl.py` | Primary in many production runs |
| Minimal | `worker.py` `_minimal_parse_fallback` | Last resort |

- Configurable model (`OPENAI_MODEL`, default `gpt-4o-mini`)
- 100-item MD5 LRU cache for OpenAI responses
- Title correction heuristics (`_correct_title_if_needed`, etc.)
- Unified schema across all seven asset types

---

## Automation (asset types)

| Type | Implementation |
|---|---|
| Conference presentation | `presentations_impl.py` |
| Conference poster | `poster_impl.py` |
| Conference proceedings | `proceedings_impl.py` |
| Journal article | `journal_impl.py` |
| Book chapter | `book_chapters_impl.py` |
| Abstract | `abstract_impl.py` |
| Technical documentation | `technical_documentation_impl.py` |

Shared utilities: `utils/citation_parser_utils.py`, `utils/author_automation.py`.

Playwright patterns: `get_by_role`, scoped `locator().filter()`, retry helpers.

---

## Worker

- `automation/worker.py` — subprocess, not a thread
- `ASSET_TYPE_HANDLERS` dispatch table
- `_try_parse_with_fallback` chain
- Structured logging via `utils/logging_utils.py`
- Status files: `citation_status_<channel>.json`
- Auto-restart policy for long sessions

---

## Configuration & state

- `.env` — secrets (gitignored); template: [`ENV_EXAMPLE.md`](ENV_EXAMPLE.md)
- `bot_config.json` — runtime config + cumulative stats
- `citations_config.json` — parser/detection rules
- `ConfigManager` — cached reads, debounced atomic writes
- File-based IPC — see [`IPC_PROTOCOL.md`](IPC_PROTOCOL.md)

---

## Launchers & scripts

| Script | Purpose |
|---|---|
| `run_standalone.command` | macOS GUI-only entry |
| `start_all.sh` | Full local stack |
| `start_smart_batch.sh` | Discord bot only |
| `start_desktop.sh` | Xvfb + VNC for headed debugging |
| `scripts/ensure_python_venv.sh` | `.venv` bootstrap |
| `scripts/cleanup_project.sh` | Remove generated artifacts |

---

## Output & reporting

- `citationsPresentations.csv` — audit trail
- `filled_fields_summary.txt` — per-run fill summary
- Discord channel summaries after each fill
- `logs/` — bot and Flask process logs

---

## Testing & benchmarks

```bash
.venv/bin/python test_citations.py
.venv/bin/python tests/performance_tests.py
.venv/bin/python test_proceedings.py
.venv/bin/python test_book_chapter.py
.venv/bin/python test_tech_doc_parser.py
```

---

## Reliability features

- Persistent Chromium session (login once per worker lifecycle)
- Auto-restart interval (configurable, default every 7 citations)
- Single-instance guard in `start_all.sh` (kills stale processes)
- Parser fallback chain (never blocks on OpenAI alone)
- Scoped Playwright selectors (strict-mode safe)
