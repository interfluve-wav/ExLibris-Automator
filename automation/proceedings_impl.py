"""
Esploro automation for Conference Proceedings.
Parses citations (OpenAI with manual helpers), drives Playwright, and fills
the proceedings form with normalized fields.
"""
import os
from dotenv import load_dotenv
import csv
import re
from typing import Dict, List
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

load_dotenv()


DEFAULT_PARSER = "openai"


def parse_any_citation(citation_text: str) -> Dict[str, str]:
    """Parse proceedings citations using OpenAI; fallback to manual regex helpers."""
    parser_type = os.getenv("CITATION_PARSER", DEFAULT_PARSER).lower()
    if parser_type == "openai":
        if not parse_citation_with_openai:
            return {"error": "OpenAI parser not available"}
        llm_data = parse_citation_with_openai(citation_text) or {}
        if not llm_data:
            return {"error": "OpenAI returned empty/invalid result"}
        # Normalize number to digits
        try:
            cn_raw = llm_data.get("conference_number", "") or ""
            m_cn = re.match(r"\s*(\d+)", cn_raw)
            if m_cn:
                llm_data["conference_number"] = m_cn.group(1)
            conf_name_val = (llm_data.get('conference_name') or '').strip()
            if conf_name_val:
                detected_num, cleaned_name = extract_ordinal_word_number(conf_name_val)
                if detected_num and not (llm_data.get('conference_number') or '').strip():
                    llm_data['conference_number'] = detected_num
                if detected_num:
                    llm_data['conference_name'] = cleaned_name
        except Exception:
            pass
        # Fallback title if needed
        if not (llm_data.get("proceedings_title") or "").strip():
            manual = parse_citation_manual(citation_text)
            if manual.get("proceedings_title"):
                llm_data["proceedings_title"] = manual["proceedings_title"]
        return llm_data
    # Manual path
    return parse_citation_manual(citation_text)


def goto_with_retries(page, url: str, attempts: int = 3, wait_until: str = "load") -> bool:
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
    return False


def parse_citation_manual(citation_text: str) -> Dict[str, str]:
    """A conservative manual parser for proceedings-style citations."""
    text = (citation_text or "").strip()
    if not text:
        return {"error": "Empty citation"}

    # Basic link extraction
    link = ""
    try:
        m_link = re.search(r"(https?://[^\s)]+)", text)
        if m_link:
            link = m_link.group(1).rstrip(".,);")
    except Exception:
        link = ""

    authors = ""
    title = ""

    # Date in parentheses
    m_date = re.search(r"\((\d{4})(?:,\s*([A-Za-z]{3,9})\.?\s*(\d{1,2})?)?\)", text)
    year = m_date.group(1) if m_date else ""

    # Authors are everything before the date parenthesis
    if m_date:
        before_date = text[: m_date.start()].strip()
        authors = before_date.rstrip(" .,")
    else:
        # Fallback: split before a period followed by a capitalized word
        m_auth_boundary = re.search(r"\.\s+(?=[A-Z][A-Za-z'\-]{2,})", text)
        if m_auth_boundary:
            authors = text[: m_auth_boundary.start()].strip().rstrip(" .,")
        else:
            authors = text.split(",")[0].strip()

    # After the date, derive title as the first sentence
    work = re.sub(r"\[[^\]]*\]", "", text)
    after_date = re.split(r"\)\.?\s*", work, maxsplit=1)
    if len(after_date) > 1:
        tail = after_date[1]
    else:
        tail = work
    sentences = [s.strip() for s in tail.split(".") if s.strip()]
    if sentences:
        title = sentences[0]

    # Conference line heuristics from the next sentence(s)
    conf_name = ""
    conf_number = ""
    conf_location = ""
    conf_index = 1 if len(sentences) >= 2 else 0
    conf_sent = sentences[conf_index] if len(sentences) > conf_index else ""
    if conf_sent:
        # Extract conference number if present
        m_ord = re.search(r"\b(\d+)\s*(?:st|nd|rd|th)\b", conf_sent, flags=re.I)
        if m_ord:
            conf_number = m_ord.group(1)
            conf_name = re.sub(r"\b\d+\s*(?:st|nd|rd|th)\b", "", conf_sent, flags=re.I).strip().rstrip(" ,")
        else:
            conf_name = conf_sent.strip().rstrip(" ,")

    # Location: try the third sentence or the tail of the conference sentence
    third_sentence = sentences[2] if len(sentences) >= 3 else ""
    if third_sentence:
        loc_sent = re.sub(r"(,\s*)?and online\.?$", "", third_sentence, flags=re.I)
        loc_sent = re.sub(r"\bonline\b\.?$", "", loc_sent, flags=re.I).strip()
        conf_location = loc_sent.rstrip(" ,")

    return {
        "proceedings_title": title,
        "authors": authors.rstrip(" ."),
        "date_presented": year,
        "date_presented_mmddyyyy": "",
        "date_presented_mmyyyy": "",
        "year": year,
        "published_proceedings_title": "",
        "conference_name": conf_name,
        "conference_number": conf_number,
        "conference_location": conf_location,
        "research_topics": "",
        "link": link,
    }


