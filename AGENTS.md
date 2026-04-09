## Learned User Preferences
- Prefer UI-only changes when requested and avoid backend or behavior regressions.
- Wants direct root-cause investigation and fixes when automation is broken, not just high-level advice.
- Prefers concise, copy-pasteable command answers for operational tasks.
- For matching/automation logic, prefers strict primary matching first, then explicit fallback behavior.
- Prefers preserving the existing local interactive workflow (`./start_all.sh`) over Docker-first operation.
- Wants queue indicators to reflect current-run remaining citations rather than lifetime totals.

## Learned Workspace Facts
- Primary workspace repo is `/Users/suhaas/Documents/Developer/esp - warp`.
- `./start_all.sh` is used to launch both `discord_bot_batch_smart.py` and `esp_gui_web.py`.
- The Flask UI is driven by `templates/index.html` and supports keyboard-triggered fill actions.
- Runtime bot/worker coordination relies on file-based IPC (`citation_control_*.json`, `citation_status_*.json`).
- Parent transcript files for continual learning live under `/Users/suhaas/.cursor/projects/Users-suhaas-Documents-Developer-esp-warp/agent-transcripts`.
- User-facing app branding is `ExLibris Automator`.
