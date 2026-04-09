"""
Thin wrapper: re-exports the proceedings automation API from
`automation.proceedings_impl` (parse_any_citation, goto_with_retries,
save_citation_to_csv, process_citation).
"""
try:
    from .proceedings_impl import (
        parse_any_citation,
        goto_with_retries,
        save_citation_to_csv,
        process_citation,
    )
except Exception as e:
    def _missing(*_args, **_kwargs):  # pragma: no cover
        raise RuntimeError("Proceedings automation implementation not available. Please add automation/proceedings_impl.py.")

    parse_any_citation = _missing
    goto_with_retries = _missing
    save_citation_to_csv = _missing
    process_citation = _missing