def save_citation_to_csv(citation_data: Dict[str, str], output_file: str):
    fieldnames = [
        "proceedings_title",
        "authors",
        "year",
        "date_presented",
        "published_proceedings_title",
        "conference_name",
        "conference_number",
        "conference_location",
        "research_topics",
    ]
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerow(citation_data)


def process_citation(page, citation_data: Dict[str, str], pause_after: bool = True, start_from_home: bool = True):
    """Fill one Conference Proceedings citation in Esploro UI."""
    if start_from_home:
        try:
            page.get_by_role("link", name="Deposit Asset").click()
        except Exception:
            page.goto(
                "https://umassd-researchmanagement.esploro.exlibrisgroup.com/ng;u=%2Fmng%2Faction%2Fhome.do%3FngHome%3Dtrue"
            )
            page.get_by_role("link", name="Deposit Asset").click()

    researcher = (
        citation_data.get("researcher")
        or os.getenv("DEFAULT_RESEARCHER")
        or "Scarano, Frank J"
    ).strip()

    page.get_by_role("textbox", name="Researcher").click()
    page.get_by_role("textbox", name="Researcher").fill(researcher)
    page.locator("a.dropdown-item.ui-menu-item-wrapper").filter(has_text=researcher).first.click()

    # Asset type: Conference proceeding
    page.get_by_role("combobox", name="Select an item from the list").click()
    page.get_by_role("combobox", name="Asset type *").click()
    page.get_by_role("combobox", name="Asset type *").fill("Conference proceeding")
    page.get_by_label("Publication <strong>").get_by_text("Conference proceeding").click()
    page.get_by_role("button", name="Next").click()
    try:
        page.locator("#loadingBlocker").wait_for(state="hidden", timeout=10000)
    except Exception:
        page.wait_for_timeout(300)

    # Proceedings title (use appropriate textbox)
    filled_title = False
    for title_name in ["Proceedings title *", "Proceedings title", "Conference presentation title *"]:
        try:
            page.get_by_role("textbox", name=title_name).click()
            page.get_by_role("textbox", name=title_name).fill(citation_data.get("proceedings_title", ""))
            filled_title = True
            break
        except Exception:
            continue
    if not filled_title:
        print("✗ Could not locate a proceedings title field")

    page.wait_for_timeout(1500)

    # Date Presented
    try:
        page.get_by_role("button", name=" Add Date").click()
        page.get_by_role("combobox", name="Date type *").click()
        page.get_by_label("Recent", exact=True).get_by_text("Date Presented").click()
        page.get_by_role("textbox", name="Choose date *").click()
        date_to_fill = (
            citation_data.get("date_presented_mmddyyyy")
            or citation_data.get("date_presented_mmyyyy")
            or citation_data.get("year", "")
        )
        page.get_by_role("textbox", name="Choose date *").fill(date_to_fill)
        page.get_by_role("button", name="Add and close").click()
        print("✓ Added date")
    except Exception as e:
        print(f"✗ Failed to add date: {e}")
    try:
        page.locator("#loadingBlocker").wait_for(state="hidden", timeout=3000)
    except Exception:
        page.wait_for_timeout(500)

    # Conference name
    conf_name_value = (citation_data.get("conference_name", "") or "").strip()
    if conf_name_value:
        try:
            field = page.get_by_role("textbox", name="Conference name")
            field.click()
            try:
                field.fill("")
            except Exception:
                pass
            field.fill(conf_name_value)
            print("✓ Conference name filled")
        except Exception as e:
            print(f"✗ Conference name error: {e}")

    # Location
    try:
        page.get_by_role("textbox", name="Conference location").click()
        page.get_by_role("textbox", name="Conference location").fill(
            citation_data.get("conference_location", "")
        )
        print("✓ Filled conference location")
    except Exception as e:
        print(f"✗ Conference location error: {e}")

    # Conference number
    try:
        page.get_by_role("textbox", name="Conference number").click()
        page.get_by_role("textbox", name="Conference number").fill(
            citation_data.get("conference_number", "")
        )
        print("✓ Filled conference number")
    except Exception as e:
        print(f"✗ Conference number error: {e}")

    print(f"✓ Form filled for: {citation_data.get('proceedings_title', '')}")
    print("Add creators manually, then submit when ready.")
    if pause_after:
        input("Press Enter to continue...")

