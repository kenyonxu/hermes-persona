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
    _recall_memories,
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


# ── _recall_memories (P2) ────────────────────────────────────────────────


class TestMemoryRecall:
    def test_memory_disabled(self):
        """memory.enabled=false → returns None."""
        result = _recall_memories("hello", {"enabled": False})
        assert result is None

    def test_memory_no_api_url(self):
        """enabled=True but no api_url → returns None."""
        result = _recall_memories("hello", {"enabled": True})
        assert result is None

    def test_memory_recall_integration(self):
        """memory.enabled=true + valid api_url → injects memory content."""
        import httpx
        from unittest import mock

        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": ["记忆片段1", "记忆片段2"]}

        with mock.patch.object(httpx, "post", return_value=mock_response):
            result = _recall_memories("hello", {
                "enabled": True,
                "api_url": "http://example.com/memory",
            })
        assert result is not None
        assert "📝 相关记忆:" in result
        assert "- 记忆片段1" in result
        assert "- 记忆片段2" in result

    def test_memory_content_truncation(self):
        """Results longer than 120 chars are truncated."""
        import httpx
        from unittest import mock

        long_text = "A" * 200
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [long_text]}

        with mock.patch.object(httpx, "post", return_value=mock_response):
            result = _recall_memories("hello", {
                "enabled": True,
                "api_url": "http://example.com/memory",
            })
        assert result is not None
        # Verify truncation: "- AAAA...120 chars"
        truncated = "A" * 120
        assert f"- {truncated}" in result
        # The original 200-char string must NOT appear in full
        assert long_text not in result

    def test_memory_api_error(self):
        """Non-200 status code → returns None."""
        import httpx
        from unittest import mock

        mock_response = mock.Mock()
        mock_response.status_code = 500

        with mock.patch.object(httpx, "post", return_value=mock_response):
            result = _recall_memories("hello", {
                "enabled": True,
                "api_url": "http://example.com/memory",
            })
        assert result is None

    def test_memory_empty_results(self):
        """Empty results list → returns None."""
        import httpx
        from unittest import mock

        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        with mock.patch.object(httpx, "post", return_value=mock_response):
            result = _recall_memories("hello", {
                "enabled": True,
                "api_url": "http://example.com/memory",
            })
        assert result is None

    def test_memory_no_httpx(self):
        """httpx not installed → returns None (graceful degradation)."""
        import builtins

        _original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "httpx":
                raise ImportError(f"No module named '{name}'")
            return _original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=_mock_import):
            result = _recall_memories("hello", {
                "enabled": True,
                "api_url": "http://example.com/memory",
            })
        assert result is None

    def test_memory_network_timeout(self):
        """Network timeout exception → returns None."""
        import httpx
        from unittest import mock

        import httpx as httpx_mod

        # httpx.TimeoutException may not exist in all versions; use a generic Exception
        with mock.patch.object(httpx_mod, "post", side_effect=Exception("timeout")):
            result = _recall_memories("hello", {
                "enabled": True,
                "api_url": "http://example.com/memory",
            })
        assert result is None


# ── inject_context P2 integration ────────────────────────────────────────


class TestInjectContextP2:
    @patch("hermes_persona.injector._load_config")
    def test_keyword_injection_in_context(self, mock_load, inject_context_defaults):
        """Keyword matching injects rules into the full context."""
        mock_load.return_value = {
            "dynamic": {"keywords": {"bug": ["检测到异常"]}},
        }
        inject_context_defaults["user_message"] = "发现了一个bug"
        result = inject_context(**inject_context_defaults)
        assert result is not None
        assert "检测到异常" in result["context"]

    @patch("hermes_persona.injector._load_config")
    @patch("hermes_persona.injector._recall_memories")
    def test_memory_injection_in_context(self, mock_recall, mock_load, inject_context_defaults):
        """Memory recall result is injected into the full context."""
        mock_load.return_value = {
            "memory": {"enabled": True, "api_url": "http://example.com"},
        }
        mock_recall.return_value = "📝 相关记忆:\n- 历史片段"
        result = inject_context(**inject_context_defaults)
        assert result is not None
        assert "历史片段" in result["context"]

    @patch("hermes_persona.injector._load_config")
    @patch("hermes_persona.injector._recall_memories")
    def test_memory_none_not_injected(self, mock_recall, mock_load, inject_context_defaults):
        """When memory recall returns None, it is not appended."""
        mock_load.return_value = {
            "memory": {"enabled": True, "api_url": "http://example.com"},
        }
        mock_recall.return_value = None
        result = inject_context(**inject_context_defaults)
        # Result may still have time context
        if result is not None:
            assert "📝 相关记忆" not in result["context"]


# ── _read_kanban (P3) ──────────────────────────────────────────────────


