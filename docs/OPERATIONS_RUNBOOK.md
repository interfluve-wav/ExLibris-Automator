# Operations Runbook

This runbook covers day-to-day operation, health checks, and safe recovery steps for ExLibris Automator.

## 1) Standard Startup

```bash
./start_all.sh
```

Expected result:
- Discord bot running
- Flask GUI running on `http://localhost:8765`

## 2) Pre-Flight Checklist

- `.env` exists and required variables are set:
  - `OPENAI_API_KEY`
  - `ESPLORO_USERNAME`
  - `ESPLORO_PASSWORD`
  - `DISCORD_BOT_TOKEN`
- Python environment is activated.
- Playwright Chromium is installed.

## 3) Runtime Health Checks

Use these to verify service health quickly:

```bash
tail -f logs/discord_bot.log
tail -f logs/flask_gui.log
```

Check that:
- The bot is connected and accepting commands.
- The Flask UI is serving status updates.
- Worker transitions status through `processing` to `completed` (or `failed` with error).

## 4) Queue Behavior Expectations

- Queue count should reflect current run remaining citations in UI.
- As citations are filled, queue count should decrement.
- Historical `enqueued/processed` stats may remain cumulative.

## 5) Common Recovery Actions

### Bot not responding
1. Stop services (`Ctrl+C` in the `start_all.sh` terminal).
2. Restart with `./start_all.sh`.
3. Confirm `DISCORD_BOT_TOKEN` and `CITATION_CHANNEL_ID`.

### Fill stuck in "processing"
1. Check `logs/discord_bot.log` and `logs/flask_gui.log`.
2. Inspect latest worker status file:
   - `citation_status_<channel_id>.json`
3. If status is `failed`, review error and retry citation.

### UI queue count looks wrong
1. Refresh web UI.
2. Verify queue via UI `View Queue` action.
3. Restart stack if stale status files are suspected.

## 6) Safe Shutdown

Preferred:
- Stop with `Ctrl+C` in the terminal running `start_all.sh`.

This shuts down:
- Discord bot process
- Flask process
- Associated worker processes started by this session

## 7) File-Based IPC Reference

Key files:
- `citation_control_<channel>.json`
- `citation_status_<channel>.json`
- `gui_completion_status.json`

Worker status includes:
- `last_written_id`
- `state` (`processing`, `completed`, `failed`)
- `error` (present on failed)

## 8) Change Management Notes

- Keep UI-only requests limited to templates/static behavior.
- Avoid backend behavior changes unless explicitly requested.
- Do not hard-code secrets; use `.env` only.
