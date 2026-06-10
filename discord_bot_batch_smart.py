#!/usr/bin/env python3
"""
Discord Bot for Smart Batch Citation Processing
Keeps browser open and fills citations one at a time with !f command
"""

import os
import sys
import json
import time
import discord
import asyncio
import subprocess
import signal
from collections import deque
from typing import Dict, Deque, Optional, List
from dotenv import load_dotenv
from utils.logging_utils import make_logger
from utils.asset_type_utils import normalize_config_mode, VALID_CONFIG_MODES
from utils.config_manager import get_config_manager
from utils.input_validation import validate_citation_text, validate_researcher_name, sanitize_text
from discord import app_commands

# Load environment variables
load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
LOG = make_logger("BOT")

# Bot token from environment
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Configuration
CITATION_CHANNEL_ID = os.getenv('CITATION_CHANNEL_ID')
DEFAULT_ASSET_TYPE = "presentation"
DISCORD_GUILD_ID_ENV = os.getenv('DISCORD_GUILD_ID')  # optional, speeds up slash registration

# Citation queues per channel (channel_id -> deque of citations)
citation_queues: Dict[int, Deque[dict]] = {}

# Active browser process per channel
active_processes: Dict[int, subprocess.Popen] = {}
# Track fills per active process to know when to restart
process_fill_counts: Dict[int, int] = {}

# Current citation being processed per channel
processing_citations: Dict[int, dict] = {}


# --------------------
# Bot Config (persistent) - Using ConfigManager for optimized I/O
# --------------------
CONFIG_PATH = os.getenv("BOT_CONFIG_PATH", "bot_config.json")
_config_manager = get_config_manager()

def _default_config():
    return {
        "default_researcher": os.getenv("DEFAULT_RESEARCHER", "Scarano, Frank J"),
        "asset_mode": "auto",  # one of: auto | presentation | poster
        "paused": False,
        "auto_restart_interval": 0,  # 0 means disabled
        "stats": {"enqueued": 0, "processed": 0, "errors": 0},
        "known_researchers": [os.getenv("DEFAULT_RESEARCHER", "Scarano, Frank J")],
    }

# Initialize ConfigManager with the config path
_config_manager.initialize(CONFIG_PATH, default_factory=_default_config)

def load_config() -> dict:
    """Load config using ConfigManager (cached, faster than direct file I/O)."""
    return _config_manager.get_all_sync()

def save_config(cfg: dict) -> None:
    """Save config using ConfigManager (immediate, atomic writes)."""
    # Update with merge to preserve keys not in cfg
    current = load_config()
    current.update(cfg)
    # Update all values and save synchronously
    _config_manager.update_sync(current)
    _config_manager.save_sync()

config = load_config()

# Ensure current researcher is in known_researchers list
if 'known_researchers' not in config:
    config['known_researchers'] = []
current_researcher = config.get('default_researcher')
if current_researcher and current_researcher not in config['known_researchers']:
    config['known_researchers'].append(current_researcher)
    save_config(config)


def get_queue(channel_id: int) -> Deque[dict]:
    """Get or create queue for a channel"""
    if channel_id not in citation_queues:
        citation_queues[channel_id] = deque()
    return citation_queues[channel_id]


class _InteractionMessageAdapter:
    """Minimal adapter exposing .channel for reuse of fill_citation() with slash commands."""
    def __init__(self, channel):
        self.channel = channel


@client.event
async def on_ready():
    LOG.info(f'{client.user} connected')
    if CITATION_CHANNEL_ID:
        print(f'📋 Bot is listening for citations in channel: {CITATION_CHANNEL_ID}')
    else:
        print(f'📋 Bot is listening for citations in ALL channels')
    LOG.info(f"Default asset type: {DEFAULT_ASSET_TYPE}")
    LOG.info(f"Config: asset_mode={config.get('asset_mode')} | researcher={config.get('default_researcher')} | paused={config.get('paused')}")
    print(f'\n📚 SMART BATCH MODE COMMANDS:')
    print(f'  !f (or !fill)  - Fill next citation in browser (keeps browser open)')
    print(f'  !add <text>    - Manually add a citation (if auto-detect fails)')
    print(f'  !queue         - Show queued citations')
    print(f'  !clear         - Clear all queued citations')
    print(f'  !close         - Close the browser window')
    print(f'  !skip          - Skip current citation')
    print(f'  !help          - Show help message')
    print()
    print(f'💡 CITATION DETECTION:')
    print(f'   - Bot auto-detects most citation formats')
    print(f'   - If detection fails, use: !add <your citation>')
    print()
    # Sync slash commands (guild-scoped if DISCORD_GUILD_ID is set, else global)
    try:
        if DISCORD_GUILD_ID_ENV:
            guild = discord.Object(id=int(DISCORD_GUILD_ID_ENV))
            # 1) Copy current global commands to the guild scope (so they exist in guild)
            try:
                await tree.copy_global_to(guild=guild)
            except Exception:
                pass
            # 2) Purge global commands to avoid duplicates in clients that show both global+guild
            try:
                tree.clear_commands(guild=None)
                await tree.sync()  # apply global purge
                LOG.info('Purged global slash commands to avoid duplicates')
            except Exception:
                pass
            # 3) Sync to the guild only
            await tree.sync(guild=guild)
            LOG.info(f'Slash commands synced to guild {DISCORD_GUILD_ID_ENV}')
            print(f'✅ Slash commands registered for guild: {DISCORD_GUILD_ID_ENV} (global commands purged)')
        else:
            await tree.sync()
            LOG.info('Slash commands synced globally')
            print('✅ Slash commands registered globally (may take up to 1 minute to appear)')
    except Exception as e:
        LOG.warn(f'Slash command sync failed: {e}')
        print('⚠️ Slash command sync failed; try setting DISCORD_GUILD_ID and using !resync')

    # Start background watcher for local control signals (from launcher UI)
    try:
        asyncio.create_task(watch_control_signals())
        LOG.info('Control signal watcher started')
    except Exception as e:
        LOG.warn(f'Failed to start control watcher: {e}')


