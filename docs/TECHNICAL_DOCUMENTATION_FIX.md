# Technical Documentation Asset Type - Fix Summary

## Problem
The `technical_documentation` asset type wasn't working properly across the system. When set in the bot config, it would fall through validation checks and default to "presentation" or "poster".

## Root Cause
1. **Missing from validation lists**: Discord bot had hardcoded tuples checking for valid asset types, but `"technical_documentation"` was missing from several critical locations
2. **Wrong field names**: The automation module was using presentation-style field names instead of the correct "Asset title" field

## Fixes Applied

### 1. Discord Bot (`discord_bot_batch_smart.py`)

**Fixed validation in 4 locations:**
- Line 313, 315: `on_message` handler ✅ (already had it)
- Line 639, 641: `!add` command ✅ (already had it)
- **Line 957, 962**: `/add` slash command - **FIXED**
- **Line 1355, 1357**: `add_citation_via_gui()` - **FIXED**

**Before:**
```python
if forced_type in ("poster", "presentation", "book_chapter", "journal_article", "proceedings", "abstract"):
    asset_type = forced_type
elif current_asset_mode in ("poster", "presentation", "book_chapter", "journal_article", "proceedings", "abstract"):
    asset_type = current_asset_mode
```

**After:**
```python
if forced_type in ("poster", "presentation", "book_chapter", "journal_article", "proceedings", "abstract", "technical_documentation"):
    asset_type = forced_type
elif current_asset_mode in ("poster", "presentation", "book_chapter", "journal_article", "proceedings", "abstract", "technical_documentation"):
    asset_type = current_asset_mode
```

### 2. Technical Documentation Module (`automation/technical_documentation_impl.py`)

**Updated field names:**
- Changed from `"Publication title *"` to `"Asset title *"` (line 265)
- Added `asset_title` field to parsed data alongside `proceedings_title` for compatibility

**Before:**
```python
try:
    page.get_by_role('textbox', name='Publication title *').click()
    page.get_by_role('textbox', name='Publication title *').fill(citation_data.get('proceedings_title', ''))
except Exception:
    # Try alternate...
```

**After:**
```python
try:
    page.get_by_role('textbox', name='Asset title *').click()
    page.get_by_role('textbox', name='Asset title *').fill(citation_data.get('proceedings_title', ''))
except Exception as e:
    print(f"⚠️ Asset title field error: {e}")
```

### 3. OpenAI Parser (`openai_parser.py`)

**Added technical documentation fields to schema:**
- `publisher_name`: Organization/publisher name
- `report_number`: Report or document number
- `asset_title`: Document title (same as proceedings_title for tech docs)

**Updates:**
- Line 106-108: Added fields to prompt
- Line 172-174: Added fields to defaults dict

## Testing

The fix was verified with the logs showing:
```
[2026-02-11 18:57:21] [BOT] [INFO] GUI: Setting asset_mode to technical_documentation in config
[2026-02-11 18:57:21] [BOT] [INFO] GUI: Asset mode updated to: technical_documentation
✅ Asset mode set to: technical_documentation
[2026-02-11 18:57:38] [WORKER] [INFO] Processing Technical Documentation
[2026-02-11 18:57:38] [WORKER] [INFO] Title: Vineyard Wind demersal trawl survey annual report – VW1 study area: 2023/2024
```

## Field Mapping

### Technical Documentation Form Fields
- **Asset title \***: Main document title (mapped from `proceedings_title` or `asset_title`)
- **Publisher name**: Organization/company name
- **Report number**: Document/report identifier
- **DOI**: Digital Object Identifier
- **Date**: Publication/presentation date
- **Language**: Publication language
- **Description and Research topics**: Research categorization

### Comparison with Other Asset Types

| Asset Type | Title Field Name |
|------------|------------------|
| Conference Presentation | `Conference presentation title *` |
| Conference Poster | `Poster presentation title *` (assumed) |
| Conference Proceedings | `Publication title` |
| Journal Article | `Article title` |
| Book Chapter | `Chapter title` |
| **Technical Documentation** | **`Asset title *`** |

## Related Infrastructure

### New IPC Protocol (`utils/ipc_protocol.py`)
Created centralized communication protocol handler to prevent future asset type normalization issues:
- Automatic asset type normalization at all message boundaries
- Consistent message format across Bot ↔ Worker ↔ Flask ↔ Terminal
- Type-safe operations with built-in validation
- See `docs/IPC_PROTOCOL.md` for usage guide

### Asset Type Utils (`utils/asset_type_utils.py`)
Already had proper support for `technical_documentation`:
- `VALID_CONFIG_MODES` includes `"technical_documentation"`
- `normalize_config_mode()` handles all variations
- `CONFIG_MODE_TO_ASSET_TYPE` mapping works correctly

## Validation

All asset types now properly validated:
```python
VALID_CONFIG_MODES = {
    "auto",
    "presentation",
    "poster",
    "book_chapter",
    "journal_article",
    "proceedings",
    "abstract",
    "technical_documentation"  # ✅ Properly supported
}
```

## Future Prevention

To avoid similar issues:
1. **Use centralized validation**: Import from `utils/asset_type_utils.py` instead of hardcoding lists
2. **Use IPC protocol**: Leverage `utils/ipc_protocol.py` for all inter-process communication
3. **Cross-reference**: When adding new asset types, grep for all validation tuples and update them together
4. **Testing**: Add new asset type to `test_citations.py` test suite

## Files Modified

1. `discord_bot_batch_smart.py` - Fixed validation in slash command and GUI handler
2. `automation/technical_documentation_impl.py` - Updated to use correct "Asset title" field
3. `openai_parser.py` - Added technical documentation fields to schema
4. `utils/ipc_protocol.py` - Created (new infrastructure)
5. `docs/IPC_PROTOCOL.md` - Created (documentation)
