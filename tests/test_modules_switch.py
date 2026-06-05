"""Tests for module switch system — _MODULE_REGISTRY, _resolve_modules,
_is_enabled, _has_any_dynamic, and integration tests for each module.

TDD red phase: all tests should FAIL until implementation is done.
"""

from unittest.mock import patch

import pytest

import injector


# ── TestModuleRegistry ────────────────────────────────────────────────────


class TestModuleRegistry:
    def test_all_expected_modules_registered(self):
        """_MODULE_REGISTRY must contain 11 module keys."""
        registry = injector._MODULE_REGISTRY
        expected_keys = {"time", "weather", "static_rules", "dynamic", "fixed_signals", "expression_vector", "variance", "memory", "kanban", "debug", "translate"}
        assert set(registry.keys()) == expected_keys

    def test_each_module_has_required_fields(self):
        """Each registry entry must contain description, default, phase fields."""
        for key, meta in injector._MODULE_REGISTRY.items():
            assert "description" in meta, f"{key} missing description"
            assert "default" in meta, f"{key} missing default"
            assert "phase" in meta, f"{key} missing phase"


# ── TestResolveModules ────────────────────────────────────────────────────


class TestResolveModules:
    def test_new_format_priority(self):
        """modules key exists → use it directly, ignore legacy format."""
        config = {"modules": {"time": False}, "time": {"enabled": True}}
        modules = injector._resolve_modules(config)
        assert modules["time"] is False

    def test_legacy_synthesis_time_disabled(self):
        """No modules key, time.enabled=false → modules['time']=False."""
        config = {"time": {"enabled": False}}
        modules = injector._resolve_modules(config)
        assert modules["time"] is False

    def test_legacy_synthesis_memory_enabled(self):
        """No modules key, memory.enabled=true → modules['memory']=True."""
        config = {"memory": {"enabled": True}}
        modules = injector._resolve_modules(config)
        assert modules["memory"] is True

    def test_legacy_synthesis_project_to_kanban(self):
        """No modules key, project.enabled=true → modules['kanban']=True."""
        config = {"project": {"enabled": True}}
        modules = injector._resolve_modules(config)
        assert modules["kanban"] is True

    def test_empty_config_falls_back_to_defaults(self):
        """config={} → all modules use _MODULE_REGISTRY default values."""
        modules = injector._resolve_modules({})
        for key, meta in injector._MODULE_REGISTRY.items():
            if key == "dynamic":
                continue  # dynamic is special, not a simple bool
            assert modules.get(key, meta["default"]) == meta["default"], (
                f"{key}: expected default {meta['default']}, got {modules.get(key)}"
            )

    def test_modules_empty_object(self):
        """modules={} → missing keys filled from legacy config or registry defaults."""
        config = {"modules": {}}
        modules = injector._resolve_modules(config)
        # All registered modules get their default values merged in
        for key, meta in injector._MODULE_REGISTRY.items():
            assert key in modules, f"{key} should be merged into modules"
            expected = meta["default"]
            actual = modules[key]
            if isinstance(actual, dict):
                # dynamic sub-channel dicts default to all True
                assert actual.get("enabled", True) is True
            else:
                assert actual == expected, f"{key}: expected {expected}, got {actual}"

    def test_legacy_missing_section(self):
        """Only time.enabled=False in config → memory/kanban use defaults."""
        config = {"time": {"enabled": False}}
        modules = injector._resolve_modules(config)
        assert modules["time"] is False
        # memory default is False, kanban default is False
        assert modules["memory"] is False
        assert modules["kanban"] is False

    def test_legacy_synthesis_expression_vector(self):
        """No modules key, expression_vector.enabled=true → modules['expression_vector']=True."""
        config = {"expression_vector": {"enabled": True}}
        modules = injector._resolve_modules(config)
        assert modules["expression_vector"] is True

    def test_legacy_synthesis_expression_vector_default(self):
        """No modules key, no expression_vector section → default False."""
        config = {}
        modules = injector._resolve_modules(config)
        assert modules["expression_vector"] is False


