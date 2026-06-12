# Commands Reference

All operator-facing commands for the Discord bot, Flask web UI, and shell
launchers.

**Asset types supported:** `auto`, `presentation`, `poster`, `proceedings`,
`journal_article`, `book_chapter`, `abstract`, `technical_documentation`

---

## Shell launchers

| Command | Mode | Web UI |
|---|---|---|
| `./run_standalone.command` | GUI only (no Discord) | http://localhost:8765 |
| `./start_all.sh` | Discord + Flask + worker | http://localhost:8765 |
| `./start_smart_batch.sh` | Discord bot + worker only | — |
| `./run_esp_app.command` | Delegates to `start_all.sh` | http://localhost:8765 |
| `run_standalone.command` (double-click) | macOS GUI-only entry | http://localhost:8765 |

Advanced:

```bash
.venv/bin/python esp_gui_web.py --standalone --port 8765
.venv/bin/python -m automation.worker <channel_id>
```

---

## Flask web UI (standalone & full stack)

### Pages

| Route | Description |
|---|---|
| `/` | Main control panel |
| `/matcher` | Citation fuzzy-match / dedup |

### Citation management

| Action / Route | Method | Description |
|---|---|---|
| Add citation | `POST /api/add` | Body: `{ "text": "..." }` — supports multi-citation paste |
| Fill next | `POST /api/fill` | Start worker on next queued citation |
| View queue | `GET /api/queue` | List queued citations |
| Clear queue | `POST /api/clear` | Remove all queued citations |
| Match citations | `POST /api/match_citations` | Fuzzy-match against a reference list |

### Worker control

| Action / Route | Method | Description |
|---|---|---|
| Status | `GET /api/status` | Worker state, queue size, researcher, asset mode |
| Logs | `GET /api/logs` | Tail recent log lines |
| Pause | `POST /api/pause` | Pause worker loop |
| Resume | `POST /api/resume` | Resume worker loop |
| Skip | `POST /api/skip` | Skip current citation |
| Continue | `POST /api/continue` | Signal form was saved; advance queue |
| Go home | `POST /api/go_home` | Navigate browser to Esploro home |
| Close | `POST /api/close` | Shut down worker and Flask |

### Configuration

| Action / Route | Body | Description |
|---|---|---|
| `POST /api/set_researcher` | `{ "name": "Last, First" }` | Set active researcher |
| `POST /api/set_asset_type` | `{ "type": "presentation" }` | Set asset mode |
| `POST /api/set_restart_policy` | `{ "enabled": bool, "interval": int }` | Auto-restart policy |
| `POST /api/set_author_add_delay` | `{ "delay": int }` | ms between author additions |
| `POST /api/toggle_auto_fill_authors` | — | Toggle auto-fill authors |
| `POST /api/add_topic` | topic text | Add research topic |
| `POST /api/remove_topic` | topic text | Remove research topic |
| `POST /api/clear_topics` | — | Clear all additional topics |

Keyboard shortcuts are documented in the UI (`templates/index.html`).

---

## Discord slash commands

| Command | Description |
|---|---|
| `/fill` | Fill the next citation in the queue |
| `/queue` | Show current queue |
| `/clear` | Clear the queue for this channel |
| `/skip` | Skip the current citation |
| `/close` | Close worker/browser |
| `/pause` | Pause processing |
| `/resume` | Resume processing |
| `/stats` | Show enqueued / processed / error counters |
| `/resync` | Re-register slash commands (after `DISCORD_GUILD_ID` change) |
| `/set_type` | Set asset mode: Auto, Presentation, Poster, Proceedings, Journal Article, Book Chapter, Abstract, Technical Documentation |
| `/set_researcher` | Set default researcher (dropdown) |
| `/add` | Manually add a citation with optional type override |
| `/set_additional_topic` | Add a Description & Research topic (up to 6) |
| `/clear_additional_topics` | Remove all additional topics |

---

## Discord text commands (legacy)

| Command | Alias | Description |
|---|---|---|
| `!fill` | `!f` | Fill next citation |
| `!queue` | — | Display queue |
| `!clear` | — | Clear queue |
| `!skip` | — | Skip current |
| `!close` | — | Close worker/browser |
| `!pause` | — | Pause |
| `!resume` | — | Resume |
| `!stats` | — | Show counters |
| `!resync` | — | Re-register slash commands |
| `!add <text>` | — | Manually add citation |
| `!set type <mode>` | — | Set asset type mode |
| `!set researcher "Last, First"` | — | Set researcher |
| `!help` | — | Show command list |

---

## Test & maintenance scripts

```bash
.venv/bin/python test_citations.py
.venv/bin/python test_parser_simple.py      # OpenAI path only
.venv/bin/python test_book_chapter.py
.venv/bin/python test_proceedings.py
.venv/bin/python test_tech_doc_parser.py
.venv/bin/python tests/performance_tests.py
bash scripts/cleanup_project.sh
bash scripts/update_dependencies.sh
```
