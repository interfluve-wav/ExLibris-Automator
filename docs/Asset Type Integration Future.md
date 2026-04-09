# Asset Type Integration Guide

## Overview
This guide provides step-by-step instructions for adding a new asset type to the ESP Citation Automation system. Follow these steps to integrate any new asset type (e.g., Technical Report, Dataset, Patent, etc.).

---

## Prerequisites

Before starting, ensure you have:
- Working knowledge of Python
- Playwright basics (for browser automation)
- Access to Esploro to test form fields
- Existing asset type implementations as reference (e.g., `abstract_impl.py`, `journal_impl.py`)

---

## Step-by-Step Integration Process

### Step 1: Create Implementation File

**File**: `automation/{asset_type}_impl.py`

This file contains all the automation logic for your new asset type.

#### 1.1 File Header and Imports

```python
"""
Esploro automation for [Asset Type Name].
Parses citations (OpenAI with conservative manual fallback), navigates with
Playwright, and fills the [asset type] form fields.
"""
import os
from dotenv import load_dotenv
import csv
import re
from typing import List, Dict
from utils.config_utils import extract_ordinal_word_number, get_additional_topics_for_channel

try:
    from openai_parser import parse_citation_with_openai
except Exception:
    parse_citation_with_openai = None

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

load_dotenv()

# Citation parser configuration
DEFAULT_PARSER = "openai"  # Change to "manual" if needed
```

#### 1.2 Implement `parse_any_citation()` Function

This function parses citation text and returns structured data.

**Template:**
```python
def parse_any_citation(citation_text: str) -> Dict[str, str]:
    """Parse using OpenAI or manual regex parser based on configuration."""
    parser_type = os.getenv('CITATION_PARSER', DEFAULT_PARSER).lower()

    if parser_type == "openai":
        try:
            model_name = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
            print(f"[parser] Using OpenAI model: {model_name}")
        except Exception:
            print("[parser] Using OpenAI (model unknown)")

        if not parse_citation_with_openai:
            return {"error": "OpenAI parser not available"}

        llm_data = parse_citation_with_openai(citation_text) or {}
        if not llm_data:
            return {"error": "OpenAI returned empty/invalid result"}
    else:
        print("[parser] Using manual regex parser")
        return parse_citation(citation_text)

    # Handle errors from LLM parsers
    if "error" in llm_data:
        return llm_data

    # Normalize LLM results for your asset type
    try:
        # Clear fields not relevant to this asset type
        llm_data['conference_name'] = ''
        llm_data['conference_number'] = ''
        llm_data['conference_location'] = ''
        llm_data['conference_date_from'] = ''
        llm_data['conference_date_to'] = ''
        llm_data['published_proceedings_title'] = ''

        # Map asset-specific fields
        # Example: if your asset type has a "report_number" field
        # llm_data['report_number'] = llm_data.get('number', '')

        # Normalize DOI (strip URL prefix)
        if llm_data.get('doi'):
            m = re.search(r"(10\.\d{4,9}/\S+)$", str(llm_data['doi']))
            if m:
                llm_data['doi'] = m.group(1)

        # Ensure year is set
        if not llm_data.get('year'):
            m_year = re.search(r'\b(\d{4})\b', citation_text)
            if m_year:
                llm_data['year'] = m_year.group(1)

        # Set date_presented to year for compatibility
        llm_data['date_presented'] = llm_data.get('year', '')

    except Exception:
        pass

    # Fallback: if LLM misses critical fields, use manual parser
    needs_fallback = (
        not llm_data.get('proceedings_title')
        or len(llm_data.get('proceedings_title', '').strip()) < 5
        or not llm_data.get('publisher_name')
    )

    if needs_fallback:
        try:
            manual = parse_citation(citation_text)
        except Exception:
            manual = {}

        # Fill missing fields from manual parse
        for k in ['proceedings_title', 'publisher_name', 'authors', 'year']:
            if not llm_data.get(k) and manual.get(k):
                llm_data[k] = manual[k]

    return llm_data
```

#### 1.3 Implement `parse_citation()` Function (Manual Parser)

Regex-based parser as fallback. Study your citation format carefully.