async def on_message(message):
    if message.author == client.user:
        return

    # Only process messages in the designated citation channel (if specified)
    if CITATION_CHANNEL_ID and str(message.channel.id) != CITATION_CHANNEL_ID:
        return

    channel_id = message.channel.id
    content = message.content.strip()

    # Handle commands
    if content.startswith('!'):
        await handle_command(message, content)
        return

    # Skip empty messages
    if not content:
        return

    LOG.debug(f"Message: {content[:80]}…")

    # Smart citation detection - be VERY inclusive
    # Accept anything that looks like it could be academic/scholarly text
    import re

    # Basic checks
    has_period = '.' in content
    has_comma = ',' in content
    has_year = bool(re.search(r'\\b(19|20)\\d{2}\\b', content))
    has_capital = bool(re.search(r'[A-Z]', content))
    is_long_enough = len(content.strip()) > 20

    # Check for common citation patterns
    has_author_pattern = bool(re.search(r'\\b[A-Z][a-z]+,\\s*[A-Z]\\.?', content))  # Smith, J.
    has_parentheses = '(' in content and ')' in content

    # Academic/scholarly keywords (very broad)
    academic_keywords = [
        'university', 'college', 'institute', 'academy', 'school',
        'dept', 'department', 'faculty', 'division',
        'journal', 'proceedings', 'conference', 'symposium', 'meeting',
        'workshop', 'seminar', 'congress', 'summit',
        'presented', 'published', 'edited', 'vol', 'pp', 'doi',
        'research', 'study', 'analysis', 'investigation',
        'et al', 'eds', 'ed.', 'vol.', 'no.', 'issue',
        'january', 'february', 'march', 'april', 'may', 'june',
        'july', 'august', 'september', 'october', 'november', 'december',
        'spring', 'summer', 'fall', 'winter', 'quarterly',
        'press', 'publisher', 'publication', 'edition'
    ]

    content_lower = content.lower()
    has_academic_keyword = any(keyword in content_lower for keyword in academic_keywords)

    # Be VERY liberal - accept if ANY of these conditions are met:
    is_citation = (
        # Has year + period + comma (most citations)
        (has_year and has_period and has_comma) or
        # Has academic keywords
        has_academic_keyword or
        # Has author pattern (Last, F.)
        has_author_pattern or
        # Has parentheses + year (citation style)
        (has_parentheses and has_year) or
        # Long text with capitals and punctuation (likely academic)
        (is_long_enough and has_capital and has_period and len(content) > 50)
    )

    if not is_citation:
        print(f"⏭️  Message doesn't look like a citation")
        print(f"     Tip: Add it anyway with: !add {content[:30]}...")
        return

    LOG.info("Citation detected")

    # Check if message contains multiple citations (separated by blank lines or double newlines)
    # Split on double newlines or single newlines with enough spacing
    potential_citations = []

    # Try splitting by double newlines first
    if '\\n\\n' in content:
        potential_citations = [c.strip() for c in content.split('\\n\\n') if c.strip()]
        LOG.debug(f"Detected {len(potential_citations)} potential citations (double newline)")
    # Try splitting by single newlines if lines are long enough
    elif '\\n' in content:
        lines = content.split('\\n')
        current_citation = []
        for line in lines:
            line = line.strip()
            if not line:  # Empty line - citation boundary
                if current_citation:
                    potential_citations.append(' '.join(current_citation))
                    current_citation = []
            else:
                current_citation.append(line)
        # Add last citation
        if current_citation:
            potential_citations.append(' '.join(current_citation))

        # Only consider it multi-citation if we found more than 1
        if len(potential_citations) > 1:
            LOG.debug(f"Detected {len(potential_citations)} potential citations (newline)")
        else:
            potential_citations = [content]  # Treat as single citation
    else:
        potential_citations = [content]  # Single citation

    valid_citations = [c for c in potential_citations if len(c) > 30]

    if len(valid_citations) == 0:
        valid_citations = [content]  # Fall back to original

    # Add all citations to queue
    queue = get_queue(channel_id)
    added_count = 0

    import time, re
    for citation_text in valid_citations:
        # Validate citation text before processing
        is_valid, error_msg = validate_citation_text(citation_text)
        if not is_valid:
            LOG.warn(f"[{channel_id}] Skipping invalid citation: {error_msg}")
            continue

        # Sanitize the citation text
        citation_text = sanitize_text(citation_text, max_length=5000)

        # Detect explicit tag override (--pos|--pres|--proc)
        citation_lower = citation_text.lower()
        m_tag = re.search(r"\s--(pos|pres|proc)\b", citation_lower)
        forced_type = None
        if m_tag:
            tag = m_tag.group(1)
            if tag == 'pos':
                forced_type = 'poster'
            elif tag == 'pres':
                forced_type = 'presentation'
            elif tag == 'proc':
                forced_type = 'proceedings'

        # Strip helper tags from the text before parsing/queueing
        citation_text = re.sub(r"\s--(pos|pres|proc)\b", "", citation_text, flags=re.I)
        citation_text = re.sub(r"\(\s*pos\s*\)", "", citation_text, flags=re.I)

        # Resolve asset type by precedence: explicit tag > config override > auto-detect
        current_asset_mode = config.get('asset_mode', 'auto')
        if forced_type in ("poster", "presentation", "book_chapter", "journal_article", "proceedings", "abstract", "technical_documentation"):
            asset_type = forced_type
        elif current_asset_mode in ("poster", "presentation", "book_chapter", "journal_article", "proceedings", "abstract", "technical_documentation"):
            asset_type = current_asset_mode
        else:
            # Auto-detect poster keywords if no overrides
            if ('poster presentation' in citation_lower
                or 'poster' in citation_lower
                or '(pos)' in citation_lower
                or '--pos' in citation_lower):
                asset_type = "poster"
            else:
                asset_type = "presentation"

        if asset_type == "poster":
            asset_display = "Conference Poster"
        elif asset_type == "book_chapter":
            asset_display = "Book Chapter"
        elif asset_type == "proceedings":
            asset_display = "Conference Proceedings"
        elif asset_type == "abstract":
            asset_display = "Abstract"
        elif asset_type == "technical_documentation":
            asset_display = "Technical Documentation"
        else:
            asset_display = "Conference Presentation"

        # Create unique citation ID (timestamp + index)
        citation_id = f"{message.id}_{int(time.time() * 1000)}_{added_count}"

        citation_data = {
            'text': citation_text,
            'asset_type': asset_type,
            'message_id': message.id,
            'citation_id': citation_id,
            'author': str(message.author),
            'researcher': config.get('default_researcher')
        }
        queue.append(citation_data)
        # Stats
        try:
            config['stats']['enqueued'] += 1
            save_config(config)
        except Exception:
            pass
        added_count += 1
        LOG.info(f"Queued {added_count} [{asset_display}] {citation_text[:60]}…")
        time.sleep(0.001)  # Ensure unique timestamps

        # Kick off background pre-parse to speed up !f (use automation wrapper)
        try:
            from automation.presentations import parse_any_citation as _pre_parse
            loop = asyncio.get_event_loop()
            async def _do_preparse(ref_dict, text):
                try:
                    data = await loop.run_in_executor(None, _pre_parse, text)
                    if isinstance(data, dict) and data and 'error' not in data:
                        ref_dict['parsed'] = data
                except Exception:
                    pass
            asyncio.create_task(_do_preparse(citation_data, citation_text))
        except Exception:
            pass

    # React to show it was added
    await message.add_reaction('📋')

    # Send appropriate reply based on single vs multiple
    if added_count == 1:
        queue_position = len(queue)
        await message.reply(
            f"✅ **Citation added to queue!**\\n\\n"
            f"📊 **Queue position:** {queue_position}\\n"
            f"📋 **Asset type:** {asset_type.title()}\\n\\n"
            f"Use `!f` to fill the next citation (browser stays open)."
        )
    else:
        queue_start = len(queue) - added_count + 1
        queue_end = len(queue)
        await message.reply(
            f"✅ **{added_count} citations added to queue!**\\n\\n"
            f"📊 **Queue positions:** {queue_start}-{queue_end}\\n"
            f"📋 **Asset type:** {asset_type.title()}\\n\\n"
            f"Use `!f` to fill citations one at a time (browser stays open)."
        )

    LOG.info(f"Queue size now {len(queue)}")


# ============================================================================
# Command Handler Functions (extracted for clarity)
# ============================================================================

async def _cmd_resync(message) -> None:
    """Handle !resync command - sync slash commands."""
    try:
        if DISCORD_GUILD_ID_ENV:
            guild = discord.Object(id=int(DISCORD_GUILD_ID_ENV))
            try:
                await tree.copy_global_to(guild=guild)
            except Exception:
                pass
            try:
                tree.clear_commands(guild=None)
                await tree.sync()
            except Exception:
                pass
            await tree.sync(guild=guild)
            await message.reply(f"✅ Slash commands synced to guild {DISCORD_GUILD_ID_ENV} (global commands purged)")
        else:
            await tree.sync()
            await message.reply("✅ Slash commands synced globally (may take up to 1 minute)")
    except Exception as e:
        await message.reply(f"⚠️ Resync failed: {e}\nTip: set DISCORD_GUILD_ID in .env for faster registration")


async def _cmd_pause(message) -> None:
    """Handle !pause command."""
    global config
    if not config.get('paused'):
        config['paused'] = True
        save_config(config)
    await message.reply("⏸️ Bot paused. Use !resume to continue.")


async def _cmd_resume(message) -> None:
    """Handle !resume command."""
    global config
    if config.get('paused'):
        config['paused'] = False
        save_config(config)
    await message.reply("▶️ Bot resumed. Use !f to fill next citation.")


async def _cmd_stats(message, channel_id: int) -> None:
    """Handle !stats command."""
    qlen = len(get_queue(channel_id))
    st = config.get('stats', {})
    pid = None
    if channel_id in active_processes and active_processes[channel_id].poll() is None:
        pid = active_processes[channel_id].pid
    msg = (
        f"📊 Stats\n\n"
        f"Queue: {qlen}\n"
        f"Processed: {st.get('processed', 0)}\n"
        f"Enqueued: {st.get('enqueued', 0)}\n"
        f"Errors: {st.get('errors', 0)}\n"
        f"Paused: {config.get('paused')}\n"
        f"Browser PID: {pid if pid else '—'}\n"
        f"Researcher: {config.get('default_researcher')}\n"
        f"Type mode: {config.get('asset_mode')}\n"
    )
    await message.reply(msg)


async def _cmd_set(message, content: str) -> None:
    """Handle !set command for researcher and type settings."""
    global config
    try:
        parts = content.split(None, 2)
        if len(parts) < 3:
            await message.reply("❌ Usage: !set researcher \"Last, First\" | !set researcher reset | !set type presentation|poster|auto|reset")
            return

        subcmd = parts[1].lower()
        arg = parts[2].strip().strip('"')

        if subcmd == 'researcher':
            await _cmd_set_researcher(message, arg)
        elif subcmd == 'type':
            await _cmd_set_type(message, arg)
        else:
            await message.reply("❌ Unknown setting. Use: researcher | type")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")


async def _cmd_set_researcher(message, arg: str) -> None:
    """Handle !set researcher subcommand."""
    global config
    if arg.lower() == 'reset':
        default_r = _default_config().get('default_researcher')
        config['default_researcher'] = default_r
        save_config(config)
        await message.reply(f"✅ Researcher reset to: {default_r}")
    else:
        if not arg:
            await message.reply("❌ Provide a researcher: !set researcher \"Last, First\"")
            return

        # Validate researcher name
        is_valid, error_msg = validate_researcher_name(arg)
        if not is_valid:
            await message.reply(f"❌ Invalid researcher name: {error_msg}")
            LOG.warn(f"Rejected invalid researcher name: {arg} - {error_msg}")
            return

        # Sanitize the name
        researcher_name = sanitize_text(arg, max_length=200)

        config['default_researcher'] = researcher_name
        save_config(config)
        await message.reply(f"✅ Researcher set to: {researcher_name}")


async def _cmd_set_type(message, arg: str) -> None:
    """Handle !set type subcommand."""
    global config
    if arg.lower() == 'reset':
        config['asset_mode'] = 'auto'
        save_config(config)
        await message.reply("✅ Asset type mode reset to: auto")
    else:
        # Normalize type name
        normalized_arg = arg.lower().replace(' ', '_')
        if normalized_arg in ('book_chapter', 'bookchapter'):
            normalized_arg = 'book_chapter'
        if normalized_arg in ('journal', 'journal_article', 'journal article'):
            normalized_arg = 'journal_article'
        if normalized_arg in ('proceeding', 'conference_proceeding', 'conference_proceedings'):
            normalized_arg = 'proceedings'

        if normalized_arg not in ('auto', 'presentation', 'poster', 'book_chapter', 'journal_article', 'proceedings', 'abstract', 'technical_documentation'):
            await message.reply("❌ Type must be one of: auto | presentation | poster | book_chapter | journal_article | proceedings | abstract | technical_documentation | reset")
            return

        config['asset_mode'] = normalized_arg
        save_config(config)
        config = load_config()  # Reload to ensure sync
        LOG.info(f"Asset mode set via !set command to: {normalized_arg}")
        await message.reply(f"✅ Asset type mode set to: {config['asset_mode']}")


