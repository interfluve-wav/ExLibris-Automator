# Web App & Discord Bot Integration Steps

## Overview
This document outlines the steps to integrate new asset types with the Discord Bot and Flask Web App for the ESP Citation Automation system.

## System Architecture

The system consists of three main components:

1. **Discord Bot** (`discord_bot_batch_smart.py`) - Receives citations from Discord channels, queues them, and manages the automation workflow
2. **Flask Web App** (`esp_gui_web.py`) - Provides a web interface for controlling the bot, adding citations, and managing settings
3. **Browser Worker** (`automation/worker.py`) - Runs Playwright automation to fill forms in Esploro

### Communication Flow

```
Discord Message → Bot Queue → Worker Process → Esploro Form
   ↑                ↓              ↑                ↓
   └─────────← Status Files ←──────┴────────────────┘

Web App → Control Files → Bot → Worker → Esploro Form
```

## File Structure

```
esp (mini)/
├── automation/
│   ├── abstract.py              # Thin wrapper (export module)
│   ├── abstract_impl.py         # Implementation file
│   ├── journal.py              # Thin wrapper
│   ├── journal_impl.py         # Implementation
│   ├── presentations.py        # Thin wrapper
│   ├── presentations_impl.py   # Implementation
│   ├── poster.py               # Thin wrapper
│   ├── poster_impl.py          # Implementation
│   ├── worker.py               # Browser automation worker
│   └── openai_parser.py        # Citation parser
├── discord_bot_batch_smart.py  # Main Discord bot
├── esp_gui_web.py              # Flask web interface
├── bot_config.json             # Bot configuration
└── .env                        # Environment variables
```

## Integration Steps

### Step 1: Verify Asset Type Implementation Files Exist

Before integrating, ensure you have:
- `automation/{asset_type}_impl.py` - Implementation file with automation logic
- `automation/{asset_type}.py` - Thin wrapper that exports the API

**Required Functions in Implementation File:**
```python
def parse_any_citation(citation_text: str) -> Dict[str, str]:
    """Parse citation text and return structured data"""
    pass

def process_citation(page, citation_data: Dict[str, str], 
                    pause_after: bool = True, 
                    start_from_home: bool = True):
    """Fill Esploro form using Playwright"""
    pass

def save_citation_to_csv(citation_data: Dict[str, str], output_file: str):
    """Save citation to CSV file"""
    pass

def goto_with_retries(page, url: str, attempts: int = 3, 
                     wait_until: str = 'load') -> bool:
    """Navigate with retries"""
    pass
```

### Step 2: Add Asset Type to Worker

Edit `automation/worker.py`:

1. **Import the module** (add at top):
```python
from automation import your_asset_type as your_asset_type_mod
```

2. **Load the module** (in `main()` function):
```python
def main(channel_id):
    # ... existing code ...
    your_asset_type_mod = load_your_asset_type_module()
    your_asset_type_parse = getattr(your_asset_type_mod, "parse_any_citation")
    your_asset_type_process = getattr(your_asset_type_mod, "process_citation")
```

3. **Add loader function**:
```python
def load_your_asset_type_module():
    return your_asset_type_mod
```

4. **Add to asset type switch** (in the worker loop):
```python
# Around line 189-212 in worker.py
elif asset_type == 'your_asset_type':
    parse_fn = your_asset_type_parse
    process_fn = your_asset_type_process
    asset_display = "Your Asset Type Display Name"
```

### Step 3: Add Asset Type to Discord Bot

Edit `discord_bot_batch_smart.py`:

1. **Add to asset type detection** (around line 240-260):
```python
# In detect_asset_type() function
if any(keyword in text_lower for keyword in ['your', 'keywords']):
    return 'your_asset_type'
```

2. **Add slash command option** (around line 580-620):
```python
@tree.command(name="add_your_asset_type", description="Add your asset type citation")
async def add_your_asset_type(interaction: discord.Interaction, citation: str):
    """Add your asset type citation to queue"""
    await add_citation_common(interaction, citation, asset_type='your_asset_type')
```

3. **Update help text** (around line 100-130):
```python
# In on_ready() function
print(f'  /add_your_asset_type - Add your asset type citation')
```

4. **Add to valid asset types list** (search for asset type validation):
```python
VALID_ASSET_TYPES = ['presentation', 'poster', 'book_chapter', 
                     'journal_article', 'proceedings', 'abstract', 
                     'your_asset_type']
```

### Step 4: Add Asset Type to Web App

Edit `esp_gui_web.py`:

1. **Add to asset type dropdown** (around line 233-241 in HTML_TEMPLATE):
```html
<select id="assetTypeSelect" style="...">
    <option value="auto">Auto</option>
    <option value="presentation">Presentation</option>
    <option value="poster">Poster</option>
    <option value="book_chapter">Book Chapter</option>
    <option value="journal_article">Journal Article</option>
    <option value="proceedings">Proceedings</option>
    <option value="abstract">Abstract</option>
    <option value="your_asset_type">Your Asset Type</option>
</select>
```

2. **Add display name mapping** (around line 565-571 in JavaScript):
```javascript
if (assetType === 'your_asset_type') displayName = 'Your Asset Type';
```

