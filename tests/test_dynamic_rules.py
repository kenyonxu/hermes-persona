"""P1 tests for hermes_persona.dynamic_rules — time slots, turn stages,
in-time-range logic, and dynamic rule selection."""

from unittest.mock import patch

import pytest

from hermes_persona.dynamic_rules import (
    _in_time_range,
    _match_keyword,
    _match_time_slot,
    _match_turn_stage,
    _select_dynamic_rules,
)


# ── _in_time_range ─────────────────────────────────────────────────────


class TestInTimeRange:
    def test_normal_range_inside(self):
        """10:00 is inside [09:00, 17:00)."""
        assert _in_time_range("10:00", "09:00", "17:00") is True

    def test_normal_range_at_start(self):
        """09:00 is inside [09:00, 17:00) — inclusive lower bound."""
        assert _in_time_range("09:00", "09:00", "17:00") is True

    def test_normal_range_at_end(self):
        """17:00 is NOT inside [09:00, 17:00) — exclusive upper bound."""
        assert _in_time_range("17:00", "09:00", "17:00") is False

    def test_normal_range_outside(self):
        """18:00 is outside [09:00, 17:00)."""
        assert _in_time_range("18:00", "09:00", "17:00") is False

    def test_cross_midnight_inside_night(self):
        """02:00 is inside [22:00, 05:00) — cross-midnight."""
        assert _in_time_range("02:00", "22:00", "05:00") is True

    def test_cross_midnight_inside_evening(self):
        """23:30 is inside [22:00, 05:00) — cross-midnight."""
        assert _in_time_range("23:30", "22:00", "05:00") is True

    def test_cross_midnight_outside(self):
        """12:00 is outside [22:00, 05:00) — cross-midnight."""
        assert _in_time_range("12:00", "22:00", "05:00") is False

    def test_cross_midnight_at_start(self):
        """22:00 is inside [22:00, 05:00) — inclusive lower bound."""
        assert _in_time_range("22:00", "22:00", "05:00") is True


# ── _match_time_slot ───────────────────────────────────────────────────


class TestMatchTimeSlot:
    @patch("hermes_persona.dynamic_rules.datetime")
    def test_normal_slot_match(self, mock_dt):
        """09:00-17:00 slot matches at 14:30."""
        from datetime import datetime

        mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
        slots = {"09:00-17:00": ["工作时间规则"]}
        result = _match_time_slot(slots)
        assert len(result) == 1
        assert "[09:00-17:00]" in result[0]
        assert "工作时间规则" in result[0]

    @patch("hermes_persona.dynamic_rules.datetime")
    def test_cross_midnight_match_at_night(self, mock_dt):
        """22:00-05:00 slot matches at 02:30 (cross-midnight)."""
        from datetime import datetime

        mock_dt.now.return_value = datetime(2026, 5, 16, 2, 30, 0)
        slots = {"22:00-05:00": ["深夜模式"]}
        result = _match_time_slot(slots)
        assert len(result) == 1
        assert "[22:00-05:00]" in result[0]
        assert "深夜模式" in result[0]

    @patch("hermes_persona.dynamic_rules.datetime")
    def test_cross_midnight_match_at_edge(self, mock_dt):
        """22:00-05:00 slot matches at 22:00 (edge)."""
        from datetime import datetime

        mock_dt.now.return_value = datetime(2026, 5, 16, 22, 0, 0)
        slots = {"22:00-05:00": ["深夜启动"]}
        result = _match_time_slot(slots)
        assert len(result) == 1

    @patch("hermes_persona.dynamic_rules.datetime")
    def test_no_match(self, mock_dt):
        """Returns [] when current time is not in any slot."""
        from datetime import datetime

        mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
        slots = {"22:00-05:00": ["深夜模式"]}
        result = _match_time_slot(slots)
        assert result == []

    def test_invalid_slot_key_skipped(self):
        """A malformed slot key is skipped silently."""
        with patch("hermes_persona.dynamic_rules.datetime") as mock_dt:
            from datetime import datetime

            mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
            # "bad-format" cannot be split into start/end with one dash (it has one dash but "bad" is not HH:MM)
            # Actually "bad-format" splits into "bad" and "format" → both pass as strings, so this test
            # is about a truly invalid format. Let's use something with no dash.
            slots = {"no_dash": ["规则"]}  # missing dash → ValueError on split
            result = _match_time_slot(slots)
            assert result == []


# ── _match_turn_stage ──────────────────────────────────────────────────


