# ExLibris Automator (Esploro Bot)

## Project Overview

A Python-based automation suite that streamlines entry of academic citations into the Esploro research repository system. It uses AI-driven parsing (OpenAI GPT-4o-mini) to extract metadata from citations and browser automation (Playwright) to populate web forms.

## Architecture

- **Web UI**: Flask-based control panel (`esp_gui_web.py`) running on port 5000
- **Automation Worker**: `automation/worker.py` — background process using Playwright for browser-based form filling
- **AI Parser**: `openai_parser.py` — uses OpenAI API to parse citation text into structured JSON
- **Discord Bot**: `discord_bot_batch_smart.py` — optional Discord interface for command-driven citation queueing
- **IPC**: File-based inter-process communication via JSON control files in the project root

## Key Files

- `esp_gui_web.py` — Main Flask web application
- `discord_bot_batch_smart.py` — Discord bot integration
- `openai_parser.py` — Citation parsing with OpenAI
- `automation/worker.py` — Playwright browser automation worker
- `automation/presentations_impl.py` — Presentations form automation
- `automation/journal_impl.py` — Journal articles form automation
- `automation/book_chapters_impl.py` — Book chapters form automation
- `automation/proceedings_impl.py` — Conference proceedings form automation (two variants)
- `automation/poster_impl.py` — Posters form automation
- `utils/` — Shared helper modules (config, logging, IPC, validation)
- `templates/index.html` — Main web UI template
- `bot_config.json` — Bot configuration (researchers, asset types)
- `citations_config.json` — Citation processing configuration
- `start_desktop.sh` — Xvfb + x11vnc launcher for VNC Desktop workflow

## Running the App

The app runs in standalone mode (no Discord bot required) on port 5000:

```
FLASK_HOST=0.0.0.0 NO_OPEN_BROWSER=1 python esp_gui_web.py --standalone --port 5000
```

## Configured Workflows

- **Start application** — `FLASK_HOST=0.0.0.0 NO_OPEN_BROWSER=1 python esp_gui_web.py --standalone --port 5000` (webview, port 5000)
- **VNC Desktop** — `bash start_desktop.sh` (vnc) — runs Xvfb on `:99` + x11vnc so headed Playwright windows are visible

## Environment Variables / Secrets

- `ESPLORO_USERNAME` — Replit secret — Esploro login username
- `ESPLORO_PASSWORD` — Replit secret — Esploro login password
- `FLASK_HOST` — Set to `0.0.0.0` in workflow command
- `NO_OPEN_BROWSER` — Set to `1` in workflow command
- `OPENAI_API_KEY` — Not set; app falls back to manual citation parser
- `DISPLAY` — Worker subprocess uses `DISPLAY=:99` (set by worker.py) for headed Playwright

## IPC Control Files (project root)

The Flask app writes JSON files; the worker loop polls and deletes them:

| File | Action |
|------|--------|
| `gui_skip.json` | Skip the current citation being processed |
| `gui_go_home.json` | Navigate to UMassD Libraries home screen |
| `gui_pause.json` | Pause the worker loop |

## Flask API Endpoints (key)

- `POST /api/skip` — Write `gui_skip.json` to skip current citation
- `POST /api/go_home` — Write `gui_go_home.json` to navigate home in browser
- `POST /api/set_researcher` — Set active researcher name
- `GET /api/status` — Return current worker status JSON

## Automation Flow (per citation)

1. Worker picks next citation from queue
2. Navigates: clicks "UMassD Libraries" home link → "Deposit Asset"
3. Selects asset type (Journal, Presentation, Poster, etc.)
4. Fills all form fields (title, authors, date, DOI, abstract, etc.)
5. Waits for user to manually save, then click **"✅ Saved — Continue"** in the web UI
6. Waits **10 seconds** after continue signal
7. Clicks "UMassD Libraries" to return home (fallback: direct URL)
8. Ready for next citation

## Cookie / Banner Handling

`dismiss_cookie_banner()` in `automation/worker.py` auto-clicks Accept/I Agree banners on login and after home navigation. Chromium launched with `--disable-infobars`.

## UI Controls (templates/index.html button-grid)

- **View Queue** — Show pending citations
- **Clear Queue** — Remove all queued citations
- **Pause / Resume** — Pause/resume worker loop
- **Skip Current** — Skip citation currently being processed
- **Go Home** — Immediately trigger home navigation in the browser

## Frontend (Tailwind CSS + Material Tailwind)

The frontend uses Tailwind CSS v3 with Material Tailwind HTML v2 for styling. CSS is compiled from `src/input.css` to `static/css/output.css`.

- **Color scheme**: Neutral/charcoal palette — grays and slate tones for surfaces, borders, and backgrounds. No purple/indigo colors. Dark mode uses `#111827` background, `#374151` surfaces. Light mode uses clean whites with charcoal text.
- **Material Tailwind**: `@material-tailwind/html` v2 installed, config wrapped with `withMT()` in `tailwind.config.js`
- **Build CSS**: `npm run build:css` — compiles and minifies Tailwind output
- **Watch CSS**: `npm run watch:css` — rebuilds on file changes
- **Config**: `tailwind.config.js` — custom colors, animations, content paths, Material Tailwind plugin
- **Source**: `src/input.css` — Tailwind directives + custom component/state styles
- **Output**: `static/css/output.css` — compiled CSS linked in both templates
- **Templates**: `templates/index.html` and `templates/matcher.html` use Tailwind utility classes

After modifying CSS classes in templates or `src/input.css`, run `npm run build:css` to rebuild.

## Dependencies

Managed via `requirements.txt` with pip. Key packages:
- `flask` — Web framework
- `playwright` — Browser automation
- `openai` — AI citation parsing
- `discord.py` — Discord bot interface
- `pandas`, `openpyxl`, `xlrd` — Data processing
- `PyPDF2`, `python-docx` — Document parsing
- `rapidfuzz` — Fuzzy string matching
- `python-dotenv` — Environment variable management
- `gunicorn` — Production WSGI server

## Nix System Dependencies (required for Playwright)

`expat`, `libxkbcommon`, `udev`, `libgbm`, `mesa`, `lsof` — configured in `.replit` / `replit.nix`.

## Deployment

Configured as a VM deployment (always-on) since the app uses file-based IPC and persistent state.

## Known Non-Issues

- `favicon.ico` returns 404 — harmless
- Pandas warns about `pyarrow` not installed — non-critical