async def _cmd_help(message) -> None:
    """Handle !help command."""
    help_msg = (
        "📚 **Smart Batch Citation Bot Commands**\n\n"
        "**Commands:**\n"
        "`!f` or `!fill` - Fill next citation (browser stays open)\n"
        "`!resync` - Force slash commands to sync (useful if they don't show)\n"
        "`!add <text>` - Manually add a citation (if auto-detect fails)\n"
        "`!queue` - Show all queued citations\n"
        "`!close` - Close the browser window\n"
        "`!clear` - Clear all queued citations\n"
        "`!skip` - Skip current citation\n"
        "`!pause` / `!resume` - Pause or resume the bot\n"
        "`!stats` - Show queue and processing stats\n"
        "`!set researcher \"Last, First\"` - Set default researcher\n"
        "`!set researcher reset` - Reset researcher to default\n"
        "`!set type presentation|poster|book_chapter|journal_article|proceedings|abstract|technical_documentation|auto` - Set asset type mode\n"
        "`!set type reset` - Reset type mode to auto\n\n"
        "**Workflow:**\n"
        "1. Send citations (they'll be auto-queued)\n"
        "   💡 **Tip:** Send multiple citations in one message!\n"
        "   Separate with blank lines or paste them together.\n"
        "2. Use `!f` - browser opens and logs in\n"
        "3. **YOU manually** click 'Deposit Asset', select researcher/type, click 'Next'\n"
        "4. Form auto-fills with citation data!\n"
        "5. Review and submit\n"
        "6. **YOU manually** click 'Deposit Asset' again for next one\n"
        "7. Use `!f` - fills next citation\n"
        "8. Repeat until done\n"
        "9. Use `!close` when finished\n\n"
        "**Benefits:** You control navigation, bot fills data!\n"
    )
    await message.reply(help_msg)


async def _cmd_queue(message, channel_id: int) -> None:
    """Handle !queue command."""
    queue = get_queue(channel_id)

    if not queue:
        await message.reply("📭 **Queue is empty!** Send some citations to get started.")
        return

    queue_msg = f"📋 **Citation Queue ({len(queue)} items)**\n\n"
    for i, citation in enumerate(queue, 1):
        citation_preview = citation['text'][:60] + ('...' if len(citation['text']) > 60 else '')
        queue_msg += f"**{i}.** {citation['asset_type'].title()}\n"
        queue_msg += f"   {citation_preview}\n\n"

    queue_msg += f"Use `!f` to fill the next citation."
    await message.reply(queue_msg)


async def _cmd_clear(message, channel_id: int) -> None:
    """Handle !clear command."""
    queue = get_queue(channel_id)
    count = len(queue)
    queue.clear()

    if channel_id in processing_citations:
        del processing_citations[channel_id]

    await message.reply(f"🗑️ **Queue cleared!** Removed {count} citation(s).")
    LOG.info(f"Queue cleared for channel {channel_id}")


async def _cmd_skip(message, channel_id: int) -> None:
    """Handle !skip command."""
    if channel_id in processing_citations:
        citation = processing_citations[channel_id]
        del processing_citations[channel_id]
        await message.reply(f"⏭️ **Skipped current citation.**\nUse `!f` to process the next one.")
        print(f"⏭️ Skipped citation in channel {channel_id}")
    else:
        await message.reply("⚠️ **No citation is currently being processed.**")


async def _cmd_close(message, channel_id: int) -> None:
    """Handle !close command."""
    if channel_id in active_processes:
        process = active_processes[channel_id]
        try:
            print(f"🔴 Closing browser (PID: {process.pid})...")
            process.terminate()
            await asyncio.sleep(2)
            if process.poll() is None:
                process.kill()
            del active_processes[channel_id]
            await message.reply("🔴 **Browser closed!**")
            print(f"✓ Browser closed for channel {channel_id}")
        except Exception as e:
            LOG.error(f"Error closing browser: {e}")
            await message.reply(f"⚠️ **Error closing browser:** {str(e)}")
    else:
        await message.reply("⚠️ **No browser is currently open.**")


async def _cmd_add(message, content: str, channel_id: int) -> None:
    """Handle !add command - manually add a citation."""
    import re, time

    citation_text = content[len('!add'):].strip()
    if not citation_text:
        await message.reply("❌ **Usage:** `!add <citation text>`\n\nExample: `!add Smith, J. (2024). My Paper. Conference.`")
        return

    queue = get_queue(channel_id)

    # Determine asset type with tag/override precedence
    citation_lower = citation_text.lower()
    m_tag = re.search(r"\s--(pos|pres|proc)\b", citation_lower)
    forced_type = None
    if m_tag:
        tag = m_tag.group(1)
        if tag == 'pos': forced_type = 'poster'
        elif tag == 'pres': forced_type = 'presentation'
        elif tag == 'proc': forced_type = 'proceedings'

    # Strip helper tags
    citation_text = re.sub(r"\s--(pos|pres|proc)\b", "", citation_text, flags=re.I)
    citation_text = re.sub(r"\(\s*pos\s*\)", "", citation_text, flags=re.I)

    # Resolve type
    if forced_type in ("poster", "presentation", "book_chapter", "journal_article", "proceedings", "abstract", "technical_documentation"):
        asset_type = forced_type
    elif config.get('asset_mode') in ("poster", "presentation", "book_chapter", "journal_article", "proceedings", "abstract", "technical_documentation"):
        asset_type = config.get('asset_mode')
    else:
        asset_type = "poster" if ('poster presentation' in citation_lower or 'poster' in citation_lower or '(pos)' in citation_lower or '--pos' in citation_lower) else "presentation"

    citation_id = f"{message.id}_{int(time.time() * 1000)}_manual"
    citation_data = {
        'text': citation_text,
        'asset_type': asset_type,
        'message_id': message.id,
        'citation_id': citation_id,
        'author': str(message.author),
        'researcher': config.get('default_researcher')
    }

    queue.append(citation_data)
    try:
        config['stats']['enqueued'] += 1
        save_config(config)
    except Exception:
        pass

    await message.add_reaction('📋')
    queue_position = len(queue)
    await message.reply(
        f"✅ **Citation added to queue!**\n\n"
        f"📊 **Queue position:** {queue_position}\n"
        f"📋 **Asset type:** {asset_type.title()}\n\n"
        f"Use `!f` to fill the next citation."
    )
    LOG.info(f"Manually added citation (type: {asset_type})")


# ============================================================================
# Main Command Router
# ============================================================================

async def handle_command(message, content):
    """Handle bot commands - routes to specific command handlers."""
    global config
    channel_id = message.channel.id
    command = content.lower().split()[0]

    # Command dispatch table
    command_handlers = {
        '!resync': lambda: _cmd_resync(message),
        '!pause': lambda: _cmd_pause(message),
        '!resume': lambda: _cmd_resume(message),
        '!stats': lambda: _cmd_stats(message, channel_id),
        '!set': lambda: _cmd_set(message, content),
        '!help': lambda: _cmd_help(message),
        '!queue': lambda: _cmd_queue(message, channel_id),
        '!clear': lambda: _cmd_clear(message, channel_id),
        '!skip': lambda: _cmd_skip(message, channel_id),
        '!close': lambda: _cmd_close(message, channel_id),
        '!add': lambda: _cmd_add(message, content, channel_id),
    }

    handler = command_handlers.get(command)
    if handler:
        await handler()
        return

    # Handle !f and !fill commands (they have more complex logic)
    if command in ['!f', '!fill']:
        if config.get('paused'):
            await message.reply("⏸️ Bot is paused. Use !resume to continue.")
            return
        queue = get_queue(channel_id)

        if not queue:
            await message.reply(
                "📭 **Queue is empty!**\n\n"
                "Send some citations to get started. They'll be automatically added to the queue."
            )
            return

        # Get next citation
        citation = queue.popleft()
        processing_citations[channel_id] = citation

        remaining = len(queue)

        # Check if browser is already open
        browser_already_open = channel_id in active_processes and active_processes[channel_id].poll() is None

        if browser_already_open:
            await message.reply(
                f"📝 **Filling next citation...**\n\n"
                f"📋 **Asset type:** {citation['asset_type'].title()}\n"
                f"📊 **Remaining in queue:** {remaining}\n\n"
                f"Make sure you're on the deposit form page!"
            )
        else:
            await message.reply(
                f"🌐 **Opening browser...**\n\n"
                f"📋 **Asset type:** {citation['asset_type'].title()}\n"
                f"📊 **Remaining in queue:** {remaining}\n\n"
                f"**Next steps:**\n"
                f"1. Browser will open and log in\n"
                f"2. Manually click 'Deposit Asset'\n"
                f"3. Select researcher and asset type\n"
                f"4. Click 'Next' to get to form\n"
                f"5. Form will auto-fill with citation data!"
            )

        LOG.info(f"Filling: {citation['text'][:80]}… | type={citation['asset_type']} | remaining={remaining} | browser_open={browser_already_open}")

        # Process the citation
        try:
            await fill_citation(message, citation, channel_id)
            try:
                config['stats']['processed'] += 1
                save_config(config)
            except Exception:
                pass
        except Exception as e:
            try:
                config['stats']['errors'] += 1
                save_config(config)
            except Exception:
                pass
            raise

        # Suppress extra completion chatter; a single field summary will be posted by fill_citation()
        if remaining == 0:
            # Optional minimal notification when queue becomes empty
            try:
                await message.channel.send("✅ All queued citations processed.")
            except Exception:
                pass

        return