# ── TestIsEnabled ─────────────────────────────────────────────────────────


class TestIsEnabled:
    def test_key_true(self):
        """modules={'time': True} → True."""
        assert injector._is_enabled({"time": True}, "time") is True

    def test_key_false(self):
        """modules={'time': False} → False."""
        assert injector._is_enabled({"time": False}, "time") is False

    def test_key_missing_falls_back_to_default(self):
        """modules={} → falls back to registry default for 'time' (True)."""
        assert injector._is_enabled({}, "time") is True

    def test_dynamic_dict_means_parent_enabled(self):
        """modules={'dynamic': {'time_slots': True}} → dynamic is enabled (dict=True)."""
        assert injector._is_enabled({"dynamic": {"time_slots": True}}, "dynamic") is True

    def test_dynamic_bool_false(self):
        """modules={'dynamic': False} → dynamic is disabled."""
        assert injector._is_enabled({"dynamic": False}, "dynamic") is False

    def test_unknown_key_fail_open(self):
        """modules={}, key='nonexistent' → returns True (fail-open)."""
        assert injector._is_enabled({}, "nonexistent") is True


# ── TestHasAnyDynamic ────────────────────────────────────────────────────


class TestHasAnyDynamic:
    def test_all_subchannels_on(self):
        """All subchannels True → True."""
        modules = {"dynamic": {"time_slots": True, "turn_stage": True, "keyword": True}}
        assert injector._has_any_dynamic(modules) is True

    def test_only_time_slots_on(self):
        """Only time_slots True → True."""
        modules = {"dynamic": {"time_slots": True, "turn_stage": False, "keyword": False}}
        assert injector._has_any_dynamic(modules) is True

    def test_all_subchannels_off(self):
        """All subchannels False → False."""
        modules = {"dynamic": {"time_slots": False, "turn_stage": False, "keyword": False}}
        assert injector._has_any_dynamic(modules) is False

    def test_parent_disabled(self):
        """dynamic=False → False regardless of subchannels."""
        modules = {"dynamic": False}
        assert injector._has_any_dynamic(modules) is False

    def test_dynamic_bool_true(self):
        """dynamic=True (bool) → True."""
        modules = {"dynamic": True}
        assert injector._has_any_dynamic(modules) is True


# ── TestModuleSwitchIntegration ──────────────────────────────────────────


class TestModuleSwitchIntegration:
    def test_time_disabled_no_time_context(self, inject_context_defaults):
        """modules.time=false → result does not contain time string."""
        with patch("injector._load_config", return_value={
            "modules": {"time": False},
            "time": {"format": "cn_full"},
        }):
            result = injector.inject_context(**inject_context_defaults)
        if result is not None:
            assert "🕐" not in result["context"]

    def test_time_enabled_normal_injection(self, inject_context_defaults):
        """modules.time=true → result contains time string."""
        with patch("injector._load_config", return_value={
            "modules": {"time": True},
            "time": {"format": "cn_full"},
        }):
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "🕐" in result["context"]

    def test_static_rules_disabled_no_rules(self, inject_context_defaults):
        """modules.static_rules=false → no rules injected."""
        with patch("injector._load_config", return_value={
            "modules": {"time": False, "static_rules": False},
            "context": {"rules": ["规则1", "规则2"]},
        }):
            result = injector.inject_context(**inject_context_defaults)
        if result is not None:
            assert "规则1" not in result["context"]
            assert "规则2" not in result["context"]

    def test_static_rules_enabled_normal_injection(self, inject_context_defaults):
        """modules.static_rules=true → rules injected."""
        with patch("injector._load_config", return_value={
            "modules": {"time": False, "static_rules": True},
            "context": {"rules": ["测试规则"]},
        }):
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "测试规则" in result["context"]

    def test_dynamic_parent_disabled(self, inject_context_defaults):
        """modules.dynamic=false → no dynamic rules."""
        with patch("injector._load_config", return_value={
            "modules": {"time": False, "dynamic": False},
            "dynamic": {"keywords": {"bug": ["规则"]}},
        }), patch("injector._recall_memories", return_value=None):
            result = injector.inject_context(**inject_context_defaults)
        if result is not None:
            assert "bug" not in result["context"]
            assert "💬" not in result["context"]

    def test_dynamic_only_time_slots_disabled(self, inject_context_defaults):
        """Only time_slots off → turn_stage and keyword still work."""
        with patch("injector._load_config", return_value={
            "modules": {
                "time": False,
                "dynamic": {"time_slots": False, "turn_stage": True, "keyword": True},
            },
            "dynamic": {
                "time_slots": {"22:00-05:00": ["深夜规则"]},
                "turn_stage": {"after_10": ["中期规则"]},
                "keywords": {"bug": ["Bug规则"]},
            },
        }), patch("injector._recall_memories", return_value=None):
            inject_context_defaults["conversation_history"] = [{"role": "user"}] * 30
            inject_context_defaults["is_first_turn"] = False
            inject_context_defaults["user_message"] = "there is a bug"
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "中期规则" in result["context"]
        assert "Bug规则" in result["context"]
        assert "深夜规则" not in result["context"]

    def test_dynamic_only_turn_stage_disabled(self, inject_context_defaults):
        """Only turn_stage off → time_slots and keyword still work."""
        with patch("injector._load_config", return_value={
            "modules": {
                "time": False,
                "dynamic": {"time_slots": True, "turn_stage": False, "keyword": True},
            },
            "dynamic": {
                "time_slots": {"09:00-17:00": ["工作规则"]},
                "turn_stage": {"after_10": ["中期规则"]},
                "keywords": {"bug": ["Bug规则"]},
            },
        }), patch("dynamic_rules.datetime") as mock_dt:
            from datetime import datetime
            mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
            inject_context_defaults["conversation_history"] = [{"role": "user"}] * 30
            inject_context_defaults["is_first_turn"] = False
            inject_context_defaults["user_message"] = "there is a bug"
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "工作规则" in result["context"]
        assert "Bug规则" in result["context"]
        assert "中期规则" not in result["context"]

    def test_dynamic_only_keyword_disabled(self, inject_context_defaults):
        """Only keyword off → time_slots and turn_stage still work."""
        with patch("injector._load_config", return_value={
            "modules": {
                "time": False,
                "dynamic": {"time_slots": True, "turn_stage": True, "keyword": False},
            },
            "dynamic": {
                "time_slots": {"09:00-17:00": ["工作规则"]},
                "turn_stage": {"after_10": ["中期规则"]},
                "keywords": {"bug": ["Bug规则"]},
            },
        }), patch("dynamic_rules.datetime") as mock_dt:
            from datetime import datetime
            mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
            inject_context_defaults["conversation_history"] = [{"role": "user"}] * 30
            inject_context_defaults["is_first_turn"] = False
            inject_context_defaults["user_message"] = "there is a bug"
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "工作规则" in result["context"]
        assert "中期规则" in result["context"]
        assert "Bug规则" not in result["context"]

    def test_variance_disabled(self, inject_context_defaults):
        """modules.variance=false → no variance injected."""
        with patch("injector._load_config", return_value={
            "modules": {"time": False, "variance": False},
            "variance": {"fox_ears": {"probability": 1.0, "variants": ["耳朵动了"]}},
        }):
            result = injector.inject_context(**inject_context_defaults)
        if result is not None:
            assert "耳朵动了" not in result["context"]

    def test_variance_enabled(self, inject_context_defaults):
        """modules.variance=true, probability=1.0 → variance injected."""
        with patch("injector._load_config", return_value={
            "modules": {"time": False, "variance": True},
            "variance": {"fox_ears": {"probability": 1.0, "variants": ["耳朵动了"]}},
        }), patch("random.random", return_value=0.0):
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "耳朵动了" in result["context"]

    def test_memory_disabled_not_called(self, inject_context_defaults):
        """modules.memory=false → _recall_memories is not called."""
        with patch("injector._load_config", return_value={
            "modules": {"memory": False},
            "memory": {"enabled": True, "api_url": "http://example.com"},
        }), patch("injector._recall_memories") as mock_recall:
            injector.inject_context(**inject_context_defaults)
        mock_recall.assert_not_called()

    def test_memory_enabled_called(self, inject_context_defaults):
        """modules.memory=true → _recall_memories is called."""
        with patch("injector._load_config", return_value={
            "modules": {"memory": True},
            "memory": {"enabled": True, "api_url": "http://example.com"},
        }), patch("injector._recall_memories", return_value=None) as mock_recall:
            injector.inject_context(**inject_context_defaults)
        mock_recall.assert_called_once()

    def test_kanban_disabled_not_injected(self, inject_context_defaults, tmp_path):
        """is_first_turn=True, modules.kanban=false → no kanban."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        (kanban_dir / "task.md").write_text("优先级: P0\n", encoding="utf-8")

        with patch("injector._load_config", return_value={
            "modules": {"time": False, "kanban": False},
            "project": {"enabled": True, "kanban_path": str(kanban_dir)},
        }):
            result = injector.inject_context(**inject_context_defaults)
        if result is not None:
            assert "📋 项目状态:" not in result["context"]

    def test_kanban_enabled_normal_injection(self, inject_context_defaults, tmp_path):
        """is_first_turn=True, modules.kanban=true → kanban injected."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        (kanban_dir / "task.md").write_text("优先级: P0\n", encoding="utf-8")

        with patch("injector._load_config", return_value={
            "modules": {"time": False, "kanban": True},
            "project": {"enabled": True, "kanban_path": str(kanban_dir)},
        }):
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "📋 项目状态:" in result["context"]

    def test_kanban_not_first_turn(self, inject_context_defaults, tmp_path):
        """is_first_turn=False → kanban not injected even if enabled."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        (kanban_dir / "task.md").write_text("优先级: P0\n", encoding="utf-8")

        inject_context_defaults["is_first_turn"] = False
        with patch("injector._load_config", return_value={
            "modules": {"time": False, "kanban": True},
            "project": {"enabled": True, "kanban_path": str(kanban_dir)},
        }):
            result = injector.inject_context(**inject_context_defaults)
        if result is not None:
            assert "📋 项目状态:" not in result["context"]

    def test_all_modules_disabled_returns_none(self, inject_context_defaults):
        """All modules off → inject_context returns None."""
        with patch("injector._load_config", return_value={
            "modules": {
                "time": False,
                "static_rules": False,
                "dynamic": False,
                "variance": False,
                "memory": False,
                "kanban": False,
                "debug": False,
            },
            "time": {"format": "cn_full"},
        }):
            result = injector.inject_context(**inject_context_defaults)
        assert result is None

    # ── expression_vector / fixed_signals module switches (SPEC-011) ──────

    def test_expression_vector_module_switch_off(self, inject_context_defaults):
        """modules.expression_vector=False → EV not initialized even if ev_cfg.enabled=True."""
        with patch("injector._load_config", return_value={
            "modules": {"time": True, "expression_vector": False},
            "time": {"format": "cn_full"},
            "expression_vector": {
                "enabled": True,
                "dimensions": {
                    "work": {"label": "工作", "keywords": ["代码"], "score_rules": [1, -0.5, 1, 0.95]},
                },
                "reset": "session",
                "storage_path": "",
            },
        }):
            result = injector.inject_context(**inject_context_defaults)
        context = result["context"] if result else ""
        assert "表达向量" not in context

    def test_expression_vector_func_switch_off(self, inject_context_defaults):
        """modules.expression_vector=True but ev_cfg.enabled=False → EV not initialized."""
        with patch("injector._load_config", return_value={
            "modules": {"time": True, "expression_vector": True},
            "time": {"format": "cn_full"},
            "expression_vector": {
                "enabled": False,
                "dimensions": {
                    "work": {"label": "工作", "keywords": ["代码"], "score_rules": [1, -0.5, 1, 0.95]},
                },
                "reset": "session",
                "storage_path": "",
            },
        }):
            result = injector.inject_context(**inject_context_defaults)
        context = result["context"] if result else ""
        assert "表达向量" not in context

    def test_fixed_signals_module_switch_off(self, inject_context_defaults):
        """modules.fixed_signals=False → all fixed signal hints skipped."""
        with patch("injector._load_config", return_value={
            "modules": {"time": True, "fixed_signals": False},
            "time": {"format": "cn_full"},
            "fixed_signals": {
                "message_length": {"enabled": True, "threshold": 50},
                "reply_gap": {"enabled": True, "threshold_minutes": 30},
                "daily_turn_count": {"enabled": True, "thresholds": {"morning": 10}, "storage_path": ""},
            },
        }):
            result = injector.inject_context(
                user_message="hi",
                session_id="test",
                conversation_history=[],
                is_first_turn=True,
                model="claude",
                platform="test",
            )
        context = result["context"] if result else ""
        assert "消息较短" not in context
        assert "欢迎回来" not in context
        assert "今日第" not in context


# ── TestDebugMode ────────────────────────────────────────────────────────


class TestDebugMode:
    def test_debug_disabled_no_summary(self, inject_context_defaults):
        """modules.debug=false (default) → context does not contain debug summary."""
        with patch("injector._load_config", return_value={
            "modules": {"time": True, "debug": False},
            "time": {"format": "cn_full"},
        }):
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "🔧 [Debug]" not in result["context"]

    def test_debug_enabled_appends_summary(self, inject_context_defaults):
        """modules.debug=true → _PENDING_DEBUG_BLOCK is set with debug summary."""
        with patch("injector._load_config", return_value={
            "modules": {"time": True, "debug": True},
            "time": {"format": "cn_full"},
        }):
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        # Debug goes to _PENDING_DEBUG_BLOCK, not context
        assert "🔧 [Debug]" not in result["context"]
        assert injector._PENDING_DEBUG_BLOCK is not None
        assert "🔧 [Debug] 本轮注入:" in injector._PENDING_DEBUG_BLOCK
        assert "① 🕐" in injector._PENDING_DEBUG_BLOCK
        assert "② 📜" in injector._PENDING_DEBUG_BLOCK
        assert "③ ⚡" in injector._PENDING_DEBUG_BLOCK
        assert "④ 🎲" in injector._PENDING_DEBUG_BLOCK
        assert "⑤ 🧠" in injector._PENDING_DEBUG_BLOCK
        assert "⑥ 📋" in injector._PENDING_DEBUG_BLOCK

    def test_debug_only_all_modules_off_returns_none(self, inject_context_defaults):
        """All modules off + debug on → returns None (debug doesn't count for empty check)."""
        with patch("injector._load_config", return_value={
            "modules": {
                "time": False,
                "static_rules": False,
                "dynamic": False,
                "variance": False,
                "memory": False,
                "kanban": False,
                "debug": True,
            },
        }):
            result = injector.inject_context(**inject_context_defaults)
        assert result is None

    def test_debug_memory_disabled_shows_stopped(self, inject_context_defaults):
        """debug=true, memory=false → _PENDING_DEBUG_BLOCK shows 🧠 已停用."""
        with patch("injector._load_config", return_value={
            "modules": {"time": True, "memory": False, "debug": True},
            "time": {"format": "cn_full"},
        }):
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "🧠 已停用" not in result["context"]
        assert injector._PENDING_DEBUG_BLOCK is not None
        assert "🧠 已停用" in injector._PENDING_DEBUG_BLOCK


# ── TestBackwardCompatibility ────────────────────────────────────────────


class TestBackwardCompatibility:
    def test_legacy_time_enabled_false(self, inject_context_defaults):
        """No modules key, time.enabled=false → time not injected."""
        with patch("injector._load_config", return_value={
            "time": {"enabled": False},
        }):
            result = injector.inject_context(**inject_context_defaults)
        if result is not None:
            assert "🕐" not in result["context"]

    def test_legacy_memory_enabled_true(self, inject_context_defaults):
        """No modules key, memory.enabled=true → memory recall is called."""
        with patch("injector._load_config", return_value={
            "memory": {"enabled": True, "api_url": "http://example.com"},
        }), patch("injector._recall_memories", return_value=None) as mock_recall:
            injector.inject_context(**inject_context_defaults)
        mock_recall.assert_called_once()

    def test_legacy_project_enabled_true(self, inject_context_defaults, tmp_path):
        """No modules key, project.enabled=true → kanban injected."""
        kanban_dir = tmp_path / "kanban"
        kanban_dir.mkdir()
        (kanban_dir / "task.md").write_text("优先级: P0\n", encoding="utf-8")

        with patch("injector._load_config", return_value={
            "project": {"enabled": True, "kanban_path": str(kanban_dir)},
        }):
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "📋 项目状态:" in result["context"]

    def test_modules_wins_over_legacy(self, inject_context_defaults):
        """Both modules.time=true and time.enabled=false → modules wins."""
        with patch("injector._load_config", return_value={
            "modules": {"time": True},
            "time": {"enabled": False},
        }):
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "🕐" in result["context"]

    def test_no_modules_no_legacy_default_behavior(self, inject_context_defaults):
        """No modules, no legacy switches → default behavior (time enabled)."""
        with patch("injector._load_config", return_value={}):
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "🕐" in result["context"]


# ── TestEdgeCases ────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_modules_none_no_crash(self, inject_context_defaults):
        """modules=None in config → no TypeError, defaults to default behavior."""
        with patch("injector._load_config", return_value={
            "modules": None,
        }):
            result = injector.inject_context(**inject_context_defaults)
        # Should degrade gracefully (time default True)
        assert result is not None
        assert "🕐" in result["context"]

    def test_modules_non_bool_value_truthy(self, inject_context_defaults):
        """modules.time=1 → truthy, treated as True."""
        with patch("injector._load_config", return_value={
            "modules": {"time": 1},
            "time": {"format": "cn_full"},
        }):
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        assert "🕐" in result["context"]

    def test_dynamic_subchannel_missing_keys_default_true(self, inject_context_defaults):
        """dynamic dict missing some subchannel keys → defaults to True."""
        with patch("injector._load_config", return_value={
            "modules": {
                "time": False,
                "dynamic": {"time_slots": False},  # turn_stage & keyword missing
            },
            "dynamic": {
                "time_slots": {"09:00-17:00": ["工作规则"]},
                "turn_stage": {"after_10": ["中期规则"]},
                "keywords": {"bug": ["Bug规则"]},
            },
        }), patch("dynamic_rules.datetime") as mock_dt:
            from datetime import datetime
            mock_dt.now.return_value = datetime(2026, 5, 16, 14, 30, 0)
            inject_context_defaults["conversation_history"] = [{"role": "user"}] * 30
            inject_context_defaults["is_first_turn"] = False
            inject_context_defaults["user_message"] = "there is a bug"
            result = injector.inject_context(**inject_context_defaults)
        assert result is not None
        # turn_stage and keyword should work (default True)
        assert "中期规则" in result["context"]
        assert "Bug规则" in result["context"]
        # time_slots explicitly disabled
        assert "工作规则" not in result["context"]

    def test_all_modules_off_no_exception(self, inject_context_defaults):
        """All modules off → returns None, no exception."""
        with patch("injector._load_config", return_value={
            "modules": {
                "time": False,
                "static_rules": False,
                "dynamic": False,
                "variance": False,
                "memory": False,
                "kanban": False,
            },
        }):
            result = injector.inject_context(**inject_context_defaults)
        assert result is None