**Template:**
```python
def parse_citation(citation_text: str) -> Dict[str, str]:
    """Parse [asset type] citations manually using regex.

    Example format:
    Authors. (YYYY). Title. Publisher/Source, Additional Info.
    """
    text = (citation_text or "").strip()
    if not text:
        return {"error": "Empty citation"}

    # Extract year: (YYYY)
    m_date = re.search(r"\((\d{4})\)", text)
    year = m_date.group(1) if m_date else ""

    # Extract authors (everything before the date)
    authors = ""
    if m_date:
        date_start = m_date.start()
        authors = text[:date_start].strip().rstrip(' .,')

    # Extract title (between year and next section)
    title = ""
    if m_date:
        after_date = text[m_date.end():].strip()
        if after_date.startswith('.'):
            after_date = after_date[1:].strip()

        first_period = after_date.find('.')
        if first_period > 0:
            title = after_date[:first_period].strip()

    # Extract additional fields as needed for your asset type
    # Example: publisher_name, volume, DOI, etc.

    # Extract DOI if present
    doi = ""
    m_doi = re.search(r"(?:DOI[:\s]*)?(10\.\d{4,9}/\S+)", text, flags=re.I)
    if m_doi:
        doi = m_doi.group(1)

    # Return all fields (use empty strings for missing data)
    return {
        "proceedings_title": title,
        "authors": authors.rstrip(' .'),
        "year": year,
        "date_presented": year,
        "publisher_name": "",  # Fill if parsed
        "doi": doi,
        # Add asset-specific fields here
        "research_topics": "",
        "link": "",
        # Clear conference fields
        "conference_name": "",
        "conference_number": "",
        "conference_location": "",
        "conference_date_from": "",
        "conference_date_to": "",
        "published_proceedings_title": "",
    }
```

#### 1.4 Implement `goto_with_retries()` Function

Standard navigation helper with retries.

```python
def goto_with_retries(page, url: str, attempts: int = 3, wait_until: str = 'load') -> bool:
    """Navigate with simple retries to mitigate transient net::ERR_CONNECTION_RESET."""
    for attempt in range(attempts):
        try:
            page.goto(url, wait_until=wait_until, timeout=45000)
            return True
        except Exception as e:
            if attempt == attempts - 1:
                print(f"✗ Navigation to {url} failed after {attempts} attempts: {e}")
                return False
            backoff_ms = (attempt + 1) * 2000
            print(f"… navigation error ({e}); retrying in {backoff_ms} ms [{attempt + 1}/{attempts}]")
            page.wait_for_timeout(backoff_ms)
```

#### 1.5 Implement `save_citation_to_csv()` Function

Save parsed data to CSV for reference.

```python
def save_citation_to_csv(citation_data: Dict[str, str], output_file: str):
    """Save single citation to CSV (overwrites existing file)"""
    # Define fieldnames based on your asset type
    fieldnames = [
        "proceedings_title", "authors", "year", "date_presented",
        "publisher_name", "doi", "research_topics"
        # Add asset-specific fields
    ]

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerow(citation_data)
```

#### 1.6 Implement `process_citation()` Function

**This is the most important function** - it automates form filling in Esploro.

