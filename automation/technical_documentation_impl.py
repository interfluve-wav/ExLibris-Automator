"""
Esploro automation for Technical Documentation.
Parses citations (OpenAI with conservative manual fallback), navigates with
Playwright, and fills the technical documentation form fields.
"""
import os
from dotenv import load_dotenv
import csv
import re
from typing import List, Dict
from utils.config_utils import get_additional_topics_for_channel
from utils.logging_utils import make_logger
try:
    from openai_parser import parse_citation_with_openai
except Exception:
    parse_citation_with_openai = None
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

# Load environment variables from .env if present
load_dotenv()

# Citation parser configuration
DEFAULT_PARSER = "openai"  # Change to "manual" if needed

# Logger
LOG = make_logger("TECH_DOC")

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
            print("[parser] OpenAI returned empty, trying manual parser as fallback")
            return parse_citation(citation_text)
    else:
        print("[parser] Using manual regex parser")
        # Use manual regex parser as fallback
        return parse_citation(citation_text)

    # Handle errors from LLM parsers
    if "error" in llm_data:
        return llm_data

    # Normalize LLM results for technical documentation
    try:
        # Clear conference-related fields for technical documentation
        llm_data['published_proceedings_title'] = ''
        llm_data['conference_name'] = ''
        llm_data['conference_number'] = ''
        llm_data['conference_location'] = ''
        llm_data['conference_date_from'] = ''
        llm_data['conference_date_to'] = ''

        # Set asset_title from proceedings_title or article_title
        title = llm_data.get('proceedings_title') or llm_data.get('article_title') or llm_data.get('asset_title') or ''
        llm_data['asset_title'] = title
        llm_data['proceedings_title'] = title  # Keep for compatibility

        # Clean DOI
        if llm_data.get('doi'):
            doi = llm_data['doi']
            # Remove "DOI:" prefix if present
            doi = re.sub(r'^(?:DOI[:\s]*)', '', doi, flags=re.I)
            # Extract just the DOI part (10.xxxx/...)
            m = re.search(r'(10\.\d{4,9}/\S+)$', doi)
            if m:
                doi = m.group(1)
            llm_data['doi'] = doi.strip()

        # Ensure year is set
        if not llm_data.get('year'):
            m_year = re.search(r'\b(\d{4})\b', citation_text)
            if m_year:
                llm_data['year'] = m_year.group(1)

        llm_data['date_presented'] = llm_data.get('year', '')
    except Exception:
        pass

    # Fallback: if LLM misses critical fields, use manual parser
    try:
        title_candidate = (llm_data.get('proceedings_title') or '').strip()
        needs_fallback = (
            not title_candidate
            or len(title_candidate.strip('. ')) < 5
            or not llm_data.get('publisher_name')
        )
    except Exception:
        needs_fallback = False

    if needs_fallback:
        try:
            manual = parse_citation(citation_text)
        except Exception:
            manual = {}

        # Fill missing fields from manual parse
        for k in ['proceedings_title', 'publisher_name', 'report_number',
                  'doi', 'year', 'date_presented']:
            if not llm_data.get(k) and manual.get(k):
                llm_data[k] = manual[k]

    return llm_data

def goto_with_retries(page, url: str, attempts: int = 3, wait_until: str = 'load') -> bool:
    """Navigate with simple retries to mitigate transient net::ERR_CONNECTION_RESET."""
    for attempt in range(attempts):
        try:
            page.goto(url, wait_until=wait_until, timeout=30000)
            return True
        except Exception as e:
            if attempt == attempts - 1:
                print(f"✗ Navigation to {url} failed after {attempts} attempts: {e}")
                return False
            backoff_ms = (attempt + 1) * 2000
            print(f"… navigation error ({e}); retrying in {backoff_ms} ms [{attempt + 1}/{attempts}]")
            page.wait_for_timeout(backoff_ms)

