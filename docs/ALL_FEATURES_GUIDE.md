# All Features Guide

An end-to-end guide aggregating setup, configuration, commands, parsing/automation behavior, performance tools, and troubleshooting.

## 1) Installation & Setup
- Python 3.10+
- Create venv, install deps, install Playwright Chromium.
- Copy `.env` from `docs/ENV_EXAMPLE.md` and set required secrets.
- First-time Discord setup: see `docs/DISCORD_SETUP.md`.

## 2) Running
- Preferred: `./start_smart_batch.sh` to launch bot + worker.
- Alternative (GUI): `run_esp_app.command` with “Fill Next” / “Close”.
- Advanced: `python3 -m automation.worker <channel_id>` to run worker by hand.

## 3) Using the Bot
- Queue citations by pasting or via `/add` / `!add`.
- Trigger fill: `/fill` or `!f`.
- Manage queue: `/queue`, `/clear`, `/skip`.
- Control flow: `/pause`, `/resume`, `/close`.
- Configure mode and defaults: `/set_type`, `/set_researcher`.
- Topics: `/set_additional_topic`, `/clear_additional_topics`.
- Health & admin: `/stats`, `/resync`.

## 4) Supported Asset Types
- Conference Presentation
- Poster Presentation
- Conference Proceedings
- Journal Article
- Book Chapter
- Abstract

Each asset has:
- `parse_any_citation(citation_text)` – normalize fields
- `process_citation(page, data)` – fill Esploro form via Playwright

## 5) Parsing Pipeline
- OpenAI-based structured extraction with configurable model and 100-item LRU cache.
- Title correction heuristics ensure human-like titles; falls back to manual parser when needed.
- Normalized schema includes authors, titles, dates, venue, location, journal/book metadata, pages, editors, and identifiers.

## 6) Worker & Browser
- Persistent Chromium context with login on startup.
- Robust navigation via `goto_with_retries` and sensible timeouts.
- O(1) asset dispatch by type and file-based IPC with control/status JSON files.

## 7) Configuration
- `.env` for secrets and runtime flags.
- `bot_config.json` persisted via ConfigManager with debounced writes.
- `citations_config.json` for ordinal words, conference strip patterns, and overrides.

## 8) Outputs
- `citationsPresentations.csv` – full field set across runs.
- `filled_fields_summary.txt` – concise fill metrics.
- `logs/` – screenshots and traces for audit/debug.

## 9) Performance
- Benchmarks in `tests/performance_tests.py`.
- Parser cache provides near-instant repeat parses.
- ConfigManager drastically lowers disk churn and speeds reads.

## 10) Troubleshooting
- No slash commands? Ensure `DISCORD_GUILD_ID`, then `/resync`.
- Mac launcher inert? Ensure `CITATION_CHANNEL_ID` and non-empty queue, be on form page.
- Parser bad titles? Check heuristics; manual fallback will attempt correction.
- Browser stuck? Try `/close` then `/fill` to cycle the worker.

## 11) Developer Notes
- Add new asset types under `automation/*_impl.py` and a thin wrapper.
- Update worker routing and parser prompt accordingly.
- Prefer compiled regex in `utils/citation_parser_utils.py` for common patterns.
- Keep logging consistent with `[YYYY-MM-DD HH:MM:SS] [SECTION] [LEVEL]`.
