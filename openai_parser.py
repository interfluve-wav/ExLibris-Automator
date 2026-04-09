"""
OpenAI-powered citation parser that returns a unified schema across
conference presentations, proceedings, posters, and journal articles.
Used by the automation flows and the Discord bot.
"""
import os
import re
import json
import hashlib
from functools import lru_cache
from typing import Dict, Optional
from utils.logging_utils import make_logger
from utils.config_utils import extract_ordinal_word_number
from utils.asset_type_utils import normalize_asset_type_from_parser
from utils.citation_parser_utils import (
    extract_year, extract_quoted_text, is_author_like,
    extract_date_range, normalize_conference_number,
    clean_title, looks_like_conference_citation,
    YEAR_PATTERN, ORDINAL_PATTERN, CONFERENCE_KEYWORDS,
    BRACKETED_TEXT_PATTERN, AUTHOR_LASTNAME_INITIAL,
    remove_author_blocks, extract_title_from_citation
)

LOG = make_logger("PARSER")

# Silence verbose SDK logs unless explicitly enabled
_force_openai_log = os.getenv("FORCE_OPENAI_LOG", "").lower() in ("1", "true", "yes")
if not _force_openai_log:
    os.environ.pop("OPENAI_LOG", None)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# ============================================================================
# Global OpenAI client (cached, not recreated on every call)
# ============================================================================
_openai_client: Optional[OpenAI] = None
_openai_client_api_key: Optional[str] = None

def _get_openai_client() -> Optional[OpenAI]:
    """Get or create cached OpenAI client."""
    global _openai_client, _openai_client_api_key
    
    if OpenAI is None:
        return None
    
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    
    # Create new client if API key changed or client doesn't exist
    if _openai_client is None or _openai_client_api_key != api_key:
        _openai_client = OpenAI(api_key=api_key)
        _openai_client_api_key = api_key
    
    return _openai_client

# ============================================================================
# Response caching (LRU cache for identical citations)
# ============================================================================
@lru_cache(maxsize=100)
def _cached_parse(citation_hash: str, citation_text: str, model: str) -> str:
    """Cache OpenAI responses by citation hash."""
    # This function is wrapped by parse_citation_with_openai
    # The actual API call happens there
    pass


def _extract_json_object(text: str) -> Dict[str, str]:
    """Extract the first JSON object from arbitrary text."""
    try:
        match = re.search(r"\{[\s\S]*\}", text)
        return json.loads(match.group(0)) if match else {}
    except Exception:
        return {}


