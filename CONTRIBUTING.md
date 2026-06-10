# Contributing to ExLibris Automator

Thanks for working on this project. The rules below are short on purpose;
they exist to keep the local-operator workflow (the supported deployment
target) stable.

If anything here disagrees with [`AGENTS.md`](AGENTS.md), follow `AGENTS.md`.
That file captures hard preferences from the maintainer and supersedes
generic guidance.

---

## 1. Ground rules

1. **The local stack must keep working.** `./run_standalone.command` and
   `./start_all.sh` are the supported entry points. A change that breaks
   either is a regression even if everything else still passes.
2. **Never commit secrets.** Real `ESPLORO_PASSWORD`, `OPENAI_API_KEY`,
   `DISCORD_BOT_TOKEN`, browser cookies, or `auth.json` must never reach the
   repo. `.env` and `auth.json` are in `.gitignore`; keep them there. See
   [`SECURITY.md`](SECURITY.md).
3. **UI-only changes stay UI-only.** If the task is "tweak the panel", don't
   refactor `automation/worker.py` while you're there.
4. **Strict primary matching first, then fallback.** Automation logic
   (matchers, parsers) should attempt the precise rule first, then fall back
   explicitly. Avoid lossy generic catch-alls.
5. **Operator-supervised submits.** Never auto-click the final
   submit/save in Esploro. The worker fills the form; the human saves.

---

## 2. Development setup

### One-time

```bash
git clone git@github.com:interfluve-wav/ExLibris-Automator.git
cd ExLibris-Automator

# Python 3.12 (pinned in .python-version)
bash scripts/ensure_python_venv.sh

# Frontend toolchain
npm install
npm run build:css

# Playwright browsers (Chromium is the one we drive)
.venv/bin/python -m playwright install chromium

# Local secrets
cp docs/ENV_EXAMPLE.md .env   # then edit
```

### Running

| Goal | Command |
|---|---|
| GUI-only (no Discord) | `./run_standalone.command` |
| Full stack (bot + UI + worker) | `./start_all.sh` |
| Discord bot in isolation | `./start_smart_batch.sh` |
| Watch Tailwind during UI work | `npm run watch:css` |

The standalone UI binds to `http://localhost:8765` by default. If the port is
occupied (Apple AirTunes uses `:5000` on macOS), use `--port 8765` — that's
already the default in `run_standalone.command`.

---

## 3. Branching & commits

- **Branch from `v7`** for active development (this is the working branch).
  `main` is the upstream-tracking branch and only receives merged work. The
  legacy `JIT` branch has been retired; its history lives on `v7` and on the
  archived `jit-backup-2026-04-26` safety branch.
- **Branch names:** `fix/<slug>`, `feat/<slug>`, `chore/<slug>`,
  `docs/<slug>`, `revert/<slug>`.
- **Commit style:** Conventional Commits, lowercased subjects, imperative
  mood:

  ```
  <type>(<scope>): <short subject>

  <wrap body at ~72 cols.
  Explain the WHY, not the WHAT. The diff already shows what changed.>
  ```

  Allowed types: `feat`, `fix`, `revert`, `chore`, `docs`, `refactor`,
  `test`, `perf`, `build`, `ci`.

- **One logical change per commit.** Five small commits beats one giant one
  if it makes the history bisectable.
- **Never `git commit --amend` after pushing**, and never `git push --force`
  to `main` or `v7` without explicit owner approval.

Example:

```
fix(automation): scope researcher autocomplete click to dropdown item

`page.get_by_text(researcher).click()` matched both the Esploro autocomplete's
"All contains <name>" hint span and the actual `<a class="dropdown-item …">`
menu link, causing a Playwright strict-mode violation on names like
"Calabrese, Nicholas M".
```

---

## 4. Pull requests

PRs target `v7`. Before opening:

- [ ] `./run_standalone.command` boots and `GET /api/status` returns 200.
- [ ] If you touched `automation/`, smoke-test by enqueueing one citation
      end-to-end against a staging or throwaway Esploro account.
