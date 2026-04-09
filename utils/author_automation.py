"""
Shared author automation utilities for all asset types.
Provides functions to parse author names and fill them in Esploro forms.
"""
import os
import re
from typing import List, Dict


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[A-Za-z]+", (text or "").lower()) if t]


def _option_match_score(target: Dict[str, str], option_label: str) -> int:
    """
    Score whether a dropdown option matches an author target.
    Higher score = better match, 0 = no match.
    """
    label = _norm(option_label)
    if not label:
        return 0

    if "," in label:
        cand_last, cand_given = [x.strip() for x in label.split(",", 1)]
    else:
        parts = label.split()
        if not parts:
            return 0
        cand_last, cand_given = parts[-1], " ".join(parts[:-1])

    req_last = _norm(target.get("last_name", ""))
    req_initial = (target.get("first_initial", "") or "").upper()

    cand_last_tokens = _tokens(cand_last)
    cand_given_tokens = _tokens(cand_given)
    req_last_tokens = _tokens(req_last)
    if not cand_last_tokens or not req_last_tokens:
        return 0

    # Initial gate: if we know the initial, candidate given name must start with it.
    if req_initial:
        first_given_initial = cand_given_tokens[0][0].upper() if cand_given_tokens else ""
        if first_given_initial != req_initial:
            return 0

    cand_last_norm = " ".join(cand_last_tokens)
    req_last_norm = " ".join(req_last_tokens)

    # Best: exact surname equality + initial check.
    if cand_last_norm == req_last_norm:
        return 100

    # Compound surname variant:
    # requested: "Campos Anchieta", option: "Anchieta, David Campos"
    # accept when candidate surname equals one requested token and remaining requested
    # tokens appear in candidate given names.
    if len(req_last_tokens) > 1:
        if cand_last_tokens == [req_last_tokens[-1]]:
            remaining = req_last_tokens[:-1]
            if all(tok in cand_given_tokens for tok in remaining):
                return 92
        if cand_last_tokens == [req_last_tokens[0]]:
            remaining = req_last_tokens[1:]
            if all(tok in cand_given_tokens for tok in remaining):
                return 90

    # We deliberately reject weak partial matches to avoid wrong selections.
    return 0


def parse_authors_list(authors_string: str) -> List[Dict[str, str]]:
    """
    Parse authors into selection targets with last_name + first_initial.
    
    Examples:
    - "H.W. Wallace" -> "Wallace"
    - "Y.J. Leong" -> "Leong"
    - "D. Anderson" -> "Anderson"
    """
    if not authors_string:
        return []
    
    print(f"[DEBUG] Raw authors: '{authors_string}'")
    
    # Remove "et al.", "and"
    authors_string = re.sub(r'\s*et\s+al\.?\s*$', '', authors_string, flags=re.I)
    authors_string = re.sub(r'\s+&\s+', ', ', authors_string)
    authors_string = re.sub(r'\s+and\s+', ', ', authors_string, flags=re.I)
    authors_string = authors_string.strip(' .,')
    
    # Split by comma
    parts = [p.strip() for p in authors_string.split(',') if p.strip()]
    
    targets: List[Dict[str, str]] = []
    # Preferred pattern: "Last, F." (or "Last, F. M.")
    pairs = re.findall(r"([A-Za-z][A-Za-z' -]+),\s*([A-Z])(?:\s*\.|$)", authors_string)
    if pairs:
        for last_name, first_initial in pairs:
            ln = last_name.strip().strip('.,')
            if ln:
                targets.append({"last_name": ln, "first_initial": first_initial.upper()})
                print(f"[DEBUG] '{ln}' -> '{ln}, {first_initial.upper()}'")
    else:
        # Fallback for non-standard formats: keep last name only.
        for part in parts:
            words = part.split()
            name_words = [w for w in words if not re.match(r'^[A-Z]\.?$', w) and not re.match(r'^[A-Z]\.[A-Z]\.?$', w)]
            if name_words:
                last_name = name_words[-1].strip('.,')
                if last_name and re.match(r'^[A-Z][a-z]', last_name):
                    targets.append({"last_name": last_name, "first_initial": ""})
                    print(f"[DEBUG] '{part}' -> '{last_name}'")
    
    print(f"[DEBUG] Found {len(targets)} names: {[t['last_name'] for t in targets]}")
    return targets


