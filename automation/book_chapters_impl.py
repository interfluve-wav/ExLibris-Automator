"""
Esploro automation for Book Chapters.
Parses citations (OpenAI with conservative manual fallback), navigates with
Playwright, and fills the book chapter form fields.
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

    # Normalize LLM results for book chapters
    try:
        # Ensure book chapter fields exist
        for field in ['book_title', 'editors', 'publication_place', 'start_page', 'end_page', 'isbn', 'eisbn', 'edition']:
            if field not in llm_data:
                llm_data[field] = ''

        # Normalize ISBN (remove hyphens/spaces)
        if llm_data.get('isbn'):
            llm_data['isbn'] = re.sub(r'[-\s]', '', llm_data['isbn'])
        if llm_data.get('eisbn'):
            llm_data['eisbn'] = re.sub(r'[-\s]', '', llm_data['eisbn'])

        # Normalize edition (extract number only)
        if llm_data.get('edition'):
            ed_match = re.search(r'(\d+)', str(llm_data['edition']))
            if ed_match:
                llm_data['edition'] = ed_match.group(1)

        # For book chapters, date_presented should typically just be the year
        if not llm_data.get('date_presented'):
            llm_data['date_presented'] = llm_data.get('year', '')

        # Clear conference-specific fields for book chapters
        llm_data['conference_name'] = ''
        llm_data['conference_number'] = ''
        llm_data['conference_location'] = ''
        llm_data['conference_date_from'] = ''
        llm_data['conference_date_to'] = ''
        llm_data['published_proceedings_title'] = ''

        # Fallback: if LLM misses chapter title or book title, try manual parser
        needs_fallback = (
            not llm_data.get('proceedings_title') or
            not llm_data.get('book_title') or
            len((llm_data.get('proceedings_title') or '').strip()) < 5
        )

        if needs_fallback:
            try:
                manual = parse_citation(citation_text)
                if manual:
                    if not llm_data.get('proceedings_title') and manual.get('proceedings_title'):
                        llm_data['proceedings_title'] = manual['proceedings_title']
                    if not llm_data.get('book_title') and manual.get('book_title'):
                        llm_data['book_title'] = manual['book_title']
                    # Fill other missing fields from manual parse
                    for k in ['editors', 'publication_place', 'start_page', 'end_page', 'isbn', 'eisbn', 'edition', 'year', 'authors']:
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
    """Parse book chapter-style citations like:
    Authors. (YYYY). Chapter Title. In Editor1, E. and Editor2, E. (Eds) Book Title. City, State: Publisher.
    Example: Goldstein, R., Macrine, S., and Chesky, N. (2011). Competing Definitions of Hope in Obama's Education Marketplace: Media Representations of School Reform, Equality, and Social Justice. In Carr, P. and Porfilio, B. (Eds) The Phenomenon of Obama and the Agenda for Education. NC: Charlotte: Information age Publishing.
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

    # Extract year: (YYYY)
    m_date = re.search(r"\((\d{4})\)", text)
    year = m_date.group(1) if m_date else ""

    # Extract authors (everything before the date)
    authors = ""
    if m_date:
        date_start = m_date.start()
        authors = text[:date_start].strip().rstrip(' .,')

    # Extract chapter title (between year and "In")
    chapter_title = ""
    if m_date:
        after_date = text[m_date.end():].strip()
        # Handle common "(YYYY). Title..." format.
        if after_date.startswith('.'):
            after_date = after_date[1:].strip()
        # Look for "In" followed by editor names
        m_in = re.search(r"\.\s+In\s+", after_date, flags=re.I)
        if m_in:
            chapter_title = after_date[:m_in.start()].strip().rstrip(' .')
        else:
            # Fallback: take first sentence after date
            first_period = after_date.find('.')
            if first_period > 0:
                chapter_title = after_date[:first_period].strip()

    # Extract editors and book title
    editors = ""
    book_title = ""
    publication_place = ""
    publisher = ""
    start_page = ""
    end_page = ""
    isbn = ""
    eisbn = ""
    edition = ""

    # Look for "In Editor1, E. and Editor2, E. (Eds) Book Title"
    m_in_editors = re.search(r"\.\s+In\s+(.+?)\s*\(Eds?\)\s*(.+?)(?:\.|$)", text, flags=re.I)
    if m_in_editors:
        editors = m_in_editors.group(1).strip().rstrip(' .,')
        # Book title is the next part until publisher info
        book_part = m_in_editors.group(2).strip()

        # Try to extract publication place and publisher
        # Pattern: "Book Title. State: City: Publisher" or "Book Title. City, State: Publisher"
        # Look for patterns like "NC: Charlotte: Information age Publishing" or "Charlotte, NC: Information age Publishing"
        pub_patterns = [
            r"^(.+?)\.\s*([A-Z]{2}):\s*([^:]+):\s*(.+)$",  # State: City: Publisher
            r"^(.+?)\.\s*([^,]+),\s*([A-Z]{2}):\s*(.+)$",  # City, State: Publisher
            r"^(.+?)\.\s*([^:]+):\s*(.+)$",  # City: Publisher (fallback)
        ]

        for pattern in pub_patterns:
            m_pub = re.search(pattern, book_part)
            if m_pub:
                if len(m_pub.groups()) == 4:
                    if ':' in m_pub.group(2) and ':' in m_pub.group(3):
                        # State: City: Publisher format
                        book_title = m_pub.group(1).strip()
                        state = m_pub.group(2).strip()
                        city = m_pub.group(3).strip()
                        publisher = m_pub.group(4).strip()
                        publication_place = f"{city}, {state}"
                    else:
                        # City, State: Publisher format
                        book_title = m_pub.group(1).strip()
                        city = m_pub.group(2).strip()
                        state = m_pub.group(3).strip()
                        publisher = m_pub.group(4).strip()
                        publication_place = f"{city}, {state}"
                elif len(m_pub.groups()) == 3:
                    # City: Publisher format
                    book_title = m_pub.group(1).strip()
                    city = m_pub.group(2).strip()
                    publisher = m_pub.group(3).strip()
                    publication_place = city
                break

        # If no publisher pattern matched, book_title is everything before the last period
        if not book_title:
            last_period = book_part.rfind('.')
            if last_period > 0:
                book_title = book_part[:last_period].strip()
            else:
                book_title = book_part.strip()

    # Extract page numbers if present (e.g., "pp. 23-40" or "23-40" or "23")
    m_pages = re.search(r"(?:pp?\.?\s*)?(\d+)(?:\s*[-–]\s*(\d+))?", text, flags=re.I)
    if m_pages:
        start_page = m_pages.group(1)
        if m_pages.group(2):
            end_page = m_pages.group(2)

    # Extract ISBN (10 or 13 digits, may have hyphens)
    m_isbn = re.search(r"(?:ISBN[:\s-]*)?(\d{3}[- ]?\d{1}[- ]?\d{3}[- ]?\d{5}[- ]?\d|978[- ]?\d{1}[- ]?\d{3}[- ]?\d{5}[- ]?\d)", text)
    if m_isbn:
        isbn = re.sub(r'[-\s]', '', m_isbn.group(1))

    # Extract eISBN (may be labeled as e-ISBN or eISBN)
    m_eisbn = re.search(r"(?:e-?ISBN[:\s-]*|eISBN[:\s-]*)(\d{3}[- ]?\d{1}[- ]?\d{3}[- ]?\d{5}[- ]?\d|978[- ]?\d{1}[- ]?\d{3}[- ]?\d{5}[- ]?\d)", text, flags=re.I)
    if m_eisbn:
        eisbn = re.sub(r'[-\s]', '', m_eisbn.group(1))

    # Extract edition (e.g., "1st edition", "2nd ed.", "Edition 1")
    m_edition = re.search(r"(?:(\d+)(?:st|nd|rd|th)?\s*(?:edition|ed\.?)|Edition\s*(\d+))", text, flags=re.I)
    if m_edition:
        edition = m_edition.group(1) or m_edition.group(2) or ""

    # Date fields for compatibility (book chapters typically only have year)
    date_presented = year
    date_presented_mmddyyyy = ""
    date_presented_mmyyyy = ""
    return {
        "proceedings_title": chapter_title,  # Chapter title (reusing field name for compatibility)
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
        "book_title": book_title,
        "editors": editors,
        "publication_place": publication_place,
        "start_page": start_page,
        "end_page": end_page,
        "isbn": isbn,
        "eisbn": eisbn,
        "edition": edition,
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
    page.get_by_text(researcher).click()

  # Asset Type Selection

    # For Book Chapter
    page.get_by_role('combobox', name='Select an item from the list').click()
    page.get_by_role('combobox', name='Asset type *').click()
    page.get_by_role('combobox', name='Asset type *').fill('Book chapter')   #Change fill type to use other asset type
    page.get_by_label('Publication <strong>').get_by_text('Book chapter').click() #Change get by text type to use other asset type
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
    page.get_by_role('textbox', name='Chapter title *').click()
    page.get_by_role('textbox', name='Chapter title *').fill(citation_data.get('proceedings_title', ''))

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

    # Add small wait before book chapter fields
    page.wait_for_timeout(500)

    # Fill Book Title
    try:
        book_title = citation_data.get('book_title', '').strip()
        if book_title:
            page.get_by_role('textbox', name='Book title').click()
            page.get_by_role('textbox', name='Book title').fill(book_title)
            print(f"✓ Filled book title: {book_title}")
        else:
            print("⚠️ Book title is empty; skipping fill")
    except Exception as e:
        print(f"✗ Book title error: {e}")

    # Fill Publication Place
    try:
        pub_place = citation_data.get('publication_place', '').strip()
        if pub_place:
            page.get_by_role('textbox', name='Publication Place').click()
            page.get_by_role('textbox', name='Publication Place').fill(pub_place)
            print(f"✓ Filled publication place: {pub_place}")
    except Exception as e:
        print(f"✗ Publication place error: {e}")

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

    # Fill ISBN
    try:
        isbn = citation_data.get('isbn', '').strip()
        if isbn:
            page.get_by_role('textbox', name='ISBN').click()
            page.get_by_role('textbox', name='ISBN').fill(isbn)
            print(f"✓ Filled ISBN: {isbn}")
    except Exception as e:
        print(f"✗ ISBN error: {e}")

    # Fill eISBN
    try:
        eisbn = citation_data.get('eisbn', '').strip()
        if eisbn:
            page.get_by_role('textbox', name='eISBN').click()
            page.get_by_role('textbox', name='eISBN').fill(eisbn)
            print(f"✓ Filled eISBN: {eisbn}")
    except Exception as e:
        print(f"✗ eISBN error: {e}")

    # Fill Edition
    try:
        edition = citation_data.get('edition', '').strip()
        if edition:
            page.get_by_role('textbox', name='Edition').click()
            page.get_by_role('textbox', name='Edition').fill(edition)
            print(f"✓ Filled edition: {edition}")
    except Exception as e:
        print(f"✗ Edition error: {e}")

    # Fill Volume
    try:
        volume = citation_data.get('volume', '').strip()
        if volume:
            page.get_by_role('textbox', name='Volume').click()
            page.get_by_role('textbox', name='Volume').fill(volume)
            print(f"✓ Filled volume: {volume}")
    except Exception as e:
        print(f"✗ Volume error: {e}")

    # Fill Publisher
    try:
        publisher = citation_data.get('publisher_name', '').strip()
        if publisher:
            page.get_by_role('textbox', name='Publisher').click()
            page.get_by_role('textbox', name='Publisher').fill(publisher)
            print(f"✓ Filled publisher: {publisher}")
    except Exception as e:
        print(f"✗ Publisher error: {e}")

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
