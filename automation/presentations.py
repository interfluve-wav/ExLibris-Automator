"""
Thin wrapper: re-exports the presentation automation API from
`automation.presentations_impl` (parse_any_citation, goto_with_retries,
save_citation_to_csv, process_citation).
"""
from .presentations_impl import (
    parse_any_citation,
    goto_with_retries,
    save_citation_to_csv,
    process_citation,
)


