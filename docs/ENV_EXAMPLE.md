# Environment Variables

Copy these into a `.env` file at the project root. **Never commit `.env`.**

```bash
# ── Required for Esploro automation ──────────────────────────────────
ESPLORO_USERNAME=
ESPLORO_PASSWORD=

# ── Optional: OpenAI parsing (manual parsers work without this) ──────
# OPENAI_API_KEY=sk-prod-...
# OPENAI_MODEL=gpt-4o-mini
# CITATION_PARSER=openai

# ── Required only for Discord bot mode ───────────────────────────────
# DISCORD_BOT_TOKEN=
# CITATION_CHANNEL_ID=123456789012345678
#   Discord → Settings → Advanced → Developer Mode ON
#   Right-click channel → Copy Channel ID
# DISCORD_GUILD_ID=123456789012345678
#   Right-click server icon → Copy Server ID (speeds slash-command sync)

# ── Optional runtime ─────────────────────────────────────────────────
# DEFAULT_RESEARCHER=Scarano, Frank J
# LOG_LEVEL=INFO
# HEADLESS=0
# BOT_CONFIG_PATH=./bot_config.json
# ESP_STANDALONE=1          # set automatically by run_standalone.command
# FLASK_HOST=127.0.0.1
# NO_OPEN_BROWSER=1

# ── Optional notifications (not wired in all deployments) ──────────
# DISCORD_WEBHOOK_URL=
# NOTIFICATION_EMAIL=
```

## Variable reference

| Variable | Required | Mode | Description |
|---|---|---|---|
| `ESPLORO_USERNAME` | Yes | all | Esploro login username |
| `ESPLORO_PASSWORD` | Yes | all | Esploro login password |
| `OPENAI_API_KEY` | No | all | GPT citation parser; unset → manual parser |
| `OPENAI_MODEL` | No | all | Default `gpt-4o-mini` |
| `CITATION_PARSER` | No | all | `openai` when key is set |
| `DISCORD_BOT_TOKEN` | Yes | bot | Bot token from Discord Developer Portal |
| `CITATION_CHANNEL_ID` | Recommended | bot | Restrict bot to one channel |
| `DISCORD_GUILD_ID` | No | bot | Guild-scoped slash command registration |
| `DEFAULT_RESEARCHER` | No | all | Override default researcher name |
| `HEADLESS` | No | all | `1` / `true` for headless Chromium |
| `LOG_LEVEL` | No | all | `DEBUG`, `INFO`, `WARN` |
| `BOT_CONFIG_PATH` | No | all | Alternate path to `bot_config.json` |
| `ESP_STANDALONE` | No | standalone | `1` bypasses Discord requirement |

## Parser note

Many operators run **without** `OPENAI_API_KEY`. The worker falls back to
asset-specific manual parsers in `automation/*_impl.py`. This is the
supported production path when OpenAI quota is unavailable.

See [`GETTING_STARTED.md` §6](GETTING_STARTED.md#6-parser-behavior).
