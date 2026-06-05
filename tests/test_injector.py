"""P1 tests for injector — config loading, time context,
static rules, and inject_context assembly."""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

import injector
from expression_vector import _ExpressionVector
from injector import (
    _debug_summary,
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

    @patch("injector.datetime")
    def test_iso_format(self, mock_dt):
        """iso format produces ISO8601 string."""
        mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
        result = _time_context("iso")
        assert result == "🕐 2026-05-16T14:30:00"

    @patch("injector.datetime")
    def test_compact_format(self, mock_dt):
        """compact format produces MM/DD HH:MM string."""
        mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
        result = _time_context("compact")
        assert result == "🕐 05/16 14:30"

    @patch("injector.datetime")
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
    @patch("injector._load_config", return_value={})
    def test_empty_config_returns_time_context(self, _mock_load, inject_context_defaults):
        """With empty config {}, inject_context returns at least time context."""
        result = inject_context(**inject_context_defaults)
        assert result is not None
        assert "context" in result
        assert "🕐" in result["context"]

    @patch("injector._load_config", return_value={})
    def test_time_disabled(self, _mock_load, inject_context_defaults):
        """When time.enabled is False, no time line in output."""
        _mock_load.return_value = {"time": {"enabled": False}}
        result = inject_context(**inject_context_defaults)
        # With time disabled and no other rules, parts may be empty → None
        if result is not None:
            assert "🕐" not in result["context"]

    @patch("injector._load_config")
    def test_static_rules_appear_every_turn(self, mock_load, inject_context_defaults):
        """Static rules from context.rules appear in every turn."""
        mock_load.return_value = {
            "context": {"rules": ["你是助手"]},
        }
        inject_context_defaults["is_first_turn"] = False
        result = inject_context(**inject_context_defaults)
        assert result is not None
        assert "你是助手" in result["context"]

    @patch("injector._load_config")
    def test_rules_first_turn_only_first_turn(self, mock_load, inject_context_defaults):
        """First-turn-only rules appear on the first turn."""
        mock_load.return_value = {
            "context": {"rules_first_turn_only": ["欢迎新用户"]},
        }
        inject_context_defaults["is_first_turn"] = True
        result = inject_context(**inject_context_defaults)
        assert result is not None
        assert "欢迎新用户" in result["context"]

    @patch("injector._load_config")
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
        with patch("injector._load_config", return_value={}):
            result = inject_context(**inject_context_defaults)
        assert result is not None  # at least time context

    def test_history_empty_no_crash(self, inject_context_defaults):
        """conversation_history=[] should not crash."""
        inject_context_defaults["conversation_history"] = []
        with patch("injector._load_config", return_value={}):
            result = inject_context(**inject_context_defaults)
        assert result is not None

    @patch("injector._load_config")
    def test_no_parts_returns_none(self, mock_load, inject_context_defaults):
        """When all config is disabled, inject_context returns None."""
        mock_load.return_value = {
            "time": {"enabled": False},
        }
        inject_context_defaults["is_first_turn"] = False
        result = inject_context(**inject_context_defaults)
        assert result is None

    @patch("injector._load_config")
    def test_exception_does_not_propagate(self, mock_load, inject_context_defaults):
        """Any exception inside inject_context returns None, not an unhandled error."""
        mock_load.side_effect = RuntimeError("simulated failure")
        result = inject_context(**inject_context_defaults)
        assert result is None


# ── Code audit: no role-specific content ────────────────────────────────


class TestCodeGeneric:
    """Ensure code contains no role-specific / character-specific content."""

    ROLE_TERMS = [
        "Luna", "luna-bot", "luna",
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

        py_files = glob.glob("*.py", recursive=False)
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
    @patch("injector._load_config")
    def test_keyword_injection_in_context(self, mock_load, inject_context_defaults):
        """Keyword matching injects rules into the full context."""
        mock_load.return_value = {
            "dynamic": {"keywords": {"bug": ["检测到异常"]}},
        }
        inject_context_defaults["user_message"] = "发现了一个bug"
        result = inject_context(**inject_context_defaults)
        assert result is not None
        assert "检测到异常" in result["context"]

    @patch("injector._load_config")
    @patch("injector._recall_memories")
    def test_memory_injection_in_context(self, mock_recall, mock_load, inject_context_defaults):
        """Memory recall result is injected into the full context."""
        mock_load.return_value = {
            "memory": {"enabled": True, "api_url": "http://example.com"},
        }
        mock_recall.return_value = "📝 相关记忆:\n- 历史片段"
        result = inject_context(**inject_context_defaults)
        assert result is not None
        assert "历史片段" in result["context"]

    @patch("injector._load_config")
    @patch("injector._recall_memories")
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
    @patch("injector._load_config")
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

    @patch("injector._load_config")
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

    @patch("injector._load_config")
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

    @patch("injector._load_config")
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

    @patch("injector._load_config")
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

    @patch("injector._load_config")
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


# ── INT-EV: Expression vector integration (US-002) ──────────────────────


class TestExpressionVectorIntegration:
    """INT-EV-01 ~ INT-EV-04: 表达向量端到端集成测试。"""

    def test_INT_EV01_enabled_injects_vector(
        self, temp_config_root, write_config, inject_context_defaults
    ):
        """INT-EV-01: expression_vector.enabled=true → 注入含 📊 [表达向量]。"""
        ev_path = str(temp_config_root / "ev.json")
        write_config({
            "hermes-persona": {
                "modules": {
                    "time": False, "static_rules": False, "dynamic": False,
                    "variance": False, "memory": False, "kanban": False,
                    "debug": False,
                },
                "expression_vector": {
                    "enabled": True,
                    "dimensions": {"work": ["代码"]},
                    "score_rules": {"work": [1, -0.5, 1]},
                    "reset": "session",
                    "storage_path": ev_path,
                },
            }
        })
        defaults = {**inject_context_defaults, "user_message": "写代码"}
        result = injector.inject_context(**defaults)
        assert result is not None
        assert "📊 [表达向量]" in result["context"]
        assert "work:1" in result["context"]

    def test_INT_EV02_disabled_no_injection(
        self, temp_config_root, write_config, inject_context_defaults
    ):
        """INT-EV-02: expression_vector.enabled=false → 不含表达向量。"""
        write_config({
            "hermes-persona": {
                "modules": {"time": True},
                "expression_vector": {"enabled": False},
            }
        })
        result = injector.inject_context(**inject_context_defaults)
        if result is not None:
            assert "📊 [表达向量]" not in result["context"]

    def test_INT_EV03_not_configured(
        self, temp_config_root, write_config, inject_context_defaults
    ):
        """INT-EV-03: 不配置 expression_vector → 插件正常运行。"""
        write_config({"hermes-persona": {"modules": {"time": True}}})
        result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "📊 [表达向量]" not in result["context"]

    def test_INT_EV04_keyword_hit_accumulates(
        self, temp_config_root, write_config, inject_context_defaults
    ):
        """INT-EV-04: 连续调用 2 次，第二次 work 值 > 第一次。"""
        ev_path = str(temp_config_root / "ev.json")
        write_config({
            "hermes-persona": {
                "modules": {
                    "time": False, "static_rules": False, "dynamic": False,
                    "variance": False, "memory": False, "kanban": False,
                    "debug": False,
                },
                "expression_vector": {
                    "enabled": True,
                    "dimensions": {"work": ["代码"]},
                    "score_rules": {"work": [1, -0.5, 1]},
                    "reset": "session",
                    "storage_path": ev_path,
                },
            }
        })
        defaults = {**inject_context_defaults, "user_message": "写代码"}

        r1 = injector.inject_context(**defaults)
        assert "work:1" in r1["context"]

        r2 = injector.inject_context(**defaults)
        assert "work:2" in r2["context"]

    def test_INT_EV05_background_message_skipped(
        self, temp_config_root, write_config, inject_context_defaults
    ):
        """INT-EV-05: 后台进程消息不触发表达向量更新。"""
        ev_path = str(temp_config_root / "ev.json")
        write_config({
            "hermes-persona": {
                "modules": {
                    "time": False, "static_rules": False, "dynamic": False,
                    "variance": False, "memory": False, "kanban": False,
                    "debug": False,
                },
                "expression_vector": {
                    "enabled": True,
                    "dimensions": {"work": ["代码", "Bug"]},
                    "score_rules": {"work": [1, -0.5, 1]},
                    "reset": "session",
                    "storage_path": ev_path,
                },
            }
        })

        # 先发一条正常消息，让 work 有值
        defaults = {**inject_context_defaults, "user_message": "写代码"}
        result = injector.inject_context(**defaults)
        assert result is not None
        assert "📊 [表达向量]" in result["context"]

        ev = _ExpressionVector(
            {"dimensions": {"work": ["代码", "Bug"]},
             "score_rules": {"work": [1, -0.5, 1]},
             "reset": "session", "storage_path": ev_path}
        )
        ev.load()
        old_work = ev.vectors["work"]
        assert old_work > 0

        # 发后台进程完成消息
        bg_msg = (
            "[Kai.Xu] [IMPORTANT: Background process proc_123 completed"
            " (exit code 0).\nCommand: claude -p 'write plan'\n"
            "Output:\nPLAN-004 done."
        )
        defaults2 = {**inject_context_defaults, "user_message": bg_msg}
        result2 = injector.inject_context(**defaults2)
        assert result2 is not None
        # 后台消息被过滤，context 仍包含表达向量（来自旧值）
        assert "📊 [表达向量]" in result2["context"]

        ev.load()
        assert ev.vectors["work"] == old_work  # 未变


# ── INT-FS: Fixed signals integration (US-002) ──────────────────────────


class TestFixedSignalsIntegration:
    """INT-FS-01 ~ INT-FS-03: 固定信号端到端集成测试。"""

    def test_INT_FS01_short_message_hint(
        self, temp_config_root, write_config, inject_context_defaults
    ):
        """INT-FS-01: 短消息 → 注入含 '📏 消息较短'。"""
        write_config({
            "hermes-persona": {
                "modules": {
                    "time": False, "static_rules": False, "dynamic": False,
                    "variance": False, "memory": False, "kanban": False,
                    "debug": False,
                },
                "fixed_signals": {
                    "message_length": {"enabled": True, "threshold": 50},
                },
            }
        })
        defaults = {**inject_context_defaults, "user_message": "好"}
        result = injector.inject_context(**defaults)
        assert result is not None
        assert "📏 消息较短" in result["context"]

    def test_INT_FS02_long_gap_welcome_back(
        self, temp_config_root, write_config, inject_context_defaults
    ):
        """INT-FS-02: 长间隔 → 注入含 '🎵 欢迎回来'。"""
        import time as _time

        timing_path = str(temp_config_root / "reply_timing.json")
        with open(timing_path, "w") as f:
            json.dump({"last_reply_at": _time.time() - 3600}, f)

        write_config({
            "hermes-persona": {
                "modules": {
                    "time": False, "static_rules": False, "dynamic": False,
                    "variance": False, "memory": False, "kanban": False,
                    "debug": False,
                },
                "fixed_signals": {
                    "reply_gap": {
                        "enabled": True,
                        "threshold_minutes": 30,
                        "storage_path": timing_path,
                    },
                },
            }
        })
        result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "🎵 欢迎回来" in result["context"]

    def test_INT_FS03_not_configured(
        self, temp_config_root, write_config, inject_context_defaults
    ):
        """INT-FS-03: 不配置 fixed_signals → 插件正常运行。"""
        write_config({"hermes-persona": {"modules": {"time": True}}})
        result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "📏" not in result["context"]
        assert "🎵" not in result["context"]


# ── INT-ALL: Full integration (US-002) ──────────────────────────────────


class TestFullIntegration:
    """INT-ALL-01 ~ INT-ALL-02: 全链路集成测试。"""

    def test_INT_ALL01_all_features_enabled(
        self, temp_config_root, write_config, inject_context_defaults
    ):
        """INT-ALL-01: 全部新功能 + 现有模块同时开启，无异常。"""
        ev_path = str(temp_config_root / "ev.json")
        write_config({
            "hermes-persona": {
                "modules": {
                    "time": True, "static_rules": True, "dynamic": True,
                    "variance": False, "memory": False, "kanban": False,
                    "debug": False,
                },
                "context": {"rules": ["测试规则"]},
                "dynamic": {"time_slots": {}, "turn_stage": {}, "keywords": {}},
                "expression_vector": {
                    "enabled": True,
                    "dimensions": {"work": ["代码"]},
                    "score_rules": {"work": [1, -0.5, 1]},
                    "reset": "session",
                    "storage_path": ev_path,
                },
                "fixed_signals": {
                    "message_length": {"enabled": True, "threshold": 50},
                    "reply_gap": {"enabled": False},
                },
            }
        })
        defaults = {**inject_context_defaults, "user_message": "写代码"}
        result = injector.inject_context(**defaults)
        assert result is not None
        ctx = result["context"]
        assert "🕐" in ctx               # time
        assert "测试规则" in ctx           # static rules
        assert "📊 [表达向量]" in ctx      # expression vector
        assert "📏 消息较短" in ctx        # fixed signal

    def test_INT_ALL02_injection_order(
        self, temp_config_root, write_config, inject_context_defaults
    ):
        """INT-ALL-02: 注入顺序验证——表达向量在 dynamic 之后、variance 之前。"""
        ev_path = str(temp_config_root / "ev.json")
        write_config({
            "hermes-persona": {
                "modules": {
                    "time": True, "static_rules": True, "dynamic": True,
                    "variance": False, "memory": False, "kanban": False,
                    "debug": False,
                },
                "context": {"rules": []},
                "dynamic": {
                    "time_slots": {},
                    "turn_stage": {"first_turn": ["首次交流"]},
                    "keywords": {},
                },
                "expression_vector": {
                    "enabled": True,
                    "dimensions": {"work": ["代码"]},
                    "score_rules": {"work": [1, -0.5, 1]},
                    "reset": "session",
                    "storage_path": ev_path,
                },
            }
        })
        defaults = {**inject_context_defaults, "user_message": "写代码"}
        result = injector.inject_context(**defaults)
        assert result is not None
        ctx = result["context"]

        # dynamic (含 "首次交流") 在 expression_vector 之前
        pos_dynamic = ctx.find("首次交流")
        pos_ev = ctx.find("📊 [表达向量]")
        assert pos_dynamic < pos_ev, (
            f"dynamic ({pos_dynamic}) 应在 expression_vector ({pos_ev}) 之前"
        )


# ── TestDebugMode ────────────────────────────────────────────────────────────


class TestDebugModes:
    """debug compact/detailed 双模式测试。"""

    def _make_modules(self, **overrides):
        base = {"debug": True, "time": False, "static_rules": True,
                "dynamic": True, "variance": False, "memory": False, "kanban": False}
        base.update(overrides)
        return base

    def test_DBG01_compact_shows_count_only(self):
        """compact 模式显示条数，不展开规则内容。"""
        modules = self._make_modules(dynamic=False, variance=False)
        summary = _debug_summary(modules, [])
        assert "🔧 [Debug] 本轮注入:" in summary
        assert "📜" in summary  # 静态规则条数

    def test_DBG02_compact_dynamic_shows_sub_status(self):
        """compact 模式动态规则显示子通道开关。"""
        modules = self._make_modules(
            static_rules=False, variance=False,
            dynamic={"time_slots": True, "turn_stage": False, "keyword": True},
        )
        summary = _debug_summary(modules, [])
        assert "time_slots: on" in summary
        assert "turn_stage: off" in summary
        assert "keyword: on" in summary

    def test_DBG03_detailed_mode(self):
        """detail: 'detailed' 触发详细模式。"""
        modules = self._make_modules(
            static_rules=False, dynamic=False, variance=False,
        )
        config = {"debug": {"detail": "detailed"}}
        summary = _debug_summary(modules, [], config=config)
        assert "Debug" in summary

    def test_DBG04_detailed_with_ev_context(self):
        """详细模式 + expression_vector debug context。"""
        modules = self._make_modules(
            static_rules=False, dynamic=False, variance=False,
        )
        config = {"debug": {"detail": "detailed"}}
        debug_ctx = {
            "fixed_signals": {
                "message_length": {"triggered": False, "length": 10, "threshold": 50},
                "reply_gap": {"enabled": False, "triggered": False},
                "daily_turn_count": {"triggered": False},
            },
            "expression_vector": {
                "enabled": True,
                "turn_count": 42,
                "dimensions": {
                    "work": {"old": 5.0, "new": 6.0, "delta": 1.0,
                             "hit_keywords": ["代码"], "hit_count": 1},
                },
            },
            "variance": {"items": [], "total": 0, "hits": 0},
        }
        summary = _debug_summary(modules, [], config=config, debug_context=debug_ctx)
        assert "Debug" in summary

    def test_DBG05_detail_defaults_compact(self):
        """缺失 detail 键默认 compact。"""
        modules = self._make_modules(static_rules=False, dynamic=False, variance=False)
        config = {"debug": {}}  # no detail key
        summary = _debug_summary(modules, [], config=config)
        assert "🔧 [Debug] 本轮注入:" in summary


# ── Weather integration ─────────────────────────────────────────────────


class TestWeatherInjection:
    def test_weather_disabled_by_default(self, temp_config_root, write_config,
                                          inject_context_defaults):
        """weather 默认关闭，不注入天气。"""
        write_config({
            "hermes-persona": {
                "modules": {},
                "weather": {"location": "北京", "detail": "brief", "label": "🌤"},
            }
        })
        result = inject_context(**inject_context_defaults)
        if result:
            assert "🌤" not in result["context"]

    def test_weather_enabled_injects(self, temp_config_root, write_config,
                                      inject_context_defaults):
        """weather 开启且有 location 时注入天气。"""
        write_config({
            "hermes-persona": {
                "modules": {"weather": True, "time": True},
                "weather": {"location": "北京", "detail": "brief", "label": "🌤"},
                "time": {"enabled": True, "format": "cn_full"},
            }
        })
        with patch("weather._get_weather_data") as mock_get:
            mock_get.return_value = {
                "weather_code": 0, "temperature": 26.3, "humidity": 45,
                "wind_speed": 12.5, "location": "北京",
            }
            result = inject_context(**inject_context_defaults)
            assert result is not None
            assert "🌤" in result["context"]
            assert "北京" in result["context"]

    def test_weather_no_location_skips(self, temp_config_root, write_config,
                                        inject_context_defaults):
        """location 为空时不注入天气。"""
        write_config({
            "hermes-persona": {
                "modules": {"weather": True, "time": True},
                "weather": {"location": "", "detail": "brief", "label": "🌤"},
                "time": {"enabled": True, "format": "cn_full"},
            }
        })
        result = inject_context(**inject_context_defaults)
        if result:
            assert "🌤" not in result["context"]

    def test_weather_translate_mode(self, temp_config_root, write_config,
                                     inject_context_defaults):
        """translate 模式下天气融入自然语言。"""
        write_config({
            "hermes-persona": {
                "modules": {"weather": True, "time": True, "translate": True,
                            "dynamic": False},
                "weather": {"location": "北京", "detail": "brief", "label": "🌤"},
                "time": {"enabled": True, "format": "cn_full"},
                "context": {},
            }
        })
        with patch("weather._get_weather_data") as mock_get:
            mock_get.return_value = {
                "weather_code": 0, "temperature": 26.3, "humidity": 45,
                "wind_speed": 12.5, "location": "北京",
            }
            result = inject_context(**inject_context_defaults)
            assert result is not None
            assert "当地天气" in result["context"]
            assert "晴" in result["context"]

    def test_weather_injection_order(self, temp_config_root, write_config,
                                      inject_context_defaults):
        """天气在时间之后、静态规则之前注入。"""
        write_config({
            "hermes-persona": {
                "modules": {"weather": True, "time": True, "static_rules": True},
                "weather": {"location": "北京", "detail": "brief", "label": "🌤"},
                "time": {"enabled": True, "format": "cn_full"},
                "context": {"rules": ["测试规则"]},
            }
        })
        with patch("weather._get_weather_data") as mock_get:
            mock_get.return_value = {
                "weather_code": 0, "temperature": 26.3, "humidity": 45,
                "wind_speed": 12.5, "location": "北京",
            }
            result = inject_context(**inject_context_defaults)
            assert result is not None
            ctx = result["context"]
            time_pos = ctx.index("🕐")
            weather_pos = ctx.index("🌤")
            rule_pos = ctx.index("测试规则")
            assert time_pos < weather_pos < rule_pos

    def test_weather_debug_compact(self, temp_config_root, write_config,
                                    inject_context_defaults):
        """compact debug 模式显示天气注入状态。"""
        write_config({
            "hermes-persona": {
                "modules": {"weather": True, "time": True, "debug": True},
                "weather": {"location": "北京", "detail": "brief", "label": "🌤"},
                "time": {"enabled": True, "format": "cn_full"},
                "debug": {"detail": "compact"},
            }
        })
        with patch("weather._get_weather_data") as mock_get:
            mock_get.return_value = {
                "weather_code": 0, "temperature": 26.3, "humidity": 45,
                "wind_speed": 12.5, "location": "北京",
            }
            injector.inject_context(**inject_context_defaults)
            debug_block = injector._PENDING_DEBUG_BLOCK
            assert debug_block is not None
            assert "🌤" in debug_block
