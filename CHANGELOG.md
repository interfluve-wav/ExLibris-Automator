# Changelog

All notable changes to **ExLibris Automator** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres loosely to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

_Nothing yet._

---

## [1.0.1] — 2026-05-11

Quickstart commands, repository audit, and dependency hygiene.

### Added
- **`docs/QUICKSTART.md`** — copy-paste command reference: first-time setup,
  standalone/full-stack launch, daily workflow, health checks, recovery,
  git workflow, smoke tests.
- **`docs/AUDIT.md`** — 2026-05-11 health audit (imports, compile, launchers,
  API health, parser chain, selector fix verification).

### Changed
- **`README.md`** — prominent quickstart command block + links to
  `QUICKSTART.md` and `AUDIT.md`.
- **`docs/GETTING_STARTED.md`**, **`docs/INDEX.md`** — cross-links to
  quickstart and audit docs.

### Fixed
- **`requirements.txt`** — removed duplicate unpinned package entries (lines
  13–26) that could cause version drift on fresh installs; removed erroneous
  `docx` alias (use `python-docx` only).

---

## [1.0.0] — 2026-05-11

First stable documentation release on the **`v7`** working branch. Consolidates
operator guides, corrects stale references (ports, branch names, removed asset
types), and documents the manual-parser production workflow.

### Added
- **`docs/GETTING_STARTED.md`** — canonical step-by-step onboarding (clone,
  bootstrap, `.env`, run modes, first citation, parser chain, verification).
- Full documentation overhaul across the `docs/` tree (see Changed below).

### Changed
- **`README.md`** — recommends `./run_standalone.command`; default port **8765**
  everywhere; links `GETTING_STARTED.md`; documents manual-parser fallback;
  notes `v7` as working branch.
- **`docs/INDEX.md`** — audience-grouped index with status labels (current /
  reference / roadmap / legacy).
- **`docs/OPERATIONS_RUNBOOK.md`** — standalone + full-stack startup, health
  checks, manual-parser expectations, worker restart recovery, port guidance.
- **`docs/COMMANDS_REFERENCE.md`** — complete Flask API, Discord commands,
  launchers, test scripts; includes `technical_documentation` asset type.
- **`docs/ALL_FEATURES_GUIDE.md`** — rewritten end-to-end feature reference.
- **`docs/FEATURES_OVERVIEW.md`** — rewritten subsystem catalog.
- **`docs/ENV_EXAMPLE.md`** — `OPENAI_API_KEY` marked optional; variable
  reference table; manual-parser note.
- **`docs/SMART_BATCH_GUIDE.md`** — removed stale local path reference.
- **`docs/ARCHITECTURE.md`** — `v7` branch and default port callout.
- **`AGENTS.md`** — `v7` working branch; manual-parser as common production path.

### Repository state at 1.0.0
- **Working branch:** `v7` (legacy `JIT` deleted; history on `jit-backup-2026-04-26`).
- **Asset types:** 7 supported (presentation, poster, proceedings, journal,
  book chapter, abstract, technical documentation). Ad Media Mention removed.
- **Parser:** OpenAI → manual asset parser → minimal fallback.
- **Selector fix:** researcher autocomplete scoped to dropdown menu item.

---

## [0.3.0] — 2026-05-11

Reverts the Ad Media Mention asset type introduced in `0.2.0`. The shared
selector fix from `0.2.0` is retained.

### Removed
- Ad Media Mention asset type end-to-end (`automation/ad_media_mention*.py`,
  `scripts/esploro_media_mentions_playwright.py`, `src/Media Mentions Data.md`,
  UI dropdown, Discord choices, worker/registry entries).

### Retained from `0.2.0`
- Researcher autocomplete strict-mode fix.
- Per-line citation splitting in `/api/add`.

---

## [0.2.0] — 2026-05-11

First documented release on the `JIT` branch (now retired).

### Added
- Ad Media Mention asset type (later removed in `0.3.0`).
- Per-line citation queueing in `/api/add`.
- `CHANGELOG.md`, expanded `README.md`, `AGENTS.md` notes.

### Changed
- Esploro researcher autocomplete selector scoped to dropdown link (all 7
  asset-type implementations).

### Fixed
- Playwright strict-mode failure on researcher names like "Calabrese, Nicholas M".

### Repository hygiene
- Stopped tracking `.cursor/` IDE state.

---

## [0.1.0] — 2026-04-11

- Initial sanitized import: Flask web UI, Discord bot, Playwright worker,
  citation parser (OpenAI + regex fallback), seven asset types.

[Unreleased]: https://github.com/interfluve-wav/ExLibris-Automator/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/interfluve-wav/ExLibris-Automator/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/interfluve-wav/ExLibris-Automator/compare/v0.3.0...v1.0.0
[0.3.0]: https://github.com/interfluve-wav/ExLibris-Automator/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/interfluve-wav/ExLibris-Automator/releases/tag/v0.2.0
[0.1.0]: https://github.com/interfluve-wav/ExLibris-Automator/releases/tag/v0.1.0
