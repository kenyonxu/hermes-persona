"""Tests for detailed debug mode (SPEC-003 §2.1-2.2)."""

from __future__ import annotations

import pytest

import injector
from locales import _init_locales, _t, _resolve_language


# Initialize locales once for module-level tests
_init_locales(".", {"language": "zh"})


class TestDebugModeSwitch:
    """_debug_summary() 模式切换测试。"""

    def test_default_mode_compact(self):
        """不传 config 参数 → 默认 compact 模式。"""
        result = injector._debug_summary(
            {"time": True, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
        )
        assert "🔧 [Debug] 本轮注入:" in result

    def test_detailed_mode_not_crash(self):
        """detailed 模式空 debug_context 不崩溃。"""
        result = injector._debug_summary(
            {"time": True, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={},
        )
        assert result  # 非空字符串

    def test_invalid_detail_fallback_to_compact(self):
        """无效 detail 值 → 回退 compact。"""
        result = injector._debug_summary(
            {"time": True, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "invalid_mode"}},
        )
        assert "🔧 [Debug] 本轮注入:" in result


class TestDebugDetailedFixedSignals:
    """④a 固定信号详细模式测试。"""

    def test_fixed_signals_all_triggered(self):
        """部分信号触发 → 显示 2/3 触发（reply_gap 未触发）。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={
                "fixed_signals": {
                    "message_length": {"visible": True, "triggered": True, "length": 3, "threshold": 50},
                    "reply_gap": {"enabled": True, "triggered": False, "last_reply": "2026-05-19 19:25:32", "gap_minutes": 0.5, "threshold_minutes": 30},
                    "daily_turn_count": {"visible": True, "triggered": True, "count": 42, "date": "2026-05-19"},
                },
            },
        )
        assert "2/3触发" in result or "2/3 triggered" in result

    def test_reply_gap_detail_shown(self):
        """reply_gap 显示 last_reply 时间戳。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={
                "fixed_signals": {
                    "reply_gap": {"enabled": True, "triggered": False, "last_reply": "2026-05-19 19:25:32", "gap_minutes": 0.5, "threshold_minutes": 30},
                },
            },
        )
        assert "2026-05-19" in result

    def test_no_fixed_signals(self):
        """无固定信号配置 → 显示无触发。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={"fixed_signals": {}},
        )
        assert "无触发" in result or "none" in result


class TestDebugDetailedExpressionVector:
    """④b 表达向量详细模式测试。"""

    def test_dimension_delta_shown(self):
        """维度变化显示 old→new (delta)。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={
                "expression_vector": {
                    "enabled": True,
                    "turn_count": 42,
                    "dimensions": {
                        "care": {"old": 2.0, "new": 3.0, "delta": 1.0, "hit_keywords": ["吃饭"], "hit_count": 1, "decay_dims": []},
                    },
                },
            },
        )
        assert "2→3" in result
        assert "care" in result

    def test_no_hit_displayed(self):
        """无命中维度显示无命中标注。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={
                "expression_vector": {
                    "enabled": True,
                    "turn_count": 1,
                    "dimensions": {
                        "work": {"old": 0.0, "new": 0.0, "delta": 0.0, "hit_keywords": [], "hit_count": 0, "decay_dims": []},
                    },
                },
            },
        )
        assert "无命中" in result or "none" in result

    def test_disabled_expression_vector(self):
        """表达向量未启用 → 显示未启用。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={"expression_vector": {"enabled": False}},
        )
        assert "未启用" in result or "Disabled" in result


class TestDebugDetailedVariance:
    """④ 随机变化详细模式测试。"""

    def test_variance_hit_miss_displayed(self):
        """显示每个变体抽中/未抽中状态。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": True, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=1,
            config={"debug": {"detail": "detailed"}},
            debug_context={
                "variance": {
                    "items": [
                        {"name": "fox_girl_body_language", "probability": 0.6, "rolled": True, "chosen": "🦊 test"},
                        {"name": "maid_body_language", "probability": 0.6, "rolled": False, "chosen": None},
                    ],
                },
            },
        )
        assert "✓" in result
        assert "✗" in result

    def test_variance_stopped(self):
        """variance 模块关闭 → 显示已停用。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={"variance": {"items": []}},
        )
        assert "已停用" in result


class TestCompactBackwardCompatibility:
    """compact 模式兼容性测试 — 输出必须与当前完全一致。"""

    def test_compact_output_unchanged(self):
        """compact 模式输出格式与当前一致。"""
        # 模拟典型 debug 场景
        parts = [
            "🕐 现在是 2026年5月21日 星期四 03:03",
            "📝 测试规则1",
            "📝 测试规则2",
            "📏 消息较短",
            "📊 [表达向量] care:2 intimacy:0 work:0 | 第 10 轮",
            "🦊 狐尾轻轻摆动",
        ]
        result = injector._debug_summary(
            {"time": True, "static_rules": True, "dynamic": {"time_slots": True, "turn_stage": False, "keyword": True}, "variance": True, "memory": False, "kanban": True, "debug": True},
            parts,
            var_count=1,
        )
        assert "🔧 [Debug] 本轮注入:" in result
        assert "① 🕐 时间已注入" in result
        assert "② 📜" in result
        assert "③ ⚡" in result
        assert "④a" in result
        assert "④b" in result
        assert "④ 🎲" in result
        assert "⑤ 🧠 已停用" in result
        assert "⑥ 📋" in result