- [ ] If you added a new asset type, you updated **all five** registration
      points listed in
      [`docs/ARCHITECTURE.md` §3](docs/ARCHITECTURE.md#3-module-map).
- [ ] If you changed any user-visible behavior, you added an entry under
      `[Unreleased]` in [`CHANGELOG.md`](CHANGELOG.md).
- [ ] `rg "TODO|FIXME|XXX"` shows no new placeholders left in your diff.
- [ ] `rg -n "sk-[A-Za-z0-9]{16,}|xox[baprs]-|AIza[A-Za-z0-9_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"`
      finds nothing in your diff.

A good PR description has:

1. **What** — one short paragraph.
2. **Why** — what symptom or use-case drove the change.
3. **How** — design notes only if non-obvious.
4. **How verified** — exact commands or steps you ran, with output.
5. **Risk** — what could break, and where to look first if it does.

---

## 5. Coding standards

### Python

- Target **Python 3.12**. Use modern syntax (`list[str]`, `match`,
  `dict | None`, `pathlib.Path`).
- Prefer the standard library where possible. Add a new third-party
  dependency only when it pays for itself; pin the exact version in
  `requirements.txt`.
- **No silent excepts.** `except Exception: pass` is only acceptable when the
  code path is truly best-effort (e.g. writing a debug summary file). In
  every other case, log via `utils.logging_utils.LOG`.
- **No prints in library code.** Use `LOG.info / LOG.warn / LOG.error`. Top-
  level launcher prints in `esp_gui_web.py` and `discord_bot_batch_smart.py`
  are fine.
- **Path discipline.** Don't hard-code absolute paths. Resolve everything
  relative to `SCRIPT_DIR` / project root.
- **No new global mutable state.** If you need shared state, route it
  through `utils/config_manager.py` or an explicit IPC file.

### Playwright

- **Always prefer role-based locators** (`get_by_role`, `get_by_label`) and
  scope them. When you need text matching, scope to a parent element
  (`page.locator("a.dropdown-item.…").filter(has_text=…).first`). A bare
  `page.get_by_text(...)` is a strict-mode violation waiting to happen.
- **Don't auto-click final submits** in Esploro. Stop at the operator-review
  point and surface a status update through the IPC.
- **Respect the headless flag.** `HEADLESS=1` should always work; never
  hard-code `headless=False`.

### Frontend (Tailwind / Jinja2)

- Tailwind classes only — don't add hand-rolled CSS in `output.css`.
  Customizations live in `src/input.css` or `tailwind.config.js`.
- Re-run `npm run build:css` after editing templates or `src/input.css`
  before committing.
- Dark mode is `class`-based — preserve both color schemes when adding new UI.

### Shell scripts

- All `.sh` and `.command` files set `set -e` (or `set -euo pipefail` where
  the surrounding code supports it).
- Use `"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` to anchor scripts to
  their own directory, not the caller's.

---

## 6. Testing

This project does not (yet) have a unified `pytest` runner. Run the relevant
script(s) directly:

```bash
.venv/bin/python test_citations.py
.venv/bin/python test_parser_simple.py
.venv/bin/python test_book_chapter.py
.venv/bin/python test_proceedings.py
.venv/bin/python test_proceedings_automation.py
.venv/bin/python test_tech_doc_parser.py
.venv/bin/python tests/performance_tests.py
```

If you add a `pytest`-style test, also add `pytest` and the appropriate
plugins to `requirements.txt` and document the runner in
[`docs/ARCHITECTURE.md` §8](docs/ARCHITECTURE.md#8-testing).

End-to-end Playwright verification is manual: enqueue one representative
citation per asset type you touched and watch the worker fill it.

---

## 7. Pre-commit & secret scanning

`.pre-commit-config.yaml` ships with the repo. To enable it locally:

```bash
pip install pre-commit
pre-commit install
```

CI runs TruffleHog on every push. If it flags your diff, the right answer is
always **rotate the credential, then strip the value with `git filter-repo`
or a fresh branch** — never `git push --force` over it without first
rotating.

---

## 8. Documentation expectations

If your change is user-visible:

- Update the relevant doc under `docs/`.
- Add a `CHANGELOG.md` entry under `[Unreleased]`. Reserve numbered version
  sections for actual releases.
- If you introduce a new module, add a row in
  [`docs/ARCHITECTURE.md` §3](docs/ARCHITECTURE.md#3-module-map).
- If you change the IPC contract (`citation_control_*.json`,
  `citation_status_*.json`, `gui_*.json`), update
  [`docs/IPC_PROTOCOL.md`](docs/IPC_PROTOCOL.md) **in the same commit**.

---

## 9. Code of conduct

Be specific, be kind, and assume the other person has reasons. If a
maintainer redirects ("stop guessing", "ultrathink this"), that's an
instruction to slow down and gather evidence, not a personal critique.
