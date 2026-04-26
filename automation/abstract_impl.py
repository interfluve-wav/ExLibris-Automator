"""
Esploro automation for Abstracts.
Parses citations (OpenAI with conservative manual fallback), navigates with
Playwright, and fills the presentation form fields.
"""
# flow7_batch.py
import os
from dotenv import load_dotenv
import csv
import re
from typing import List, Dict
from utils.config_utils import extract_ordinal_word_number, get_additional_topics_for_channel
from utils.author_automation import fill_authors_if_enabled
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
        # Use manual regex parser as fallback
        return parse_citation(citation_text)

    # Handle errors from LLM parsers
    if "error" in llm_data:
        return llm_data

    # Normalize LLM results for abstracts
    try:
        # Clear conference-related fields for abstracts
        llm_data['published_proceedings_title'] = ''
        llm_data['conference_name'] = ''
        llm_data['conference_number'] = ''
        llm_data['conference_location'] = ''
        llm_data['conference_date_from'] = ''
        llm_data['conference_date_to'] = ''

        # Ensure abstract title is in proceedings_title field
        if not llm_data.get('proceedings_title'):
            llm_data['proceedings_title'] = llm_data.get('abstract_title', '')

        # Normalize numeric fields
        for field in ['volume', 'issue', 'start_page', 'end_page']:
            val = llm_data.get(field, '')
            if val:
                # Extract just the number if there's extra text
                m_num = re.search(r'(\d+)', str(val))
                if m_num:
                    llm_data[field] = m_num.group(1)

        # Clean DOI
        if llm_data.get('doi'):
            doi = llm_data['doi']
            # Remove "DOI:" prefix if present
            doi = re.sub(r'^(?:DOI[:\s]*)', '', doi, flags=re.I)
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
        for k in ['proceedings_title', 'publisher_name', 'volume', 'issue',
                  'start_page', 'end_page', 'doi', 'issn', 'eissn', 'year',
                  'date_presented', 'article_number']:
            if not llm_data.get(k) and manual.get(k):
                llm_data[k] = manual[k]

    return llm_data

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

