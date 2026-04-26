# IPC Protocol Guide

## Overview

The `utils/ipc_protocol.py` module provides a centralized, normalized protocol for communication between all system components:

- **Discord Bot** (`discord_bot_batch_smart.py`)
- **Flask Web GUI** (`esp_gui_web.py`)
- **Worker Process** (`automation/worker.py`)
- **Terminal/CLI** (future)

## Key Benefits

1. **Asset Type Normalization**: All asset types are automatically normalized before transmission
2. **Consistent Message Format**: All messages have standard structure with timestamps
3. **Type Safety**: Centralized validation ensures valid asset types across all components
4. **Error Handling**: Built-in timeout and retry logic for reliable communication
5. **Single Source of Truth**: All IPC logic in one place, easier to maintain and debug

## Architecture

### Communication Patterns

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Discord Bot   │◄────────│  Control Files   │────────►│     Worker      │
│                 │         │  (.json files)   │         │                 │
└─────────────────┘         └──────────────────┘         └─────────────────┘
        ▲                           ▲
        │                           │
        └───────────────────────────┘
               │
               ▼
        ┌──────────────────┐
        │   Flask GUI      │
        └──────────────────┘
```

### File-Based IPC

**Bot → Worker:**
- `citation_control_{channel_id}.json` - Send citation for processing
- `citation_status_{channel_id}.json` - Worker status updates

**GUI → Bot:**
- `gui_add_citation.json` - Add citation to queue
- `gui_set_asset_type.json` - Change asset type mode
- `gui_set_researcher.json` - Change default researcher
- `gui_pause.json`, `gui_resume.json`, `gui_skip.json` - Control commands
- ... (other GUI control files)

## Usage Examples

### Discord Bot: Sending Citation to Worker

**Before (manual, no normalization):**
```python
control_file = f"citation_control_{channel_id}.json"
with open(control_file, 'w') as f:
    json.dump({
        'text': citation['text'],
        'asset_type': citation['asset_type'],  # ⚠️ May not be normalized!
        'message_id': citation['message_id'],
        # ...
    }, f)
```

**After (using IPC protocol):**
```python
from utils.ipc_protocol import get_protocol

protocol = get_protocol()
protocol.send_citation_to_worker(
    channel_id=channel_id,
    citation_text=citation['text'],
    asset_type=citation['asset_type'],  # ✓ Automatically normalized
    researcher=researcher,
    citation_id=citation_id,
    message_id=message_id,
    author=author,
    parsed_data=parsed_data
)
```

### Flask GUI: Setting Asset Type

**Before (manual):**
```python
asset_type_file = os.path.join(PROJECT_DIR, 'gui_set_asset_type.json')
with open(asset_type_file, 'w', encoding='utf-8') as f:
    json.dump({'asset_type': asset_type}, f)  # ⚠️ Not normalized

# Poll for response...
while time.time() - start_time < max_wait:
    with open(asset_type_file, 'r', encoding='utf-8') as f:
        response = json.load(f)
    if 'success' in response:
        return response
    time.sleep(0.2)
```

**After (using IPC protocol):**
```python
from utils.ipc_protocol import get_protocol

protocol = get_protocol(PROJECT_DIR)
response = protocol.gui_set_asset_type(asset_type)  # ✓ Normalized + response handling
return response
```

### Worker: Reading Citations

**Before:**
```python
with open(control_file, 'r') as f:
    data = json.load(f)
asset_type = data.get('asset_type', 'presentation')  # ⚠️ Trusts incoming value
```

**After:**
```python
from utils.ipc_protocol import get_protocol

protocol = get_protocol()
citation_data = protocol.read_message(f"citation_control_{channel_id}.json")
if citation_data:
    asset_type = citation_data.get('asset_type')  # ✓ Already normalized
```

## Asset Type Normalization

### Normalization Flow

The protocol automatically normalizes asset types from any format to the standard config mode format:

```python
from utils.ipc_protocol import IPCProtocol

# All of these normalize to "technical_documentation"
IPCProtocol.normalize_asset_type_input("technical_documentation")
IPCProtocol.normalize_asset_type_input("technical document")
IPCProtocol.normalize_asset_type_input("Technical Documentation")
IPCProtocol.normalize_asset_type_input("techdoc")
IPCProtocol.normalize_asset_type_input("whitepaper")
# → "technical_documentation"

