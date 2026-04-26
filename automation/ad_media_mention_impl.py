"""
Ad Media Mention automation.

Initial implementation delegates to the presentation flow so the new asset type
is immediately usable without introducing form-fill regressions. This module is
the dedicated extension point for Ad Media Mention-specific parsing and field
mapping once selectors/requirements are finalized.
"""
import re
from typing import Dict

from .presentations_impl import (
    parse_any_citation as _base_parse_any_citation,
    goto_with_retries,
    save_citation_to_csv,
    process_citation as _base_process_citation,
)


def _classify_media_mention_source(text: str) -> str:
    """
    Classify the citation source for ad media mentions.

    Returns one of:
    - "articles_export_code"
    - "news_article"
    """
    src = (text or "").strip()
    if not src:
        return "news_article"

    # Strong signal for an export/code-like row identifier.
    # Examples this catches: ART-12345, ARTICLE_9988, export code: 7721.
    export_code_patterns = [
        r"\b(?:art|article)[-_ ]?\d{3,}\b",
        r"\b(?:export|article)\s*code\s*[:#-]?\s*[A-Za-z0-9_-]{3,}\b",
        r"\b(?:id|record)\s*[:#-]?\s*(?:art|article)[-_ ]?\d{2,}\b",
    ]
    for pattern in export_code_patterns:
        if re.search(pattern, src, flags=re.I):
            return "articles_export_code"

    # If the citation looks URL/publication/date heavy, treat as a news article.
    news_article_signals = [
        r"https?://",
        r"\b(?:news|times|post|herald|gazette|tribune|journal)\b",
        r"\b(?:published|publication|interview|op-ed)\b",
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\b",
    ]
    if any(re.search(pattern, src, flags=re.I) for pattern in news_article_signals):
        return "news_article"

    # Conservative default: treat as regular news citation unless proven export code.
    return "news_article"


def _extract_url(text: str) -> str:
    m = re.search(r"(https?://[^\s)]+)", text or "", flags=re.I)
    if not m:
        return ""
    return m.group(1).rstrip(".,);")


def _extract_year(text: str) -> str:
    m = re.search(r"\b(19|20)\d{2}\b", text or "")
    return m.group(0) if m else ""


def _derive_title(text: str, url: str) -> str:
    src = (text or "").strip()
    if url:
        src = src.replace(url, " ").strip()
    # Normalize wrapper punctuation from structured input:
    # "Title. (2023). https://..."
    src = re.sub(r"\(\s*(19|20)\d{2}\s*\)", " ", src)
    src = re.sub(r"\b(19|20)\d{2}\b", " ", src)
    src = re.sub(r"\s+", " ", src).strip(" .,-;:")
    return src


def parse_citation(citation_text: str) -> Dict[str, str]:
    """
    Deterministic parser for Ad Media Mention entries.

    Mandatory data model for this workflow:
    - proceedings_title (maps media mention title into existing form flow)
    - year (published year when present)
    - link (source URL when present)
    """
    text = (citation_text or "").strip()
    if not text:
        return {"error": "Empty media mention input"}

    link = _extract_url(text)
    year = _extract_year(text)
    title = _derive_title(text, link)
    if not title and link:
        # Last resort: URL slug as title
        title = link.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").strip()
    if not title:
        return {"error": "Could not derive media mention title"}

    parsed = {
        "proceedings_title": title,
        "year": year,
        "date_presented": year,
        "date_presented_mmyyyy": "",
        "date_presented_mmddyyyy": "",
        "published_proceedings_title": "",
        "conference_name": "",
        "conference_number": "",
        "conference_location": "",
        "research_topics": "",
        "authors": "",
        "link": link,
    }
    return parsed


def parse_any_citation(citation_text: str) -> Dict[str, str]:
    """
    Prefer deterministic media mention parsing; fall back to base parser only if
    deterministic parsing cannot derive a usable title.
    """
    parsed = parse_citation(citation_text)
    if "error" in parsed:
        parsed = _base_parse_any_citation(citation_text) or {}
        if "error" in parsed:
            return parsed

    source_type = _classify_media_mention_source(citation_text)
    parsed["media_mention_source_type"] = source_type
    # Keep original text around for downstream mapping decisions.
    parsed["media_mention_raw_text"] = (citation_text or "").strip()
    return parsed


def process_citation(page, parsed: Dict[str, str], pause_after: bool = False, start_from_home: bool = True):
    """
    Process citation using the existing stable Playwright flow for now.
    Ad Media Mention-specific UI branching will use `media_mention_source_type`.
    """
    return _base_process_citation(
        page,
        parsed,
        pause_after=pause_after,
        start_from_home=start_from_home,
    )