# --------------------
# Slash commands
# --------------------

@tree.command(name="help", description="Show Smart Batch bot help")
async def slash_help(interaction: discord.Interaction):
    await interaction.response.send_message(
        "📚 **Smart Batch Citation Bot Commands**\n\n"
        "**Slash Commands:**\n"
        "/fill - Fill next citation (browser stays open)\n"
        "/resync - Force re-sync of slash commands\n"
        "/add text:<citation> [type_mode] - Add a citation (optional forced type)\n"
        "/queue - Show queued citations\n"
        "/clear - Clear all queued citations\n"
        "/close - Close the browser window\n"
        "/skip - Skip current citation\n"
        "/pause /resume - Pause or resume\n"
        "/stats - Show stats\n"
        "/set_type - Set asset type mode (dropdown)\n"
        "/set_researcher name:<Last, First> - Set default researcher\n"
        "/set_additional_topic topic:<text> - Add a 'Description and Research' topic (max 6)\n"
        "/clear_additional_topics - Clear all additional topics for this channel\n\n"
        "You can still use the text commands starting with ! as well.")


@tree.command(name="stats", description="Show queue and processing stats")
async def slash_stats(interaction: discord.Interaction):
    channel_id = interaction.channel.id
    qlen = len(get_queue(channel_id))
    st = config.get('stats', {})
    pid = None
    if channel_id in active_processes and active_processes[channel_id].poll() is None:
        pid = active_processes[channel_id].pid
    msg = (
        f"📊 Stats\n\n"
        f"Queue: {qlen}\n"
        f"Processed: {st.get('processed', 0)}\n"
        f"Enqueued: {st.get('enqueued', 0)}\n"
        f"Errors: {st.get('errors', 0)}\n"
        f"Paused: {config.get('paused')}\n"
        f"Browser PID: {pid if pid else '—'}\n"
        f"Researcher: {config.get('default_researcher')}\n"
        f"Type mode: {config.get('asset_mode')}\n"
    )
    await interaction.response.send_message(msg)


@tree.command(name="pause", description="Pause the bot")
async def slash_pause(interaction: discord.Interaction):
    config['paused'] = True
    save_config(config)
    await interaction.response.send_message("⏸️ Bot paused. Use /resume to continue.")


@tree.command(name="resume", description="Resume the bot")
async def slash_resume(interaction: discord.Interaction):
    config['paused'] = False
    save_config(config)
    await interaction.response.send_message("▶️ Bot resumed. Use /fill to fill next citation.")


@tree.command(name="queue", description="Show queued citations")
async def slash_queue(interaction: discord.Interaction):
    try:
        # Defer immediately to avoid timeout
        try:
            await interaction.response.defer()
        except Exception:
            # Already responded or timed out
            pass

        queue = get_queue(interaction.channel.id)
        if not queue:
            try:
                await interaction.followup.send("📭 **Queue is empty!** Send some citations to get started.")
            except Exception:
                pass
            return

        queue_msg = f"📋 **Citation Queue ({len(queue)} items)**\n\n"
        for i, citation in enumerate(queue, 1):
            citation_preview = citation['text'][:60] + ('...' if len(citation['text']) > 60 else '')
            queue_msg += f"**{i}.** {citation['asset_type'].title()}\n   {citation_preview}\n\n"
        queue_msg += f"Use /fill to fill the next citation."

        try:
            await interaction.followup.send(queue_msg)
        except Exception:
            # Interaction expired or channel unavailable
            pass
    except Exception as e:
        LOG.warn(f"Error in slash_queue: {e}")
        try:
            await interaction.followup.send("⚠️ Error retrieving queue. Please try again.")
        except Exception:
            pass


@tree.command(name="clear", description="Clear all queued citations")
async def slash_clear(interaction: discord.Interaction):
    queue = get_queue(interaction.channel.id)
    count = len(queue)
    queue.clear()
    if interaction.channel.id in processing_citations:
        del processing_citations[interaction.channel.id]
    await interaction.response.send_message(f"🗑️ **Queue cleared!** Removed {count} citation(s).")


@tree.command(name="close", description="Close the browser window")
async def slash_close(interaction: discord.Interaction):
    channel_id = interaction.channel.id
    if channel_id in active_processes:
        process = active_processes[channel_id]
        try:
            process.terminate()
            await asyncio.sleep(2)
            if process.poll() is None:
                process.kill()
            del active_processes[channel_id]
            await interaction.response.send_message("🔴 **Browser closed!**")
        except Exception as e:
            await interaction.response.send_message(f"⚠️ **Error closing browser:** {str(e)}")
    else:
        await interaction.response.send_message("⚠️ **No browser is currently open.**")


@tree.command(name="skip", description="Skip current citation")
async def slash_skip(interaction: discord.Interaction):
    channel_id = interaction.channel.id
    if channel_id in processing_citations:
        del processing_citations[channel_id]
        await interaction.response.send_message("⏭️ **Skipped current citation.** Use /fill to process the next one.")
    else:
        await interaction.response.send_message("⚠️ **No citation is currently being processed.**")


@tree.command(name="set_type", description="Set asset type mode")
@app_commands.choices(mode=[
    app_commands.Choice(name="Auto", value="auto"),
    app_commands.Choice(name="Presentation", value="presentation"),
    app_commands.Choice(name="Conference Poster", value="poster"),
    app_commands.Choice(name="Book Chapter", value="book_chapter"),
    app_commands.Choice(name="Journal Article", value="journal_article"),
    app_commands.Choice(name="Proceedings", value="proceedings"),
    app_commands.Choice(name="Abstract", value="abstract"),
    app_commands.Choice(name="Technical Documentation", value="technical_documentation"),
    app_commands.Choice(name="Reset", value="reset"),
])
async def slash_set_type(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    val = mode.value
    if val == 'reset':
        val = 'auto'
    # Normalize using shared utility
    normalized = normalize_config_mode(val)
    config['asset_mode'] = normalized
    save_config(config)
    await interaction.response.send_message(f"✅ Asset type mode set to: {normalized}")


# Helper function to get researcher choices dynamically
def _get_researcher_choices() -> List[app_commands.Choice[str]]:
    """Generate researcher choices from config. Called at command invocation time."""
    known = config.get('known_researchers', [])
    choices = []
    # Add "reset" option first
    choices.append(app_commands.Choice(name="🔄 Reset to default", value="reset"))
    # Add "new" option to add a new researcher
    choices.append(app_commands.Choice(name="➕ Add new researcher...", value="__new__"))
    # Add all known researchers (limit to 23 to leave room for reset + new + current)
    for r in known[:23]:
        if r and r not in ["reset", "__new__"]:
            choices.append(app_commands.Choice(name=r, value=r))
    return choices


@tree.command(name="set_researcher", description="Set default researcher (Last, First)")
async def slash_set_researcher_dropdown(interaction: discord.Interaction):
    """Show researcher selection with dynamic dropdown."""
    choices = _get_researcher_choices()

    # Create a simple view with a select menu
    class ResearcherSelect(discord.ui.Select):
        def __init__(self):
            options = [
                discord.SelectOption(label=choice.name, value=choice.value)
                for choice in choices
            ]
            super().__init__(placeholder="Select a researcher...", options=options, min_values=1, max_values=1)

        async def callback(self, interaction: discord.Interaction):
            selected = self.values[0]

            if selected == "reset":
                default_r = _default_config().get('default_researcher')
                config['default_researcher'] = default_r
                save_config(config)
                await interaction.response.send_message(f"✅ Researcher reset to: {default_r}", ephemeral=True)
            elif selected == "__new__":
                # Show modal for entering new researcher
                class NewResearcherModal(discord.ui.Modal, title="Add New Researcher"):
                    researcher_name = discord.ui.TextInput(
                        label="Researcher Name",
                        placeholder="Last, First Middle",
                        style=discord.TextStyle.short,
                        required=True,
                        max_length=100
                    )

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        new_name = self.researcher_name.value.strip()
                        if not new_name:
                            await modal_interaction.response.send_message("❌ Name cannot be empty", ephemeral=True)
                            return

                        # Validate researcher name
                        is_valid, error_msg = validate_researcher_name(new_name)
                        if not is_valid:
                            await modal_interaction.response.send_message(
                                f"❌ Invalid researcher name: {error_msg}",
                                ephemeral=True
                            )
                            LOG.warn(f"Rejected invalid researcher name: {new_name} - {error_msg}")
                            return

                        # Sanitize the name
                        new_name = sanitize_text(new_name, max_length=200)

                        # Add to known researchers if not already there
                        known = config.get('known_researchers', [])
                        if new_name not in known:
                            known.append(new_name)
                            config['known_researchers'] = known

                        config['default_researcher'] = new_name
                        save_config(config)
                        await modal_interaction.response.send_message(
                            f"✅ Researcher added and set to: {new_name}\n"
                            f"📋 Total researchers in list: {len(known)}",
                            ephemeral=True
                        )

                await interaction.response.send_modal(NewResearcherModal())
            else:
                config['default_researcher'] = selected
                save_config(config)
                await interaction.response.send_message(f"✅ Researcher set to: {selected}", ephemeral=True)

    class ResearcherView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)  # 3 minute timeout
            self.add_item(ResearcherSelect())

    await interaction.response.send_message(
        f"**Select Researcher**\nCurrent: {config.get('default_researcher', 'Not set')}",
        view=ResearcherView(),
        ephemeral=True
    )