def parse_citation(citation_text: str) -> Dict[str, str]:
    """Parse technical documentation citations like:
    Authors. (YYYY). Title. Publisher/Organization. Report No. XXX. DOI: ...
    """
    text = (citation_text or "").strip()
    if not text:
        return {"error": "Empty citation"}

    # Optional link (URL) anywhere in the citation
    link = ""
    try:
        m_link = re.search(r"(https?://[^\s)]+)", text)
        if m_link:
            # Strip trailing punctuation if present
            link = m_link.group(1).rstrip('.,);')
    except Exception:
        link = ""

    # Extract year: (YYYY)
    m_date = re.search(r"\((\d{4})\)", text)
    year = m_date.group(1) if m_date else ""

    # Extract authors (everything before the date)
    authors = ""
    if m_date:
        date_start = m_date.start()
        authors = text[:date_start].strip().rstrip(' .,')

    # Extract title (between year and the publisher/organization section)
    title = ""
    after_title = ""
    if m_date:
        # Get text after the year, handle optional period after closing paren
        after_date = text[m_date.end():].strip()
        # Skip leading period if present
        if after_date.startswith('.'):
            after_date = after_date[1:].strip()

        # Title ends at the next period (before publisher section)
        first_period = after_date.find('.')
        if first_period > 0:
            title = after_date[:first_period].strip()
            # Everything after the title period is publisher info
            after_title = after_date[first_period+1:].strip()
        else:
            # No period found, try to split at first comma
            first_comma = after_date.find(',')
            if first_comma > 0:
                title = after_date[:first_comma].strip()
                after_title = after_date[first_comma+1:].strip()
            else:
                # Fallback: entire text is the title
                title = after_date.strip()

    # Extract publisher name
    publisher_name = ""
    # Pattern: Publisher Name, ...
    m_pub = re.match(r"^([^,.]+)", after_title)
    if m_pub:
        publisher_name = m_pub.group(1).strip()

    # Extract report number if present
    report_number = ""
    m_report = re.search(r"(?:Report|Tech\.?\s*Report|Technical\s*Report|No\.?)\s*([A-Z0-9\-]+)", text, flags=re.I)
    if m_report:
        report_number = m_report.group(1)

    # Extract DOI if present
    doi = ""
    m_doi = re.search(r"(?:DOI[:\s]*)?(10\.\d{4,9}/\S+)", text, flags=re.I)
    if m_doi:
        doi = m_doi.group(1)

    # Date fields for compatibility
    date_presented = year
    date_presented_mmddyyyy = ""
    date_presented_mmyyyy = ""

    return {
        "proceedings_title": title,  # Main title field (kept for compatibility)
        "asset_title": title,  # Technical Documentation uses "Asset title"
        "authors": authors.rstrip(' .'),
        "year": year,
        "date_presented": date_presented,
        "date_presented_mmddyyyy": date_presented_mmddyyyy,
        "date_presented_mmyyyy": date_presented_mmyyyy,
        "conference_date_from": "",
        "conference_date_to": "",
        "published_proceedings_title": "",
        "conference_name": "",
        "conference_number": "",
        "conference_location": "",
        "publisher_name": publisher_name,
        "report_number": report_number,
        "doi": doi,
        "research_topics": "",
        "link": link,
    }



def save_citation_to_csv(citation_data: Dict[str, str], output_file: str):
    """Save single citation to CSV (overwrites existing file)"""
    fieldnames = [
        "proceedings_title", "authors", "year", "date_presented", "publisher_name",
        "report_number", "doi", "research_topics"
    ]

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        # Ignore any extra fields (e.g., 'link') not in fieldnames
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerow(citation_data)

