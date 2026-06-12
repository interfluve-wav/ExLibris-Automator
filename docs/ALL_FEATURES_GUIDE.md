# All Features Guide

End-to-end reference: setup, running modes, parsing, automation, configuration,
outputs, performance, and troubleshooting.

For a shorter onboarding path see [`GETTING_STARTED.md`](GETTING_STARTED.md).

---

## 1. Installation & setup

| Step | Action |
|---|---|
| Clone | `git clone … && cd ExLibris-Automator && git checkout v7` |
| Python | 3.12 (`.python-version`); `bash scripts/ensure_python_venv.sh` |
| Frontend | `npm install && npm run build:css` |
| Browser | `.venv/bin/python -m playwright install chromium` |
| Secrets | Copy [`ENV_EXAMPLE.md`](ENV_EXAMPLE.md) → `.env` and fill in values |
| Discord (optional) | [`DISCORD_SETUP.md`](DISCORD_SETUP.md) |

---

## 2. Running modes

| Mode | Entry point | Discord | Web UI |
|---|---|---|---|
| **Standalone** | `./run_standalone.command` | No | :8765 |
| **Full stack** | `./start_all.sh` | Yes | :8765 |
| **Bot only** | `./start_smart_batch.sh` | Yes | No |
| **macOS shortcut** | `run_esp_app.command` | Yes (via `start_all.sh`) | :8765 |

---

## 3. Web UI features

- Paste single or bulk citations (blank-line or per-line splitting)
- Queue management: add, view, clear, fill, skip, continue
- Live status polling (`/api/status`): queue size, researcher, asset mode, errors
- Asset type selector and researcher picker
- Research topic management (up to 6 per channel)
- Auto-restart policy configuration
- Author auto-fill toggle and delay control
- Citation matcher (`/matcher`) with rapidfuzz dedup
- Document upload parsing (PDF, DOCX, XLSX via PyPDF2 / python-docx / pandas)
- Dark mode UI (Tailwind `class` strategy)

---

## 4. Discord bot features

- Slash commands (`/fill`, `/queue`, `/set_type`, …) and legacy text commands
- Per-channel citation queues with pause/resume
- Auto-detect poster vs presentation from citation keywords
- Configurable asset type override (`/set_type`)
- Researcher dropdown with add-new flow
- Field-fill summary messages after each deposit
- Stats counters (enqueued / processed / errors)
- Integration with Mac launcher signal files (`fill_next_signal`, `shutdown_signal`)

---

## 5. Supported asset types

| Config mode | Module | Esploro form |
|---|---|---|
| `presentation` | `presentations_impl.py` | Conference presentation |
| `poster` | `poster_impl.py` | Conference poster |
| `proceedings` | `proceedings_impl.py` | Conference proceedings |
| `journal_article` | `journal_impl.py` | Journal article |
| `book_chapter` | `book_chapters_impl.py` | Book chapter |
| `abstract` | `abstract_impl.py` | Conference abstract |
| `technical_documentation` | `technical_documentation_impl.py` | Technical documentation |
| `auto` | keyword/heuristic detection | varies |

Each `_impl.py` exports `parse_any_citation()` and `process_citation(page, data)`.

---

## 6. Parsing pipeline

```
OpenAI (gpt-4o-mini, optional)
    ↓ on failure / no key / quota exhausted
Asset-specific manual parser (automation/*_impl.py)
    ↓ on failure
Minimal generic parser (title + year extraction)
```

- OpenAI path: `openai_parser.py` with LRU cache (100 items)
- Title correction heuristics prevent author names becoming titles
- **Manual parser is the effective primary** for many production runs
- Normalized schema: authors, titles, dates, venue, DOI, conference metadata, etc.

---

## 7. Worker & browser automation

- Separate `python -m automation.worker <channel>` process per session
- Persistent Chromium context — login once, fill many citations
- O(1) asset dispatch via `ASSET_TYPE_HANDLERS` in `worker.py`
- Researcher autocomplete: scoped to `a.dropdown-item.ui-menu-item-wrapper`
- File-based IPC for control and status (see [`IPC_PROTOCOL.md`](IPC_PROTOCOL.md))
- Auto-restart every N citations (`auto_restart_interval`, default 7)
- Operator-supervised submit: worker fills form; human clicks Save in Esploro

---

## 8. Configuration

| File / source | Contents |
|---|---|
| `.env` | Secrets and runtime flags (see [`ENV_EXAMPLE.md`](ENV_EXAMPLE.md)) |
| `bot_config.json` | Researcher, asset mode, pause, stats, topics, restart policy |
| `citations_config.json` | Parser rules, keyword mappings, conference strip patterns |

`ConfigManager` (`utils/config_manager.py`) provides thread-safe debounced writes.

---

## 9. Outputs & artifacts

| Artifact | Purpose |
|---|---|
| `citationsPresentations.csv` | Full parsed field audit trail |
| `filled_fields_summary.txt` | Concise fill metrics per run |
| `citation_control_*.json` | Worker input (gitignored at runtime) |
| `citation_status_*.json` | Worker output state |
| `logs/` | Bot and Flask logs (gitignored) |

---

## 10. Performance

- Parser LRU cache: near-instant repeat parses
- ConfigManager: reduced disk I/O via caching + debounced writes
- Persistent browser session: faster subsequent fills
- `goto_with_retries`: resilient Esploro navigation
- Benchmarks: `tests/performance_tests.py`

---

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| No slash commands | Set `DISCORD_GUILD_ID`, run `/resync` |
| Port in use | Default is 8765; avoid 5000 on macOS (AirTunes) |
| Strict-mode locator error | Restart worker: `pkill -f automation.worker` |
| Parser returns bad titles | Check manual fallback logs; verify asset type |
| OpenAI 429 errors | Expected if quota exhausted; manual parser takes over |
| Stale worker code after pull | `pkill -f automation.worker`, re-fill |
| UI unstyled | `npm run build:css` |

Full recovery procedures: [`OPERATIONS_RUNBOOK.md`](OPERATIONS_RUNBOOK.md).

---

## 12. Developer notes

- Working branch: **`v7`**
- Add asset types: five registration points in [`ARCHITECTURE.md` §3](ARCHITECTURE.md#3-module-map)
- Playwright: prefer role-based locators; scope text matches
- Logging: `LOG.info/warn/error` via `utils/logging_utils.py`
- Contributing: [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
