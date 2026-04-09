#!/usr/bin/env python3
"""
Persistent browser worker for the Discord bot (automation layer)
"""

import os
import sys
import json
import time
import re
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from utils.logging_utils import make_logger

load_dotenv()
LOG = make_logger("WORKER")


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write_field_summary(parsed: dict, path: str = "filled_fields_summary.txt") -> None:
    try:
        filled_keys, empty_keys = [], []
        for key, value in (parsed or {}).items():
            val = (value or "").strip() if isinstance(value, str) else value
            (filled_keys if val else empty_keys).append(key)
        lines = [
            "Field Fill Summary",
            "===================",
        ]
        title = (parsed.get("proceedings_title") or parsed.get("title") or "").strip()
        if title:
            lines.append(f"Title: {title}")
        authors = (parsed.get("authors") or "").strip()
        if authors:
            lines.append(f"Authors: {authors}")
        year = (parsed.get("year") or "").strip()
        if year:
            lines.append(f"Year: {year}")
        conf_name = (parsed.get("conference_name") or "").strip()
        if conf_name:
            lines.append(f"Conference: {conf_name}")
        conf_loc = (parsed.get("conference_location") or "").strip()
        if conf_loc:
            lines.append(f"Location: {conf_loc}")
        conf_num = (parsed.get("conference_number") or "").strip()
        if conf_num:
            lines.append(f"Conference Number: {conf_num}")
        lines += [
            "",
            f"✓ Filled fields: {len(filled_keys)}",
            f"✗ Empty fields: {len(empty_keys)}",
            "",
        ]
        if filled_keys:
            lines.append("Filled:")
            for k in sorted(filled_keys):
                v = parsed.get(k)
                v_str = v if isinstance(v, str) else (str(v) if v is not None else "")
                if len(v_str) > 120:
                    v_str = v_str[:117] + "…"
                lines.append(f"  - {k}: {v_str}")
            lines.append("")
        if empty_keys:
            lines.append("Empty:")
            for k in sorted(empty_keys):
                lines.append(f"  - {k}")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass


# ============================================================================
# Module loading (done once at module level for performance)
# ============================================================================
from automation import presentations as presentations_mod
from automation import poster as poster_mod
from automation import book_chapters as book_chapters_mod
from automation import journal as journal_mod
from automation import proceedings as proceedings_mod
from automation import abstract as abstract_mod
from automation import technical_documentation as technical_documentation_mod

# Create asset type dispatch table (cleaner than if-elif chains)
ASSET_TYPE_HANDLERS = {
    'poster': {
        'parse': getattr(poster_mod, "parse_any_citation"),
        'process': getattr(poster_mod, "process_citation"),
        'display': "Conference Poster"
    },
    'book_chapter': {
        'parse': getattr(book_chapters_mod, "parse_any_citation"),
        'process': getattr(book_chapters_mod, "process_citation"),
        'display': "Book Chapter"
    },
    'journal_article': {
        'parse': getattr(journal_mod, "parse_any_citation"),
        'process': getattr(journal_mod, "process_citation"),
        'display': "Journal Article"
    },
    'proceedings': {
        'parse': getattr(proceedings_mod, "parse_any_citation"),
        'process': getattr(proceedings_mod, "process_citation"),
        'display': "Conference Proceedings"
    },
    'abstract': {
        'parse': getattr(abstract_mod, "parse_any_citation"),
        'process': getattr(abstract_mod, "process_citation"),
        'display': "Abstract"
    },
    'technical_documentation': {
        'parse': getattr(technical_documentation_mod, "parse_any_citation"),
        'process': getattr(technical_documentation_mod, "process_citation"),
        'display': "Technical Documentation"
    },
    'presentation': {
        'parse': getattr(presentations_mod, "parse_any_citation"),
        'process': getattr(presentations_mod, "process_citation"),
        'display': "Conference Presentation"
    }
}

# Common utilities
presentations_save_csv = getattr(presentations_mod, "save_citation_to_csv", None)
goto_with_retries = getattr(presentations_mod, "goto_with_retries", None)


def _minimal_parse_fallback(text: str) -> dict:
    """
    Final parser safety net when both OpenAI and asset-specific manual parsing fail.
    Returns minimal fields required by downstream automation.
    """
    src = (text or "").strip()
    if not src:
        return {"error": "Empty citation"}

    year = ""
    # Prefer full parenthesized date span, e.g. "(2016, December)" or "(2016, May 12)".
    m_date_span = re.search(r"\((\d{4})(?:,\s*[A-Za-z]{3,9}\.?\s*\d{0,2})?\)", src)
    m_year = m_date_span or re.search(r"\b(\d{4})\b", src)
    if m_year:
        year = m_year.group(1)

    authors = ""
    title = ""
    after = src
    if m_year:
        authors = src[: m_year.start()].strip().rstrip(" .,")
        after = src[m_year.end() :].strip()

    # Handle common date punctuation before title.
    if after.startswith(")."):
        after = after[2:].strip()
    elif after.startswith(")"):
        after = after[1:].strip()
    if after.startswith("."):
        after = after[1:].strip()

    # Title heuristic: first sentence after year.
    sentences = [s.strip() for s in re.split(r"\.\s+", after) if s.strip()]
    if sentences:
        title = sentences[0].rstrip(" .")
    if not title:
        title = after[:160].strip().rstrip(" .")
    if not title:
        return {"error": "Unable to extract title in minimal fallback"}

    return {
        "proceedings_title": title,
        "authors": authors,
        "year": year,
        "date_presented": year,
        "date_presented_mmddyyyy": "",
        "date_presented_mmyyyy": "",
        "conference_name": "",
        "conference_number": "",
        "conference_location": "",
        "conference_date_from": "",
        "conference_date_to": "",
        "published_proceedings_title": "",
        "research_topics": "",
    }


