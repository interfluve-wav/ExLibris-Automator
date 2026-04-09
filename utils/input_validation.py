"""
Input validation utilities for citation text and user inputs.

Provides validation functions to prevent DoS attacks, injection, and malformed data.
"""
import re
from typing import Tuple


# Constants
MAX_CITATION_LENGTH = 5000  # Maximum characters in a citation
MAX_RESEARCHER_NAME_LENGTH = 200  # Maximum characters in researcher name
MIN_CITATION_LENGTH = 20  # Minimum plausible citation length


def validate_citation_text(text: str) -> Tuple[bool, str]:
    """
    Validate citation text input.

    Args:
        text: The citation text to validate

    Returns:
        Tuple of (is_valid, error_message)
        If valid, error_message is empty string
    """
    if not text or not isinstance(text, str):
        return False, "Citation text cannot be empty"

    text = text.strip()

    if len(text) < MIN_CITATION_LENGTH:
        return False, f"Citation too short (minimum {MIN_CITATION_LENGTH} characters)"

    if len(text) > MAX_CITATION_LENGTH:
        return False, f"Citation too long (maximum {MAX_CITATION_LENGTH} characters)"

    # Check for suspicious patterns (potential injection)
    if re.search(r'<script|javascript:|on\w+\s*=', text, re.IGNORECASE):
        return False, "Citation contains potentially malicious content"

    # Must contain at least some alphabetic characters
    if not re.search(r'[a-zA-Z]{3,}', text):
        return False, "Citation must contain readable text"

    return True, ""


def validate_researcher_name(name: str) -> Tuple[bool, str]:
    """
    Validate researcher name format.

    Args:
        name: Researcher name to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name or not isinstance(name, str):
        return False, "Researcher name cannot be empty"

    name = name.strip()

    if len(name) > MAX_RESEARCHER_NAME_LENGTH:
        return False, f"Researcher name too long (maximum {MAX_RESEARCHER_NAME_LENGTH} characters)"

    # Should contain alphabetic characters
    if not re.search(r'[a-zA-Z]', name):
        return False, "Researcher name must contain letters"

    # Check for suspicious patterns
    if re.search(r'<|>|javascript:|on\w+\s*=', name, re.IGNORECASE):
        return False, "Researcher name contains invalid characters"

    # Common format is "Lastname, Firstname" or "Firstname Lastname"
    # Allow letters, spaces, commas, periods, hyphens, apostrophes
    if not re.match(r"^[a-zA-Z\s,.'\-]+$", name):
        return False, "Researcher name contains invalid characters"

    return True, ""


def sanitize_text(text: str, max_length: int = None) -> str:
    """
    Sanitize text input by removing potentially harmful characters.

    Args:
        text: Text to sanitize
        max_length: Optional maximum length to truncate to

    Returns:
        Sanitized text
    """
    if not text:
        return ""

    # Remove null bytes and other control characters except newlines/tabs
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # Truncate if needed
    if max_length and len(text) > max_length:
        text = text[:max_length]

    return text.strip()


def validate_channel_id(channel_id: any) -> Tuple[bool, str]:
    """
    Validate Discord channel ID.

    Args:
        channel_id: Channel ID to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Channel IDs should be integers or strings of integers
        if isinstance(channel_id, int):
            if channel_id <= 0:
                return False, "Channel ID must be positive"
            return True, ""

        if isinstance(channel_id, str):
            channel_id = channel_id.strip()
            if not channel_id.isdigit():
                return False, "Channel ID must be numeric"
            if int(channel_id) <= 0:
                return False, "Channel ID must be positive"
            return True, ""

        return False, "Channel ID must be an integer or numeric string"
    except ValueError:
        return False, "Invalid channel ID format"
