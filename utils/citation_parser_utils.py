"""
Citation Parser Utilities: Common regex patterns and parsing functions.

Provides compiled regex patterns and reusable citation parsing logic
to eliminate duplication and improve performance.
"""
import re
from typing import Dict, Tuple, Optional


# ============================================================================
# Compiled Regex Patterns (compiled once at module load)
# ============================================================================

# Author patterns
AUTHOR_NAME_PATTERN = re.compile(r'\b[A-Z][a-z]+,\s*[A-Z]\.?', re.I)
AUTHOR_INITIALS_PATTERN = re.compile(r'\b[A-Z]\.?\s+[A-Z]\.?\s+[A-Z][a-z]+', re.I)
AUTHOR_ET_AL_PATTERN = re.compile(r'\b(et\s+al\.|&|and)\b', re.I)
AUTHOR_LASTNAME_INITIAL = re.compile(r'^[A-Z][A-Za-z\'\-]+,\s*[A-Z](?:[A-Z]|\.)*', re.I)

# Date patterns
YEAR_PATTERN = re.compile(r'\b(19|20)\d{2}\b')
MONTH_PATTERN = re.compile(
    r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|'
    r'jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b',
    re.I
)
DATE_RANGE_SAME_MONTH = re.compile(
    r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|'
    r'aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?\s*'
    r'(\d{1,2})\s*[-–]\s*(\d{1,2})(?:\s*,\s*(\d{4}))?',
    re.I
)
DATE_RANGE_CROSS_MONTH = re.compile(
    r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|'
    r'aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?\s*'
    r'(\d{1,2})\s*[-–]\s*'
    r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|'
    r'aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?\s*'
    r'(\d{1,2})(?:\s*,\s*(\d{4}))?',
    re.I
)

# Conference patterns
CONFERENCE_KEYWORDS = re.compile(
    r'\b(conference|symposium|meeting|workshop|seminar|congress|summit)\b',
    re.I
)
ORDINAL_PATTERN = re.compile(r'\b(\d+)\s*(?:st|nd|rd|th)\b', re.I)

# Title patterns
QUOTED_TEXT_PATTERN = re.compile(r'["\'“”]([^"\'“”]+)["\'“”]')
BRACKETED_TEXT_PATTERN = re.compile(r'\[[^\]]*\]')

# Location patterns
STATE_ABBREV_PATTERN = re.compile(r'\b[A-Z]{2}\b')

# Journal patterns
VOLUME_ISSUE_PATTERN = re.compile(r'\bvol\.?\s*(\d+)', re.I)
ISSUE_PATTERN = re.compile(r'\b(?:no\.|issue)\s*(\d+)', re.I)
PAGES_PATTERN = re.compile(r'\bpp?\.?\s*(\d+)\s*[-–]\s*(\d+)', re.I)
DOI_PATTERN = re.compile(r'\bdoi:\s*([^\s]+)', re.I)

# Month name to number mapping
MONTH_MAP = {
    'jan': '01', 'january': '01',
    'feb': '02', 'february': '02',
    'mar': '03', 'march': '03',
    'apr': '04', 'april': '04',
    'may': '05',
    'jun': '06', 'june': '06',
    'jul': '07', 'july': '07',
    'aug': '08', 'august': '08',
    'sep': '09', 'sept': '09', 'september': '09',
    'oct': '10', 'october': '10',
    'nov': '11', 'november': '11',
    'dec': '12', 'december': '12',
}


# ============================================================================
# Parsing Functions
# ============================================================================

def extract_year(text: str) -> Optional[str]:
    """Extract 4-digit year from text."""
    match = YEAR_PATTERN.search(text)
    return match.group(0) if match else None


def extract_quoted_text(text: str) -> Optional[str]:
    """Extract text within quotes."""
    match = QUOTED_TEXT_PATTERN.search(text)
    return match.group(1).strip() if match else None


