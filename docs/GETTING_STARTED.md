# Getting Started

Step-by-step setup for **ExLibris Automator** on macOS (the supported daily-driver
environment).

**Just want commands?** → [`QUICKSTART.md`](QUICKSTART.md)

For architecture detail see [`ARCHITECTURE.md`](ARCHITECTURE.md); for day-to-day
operation see [`OPERATIONS_RUNBOOK.md`](OPERATIONS_RUNBOOK.md).

---

## 1. Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Python | **3.12** (pinned in `.python-version`) | `python3 --version` |
| Node.js | 18+ | `node --version` |
| npm | bundled with Node | `npm --version` |
| Git | any recent | `git --version` |

Clone and enter the repo:

```bash
git clone git@github.com:interfluve-wav/ExLibris-Automator.git
cd ExLibris-Automator
git checkout v7    # working branch
```

---

## 2. Bootstrap the environment

The launchers call `scripts/ensure_python_venv.sh` automatically, but you can
run it once up front:

```bash
bash scripts/ensure_python_venv.sh
```

Install frontend assets and Playwright Chromium:

```bash
npm install
npm run build:css
.venv/bin/python -m playwright install chromium
```

---

## 3. Configure secrets

Copy the template and edit:

```bash
cp docs/ENV_EXAMPLE.md .env   # then open .env in your editor
```

| Variable | Required | Notes |
|---|---|---|
| `ESPLORO_USERNAME` | **Yes** | Esploro login |
| `ESPLORO_PASSWORD` | **Yes** | Esploro login |
| `OPENAI_API_KEY` | No | Enables GPT parsing; **manual parsers run without it** |
| `DISCORD_BOT_TOKEN` | Only for bot mode | See [`DISCORD_SETUP.md`](DISCORD_SETUP.md) |
| `CITATION_CHANNEL_ID` | Only for bot mode | Discord channel the bot listens on |

Never commit `.env`. See [`../SECURITY.md`](../SECURITY.md).

---

## 4. Choose a run mode

### A. Standalone (recommended — no Discord)

Double-click **`run_standalone.command`** or:

```bash
./run_standalone.command
```

- Web UI: **http://localhost:8765**
- No Discord bot required
- `ESP_STANDALONE=1` is set automatically

### B. Full stack (Discord + Flask UI)

Requires a configured `.env` with `DISCORD_BOT_TOKEN`:

```bash
./start_all.sh
```

- Web UI: **http://localhost:8765**
- Discord bot + Flask + worker coordination

### C. Discord bot only

```bash
./start_smart_batch.sh
```

---

## 5. First citation (standalone)

1. Open **http://localhost:8765**
2. Paste a citation into the text area and click **Add**
3. Set researcher and asset type if needed
4. Click **Fill** — Chromium opens, logs into Esploro, fills the form
5. **You** review the form in the browser and click Save in Esploro
6. Click **Saved — Continue** in the web UI to advance the queue

The worker never auto-submits. This is intentional.

---

## 6. Parser behavior

Citation parsing follows a fallback chain:

1. **OpenAI** (if `OPENAI_API_KEY` is set and quota is available)
2. **Asset-specific manual parser** (`automation/*_impl.py`)
3. **Minimal generic parser** (title/year extraction only)

In practice many operators run with the **manual parser** as the effective
primary path when OpenAI quota is exhausted or the key is unset. This is
normal — not a regression.

---

## 7. Verify the install

```bash
# Module smoke test
.venv/bin/python -c "import esp_gui_web, automation.worker; print('OK')"

# Health check (with app running)
curl -s http://127.0.0.1:8765/api/status | python3 -m json.tool
```

Expected: `"status": "idle"` or `"processing"` with valid JSON fields.

---

## 8. Next steps

| Goal | Document |
|---|---|
| Daily workflow | [`SMART_BATCH_GUIDE.md`](SMART_BATCH_GUIDE.md) |
| All commands | [`COMMANDS_REFERENCE.md`](COMMANDS_REFERENCE.md) |
| Health checks & recovery | [`OPERATIONS_RUNBOOK.md`](OPERATIONS_RUNBOOK.md) |
| Discord bot setup | [`DISCORD_SETUP.md`](DISCORD_SETUP.md) |
| How the system fits together | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Contributing / PRs | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |
