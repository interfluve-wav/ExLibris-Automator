"""
Shared utility for normalizing asset types across all components.
Ensures Discord bot, Flask app, worker, and parser all use consistent asset type values.
"""

# Valid asset types that the system supports
VALID_ASSET_TYPES = {
    "conference_presentation",
    "conference_proceeding",
    "poster_presentation",
    "journal_article",
    "book_chapter",
    "abstract",
    "technical_documentation",
    "other"
}

# Valid modes for bot configuration (snake_case)
VALID_CONFIG_MODES = {
    "auto",
    "presentation",
    "poster",
    "book_chapter",
    "journal_article",
    "proceedings",
    "abstract",
    "technical_documentation",
}

# Mapping from OpenAI parser asset types to config modes
ASSET_TYPE_TO_CONFIG_MODE = {
    "conference_presentation": "presentation",
    "poster_presentation": "poster",
    "conference_proceeding": "proceedings",
    "journal_article": "journal_article",
    "book_chapter": "book_chapter",
    "abstract": "abstract",
    "technical_documentation": "technical_documentation",
    "other": "presentation"  # Default fallback
}

# Mapping from config modes to OpenAI parser asset types
CONFIG_MODE_TO_ASSET_TYPE = {
    "auto": "",  # Auto mode doesn't override
    "presentation": "conference_presentation",
    "poster": "poster_presentation",
    "proceedings": "conference_proceeding",
    "journal_article": "journal_article",
    "book_chapter": "book_chapter",
    "abstract": "abstract",
    "technical_documentation": "technical_documentation",
}


def normalize_asset_type_from_parser(asset_type: str) -> str:
    """
    Normalize asset type returned by OpenAI parser to valid system values.

    Args:
        asset_type: Raw asset type string from parser

    Returns:
        Normalized asset type (one of VALID_ASSET_TYPES)
    """
    if not asset_type:
        return "conference_presentation"

    asset_type_lower = asset_type.strip().lower()

    # Map common variations to valid types
    type_map = {
        # Technical documentation variants - keep as technical_documentation
        "technical_documentation": "technical_documentation",
        "technical document": "technical_documentation",
        "documentation": "technical_documentation",
        "whitepaper": "technical_documentation",
        "white paper": "technical_documentation",
        "report": "technical_documentation",
        "technical report": "technical_documentation",
        "tech doc": "technical_documentation",
        "techdoc": "technical_documentation",

        # Presentation variants
        "conference presentation": "conference_presentation",
        "presentation": "conference_presentation",

        # Poster variants
        "poster": "poster_presentation",

        # Proceedings variants
        "proceeding": "conference_proceeding",
        "proceedings": "conference_proceeding",
        "conference_proceeding": "conference_proceeding",
        "conference_proceedings": "conference_proceeding",

        # Journal variants
        "journal": "journal_article",
        "article": "journal_article",

        # Book chapter variants
        "chapter": "book_chapter",
        "bookchapter": "book_chapter",
        "book chapter": "book_chapter",

        # Abstract variants
        "abstract": "abstract",
        "conference_abstract": "abstract",

        # Already valid types (normalized)
        "conference_presentation": "conference_presentation",
        "poster_presentation": "poster_presentation",
        "journal_article": "journal_article",
        "technical_documentation": "technical_documentation",
        "other": "other"
    }

    normalized = type_map.get(asset_type_lower, "conference_presentation")
    return normalized


def normalize_config_mode(mode: str) -> str:
    """
    Normalize config mode string to valid values.

    Args:
        mode: Raw mode string from user input or config

    Returns:
        Normalized mode (one of VALID_CONFIG_MODES)
    """
    if not mode:
        return "auto"

    mode_lower = mode.strip().lower()

    # Map variations to valid config modes
    mode_map = {
        "auto": "auto",
        "presentation": "presentation",
        "conference_presentation": "presentation",
        "poster": "poster",
        "poster_presentation": "poster",
        "proceedings": "proceedings",
        "proceeding": "proceedings",
        "conference_proceeding": "proceedings",
        "conference_proceedings": "proceedings",
        "journal": "journal_article",
        "journal_article": "journal_article",
        "article": "journal_article",
        "book_chapter": "book_chapter",
        "bookchapter": "book_chapter",
        "book chapter": "book_chapter",

        # Abstract variants
        "abstract": "abstract",
        "conference_abstract": "abstract",

        # Technical documentation variants
        "technical_documentation": "technical_documentation",
        "technical document": "technical_documentation",
        "tech doc": "technical_documentation",
        "techdoc": "technical_documentation",
        "documentation": "technical_documentation",
        "whitepaper": "technical_documentation",
        "white paper": "technical_documentation",
    }
    normalized = mode_map.get(mode_lower, "auto")
    return normalized


def asset_type_to_config_mode(asset_type: str) -> str:
    """
    Convert asset type to config mode.

    Args:
        asset_type: Asset type from parser (e.g., "conference_presentation")

    Returns:
        Config mode string (e.g., "presentation")
    """
    normalized = normalize_asset_type_from_parser(asset_type)
    return ASSET_TYPE_TO_CONFIG_MODE.get(normalized, "presentation")


def config_mode_to_asset_type(mode: str) -> str:
    """
    Convert config mode to asset type.

    Args:
        mode: Config mode (e.g., "presentation")

    Returns:
        Asset type string (e.g., "conference_presentation")
    """
    normalized = normalize_config_mode(mode)
    return CONFIG_MODE_TO_ASSET_TYPE.get(normalized, "")


def is_valid_asset_type(asset_type: str) -> bool:
    """Check if asset type is valid."""
    return asset_type in VALID_ASSET_TYPES


def is_valid_config_mode(mode: str) -> bool:
    """Check if config mode is valid."""
    return mode in VALID_CONFIG_MODES