**Template:**
```python
def process_citation(page, citation_data: Dict[str, str],
                    pause_after: bool = True,
                    start_from_home: bool = True):
    """Fill one citation for [Asset Type] asset type"""

    # Navigate to deposit wizard
    if start_from_home:
        try:
            page.get_by_role('link', name='Deposit Asset').click()
        except Exception:
            page.goto('https://umassd-researchmanagement.esploro.exlibrisgroup.com/ng;u=%2Fmng%2Faction%2Fhome.do%3FngHome%3Dtrue')
            page.get_by_role('link', name='Deposit Asset').click()

    # Select researcher
    researcher = (citation_data.get('researcher') or
                 os.getenv('DEFAULT_RESEARCHER') or
                 'Scarano, Frank J').strip()
    page.get_by_role('textbox', name='Researcher').click()
    page.get_by_role('textbox', name='Researcher').fill(researcher)
    page.get_by_text(researcher).click()

    # Asset Type Selection
    page.get_by_role('combobox', name='Select an item from the list').click()
    page.get_by_role('combobox', name='Asset type *').click()
    page.get_by_role('combobox', name='Asset type *').fill('[Your Asset Type Text]')
    page.get_by_label('Publication <strong>').get_by_text('[Your Asset Type]').click()
    page.get_by_role('button', name='Next').click()

    # Wait for loading
    try:
        page.locator('#loadingBlocker').wait_for(state='hidden', timeout=10000)
    except Exception:
        page.wait_for_timeout(300)

    # Fill main title field
    # IMPORTANT: Update field name to match Esploro form
    page.get_by_role('textbox', name='[Title Field Name] *').click()
    page.get_by_role('textbox', name='[Title Field Name] *').fill(
        citation_data.get('proceedings_title', '')
    )

    # Add timeout for auto-parsing
    page.wait_for_timeout(1500)

    # Fill additional fields specific to your asset type
    # Example: Report Number, Publisher, Volume, etc.
    # Use try-except blocks for each field

    try:
        field_value = citation_data.get('your_field', '').strip()
        if field_value:
            page.get_by_role('textbox', name='[Field Name]').click()
            page.get_by_role('textbox', name='[Field Name]').fill(field_value)
            print(f"✓ Filled [field name]: {field_value}")
    except Exception as e:
        print(f"✗ [Field name] error: {e}")

    # Add Date section
    try:
        page.get_by_role('button', name=' Add Date').click()
        page.get_by_role('combobox', name='Date type *').click()
        page.get_by_label('Recent', exact=True).get_by_text('[Date Type]').click()
        page.get_by_role('textbox', name='Choose date *').click()

        # Prefer MM/DD/YYYY, then MM/YYYY, else fallback to YYYY
        date_to_fill = (
            citation_data.get('date_presented_mmddyyyy')
            or citation_data.get('date_presented_mmyyyy')
            or citation_data.get('year', '')
        )
        page.get_by_role('textbox', name='Choose date *').fill(date_to_fill)
        page.get_by_role('button', name='Add and close').click()
        print("✓ Added date")
    except Exception as e:
        print(f"✗ Failed to add date: {e}")

    # Wait for loading blocker
    try:
        page.locator('#loadingBlocker').wait_for(state='hidden', timeout=3000)
    except Exception:
        page.wait_for_timeout(500)

    # Add Language
    page.get_by_role('combobox', name='Language').click()
    page.get_by_label('Recent', exact=True).get_by_text('English', exact=True).click()

    # Close language dropdown
    try:
        page.keyboard.press('Escape')
        page.wait_for_timeout(100)
    except Exception:
        pass

    try:
        page.mouse.click(5, 5)
        page.wait_for_timeout(100)
    except Exception:
        pass

    # Fill DOI if present
    try:
        doi = (citation_data.get('doi') or '').strip()
        if doi:
            page.get_by_role('textbox', name='DOI').click()
            page.get_by_role('textbox', name='DOI').fill(doi)
            print(f"✓ Filled DOI: {doi}")
    except Exception as e:
        print(f"⚠️ DOI fill skipped: {e}")

    # Additional 'Description and Research' topics
    try:
        channel_id = str(citation_data.get('channel_id') or '')
        topics: List[str] = get_additional_topics_for_channel(channel_id) if channel_id else []
        if topics:
            box = page.get_by_role('group', name='Description and Research').get_by_role('textbox').nth(2)
            box.click()
            for t in topics[:6]:
                box.fill(t)
                box.press('Enter')
            try:
                box.fill('')
            except Exception:
                pass
            print(f"✓ Filled additional topics: {', '.join(topics[:6])}")
        else:
            print("… No additional topics configured for this channel")
    except Exception as e:
        print(f"⚠️ Additional topics fill skipped: {e}")

    print(f"✓ Form filled for: {citation_data.get('proceedings_title', '')}")
    print("Add creators manually, then submit when ready.")

    if pause_after:
        input("Press Enter to continue...")
```

#### 1.7 Add `main()` Function for Standalone Testing

```python
def main():
    print("=== Citation Processor ===")

    citation_text = input("Enter your citation: ").strip()

    if not citation_text:
        print("No citation entered. Exiting.")
        return

    print(f"Processing: {citation_text}")

    # Parse citation
    parsed_citation = parse_any_citation(citation_text)

    if "error" in parsed_citation:
        print(f"Error: {parsed_citation['error']}")
        return

    # Save to CSV
    csv_file = 'citations[AssetType].csv'
    save_citation_to_csv(parsed_citation, csv_file)
    print(f"✓ Saved to {csv_file}")

    # Show parsed data
    print("\nParsed citation data:")
    for key, value in parsed_citation.items():
        if value:
            print(f"  {key}: {value}")

    # Start browser automation
    if sync_playwright is None:
        print("Playwright not installed; skipping automation.")
        return

    print("\n=== Starting browser automation ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # Login
        page.goto('https://umassd-researchmanagement.esploro.exlibrisgroup.com/mng/login')
        page.get_by_role('textbox', name='User Name').fill('your_username')
        page.get_by_role('textbox', name='Password').fill('your_password')
        page.get_by_role('button', name='Login').click()
        page.goto('https://umassd-researchmanagement.esploro.exlibrisgroup.com/ng;u=%2Fmng%2Faction%2Fhome.do%3FngHome%3Dtrue')

        # Process citation
        process_citation(page, parsed_citation, pause_after=True)

    print("Done!")

if __name__ == "__main__":
    main()
```