@tree.command(name="add", description="Manually add a citation to the queue")
@app_commands.describe(text="Citation text")
@app_commands.choices(type_mode=[
    app_commands.Choice(name="Auto", value="auto"),
    app_commands.Choice(name="Presentation", value="presentation"),
    app_commands.Choice(name="Conference Poster", value="poster"),
    app_commands.Choice(name="Book Chapter", value="book_chapter"),
    app_commands.Choice(name="Journal Article", value="journal_article"),
    app_commands.Choice(name="Proceedings", value="proceedings"),
    app_commands.Choice(name="Abstract", value="abstract"),
    app_commands.Choice(name="Technical Documentation", value="technical_documentation"),
])
async def slash_add(interaction: discord.Interaction, text: str, type_mode: Optional[app_commands.Choice[str]] = None):
    channel_id = interaction.channel.id
    queue = get_queue(channel_id)
    citation_text = (text or '').strip()
    if not citation_text:
        await interaction.response.send_message("❌ Provide citation text")
        return
    forced_type = None
    if type_mode and type_mode.value in ("presentation", "poster", "book_chapter", "journal_article", "proceedings", "abstract", "technical_documentation"):
        forced_type = type_mode.value
    citation_lower = citation_text.lower()
    if forced_type:
        asset_type = forced_type
    elif config.get('asset_mode') in ("poster", "presentation", "book_chapter", "journal_article", "proceedings", "abstract", "technical_documentation"):
        asset_type = config.get('asset_mode')
    else:
        asset_type = "poster" if ('poster presentation' in citation_lower or 'poster' in citation_lower or '(pos)' in citation_lower or '--pos' in citation_lower) else "presentation"
    import time
    citation_id = f"{interaction.id}_{int(time.time() * 1000)}_manual"
    citation_data = {
        'text': citation_text,
        'asset_type': asset_type,
        'message_id': interaction.id,
        'citation_id': citation_id,
        'author': str(interaction.user),
        'researcher': config.get('default_researcher')
    }
    queue.append(citation_data)
    try:
        config['stats']['enqueued'] += 1
        save_config(config)
    except Exception:
        pass
    await interaction.response.send_message(
        f"✅ **Citation manually added to queue!**\n\n"
        f"📊 **Queue position:** {len(queue)}\n"
        f"📋 **Asset type:** {asset_type.title()}\n\n"
        f"Use /fill to fill this citation.")


@tree.command(name="set_additional_topic", description="Add a 'Description and Research' topic for this channel (max 6)")
@app_commands.describe(topic="Topic text to add")
async def slash_set_additional_topic(interaction: discord.Interaction, topic: str):
    # Always ack quickly to avoid timeout
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        pass
    try:
        t = (topic or "").strip()
        if not t:
            await interaction.followup.send("❌ Provide a topic string.")
            return
        # Load config
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = load_config()
        topics_by_channel = cfg.setdefault("additional_topics", {})
        cid = str(interaction.channel.id)
        lst = topics_by_channel.get(cid) or []
        # De-duplicate, preserve order
        if t in lst:
            await interaction.followup.send(f"ℹ️ Topic already set. Current: {', '.join(lst) if lst else '—'}")
            return
        if len(lst) >= 6:
            await interaction.followup.send(f"❌ You already have 6 topics set: {', '.join(lst)}. Use /clear_additional_topics first.")
            return
        lst.append(t)
        topics_by_channel[cid] = lst
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            save_config(cfg)
        # Keep in-memory config in sync to avoid being overwritten later
        try:
            global config
            if isinstance(config, dict):
                config.setdefault("additional_topics", {})
                config["additional_topics"][cid] = lst
        except Exception:
            pass
        await interaction.followup.send(f"✅ Topic added. Current topics ({len(lst)}/6): {', '.join(lst)}")
    except Exception as e:
        try:
            await interaction.followup.send(f"⚠️ Error: {e}")
        except Exception:
            pass


@tree.command(name="clear_additional_topics", description="Clear all additional topics for this channel")
async def slash_clear_additional_topics(interaction: discord.Interaction):
    # Ack quickly, then work
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        pass
    try:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = load_config()
        topics_by_channel = cfg.setdefault("additional_topics", {})
        cid = str(interaction.channel.id)
        had = list(topics_by_channel.get(cid) or [])
        if cid in topics_by_channel:
            del topics_by_channel[cid]
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            save_config(cfg)
        # Update in-memory config to prevent later overwrites
        try:
            global config
            if isinstance(config, dict) and isinstance(config.get("additional_topics"), dict):
                config["additional_topics"].pop(cid, None)
        except Exception:
            pass
        await interaction.followup.send(f"🗑️ Cleared additional topics. Previous: {', '.join(had) if had else '—'}")
    except Exception as e:
        try:
            await interaction.followup.send(f"⚠️ Error: {e}")
        except Exception:
            pass

@tree.command(name="resync", description="Force re-sync of slash commands")
async def slash_resync(interaction: discord.Interaction):
    try:
        if DISCORD_GUILD_ID_ENV:
            guild = discord.Object(id=int(DISCORD_GUILD_ID_ENV))
            # Copy current globals to guild
            try:
                await tree.copy_global_to(guild=guild)
            except Exception:
                pass
            # Purge global commands to prevent dupes
            try:
                tree.clear_commands(guild=None)
                await tree.sync()
            except Exception:
                pass
            # Sync to guild only
            await tree.sync(guild=guild)
            await interaction.response.send_message(f"✅ Slash commands synced to guild {DISCORD_GUILD_ID_ENV} (global commands purged)")
        else:
            await tree.sync()
            await interaction.response.send_message("✅ Slash commands synced globally (may take up to 1 minute)")
    except Exception as e:
        await interaction.response.send_message(f"⚠️ Resync failed: {e}\nTip: set DISCORD_GUILD_ID in .env for faster registration")


@tree.command(name="fill", description="Fill the next citation in the queue")
async def slash_fill(interaction: discord.Interaction):
    # Defer immediately to avoid interaction timeout
    try:
        await interaction.response.defer()
    except Exception:
        pass
    if config.get('paused'):
        try:
            await interaction.followup.send("⏸️ Bot is paused. Use /resume to continue.")
        except Exception:
            pass
        return
    channel_id = interaction.channel.id
    queue = get_queue(channel_id)
    if not queue:
        try:
            await interaction.followup.send("📭 **Queue is empty!** Send some citations to get started.")
        except Exception:
            pass
        return
    citation = queue.popleft()
    processing_citations[channel_id] = citation
    remaining = len(queue)
    browser_already_open = channel_id in active_processes and active_processes[channel_id].poll() is None
    # Compose a status message and send as a followup (since we already deferred)
    try:
        if browser_already_open:
            msg = (
                f"📝 **Filling next citation...**\n\n"
                f"📋 **Asset type:** {citation['asset_type'].title()}\n"
                f"📊 **Remaining in queue:** {remaining}\n\n"
                f"Make sure you're on the deposit form page!"
            )
        else:
            msg = (
                f"🌐 **Opening browser...**\n\n"
                f"📋 **Asset type:** {citation['asset_type'].title()}\n"
                f"📊 **Remaining in queue:** {remaining}\n\n"
                f"Follow the on-screen steps; the form will auto-fill."
            )
        await interaction.followup.send(msg)
    except Exception:
        pass
    print(f"📝 Filling citation (slash): {citation['text'][:80]}...")
    adapter = _InteractionMessageAdapter(interaction.channel)
    try:
        await fill_citation(adapter, citation, channel_id)
        try:
            config['stats']['processed'] += 1
            save_config(config)
        except Exception:
            pass
    except Exception:
        try:
            config['stats']['errors'] += 1
            save_config(config)
        except Exception:
            pass
        raise
    if remaining == 0:
        try:
            await interaction.followup.send("✅ All queued citations processed.")
        except Exception:
            pass


