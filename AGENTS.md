## Learned User Preferences
- Prefer UI-only changes when requested and avoid backend or behavior regressions.
- Wants direct root-cause investigation and fixes when automation is broken, not just high-level advice.
- Prefers concise, copy-pasteable command answers for operational tasks.
- For matching/automation logic, prefers strict primary matching first, then explicit fallback behavior.
- Prefers preserving the existing local interactive workflow (`./start_all.sh`) over Docker-first operation.
- Wants queue indicators to reflect current-run remaining citations rather than lifetime totals.
- For Esploro taxonomy, classify coverage of a research output as `Media Mention` (not `Book`).
- For Esploro Playwright capture, start from the exact Esploro login URL and leave final submit/save clicks to the user when requested.

## Learned Workspace Facts
- Primary workspace repo is `/Users/suhaas/Documents/Developer/ExLibris-Automator`.
- `./start_all.sh` is used to launch both `discord_bot_batch_smart.py` and `esp_gui_web.py` and expects a `.env` file at repo root for the Discord bot; `./run_standalone.command` is the GUI-only entry point.
- The Flask UI is driven by `templates/index.html`, styled with Tailwind (built CSS at `static/css/output.css`), and supports keyboard-triggered fill actions.
- Runtime bot/worker coordination relies on file-based IPC (`citation_control_*.json`, `citation_status_*.json`).
- `scripts/ensure_python_venv.sh` bootstraps `.venv` and Python dependencies for `start_all.sh`, `start_smart_batch.sh`, and `run_standalone.command` without requiring `.env`.
- Parent transcript files for continual learning live under `/Users/suhaas/.cursor/projects/Users-suhaas-Documents-Developer-ExLibris-Automator/agent-transcripts`.
- User-facing app branding is `ExLibris Automator`.
