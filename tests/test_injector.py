"""P1 tests for hermes_persona.injector — config loading, time context,
static rules, and inject_context assembly."""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

import hermes_persona.injector as injector
from hermes_persona.injector import (
    _inject_static_rules,
    _load_config,
    _time_context,
    inject_context,
)


# ── _load_config ───────────────────────────────────────────────────────


class TestLoadConfig:
    def test_empty_config(self, temp_config_root, write_config):
        """_load_config() returns {} for empty hermes-persona key."""
        write_config({"hermes-persona": {}})
        assert _load_config() == {}

    def test_config_not_found(self, temp_config_root):
        """_load_config() returns {} when config file does not exist."""
        # temp_config_root has no persona-config.json → should degrade
        assert _load_config() == {}

    def test_malformed_json(self, temp_config_root):
        """_load_config() returns {} when JSON is malformed."""
        config_path = temp_config_root / "persona-config.json"
        config_path.write_text("this is not json", encoding="utf-8")
        assert _load_config() == {}

    def test_only_hermes_persona_key(self, temp_config_root, write_config):
        """_load_config() ignores unknown top-level keys."""
        write_config({"hermes-persona": {"time": {"enabled": True}}, "other-plugin": {"foo": 1}})
        result = _load_config()
        assert result == {"time": {"enabled": True}}
        assert "other-plugin" not in result


# ── _time_context ──────────────────────────────────────────────────────


class TestTimeContext:
    def test_cn_full_format(self):
        """cn_full produces Chinese year-month-day weekday time string."""
        result = _time_context("cn_full")
        assert result.startswith("🕐 ")
        assert "年" in result
        assert "月" in result
        assert "日" in result
        assert "周" in result
        assert ":" in result

    @patch("hermes_persona.injector.datetime")
    def test_iso_format(self, mock_dt):
        """iso format produces ISO8601 string."""
        mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
        result = _time_context("iso")
        assert result == "🕐 2026-05-16T14:30:00"

    @patch("hermes_persona.injector.datetime")
    def test_compact_format(self, mock_dt):
        """compact format produces MM/DD HH:MM string."""
        mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
        result = _time_context("compact")
        assert result == "🕐 05/16 14:30"

    @patch("hermes_persona.injector.datetime")
    def test_unknown_format_falls_back(self, mock_dt):
        """Unknown format falls back to cn_full."""
        mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
        result = _time_context("nonexistent_format")
        assert "年" in result
        assert "月" in result


# ── _inject_static_rules ───────────────────────────────────────────────


class TestStaticRules:
    def test_rules_every_turn(self):
        """context.rules are injected regardless of turn count."""
        ctx_cfg = {"rules": ["规则1", "规则2"]}
        result = _inject_static_rules(ctx_cfg, is_first_turn=False)
        assert result == ["规则1", "规则2"]

    def test_rules_first_turn_only_when_first(self):
        """rules_first_turn_only injected when is_first_turn=True."""
        ctx_cfg = {"rules_first_turn_only": ["仅首轮规则"]}
        result = _inject_static_rules(ctx_cfg, is_first_turn=True)
        assert "仅首轮规则" in result

    def test_rules_first_turn_only_skipped_after_first(self):
        """rules_first_turn_only NOT injected when is_first_turn=False."""
        ctx_cfg = {"rules": ["通用规则"], "rules_first_turn_only": ["仅首轮规则"]}
        result = _inject_static_rules(ctx_cfg, is_first_turn=False)
        assert result == ["通用规则"]
        assert "仅首轮规则" not in result

    def test_empty_context(self):
        """Empty context config returns empty list."""
        assert _inject_static_rules({}, is_first_turn=True) == []


# ── inject_context integration ─────────────────────────────────────────