def is_author_like(text: str) -> bool:
    """
    Check if text looks like author names.
    
    Returns True if text contains patterns like:
    - "Lastname, F."
    - "et al."
    - Multiple initials and commas
    """
    text = text.strip().rstrip(' ,')
    if not text:
        return False
    
    # Check for et al or conjunctions
    if AUTHOR_ET_AL_PATTERN.search(text):
        return True
    
    # Check for Lastname, Initial pattern
    if AUTHOR_LASTNAME_INITIAL.match(text):
        return True
    
    # Short fragment with comma (likely name)
    if ',' in text and len(text) <= 25 and len(text.split()) <= 4:
        return True
    
    return False


def extract_date_range(text: str, year_hint: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract date range from text (conference_date_from, conference_date_to).
    
    Returns:
        Tuple of (from_date, to_date) in MM/DD/YYYY format, or (None, None)
    
    Examples:
        "November 22-23, 2020" -> ("11/22/2020", "11/23/2020")
        "September 30–October 2, 2024" -> ("09/30/2024", "10/02/2024")
    """
    # Try cross-month range first
    match = DATE_RANGE_CROSS_MONTH.search(text)
    if match:
        m1 = match.group(1).rstrip('.').lower()
        d1 = match.group(2)
        m2 = match.group(3).rstrip('.').lower()
        d2 = match.group(4)
        year = match.group(5) or year_hint
        
        mm1 = MONTH_MAP.get(m1)
        mm2 = MONTH_MAP.get(m2)
        
        if mm1 and mm2 and year:
            from_date = f"{mm1}/{int(d1):02d}/{year}"
            to_date = f"{mm2}/{int(d2):02d}/{year}"
            return (from_date, to_date)
    
    # Try same-month range
    match = DATE_RANGE_SAME_MONTH.search(text)
    if match:
        month_tok = match.group(1).rstrip('.').lower()
        d1 = match.group(2)
        d2 = match.group(3)
        year = match.group(4) or year_hint
        
        mm = MONTH_MAP.get(month_tok)
        
        if mm and year:
            from_date = f"{mm}/{int(d1):02d}/{year}"
            to_date = f"{mm}/{int(d2):02d}/{year}"
            return (from_date, to_date)
    
    return (None, None)


def normalize_conference_number(conf_name: str) -> Tuple[Optional[str], str]:
    """
    Extract conference number and clean conference name.
    
    Args:
        conf_name: Conference name that may contain ordinal numbers
    
    Returns:
        Tuple of (conference_number, cleaned_name)
    
    Examples:
        "35th Annual Meeting" -> ("35", "Annual Meeting")
        "Eighth Annual Conference" -> ("8", "Annual Conference")  # if config supports it
    """
    # Extract numeric ordinal (e.g., "35th")
    match = ORDINAL_PATTERN.search(conf_name)
    if match:
        number = match.group(1)
        # Remove the ordinal from name
        cleaned = ORDINAL_PATTERN.sub('', conf_name)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip(' ,')
        return (number, cleaned)
    
    return (None, conf_name)


def clean_title(title: str) -> str:
    """
    Clean a title by removing common artifacts.
    
    - Removes leading bullets, dashes, asterisks
    - Strips trailing punctuation
    - Removes bracketed descriptors like [Poster Presentation]
    """
    if not title:
        return title
    
    # Remove bracketed descriptors
    title = BRACKETED_TEXT_PATTERN.sub('', title)
    
    # Remove leading special chars
    title = re.sub(r'^[\u2022\-–—\*\s]+', '', title)
    
    # Strip trailing punctuation and spaces
    title = title.rstrip(' .,;:')
    
    return title.strip()


def looks_like_conference_citation(text: str) -> bool:
    """Check if text contains conference-related keywords."""
    return bool(CONFERENCE_KEYWORDS.search(text))


def extract_volume_issue_pages(text: str) -> Dict[str, str]:
    """
    Extract volume, issue, and pages from journal citation text.
    
    Returns:
        Dict with keys: volume, issue, pages (empty strings if not found)
    """
    result = {'volume': '', 'issue': '', 'pages': ''}
    
    # Extract volume
    match = VOLUME_ISSUE_PATTERN.search(text)
    if match:
        result['volume'] = match.group(1)
    
    # Extract issue
    match = ISSUE_PATTERN.search(text)
    if match:
        result['issue'] = match.group(1)
    
    # Extract pages
    match = PAGES_PATTERN.search(text)
    if match:
        result['pages'] = f"{match.group(1)}-{match.group(2)}"
    
    return result


def extract_doi(text: str) -> Optional[str]:
    """Extract DOI from text."""
    match = DOI_PATTERN.search(text)
    return match.group(1) if match else None


def split_into_sentences(text: str) -> list[str]:
    """
    Split text into sentences using conservative boundaries.
    
    Uses period followed by space and capital letter as boundary.
    """
    sentences = [s.strip() for s in re.split(r'\.(?:\s+|$)', text) if s.strip()]
    return sentences


def remove_author_blocks(text: str, max_iterations: int = 20) -> str:
    """
    Remove leading author blocks from citation text.
    
    Handles patterns like:
    - "Lastname, F.M.,"
    - "L.D. Ziemba,"
    - "and Lastname, F.,"
    
    Args:
        text: Citation text
        max_iterations: Safety limit for removal loop
    
    Returns:
        Text with author blocks removed
    """
    removed_any = True
    iterations = 0
    
    while removed_any and iterations < max_iterations:
        removed_any = False
        iterations += 1
        
        # Pattern 1: Lastname, Initials,
        m1 = re.match(r'^\s*[A-Z][A-Za-z\'\-]+,\s*[A-Z](?:[A-Z]|\.)*\.?\s*,?\s*', text)
        # Pattern 2: Initials Lastname,
        m2 = re.match(r'^\s*(?:[A-Z](?:[A-Z]|\.)\s+)+[A-Z][A-Za-z\'\-]+,\s*', text)
        # Pattern 3: and Lastname/Initials
        m3 = re.match(
            r'^\s*and\s+(?:[A-Z][A-Za-z\'\-]+,\s*[A-Z](?:[A-Z]|\.)*\.?\s*,?\s*|'
            r'(?:[A-Z](?:[A-Z]|\.)\s+)+[A-Z][A-Za-z\'\-]+,\s*)',
            text,
            flags=re.I
        )
        
        if m1:
            text = text[m1.end():].lstrip()
            removed_any = True
        elif m2:
            text = text[m2.end():].lstrip()
            removed_any = True
        elif m3:
            text = text[m3.end():].lstrip()
            removed_any = True
    
    return text


def extract_title_from_citation(text: str, exclude_patterns: Optional[list[str]] = None) -> Optional[str]:
    """
    Extract likely title from citation text using heuristics.
    
    Args:
        text: Full citation text
        exclude_patterns: Optional list of strings to exclude (e.g., conference name, location)
    
    Returns:
        Extracted title or None
    """
    exclude_patterns = exclude_patterns or []
    
    # Remove bracketed descriptors
    work = BRACKETED_TEXT_PATTERN.sub('', text)
    
    # Try to get text after date parentheses
    parts = re.split(r'\)\.?\s*', work, maxsplit=1)
    after = parts[1].strip() if len(parts) > 1 else work.strip()
    
    # Remove author blocks
    after = remove_author_blocks(after)
    
    # Split into sentences
    sentences = split_into_sentences(after)
    
    # Find best candidate (longest non-author, non-conference sentence)
    candidates = []
    for sent in sentences:
        sent_clean = sent.strip().rstrip(' ,')
        
        # Skip if too short
        if len(sent_clean) < 20:
            continue
        
        # Skip if looks like author
        if is_author_like(sent_clean):
            continue
        
        # Skip if contains exclude patterns
        if any(excl.lower() in sent_clean.lower() for excl in exclude_patterns):
            continue
        
        # Skip if starts with author pattern
        if AUTHOR_LASTNAME_INITIAL.match(sent_clean):
            continue
        
        # Skip if conference keywords only
        if CONFERENCE_KEYWORDS.search(sent_clean) and len(sent_clean) < 40:
            continue
        
        candidates.append((len(sent_clean), sent_clean))
    
    if candidates:
        # Sort by length and return longest
        candidates.sort(reverse=True, key=lambda x: x[0])
        return clean_title(candidates[0][1])
    
    return None