class TestKanbanDirect:
    """Unit tests for _read_kanban() called directly."""

    def test_path_not_found(self, tmp_path):
        """Non-existent kanban_path → returns None, no exception."""
        bad_path = str(tmp_path / "does_not_exist")
        result = injector._read_kanban(bad_path, "")
        assert result is None

    def test_empty_string_path(self):
        """Empty kanban_path → returns None."""
        result = injector._read_kanban("", "")
        assert result is None

    def test_empty_dir(self, tmp_path):
        """Directory exists but contains no *.md files → returns None."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        result = injector._read_kanban(str(kanban_dir), "")
        assert result is None

    def test_priority_extraction(self, tmp_path):
        """Correctly extracts the first line containing '优先级:'."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        (kanban_dir / "task1.md").write_text("优先级: 高 - 修复登录页面\n详情略", encoding="utf-8")
        (kanban_dir / "task2.md").write_text("优先级: 中 - 重构API\n详情略", encoding="utf-8")

        result = injector._read_kanban(str(kanban_dir), "")
        assert result is not None
        assert "task1" in result
        assert "优先级: 高 - 修复登录页面" in result
        assert "task2" in result
        assert "优先级: 中 - 重构API" in result

    def test_no_priority_line(self, tmp_path):
        """Files without '优先级:' in the first line are skipped."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        (kanban_dir / "notes.md").write_text("Just some notes\nNo priority here", encoding="utf-8")

        result = injector._read_kanban(str(kanban_dir), "")
        assert result is None

    def test_max_five(self, tmp_path):
        """More than 5 markdown files → only the first 5 (sorted) are returned."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        for i in range(10):
            (kanban_dir / f"task{i:02d}.md").write_text(
                f"优先级: {i}\ncontent", encoding="utf-8"
            )

        result = injector._read_kanban(str(kanban_dir), "")
        assert result is not None
        # Count '-' bullet entries (but not the header line)
        bullet_count = sum(1 for line in result.split("\n") if line.startswith("- "))
        assert bullet_count == 5
        # Only first 5 files alphabetically
        assert "task00" in result
        assert "task04" in result
        assert "task05" not in result
        assert "task09" not in result

    def test_custom_label(self, tmp_path):
        """Custom label replaces the default header."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        (kanban_dir / "task.md").write_text("优先级: P0\n", encoding="utf-8")

        result = injector._read_kanban(str(kanban_dir), "🗂️ 自定义看板:")
        assert result is not None
        assert result.startswith("🗂️ 自定义看板:")
        assert "📋 项目状态:" not in result

    def test_default_label(self, tmp_path):
        """Empty label → uses default '📋 项目状态:'."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        (kanban_dir / "task.md").write_text("优先级: P0\n", encoding="utf-8")

        result = injector._read_kanban(str(kanban_dir), "")
        assert result is not None
        assert result.startswith("📋 项目状态:")


# ── inject_context P3 integration ──────────────────────────────────────


class TestInjectContextP3:
    @patch("hermes_persona.injector._load_config")
    def test_kanban_first_turn_injects(self, mock_load, inject_context_defaults, tmp_path):
        """Kanban is injected when is_first_turn=True and project.enabled=True."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        (kanban_dir / "task.md").write_text("优先级: P0\n", encoding="utf-8")

        mock_load.return_value = {
            "project": {
                "enabled": True,
                "kanban_path": str(kanban_dir),
            },
        }
        inject_context_defaults["is_first_turn"] = True
        result = inject_context(**inject_context_defaults)
        assert result is not None
        assert "📋 项目状态:" in result["context"]
        assert "task" in result["context"]

    @patch("hermes_persona.injector._load_config")
    def test_kanban_not_first_turn(self, mock_load, inject_context_defaults, tmp_path):
        """Kanban is NOT injected when is_first_turn=False."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        (kanban_dir / "task.md").write_text("优先级: P0\n", encoding="utf-8")

        mock_load.return_value = {
            "project": {
                "enabled": True,
                "kanban_path": str(kanban_dir),
            },
        }
        inject_context_defaults["is_first_turn"] = False
        result = inject_context(**inject_context_defaults)
        if result is not None:
            assert "📋 项目状态:" not in result["context"]

    @patch("hermes_persona.injector._load_config")
    def test_kanban_path_not_found_degradation(self, mock_load, inject_context_defaults, tmp_path):
        """Non-existent kanban directory → graceful degradation, no exception."""
        bad_path = str(tmp_path / "does_not_exist")
        mock_load.return_value = {
            "project": {
                "enabled": True,
                "kanban_path": bad_path,
            },
        }
        inject_context_defaults["is_first_turn"] = True
        result = inject_context(**inject_context_defaults)
        # Should not crash; result may have time context but no kanban
        if result is not None:
            assert "📋 项目状态:" not in result["context"]

    @patch("hermes_persona.injector._load_config")
    def test_kanban_empty_dir_no_injection(self, mock_load, inject_context_defaults, tmp_path):
        """Empty kanban directory → no kanban content injected."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()

        mock_load.return_value = {
            "project": {
                "enabled": True,
                "kanban_path": str(kanban_dir),
            },
        }
        inject_context_defaults["is_first_turn"] = True
        result = inject_context(**inject_context_defaults)
        if result is not None:
            assert "📋 项目状态:" not in result["context"]

    @patch("hermes_persona.injector._load_config")
    def test_kanban_custom_label_active(self, mock_load, inject_context_defaults, tmp_path):
        """Custom label from config is used in the injected context."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        (kanban_dir / "task.md").write_text("优先级: P0\n", encoding="utf-8")

        mock_load.return_value = {
            "project": {
                "enabled": True,
                "kanban_path": str(kanban_dir),
                "label": "🗂️ 团队看板:",
            },
        }
        inject_context_defaults["is_first_turn"] = True
        result = inject_context(**inject_context_defaults)
        assert result is not None
        assert "🗂️ 团队看板:" in result["context"]

    @patch("hermes_persona.injector._load_config")
    def test_kanban_disabled_no_injection(self, mock_load, inject_context_defaults, tmp_path):
        """When project.enabled=False, kanban is never injected even on first turn."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        (kanban_dir / "task.md").write_text("优先级: P0\n", encoding="utf-8")

        mock_load.return_value = {
            "project": {
                "enabled": False,
                "kanban_path": str(kanban_dir),
            },
        }
        inject_context_defaults["is_first_turn"] = True
        result = inject_context(**inject_context_defaults)
        if result is not None:
            assert "📋 项目状态:" not in result["context"]