def process_citation(page, citation_data: Dict[str, str], pause_after: bool = True, start_from_home: bool = True):
    """Fill one citation for Technical Documentation asset type"""
    LOG.info("Starting process_citation for Technical Documentation")

    # Navigate to deposit wizard (optional)
    if start_from_home:
        LOG.debug("Navigating to Deposit Asset page...")
        try:
            page.get_by_role('link', name='Deposit Asset').click(timeout=10000)
            LOG.debug("Clicked 'Deposit Asset' link")
        except Exception as e:
            LOG.debug(f"First click failed: {e}, navigating directly")
            page.goto('https://umassd-researchmanagement.esploro.exlibrisgroup.com/ng;u=%2Fmng%2Faction%2Fhome.do%3FngHome%3Dtrue', timeout=30000)
            page.get_by_role('link', name='Deposit Asset').click(timeout=10000)

    # Select researcher and asset type
    LOG.debug("Selecting researcher...")
    researcher = (citation_data.get('researcher') or os.getenv('DEFAULT_RESEARCHER') or 'Scarano, Frank J').strip()
    # Wait for the form to load
    try:
        page.get_by_role('textbox', name='Researcher').wait_for(timeout=10000)
    except Exception:
        LOG.debug("Researcher field wait timeout, continuing anyway")
        page.wait_for_timeout(1000)
    page.get_by_role('textbox', name='Researcher').click(timeout=5000)
    page.get_by_role('textbox', name='Researcher').fill(researcher, timeout=5000)
    page.get_by_text(researcher).click(timeout=5000)
    LOG.debug(f"Researcher selected: {researcher}")

    # Asset Type Selection - Technical Documentation
    LOG.debug("Selecting asset type: Technical documentation")
    page.get_by_role('combobox', name='Select an item from the list').click(timeout=5000)
    page.get_by_role('combobox', name='Asset type *').click(timeout=5000)
    page.get_by_role('combobox', name='Asset type *').fill('Technical documentation', timeout=5000)
    page.get_by_label('Publication <strong>').get_by_text('Technical documentation ').click(timeout=5000)
    LOG.debug("Asset type selected, clicking Next")
    page.get_by_role('button', name='Next').click(timeout=5000)
    LOG.debug("Waiting for loading blocker to disappear...")
    try:
        page.locator('#loadingBlocker').wait_for(state='hidden', timeout=8000)
        LOG.debug("Loading blocker hidden")
    except Exception:
        LOG.debug("Loading blocker timeout, continuing anyway")
        page.wait_for_timeout(300)


    # Fill citation data - Asset title (autocomplete field)
    title_value = citation_data.get('proceedings_title', '')
    LOG.info(f"Attempting to fill Asset title: '{title_value}'")
    try:
        # This is an autocomplete field - just type the title and press Escape to dismiss suggestions
        # Use ID to avoid ambiguity with other similar fields (e.g. publication title)
        page.locator('#pageBeanassetrecordtitle').click(timeout=5000)
        page.locator('#pageBeanassetrecordtitle').fill(title_value)
        # Wait briefly for autocomplete suggestions to appear (if any)
        page.wait_for_timeout(500)
        # Press Escape to dismiss autocomplete dropdown and keep our typed value
        page.keyboard.press('Escape')
        page.wait_for_timeout(200)
        LOG.info(f"✓ Filled Asset title")
    except Exception as e:
        LOG.warn(f"Asset title field error: {e}")
        LOG.warn(f"Trying alternate approach...")
        # Try by label if placeholder doesn't work
        try:
            page.get_by_label('Asset title').click(timeout=3000)
            page.get_by_label('Asset title').fill(title_value)
            page.keyboard.press('Escape')
            page.wait_for_timeout(200)
            LOG.info(f"✓ Filled Asset title (via label)")
        except Exception as e2:
            LOG.error(f"Could not locate Asset title field: {e2}")

    # Timeout for parsing to complete
    page.wait_for_timeout(1500)

    # Fill Publisher/Organization
    try:
        publisher = citation_data.get('publisher_name', '').strip()
        if publisher:
            page.get_by_role('textbox', name='Publisher name').click(timeout=5000)
            page.get_by_role('textbox', name='Publisher name').fill(publisher, timeout=5000)
            LOG.info(f"✓ Filled publisher: {publisher}")
    except Exception as e:
        LOG.warn(f"Publisher fill skipped: {e}")

    # Fill Report Number if present
    try:
        report_number = citation_data.get('report_number', '').strip()
        if report_number:
            page.get_by_role('textbox', name='Report number').click(timeout=5000)
            page.get_by_role('textbox', name='Report number').fill(report_number, timeout=5000)
            LOG.info(f"✓ Filled report number: {report_number}")
    except Exception as e:
        LOG.warn(f"Report number fill skipped: {e}")

    # Add Date section
    try:
        page.get_by_role('button', name=' Add Date').click(timeout=5000)
        page.get_by_role('combobox', name='Date type *').click(timeout=5000)
        page.get_by_label('Recent', exact=True).get_by_text('Date Presented').click(timeout=5000)
        page.get_by_role('textbox', name='Choose date *').click(timeout=5000)
        # Prefer MM/DD/YYYY, then MM/YYYY, else fallback to YYYY
        date_to_fill = (
            citation_data.get('date_presented_mmddyyyy')
            or citation_data.get('date_presented_mmyyyy')
            or citation_data.get('year', '')
        )
        page.get_by_role('textbox', name='Choose date *').fill(date_to_fill, timeout=5000)
        page.get_by_role('button', name='Add and close').click(timeout=5000)
        LOG.info("✓ Added date")
    except Exception as e:
        LOG.error(f"Failed to add date: {e}")

    # Wait for loading blocker mask to disappear before filling subsequent fields
    try:
        page.locator('#loadingBlocker').wait_for(state='hidden', timeout=3000)
    except Exception:
        page.wait_for_timeout(300)

    # Add small wait before publisher fields
    page.wait_for_timeout(300)

    # Add Language (Published)
    page.get_by_role('combobox', name='Language').click(timeout=5000)
    page.get_by_label('Recent', exact=True).get_by_text('English', exact=True).click(timeout=5000)
    # Ensure the language dropdown/autocomplete closes so it doesn't intercept clicks later
    try:
        page.keyboard.press('Escape')
        page.wait_for_timeout(100)
    except Exception:
        pass
    try:
        # Click an inert area to defocus any open menus
        page.mouse.click(5, 5)
        page.wait_for_timeout(100)
    except Exception:
        pass

    # Fill DOI
    try:
        doi = (citation_data.get('doi') or '').strip()
        if doi:
            page.get_by_role('textbox', name='DOI').click(timeout=5000)
            page.get_by_role('textbox', name='DOI').fill(doi, timeout=5000)
            LOG.info(f"✓ Filled DOI: {doi}")
    except Exception as e:
        LOG.warn(f"DOI fill skipped: {e}")

    # Additional 'Description and Research' topics (configurable via slash commands)
    try:
        channel_id = str(citation_data.get('channel_id') or '')
        topics: List[str] = get_additional_topics_for_channel(channel_id) if channel_id else []
        if topics:
            box = page.get_by_role('group', name='Description and Research').get_by_role('textbox').nth(2)
            box.click(timeout=5000)
            for t in topics[:6]:
                box.fill(t, timeout=5000)
                box.press('Enter')
            # Leave empty at end to close suggestions
            try:
                box.fill('', timeout=2000)
            except Exception:
                pass
            LOG.info(f"✓ Filled additional topics: {', '.join(topics[:6])}")
        else:
            LOG.info("No additional topics configured for this channel")
    except Exception as e:
        LOG.warn(f"Additional topics fill skipped: {e}")

    # Fill authors/creators (if enabled)
    try:
        # Check if auto-fill authors is enabled in config
        auto_fill_enabled = True  # Default to True for backward compatibility
        try:
            bot_config_path = os.getenv('BOT_CONFIG_PATH', 'bot_config.json')
            if os.path.exists(bot_config_path):
                with open(bot_config_path, 'r', encoding='utf-8') as f:
                    import json as json_module
                    bot_config = json_module.load(f)
                    auto_fill_enabled = bot_config.get('auto_fill_authors', True)
        except Exception:
            pass  # If config can't be read, default to True

        if auto_fill_enabled:
            authors = citation_data.get('authors', '').strip()
            if authors:
                # Import fill_authors from presentations_impl
                try:
                    from automation.presentations_impl import fill_authors
                    fill_authors(page, authors)
                except Exception as e:
                    LOG.warn(f"Authors fill error: {e}")
            else:
                LOG.info("No authors found in citation data")
        else:
            LOG.info("Author automation disabled (skip filling)")
    except Exception as e:
        LOG.warn(f"Authors fill error: {e}")

    LOG.info(f"✓ Form filled for: {citation_data.get('proceedings_title', '')}")
    if not auto_fill_enabled:
        LOG.info("Add creators manually, then submit when ready.")
    if pause_after:
        input("Press Enter to continue...")