def parse_citation(citation_text: str) -> Dict[str, str]:
    """Parse abstract-style citations like:
    Authors. (YYYY). Title. Publisher Name, Volume(Issue), pp. start-end. DOI: ... ISSN: ...
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

    # Remove parenthetical notes like "(Contributed 50%)" at the end
    text = re.sub(r"\s*\([^)]*Contributed[^)]*\)\s*$", "", text, flags=re.I)

    # Extract year: (YYYY) - simpler format for abstracts (no month/day typically)
    m_date = re.search(r"\((\d{4})\)", text)
    year = m_date.group(1) if m_date else ""

    # Extract authors (everything before the date)
    authors = ""
    if m_date:
        date_start = m_date.start()
        authors = text[:date_start].strip().rstrip(' .,')

    # Extract abstract title (between year and the publisher/journal section)
    abstract_title = ""
    after_title = ""
    if m_date:
        # Get text after the year, handle optional period after closing paren
        after_date = text[m_date.end():].strip()
        # Skip leading period if present (e.g., "(2024). Title..." -> "Title...")
        if after_date.startswith('.'):
            after_date = after_date[1:].strip()

        # Title ends at the next period (before publisher section)
        first_period = after_date.find('.')
        if first_period > 0:
            abstract_title = after_date[:first_period].strip()
            # Everything after the title period is publisher info
            after_title = after_date[first_period+1:].strip()
        else:
            # No period found, try to split at first comma
            first_comma = after_date.find(',')
            if first_comma > 0:
                abstract_title = after_date[:first_comma].strip()
                after_title = after_date[first_comma+1:].strip()
            else:
                # Fallback: entire text is the title
                abstract_title = after_date.strip()

    # Extract publisher name, volume, issue, pages
    publisher_name = ""
    volume = ""
    issue = ""
    start_page = ""
    end_page = ""
    article_number = ""

    # Pattern: Publisher Name, Volume(Issue), pp. start-end
    # Examples:
    #   Publisher Name, 12(3), pp. 23–40
    #   Publisher Name, 12, 23-40

    # Try to match publisher with volume/issue/pages
    m_pub = re.search(r"^\s*([^,]+),\s*(\d+)(?:\s*\((\d+)\))?\s*,?\s*(?:pp\.?\s*)?(\d+)\s*[-–]\s*(\d+)", after_title)
    if m_pub:
        publisher_name = m_pub.group(1).strip()
        volume = m_pub.group(2) or ""
        issue = (m_pub.group(3) or "").strip()
        start_page = m_pub.group(4)
        end_page = m_pub.group(5)
    else:
        # Fallback: try to get publisher name up to first comma
        m_name = re.match(r"^\s*([^,]+),", after_title)
        if m_name:
            publisher_name = m_name.group(1).strip()

    # Extract DOI if present
    doi = ""
    m_doi = re.search(r"(?:DOI[:\s]*)?(10\.\d{4,9}/\S+)", text, flags=re.I)
    if m_doi:
        doi = m_doi.group(1)

    # Extract ISSN/eISSN if present
    issn = ""
    eissn = ""
    m_issn = re.search(r"\bISSN[:\s]*([0-9]{4}-?[0-9]{3}[0-9Xx])", text)
    if m_issn:
        issn = m_issn.group(1).upper()
    m_eissn = re.search(r"\bE-?ISSN[:\s]*([0-9]{4}-?[0-9]{3}[0-9Xx])", text, flags=re.I)
    if m_eissn:
        eissn = m_eissn.group(1).upper()

    # Extract article number if present
    m_article = re.search(r"\b(?:Article\s+(?:No|Number)[:\s]*|Art\.\s*)?(\d{6,})\b", text, flags=re.I)
    if m_article:
        article_number = m_article.group(1)

    # Extract page numbers if present (fallback)
    if not start_page:
        m_pages = re.search(r"(?:pp?\.?\s*)?(\d+)(?:\s*[-–]\s*(\d+))?", text, flags=re.I)
        if m_pages:
            start_page = m_pages.group(1)
            if m_pages.group(2):
                end_page = m_pages.group(2)

    # Date fields for compatibility
    date_presented = year
    date_presented_mmddyyyy = ""
    date_presented_mmyyyy = ""

    return {
        "proceedings_title": abstract_title,  # Main title field
        "abstract_title": abstract_title,
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
        "volume": volume,
        "issue": issue,
        "start_page": start_page,
        "end_page": end_page,
        "article_number": article_number,
        "doi": doi,
        "issn": issn,
        "eissn": eissn,
        "research_topics": "",
        "link": link,
    }



def save_citation_to_csv(citation_data: Dict[str, str], output_file: str):
    """Save single citation to CSV (overwrites existing file)"""
    fieldnames = [
        "proceedings_title", "authors", "year", "date_presented", "publisher_name",
        "volume", "issue", "start_page", "end_page", "article_number",
        "doi", "issn", "eissn", "research_topics"
    ]

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        # Ignore any extra fields (e.g., 'link') not in fieldnames
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerow(citation_data)

def process_citation(page, citation_data: Dict[str, str], pause_after: bool = True, start_from_home: bool = True):
    """Fill one citation for Abstract asset type"""
    # Navigate to deposit wizard (optional)
    if start_from_home:
        try:
            page.get_by_role('link', name='Deposit Asset').click()
        except Exception:
            page.goto('https://umassd-researchmanagement.esploro.exlibrisgroup.com/ng;u=%2Fmng%2Faction%2Fhome.do%3FngHome%3Dtrue')
            page.get_by_role('link', name='Deposit Asset').click()


    # Select researcher and asset type
    researcher = (citation_data.get('researcher') or os.getenv('DEFAULT_RESEARCHER') or 'Scarano, Frank J').strip()
    page.get_by_role('textbox', name='Researcher').click()
    page.get_by_role('textbox', name='Researcher').fill(researcher)
    page.get_by_text(researcher).click()

    # Asset Type Selection - Abstract
    page.get_by_role('combobox', name='Select an item from the list').click()
    page.get_by_role('combobox', name='Asset type *').click()
    page.get_by_role('combobox', name='Asset type *').fill('Abstract')
    page.get_by_label('Publication <strong>').get_by_text('Abstract').click()
    page.get_by_role('button', name='Next').click()
    try:
        page.locator('#loadingBlocker').wait_for(state='hidden', timeout=10000)
    except Exception:
        page.wait_for_timeout(300)


    # Fill citation data - Abstract title
    page.get_by_role('textbox', name='Abstract title *').click()
    page.get_by_role('textbox', name='Abstract title *').fill(citation_data.get('proceedings_title', ''))


    # Fill Start Page
    try:
        start_page = citation_data.get('start_page', '').strip()
        if start_page:
            page.get_by_role('textbox', name='Start Page').click()
            page.get_by_role('textbox', name='Start Page').fill(start_page)
            print(f"✓ Filled start page: {start_page}")
    except Exception as e:
        print(f"✗ Start page error: {e}")

    # Fill End Page
    try:
        end_page = citation_data.get('end_page', '').strip()
        if end_page:
            page.get_by_role('textbox', name='End Page').click()
            page.get_by_role('textbox', name='End Page').fill(end_page)
            print(f"✓ Filled end page: {end_page}")
    except Exception as e:
        print(f"✗ End page error: {e}")

     # Fill Volume
    try:
        volume = (citation_data.get('volume') or citation_data.get('Volume') or '').strip()
        if volume:
            page.get_by_role('textbox', name='Volume').click()
            page.get_by_role('textbox', name='Volume').fill(volume)
            print(f"✓ Filled Volume: {volume}")
    except Exception as e:
        print(f"✗ Volume error: {e}")


    # Fill Issue
    try:
        issue = (citation_data.get('issue') or citation_data.get('Issue') or '').strip()
        if issue:
            page.get_by_role('textbox', name='Issue').click()
            page.get_by_role('textbox', name='Issue').fill(issue)
            print(f"✓ Filled Issue: {issue}")
    except Exception as e:
        print(f"✗ Issue error: {e}")

    # Fill Article Number
    try:
        article_number = (citation_data.get('article_number') or citation_data.get('Article number') or '').strip()
        if article_number:
            page.get_by_role('textbox', name='Article number').click()
            page.get_by_role('textbox', name='Article number').fill(article_number)
            print(f"✓ Filled Article number: {article_number}")
    except Exception as e:
        print(f"✗ Article number error: {e}")

    # Fill DOI
    try:
        doi = (citation_data.get('doi') or '').strip()
        if doi:
            # Some forms may have uppercase DOI or different casing
            page.get_by_role('textbox', name='DOI').click()
            page.get_by_role('textbox', name='DOI').fill(doi)
            print(f"✓ Filled DOI: {doi}")
    except Exception as e:
        print(f"⚠️ DOI fill skipped: {e}")

    # Fill ISSN / eISSN if present
    try:
        issn = (citation_data.get('issn') or '').strip()
        if issn:
            page.get_by_role('textbox', name='ISSN').click()
            page.get_by_role('textbox', name='ISSN').fill(issn)
            print(f"✓ Filled ISSN: {issn}")
    except Exception as e:
        print(f"⚠️ ISSN fill skipped: {e}")
    try:
        eissn = (citation_data.get('eissn') or '').strip()
        if eissn:
            # The field name might be 'eISSN' or 'E-ISSN'; try common option
            try:
                page.get_by_role('textbox', name='eISSN').click()
                page.get_by_role('textbox', name='eISSN').fill(eissn)
            except Exception:
                page.get_by_role('textbox', name='E-ISSN').click()
                page.get_by_role('textbox', name='E-ISSN').fill(eissn)
            print(f"✓ Filled eISSN: {eissn}")
    except Exception as e:
        print(f"⚠️ eISSN fill skipped: {e}")



    #timeout for parsing to complete
    page.wait_for_timeout(1500)

    # Add Date section (mirrors depositFlo.py)
    try:
        page.get_by_role('button', name=' Add Date').click()
        page.get_by_role('combobox', name='Date type *').click()
        page.get_by_label('Recent', exact=True).get_by_text('Date Presented').click()
        #page.get_by_role('combobox', name='Date type *').fill('Date Pre')
        #page.get_by_role('combobox', name='Date type *').press('ArrowDown')
        #page.locator('#ui-id-221').click()
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
    # Wait for loading blocker mask to disappear before filling subsequent fields
    try:
        page.locator('#loadingBlocker').wait_for(state='hidden', timeout=3000)
    except Exception:
        page.wait_for_timeout(500)

    # Add Language (Published)
    page.get_by_role('combobox', name='Language').click()
    page.get_by_label('Recent', exact=True).get_by_text('English', exact=True).click()
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

    # Additional 'Description and Research' topics (configurable via slash commands)
    try:
        channel_id = str(citation_data.get('channel_id') or '')
        topics: List[str] = get_additional_topics_for_channel(channel_id) if channel_id else []
        if topics:
            box = page.get_by_role('group', name='Description and Research').get_by_role('textbox').nth(2)
            box.click()
            for t in topics[:6]:
                box.fill(t)
                box.press('Enter')
            # Leave empty at end to close suggestions
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
    # Fill authors/creators (if enabled)
    fill_authors_if_enabled(page, citation_data)

    print("Add creators manually, then submit when ready.")
    if pause_after:
        input("Press Enter to continue...")

def main():
    print("=== Citation Processor ===")

    # Ask for citation input
    citation_text = input("Enter your citation: ").strip()

    if not citation_text:
        print("No citation entered. Exiting.")
        return

    print(f"Processing: {citation_text}")

    # Parse citation
    parser_type = os.getenv('CITATION_PARSER', DEFAULT_PARSER).lower()

    # Legacy support for USE_DEEPSEEK_PARSER
    if parser_type == DEFAULT_PARSER:
        env_toggle = os.getenv('USE_DEEPSEEK_PARSER')
        if env_toggle == '1':
            parser_type = "deepseek"

    if parser_type == "openai":
        print(f"Using OpenAI parser ({os.getenv('OPENAI_MODEL', 'gpt-4o-mini')})")
    elif parser_type == "deepseek":
        print(f"Using DeepSeek parser ({os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')})")
    else:
        print("Using manual regex parser")

    parsed_citation = parse_any_citation(citation_text)

    if "error" in parsed_citation:
        print(f"Error: {parsed_citation['error']}")
        return

    # Save to CSV (overwrites old ones)
    csv_file = 'citationsAbstracts.csv'
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
        page.goto('https://umassd-researchmanagement.esploro.exlibrisgroup.com/mng/login')
        page.get_by_role('textbox', name='User Name').fill('schitturi1_lib')
        page.get_by_role('textbox', name='Password').fill('suhaas123')
        page.get_by_role('button', name='Login').click()
        page.goto('https://umassd-researchmanagement.esploro.exlibrisgroup.com/ng;u=%2Fmng%2Faction%2Fhome.do%3FngHome%3Dtrue')
        # Process the citation (pause so you can review before closing)
        process_citation(page, parsed_citation, pause_after=True)
    print("Done!")

if __name__ == "__main__":
    main()