def parse_citation_with_openai(citation_text: str) -> Dict[str, str]:
    """
    Parse an academic citation using the OpenAI API.

    Supports multiple asset types, including: conference_presentation, conference_proceeding,
    poster_presentation, journal_article, book_chapter, abstract, technical_documentation.
    The output is a single JSON object with a unified schema that remains backward-compatible with the presentation flow.

    Environment variables:
    - OPENAI_API_KEY  (required)
    - OPENAI_MODEL    (default: gpt-4o-mini)
    """
    text = (citation_text or "").strip()
    if not text:
        return {}

    # Use cached client
    client = _get_openai_client()
    if client is None:
        return {"error": "OpenAI client not available"}

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    
    # Check cache (hash the input for cache key)
    citation_hash = hashlib.md5(f"{text}:{model}".encode()).hexdigest()
    # Note: actual caching happens at API level, this is for future enhancement

    system_msg = (
        "You are an expert citation parser for multiple academic asset types. "
        "Detect the asset type and extract a unified set of fields. "
        "Output must be ONE JSON object only (no markdown, no code fences, no extra text). "
        "Unknown or inapplicable fields must be empty strings. Trim trailing punctuation. "
        "Date formatting rules: if a single exact day exists -> MM/DD/YYYY; if only month and year -> MM/YYYY; otherwise -> YYYY. "
        "Also extract conference_date_from and conference_date_to in MM/DD/YYYY when a day range is present (e.g., 'November 22-23, 2020' -> '11/22/2020' and '11/23/2020'; 'September 30–October 2, 2024' -> '09/30/2024' and '10/02/2024'). If not present, leave them empty. "
        "For cross-month date ranges (e.g., September 30–October 2, 2024) set MM/YYYY using the LAST month. "
        "For conference presentations and posters, 'published_proceedings_title' must be empty. "
        "The 'proceedings_title' is the talk/presentation title only. It is NOT the location or the conference name; never set it to a place like 'Boston, MA' or to the conference name. "
        "For book chapters: 'proceedings_title' is the chapter title; 'book_title' is the book title; 'editors' are the book editors (if present); 'publication_place' is the city and state/country (e.g., 'Charlotte, NC'); 'start_page' and 'end_page' are page numbers if present; 'isbn' and 'eisbn' are ISBN numbers if present; 'edition' is the edition number if present. "
        "IMPORTANT: Titles are often in quotation marks (\"Title Here\"). Extract the text INSIDE the quotes as the title, without the quotes. "
        "IMPORTANT: Do NOT confuse author names (Lastname, Firstname) with titles. If you see 'Author, Name. \"Title Here\"' - the title is \"Title Here\", NOT 'Author, Name'. "
        "Never invent data; prefer empty strings when unsure."
    )
    
    user_msg = f"""
Citation:
{text}

Return JSON with these EXACT keys (always include all keys):
- asset_type  (one of: conference_presentation, conference_proceeding, poster_presentation, journal_article, book_chapter, abstract, technical_documentation, other)
- proceedings_title  (title of the presentation/proceeding/chapter; extract text from inside quotes if present; for journal_article leave empty)
- article_title  (for journal articles; extract text from inside quotes if present; otherwise empty)
- authors  (as appears in the citation; typically "Lastname, Firstname" format)
- year  (4-digit year)
- date_presented  (raw human-readable date segment or year; follow date rules above)
- date_presented_mmddyyyy  (MM/DD/YYYY if single day; else empty)
- date_presented_mmyyyy  (MM/YYYY if month-year; else empty)
- conference_date_from  (MM/DD/YYYY if a day range is present; else empty)
- conference_date_to  (MM/DD/YYYY if a day range is present; else empty)
- published_proceedings_title  (only for proceedings, otherwise empty)
- conference_name
- conference_number  (digits only, e.g., "12")
- conference_location
- journal_name  (for journal articles; otherwise empty)
- volume  (for journal articles and conference proceedings; volume number if present; otherwise empty)
- issue  (for journal articles; otherwise empty)
- pages  (for journal articles; page range if present; otherwise empty)
- doi  (for journal articles; otherwise empty)
- book_title  (for book chapters; otherwise empty)
- editors  (for book chapters and conference proceedings; editors of the book/proceedings if present; otherwise empty)
- publication_place  (for book chapters; city and state/country, e.g., "Charlotte, NC"; otherwise empty)
- start_page  (for book chapters and conference proceedings; first page number if present; otherwise empty)
- end_page  (for book chapters and conference proceedings; last page number if present; otherwise empty)
- isbn  (for book chapters; ISBN number if present; otherwise empty)
- eisbn  (for book chapters; electronic ISBN if present; otherwise empty)
- edition  (for book chapters; edition number if present; otherwise empty)
- publisher_name  (for technical documentation, conference proceedings, and book chapters; organization/publisher if present; otherwise empty)
- report_number  (for technical documentation; report or document number; otherwise empty)
- asset_title  (for technical documentation; use the document title; otherwise empty)
- research_topics  (comma-separated or empty)
- link  (URL if present; otherwise empty)
""".strip()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
            timeout=30.0,  # 30 second timeout to prevent hanging
        )

        content = ""
        try:
            content = response.choices[0].message.content or ""
        except (IndexError, AttributeError) as e:
            LOG.error(f"Failed to extract OpenAI response content: {e}")
            content = ""

        if not content:
            LOG.warn("OpenAI returned empty content")
            return {}

        try:
            parsed = json.loads(content) if content.strip().startswith("{") else _extract_json_object(content)
        except json.JSONDecodeError as e:
            LOG.warn(f"Failed to parse OpenAI JSON response, trying fallback: {e}")
            parsed = _extract_json_object(content)

        defaults = {
            # General/compat layer
            "asset_type": "",
            "proceedings_title": "",
            "article_title": "",
            "authors": "",
            "year": "",
            "date_presented": "",
            "date_presented_mmddyyyy": "",
            "date_presented_mmyyyy": "",
            "conference_date_from": "",
            "conference_date_to": "",
            "published_proceedings_title": "",
            # Conference
            "conference_name": "",
            "conference_number": "",
            "conference_location": "",
            # Journal
            "journal_name": "",
            "volume": "",
            "issue": "",
            "pages": "",
            "doi": "",
            # Book Chapter
            "book_title": "",
            "editors": "",
            "publication_place": "",
            "start_page": "",
            "end_page": "",
            "isbn": "",
            "eisbn": "",
            "edition": "",
            # Technical Documentation
            "publisher_name": "",
            "report_number": "",
            "asset_title": "",
            # Misc
            "research_topics": "",
            "link": "",
        }
        out = {**defaults, **(parsed or {})}

        # Normalize asset_type using shared utility
        out["asset_type"] = normalize_asset_type_from_parser(out.get("asset_type", ""))

        # Minimal sanity check: must have either a title (proceedings/article) or at least authors+year
        if not (out.get("proceedings_title") or out.get("article_title") or (out.get("authors") and out.get("year"))):
            return {}

        # Normalize conference_number to digits only
        try:
            if out.get("conference_number"):
                m = re.match(r"\s*(\d+)", out["conference_number"]) 
                if m:
                    out["conference_number"] = m.group(1)
        except Exception:
            pass

        # Handle textual ordinal via config (e.g., "Eighth Annual …" -> number=8 and strip "Eighth")
        try:
            conf_name_val = (out.get("conference_name") or "").strip()
            if conf_name_val:
                detected_num, cleaned_name = extract_ordinal_word_number(conf_name_val)
                if detected_num and not (out.get("conference_number") or "").strip():
                    out["conference_number"] = detected_num
                if detected_num:
                    out["conference_name"] = cleaned_name
        except Exception:
            pass

        # If conference_number is present, remove its ordinal token from conference_name (e.g., "35th")
        try:
            conf_num = (out.get("conference_number") or "").strip()
            conf_name_val = (out.get("conference_name") or "").strip()
            if conf_num and conf_name_val:
                cleaned = re.sub(rf"\b{re.escape(conf_num)}\s*(?:st|nd|rd|th)\b", "", conf_name_val, flags=re.I)
                cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,")
                out["conference_name"] = cleaned
        except Exception:
            pass

        # If year missing, try to derive from date fields
        if not out.get("year"):
            for date_key in ("date_presented_mmddyyyy", "date_presented_mmyyyy", "date_presented"):
                val = (out.get(date_key) or "").strip()
                m_year = re.search(r"\b(\d{4})\b", val)
                if m_year:
                    out["year"] = m_year.group(1)
                    break

        # Derive conference_date_from/to from date_presented when a range is present and fields are empty
        try:
            if not out.get("conference_date_from") and not out.get("conference_date_to"):
                date_text = (out.get("date_presented") or "").strip()
                year_text = (out.get("year") or "").strip()
                month_map = {
                    'jan': '01','january': '01','feb': '02','february': '02','mar': '03','march': '03',
                    'apr': '04','april': '04','may': '05','jun': '06','june': '06','jul': '07','july': '07',
                    'aug': '08','august': '08','sep': '09','sept': '09','september': '09','oct': '10','october': '10',
                    'nov': '11','november': '11','dec': '12','december': '12',
                }
                # Cross-month: September 30-October 2, 2024
                m_cross = re.search(
                    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?\s*(\d{1,2})\s*[-–]\s*\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?\s*(\d{1,2})(?:\s*,\s*(\d{4}))?",
                    date_text,
                    flags=re.I,
                )
                m_same = None
                if not m_cross:
                    # Same-month: November 22-23, 2020
                    m_same = re.search(
                        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?\s*(\d{1,2})\s*[-–]\s*(\d{1,2})(?:\s*,\s*(\d{4}))?",
                        date_text,
                        flags=re.I,
                    )
                if m_cross or m_same:
                    if m_cross:
                        m1 = m_cross.group(1).rstrip('.').lower(); d1 = m_cross.group(2)
                        m2 = m_cross.group(3).rstrip('.').lower(); d2 = m_cross.group(4)
                        y = m_cross.group(5) or year_text
                        mm1 = month_map.get(m1, ""); mm2 = month_map.get(m2, "")
                        if mm1 and mm2 and y:
                            out["conference_date_from"] = f"{mm1}/{int(d1):02d}/{y}"
                            out["conference_date_to"] = f"{mm2}/{int(d2):02d}/{y}"
                    else:
                        m_tok = m_same.group(1).rstrip('.').lower(); d1 = m_same.group(2); d2 = m_same.group(3)
                        y = m_same.group(4) or year_text
                        mm = month_map.get(m_tok, "")
                        if mm and y:
                            out["conference_date_from"] = f"{mm}/{int(d1):02d}/{y}"
                            out["conference_date_to"] = f"{mm}/{int(d2):02d}/{y}"
        except Exception:
            pass

        # Heuristic correction: if the title is empty, equals location/conference name, or clearly looks like an author fragment,
        # derive the title from content after the date or author segment. Robustly skip author-like fragments such as
        # "Lastname, F." or "Lastname, F.M." and short initial-only segments created by naive period splitting.
        try:
            title_val = (out.get("proceedings_title") or "").strip()
            location_val = (out.get("conference_location") or "").strip()
            conf_name_val = (out.get("conference_name") or "").strip()
            # Detect titles that look like author fragments (commas plus initials/&/and, or "Lastname, Initials" forms)
            looks_like_authors = False
            try:
                if title_val:
                    title_val_clean = title_val.strip()
                    # Check for patterns like "Ziemba, R.J" or "Lastname, Initial" (exactly matches author name pattern)
                    if re.fullmatch(r"[A-Z][A-Za-z'\-]+,\s*[A-Z](?:[A-Z]|\.)*\s*", title_val_clean, flags=re.I):
                        looks_like_authors = True
                    # Check for patterns with initials and commas
                    elif (re.search(r"\b[A-Z]\.\b", title_val) and title_val.count(',') >= 1) or re.search(r"\b(et\s+al\.|&|and)\b", title_val, flags=re.I):
                        looks_like_authors = True
                    # Match "Lastname, F" or "Lastname, F.M" patterns (case-insensitive)
                    elif re.fullmatch(r"[A-Z][A-Za-z'\-]+,\s*[A-Z](?:[A-Z]|\.)*", title_val_clean, flags=re.I):
                        looks_like_authors = True
                    # Or very short comma fragments likely to be name initials (e.g., "Doe, J" or "Smith, A.B")
                    elif (',' in title_val_clean) and (len(title_val_clean) <= 25) and (len(title_val_clean.split()) <= 4):
                        # Additional check: if it matches the pattern of Lastname, Initial(s), it's likely an author
                        if re.match(r"^[A-Z][A-Za-z'\-]+,\s*[A-Z]", title_val_clean, flags=re.I):
                            looks_like_authors = True
            except Exception:
                looks_like_authors = False

            needs_title_fix = (
                not title_val
                or (location_val and title_val == location_val)
                or (conf_name_val and title_val == conf_name_val)
                or len(title_val.strip('. ,')) < 5
                or looks_like_authors
            )
            if needs_title_fix and (out.get("asset_type") in {"conference_presentation", "poster_presentation", "conference_proceeding", "other", ""}):
                # Remove bracketed descriptors like [Poster Presentation]
                work = re.sub(r"\[[^\]]*\]", "", text)
                # Prefer the text after a date ")" if present; otherwise use the whole text
                parts_after_date = re.split(r"\)\.?\s*", work, maxsplit=1)
                after = parts_after_date[1].strip() if len(parts_after_date) > 1 else work.strip()

                # If the string starts with an author block, drop that leading block
                # Handle full author lists like "L.D. Ziemba, R.J. Griffin, ..., and B. Rappenglück,"
                try:
                    # For citations without dates, we need to remove the entire author list
                    # Pattern: Match author names in format "Initials Lastname," or "Lastname, Initials,"
                    # Keep removing author blocks until we hit something that doesn't look like an author
                    removed_any = True
                    iterations = 0
                    while removed_any and iterations < 20:  # Safety limit
                        removed_any = False
                        iterations += 1
                        
                        # Try pattern: "Lastname, Initials," or "Initials Lastname,"
                        # Match: Lastname, Initials, (with optional dots in initials)
                        m1 = re.match(r"^\s*[A-Z][A-Za-z'\-]+,\s*[A-Z](?:[A-Z]|\.)*\.?\s*,?\s*", after)
                        # Match: Initials Lastname, (e.g., "L.D. Ziemba," or "R.J. Griffin,")
                        m2 = re.match(r"^\s*(?:[A-Z](?:[A-Z]|\.)\s+)+[A-Z][A-Za-z'\-]+,\s*", after)
                        # Match: "and Lastname, Initials," or "and Initials Lastname,"
                        m3 = re.match(r"^\s*and\s+(?:[A-Z][A-Za-z'\-]+,\s*[A-Z](?:[A-Z]|\.)*\.?\s*,?\s*|(?:[A-Z](?:[A-Z]|\.)\s+)+[A-Z][A-Za-z'\-]+,\s*)", after, flags=re.I)
                        
                        if m1:
                            after = after[m1.end():].lstrip()
                            removed_any = True
                        elif m2:
                            after = after[m2.end():].lstrip()
                            removed_any = True
                        elif m3:
                            after = after[m3.end():].lstrip()
                            removed_any = True
                except Exception:
                    pass

                # For citations without dates, split by commas first to handle author lists properly
                # Then identify the title segment (usually the longest non-author segment)
                if not re.search(r"\)", work) and looks_like_authors:
                    # Split by commas to get segments
                    comma_segments = [s.strip() for s in after.split(',') if s.strip()]
                    
                    # Find where authors end and title begins
                    # Authors typically end with a pattern like "and Lastname" or just "Lastname"
                    # After that, the title begins
                    author_end_idx = -1
                    for i, seg in enumerate(comma_segments):
                        seg_clean = seg.strip()
                        # Check if this looks like the end of author list
                        # Pattern: "and Lastname" or just "Lastname" (short, likely author)
                        if re.match(r"^(and\s+)?[A-Z](?:[A-Z]|\.)+\s+[A-Z][A-Za-z'\-]+$", seg_clean) or \
                           (len(seg_clean) <= 25 and re.match(r"^[A-Z][A-Za-z'\-]+$", seg_clean)):
                            author_end_idx = i
                        # If we hit a long segment that doesn't look like an author, that's likely the title start
                        elif len(seg_clean) > 30 and not re.match(r"^[A-Z](?:[A-Z]|\.)+\s+[A-Z][A-Za-z'\-]+$", seg_clean):
                            # This is likely the start of the title
                            if author_end_idx == -1:
                                author_end_idx = i - 1  # Title starts here
                            break
                    
                    # Extract title segments (everything after authors until we hit conference/location)
                    if author_end_idx >= 0 and author_end_idx < len(comma_segments) - 1:
                        title_parts = []
                        for i in range(author_end_idx + 1, len(comma_segments)):
                            seg = comma_segments[i].strip()
                            # Stop if we hit conference keywords
                            if re.search(r"\b(conference|symposium|meeting|workshop|annual)\b", seg, flags=re.I):
                                break
                            # Stop if we hit a location pattern (short with state abbreviation)
                            if len(seg) <= 3 and re.match(r"^[A-Z]{2}$", seg):
                                # This might be part of the title (like "TX" in "Houston, TX")
                                # Check if previous segment was long (likely part of title)
                                if title_parts and len(title_parts[-1]) > 20:
                                    title_parts.append(seg)
                                break
                            # Stop if we hit a month/year
                            if re.search(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\s+\d{4}$", seg, flags=re.I):
                                break
                            # Add to title parts
                            title_parts.append(seg)
                        
                        if title_parts:
                            potential_title = ", ".join(title_parts).strip().rstrip(' ,')
                            if len(potential_title) > 20:  # Minimum title length
                                title_candidate = potential_title
                
                # Split into candidate sentences; use a conservative boundary: period followed by space and a capital and >=3 chars ahead
                # Fallback to simple split if needed
                sentences = []
                if not title_candidate:  # Only split if we haven't found a title yet
                    try:
                        sentences = [s.strip() for s in re.split(r"\.(?:\s+|$)", after) if s.strip()]
                    except Exception:
                        sentences = [s.strip() for s in after.split('.') if s.strip()]

                def is_author_like(s: str) -> bool:
                    s_stripped = s.strip().rstrip(' ,')
                    if not s_stripped:
                        return False
                    # Contains "et al." or conjunctions typical in author lists
                    if re.search(r"\b(et\s+al\.|&|and)\b", s_stripped, flags=re.I):
                        return True
                    # Pattern: Lastname, Initials (with or without dots), possibly multiple initials
                    if re.match(r"^[A-Z][A-Za-z'\-]+,\s*[A-Z](?:[A-Z]|\.)*(?:\s+[A-Z](?:[A-Z]|\.)*)?$", s_stripped):
                        return True
                    # Short fragment with comma and 1-2 tokens only (e.g., "Doe, J")
                    if (',' in s_stripped) and (len(s_stripped) <= 20) and (len(s_stripped.split()) <= 3):
                        return True
                    return False

                def is_bad_candidate(s: str) -> bool:
                    # Exclude conference-y or location-only fragments
                    if re.search(r"\b(conference|symposium|meeting|workshop)\b", s, flags=re.I):
                        return True
                    # Exclude pure year fragments
                    if re.fullmatch(r"\s*\d{4}\s*", s):
                        return True
                    return False

                title_candidate = None
                
                # For citations without dates in parentheses where title looks like an author,
                # we need to be more aggressive in finding the actual title
                if not re.search(r"\)", work) and looks_like_authors:
                    # Find the longest sentence that doesn't look like an author or conference info
                    candidates = []
                    for s in sentences:
                        s_clean = s.strip().rstrip(' ,')
                        if len(s_clean) < 20:  # Titles should be at least 20 chars
                            continue
                        if is_author_like(s_clean) or is_bad_candidate(s_clean):
                            continue
                        # Prefer sentences that are longer and don't start with a capital letter followed by a comma
                        # (which would indicate an author name)
                        if not re.match(r"^[A-Z][A-Za-z'\-]+,\s*[A-Z]", s_clean):
                            candidates.append((len(s_clean), s_clean))
                    
                    if candidates:
                        # Sort by length (longest first) and take the first one
                        candidates.sort(reverse=True, key=lambda x: x[0])
                        title_candidate = candidates[0][1]
                    else:
                        # If no good candidates, try all sentences regardless of length check
                        for s in sentences:
                            s_clean = s.strip().rstrip(' ,')
                            if len(s_clean) < 15:
                                continue
                            if is_author_like(s_clean) or is_bad_candidate(s_clean):
                                continue
                            if not re.match(r"^[A-Z][A-Za-z'\-]+,\s*[A-Z]", s_clean):
                                title_candidate = s_clean
                                break
                
                # If we didn't find a title yet, use the standard approach
                if not title_candidate:
                    for s in sentences:
                        s_clean = s.strip().rstrip(' ,')
                        if is_author_like(s_clean) or is_bad_candidate(s_clean):
                            continue
                        if len(s_clean) < 6:
                            continue
                        # Skip if it starts with Lastname, Initial pattern
                        if re.match(r"^[A-Z][A-Za-z'\-]+,\s*[A-Z]", s_clean):
                            continue
                        title_candidate = s_clean
                        break

                # As a last resort, take the longest non-author-like fragment
                if not title_candidate and sentences:
                    non_author = [s for s in sentences if not is_author_like(s) and not is_bad_candidate(s)]
                    if non_author:
                        # Filter out author-like patterns
                        filtered = [s for s in non_author if not re.match(r"^[A-Z][A-Za-z'\-]+,\s*[A-Z]", s.strip())]
                        if filtered:
                            title_candidate = max(filtered, key=lambda x: len(x))
                        else:
                            title_candidate = max(non_author, key=lambda x: len(x))

                if title_candidate:
                    title_candidate = re.sub(r"^[\u2022\-\–\—\*\s]+", "", title_candidate)
                    out["proceedings_title"] = title_candidate.rstrip(' .')
        except Exception:
            pass

        # If still missing a presentation title but article_title is present and this looks like a conference-type
        # citation, promote article_title to proceedings_title for compatibility with the presentation flow.
        try:
            looks_like_conference = bool(re.search(r"\b(conference|symposium|meeting|workshop)\b", text, flags=re.I))
            if (
                not (out.get("proceedings_title") or "").strip()
                and (out.get("article_title") or "").strip()
                and (looks_like_conference or (out.get("asset_type") != "journal_article"))
            ):
                out["proceedings_title"] = (out.get("article_title") or "").strip().rstrip(' .')
        except Exception:
            pass

        # Additional fallback: Extract quoted title if proceedings_title looks wrong
        try:
            title_val = (out.get("proceedings_title") or "").strip()
            # Check if title looks like it's actually an author fragment (e.g., ", Jacqueline")
            looks_like_bad_title = (
                not title_val or
                title_val.startswith(',') or
                title_val.count(',') > 2 or
                (len(title_val) < 15 and ',' in title_val)
            )
            
            if looks_like_bad_title:
                # Try to extract quoted text as the title
                quoted_match = re.search(r'["""]([^"""]+)["""]', text)
                if quoted_match:
                    extracted_title = quoted_match.group(1).strip().rstrip(' .')
                    if len(extracted_title) > 5:  # Sanity check
                        out["proceedings_title"] = extracted_title
                        print(f"   Extracted quoted title: {extracted_title}")
        except Exception as e:
            pass

        # For presentations/posters (or when it looks like a conference citation), ensure published_proceedings_title is empty
        try:
            if out.get("asset_type") in {"conference_presentation", "poster_presentation"} or re.search(r"\b(conference|symposium|meeting|workshop)\b", text, flags=re.I):
                out["published_proceedings_title"] = ""
        except Exception:
            pass

        return out
    except Exception as e:
        import traceback
        error_msg = f"OpenAI API error: {str(e)}"
        LOG.error(error_msg)
        LOG.debug(f"Traceback: {traceback.format_exc()}")
        return {"error": error_msg}