# Display formatting
IPCProtocol.asset_type_to_display("technical_documentation")
# → "Technical Documentation"
```

### Valid Asset Types

After normalization, these are the valid values:

- `auto` - Auto-detect from citation text
- `presentation` - Conference Presentation
- `poster` - Conference Poster
- `proceedings` - Conference Proceedings
- `journal_article` - Journal Article
- `book_chapter` - Book Chapter
- `abstract` - Conference Abstract
- `technical_documentation` - Technical Documentation

## Migration Guide

### For Discord Bot

1. Import the protocol:
   ```python
   from utils.ipc_protocol import get_protocol
   ```

2. Initialize once (or use singleton):
   ```python
   protocol = get_protocol()
   ```

3. Replace manual file operations:
   - `json.dump()` → `protocol.write_message()`
   - `json.load()` → `protocol.read_message()`
   - Citation sending → `protocol.send_citation_to_worker()`
   - GUI responses → `protocol.send_gui_response()`

### For Flask GUI

1. Import and initialize:
   ```python
   from utils.ipc_protocol import get_protocol
   protocol = get_protocol(PROJECT_DIR)
   ```

2. Replace request/response patterns:
   - Manual writes + polling → `protocol.gui_set_asset_type()`
   - Manual writes + polling → `protocol.gui_set_researcher()`
   - Manual writes + polling → `protocol.gui_add_citation()`

### For Worker

1. Import the protocol:
   ```python
   from utils.ipc_protocol import get_protocol
   ```

2. Use protocol to read citations:
   ```python
   protocol = get_protocol()
   data = protocol.read_message(control_file)
   ```

3. Asset type will already be normalized from bot/GUI

## Testing

Test the protocol with:

```python
from utils.ipc_protocol import get_protocol

protocol = get_protocol("/tmp/test_ipc")

# Test normalization
normalized = protocol.normalize_asset_type_input("Technical Document", source="user")
assert normalized == "technical_documentation"

# Test message format
msg = protocol.create_message("request", "set_asset_type", asset_type="poster")
assert msg["type"] == "request"
assert msg["operation"] == "set_asset_type"
assert "timestamp" in msg

# Test write/read
protocol.write_message("test.json", {"foo": "bar"})
data = protocol.read_message("test.json")
assert data["foo"] == "bar"

print("✓ All tests passed")
```

## Troubleshooting

### Asset Type Not Being Applied

**Problem**: Setting asset type in GUI doesn't affect citations

**Root Cause**: Asset type was stored in config but not normalized before being sent to worker

**Solution**: Use `protocol.send_citation_to_worker()` which automatically normalizes

### Response Timeout

**Problem**: `gui_set_asset_type()` times out

**Possible Causes**:
1. Bot not running or not watching control files
2. Bot crashed when processing request
3. File permissions issue

**Debug Steps**:
1. Check if bot process is running
2. Check bot logs for errors
3. Manually inspect control file: `cat gui_set_asset_type.json`
4. Check if file has `"success"` field (indicates bot processed it)

### Inconsistent Asset Types

**Problem**: Same asset type displays differently in different parts of UI

**Root Cause**: Not using `IPCProtocol.asset_type_to_display()` for formatting

**Solution**:
```python
display_name = protocol.asset_type_to_display(asset_type)
```

## Future Enhancements

1. **Binary Protocol**: Replace JSON files with faster binary format or sockets
2. **Message Queue**: Replace polling with event-driven architecture
3. **Validation Schema**: Add JSON schema validation for all message types
4. **Logging**: Built-in audit trail for all IPC operations
5. **Encryption**: Encrypt sensitive data in control files
6. **Terminal CLI**: Add command-line tool using same IPC protocol

## Related Files

- `utils/asset_type_utils.py` - Asset type normalization utilities
- `discord_bot_batch_smart.py` - Discord bot implementation
- `esp_gui_web.py` - Flask web GUI
- `automation/worker.py` - Worker process
- `bot_config.json` - Shared configuration