class TestInjectContext:
    @patch("hermes_persona.injector._load_config", return_value={})
    def test_empty_config_returns_time_context(self, _mock_load, inject_context_defaults):
        """With empty config {}, inject_context returns at least time context."""
        result = inject_context(**inject_context_defaults)
        assert result is not None
        assert "context" in result
        assert "🕐" in result["context"]

    @patch("hermes_persona.injector._load_config", return_value={})
    def test_time_disabled(self, _mock_load, inject_context_defaults):
        """When time.enabled is False, no time line in output."""
        _mock_load.return_value = {"time": {"enabled": False}}
        result = inject_context(**inject_context_defaults)
        # With time disabled and no other rules, parts may be empty → None
        if result is not None:
            assert "🕐" not in result["context"]

    @patch("hermes_persona.injector._load_config")
    def test_static_rules_appear_every_turn(self, mock_load, inject_context_defaults):
        """Static rules from context.rules appear in every turn."""
        mock_load.return_value = {
            "context": {"rules": ["你是助手"]},
        }
        inject_context_defaults["is_first_turn"] = False
        result = inject_context(**inject_context_defaults)
        assert result is not None
        assert "你是助手" in result["context"]

    @patch("hermes_persona.injector._load_config")
    def test_rules_first_turn_only_first_turn(self, mock_load, inject_context_defaults):
        """First-turn-only rules appear on the first turn."""
        mock_load.return_value = {
            "context": {"rules_first_turn_only": ["欢迎新用户"]},
        }
        inject_context_defaults["is_first_turn"] = True
        result = inject_context(**inject_context_defaults)
        assert result is not None
        assert "欢迎新用户" in result["context"]

    @patch("hermes_persona.injector._load_config")
    def test_rules_first_turn_only_not_second_turn(self, mock_load, inject_context_defaults):
        """First-turn-only rules do NOT appear on later turns."""
        mock_load.return_value = {
            "context": {"rules_first_turn_only": ["欢迎新用户"]},
        }
        inject_context_defaults["is_first_turn"] = False
        result = inject_context(**inject_context_defaults)
        # May still have time context, but should not have the first-turn rules
        if result is not None:
            assert "欢迎新用户" not in result["context"]

    def test_history_none_no_crash(self, inject_context_defaults):
        """conversation_history=None should not crash."""
        inject_context_defaults["conversation_history"] = None
        inject_context_defaults["is_first_turn"] = True
        with patch("hermes_persona.injector._load_config", return_value={}):
            result = inject_context(**inject_context_defaults)
        assert result is not None  # at least time context

    def test_history_empty_no_crash(self, inject_context_defaults):
        """conversation_history=[] should not crash."""
        inject_context_defaults["conversation_history"] = []
        with patch("hermes_persona.injector._load_config", return_value={}):
            result = inject_context(**inject_context_defaults)
        assert result is not None

    @patch("hermes_persona.injector._load_config")
    def test_no_parts_returns_none(self, mock_load, inject_context_defaults):
        """When all config is disabled, inject_context returns None."""
        mock_load.return_value = {
            "time": {"enabled": False},
        }
        inject_context_defaults["is_first_turn"] = False
        result = inject_context(**inject_context_defaults)
        assert result is None

    @patch("hermes_persona.injector._load_config")
    def test_exception_does_not_propagate(self, mock_load, inject_context_defaults):
        """Any exception inside inject_context returns None, not an unhandled error."""
        mock_load.side_effect = RuntimeError("simulated failure")
        result = inject_context(**inject_context_defaults)
        assert result is None


# ── Code audit: no role-specific content ────────────────────────────────


class TestCodeGeneric:
    """Ensure code contains no role-specific / character-specific content."""

    ROLE_TERMS = [
        "知惠", "Zhihui", "zhihui",
        "兽娘", "兽耳", "女仆",
        "阿格莱雅", "Aglaea", "aglaea",
        "克莱茵", "Klein", "klein",
        "托帕", "Topaz", "topaz",
    ]

    @pytest.mark.parametrize("term", ROLE_TERMS)
    def test_no_character_name_in_source(self, term):
        """Source files in hermes_persona/ must not contain role-specific strings."""
        import glob
        from pathlib import Path

        py_files = glob.glob("hermes_persona/**/*.py", recursive=True)
        for py_file in py_files:
            content = Path(py_file).read_text(encoding="utf-8")
            assert term not in content, (
                f"Found role-specific term '{term}' in {py_file}"
            )