def _try_parse_with_fallback(normalized_text: str, asset_type: str, parse_fn, pre_parsed: dict) -> dict:
    """
    Parse citation with fallback to manual parser if OpenAI fails.

    Returns:
        Parsed data dict, or dict with 'error' key if all parsers fail
    """
    # Use pre-parsed data if available and valid
    if isinstance(pre_parsed, dict) and pre_parsed and pre_parsed.get('proceedings_title'):
        LOG.info("Parser path: pre-parsed")
        return pre_parsed

    # Try primary parser (usually OpenAI)
    parsed_data = parse_fn(normalized_text) or {}

    # Check if parser succeeded
    if not ("error" in parsed_data or not parsed_data or not parsed_data.get('proceedings_title')):
        LOG.info("Parser path: primary")
        return parsed_data

    # Log failure and try manual fallback
    if "error" in parsed_data:
        LOG.warn(f"Parse error: {parsed_data.get('error', 'Unknown error')}")
    else:
        LOG.warn(f"Parser returned empty/invalid result")

    LOG.info(f"Attempting manual parser fallback...")

    try:
        # Import the appropriate manual parser
        manual_parse_modules = {
            'poster': 'automation.poster_impl',
            'book_chapter': 'automation.book_chapters_impl',
            'journal_article': 'automation.journal_impl',
            'proceedings': 'automation.proceedings_impl',
            'abstract': 'automation.abstract_impl',
            'technical_documentation': 'automation.technical_documentation_impl',
            'presentation': 'automation.presentations_impl'
        }

        module_name = manual_parse_modules.get(asset_type, 'automation.presentations_impl')
        manual_parse_module = __import__(module_name, fromlist=['parse_citation'])
        manual_parse = getattr(manual_parse_module, 'parse_citation')

        parsed_data = manual_parse(normalized_text) or {}

        if "error" not in parsed_data and parsed_data.get('proceedings_title'):
            LOG.info(f"✓ Manual parser succeeded")
            LOG.info("Parser path: manual")
            return parsed_data
        else:
            LOG.warn(f"Manual parser also failed")
            LOG.info("Attempting minimal generic parser fallback...")
            minimal = _minimal_parse_fallback(normalized_text)
            if "error" not in minimal and minimal.get("proceedings_title"):
                LOG.info("✓ Minimal fallback parser succeeded")
                LOG.info("Parser path: minimal")
                return minimal
            return {"error": "OpenAI, manual, and minimal fallback parsers all failed"}

    except Exception as e:
        LOG.error(f"Manual parser fallback error: {e}")
        return {"error": f"Parser fallback failed: {str(e)}"}


def _write_status_file(status_file: str, citation_id: str, state: str, error: str = None):
    """
    Write status file with standardized format.

    Args:
        status_file: Path to status file
        citation_id: Citation ID being processed
        state: One of "processing", "completed", or "failed"
        error: Optional error message
    """
    try:
        payload = {
            "last_written_id": citation_id,
            "state": state,
            "csv_file": "citationsPresentations.csv" if os.path.exists("citationsPresentations.csv") else "",
            "summary_file": "filled_fields_summary.txt" if os.path.exists("filled_fields_summary.txt") else "",
            "written_at": time.time(),
        }
        if error:
            payload["error"] = error

        with open(status_file, "w", encoding="utf-8") as sf:
            json.dump(payload, sf)
    except Exception as e:
        LOG.error(f"Failed to write status file: {e}")


