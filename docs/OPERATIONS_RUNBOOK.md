# Operations Runbook

Day-to-day operation, health checks, and safe recovery for **ExLibris Automator**.

**Branch:** `v7` (working branch)

**Simplest way to run:** `./run_standalone.command` — Flask web app only.
Discord bot, webhooks, and `./start_all.sh` are optional.

---

## 1. Standard startup

### Standalone Flask web app (recommended)

```bash
./run_standalone.command
```

Expected: Flask UI at **http://localhost:8765**, browser may auto-open.

Requires only `ESPLORO_USERNAME` + `ESPLORO_PASSWORD` in `.env`. No Discord
token or webhook configuration needed.

### Optional: full stack (Discord + Flask)

```bash
./start_all.sh
```

Expected:
- Discord bot running (`logs/discord_bot.log`)
- Flask GUI at **http://localhost:8765** (`logs/flask_gui.log`)
- Worker spawned on first fill

> **Port note:** Default is **8765**, not 5000. On macOS, port 5000 is often
> occupied by Apple AirTunes. Use `--port` only if you have a specific reason.

---

## 2. Pre-flight checklist

| Check | Standalone | Full stack |
|---|---|---|
| `.venv` exists | auto via launcher | auto via launcher |
| `ESPLORO_USERNAME` / `ESPLORO_PASSWORD` in `.env` | required | required |
| `DISCORD_BOT_TOKEN` in `.env` | not needed | required |
| `static/css/output.css` exists | auto-built if missing | auto-built if missing |
| Playwright Chromium installed | `playwright install chromium` | same |
| `OPENAI_API_KEY` | optional (manual parser works) | optional |

---

## 3. Runtime health checks

### Web UI

```bash
curl -sI http://127.0.0.1:8765/ | head -n 1
curl -s http://127.0.0.1:8765/api/status | python3 -m json.tool
```

Healthy `/api/status` fields:
- `status`: `idle`, `processing`, or `waiting`
- `assetMode`: one of the supported config modes (not `ad_media_mention`)
- `queueSize`: current-run remaining count

### Logs

```bash
tail -f logs/flask_gui.log          # full stack
tail -f logs/discord_bot.log        # full stack only
```

### Processes

```bash
pgrep -fl "esp_gui_web.py|automation.worker|discord_bot_batch_smart"
```

### Worker status file

```bash
cat citation_status_*.json | python3 -m json.tool
```

States: `processing` → `completed` or `failed` (with `error` field).

---

## 4. Queue behavior

- **Queue count in the UI** reflects **current-run remaining** citations, not
  lifetime totals.
- `bot_config.json` → `stats.enqueued/processed/errors` are **cumulative**
  counters across all sessions.
- Citations split on blank lines; if every line is >30 chars with no blank
  lines, each line becomes its own citation (`/api/add` heuristic).

---

## 5. Parser expectations

The worker uses: **OpenAI → manual asset parser → minimal fallback**.

Operators commonly run with **manual parsers only** (no OpenAI quota or key).
Worker logs will show `Parser path: manual` — this is expected.

---

## 6. Common recovery actions

### Fill failed with Playwright strict-mode / locator error

1. Restart the worker to pick up latest code:
   ```bash
   pkill -f "automation.worker"
   ```
2. Trigger fill again from the UI — Flask spawns a fresh worker.
3. Or wait for `auto_restart_interval` (default 7 citations) to rotate it.

### Bot not responding (full stack)

1. `Ctrl+C` in the `start_all.sh` terminal.
2. `./start_all.sh`
3. Verify `DISCORD_BOT_TOKEN` and `CITATION_CHANNEL_ID` in `.env`.

### Fill stuck in "processing"

1. Check `citation_status_<channel>.json` for `failed` + `error`.
2. Tail `logs/flask_gui.log`.
3. Use **Skip** in the UI or `/skip` in Discord.
4. If browser is wedged: **Close** in UI, then restart fill.

### UI queue count looks wrong

1. Hard-refresh the browser tab.
2. `GET /api/queue` or use **View Queue** in the UI.
3. Restart `./run_standalone.command` if status files are stale.

### Worker has old code after `git pull`

```bash
pkill -f "automation.worker"
# next fill spawns fresh worker with updated modules
```

---

## 7. Safe shutdown

**Preferred:** `Ctrl+C` in the terminal running the launcher.

`run_standalone.command` and `start_all.sh` both trap `EXIT` and kill worker
processes.

Manual cleanup if needed:

```bash
pkill -f "automation.worker"
pkill -f "esp_gui_web.py"
pkill -f "discord_bot_batch_smart.py"
```

---

## 8. File-based IPC (quick reference)

| File | Direction | Purpose |
|---|---|---|
| `citation_control_<channel>.json` | UI/bot → worker | Next citation payload |
| `citation_status_<channel>.json` | worker → UI/bot | `processing` / `completed` / `failed` |
| `gui_continue.json` | UI → worker | Operator saved; advance queue |
| `gui_skip.json` | UI → worker | Skip current citation |
| `gui_pause.json` | UI → worker | Pause loop |
| `gui_go_home.json` | UI → worker | Navigate Esploro home |

Full contract: [`IPC_PROTOCOL.md`](IPC_PROTOCOL.md).

---

## 9. Change management

- UI-only requests → touch `templates/` and `src/input.css` only; run
  `npm run build:css`.
- Automation changes → update the relevant `automation/*_impl.py` **and**
  verify worker restart picks them up.
- New asset types → follow the five registration points in
  [`ARCHITECTURE.md` §3](ARCHITECTURE.md#3-module-map).
- Never commit `.env`, credentials, or runtime CSV/log artifacts.
