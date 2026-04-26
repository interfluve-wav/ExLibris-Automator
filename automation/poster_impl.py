"""
Esploro automation for Conference Posters.
Parses citations using OpenAI and fills the poster form via Playwright.
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
try:
    from automation.presentations_impl import parse_citation as _manual_presentation_parse
except Exception:
    _manual_presentation_parse = None

load_dotenv()


DEFAULT_PARSER = "openai"


def parse_any_citation(citation_text: str) -> Dict[str, str]:
    """Parse poster citations using OpenAI with manual fallback."""
    parser_type = os.getenv("CITATION_PARSER", DEFAULT_PARSER).lower()
    if parser_type == "openai":
        if not parse_citation_with_openai:
            return {"error": "OpenAI parser not available"}
        llm_data = parse_citation_with_openai(citation_text) or {}
        if not llm_data or "error" in llm_data:
            # Explicit fallback for poster mode when OpenAI is unavailable/quota-limited.
            return parse_citation(citation_text)
        # Normalize a few fields
        try:
            cn_raw = llm_data.get("conference_number", "") or ""
            m_cn = re.match(r"\s*(\d+)", cn_raw)
            if m_cn:
                llm_data["conference_number"] = m_cn.group(1)
            # Derive number from textual ordinal in conference_name if missing (e.g., "Eighth …" -> 8)
            conf_name_val = (llm_data.get('conference_name') or '').strip()
            if conf_name_val:
                detected_num, cleaned_name = extract_ordinal_word_number(conf_name_val)
                if detected_num and not (llm_data.get('conference_number') or '').strip():
                    llm_data['conference_number'] = detected_num
                if detected_num:
                    llm_data['conference_name'] = cleaned_name
        except Exception:
            pass
        return llm_data
    return parse_citation(citation_text)


def parse_citation(citation_text: str) -> Dict[str, str]:
    """
    Manual poster parser fallback.
    Reuses the presentation manual parser to keep extraction resilient when OpenAI fails.
    """
    if not _manual_presentation_parse:
        return {"error": "Manual parser not available"}
    parsed = _manual_presentation_parse(citation_text) or {}
    if "error" in parsed:
        return parsed
    # Poster flow uses proceedings_title + conference fields, same shape as presentation parser output.
    return parsed


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
    """Fill one Conference Poster citation in Esploro UI."""
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

    # Researcher
    page.get_by_role("textbox", name="Researcher").click()
    page.get_by_role("textbox", name="Researcher").fill(researcher)
    page.get_by_text(researcher).click()

    # Asset type: Conference poster
    page.get_by_role("combobox", name="Select an item from the list").click()
    page.get_by_role("combobox", name="Asset type *").click()
    page.get_by_role("combobox", name="Asset type *").fill("Conference poster")
    page.get_by_label("Conference/Event <strong>").get_by_text("Conference poster").click()
    page.get_by_role("button", name="Next").click()
    try:
        page.locator("#loadingBlocker").wait_for(state="hidden", timeout=10000)
    except Exception:
        page.wait_for_timeout(300)

    # Title field (Poster title)
    try:
        page.get_by_role("textbox", name="Poster title *").click()
        page.get_by_role("textbox", name="Poster title *").fill(
            citation_data.get("proceedings_title", "")
        )
    except Exception:
        try:
            page.get_by_role("textbox", name="Poster title").click()
            page.get_by_role("textbox", name="Poster title").fill(
                citation_data.get("proceedings_title", "")
            )
        except Exception as e:
            print(f"✗ Poster title field not found: {e}")

    # Give parser a small buffer
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

    # Conference Date Range (optional)
    try:
        conf_from = (citation_data.get("conference_date_from") or "").strip()
        conf_to = (citation_data.get("conference_date_to") or "").strip()
        if conf_from or conf_to:
            try:
                page.get_by_text("Conference date").click()
            except Exception:
                pass
            if conf_from:
                page.get_by_placeholder("From").click()
                page.get_by_placeholder("From").fill(conf_from)
                page.get_by_placeholder("From").press("Tab")
            if conf_to:
                page.get_by_placeholder("To", exact=True).fill(conf_to)
            print("✓ Filled Conference date From/To")
    except Exception as e:
        print(f"✗ Conference date From/To error: {e}")

    # Language
    page.get_by_role("combobox", name="Language").click()
    try:
        page.get_by_label("Recent", exact=True).get_by_text("English", exact=True).first.click()
    except Exception:
        page.get_by_text("English", exact=True).first.click()

    # Small wait before conference fields
    page.wait_for_timeout(500)

    # Conference name
    conf_name_value = (citation_data.get("conference_name", "") or "").strip()
    if not conf_name_value:
        print("✗ Parsed conference_name is empty; skipping fill")
    else:
        print(f"Filling Conference name: '{conf_name_value}'")
        filled_conf_name = False
        for locator in [
            lambda: page.get_by_role("textbox", name="Conference name"),
            lambda: page.get_by_label("Conference name"),
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

    # Conference location
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
    # Fill authors/creators (if enabled)
    fill_authors_if_enabled(page, citation_data)

    print("Add creators manually, then submit when ready.")
    if pause_after:
        input("Press Enter to continue...")