---

### Step 2: Create Wrapper File

**File**: `automation/{asset_type}.py`

This is a thin wrapper that exports the API.

```python
"""
Thin wrapper: re-exports the [asset type] automation API from
`automation.[asset_type]_impl` (parse_any_citation, goto_with_retries,
save_citation_to_csv, process_citation).
"""
from .[asset_type]_impl import (
    parse_any_citation,
    goto_with_retries,
    save_citation_to_csv,
    process_citation,
)
```

---

### Step 3: Test Implementation Standalone

Before integrating with the bot, test your implementation:

```bash
python3 automation/your_asset_type_impl.py
```

Enter a sample citation and verify:
- ✅ Citation parses correctly
- ✅ CSV file is created
- ✅ Browser opens and navigates to Esploro
- ✅ Form fields are filled correctly
- ✅ No errors in console

---

### Step 4: Integrate with Worker

Edit `automation/worker.py`:

1. **Add import** (around line 19):
```python
from automation import your_asset_type as your_asset_type_mod
```

2. **Add loader function** (around line 100):
```python
def load_your_asset_type_module():
    return your_asset_type_mod
```

3. **Load in main()** (around line 110):
```python
your_asset_type_mod = load_your_asset_type_module()
your_asset_type_parse = getattr(your_asset_type_mod, "parse_any_citation")
your_asset_type_process = getattr(your_asset_type_mod, "process_citation")
```

4. **Add to switch statement** (around line 206):
```python
elif asset_type == 'your_asset_type':
    parse_fn = your_asset_type_parse
    process_fn = your_asset_type_process
    asset_display = "Your Asset Type Display Name"
```

---

### Step 5: Integrate with Discord Bot

See **"Web App & Discord Bot Integration Steps.md"** Step 3 for detailed instructions.

**Quick checklist:**
- [ ] Add to `detect_asset_type()` function
- [ ] Add slash command
- [ ] Update help text
- [ ] Add to `VALID_ASSET_TYPES`

---

### Step 6: Integrate with Web App

See **"Web App & Discord Bot Integration Steps.md"** Step 4 for detailed instructions.

**Quick checklist:**
- [ ] Add to dropdown menu
- [ ] Add display name mapping
- [ ] Add validation

---

### Step 7: Test Full Integration

1. **Test with Discord Bot:**
   ```bash
   python3 discord_bot_batch_smart.py
   ```
   - Send citation in Discord
   - Use `!f` to fill
   - Verify automation works

2. **Test with Web App:**
   ```bash
   python3 esp_gui_web.py
   ```
   - Open http://localhost:8765
   - Set asset type
   - Add citation
   - Click "Fill Next Citation"
   - Verify automation works

3. **Test Edge Cases:**
   - Empty fields
   - Malformed citations
   - Special characters
   - Very long citations

---

## Common Field Mappings

When implementing `process_citation()`, you'll need to know Esploro's field names. Here are common patterns:

| Data Field | Typical Esploro Field Name |
|-----------|---------------------------|
| Title | `[Asset Type] title *` |
| Authors | Usually added manually via UI |
| Date | `Choose date *` (after "Add Date") |
| Publisher | `Publisher name` or `Source` |
| Volume | `Volume` |
| Issue | `Issue` |
| Pages | `Start Page`, `End Page` |
| DOI | `DOI` |
| ISBN | `ISBN` |
| ISSN | `ISSN` |
| URL | `URL` |

**Finding Field Names:**
1. Open Esploro deposit form manually
2. Right-click field → Inspect Element
3. Look for `name`, `aria-label`, or `placeholder` attributes
4. Use Playwright's Codegen tool:
   ```bash
   playwright codegen https://your-esploro-url
   ```

---

## Checklist: Adding a New Asset Type

### Implementation Phase
- [ ] Created `automation/{asset_type}_impl.py`
- [ ] Implemented `parse_any_citation()`
- [ ] Implemented `parse_citation()` (manual parser)
- [ ] Implemented `goto_with_retries()`
- [ ] Implemented `save_citation_to_csv()`
- [ ] Implemented `process_citation()`
- [ ] Added `main()` for standalone testing
- [ ] Created `automation/{asset_type}.py` wrapper
- [ ] Tested implementation standalone