3. **Add validation** (around line 1211-1216 in set_asset_type method):
```python
if asset_type not in ('auto', 'presentation', 'poster', 'book_chapter', 
                      'journal_article', 'proceedings', 'abstract', 
                      'your_asset_type'):
    return {'success': False, 'error': f'Invalid asset type: {asset_type}'}
```

### Step 5: Test Integration

#### Testing with Discord Bot:

1. Start the bot:
```bash
python3 discord_bot_batch_smart.py
```

2. In Discord, send a test citation message

3. Use `!f` command to fill the form

4. Check browser automation works correctly

#### Testing with Web App:

1. Start the web app:
```bash
python3 esp_gui_web.py
```

2. Open http://localhost:8765

3. Set asset type to your new type

4. Add a test citation

5. Click "Fill Next Citation"

6. Verify form automation works

### Step 6: Environment Variables

Ensure `.env` file has required variables:

```bash
# Discord Configuration
DISCORD_BOT_TOKEN=your_bot_token_here
CITATION_CHANNEL_ID=your_channel_id_here
DISCORD_GUILD_ID=your_guild_id_here  # Optional, speeds up slash commands

# Esploro Credentials
ESPLORO_USERNAME=your_username
ESPLORO_PASSWORD=your_password

# Default Settings
DEFAULT_RESEARCHER=Last, First
CITATION_PARSER=openai  # or "manual"
OPENAI_API_KEY=your_openai_key  # If using OpenAI parser
OPENAI_MODEL=gpt-4o-mini

# Bot Config
BOT_CONFIG_PATH=bot_config.json
HEADLESS=0  # Set to 1 for headless mode
```

## Control Files

The system uses JSON files for communication between components:

### Bot Control Files:
- `citation_control_{channel_id}.json` - Worker instructions
- `citation_status_{channel_id}.json` - Worker status updates
- `bot_config.json` - Bot configuration (persistent)

### Web App Control Files:
- `gui_add_citation.json` - Add citation from web
- `gui_completion_status.json` - Form fill completion status
- `gui_set_asset_type.json` - Set asset type
- `gui_set_researcher.json` - Set researcher
- `gui_add_topic.json` - Add research topic
- `gui_remove_topic.json` - Remove research topic
- `gui_clear_topics.json` - Clear all topics
- `gui_queue.json` - Queue data response
- `gui_queue_request.json` - Queue data request
- `gui_clear_queue.json` - Clear queue request
- `gui_pause.json` - Pause bot
- `gui_resume.json` - Resume bot
- `gui_skip.json` - Skip current citation
- `fill_next_signal` - Trigger next fill
- `shutdown_signal` - Shutdown bot

## Common Issues

### Asset Type Not Recognized
- Check spelling in `detect_asset_type()` function
- Verify asset type added to `VALID_ASSET_TYPES`
- Ensure asset type matches in worker.py switch statement

### Form Not Filling Correctly
- Check Playwright selectors in `process_citation()` function
- Verify field names match Esploro form
- Test with `HEADLESS=0` to see browser actions

### Web App Control Not Working
- Check control files are being created in project root
- Verify bot is watching for control files (check logs)
- Ensure `CITATION_CHANNEL_ID` is set in .env

### Parser Not Working
- Verify `parse_any_citation()` returns Dict with required fields
- Check `CITATION_PARSER` environment variable
- Test with manual parser if OpenAI fails

## Asset Type Naming Conventions

| Code Value | Display Name | File Prefix |
|-----------|--------------|-------------|
| `presentation` | Conference Presentation | presentations |
| `poster` | Conference Poster | poster |
| `book_chapter` | Book Chapter | book_chapters |
| `journal_article` | Journal Article | journal |
| `proceedings` | Conference Proceedings | proceedings |
| `abstract` | Abstract | abstract |

**When adding new asset types, follow these conventions:**
- Code value: lowercase with underscores (e.g., `technical_report`)
- Display name: Title case (e.g., "Technical Report")
- File prefix: lowercase with underscores (e.g., `technical_report_impl.py`)

## Deployment Checklist

Before deploying a new asset type integration:

- [ ] Implementation file created with all required functions
- [ ] Wrapper file created with exports
- [ ] Asset type added to `worker.py`
- [ ] Asset type added to `discord_bot_batch_smart.py`
- [ ] Asset type added to `esp_gui_web.py`
- [ ] Detection keywords added (if using auto-detection)
- [ ] Tested with Discord bot (`!f` command)
- [ ] Tested with Web App (manual add and fill)
- [ ] Tested with slash commands (if applicable)
- [ ] Documentation updated
- [ ] `.env` file configured
- [ ] Tested with real citations
- [ ] Error handling verified

## Additional Resources

- **Discord Bot Setup**: See `docs/DISCORD_SETUP.md`
- **Smart Batch Guide**: See `docs/SMART_BATCH_GUIDE.md`
- **Environment Variables**: See `docs/ENV_EXAMPLE.md`

## Support

If you encounter issues:
1. Check terminal/console logs for error messages
2. Verify all required files exist
3. Test parser independently with `python3 automation/your_asset_type_impl.py`
4. Check Esploro form field names haven't changed
5. Ensure browser automation selectors are up to date

