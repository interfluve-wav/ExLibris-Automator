"""
Esploro automation for Journal Articles.
Parses citations (OpenAI with conservative manual fallback), navigates with
Playwright, and fills the Journal Article form fields.
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
    """Parse using OpenAI or manual regex parser based on configuration (journal article)."""
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

    # Normalize LLM results for book chapters
    try:
        # Ensure journal article fields exist
        for field in ['journal_name', 'volume', 'issue', 'start_page', 'end_page', 'doi', 'issn', 'eissn']:
            if field not in llm_data:
                llm_data[field] = ''

        # Map common LLM field variants
        if not llm_data.get('proceedings_title'):
            # prefer explicit title keys if present
            llm_data['proceedings_title'] = llm_data.get('article_title') or llm_data.get('title') or ''
        else:
            # also expose article_title for clarity
            if not llm_data.get('article_title'):
                llm_data['article_title'] = llm_data['proceedings_title']
        if not llm_data.get('journal_name'):
            llm_data['journal_name'] = llm_data.get('journal') or llm_data.get('journal_title') or llm_data.get('source') or ''
        # Pages string normalization (e.g., "23-40" or "23–40")
        pages_str = (llm_data.get('pages') or '').strip()
        if pages_str and (not llm_data.get('start_page') and not llm_data.get('end_page')):
            m = re.match(r"^\s*(\d+)\s*[-–]\s*(\d+)\s*$", pages_str)
            if m:
                llm_data['start_page'] = m.group(1)
                llm_data['end_page'] = m.group(2)
        # Normalize DOI (strip URL prefix)
        if llm_data.get('doi'):
            m = re.search(r"(10\.\d{4,9}/\S+)$", str(llm_data['doi']))
            if m:
                llm_data['doi'] = m.group(1)
        # Normalize ISSN/eISSN (keep hyphen if present, strip spaces)
        for k in ['issn', 'eissn']:
            if llm_data.get(k):
                llm_data[k] = re.sub(r'\s', '', str(llm_data[k]))

        # For journal articles, date_presented should typically just be the year
        if not llm_data.get('date_presented'):
            llm_data['date_presented'] = llm_data.get('year', '')

        # Clear conference-specific fields
        llm_data['conference_name'] = ''
        llm_data['conference_number'] = ''
        llm_data['conference_location'] = ''
        llm_data['conference_date_from'] = ''
        llm_data['conference_date_to'] = ''
        llm_data['published_proceedings_title'] = ''

        # Compatibility shims for rest of system
        # Use book_title to carry journal name for legacy fills
        if not llm_data.get('book_title') and llm_data.get('journal_name'):
            llm_data['book_title'] = llm_data['journal_name']

        # Fallback: if LLM misses article title or journal title, try manual parser
        needs_fallback = (
            not llm_data.get('proceedings_title') or
            not (llm_data.get('journal_name') or llm_data.get('book_title')) or
            len((llm_data.get('proceedings_title') or '').strip()) < 5
        )

        if needs_fallback:
            try:
                manual = parse_citation(citation_text)
                if manual:
                    if (not llm_data.get('proceedings_title')) and manual.get('proceedings_title'):
                        llm_data['proceedings_title'] = manual['proceedings_title']
                    # Prefer journal_name, but also mirror into book_title for compatibility
                    if not llm_data.get('journal_name') and manual.get('journal_name'):
                        llm_data['journal_name'] = manual['journal_name']
                    if not llm_data.get('book_title') and (manual.get('journal_name') or manual.get('book_title')):
                        llm_data['book_title'] = manual.get('journal_name') or manual.get('book_title')
                    # Fill other missing fields from manual parse
                    for k in ['start_page', 'end_page', 'volume', 'issue', 'doi', 'issn', 'eissn', 'year', 'authors']:
                        if not llm_data.get(k) and manual.get(k):
                            llm_data[k] = manual[k]
            except Exception:
                pass
    except Exception:
        pass

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
    """Parse common journal article citations like:
    Authors. (YYYY). Article Title. Journal Name, Volume(Issue), pp. start–end. https://doi.org/10.xxxx/xxxxx
    """
    text = (citation_text or "").strip()
    if not text:
        return {"error": "Empty citation"}

    # Optional link (URL) anywhere in the citation
    link = ""
    try:
        m_link = re.search(r"(https?://[^\s)]+)", text)
        if m_link:
            link = m_link.group(1).rstrip('.,);')
    except Exception:
        link = ""

    # Remove parenthetical notes like "(Contributed 50%)" at the end
    text = re.sub(r"\s*\([^)]*Contributed[^)]*\)\s*$", "", text, flags=re.I)

    # Extract year: prefer (YYYY), fallback to standalone year token
    m_date = re.search(r"\((\d{4})\)", text)
    if m_date:
        year = m_date.group(1)
    else:
        m_year = re.search(r"\b(19|20)\d{2}\b", text)
        year = m_year.group(0) if m_year else ""

    # Extract authors (everything before the date)
    authors = ""
    if m_date:
        date_start = m_date.start()
        authors = text[:date_start].strip().rstrip(' .,')

    # Extract article title (between year and the journal name sentence)
    article_title = ""
    if m_date:
        after_date = text[m_date.end():].strip()
        # Handle common "(YYYY). Title..." format.
        if after_date.startswith('.'):
            after_date = after_date[1:].strip()
        # Article title is up to the next period before journal section
        first_period = after_date.find('.')
        if first_period > 0:
            article_title = after_date[:first_period].strip().rstrip(' .')

    # Extract journal name, volume, issue, pages
    journal_name = ""
    volume = ""
    issue = ""
    start_page = ""
    end_page = ""
    # Pattern: Journal Name, Volume(Issue), pages
    # Examples:
    #   Journal of Something, 12(3), 23–40.
    #   Journal of Something, 12, 23-40.
    # We'll search after the article title period
    after_title = ""
    if m_date:
        after_title = text[m_date.end():].strip()
        p = after_title.find('.')
        after_title = after_title[p+1:].strip() if p >= 0 else after_title
    m_j = re.search(r"^\s*([^,]+),\s*(\d+)(?:\s*\((\d+)\))?\s*,?\s*(?:pp\.?\s*)?(\d+)\s*[-–]\s*(\d+)", after_title)
    if m_j:
        journal_name = m_j.group(1).strip()
        volume = m_j.group(2) or ""
        issue = (m_j.group(3) or "").strip()
        start_page = m_j.group(4)
        end_page = m_j.group(5)
    else:
        # Fallback for compact citations:
        # "A. Author, B. Author, Title..., Journal Name, 14 (2), 2017, 283-305"
        m_compact = re.search(
            r",\s*([^,]+),\s*(\d+)\s*\((\d+)\)\s*,\s*((?:19|20)\d{2})\s*,\s*(\d+)\s*[-–]\s*(\d+)\s*\.?\s*$",
            text,
        )
        if m_compact:
            journal_name = m_compact.group(1).strip()
            volume = m_compact.group(2).strip()
            issue = m_compact.group(3).strip()
            year = year or m_compact.group(4).strip()
            start_page = m_compact.group(5).strip()
            end_page = m_compact.group(6).strip()

            prefix = text[:m_compact.start()].strip().rstrip(" ,.")
            # Parse leading comma-separated author tokens, then remainder as title.
            # Supports tokens like "Z. Qiao" and "Qiao, Z."
            author_token = re.compile(
                r"^(?:"
                r"(?:[A-Z]\.\s*)+[A-Z][A-Za-z'`-]+"
                r"|"
                r"[A-Z][A-Za-z'`-]+,\s*(?:[A-Z]\.?\s*)+"
                r")$"
            )
            parts = [p.strip() for p in prefix.split(",") if p.strip()]
            author_parts = []
            i = 0
            while i < len(parts) and author_token.match(parts[i]):
                author_parts.append(parts[i])
                i += 1
            if author_parts:
                authors = ", ".join(author_parts)
                article_title = ", ".join(parts[i:]).strip().rstrip(" .")

        # Fallback: try to get journal name up to first comma
        if not journal_name:
            m_name = re.match(r"^\s*([^,]+),", after_title)
            if m_name:
                journal_name = m_name.group(1).strip()
    # Extract DOI if present
    doi = ""
    m_doi = re.search(r"(10\.\d{4,9}/\S+)", text, flags=re.I)
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

    # Extract page numbers if present (fallback)
    m_pages = re.search(r"(?:pp?\.?\s*)?(\d+)(?:\s*[-–]\s*(\d+))?", text, flags=re.I)
    if m_pages:
        if not start_page:
            start_page = m_pages.group(1)
        if not end_page and m_pages.group(2):
            end_page = m_pages.group(2)

    # Date fields for compatibility (book chapters typically only have year)
    date_presented = year
    date_presented_mmddyyyy = ""
    date_presented_mmyyyy = ""
    return {
        "proceedings_title": article_title,  # Article title (compatibility field)
        "article_title": article_title,
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
        "journal_name": journal_name,
        # Compatibility: some flows still read book_title
        "book_title": journal_name,
        "volume": volume,
        "issue": issue,
        "start_page": start_page,
        "end_page": end_page,
        "doi": doi,
        "issn": issn,
        "eissn": eissn,
        "research_topics": "",
        "link": link,
    }

def save_citation_to_csv(citation_data: Dict[str, str], output_file: str):
    """Save single citation to CSV (overwrites existing file)"""
    fieldnames = [
        "proceedings_title", "authors", "year", "date_presented", "published_proceedings_title",
        "conference_name", "conference_number", "conference_location", "research_topics"
    ]

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        # Ignore any extra fields (e.g., 'link') not in fieldnames
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerow(citation_data)

def process_citation(page, citation_data: Dict[str, str], pause_after: bool = True, start_from_home: bool = True):
    """Fill one citation using flow7 logic"""
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
    page.locator("a.dropdown-item.ui-menu-item-wrapper").filter(has_text=researcher).first.click()

  # Asset Type Selection

    # For Journal Article
    page.get_by_role('combobox', name='Select an item from the list').click()
    page.get_by_role('combobox', name='Asset type *').click()
    page.get_by_role('combobox', name='Asset type *').fill('Journal article')
    page.get_by_label('Publication <strong>').get_by_text('Journal article').click()
    page.get_by_role('button', name='Next').click()
    try:
        page.locator('#loadingBlocker').wait_for(state='hidden', timeout=10000)
    except Exception:
        page.wait_for_timeout(300)

  # For Conference Proceedings
  #  page.get_by_role('combobox', name='Select an item from the list').click()
  #  page.get_by_role('combobox', name='Asset type *').fill('Conference Proc')   #Change fill type to use other asset type
  #  page.get_by_label('Publication <strong>').get_by_text('Conference proceeding').click() #Change get by text type to use other asset type
  #  page.get_by_role('button', name='Next').click()

  # For Journal Article
  #  page.get_by_role('combobox', name='Select an item from the list').click()
  #  page.get_by_role('combobox', name='Asset type *').fill('Journal article')   #Change fill type to use other asset type
  #  page.get_by_label('Publication <strong>').get_by_text('Journal article').click() #Change get by text type to use other asset type
  #  page.get_by_role('button', name='Next').click()


    # Fill citation data
    page.get_by_role('textbox', name='Article title *').click()
    page.get_by_role('textbox', name='Article title *').fill(
        citation_data.get('proceedings_title') or citation_data.get('article_title') or ''
    )

    #timeout for parsing to complete
    page.wait_for_timeout(1500)

    # Add Date section (mirrors depositFlo.py)
    try:
        page.get_by_role('button', name=' Add Date').click()
        page.get_by_role('combobox', name='Date type *').click()
        page.get_by_label('Recent', exact=True).get_by_text('Published').click()
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
    try:
        page.get_by_role('combobox', name='Language').click()
        page.get_by_label('Recent', exact=True).get_by_text('English', exact=True).click()
        # Ensure the language dropdown/autocomplete closes
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
    except Exception as e:
        print(f"✗ Language selection error: {e}")

    # Add small wait before journal fields
    page.wait_for_timeout(500)

    # Fill Journal Name
    try:
        journal_name = (citation_data.get('journal_name') or citation_data.get('book_title') or '').strip()
        if journal_name:
            page.get_by_role('textbox', name='Journal name').click()
            page.get_by_role('textbox', name='Journal name').fill(journal_name)
            print(f"✓ Filled journal name: {journal_name}")
        else:
            print("⚠️ Journal name is empty; skipping fill")
    except Exception as e:
        print(f"✗ Journal name error: {e}")

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

    # Incorporate additional field - (Research topics)
    #page.get_by_role('combobox', name='Select an item from the list').click()
    #page.get_by_role('combobox', name='Research topics').fill('bioengineering')
    #page.get_by_text('bioengineering').click()
    #page.get_by_role('combobox', name='Research topics').fill('orthopedics')
    #page.get_by_text('orthopedics').click()

    # Research Topics
#    page.get_by_role("textbox", name="Research topics").fill("Nursing")
#    page.get_by_role("textbox", name="Research topics").press("ArrowDown")
#    page.get_by_text('Nursing').click()
#    page.get_by_role("textbox", name="Research topics").fill("Nursing Education")
#    page.get_by_role("textbox", name="Research topics").press("ArrowDown")
#    page.get_by_role("textbox", name="Research topics").press("Enter")
#    page.get_by_role("textbox", name="Research topics").fill("")


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
    csv_file = 'citationsPresentations.csv'
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
