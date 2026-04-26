"""
Thin wrapper: re-exports the ad media mention automation API from
`automation.ad_media_mention_impl` (parse_any_citation, goto_with_retries,
save_citation_to_csv, process_citation).
"""
from .ad_media_mention_impl import (
    parse_any_citation,
    goto_with_retries,
    save_citation_to_csv,
    process_citation,
)
