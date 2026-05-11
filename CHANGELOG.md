# Changelog

All notable changes to **ExLibris Automator** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres loosely to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Until the project reaches a stable `1.0.0`, breaking changes may land in any
minor release.

---

## [Unreleased]

_Nothing yet — add new entries here as work lands._

---

## [0.3.0] — 2026-05-11

Reverts the Ad Media Mention asset type introduced in `0.2.0`. The flow caused
regressions across the rest of the deposit pipeline and was rolled back end-to-
end. The shared selector fix from `0.2.0` is **retained**, since it addresses a
real Playwright strict-mode bug that affects every asset type, not just Media
Mentions.

### Removed
- **Ad Media Mention asset type, end-to-end.**
  - Deleted modules: `automation/ad_media_mention.py`,
    `automation/ad_media_mention_impl.py`.
  - Deleted standalone capture script:
    `scripts/esploro_media_mentions_playwright.py`.
  - Deleted source data file: `src/Media Mentions Data.md`.
  - Worker (`automation/worker.py`): removed the `ad_media_mention` entry from
    `ASSET_TYPE_HANDLERS`, the `manual_parse_modules` fallback map, and the
    module import.
  - Asset-type registry (`utils/asset_type_utils.py`): removed
    `ad_media_mention` from `VALID_CONFIG_MODES`, `ASSET_TYPE_TO_CONFIG_MODE`,
    `CONFIG_MODE_TO_ASSET_TYPE`, and the `normalize_config_mode` alias map.
  - UI (`templates/index.html`): removed the `Ad Media Mention` option from the
    asset-type dropdown.
  - Discord bot (`discord_bot_batch_smart.py`): removed `ad_media_mention` from
    all asset-type tuples and validation strings, the `!set type` help text,
    the `elif asset_type == "ad_media_mention":` display branch, and both
    `app_commands.Choice(...)` entries on the `/set_type` and `/add` slash
    commands.
- AGENTS notes: removed the "classify coverage as Media Mention (not Book)"
  taxonomy preference, since the implementation it informed is gone.

### Retained from `0.2.0`
- The researcher autocomplete strict-mode fix
  (`a.dropdown-item.ui-menu-item-wrapper` scoping) stays — it fixes a real bug
  in every asset-type flow and is not tied to Media Mentions.
- The per-line citation splitting in `/api/add` stays — it is an independent
  operator-paste UX improvement.

### Operator note
Anyone whose `bot_config.json` still has `"asset_mode": "ad_media_mention"`
should change it (the UI dropdown defaults to `auto`); otherwise the worker
will reject the mode at validation time and fall back to `auto`.

---

## [0.2.0] — 2026-05-11

First documented release on the `JIT` branch. Establishes the Ad Media Mention
flow, hardens shared selectors, and introduces formal documentation hygiene
(`CHANGELOG.md`, expanded `README.md`).

### Added
- **Ad Media Mention asset type** (`automation/ad_media_mention.py`,
  `automation/ad_media_mention_impl.py`)
  - Deterministic parser for media coverage citations (title, year, URL).
  - Source classifier distinguishes `news_article` vs `articles_export_code`
    inputs.
  - Reuses the existing Presentation Playwright flow to fill the Esploro form
    without introducing parallel form-fill code.
  - Selectable from the UI / API via `asset_mode = "ad_media_mention"`.
- **Per-line citation queueing in `/api/add`**
  - When the pasted blob contains multiple non-empty lines and every line looks
    like a substantial citation (>30 chars), each line is enqueued as its own
    citation. Wrapped paragraphs continue to be coalesced as before.
- **`CHANGELOG.md`** (this file).
- **README**: new "Ad Media Mention" row in _Supported Asset Types_ and a link
  to the changelog from the Documentation Map.
- **AGENTS.md**: recorded preferences for persistent end-to-end execution and
  documented the `run_standalone.command` Tailwind bootstrap.

### Changed
- **Esploro researcher autocomplete selector** is now scoped to the dropdown
  link element. Previously the click used a page-wide
  `page.get_by_text(researcher)`, which collided in Playwright strict mode with
  the autocomplete's "All contains …" hint span. Applied across all 7 asset-type
  implementations:
  - `automation/journal_impl.py`
  - `automation/presentations_impl.py` (used by Ad Media Mention)
  - `automation/poster_impl.py`
  - `automation/book_chapters_impl.py`
  - `automation/abstract_impl.py`
  - `automation/technical_documentation_impl.py`
  - `automation/proceedings_impl.py` (two call sites)

### Fixed
- **Playwright strict-mode failure when selecting a researcher** such as
  _"Calabrese, Nicholas M"_. The original locator matched both the hint span
  (`All contains <name>`) and the actual `<a class="dropdown-item …">` menu
  item; now we scope to `a.dropdown-item.ui-menu-item-wrapper` and use `.first`.
- Researcher autocomplete clicks are no longer flaky on names that produce the
  Esploro "All contains" suggestion row.

### Repository hygiene
- **Stopped tracking local Cursor IDE state.** `.cursor/` (debug logs, hook
  state) is now in `.gitignore`; previously-tracked files were removed from the
  index. Local working copies are untouched.
- Documentation scan confirms no real secrets are committed; only placeholder
  values like `OPENAI_API_KEY=sk-prod-...` and `your_password` remain in
  `docs/ENV_EXAMPLE.md`, `docs/DISCORD_SETUP.md`,
  `docs/Web App & Discord Bot Integration Steps.md`, and
  `deployment/DEPLOYMENT.md`.

### Operator note
After pulling this change, the long-running Playwright worker
(`python -m automation.worker …`) must be restarted to reload the patched
modules. Either:

- let the configured `auto_restart_interval` rotate it, or
- run `pkill -f "automation.worker"` and let Flask spawn a fresh worker on the
  next fill.

---

## [0.1.0] — Initial import

- Initial sanitized import of the ExLibris Automator stack: Flask web UI,
  Discord bot, Playwright worker, citation parser (OpenAI + regex fallback),
  and supported asset types (journal, presentation, poster, proceedings, book
  chapter, abstract, technical documentation).

[Unreleased]: https://github.com/interfluve-wav/ExLibris-Automator/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/interfluve-wav/ExLibris-Automator/releases/tag/v0.2.0
[0.1.0]: https://github.com/interfluve-wav/ExLibris-Automator/releases/tag/v0.1.0
