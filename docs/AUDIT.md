# Repository Audit — 2026-05-11

One-time health audit of **ExLibris Automator** on branch `v7` at commit
`5a45a94` (pre-quickstart commit). Re-run the smoke-test block in
[`QUICKSTART.md`](QUICKSTART.md) after major changes.

---

## Summary

| Area | Result |
|---|---|
| Python imports (core modules) | **PASS** |
| Bytecode compile (`compileall`) | **PASS** |
| Shell launcher syntax (`bash -n`) | **PASS** |
| Flask UI boot + `/api/status` | **PASS** |
| Manual citation parser | **PASS** |
| Researcher selector fix (all 7 impls) | **PASS** |
| `ad_media_mention` removed from code | **PASS** |
| `split_citation_blocks` logic | **PASS** |
| OpenAI parser (`test_parser_simple.py`) | **WARN** — 429 quota (expected) |
| `requirements.txt` hygiene | **WARN** — duplicate unpinned entries |
| Legacy docs (`replit.md`, roadmap) | **INFO** — stale port 5000 / old selector examples |

**Overall:** safe to run in standalone mode on `v7`. No blocking code defects
found in this audit.

---

## Checks performed

### 1. Module import smoke test

```
utils.asset_type_utils, automation.worker, discord_bot_batch_smart,
esp_gui_web, openai_parser — all OK
```

### 2. Bytecode compilation

```bash
.venv/bin/python -m compileall -q automation utils esp_gui_web.py \
  discord_bot_batch_smart.py openai_parser.py
# exit 0
```

### 3. Shell launchers

```bash
bash -n start_all.sh start_smart_batch.sh run_standalone.command \
  scripts/ensure_python_venv.sh
# all OK
```

### 4. Runtime health (standalone)

```bash
./run_standalone.command   # background
curl -sI http://127.0.0.1:8765/           # HTTP/1.1 200 OK
curl -s http://127.0.0.1:8765/api/status  # valid JSON, status idle/processing
curl -s http://127.0.0.1:8765/api/queue   # success: true
```

### 5. Parser chain

- `test_parser_simple.py` → OpenAI 429 (`insufficient_quota`) — **not a code bug**
- Manual `journal_impl.parse_citation(...)` → **OK** (`A study of fish`)

### 6. Citation splitting (`esp_gui_web.split_citation_blocks`)

- Blank-line delimiters → 2 citations ✓
- Per-line (>30 chars, no blank lines) → 2 citations ✓
- Short wrapped text → 1 citation ✓

### 7. Asset-type registry

`VALID_CONFIG_MODES` (8 modes including `auto`):

```
abstract, auto, book_chapter, journal_article, poster,
presentation, proceedings, technical_documentation
```

`ASSET_TYPE_HANDLERS` (7 types): all present, no `ad_media_mention`.

### 8. Playwright researcher selector

`get_by_text(researcher)` — **0 matches** in `automation/` (fixed).

`a.dropdown-item.ui-menu-item-wrapper` scoping — **8 call sites** across 7
implementations (proceedings ×2).

### 9. Template / config residue

- `templates/index.html` — no `ad_media_mention` option ✓
- `*.py`, `*.json`, `*.html` — no `ad_media_mention` references ✓

---

## Warnings (non-blocking)

### `requirements.txt` duplicate entries

Lines 1–12 pin versions; lines 13–26 repeat the same packages without pins.
This can cause pip to resolve different versions on fresh installs. **Fix:**
deduplicate to pinned entries only (see commit accompanying this audit).

### OpenAI quota exhausted

Production runs use **manual parsers** as the effective primary path. Worker
logs showing `Parser path: manual` are expected.

### Stale documentation (reference only)

| File | Issue |
|---|---|
| `replit.md` | References port 5000 (legacy Replit deploy) |
| `docs/Asset Type Integration Future.md` | Example still shows `get_by_text(researcher)` |

These are roadmap/legacy docs — not operator-facing.

---

## Recommended post-pull operator steps

```bash
git pull origin v7
pkill -f "automation.worker"    # reload automation modules
./run_standalone.command
```

---

## Re-run audit

```bash
.venv/bin/python -c "import esp_gui_web, automation.worker; print('OK')"
.venv/bin/python -m compileall -q automation utils esp_gui_web.py
curl -s http://127.0.0.1:8765/api/status | python3 -m json.tool
```

See also [`QUICKSTART.md` § Smoke tests](QUICKSTART.md#smoke-tests-no-esploro-login-required).