# flow7_batch.py
import os
from dotenv import load_dotenv
import csv
import re
from typing import List, Dict
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
        if not parse_citation_with_openai:
            return {"error": "OpenAI parser not available"}
        llm_data = parse_citation_with_openai(citation_text) or {}
        if not llm_data:
            return {"error": "OpenAI returned empty/invalid result"}
    else:
        # Use manual regex parser as fallback
        return parse_citation(citation_text)

    # Handle errors from LLM parsers
    if "error" in llm_data:
        return llm_data

    # Normalize LLM results (applies to both OpenAI and DeepSeek)
    try:
        llm_data['published_proceedings_title'] = ''
        if (not llm_data.get('proceedings_title')) and llm_data.get('research_topics'):
            llm_data['proceedings_title'] = llm_data.get('research_topics', '')
        llm_data['research_topics'] = ''
        cn_raw = llm_data.get('conference_number', '') or ''
        m_cn = re.match(r"\s*(\d+)", cn_raw)
        if m_cn:
            llm_data['conference_number'] = m_cn.group(1)
        # Fallback: derive conference_number from conference_name if missing (e.g., "46th")
        if not llm_data.get('conference_number'):
            name_for_cn = llm_data.get('conference_name', '') or ''
            m_ord_in_name = re.search(r"\b(\d+)\s*(?:st|nd|rd|th)\b", name_for_cn, flags=re.I)
            if m_ord_in_name:
                llm_data['conference_number'] = m_ord_in_name.group(1)
    except Exception:
        pass

    # Fallback: if LLM misses or mislabels the title, derive it via manual parser
    try:
        needs_title_fallback = (
            not llm_data.get('proceedings_title')
            or (llm_data.get('conference_name') and llm_data.get('proceedings_title') == llm_data.get('conference_name'))
            or (llm_data.get('conference_location') and llm_data.get('proceedings_title') == llm_data.get('conference_location'))
            or len(llm_data.get('proceedings_title', '').strip('. ')) < 5
        )
    except Exception:
        needs_title_fallback = False

    if needs_title_fallback:
        try:
            manual = parse_citation(citation_text)
        except Exception:
            manual = {}
        if manual and manual.get('proceedings_title'):
            llm_data['proceedings_title'] = manual['proceedings_title']
        # Fill any missing date fields from manual parse
        for k in ['date_presented_mmddyyyy', 'date_presented_mmyyyy', 'date_presented', 'year']:
            if not llm_data.get(k) and manual.get(k):
                llm_data[k] = manual[k]
        # If conference_name equals title, prefer manual-derived conference_name when available
        if (
            llm_data.get('conference_name')
            and llm_data.get('proceedings_title') == llm_data.get('conference_name')
            and manual.get('conference_name')
        ):
            llm_data['conference_name'] = manual['conference_name']

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
    """Parse presentation-style citations like:
    Authors. (YYYY, Mon[.] [DD]). [Oral presentation]. Title. 8th World Conference on Qualitative Research. Portugal, Johannesburg, and online.
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

    # Extract authors (everything before the date). Title will be taken from the
    # first sentence after the date for presentation-style citations.
    authors = ""
    title = ""

    # Date: (YYYY, Mon[.] [DD]) or (YYYY, Month[.] [DD])
    # Allow trailing period after month inside the parentheses, e.g., "(2024, Sep.)"
    m_date = re.search(r"\((\d{4})(?:,\s*([A-Za-z]{3,9})\.?\s*(\d{1,2})?)?\)", text)
    year = m_date.group(1) if m_date else ""
    # Normalize month by stripping a trailing dot and lowercasing
    month = ((m_date.group(2) or "").rstrip('.').lower() if m_date else "")
    day = (m_date.group(3) if m_date and m_date.lastindex and m_date.lastindex >= 3 else None)
    # For UI we only need yyyy, per requirement; keep computing components if needed later
    month_map = {
        'jan': '01','january': '01','feb': '02','february': '02','mar': '03','march': '03',
        'apr': '04','april': '04','may': '05','jun': '06','june': '06','jul': '07','july': '07',
        'aug': '08','august': '08','sep': '09','september': '09','oct': '10','october': '10',
        'nov': '11','november': '11','dec': '12','december': '12',
    }
    # Try to infer month/year from anywhere in the text if not present in parentheses
    month_numeric = month_map.get(month, "")
    if not month_numeric:
        # Match patterns like "February 2025" or "Feb. 2025" or "February 4-6, 2025"
        m_any_month = re.search(
            r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?\s*(?:\d{1,2}(?:-\d{1,2})?,\s*)?(\d{4})",
            text,
            flags=re.I,
        )
        if m_any_month:
            month_token = m_any_month.group(1).rstrip('.').lower()
            # Normalize 'sept' -> 'sep'
            if month_token == 'sept':
                month_token = 'sep'
            month_numeric = month_map.get(month_token, "")
            # If no year captured earlier, use the one from this match
            if not year:
                year = m_any_month.group(2)
    # Detect cross-month day range like "September 30-October 2, 2024" and prefer last month for MM/YYYY
    m_month_range = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?\s*\d{1,2}\s*-\s*\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?\s*\d{1,2}\s*,\s*(\d{4})",
        text,
        flags=re.I,
    )
    if m_month_range:
        second_month_token = m_month_range.group(2).rstrip('.').lower()
        if second_month_token == 'sept':
            second_month_token = 'sep'
        month_numeric = month_map.get(second_month_token, month_numeric)
        if not year:
            year = m_month_range.group(3)

    # If we still don't have a specific day from the parentheses, try to detect a single day in free text
    inferred_day = None
    if month_numeric and year and not day:
        m_single_day = re.search(
            r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?\s*(\d{1,2})(?!\s*-\s*\d{1,2})(?:,)?\s*" + re.escape(year) + r"\b",
            text,
            flags=re.I,
        )
        if m_single_day:
            try:
                inferred_day = int(m_single_day.group(2))
            except Exception:
                inferred_day = None
    # Compute display-ready dates per rules
    # - If single exact day/month/year exists -> MM/DD/YYYY
    # - If a month and year exist (with or without a day range) -> MM/YYYY
    # - Otherwise just YYYY
    date_presented = year
    date_presented_mmyyyy = ""
    date_presented_mmddyyyy = ""

    # Detect explicit day range like "4-6, 2025" or cross-month ranges
    has_day_range = bool(
        re.search(r"\b\d{1,2}\s*-\s*\d{1,2}\s*,\s*\d{4}\b", text)
        or re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[^.]*?\d{1,2}\s*-\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[^.]*?\d{1,2}\s*,\s*\d{4}\b", text, flags=re.I)
    )

    if month_numeric and year:
        effective_day = day or inferred_day
        if effective_day and not has_day_range:
            # Single specific day -> MM/DD/YYYY
            day_padded = f"{int(effective_day):02d}"
            date_presented_mmddyyyy = f"{month_numeric}/{day_padded}/{year}"
        # For month present (with or without range), always provide MM/YYYY for the automation fallback
        date_presented_mmyyyy = f"{month_numeric}/{year}"

    # Authors: take the entire segment before the date
    if m_date:
        date_start = m_date.start()
        before_date = text[:date_start].strip()
        authors = before_date.rstrip(' .,')
        title = ""
    # Remove bracketed segments like [Oral presentation]
    work = re.sub(r"\[[^\]]*\]", "", text)
    # Take the part after the date )
    after_date = re.split(r"\)\.?\s*", work, maxsplit=1)
    # Title is the first sentence after the date
    title = title or ""
    conf_name = ""
    conf_number = ""
    conf_location = ""
    if len(after_date) > 1:
        sentences = [s.strip() for s in after_date[1].split('.') if s.strip()]
        # Title is the first sentence after the date
        if sentences:
            title = sentences[0]
        # Conference line is the next sentence after the title
        conf_index = 1 if len(sentences) >= 2 else 0
        # Conference line may contain an ordinal like "8th" or "13th" anywhere
        conf_sent = ""
        if len(sentences) > conf_index:
            conf_sent = sentences[conf_index]
            # Handle sentences that start with a month/date: "November 15, 2024 at the 2024 AMERSA … in Chicago, IL"
            m_month_start = re.match(
                r"^\s*(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b.*?\b\d{4}\b\s*(.*)$",
                conf_sent,
                flags=re.I,
            )
            if m_month_start:
                remainder = m_month_start.group(2).strip(' .,')
                # Look for "at (the )?XYZ (in LOCATION)?"
                m_at = re.search(r"\bat\s+(?:the\s+)?(.+)$", remainder, flags=re.I)
                if m_at:
                    after_at = m_at.group(1).strip()
                    # Optional trailing "in LOCATION"
                    m_in = re.search(r"^(.*)\b\s+in\s+([^,.]+(?:,\s*[^,.]+)?)\s*$", after_at, flags=re.I)
                    if m_in:
                        name_part = m_in.group(1).strip().rstrip(' ,')
                        loc_part = m_in.group(2).strip()
                        conf_name = name_part
                        conf_location = loc_part
                    else:
                        conf_name = after_at.rstrip(' ,')
                else:
                    conf_name = remainder.rstrip(' ,')
                # Strip a leading standalone year from the name, e.g., "2024 AMERSA …"
                conf_name = re.sub(r"^\s*\b\d{4}\b\s+", "", conf_name).strip()
                # Extract ordinal conference number if present anywhere in the name
                m_any_ord = re.search(r"\b(\d+)\s*(?:st|nd|rd|th)\b", conf_name, flags=re.I)
                if m_any_ord:
                    conf_number = m_any_ord.group(1)
            else:
                # Case 1: number at the beginning (e.g., "12th International …").
                # Require an ordinal suffix to avoid mistaking a year (e.g., 2024) for conference number.
                m_ord_begin = re.match(r"(\d+)\s*(?:st|nd|rd|th)\s+(.+)$", conf_sent, flags=re.I)
                if m_ord_begin:
                    conf_number = m_ord_begin.group(1)
                    conf_name = m_ord_begin.group(2).strip().rstrip(' ,')
                else:
                    # Case 2: number appears later (e.g., "International … 13th Network Conference")
                    m_any_ord = re.search(r"\b(\d+)\s*(?:st|nd|rd|th)\b", conf_sent, flags=re.I)
                    if m_any_ord:
                        conf_number = m_any_ord.group(1)
                        # Remove the ordinal token from the name for cleanliness
                        cleaned = re.sub(r"\b\d+\s*(?:st|nd|rd|th)\b", "", conf_sent, flags=re.I)
                        conf_name = cleaned.strip().rstrip(' ,')
                    else:
                        conf_name = conf_sent.rstrip(' ,')

        # Decide whether the third sentence is a date (e.g., contains a month name and a 4-digit year)
        date_like_third = False
        third_sentence = sentences[2] if len(sentences) >= 3 else ""
        if third_sentence:
            if re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\b.*\b\d{4}\b", third_sentence, flags=re.I):
                date_like_third = True

        if date_like_third:
            # When the third sentence is a date, preserve original spacing and
            # extract the last two comma-separated tokens from the original conference sentence.
            # Example: "AMERSA National Conference 2024, Chicago,IL" -> location "Chicago,IL"
            tail_match = re.search(r"([^,]+,[^,]+)$", conf_sent)
            if tail_match:
                tail = tail_match.group(1)
                # Name is everything before this tail
                name_prefix = conf_sent[:conf_sent.rfind(tail)]
                conf_name = name_prefix.strip().rstrip(' ,')
                # Remove any ordinal token from the name for cleanliness
                conf_name = re.sub(r"\b\d+\s*(?:st|nd|rd|th)\b", "", conf_name, flags=re.I).strip().rstrip(' ,')
                conf_location = tail.strip().strip(',').strip()
        else:
            # Location is next sentence; drop trailing 'and online'
            if third_sentence:
                loc_sent = third_sentence
                loc_sent = re.sub(r"(,\s*)?and online\.?$", "", loc_sent, flags=re.I)
                loc_sent = re.sub(r"\bonline\b\.?$", "", loc_sent, flags=re.I).strip()
                conf_location = loc_sent.rstrip(' ,')

    # Fallback path when there is no parenthesized date: infer authors, title, and conference sentence
    if not m_date:
        # Find boundary between authors and title: a period followed by a capitalized word (>=3 chars)
        m_auth_boundary = re.search(r"\.\s+(?=[A-Z][A-Za-z'\-]{2,})", work)
        rest_after_authors = ""
        if m_auth_boundary:
            authors = work[:m_auth_boundary.start()].strip().rstrip(' .,')
            rest_after_authors = work[m_auth_boundary.end():].strip()
        else:
            # Fallback: if not found, keep first 100 chars as authors (best effort)
            authors = work.split(',')[0].strip()
            rest_after_authors = work[len(authors):].lstrip(' .')

        # Title ends at the next period
        title_end = re.search(r"\.\s+", rest_after_authors)
        conf_sent_fb = ""
        if title_end:
            title = rest_after_authors[:title_end.start()].strip()
            conf_sent_fb = rest_after_authors[title_end.end():].strip()
        else:
            title = rest_after_authors.strip()
            conf_sent_fb = ""

        if conf_sent_fb:
            # Remove trailing date tail (month/year or ranges)
            m_tail = re.match(r"^(.*?)(?:,\s*)?(?:\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\b.*\b\d{4}\b)\s*$", conf_sent_fb, flags=re.I)
            base = (m_tail.group(1) if m_tail else conf_sent_fb).strip()
            # Extract conference number from ordinal
            m_ord = re.search(r"\b(\d+)\s*(?:st|nd|rd|th)\b", base, flags=re.I)
            if m_ord:
                conf_number = m_ord.group(1)
            # Split into name and location using the last comma
            m_name_loc = re.match(r"^(.*?),\s*([^,]+(?:,\s*[^,]+)?)$", base)
            if m_name_loc:
                conf_name = m_name_loc.group(1).strip().rstrip(' ,')
                conf_location = m_name_loc.group(2).strip()
            else:
                conf_name = base.rstrip(' ,')

    # If the citation explicitly contains "(online)", append it to location
    try:
        if re.search(r"\(\s*online\s*\)", text, flags=re.I):
            if conf_location and 'online' not in conf_location.lower():
                conf_location = f"{conf_location} (online)"
    except Exception:
        pass

    # Final cleanup: derive number from textual ordinal in the final name and strip it
    try:
        maybe_num, cleaned_name = extract_ordinal_word_number(conf_name)
        if maybe_num and not conf_number:
            conf_number = maybe_num
        if maybe_num:
            conf_name = cleaned_name
    except Exception:
        pass

    return {
        "proceedings_title": title,
        "authors": authors.rstrip(' .'),
        "date_presented": date_presented,
        "date_presented_mmddyyyy": date_presented_mmddyyyy,
        "date_presented_mmyyyy": date_presented_mmyyyy,
        "year": year,
        "published_proceedings_title": "",
        "conference_name": conf_name,
        # Fallback: if number wasn't detected above, try extracting from the final name
        "conference_number": (re.search(r"\b(\d+)\s*(?:st|nd|rd|th)\b", conf_name, flags=re.I).group(1)
                               if (not conf_number and conf_name and re.search(r"\b(\d+)\s*(?:st|nd|rd|th)\b", conf_name, flags=re.I)) else conf_number),
        "conference_location": conf_location,
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

    # For Conference Presentation
    page.get_by_role('combobox', name='Select an item from the list').click()
    page.get_by_role('combobox', name='Asset type *').click()
    page.get_by_role('combobox', name='Asset type *').fill('Conference proceeding')   #Change fill type to use other asset type
    page.get_by_label('Publication <strong>').get_by_text('Conference proceeding').click() #Change get by text type to use other asset type
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


    # Fill citation data (Proceedings title field)
    filled_title = False
    for title_name in ['Proceedings title *', 'Proceedings title', 'Conference presentation title *']:
        try:
            page.get_by_role('textbox', name=title_name).click()
            page.get_by_role('textbox', name=title_name).fill(citation_data.get('proceedings_title', ''))
            filled_title = True
            break
        except Exception:
            continue
    if not filled_title:
        print("✗ Could not locate a proceedings title field")

    #timeout for parsing to complete
    page.wait_for_timeout(1500)

    # Add Date section (mirror presentations flow)
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


    # Conference Date From/To (if parsed)
    try:
        conf_from = (citation_data.get('conference_date_from') or '').strip()
        conf_to = (citation_data.get('conference_date_to') or '').strip()
        if conf_from or conf_to:
            try:
                page.get_by_text('Conference date').click()
            except Exception:
                pass
            if conf_from:
                page.get_by_placeholder('From').click()
                page.get_by_placeholder('From').fill(conf_from)
                page.get_by_placeholder('From').press('Tab')
            if conf_to:
                page.get_by_placeholder('To', exact=True).fill(conf_to)
            print('✓ Filled Conference date From/To')
    except Exception as e:
        print(f"✗ Conference date From/To error: {e}")



    # Add Language (Published)
    page.get_by_role('combobox', name='Language').click()
    page.get_by_label('Recent', exact=True).get_by_text('English', exact=True).click()


    # Add small wait before conference fields
    page.wait_for_timeout(500)

    # Robust Conference name fill (plain textbox)
    conf_name_value = citation_data.get('conference_name', '').strip()
    if not conf_name_value:
        print("✗ Parsed conference_name is empty; skipping fill")
    else:
        print(f"Filling Conference name: '{conf_name_value}'")
        filled_conf_name = False
        for locator in [
            lambda: page.get_by_role('textbox', name='Conference name'),
            lambda: page.get_by_label('Conference name'),
            lambda: page.locator("input[aria-label*='Conference name']"),
            lambda: page.locator("input[name*='conference'][type='text']"),
        ]:
            try:
                field = locator()
                field.wait_for(state="visible", timeout=2000)
                try:
                    field.scroll_into_view_if_needed()
                except Exception:
                    pass
                field.click()
                # Clear then fill
                try:
                    field.fill("")
                except Exception:
                    pass
                field.fill(conf_name_value)
                filled_conf_name = True
                print("✓ Conference name filled")
                break
            except Exception as e:
                print(f"…retrying Conference name with next selector ({e})")
                continue
        if not filled_conf_name:

            print("✗ Could not locate/fill Conference name")

    try:
        page.get_by_role('textbox', name='Conference location').click()
        page.get_by_role('textbox', name='Conference location').fill(citation_data.get('conference_location', ''))
        print("✓ Filled conference location")
    except Exception as e:
        print(f"✗ Conference location error: {e}")

    try:
        page.get_by_role('textbox', name='Conference number').click()
        page.get_by_role('textbox', name='Conference number').fill(citation_data.get('conference_number', ''))
        print("✓ Filled conference number")
    except Exception as e:
        print(f"✗ Conference number error: {e}")

    # Fill Volume
    try:
        volume = citation_data.get('volume', '').strip()
        if volume:
            page.get_by_role('textbox', name='Volume').click()
            page.get_by_role('textbox', name='Volume').fill(volume)
            print(f"✓ Filled volume: {volume}")
    except Exception as e:
        print(f"✗ Volume error: {e}")

    # Fill Start Page
    try:
        start_page = citation_data.get('start_page', '').strip()
        if start_page:
            page.get_by_role('textbox', name='Start Page').click()
            page.get_by_role('textbox', name='Start Page').fill(start_page)
            print(f"✓ Filled start page: {start_page}")
    except Exception as e:
        print(f"✗ Start Page error: {e}")

    # Fill End Page
    try:
        end_page = citation_data.get('end_page', '').strip()
        if end_page:
            page.get_by_role('textbox', name='End Page').click()
            page.get_by_role('textbox', name='End Page').fill(end_page)
            print(f"✓ Filled end page: {end_page}")
    except Exception as e:
        print(f"✗ End Page error: {e}")

    # Fill Publisher
    try:
        publisher = citation_data.get('publisher_name', '').strip()
        if publisher:
            page.get_by_role('textbox', name='Publisher').click()
            page.get_by_role('textbox', name='Publisher').fill(publisher)
            print(f"✓ Filled publisher: {publisher}")
    except Exception as e:
        print(f"✗ Publisher error: {e}")

    # Fill authors/creators (if enabled)
    fill_authors_if_enabled(page, citation_data)

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

# Add small wait before conference fields
    page.wait_for_timeout(1000)

    # Incorporate additional field - (Research topics)
   # page.get_by_role('combobox', name='Select an item from the list').click()
   # page.get_by_role('combobox', name='Research topics').fill('Protein Folding')
   # page.get_by_text('Protein Folding').click()
   # page.get_by_role('combobox', name='Research topics').fill('Computer Science')
   # page.get_by_text('Computer Science').click()



    print(f"✓ Form filled for: {citation_data.get('proceedings_title', '')}")
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
