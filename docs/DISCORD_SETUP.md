## Discord Bot Setup (End-to-End)

Follow these steps to create a Discord bot, invite it to your server, and configure this project to use it.

---

## 1) Create a Discord Application and Bot

1. Go to the Discord Developer Portal: `https://discord.com/developers/applications`
2. Click New Application → give it a name → Create
3. In the left sidebar, open Bot → Add Bot → Yes, do it!
4. Under Bot → Token → Reset Token → Copy and save your token (you will put this in `.env` as `DISCORD_BOT_TOKEN`).

### Required Bot Settings
- Privileged Gateway Intents:
  - MESSAGE CONTENT INTENT: ON
  - (Server Members intent is not required for this bot)

---

## 2) Invite the Bot to Your Server

1. In the application, open OAuth2 → URL Generator
2. Scopes: check `bot` and `applications.commands`
3. Bot Permissions (minimum):
   - Read Messages/View Channels
   - Send Messages
   - Read Message History
   - Add Reactions (optional but recommended)
4. Copy the generated URL and open it in your browser
5. Select your server → Authorize

---

## 3) Find Your Channel ID (optional but recommended)

If you want to restrict the bot to one channel using `CITATION_CHANNEL_ID`:
1. In Discord → User Settings → Advanced → enable Developer Mode
2. Right‑click the channel where the bot should listen → Copy Channel ID
3. Put that value in `.env` as `CITATION_CHANNEL_ID=123456789012345678`

---

## 4) Configure Environment

Create a `.env` file in the project root (see `docs/ENV_EXAMPLE.md`) and set:

```
OPENAI_API_KEY=sk-prod-...
CITATION_PARSER=openai
ESPLORO_USERNAME=your_esploro_username
ESPLORO_PASSWORD=your_esploro_password
DISCORD_BOT_TOKEN=your_discord_bot_token
# Optional: restrict the bot to a single channel
# CITATION_CHANNEL_ID=123456789012345678

# Optional
OPENAI_MODEL=gpt-4o-mini
DEFAULT_RESEARCHER=Scarano, Frank J
```

Notes:
- The bot uses OpenAI for citation parsing and does not require any local LLM.
- Keep your token secret. If it leaks, reset it in the Developer Portal.

---

## 5) Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

---

## 6) Run the Bot

```bash
./start_smart_batch.sh
```

On first start, slash commands are automatically synced. You should see logs like “Slash commands synced”. If you don’t, see Troubleshooting.

In Discord (in the channel you invited the bot to):
- Paste citations (they’re auto-queued)
- Use `!f` or `/fill` to fill the next citation

---

## Troubleshooting

**Slash commands not showing**
- Ensure the bot has the `applications.commands` scope when invited
- Wait up to a minute after first run; try re-running the bot to resync
- Set `DISCORD_GUILD_ID` in `.env` (your server ID) to sync immediately to that guild
- In Discord, run `!resync` (or `/resync`) to force registration and purge global commands to avoid duplicates
- The bot logs “Slash commands synced …” on success

**Bot not responding to messages**
- Confirm MESSAGE CONTENT INTENT is enabled in the Developer Portal (Bot tab)
- Verify `DISCORD_BOT_TOKEN` is set correctly in `.env`
- If using `CITATION_CHANNEL_ID`, make sure you’re in that channel

**Permissions errors**
- Reinvite the bot with required permissions (Read, Send, Read History)

**OpenAI errors**
- Verify `OPENAI_API_KEY` (sk‑prod) is valid and has access to the selected model
- Check `OPENAI_MODEL` (defaults to `gpt-4o-mini`)

**Playwright/browser issues**
- Ensure browsers are installed: `python -m playwright install chromium`
- If the browser fails to open on first `!f`, check terminal logs

---

## What Happens Internally

- The Discord bot queues citations and starts a persistent Playwright worker on `!f`
- The worker logs into Esploro, fills the form, and stays open between items
- A concise field-by-field summary is posted back to Discord for each fill