async def fill_citation(message, citation, channel_id):
    """Fill a citation in the browser (keeps browser open)"""
    try:
        # Create a special script call that writes to a control file
        # The automation worker will pick this up and process it
        import json

        # Always use current config researcher (allows changing researcher without restarting)
        # This ensures that changing the researcher in the GUI affects all future fills
        current_researcher = config.get('default_researcher') or citation.get('researcher') or 'Scarano, Frank J'

        # Write citation to a control file
        control_file = f"citation_control_{channel_id}.json"
        with open(control_file, 'w') as f:
            json.dump({
                'text': citation['text'],
                'asset_type': citation['asset_type'],
                'message_id': citation['message_id'],
                'citation_id': citation.get('citation_id', citation['message_id']),
                'author': citation['author'],
                'researcher': current_researcher,  # Use current config value
                'parsed': citation.get('parsed')
            }, f)

        print(f"📝 Wrote citation to control file: {control_file}")
        status_file = f"citation_status_{channel_id}.json"

        # Check for auto-restart BEFORE processing to ensure we don't exceed the limit in this session
        restart_interval = config.get('auto_restart_interval', 0)
        if restart_interval > 0 and channel_id in process_fill_counts:
            current_fills = process_fill_counts[channel_id]
            # If we've reached the limit, restart now so the NEXT fill (this one) starts with a fresh browser.
            # This interprets "Restart after N" as "Process at most N items per session".
            # Example: Interval=5. Done=5. Restart now. Process #6 (relative total) in new session.
            # Note: The user requested "It shouldn't process the 5th citation" (if set to 5?).
            # If they mean "Restart AT 5", then we should check >= restart_interval - 1?
            # Standard interpretation is "Restart AFTER N". So 1..5 done. 6th gets new browser.
            # We'll stick to >= restart_interval (Max N items).
            if current_fills >= restart_interval:
                print(f"🔄 Auto-restart triggered: {current_fills}/{restart_interval} fills reached. Restarting worker BEFORE processing...")
                if channel_id in active_processes:
                    proc = active_processes[channel_id]
                    try:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                    except Exception:
                        pass
                    if channel_id in active_processes:
                        del active_processes[channel_id]
                    if channel_id in process_fill_counts:
                        process_fill_counts[channel_id] = 0  # Reset
                    print(f"✅ Worker closed for auto-restart. Will respawn immediately.")

        # If browser is not open, start the automation worker
        if channel_id not in active_processes or active_processes[channel_id].poll() is not None:
            print(f"🚀 Starting persistent browser automation worker...")

            # Use sys.executable to ensure we use the same Python interpreter
            # that's running this bot (with all packages installed)
            process = subprocess.Popen([
                sys.executable, '-m', 'automation.worker',
                str(channel_id)
            ], cwd=os.getcwd())

            active_processes[channel_id] = process
            process_fill_counts[channel_id] = 0  # Reset fill count for new process
            print(f"✓ Worker started with Python: {sys.executable} (PID: {process.pid})")

            # Wait for browser to open (short)
            await asyncio.sleep(2)
        else:
            print(f"✓ Using existing browser (PID: {active_processes[channel_id].pid})")
            # Just wait a bit for the new citation to be picked up
            await asyncio.sleep(1)

        # Wait until worker confirms files written for this specific citation
        csv_file = "citationsPresentations.csv"
        summary_file = "filled_fields_summary.txt"
        try:
            # Poll status file for up to ~45 seconds
            for _ in range(45):
                if os.path.exists(status_file):
                    try:
                        with open(status_file, "r", encoding="utf-8") as sf:
                            status = json.load(sf)
                        if status.get("last_written_id") == citation.get("citation_id"):
                            state = status.get("state")
                            if state == "failed":
                                worker_error = status.get("error") or "Citation processing failed"
                                completion_status_path = os.path.join(os.getcwd(), 'gui_completion_status.json')
                                try:
                                    with open(completion_status_path, 'w', encoding='utf-8') as f:
                                        json.dump({
                                            'status': 'failed',
                                            'citation_id': citation.get("citation_id"),
                                            'timestamp': time.time(),
                                            'error': worker_error,
                                            'queue_remaining': len(get_queue(channel_id))
                                        }, f)
                                except Exception:
                                    pass
                                await message.channel.send(f"❌ **Citation failed:** {worker_error}")
                                return
                            if state and state != "completed":
                                await asyncio.sleep(1)
                                continue
                            csv_file = status.get("csv_file") or csv_file
                            summary_file = status.get("summary_file") or summary_file
                            # Update GUI completion status
                            completion_status_path = os.path.join(os.getcwd(), 'gui_completion_status.json')
                            try:
                                with open(completion_status_path, 'w', encoding='utf-8') as f:
                                    json.dump({
                                        'status': 'completed',
                                        'citation_id': citation.get("citation_id"),
                                        'timestamp': time.time(),
                                        'queue_remaining': len(get_queue(channel_id))
                                    }, f)
                            except Exception:
                                pass
                            break
                    except Exception:
                        pass
                await asyncio.sleep(1)
        except Exception:
            pass

        # Post a single clear inline summary message in chat
        try:
            if os.path.exists(summary_file):
                with open(summary_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                # Truncate to keep Discord message readable
                max_chars = 1800
                preview = content[:max_chars]
                if len(content) > max_chars:
                    preview += "\n… (truncated)"
                await message.channel.send(f"```\n{preview}\n```")
        except Exception:
            # Non-fatal if preview fails
            pass

        # Increment process fill count
        if channel_id in process_fill_counts:
            process_fill_counts[channel_id] += 1
        elif channel_id in active_processes:
             process_fill_counts[channel_id] = 1

    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        await message.channel.send(f"❌ **Unexpected error:** {str(e)}")


def main():
    if not BOT_TOKEN:
        print("❌ Please set DISCORD_BOT_TOKEN in your .env file")
        print("Get your bot token from: https://discord.com/developers/applications")
        return

    print("🚀 Starting Discord Citation Bot (SMART BATCH MODE)...")
    print(f"📁 Config file: {CONFIG_PATH}")
    print(f"📺 Channel ID: {CITATION_CHANNEL_ID or 'Not set'}")
    print("📋 Browser stays open between citations!")
    print("🎯 Use !f to fill each citation, !close when done")
    print()

    client.run(BOT_TOKEN)


# --------------------
# External control (launcher UI) support
# --------------------
async def trigger_fill_for_channel(channel_id: int) -> None:
    """Programmatically trigger a fill for the given channel (used by launcher UI)."""
    try:
        queue = get_queue(channel_id)
        if not queue:
            # Optional: notify channel if accessible
            ch = client.get_channel(channel_id)
            if ch:
                try:
                    await ch.send("📭 Queue is empty. Add citations first (use /add or paste).")
                except Exception:
                    pass
            return
        citation = queue.popleft()
        processing_citations[channel_id] = citation
        # Use channel message adapter so fill_citation can post summaries
        channel = client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(channel_id)
            except Exception:
                channel = None
        adapter = _InteractionMessageAdapter(channel) if channel else _InteractionMessageAdapter(client)
        await fill_citation(adapter, citation, channel_id)
        try:
            config['stats']['processed'] += 1
            save_config(config)
        except Exception:
            pass
    except Exception:
        try:
            config['stats']['errors'] += 1
            save_config(config)
        except Exception:
            pass


async def add_citation_via_gui(channel_id: int, citation_text: str) -> dict:
    """Add a citation to the queue from the GUI. Returns status dict."""
    try:
        queue = get_queue(channel_id)

        # Parse citation similar to on_message handler
        import re
        import time
        citation_lower = citation_text.lower()

        # Detect explicit tag override
        m_tag = re.search(r"\s--(pos|pres|proc)\b", citation_lower)
        forced_type = None
        if m_tag:
            tag = m_tag.group(1)
            if tag == 'pos':
                forced_type = 'poster'
            elif tag == 'pres':
                forced_type = 'presentation'
            elif tag == 'proc':
                forced_type = 'proceedings'

        # Strip helper tags
        citation_text = re.sub(r"\s--(pos|pres|proc)\b", "", citation_text, flags=re.I)
        citation_text = re.sub(r"\(\s*pos\s*\)", "", citation_text, flags=re.I)

        # Resolve asset type
        current_asset_mode = config.get('asset_mode', 'auto')
        if forced_type in ("poster", "presentation", "book_chapter", "journal_article", "proceedings", "abstract", "technical_documentation"):
            asset_type = forced_type
        elif current_asset_mode in ("poster", "presentation", "book_chapter", "journal_article", "proceedings", "abstract", "technical_documentation"):
            asset_type = current_asset_mode
        else:
            asset_type = "poster" if ('poster presentation' in citation_lower or 'poster' in citation_lower or '(pos)' in citation_lower or '--pos' in citation_lower) else "presentation"

        citation_id = f"gui_{int(time.time() * 1000)}"
        citation_data = {
            'text': citation_text,
            'asset_type': asset_type,
            'message_id': 0,  # GUI doesn't have a message ID
            'citation_id': citation_id,
            'author': 'GUI User',
            'researcher': config.get('default_researcher')
        }
        queue.append(citation_data)

        # Stats
        try:
            config['stats']['enqueued'] += 1
            save_config(config)
        except Exception:
            pass

        # Pre-parse in background
        try:
            from automation.presentations import parse_any_citation as _pre_parse
            loop = asyncio.get_event_loop()
            async def _do_preparse(ref_dict, text):
                try:
                    data = await loop.run_in_executor(None, _pre_parse, text)
                    if isinstance(data, dict) and data and 'error' not in data:
                        ref_dict['parsed'] = data
                except Exception:
                    pass
            asyncio.create_task(_do_preparse(citation_data, citation_text))
        except Exception:
            pass

        return {
            'success': True,
            'queue_position': len(queue),
            'asset_type': asset_type,
            'citation_id': citation_id
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


async def watch_control_signals() -> None:
    """Watch for control files created by the launcher UI to drive fills or shutdown."""
    global config  # Declare at the top of the function

    control_dir = os.getcwd()
    fill_path = os.path.join(control_dir, 'fill_next_signal')
    shutdown_path = os.path.join(control_dir, 'shutdown_signal')
    add_citation_path = os.path.join(control_dir, 'gui_add_citation.json')
    completion_status_path = os.path.join(control_dir, 'gui_completion_status.json')

    # New GUI control files
    queue_request_path = os.path.join(control_dir, 'gui_queue_request.json')
    queue_response_path = os.path.join(control_dir, 'gui_queue.json')
    clear_queue_path = os.path.join(control_dir, 'gui_clear_queue.json')
    pause_path = os.path.join(control_dir, 'gui_pause.json')
    resume_path = os.path.join(control_dir, 'gui_resume.json')
    skip_path = os.path.join(control_dir, 'gui_skip.json')
    set_researcher_path = os.path.join(control_dir, 'gui_set_researcher.json')
    set_asset_type_path = os.path.join(control_dir, 'gui_set_asset_type.json')
    add_topic_path = os.path.join(control_dir, 'gui_add_topic.json')
    remove_topic_path = os.path.join(control_dir, 'gui_remove_topic.json')
    clear_topics_path = os.path.join(control_dir, 'gui_clear_topics.json')
    toggle_auto_fill_authors_path = os.path.join(control_dir, 'gui_toggle_auto_fill_authors.json')
    set_author_add_delay_path = os.path.join(control_dir, 'gui_set_author_add_delay.json')
    set_restart_policy_path = os.path.join(control_dir, 'gui_set_restart_policy.json')

    last_filled_citation_id = None

    while True:
        try:
            if os.path.exists(shutdown_path):
                try:
                    os.remove(shutdown_path)
                except Exception:
                    pass
                # Close workers first, then the bot gracefully
                try:
                    # Terminate all worker processes
                    for ch, proc in list(active_processes.items()):
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                    await asyncio.sleep(1)
                    # Force kill any that didn't terminate
                    for ch, proc in list(active_processes.items()):
                        try:
                            if proc.poll() is None:
                                proc.kill()
                        except Exception:
                            pass
                    active_processes.clear()

                    # Also kill any worker processes by name (in case they're orphaned)
                    try:
                        import psutil
                        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                            try:
                                cmdline = proc.info.get('cmdline', [])
                                if cmdline and 'automation.worker' in ' '.join(cmdline):
                                    proc.terminate()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                    except ImportError:
                        # psutil not available, use subprocess
                        try:
                            import subprocess as sp
                            sp.run(['pkill', '-TERM', '-f', 'automation.worker'],
                                  timeout=2, capture_output=True)
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    await client.close()
                except Exception:
                    pass
                # Ensure full process exit to clear Discord presence promptly
                try:
                    import os as _os
                    _os._exit(0)
                except Exception:
                    pass

            # Handle toggle auto fill authors request
            if os.path.exists(toggle_auto_fill_authors_path):
                try:
                    with open(toggle_auto_fill_authors_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # Skip if this is already a response (has 'success' key)
                    if 'success' in data:
                        pass  # Already processed, skip
                    else:
                        enabled = bool(data.get('enabled', False))
                        config['auto_fill_authors'] = enabled
                        LOG.info(f"GUI: Setting auto_fill_authors to {enabled} in config, saving to {CONFIG_PATH}")
                        save_config(config)
                        # Reload config to ensure it's in sync
                        config = load_config()
                        with open(toggle_auto_fill_authors_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': True, 'enabled': enabled}, f)
                except Exception as e:
                    LOG.error(f"Error toggling auto fill authors: {e}")
                    try:
                        with open(toggle_auto_fill_authors_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': False, 'error': str(e)}, f)
                    except Exception:
                        pass

            # Handle set author add delay request
            if os.path.exists(set_author_add_delay_path):
                try:
                    with open(set_author_add_delay_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # Skip if this is already a response (has 'success' key)
                    if 'success' in data:
                        pass  # Already processed, skip
                    else:
                        delay_ms = int(data.get('delay_ms', 1000))
                        config['author_add_delay_ms'] = delay_ms
                        LOG.info(f"GUI: Setting author_add_delay_ms to {delay_ms} in config, saving to {CONFIG_PATH}")
                        save_config(config)
                        # Reload config to ensure it's in sync
                        config = load_config()
                        with open(set_author_add_delay_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': True, 'delay_ms': delay_ms}, f)
                except Exception as e:
                    LOG.error(f"Error setting author add delay: {e}")
                    try:
                        with open(set_author_add_delay_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': False, 'error': str(e)}, f)
                    except Exception:
                        pass

            # Handle set restart policy request
            if os.path.exists(set_restart_policy_path):
                try:
                    with open(set_restart_policy_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if 'success' in data:
                        pass
                    else:
                        interval = int(data.get('interval', 0))
                        config['auto_restart_interval'] = interval
                        LOG.info(f"GUI: Setting auto_restart_interval to {interval}")
                        save_config(config)
                        config = load_config()
                        with open(set_restart_policy_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': True, 'interval': interval}, f)
                except Exception as e:
                    LOG.error(f"Error setting restart policy: {e}")
                    try:
                        with open(set_restart_policy_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': False, 'error': str(e)}, f)
                    except Exception:
                        pass

            # Handle citation addition from GUI
            if os.path.exists(add_citation_path):
                try:
                    with open(add_citation_path, 'r', encoding='utf-8') as f:
                        add_data = json.load(f)

                    # Skip if this is already a response (has 'success' key)
                    if 'success' in add_data:
                        # Already processed, clean it up
                        try:
                            os.remove(add_citation_path)
                        except Exception:
                            pass
                    else:
                        citation_text = add_data.get('text', '').strip()
                        # Use the CITATION_CHANNEL_ID loaded at startup instead of re-reading from env
                        channel_id = int(CITATION_CHANNEL_ID) if CITATION_CHANNEL_ID and CITATION_CHANNEL_ID.isdigit() else None

                        if not citation_text:
                            LOG.warn(f"GUI: No citation text in add request, removing file")
                            try:
                                os.remove(add_citation_path)
                            except Exception:
                                pass
                        elif channel_id is None:
                            LOG.warn(f"GUI: No channel ID configured (CITATION_CHANNEL_ID={CITATION_CHANNEL_ID})")
                            with open(add_citation_path, 'w', encoding='utf-8') as f:
                                json.dump({'success': False, 'error': f'Channel ID not configured. Set CITATION_CHANNEL_ID in .env'}, f)
                        else:
                            LOG.info(f"GUI: Adding citation to channel {channel_id}")
                            result = await add_citation_via_gui(channel_id, citation_text)
                            # Write response back to file
                            with open(add_citation_path, 'w', encoding='utf-8') as f:
                                json.dump(result, f)
                except Exception as e:
                    LOG.error(f"GUI: Error adding citation: {e}")
                    try:
                        with open(add_citation_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': False, 'error': str(e)}, f)
                    except Exception:
                        pass

            # Handle fill next signal
            if os.path.exists(fill_path):
                try:
                    os.remove(fill_path)
                except Exception:
                    pass
                channel_id = int(CITATION_CHANNEL_ID) if CITATION_CHANNEL_ID and CITATION_CHANNEL_ID.isdigit() else None
                if channel_id is not None:
                    # Track which citation we're about to fill
                    queue = get_queue(channel_id)
                    if queue:
                        next_citation = queue[0] if queue else None
                        last_filled_citation_id = next_citation.get('citation_id') if next_citation else None
                        # Write "filling" status
                        try:
                            with open(completion_status_path, 'w', encoding='utf-8') as f:
                                json.dump({
                                    'status': 'filling',
                                    'citation_id': last_filled_citation_id,
                                    'timestamp': time.time()
                                }, f)
                        except Exception:
                            pass
                    LOG.info(f"GUI: Triggering fill for channel {channel_id}")
                    await trigger_fill_for_channel(channel_id)
                else:
                    LOG.warn(f"GUI: Cannot fill - no channel ID configured")

            # Update completion status by checking if the citation was processed
            channel_id = int(CITATION_CHANNEL_ID) if CITATION_CHANNEL_ID and CITATION_CHANNEL_ID.isdigit() else None
            if channel_id is not None and last_filled_citation_id:
                status_file = f"citation_status_{channel_id}.json"
                if os.path.exists(status_file):
                    try:
                        with open(status_file, 'r', encoding='utf-8') as f:
                            status = json.load(f)
                        if status.get('last_written_id') == last_filled_citation_id and status.get('state') == 'completed':
                            # Citation was completed
                            try:
                                with open(completion_status_path, 'w', encoding='utf-8') as f:
                                    json.dump({
                                        'status': 'completed',
                                        'citation_id': last_filled_citation_id,
                                        'timestamp': time.time(),
                                        'queue_remaining': len(get_queue(channel_id))
                                    }, f)
                                last_filled_citation_id = None  # Reset
                            except Exception:
                                pass
                        elif status.get('last_written_id') == last_filled_citation_id and status.get('state') == 'failed':
                            try:
                                with open(completion_status_path, 'w', encoding='utf-8') as f:
                                    json.dump({
                                        'status': 'failed',
                                        'citation_id': last_filled_citation_id,
                                        'timestamp': time.time(),
                                        'error': status.get('error') or 'Citation processing failed',
                                        'queue_remaining': len(get_queue(channel_id))
                                    }, f)
                                last_filled_citation_id = None
                            except Exception:
                                pass
                    except Exception:
                        pass

            # Handle queue request from GUI
            if os.path.exists(queue_request_path):
                try:
                    channel_id = int(CITATION_CHANNEL_ID) if CITATION_CHANNEL_ID and CITATION_CHANNEL_ID.isdigit() else None
                    if channel_id is not None:
                        queue = get_queue(channel_id)
                        queue_list = []
                        for i, citation in enumerate(queue, 1):
                            queue_list.append({
                                'position': i,
                                'text': citation.get('text', '')[:100] + ('...' if len(citation.get('text', '')) > 100 else ''),
                                'asset_type': citation.get('asset_type', 'presentation'),
                                'citation_id': citation.get('citation_id', '')
                            })
                        with open(queue_response_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': True, 'queue': queue_list, 'count': len(queue_list)}, f)
                    os.remove(queue_request_path)
                except Exception:
                    pass

            # Handle clear queue request
            if os.path.exists(clear_queue_path):
                try:
                    channel_id = int(CITATION_CHANNEL_ID) if CITATION_CHANNEL_ID and CITATION_CHANNEL_ID.isdigit() else None
                    if channel_id is not None:
                        queue = get_queue(channel_id)
                        count = len(queue)
                        queue.clear()
                        if channel_id in processing_citations:
                            del processing_citations[channel_id]
                        with open(clear_queue_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': True, 'cleared': count}, f)
                    else:
                        with open(clear_queue_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': False, 'error': 'No channel ID'}, f)
                except Exception as e:
                    try:
                        with open(clear_queue_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': False, 'error': str(e)}, f)
                    except Exception:
                        pass

            # Handle pause request
            if os.path.exists(pause_path):
                try:
                    config['paused'] = True
                    save_config(config)
                    os.remove(pause_path)
                except Exception:
                    pass

            # Handle resume request
            if os.path.exists(resume_path):
                try:
                    config['paused'] = False
                    save_config(config)
                    os.remove(resume_path)
                except Exception:
                    pass

            # Handle skip request
            if os.path.exists(skip_path):
                try:
                    channel_id = int(CITATION_CHANNEL_ID) if CITATION_CHANNEL_ID and CITATION_CHANNEL_ID.isdigit() else None
                    if channel_id is not None:
                        if channel_id in processing_citations:
                            del processing_citations[channel_id]
                            with open(skip_path, 'w', encoding='utf-8') as f:
                                json.dump({'success': True, 'message': 'Citation skipped'}, f)
                            LOG.info(f"GUI: Skipped citation for channel {channel_id}")
                        else:
                            with open(skip_path, 'w', encoding='utf-8') as f:
                                json.dump({'success': False, 'error': 'No citation currently being processed'}, f)
                    else:
                        with open(skip_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': False, 'error': 'No channel ID'}, f)
                except Exception as e:
                    try:
                        with open(skip_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': False, 'error': str(e)}, f)
                    except Exception:
                        pass

            # Handle set researcher request
            if os.path.exists(set_researcher_path):
                try:
                    with open(set_researcher_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # Skip if this is already a response (has 'success' key)
                    if 'success' in data:
                        pass  # Already processed, skip
                    else:
                        researcher = data.get('researcher', '').strip()
                        if researcher:
                            config['default_researcher'] = researcher
                            LOG.info(f"GUI: Setting default_researcher to {researcher}, saving to {CONFIG_PATH}")
                            save_config(config)
                            # Reload to ensure sync
                            config = load_config()
                            LOG.info(f"GUI: Researcher updated (config reloaded, value is now: {config.get('default_researcher')})")
                            with open(set_researcher_path, 'w', encoding='utf-8') as f:
                                json.dump({'success': True, 'researcher': researcher}, f)
                        else:
                            with open(set_researcher_path, 'w', encoding='utf-8') as f:
                                json.dump({'success': False, 'error': 'Empty researcher name'}, f)
                except Exception as e:
                    try:
                        with open(set_researcher_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': False, 'error': str(e)}, f)
                    except Exception:
                        pass

            # Handle set asset type request
            if os.path.exists(set_asset_type_path):
                try:
                    with open(set_asset_type_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # Skip if this is already a response (has 'success' key)
                    if 'success' in data:
                        pass  # Already processed, skip
                    else:
                        asset_type = data.get('asset_type', '').strip()
                        # Normalize using shared utility
                        normalized_type = normalize_config_mode(asset_type)
                        config['asset_mode'] = normalized_type
                        LOG.info(f"GUI: Setting asset_mode to {normalized_type} in config, saving to {CONFIG_PATH}")
                        save_config(config)
                        # Reload config to ensure it's in sync
                        config = load_config()
                        LOG.info(f"GUI: Asset mode updated to: {normalized_type} (config reloaded from {CONFIG_PATH}, value is now: {config.get('asset_mode')})")
                        print(f"✅ Asset mode set to: {normalized_type}")
                        with open(set_asset_type_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': True, 'asset_type': normalized_type}, f)
                except Exception as e:
                    LOG.error(f"Error setting asset type: {e}")
                    try:
                        with open(set_asset_type_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': False, 'error': str(e)}, f)
                    except Exception:
                        pass

            # Handle add topic request
            if os.path.exists(add_topic_path):
                try:
                    with open(add_topic_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # Skip if this is already a response (has 'success' key)
                    if 'success' in data:
                        pass  # Already processed, skip
                    else:
                        topic = data.get('topic', '').strip()
                        if not topic:
                            with open(add_topic_path, 'w', encoding='utf-8') as f:
                                json.dump({'success': False, 'error': 'Empty topic'}, f)
                        else:
                            # Use global CITATION_CHANNEL_ID
                            channel_id = str(CITATION_CHANNEL_ID) if CITATION_CHANNEL_ID and CITATION_CHANNEL_ID.isdigit() else None
                            if channel_id:
                                try:
                                    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                                        cfg = json.load(f)
                                except Exception:
                                    cfg = load_config()

                                topics_by_channel = cfg.setdefault('additional_topics', {})
                                lst = topics_by_channel.get(channel_id, [])

                                if topic in lst:
                                    with open(add_topic_path, 'w', encoding='utf-8') as f:
                                        json.dump({'success': False, 'error': 'Topic already exists'}, f)
                                elif len(lst) >= 6:
                                    with open(add_topic_path, 'w', encoding='utf-8') as f:
                                        json.dump({'success': False, 'error': 'Maximum 6 topics allowed'}, f)
                                else:
                                    lst.append(topic)
                                    topics_by_channel[channel_id] = lst
                                    try:
                                        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                                            json.dump(cfg, f, ensure_ascii=False, indent=2)
                                    except Exception:
                                        save_config(cfg)

                                    # Update in-memory config
                                    if isinstance(config, dict):
                                        config.setdefault('additional_topics', {})
                                        config['additional_topics'][channel_id] = lst

                                    with open(add_topic_path, 'w', encoding='utf-8') as f:
                                        json.dump({'success': True, 'topic': topic, 'count': len(lst)}, f)
                            else:
                                with open(add_topic_path, 'w', encoding='utf-8') as f:
                                    json.dump({'success': False, 'error': 'No channel ID'}, f)
                except Exception as e:
                    try:
                        with open(add_topic_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': False, 'error': str(e)}, f)
                    except Exception:
                        pass

            # Handle remove topic request
            if os.path.exists(remove_topic_path):
                try:
                    with open(remove_topic_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # Skip if this is already a response (has 'success' key)
                    if 'success' in data:
                        pass  # Already processed, skip
                    else:
                        topic = data.get('topic', '').strip()
                        if not topic:
                            with open(remove_topic_path, 'w', encoding='utf-8') as f:
                                json.dump({'success': False, 'error': 'Empty topic'}, f)
                        else:
                            # Use global CITATION_CHANNEL_ID
                            channel_id = str(CITATION_CHANNEL_ID) if CITATION_CHANNEL_ID and CITATION_CHANNEL_ID.isdigit() else None
                            if channel_id:
                                try:
                                    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                                        cfg = json.load(f)
                                except Exception:
                                    cfg = load_config()

                                topics_by_channel = cfg.setdefault('additional_topics', {})
                                lst = topics_by_channel.get(channel_id, [])

                                if topic in lst:
                                    lst.remove(topic)
                                    topics_by_channel[channel_id] = lst
                                    try:
                                        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                                            json.dump(cfg, f, ensure_ascii=False, indent=2)
                                    except Exception:
                                        save_config(cfg)

                                    # Update in-memory config
                                    if isinstance(config, dict):
                                        config.setdefault('additional_topics', {})
                                        config['additional_topics'][channel_id] = lst

                                    with open(remove_topic_path, 'w', encoding='utf-8') as f:
                                        json.dump({'success': True, 'topic': topic, 'count': len(lst)}, f)
                                else:
                                    with open(remove_topic_path, 'w', encoding='utf-8') as f:
                                        json.dump({'success': False, 'error': 'Topic not found'}, f)
                            else:
                                with open(remove_topic_path, 'w', encoding='utf-8') as f:
                                    json.dump({'success': False, 'error': 'No channel ID'}, f)
                except Exception as e:
                    try:
                        with open(remove_topic_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': False, 'error': str(e)}, f)
                    except Exception:
                        pass

            # Handle clear topics request
            if os.path.exists(clear_topics_path):
                try:
                    # Check if this is already a response (has 'success' key)
                    try:
                        with open(clear_topics_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        if 'success' in data:
                            pass  # Already processed, skip
                        else:
                            # Use global CITATION_CHANNEL_ID
                            channel_id = str(CITATION_CHANNEL_ID) if CITATION_CHANNEL_ID and CITATION_CHANNEL_ID.isdigit() else None
                            if channel_id:
                                try:
                                    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                                        cfg = json.load(f)
                                except Exception:
                                    cfg = load_config()

                                topics_by_channel = cfg.setdefault('additional_topics', {})
                                had = list(topics_by_channel.get(channel_id, []))

                                if channel_id in topics_by_channel:
                                    del topics_by_channel[channel_id]

                                try:
                                    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                                        json.dump(cfg, f, ensure_ascii=False, indent=2)
                                except Exception:
                                    save_config(cfg)

                                # Update in-memory config
                                if isinstance(config, dict) and isinstance(config.get('additional_topics'), dict):
                                    config['additional_topics'].pop(channel_id, None)

                                with open(clear_topics_path, 'w', encoding='utf-8') as f:
                                    json.dump({'success': True, 'cleared': len(had)}, f)
                            else:
                                with open(clear_topics_path, 'w', encoding='utf-8') as f:
                                    json.dump({'success': False, 'error': 'No channel ID'}, f)
                    except Exception:
                        pass  # File might be empty or invalid, continue processing
                except Exception as e:
                    try:
                        with open(clear_topics_path, 'w', encoding='utf-8') as f:
                            json.dump({'success': False, 'error': str(e)}, f)
                    except Exception:
                        pass
        except Exception:
            # Never crash the watcher
            pass
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    main()
