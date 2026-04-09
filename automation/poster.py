"""
Thin wrapper: re-exports the conference poster automation API from
`automation.poster_impl` (parse_any_citation, goto_with_retries,
save_citation_to_csv, process_citation).
"""
try:
    from .poster_impl import (
        parse_any_citation,
        goto_with_retries,
        save_citation_to_csv,
        process_citation,
    )
except Exception as e:
    def _missing(*_args, **_kwargs):  # pragma: no cover
        raise RuntimeError("Conference Poster automation implementation not available. Please add automation/poster_impl.py.")

    parse_any_citation = _missing
    goto_with_retries = _missing
    save_citation_to_csv = _missing
    process_citation = _missing