def main(channel_id):
    control_file = f"citation_control_{channel_id}.json"
    status_file = f"citation_status_{channel_id}.json"

    LOG.info(f"Starting worker for channel {channel_id}")
    LOG.info(f"Watching control: {control_file}")

    headless_env = (os.getenv('HEADLESS') or '').strip().lower() in ('1', 'true', 'yes')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless_env)
        context = browser.new_context()
        page = context.new_page()

        username = (os.getenv('ESPLORO_USERNAME') or '').strip()
        password = (os.getenv('ESPLORO_PASSWORD') or '').strip()

        LOG.info("Logging into Esploro…")
        page.goto('https://umassd-researchmanagement.esploro.exlibrisgroup.com/mng/login')
        page.get_by_role('textbox', name='User Name').fill(username)
        page.get_by_role('textbox', name='Password').fill(password)
        page.get_by_role('button', name='Login').click()

        home_url = 'https://umassd-researchmanagement.esploro.exlibrisgroup.com/ng;u=%2Fmng%2Faction%2Fhome.do%3FngHome%3Dtrue'
        try:
            if goto_with_retries:
                goto_with_retries(page, home_url)
            else:
                page.goto(home_url)
        except Exception as e:
            LOG.warn(f"Navigation to home failed: {e}; retrying in a new page")
            page = context.new_page()
            if goto_with_retries:
                goto_with_retries(page, home_url)
            else:
                page.goto(home_url)

        LOG.info("Browser ready")
        if headless_env:
            LOG.info("Running in HEADLESS mode: automation will navigate without manual clicks")
        else:
            LOG.info("Waiting for !f command…")

        last_processed = None

        while True:
            try:
                if not os.path.exists(control_file):
                    time.sleep(0.2)
                    continue

                with open(control_file, 'r') as f:
                    data = json.load(f)

                citation_id = data.get('citation_id', data.get('message_id'))
                if citation_id and citation_id != last_processed:
                    citation_text = data.get('text', '')
                    asset_type = data.get('asset_type', 'presentation')
                    pre_parsed = data.get('parsed') or None
                    researcher = data.get('researcher')

                    if not citation_text:
                        time.sleep(0.2)
                        continue

                    # Use dispatch table (faster than if-elif chain)
                    handler = ASSET_TYPE_HANDLERS.get(asset_type, ASSET_TYPE_HANDLERS['presentation'])
                    parse_fn = handler['parse']
                    process_fn = handler['process']
                    asset_display = handler['display']

                    LOG.info(f"Processing {asset_display}")
                    LOG.debug(f"Text: {citation_text[:80]}…")

                    # Parse citation with automatic fallback
                    normalized_text = re.sub(r"\(\s*pos\s*\)|--pos\b", "", citation_text, flags=re.I).strip()
                    parsed_data = _try_parse_with_fallback(normalized_text, asset_type, parse_fn, pre_parsed)

                    # Check if parsing failed completely
                    if "error" in parsed_data:
                        LOG.error(f"Parsing failed: {parsed_data.get('error')}")
                        last_processed = citation_id
                        _write_status_file(status_file, citation_id, state="failed", error=parsed_data.get('error'))
                        time.sleep(0.2)
                        continue

                    parsed_data['asset_type'] = asset_type
                    if researcher:
                        parsed_data['researcher'] = researcher
                    # Pass channel id forward so automation can fetch per-channel topics
                    try:
                        parsed_data['channel_id'] = str(channel_id)
                    except Exception:
                        parsed_data['channel_id'] = str(channel_id)

                    # If citation is explicitly virtual and no location was parsed, set location to "Virtual".
                    try:
                        has_virtual = bool(re.search(r"\bvirtual(?:\s+meeting)?\b", citation_text, flags=re.I))
                        if has_virtual and not (parsed_data.get('conference_location') or '').strip():
                            parsed_data['conference_location'] = 'Virtual'
                    except Exception:
                        pass

                    LOG.info(f"Title: {parsed_data.get('proceedings_title', 'N/A')[:80]}")

                    try:
                        if presentations_save_csv:
                            presentations_save_csv(parsed_data, "citationsPresentations.csv")
                    except Exception:
                        pass

                    try:
                        write_field_summary(parsed_data, "filled_fields_summary.txt")
                    except Exception:
                        pass

                    try:
                        # Mark active processing before invoking automation.
                        _write_status_file(status_file, citation_id, state="processing")

                        # Always start from home for full automation (bot handles entire workflow)
                        start_from_home = True
                        LOG.info(f"Calling process_fn (headless={headless_env}, start_from_home={start_from_home})")
                        LOG.info(f"About to call: {process_fn.__name__} from {process_fn.__module__}")
                        process_fn(page, parsed_data, pause_after=False, start_from_home=start_from_home)
                        _write_status_file(status_file, citation_id, state="completed")
                        last_processed = citation_id
                        LOG.info(f"Processed {asset_display}")
                        LOG.info("Waiting for next !f…")
                    except Exception as e:
                        LOG.error(f"Error processing citation: {e}")
                        import traceback
                        LOG.error(f"Traceback: {''.join(traceback.format_exception(type(e), e, e.__traceback__))}")
                        _write_status_file(status_file, citation_id, state="failed", error=str(e))
                        last_processed = citation_id

                time.sleep(0.2)

            except KeyboardInterrupt:
                LOG.warn("Stopping worker (KeyboardInterrupt)")
                break
            except Exception as e:
                LOG.warn(f"Worker loop error: {e}")
                time.sleep(2)

        LOG.info("Closing browser…")
        context.close()
        browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 automation/worker.py <channel_id>")
        sys.exit(1)
    main(sys.argv[1])
