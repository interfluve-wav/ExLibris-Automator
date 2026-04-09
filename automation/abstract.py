"""
Thin wrapper: re-exports the abstract automation API from
`automation.abstract_impl` (parse_any_citation, goto_with_retries,
save_citation_to_csv, process_citation).
"""
from .abstract_impl import (
    parse_any_citation,
    goto_with_retries,
    save_citation_to_csv,
    process_citation,
)