def main():
    print("=== Citation Processor (Technical Documentation) ===")

    # Ask for citation input
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

    # Save to CSV (overwrites old ones)
    csv_file = 'citationsTechnicalDocumentation.csv'
    save_citation_to_csv(parsed_citation, csv_file)
    print(f"✓ Saved to {csv_file}")

    # Show parsed data
    print("\nParsed citation data:")
    for key, value in parsed_citation.items():
        if value:
            print(f"  {key}: {value}")

    # Automatically continue to automation after parsing and saving the CSV

    if sync_playwright is None:
        print("Playwright not installed; skipping automation. Parser output saved.")
        return

    print("\n=== Starting browser automation ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        # Login
        username = os.getenv('ESPLORO_USERNAME', '').strip()
        password = os.getenv('ESPLORO_PASSWORD', '').strip()
        page.goto('https://umassd-researchmanagement.esploro.exlibrisgroup.com/mng/login')
        page.get_by_role('textbox', name='User Name').fill(username)
        page.get_by_role('textbox', name='Password').fill(password)
        page.get_by_role('button', name='Login').click()
        page.goto('https://umassd-researchmanagement.esploro.exlibrisgroup.com/ng;u=%2Fmng%2Faction%2Fhome.do%3FngHome%3Dtrue')
        # Process the citation (pause so you can review before closing)
        process_citation(page, parsed_citation, pause_after=True)
    print("Done!")

if __name__ == "__main__":
    main()
