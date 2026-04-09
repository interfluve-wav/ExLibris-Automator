"""
Thin wrapper: re-exports the technical documentation automation API from
`automation.technical_documentation_impl` (parse_any_citation, goto_with_retries,
save_citation_to_csv, process_citation).
"""
from .technical_documentation_impl import (
    parse_any_citation,
    goto_with_retries,
    save_citation_to_csv,
    process_citation,
)