class TestMatchTurnStage:
    def test_first_turn_injected(self):
        """first_turn rules are injected when is_first_turn=True."""
        stages = {"first_turn": ["首次问候"]}
        result = _match_turn_stage(stages, is_first_turn=True, turn_count=0)
        assert result == ["首次问候"]

    def test_first_turn_not_injected_when_false(self):
        """first_turn rules are NOT injected when is_first_turn=False."""
        stages = {"first_turn": ["首次问候"]}
        result = _match_turn_stage(stages, is_first_turn=False, turn_count=0)
        assert result == []

    def test_after_30_matches_at_35(self):
        """At turn_count=35, after_30 matches, not after_10."""
        stages = {
            "after_10": ["中期规则"],
            "after_30": ["后期规则"],
        }
        result = _match_turn_stage(stages, is_first_turn=False, turn_count=35)
        assert result == ["后期规则"]

    def test_after_10_matches_at_12(self):
        """At turn_count=12, after_10 matches."""
        stages = {
            "after_10": ["中期规则"],
            "after_30": ["后期规则"],
        }
        result = _match_turn_stage(stages, is_first_turn=False, turn_count=12)
        assert result == ["中期规则"]

    def test_after_10_matches_at_exactly_10(self):
        """At turn_count=10, after_10 matches (turn_count >= threshold)."""
        stages = {"after_10": ["满10轮规则"]}
        result = _match_turn_stage(stages, is_first_turn=False, turn_count=10)
        assert result == ["满10轮规则"]

    def test_no_match_below_threshold(self):
        """At turn_count=5 with only after_10, nothing matches."""
        stages = {"after_10": ["中期规则"]}
        result = _match_turn_stage(stages, is_first_turn=False, turn_count=5)
        assert result == []

    def test_invalid_after_key_skipped(self):
        """after_xyz is not a valid integer → skipped."""
        stages = {"after_xyz": ["无效规则"], "after_10": ["中期规则"]}
        result = _match_turn_stage(stages, is_first_turn=False, turn_count=12)
        assert result == ["中期规则"]

    def test_highest_threshold_wins(self):
        """When multiple after_N match, the highest N wins."""
        stages = {
            "after_5": ["5轮规则"],
            "after_10": ["10轮规则"],
            "after_20": ["20轮规则"],
        }
        result = _match_turn_stage(stages, is_first_turn=False, turn_count=100)
        assert result == ["20轮规则"]  # highest threshold wins


# ── _select_dynamic_rules ──────────────────────────────────────────────


class TestSelectDynamicRules:
    def test_empty_config_returns_empty(self):
        """Empty dynamic config returns []."""
        result = _select_dynamic_rules({}, "hello", False, 0)
        assert result == []

    @patch("hermes_persona.dynamic_rules.datetime")
    def test_selects_time_slot_and_turn_stage(self, mock_dt):
        """Combines time slot and turn stage rules."""
        from datetime import datetime

        mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
        dynamic_cfg = {
            "time_slots": {"09:00-17:00": ["工作时间"]},
            "turn_stage": {"after_10": ["后期对话"]},
        }
        result = _select_dynamic_rules(dynamic_cfg, "hello", False, 15)
        assert len(result) == 2
        assert any("工作时间" in r for r in result)
        assert any("后期对话" in r for r in result)

    @patch("hermes_persona.dynamic_rules.datetime")
    def test_first_turn_in_select(self, mock_dt):
        """First turn rules are injected via _select_dynamic_rules."""
        from datetime import datetime

        mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
        dynamic_cfg = {
            "turn_stage": {"first_turn": ["首次欢迎"]},
        }
        result = _select_dynamic_rules(dynamic_cfg, "hello", is_first_turn=True, turn_count=0)
        assert any("首次欢迎" in r for r in result)


# ── _match_keyword (P2) ─────────────────────────────────────────────────


class TestMatchKeyword:
    def test_keyword_match(self):
        """Message containing pattern returns matching rules."""
        keywords = {"bug": ["检测到Bug，请检查"]}
        result = _match_keyword(keywords, "系统出了个bug炸了")
        assert result == ["💬 [bug] 检测到Bug，请检查"]

    def test_keyword_first_match_wins(self):
        """When two patterns both match, only the first is returned."""
        keywords = {
            "bug": ["规则A"],
            "error": ["规则B"],
        }
        result = _match_keyword(keywords, "there is a bug and an error")
        assert result == ["💬 [bug] 规则A"]

    def test_keyword_empty_message(self):
        """Empty user_message returns []."""
        keywords = {"bug": ["规则"]}
        result = _match_keyword(keywords, "")
        assert result == []

    def test_keyword_no_match(self):
        """No pattern matches → returns []."""
        keywords = {"bug": ["规则"]}
        result = _match_keyword(keywords, "一切正常")
        assert result == []

    def test_keyword_regex_search(self):
        """re.search is used, so substring matching works."""
        keywords = {"坏了": ["故障规则"]}
        # "坏了" is a substring of "系统坏了" → match
        result = _match_keyword(keywords, "系统坏了")
        assert result == ["💬 [坏了] 故障规则"]

    def test_keyword_regex_special_chars(self):
        """Regex special characters in pattern work correctly."""
        keywords = {r"\bbug\b": ["单词匹配Bug"]}
        # "bug" as a whole word
        result = _match_keyword(keywords, "there is a bug here")
        assert result == ["💬 [\\bbug\\b] 单词匹配Bug"]
        # "debug" contains "bug" but not as a whole word
        result2 = _match_keyword(keywords, "let us debug this")
        assert result2 == []

    def test_keyword_pattern_order(self):
        """Config insertion order determines match priority."""
        keywords = {
            "first": ["第一规则"],
            "second": ["第二规则"],
        }
        # Both match, but "first" comes first
        result = _match_keyword(keywords, "first second")
        assert result == ["💬 [first] 第一规则"]

    def test_keyword_multiple_rules_per_pattern(self):
        """A single pattern can have multiple rules."""
        keywords = {"bug": ["规则1", "规则2"]}
        result = _match_keyword(keywords, "发现一个bug")
        assert len(result) == 2
        assert "💬 [bug] 规则1" in result
        assert "💬 [bug] 规则2" in result

    def test_keyword_in_select_dynamic_rules(self):
        """Keyword matching is wired into _select_dynamic_rules."""
        from datetime import datetime

        with patch("hermes_persona.dynamic_rules.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
            dynamic_cfg = {
                "keywords": {"bug": ["检测到Bug"]},
            }
            result = _select_dynamic_rules(dynamic_cfg, "there is a bug", False, 0)
            assert any("检测到Bug" in r for r in result)

    def test_keyword_empty_keywords_config(self):
        """Empty keywords config → no keyword rules."""
        result = _match_keyword({}, "hello world")
        assert result == []
