# Commands Reference

Concise reference for all commands exposed by the Discord bot and helper scripts.

## Discord Slash Commands
- `/fill` – Fill the next citation in the queue.
- `/queue` – Show current queue.
- `/clear` – Clear the queue for this channel.
- `/skip` – Skip the current citation.
- `/close` – Close the worker/browser and stop processing.
- `/pause`, `/resume` – Pause or resume processing for this channel.
- `/stats` – Show counters (enqueued/processed/errors).
- `/resync` – Force slash command re-sync (useful after setting `DISCORD_GUILD_ID`).
- `/set_type` – Set asset type mode for the channel (Auto, Presentation, Poster, Proceedings, Journal Article, Book Chapter, Abstract).
- `/set_researcher name:"Last, First"` – Set default researcher (autocomplete supported).
- `/set_additional_topic topic:<text>` – Add a “Description and Research” topic (up to 6 per channel).
- `/clear_additional_topics` – Remove all additional topics for this channel.

## Text Commands (legacy)
- `!f`, `!fill` – Fill next citation.
- `!queue` – Display queue.
- `!clear` – Clear queue.
- `!skip` – Skip current citation.
- `!close` – Close worker/browser.
- `!pause`, `!resume` – Pause/resume.
- `!stats` – Show counters.
- `!resync` – Re-register slash commands.

## Mac Launcher
- Double-click `run_esp_app.command`.
- Buttons:
  - “Fill Next” – writes `fill_next_signal` the bot watches.
  - “Close” – writes `shutdown_signal` to stop worker and bot.

## Scripts
- `./start_smart_batch.sh` – Start the Discord bot + worker.
- `python3 test_citations.py` – Parser validation over curated inputs.
- `python3 tests/performance_tests.py` – Performance and I/O benchmarks.
- `python3 -m automation.worker <channel_id>` – Start worker manually (advanced).
