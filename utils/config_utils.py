import os
import json
import re
from typing import Dict, Tuple, List

_CONFIG_CACHE: Dict[str, Dict] = {}


def _default_config_path() -> str:
    # Default to repo root citations_config.json
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, '..', 'citations_config.json'))


def load_citations_config() -> Dict:
    path = os.getenv('CITATIONS_CONFIG_PATH', _default_config_path()).strip()
    try:
        mtime_key = f"{path}::mtime"
        current_mtime = os.path.getmtime(path)
        cached = _CONFIG_CACHE.get(path)
        cached_mtime = _CONFIG_CACHE.get(mtime_key)
        if cached is not None and cached_mtime == current_mtime:
            return cached
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _CONFIG_CACHE[path] = data
        _CONFIG_CACHE[mtime_key] = current_mtime
        return data
    except Exception:
        # Safe defaults
        return {
            'ordinal_words': {},
            'tens_bases': {},
            'tens_ordinals': {},
            'number_overrides': [],
            'conference_name_strips': []
        }


def extract_ordinal_word_number(conference_name: str) -> Tuple[str, str]:
    """Return (number_str or '', cleaned_name). If no number, returns ('', original_or_cleaned).

    - Uses built-in English ordinals plus config-driven extensions.
    - Applies number_overrides first.
    - Removes the matched ordinal token from the returned conference name.
    - Applies conference_name_strips regexes at the end.
    """
    name = (conference_name or '').strip()
    if not name:
        return '', name

    cfg = load_citations_config() or {}
    units = {
        'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
        'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10,
        'eleventh': 11, 'twelfth': 12, 'thirteenth': 13, 'fourteenth': 14,
        'fifteenth': 15, 'sixteenth': 16, 'seventeenth': 17, 'eighteenth': 18,
        'nineteenth': 19,
    }
    tens_ordinal = {
        'twentieth': 20, 'thirtieth': 30, 'fortieth': 40, 'fiftieth': 50,
        'sixtieth': 60, 'seventieth': 70, 'eightieth': 80, 'ninetieth': 90,
    }
    tens_base = {
        'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
        'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90,
    }

    # Merge config extensions
    try:
        for k, v in (cfg.get('ordinal_words') or {}).items():
            if isinstance(k, str) and isinstance(v, int):
                units[k.lower()] = v
        for k, v in (cfg.get('tens_bases') or {}).items():
            if isinstance(k, str) and isinstance(v, int):
                tens_base[k.lower()] = v
        for k, v in (cfg.get('tens_ordinals') or {}).items():
            if isinstance(k, str) and isinstance(v, int):
                tens_ordinal[k.lower()] = v
    except Exception:
        pass

    # 1) Overrides
    try:
        for rule in (cfg.get('number_overrides') or []):
            pattern = (rule.get('pattern') or '').strip()
            number = str(rule.get('number') or '').strip()
            strip_match = bool(rule.get('strip_match_from_name', True))
            if not pattern or not number:
                continue
            m = re.search(pattern, name, flags=re.I)
            if m:
                cleaned = name
                if strip_match:
                    cleaned = (name[:m.start()] + name[m.end():]).strip()
                cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(' ,')
                # Apply generic post-strips
                for rx in (cfg.get('conference_name_strips') or []):
                    try:
                        cleaned = re.sub(rx, ' ', cleaned)
                    except Exception:
                        pass
                cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(' ,')
                return number, cleaned
    except Exception:
        pass

    # 2) Compound base + unit (twenty first / twenty-first)
    try:
        base_re = "|".join(map(re.escape, tens_base.keys()))
        units_re = "|".join(map(re.escape, units.keys()))
        m_comp = re.search(rf"\b({base_re})[\-\s]+({units_re})\b", name, flags=re.I)
        if m_comp:
            num = tens_base[m_comp.group(1).lower()] + units[m_comp.group(2).lower()]
            cleaned = (name[:m_comp.start()] + name[m_comp.end():]).strip()
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(' ,')
            for rx in (cfg.get('conference_name_strips') or []):
                try:
                    cleaned = re.sub(rx, ' ', cleaned)
                except Exception:
                    pass
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(' ,')
            return str(num), cleaned
    except Exception:
        pass

    # 3) Tens ordinals (thirtieth)
    try:
        tens_re = "|".join(map(re.escape, tens_ordinal.keys()))
        m_tens = re.search(rf"\b({tens_re})\b", name, flags=re.I)
        if m_tens:
            num = tens_ordinal[m_tens.group(1).lower()]
            cleaned = (name[:m_tens.start()] + name[m_tens.end():]).strip()
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(' ,')
            for rx in (cfg.get('conference_name_strips') or []):
                try:
                    cleaned = re.sub(rx, ' ', cleaned)
                except Exception:
                    pass
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(' ,')
            return str(num), cleaned
    except Exception:
        pass

    # 4) Unit ordinals (eighth)
    try:
        unit_re = "|".join(map(re.escape, units.keys()))
        m_unit = re.search(rf"\b({unit_re})\b", name, flags=re.I)
        if m_unit:
            num = units[m_unit.group(1).lower()]
            cleaned = (name[:m_unit.start()] + name[m_unit.end():]).strip()
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(' ,')
            for rx in (cfg.get('conference_name_strips') or []):
                try:
                    cleaned = re.sub(rx, ' ', cleaned)
                except Exception:
                    pass
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(' ,')
            return str(num), cleaned
    except Exception:
        pass

    # Nothing found; still apply cleanup patterns
    cleaned = name
    for rx in (cfg.get('conference_name_strips') or []):
        try:
            cleaned = re.sub(rx, ' ', cleaned)
        except Exception:
            pass
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(' ,')
    return '', cleaned


def load_bot_config(path: str = None) -> Dict:
    # Allow env override for shared config across different launch paths
    if not path or not isinstance(path, str) or not path.strip():
        path = os.getenv('BOT_CONFIG_PATH', 'bot_config.json')
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def get_additional_topics_for_channel(channel_id: str) -> List[str]:
    """Return up to 6 configured additional topics for the given Discord channel."""
    cfg = load_bot_config()
    topics_by_channel = (cfg.get("additional_topics") or {})
    topics = topics_by_channel.get(str(channel_id)) or []
    # Normalize and clamp
    clean = []
    for t in topics:
        s = (t or "").strip()
        if s and s not in clean:
            clean.append(s)
        if len(clean) >= 6:
            break
    return clean