### Integration Phase
- [ ] Added import to `worker.py`
- [ ] Added loader function to `worker.py`
- [ ] Added to asset type switch in `worker.py`
- [ ] Added detection keywords to `discord_bot_batch_smart.py`
- [ ] Added slash command to `discord_bot_batch_smart.py`
- [ ] Added to help text in `discord_bot_batch_smart.py`
- [ ] Added to `VALID_ASSET_TYPES` in `discord_bot_batch_smart.py`
- [ ] Added to dropdown in `esp_gui_web.py`
- [ ] Added display name mapping in `esp_gui_web.py`
- [ ] Added validation in `esp_gui_web.py`

### Testing Phase
- [ ] Tested standalone with sample citation
- [ ] Tested with Discord bot (`!f` command)
- [ ] Tested with Web App
- [ ] Tested auto-detection (if applicable)
- [ ] Tested slash command
- [ ] Tested with malformed citations
- [ ] Tested with edge cases
- [ ] Verified all fields fill correctly
- [ ] Verified CSV output is correct

### Documentation Phase
- [ ] Updated this file with asset-specific notes
- [ ] Added example citations to documentation
- [ ] Noted any special handling required
- [ ] Updated README if necessary

---

## Tips and Best Practices

### Parsing
- **Use OpenAI parser when possible** - It's more flexible
- **Always have manual parser as fallback** - Regex is deterministic
- **Normalize field names** - LLMs may return different field names
- **Validate critical fields** - Check title, authors, year aren't empty
- **Strip whitespace** - Always `.strip()` string fields
- **Handle optional fields gracefully** - Use `.get()` with defaults

### Browser Automation
- **Use role-based selectors** - More stable than CSS selectors
- **Add waits after filling** - Forms may have JavaScript validation
- **Wait for loading blockers** - Always wait for `#loadingBlocker` to disappear
- **Close dropdowns explicitly** - Use Escape key or click elsewhere
- **Use try-except blocks** - Every field fill should be in try-except
- **Print status messages** - Help debugging with `print()` statements
- **Don't hard-code credentials** - Use environment variables

### Error Handling
- **Return error dicts** - `{"error": "message"}` for parse failures
- **Log errors verbosely** - Include field name and error message
- **Fail gracefully** - Skip optional fields if they error
- **Test edge cases** - Empty strings, special characters, very long text

### Performance
- **Minimize waits** - Only wait when necessary
- **Use short timeouts** - Start with 100ms, increase if needed
- **Batch operations** - Fill related fields without waiting between them
- **Reuse browser** - Worker keeps browser open between citations

---

## Examples

### Example 1: Technical Report

**Citation format:**
```
Smith, J., & Doe, A. (2024). Advanced Machine Learning Techniques.
Tech Report TR-2024-001, MIT Computer Science Department.
https://doi.org/10.1234/tr.2024.001
```

**Key fields:**
- Report number: `TR-2024-001`
- Department/Organization: `MIT Computer Science Department`
- Title: `Advanced Machine Learning Techniques`

### Example 2: Dataset

**Citation format:**
```
Johnson, M. (2023). Climate Change Temperature Dataset.
figshare. Dataset. https://doi.org/10.6084/m9.figshare.12345678
```

**Key fields:**
- Title: `Climate Change Temperature Dataset`
- Repository: `figshare`
- Resource type: `Dataset`

---

## Troubleshooting

### "Asset type not recognized"
- Check spelling in all three files (worker, bot, web app)
- Verify asset type is lowercase with underscores
- Check `VALID_ASSET_TYPES` list

### "Form fields not filling"
- Use Playwright Codegen to verify selectors
- Check if Esploro changed field names
- Add waits before filling fields
- Check for loading blockers

### "Parser returns empty dict"
- Test parser with `print()` statements
- Verify citation format matches expected pattern
- Check regex patterns are correct
- Try OpenAI parser instead of manual

### "Browser not opening"
- Check `HEADLESS` environment variable
- Verify Playwright is installed: `pip install playwright`
- Run: `playwright install chromium`
- Check credentials in `.env` file

---

## Reference Files

Use these as templates when creating new asset types:

- **Simple format**: `automation/abstract_impl.py` - Good for basic forms
- **Complex format**: `automation/journal_impl.py` - Has volume, issue, pages
- **Conference format**: `automation/presentations_impl.py` - Has conference fields

---

## Next Steps

After completing integration:

1. **Create pull request** (if using version control)
2. **Update team documentation**
3. **Train users on new asset type**
4. **Monitor for issues** in first few days
5. **Gather feedback** and iterate

---

## Additional Resources

- **Playwright Documentation**: https://playwright.dev/python/
- **Regex Testing**: https://regex101.com/
- **OpenAI API Docs**: https://platform.openai.com/docs/
- **Integration Steps**: See `Web App & Discord Bot Integration Steps.md`
