from __future__ import annotations

"""Dynamic rule selection: time slots, turn stages, and keyword matching.

P1 implements time_slots + turn_stage. P2 adds keyword matching.
SPEC-006 upgrades keyword matching to expression-vector-based jieba engine.
"""

import re
from datetime import datetime
from pathlib import Path

from expression_vector import _KeywordMatcher, _RELOAD_KEYWORDS

# ---------------------------------------------------------------------------
# Keyword matcher instance (lazy, hot-reloadable)
# ---------------------------------------------------------------------------

_km: _KeywordMatcher | None = None


def _get_keyword_matcher() -> _KeywordMatcher:
    global _km, _RELOAD_KEYWORDS
    keywords_dir = Path(__file__).resolve().parent / "keywords"
    if _km is None or _RELOAD_KEYWORDS:
        _km = _KeywordMatcher(keywords_dir)
        _RELOAD_KEYWORDS = False
    return _km


# ---------------------------------------------------------------------------
# Main selector
# ---------------------------------------------------------------------------


def _select_dynamic_rules(
    dynamic_cfg: dict,
    user_message: str,
    is_first_turn: bool,
    turn_count: int,
    modules: dict | None = None,
) -> list[str]:
    """Select dynamic rules by time / turn-stage / keyword dimensions.

    Injection order (per spec D2): time_slots → turn_stage → keyword.
    Returns list of rule strings for inject_context to concatenate.
    """
    # Normalize modules: if not a dict (e.g. True), treat as all-enabled
    if not isinstance(modules, dict):
        modules = None

    rules: list[str] = []

    # time_slots — modules not passed defaults to enabled
    if modules is None or modules.get("time_slots", True):
        rules.extend(_match_time_slot(dynamic_cfg.get("time_slots", {})))

    # turn_stage — modules not passed defaults to enabled
    if modules is None or modules.get("turn_stage", True):
        rules.extend(
            _match_turn_stage(dynamic_cfg.get("turn_stage", {}), is_first_turn, turn_count)
        )

    # keyword — modules not passed defaults to enabled
    if modules is None or modules.get("keyword", True):
        rules.extend(_match_keyword(dynamic_cfg.get("keywords", {}), user_message))

    return rules


# ---------------------------------------------------------------------------
# Time slots
# ---------------------------------------------------------------------------


def _match_time_slot(time_slots: dict) -> list[str]:
    """Match current time against configured time slots.

    time_slots: {"22:00-05:00": ["rule A", "rule B"], "09:00-17:00": [...]}
    Returns prefixed rule strings like ["🕐 [22:00-05:00] rule A", ...]
    """
    now = datetime.now().strftime("%H:%M")
    matched: list[str] = []
    for slot_range, rules in time_slots.items():
        try:
            start, end = slot_range.split("-", 1)
            start = start.strip()
            end = end.strip()
        except ValueError:
            continue  # skip malformed slot keys
        if _in_time_range(now, start, end):
            for rule in rules:
                matched.append(f"🕐 [{slot_range}] {rule}")
    return matched


def _in_time_range(now: str, start: str, end: str) -> bool:
    """Check if now (HH:MM) falls within [start, end).

    Supports cross-midnight: start="22:00", end="05:00" → now>=22:00 or now<05:00
    """
    if start <= end:
        return start <= now < end
    else:
        # Cross-midnight range
        return now >= start or now < end


# ---------------------------------------------------------------------------
# Turn stages
# ---------------------------------------------------------------------------


def _match_turn_stage(
    turn_stages: dict, is_first_turn: bool, turn_count: int
) -> list[str]:
    """Match turn-based rules against the current conversation stage.

    turn_stages: {"first_turn": [...], "after_10": [...], "after_30": [...]}
    - "first_turn" rules are injected only when is_first_turn is True.
    - "after_N" rules match from highest threshold downward; the first
      threshold where turn_count >= N wins.
    """
    matched: list[str] = []

    # First-turn rules
    if is_first_turn and "first_turn" in turn_stages:
        matched.extend(turn_stages["first_turn"])

    # Collect after_N entries, sorted by N descending
    after_entries: list[tuple[int, list[str]]] = []
    for key, rules in turn_stages.items():
        if not key.startswith("after_"):
            continue
        try:
            n = int(key[len("after_"):])
        except ValueError:
            continue  # skip keys like "after_xyz"
        after_entries.append((n, rules))

    # Match from highest threshold down, first match wins
    after_entries.sort(key=lambda x: x[0], reverse=True)
    for threshold, rules in after_entries:
        if turn_count >= threshold:
            matched.extend(rules)
            break

    return matched


# ---------------------------------------------------------------------------
# Keyword matching (expression-vector powered, SPEC-006)
# ---------------------------------------------------------------------------


def _match_keyword(keywords: dict, user_message: str) -> list[str]:
    """Match user message against expression-vector dimensions.

    SPEC-006: Uses jieba-based expression vector engine with synonym expansion
    and negation detection.  Falls back to regex for legacy pattern keys.

    Args:
        keywords: {"dimension_name": ["rule A"], "legacy_pattern": ["rule B"], ...}
        user_message: The user's current message text.

    Returns:
        Prefixed rule strings like ["💬 [work] rule A", ...].
        Multiple dimensions may match simultaneously (all matches returned).
        Empty message or no match → [].
    """
    if not user_message or not keywords:
        return []

    km = _get_keyword_matcher()
    matched_dims = km.match(user_message) if km._dimensions else []

    rules: list[str] = []
    known_dims = set(km.dimensions.keys()) if km._dimensions else set()

    for key, dim_rules in keywords.items():
        if key in matched_dims:
            # Expression-vector dimension match
            for rule in dim_rules:
                rules.append(f"💬 [{key}] {rule}")
        elif key not in known_dims:
            # Legacy regex fallback for unknown keys
            if re.search(key, user_message):
                for rule in dim_rules:
                    rules.append(f"💬 [{key}] {rule}")

    return rules