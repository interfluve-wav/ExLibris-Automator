# Esploro Citation Automation – Feature Catalog

Comprehensive reference for every feature the system provides across Discord bot orchestration, citation parsing, Playwright automation, and auxiliary tooling.

## Core Workflow
- Discord bot receives citations (pasted text, `/add`, or `!add`) and queues them per channel.
- Worker process watches control files (e.g., `citation_control_{channel_id}.json`) and keeps a persistent Chromium session alive.
- Asset-type implementations parse and fill Esploro forms, writing status back to `citation_status_{channel_id}.json`.
- Users trigger fills via Discord commands or the Mac launcher’s “Fill Next” button; the browser stays open between fills for speed.

## Discord Bot Layer
- Supports both legacy text commands (`!f`, `!queue`, `!skip`, `!close`, etc.) and slash commands (`/fill`, `/set_type`, `/set_researcher`, `/stats`, `/pause`, `/resume`, `/resync`).
- Command handlers are modularized via `_cmd_*` functions and a dispatch table for maintainability.
- Queue management per channel using deques allows pausing/resuming and displaying queues.
- Writes concise “Field Fill Summary” messages back to Discord after each fill.
- Watches `fill_next_signal` and `shutdown_signal` control files to integrate with GUI launcher triggers.
- Bot configuration (`bot_config.json`) persists researcher, asset mode, stats counters, and up to six “Description and Research” topics per channel.

## Citation Parsing
- Primary parser powered by OpenAI (`openai_parser.py`) with configurable `OPENAI_MODEL`.
- 100-item MD5-hash keyed LRU cache avoids duplicate API calls and accelerates repeated citations.
- Title correction pipeline with `_correct_title_if_needed()`, `_title_looks_like_authors()`, and `_extract_title_heuristically()` to prevent author names or conference titles being misidentified as citation titles.
- Fallback manual parser engages automatically on suspicious OpenAI outputs, ensuring robust extraction.
- Unified JSON schema covers conference presentations, posters, proceedings, journal articles, book chapters, and abstracts.

## Automation Layer (Asset Types)
- Dedicated implementations for `presentations`, `poster`, `proceedings`, `journal`, `book_chapters`, and `abstract` assets, each exporting `parse_any_citation()` and `process_citation()`.
- Modules share utilities from `utils/citation_parser_utils.py` (e.g., `extract_year`, `extract_date_range`, `is_author_like`).
- Playwright-based form filling leverages resilient selectors (`page.get_by_role`, `page.locator`) with retry helpers.
- Wrapper modules (e.g., `automation/presentations.py`) maintain backward compatibility with legacy imports.

## Worker Layer
- `automation/worker.py` keeps a single Chromium context open, reducing login overhead.
- Asset routing uses an O(1) dispatch table keyed by asset type.
- Structured logging via `utils/logging_utils.py` with `[YYYY-MM-DD HH:MM:SS] [SECTION] [LEVEL] message`.
- Error handling ensures failed citations still advance the queue by writing status artifacts and preventing infinite retries.

## Configuration & State Management
- `ConfigManager` caches reads from `bot_config.json` / `citations_config.json` and batches writes with a debounce (0.5 s) for durability.
- Environment configuration lives in `.env` (template `docs/ENV_EXAMPLE.md`) with required keys: `OPENAI_API_KEY`, `ESPLORO_USERNAME`, `ESPLORO_PASSWORD`, `DISCORD_BOT_TOKEN`, `CITATION_PARSER=openai`.
- Optional envs: `CITATION_CHANNEL_ID`, `DISCORD_GUILD_ID`, `OPENAI_MODEL`, `DEFAULT_RESEARCHER`, `HEADLESS`, `LOG_LEVEL`.

## GUI & Control Utilities
- `run_esp_app.command` launches a Mac dialog offering “Fill Next” and “Close” buttons that write control files for the bot to consume.
- `scripts/cleanup_project.sh` tidies generated artifacts and reorganizes directories.
- `scripts/logs_viewer.py` presents CSV submission logs in a compact CLI table.

## Output & Reporting
- `citationsPresentations.csv` captures all parsed citation fields for audit trails.
- `filled_fields_summary.txt` enumerates filled vs. empty Esploro fields across runs.
- `logs/` directory stores Playwright screenshots and detailed automation traces.
- Discord summaries highlight each fill’s key metadata without flooding channels.

## Performance & Reliability
- OpenAI response caching plus parser refactors delivered ~40% code reduction and 30–50% faster processing.
- ConfigManager cuts disk I/O by >10× through aggressive caching and atomic writes.
- Worker keeps browser sessions alive, yielding faster subsequent fills.
- Robust retry helpers (`goto_with_retries`) mitigate transient network issues.

## Testing & Benchmarks
- `python3 test_citations.py` validates parser accuracy across curated citation samples.
- `tests/performance_tests.py` measures parser latency, cache effectiveness, and config I/O improvements.
- Asset-specific tests (e.g., `test_proceedings.py`, `test_book_chapter.py`) ensure Playwright logic and parser heuristics stay reliable.