def fill_authors(page, authors_string: str) -> bool:
    """
    Fill the creators/authors field with parsed author last names.
    Returns True if successful, False otherwise.
    
    Args:
        page: Playwright page object
        authors_string: String containing author names (e.g., "Smith, J., & Doe, A.")
    
    Returns:
        True if at least one author was added successfully, False otherwise
    """
    if not authors_string or not authors_string.strip():
        print("… No authors to fill")
        return False
    
    author_targets = parse_authors_list(authors_string)
    if not author_targets:
        print("✗ Could not parse author names")
        return False
    
    print(f"Filling {len(author_targets)} author(s): {', '.join(t['last_name'] for t in author_targets)}")
    
    # Load delay between authors (helps when site lags)
    author_delay_ms = 1000
    try:
        bot_config_path = os.getenv('BOT_CONFIG_PATH', 'bot_config.json')
        if os.path.exists(bot_config_path):
            with open(bot_config_path, 'r', encoding='utf-8') as f:
                import json as json_module
                bot_config = json_module.load(f)
                author_delay_ms = int(bot_config.get('author_add_delay_ms', 1000))
    except Exception:
        pass
    
    try:
        # Click "Add creator" button
        page.get_by_role('button', name=' Add creator').click()
        page.wait_for_timeout(500)
        
        added_count = 0
        for idx, target in enumerate(author_targets):
            last_name = target.get("last_name", "").strip()
            first_initial = target.get("first_initial", "").strip().upper()
            try:
                # Click the textbox
                page.get_by_role('textbox', name='Choose researcher *').click(timeout=3000)
                page.wait_for_timeout(150)
                
                # Clear and fill with last name
                page.get_by_role('textbox', name='Choose researcher *').fill('')
                page.get_by_role('textbox', name='Choose researcher *').fill(last_name)
                page.wait_for_timeout(800)  # Wait for dropdown
                
                # Score visible options to choose the best robust match.
                try:
                    target = {"last_name": last_name, "first_initial": first_initial}
                    selected_label = ""
                    selected = False

                    # Stage 1 (legacy-first): direct text match by "Last, Initial"
                    if first_initial:
                        fast_pat = re.compile(
                            rf"^{re.escape(last_name)}\s*,\s*{re.escape(first_initial)}",
                            flags=re.I
                        )
                        try:
                            fast = page.get_by_text(fast_pat).first
                            selected_label = fast.inner_text().strip()
                            fast.click(timeout=1200)
                            selected = True
                            print(f"    [author-match] fast: {selected_label}")
                        except Exception:
                            selected = False

                    # Stage 2 fallback: robust scored option matching
                    if not selected:
                        options = page.get_by_role('option')
                        best_idx = -1
                        best_score = 0
                        best_label = ""
                        try:
                            count = min(options.count(), 30)
                        except Exception:
                            count = 0
                        for oi in range(count):
                            try:
                                label = options.nth(oi).inner_text().strip()
                            except Exception:
                                continue
                            score = _option_match_score(target, label)
                            if score > best_score:
                                best_score = score
                                best_idx = oi
                                best_label = label

                        if best_idx >= 0 and best_score >= 90:
                            options.nth(best_idx).click(timeout=1500)
                            selected = True
                            selected_label = best_label
                            print(f"    [author-match] fallback(score={best_score}): {selected_label}")

                    if not selected:
                        shown = f"{last_name}, {first_initial}" if first_initial else last_name
                        print(f"  ✗ {idx + 1}/{len(author_targets)}: {shown} (no robust match found)")
                        try:
                            page.get_by_role('textbox', name='Choose researcher *').fill('')
                        except Exception:
                            pass
                        continue

                    page.wait_for_timeout(150)
                    
                    # Click "Add" button
                    page.get_by_role('button', name='Add', exact=True).click(timeout=2000)
                    # Delay between authors (configurable via author_add_delay_ms in bot_config.json)
                    page.wait_for_timeout(author_delay_ms)
                    
                    added_count += 1
                    shown = f"{last_name}, {first_initial}" if first_initial else last_name
                    print(f"  ✓ {idx + 1}/{len(author_targets)}: {shown}")
                    
                except Exception:
                    shown = f"{last_name}, {first_initial}" if first_initial else last_name
                    print(f"  ✗ {idx + 1}/{len(author_targets)}: {shown} (not found)")
                    # Clear field and continue
                    try:
                        page.get_by_role('textbox', name='Choose researcher *').fill('')
                    except Exception:
                        pass
                
            except Exception as e:
                shown = f"{last_name}, {first_initial}" if first_initial else last_name
                print(f"  ✗ Error with {shown}: {e}")
                continue
        
        # Click "Add and close"
        try:
            page.get_by_role('button', name='Add and close').click(timeout=3000)
            page.wait_for_timeout(300)
        except Exception as e:
            print(f"⚠️  Could not click 'Add and close': {e}")
        
        print(f"✓ Added {added_count}/{len(author_targets)} author(s)")
        return added_count > 0
        
    except Exception as e:
        print(f"✗ Error filling authors: {e}")
        return False


def should_fill_authors() -> bool:
    """
    Check if author automation is enabled in bot config.
    Returns True if enabled (or config not found - backward compatibility), False otherwise.
    """
    try:
        bot_config_path = os.getenv('BOT_CONFIG_PATH', 'bot_config.json')
        if os.path.exists(bot_config_path):
            with open(bot_config_path, 'r', encoding='utf-8') as f:
                import json as json_module
                bot_config = json_module.load(f)
                return bot_config.get('auto_fill_authors', True)
    except Exception:
        pass  # If config can't be read, default to True
    
    return True  # Default to True for backward compatibility


def fill_authors_if_enabled(page, citation_data: dict) -> None:
    """
    Convenience function that checks config and fills authors if enabled.
    
    Args:
        page: Playwright page object
        citation_data: Dictionary containing citation data with 'authors' field
    """
    try:
        if should_fill_authors():
            authors = citation_data.get('authors', '').strip()
            if authors:
                fill_authors(page, authors)
            else:
                print("… No authors found in citation data")
        else:
            print("… Author automation disabled (skip filling)")
    except Exception as e:
        print(f"⚠️  Authors fill error: {e}")
