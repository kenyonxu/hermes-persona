"""Dynamic rule selection: time slots, turn stages, and keyword matching.

P1 implements time_slots + turn_stage. Keyword matching is a stub for P2.
"""

from datetime import datetime


def _select_dynamic_rules(
    dynamic_cfg: dict,
    user_message: str,
    is_first_turn: bool,
    turn_count: int,
) -> list[str]:
    """Select dynamic rules by time / turn-stage / keyword dimensions.

    P1: time_slots + turn_stage. P2 adds keyword.
    Returns list of rule strings for inject_context to concatenate.
    """
    rules: list[str] = []
    rules.extend(_match_time_slot(dynamic_cfg.get("time_slots", {})))
    rules.extend(
        _match_turn_stage(dynamic_cfg.get("turn_stage", {}), is_first_turn, turn_count)
    )
    # rules.extend(_match_keyword(...))  # P2
    return rules


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


def _match_keyword(keywords: dict, user_message: str) -> list[str]:
    """P2 stub. Match keywords in user message against configured patterns.

    Currently returns [] — full implementation deferred to P2-T1.
    """
    return []
