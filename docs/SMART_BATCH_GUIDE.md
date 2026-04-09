## Smart Batch Guide

Process multiple citations efficiently. The browser opens once and stays open while you fill items.

---

Prereqs:
- Complete Discord bot setup first: see `docs/DISCORD_SETUP.md`
- Ensure `.env` is configured (see `docs/ENV_EXAMPLE.md`) and Playwright installed

## Quick Start

### Start the Bot

```bash
cd /Users/suhaas/esp (mini)
./start_smart_batch.sh
```

### Mac Launcher (GUI buttons)
- Double‑click `run_esp_app.command` to start the bot and show a small dialog with “Fill Next” and “Close”.
- Requirements:
  - `CITATION_CHANNEL_ID` must be set (the launcher can prompt; you can also export it ahead of time).
  - The Discord queue must not be empty (paste a citation or use `/add <citation>`).
- After login, click “Deposit Asset”, select the researcher and asset type (“Conference presentation”), then click “Next” to reach the form page. The bot fills fields automatically there.
- “Close” stops the worker and the bot and should take the bot offline immediately.

### Send Your Citations

Paste citations in the bot's channel (or the channel set via `CITATION_CHANNEL_ID`):

```
Smith, J. (2024). Citation 1. Proceedings...
```
Bot: `✅ Citation added to queue! Position: 1`

```
Jones, A. (2024). Citation 2. Proceedings...
```
Bot: `✅ Citation added to queue! Position: 2`

```
Brown, B. (2024). Citation 3. Proceedings...
```
Bot: `✅ Citation added to queue! Position: 3`

### Process Them

**Step 1:** Start filling

```
!f
```

Bot response:
```
🌐 Opening browser and filling first citation...
📋 Asset type: Presentation
📊 Remaining in queue: 2

Browser will stay open. Use !f for next citation.
```

**Browser opens** → Form is filled → Review and submit

**Step 2:** Fill next (in same browser!)

```
!f
```

Bot response:
```
📝 Filling next citation in existing browser...
📋 Asset type: Presentation
📊 Remaining in queue: 1

The form will refresh with new data.
```

**Same browser** → Form refreshes with new data → Review and submit

**Step 3:** Fill last one

```
!f
```

Bot response:
```
📝 Filling next citation in existing browser...
📋 Asset type: Presentation
📊 Remaining in queue: 0

🎉 This was the last citation!
```

**Same browser** → Form refreshes → Submit

**Step 4:** Close browser

```
!close
```

Bot: `🔴 Browser closed!`

**Done!** 🎉

---

## Commands

| Command | What it does |
|---------|--------------|
| `!f` or `!fill` | Fill next citation (browser stays open) |
| `/fill` | Slash version of fill |
| `!queue` | Show all queued citations |
| `!close` | Close the browser window |
| `!clear` | Remove all queued citations |
| `!skip` | Skip current citation |
| `!help` | Show help message |
| `/set_additional_topic topic:<text>` | Add a "Description and Research" topic (max 6) |
| `/clear_additional_topics` | Clear all additional topics for this channel |
| `/set_type` | Set asset type mode |
| `/set_researcher` | Set default researcher |
| `/stats`, `/pause`, `/resume`, `/resync` | Utilities |

---

## Example Session

```
[User] Smith, J. (2024). Citation 1...
[Bot]  ✅ Added to queue! Position: 1

[User] Jones, A. (2024). Citation 2...
[Bot]  ✅ Added to queue! Position: 2

[User] Brown, B. (2024). Citation 3...
[Bot]  ✅ Added to queue! Position: 3

[User] !queue
[Bot]  📋 Citation Queue (3 items)
       1. Presentation - Smith, J. (2024)...
       2. Presentation - Jones, A. (2024)...
       3. Presentation - Brown, B. (2024)...

[User] !f
[Bot]  🌐 Opening browser...
       [Browser opens with Citation 1 filled]
       📄 Attached: CSV + summary files

[User reviews and submits form in browser]

[User] !f
[Bot]  📝 Filling next citation in existing browser...
       [Same browser refreshes with Citation 2]
       📄 Attached: CSV + summary files

[User reviews and submits form]

[User] !f
[Bot]  📝 Filling next citation in existing browser...
       🎉 This was the last citation!
       [Same browser refreshes with Citation 3]
       📄 Attached: CSV + summary files

[User reviews and submits form]

[User] !close
[Bot]  🔴 Browser closed!
```

---

## Tips

1. **Queue all citations first**
   - Paste all citations before starting
   - Verify with `!queue`

2. **Keep your rhythm**
   - `!f` → Review → Submit → `!f` → Review → Submit...
   - No browser closing delays!

3. **Keep browser visible**
   - Don't minimize the browser
   - Makes it easier to review each form

4. **Use keyboard shortcuts**
   - Tab to navigate form fields
   - Enter to submit
   - Faster than clicking

5. **Skip problematic ones**
   - Use `!skip` if a citation is bad
   - Come back to it later

---

## Troubleshooting

### Browser doesn't open on first `!f`
- Check terminal output for errors
- Make sure Playwright is installed: `python -m playwright install chromium`

### “Fill Next” button in launcher does nothing
- Ensure `CITATION_CHANNEL_ID` is set (required for launcher-triggered fill).
- Ensure the queue has items (`/queue`), add one with `/add`.
- After login, navigate to the form page (Deposit Asset → select researcher/type → Next).

### Browser closes between citations
- Make sure you're using `./start_smart_batch.sh`
- Don't manually close the browser
- Use `!close` command when done

### Form doesn't refresh on `!f`
- Browser might have crashed
- Use `!close` then `!f` to restart

### Wrong data in form
- Check the CSV/summary files the bot sends
- Data comes from citation parsing
- Manually correct in browser if needed

---

<!-- Other modes removed in minimal setup. -->

---

## How It Works

**Behind the scenes:**

1. Bot starts a **persistent worker process**
2. Worker opens browser and logs into Esploro
3. Worker **stays running** and watches for citations
4. Each `!f` command sends a citation to the worker
5. Worker fills the form **in the same browser**
6. Browser stays open until you use `!close`

**Result:** Maximum efficiency! 🚀

---

## Quick Commands Reference

```bash
# Start smart batch bot
./start_smart_batch.sh

# In Discord:
!f        # Fill next (browser stays open!)
!queue    # Show queue
!close    # Close browser when done
!skip     # Skip current
!clear    # Clear all
!help     # Show help
```

---

<!-- Switching modes is not applicable in minimal setup. -->

**Smart Batch Mode = Best for bulk processing! 📚⚡**
