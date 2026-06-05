"""Tests for injection rule translation (narrative assembly) — SPEC-009."""

from unittest.mock import patch

import pytest

import injector as injector
from injector import (
    _assemble_narrative,
    _clean_variance_item,
)


class TestAssembleNarrative:
    """_assemble_narrative() 单元测试 — T-01~T-05, T-08."""

    def test_T01_all_data_complete(self):
        """T-01: 全部数据完整 → 五个段落全部输出。"""
        result = _assemble_narrative(
            weekday="周四",
            current_time="20:29",
            time_slot_desc="晚间——用户这段时间一般会继续工作，保持高效和温暖的工作节奏即可。",
            weather_desc=None,
            today_turn=30,
            turn_stage_hint=None,
            top3=[("工作投入", 16, "→"), ("亲密温度", 5, "→")],
            variance_items=["蓬松的大狐尾", "女仆礼仪,温柔感强"],
            fixed_rules=["感知表达自然化", "核心态度", "永远不主动结束对话"],
        )
        assert "现在时间是：周四，20:29" in result
        assert "晚间——用户这段时间一般会继续工作" in result
        assert "这是今天的第30轮对话" in result
        assert "当前用户状态是" in result
        assert "工作投入（→）" in result
        assert "亲密温度（→）" in result
        assert "蓬松的大狐尾" in result
        assert "女仆礼仪" in result
        assert "感知表达自然化" in result
        assert "核心态度" in result

    def test_T02_empty_time_slot_desc(self):
        """T-02: time_slot_desc 为空 → 跳过时段描述，时间仍输出。"""
        result = _assemble_narrative(
            weekday="周四",
            current_time="20:29",
            time_slot_desc="",
            weather_desc=None,
            today_turn=0,
            turn_stage_hint=None,
            top3=[],
            variance_items=[],
            fixed_rules=[],
        )
        assert "现在时间是：周四，20:29。" in result
        assert "这是今天的第" not in result

    def test_T03_top3_all_zero(self):
        """T-03: top3 为空（所有维度为 0）→ 跳过表达向量段落。"""
        result = _assemble_narrative(
            weekday="周四",
            current_time="20:29",
            time_slot_desc="晚间——工作时间。",
            weather_desc=None,
            today_turn=5,
            turn_stage_hint=None,
            top3=[],
            variance_items=["蓬松的大狐尾"],
            fixed_rules=["感知表达自然化"],
        )
        assert "现在时间是" in result
        assert "这是今天的第5轮对话" in result
        assert "当前用户状态是" not in result
        assert "蓬松的大狐尾" in result

    def test_T04_empty_variance_items(self):
        """T-04: variance_items 为空 → 跳过随机变化段落。"""
        result = _assemble_narrative(
            weekday="周四",
            current_time="20:29",
            time_slot_desc="晚间——工作时间。",
            weather_desc=None,
            today_turn=5,
            turn_stage_hint=None,
            top3=[("工作投入", 16, "→")],
            variance_items=[],
            fixed_rules=["感知表达自然化"],
        )
        assert "使用" not in result
        assert "当前用户状态是" in result

    def test_T05_only_one_dimension(self):
        """T-05: 只有 1 个维度有值 → 只输出有值的维度。"""
        result = _assemble_narrative(
            weekday="周四",
            current_time="20:29",
            time_slot_desc="晚间——工作时间。",
            weather_desc=None,
            today_turn=5,
            turn_stage_hint=None,
            top3=[("工作投入", 16, "→")],
            variance_items=[],
            fixed_rules=["感知表达自然化"],
        )
        assert "工作投入（→）" in result
        assert "当前用户状态是工作投入（→）。" in result

    def test_T08_today_turn_zero(self):
        """T-08: today_turn=0 → 跳过轮数段落。"""
        result = _assemble_narrative(
            weekday="周四",
            current_time="20:29",
            time_slot_desc="晚间——工作时间。",
            weather_desc=None,
            today_turn=0,
            turn_stage_hint=None,
            top3=[("工作投入", 16, "→")],
            variance_items=[],
            fixed_rules=[],
        )
        assert "现在时间是" in result
        assert "这是今天的第" not in result
        assert "当前用户状态是" in result

    def test_turn_stage_hint_appended(self):
        """turn_stage_hint 不为 None 时追加到轮数段落。"""
        result = _assemble_narrative(
            weekday="周四",
            current_time="20:29",
            time_slot_desc="",
            weather_desc=None,
            today_turn=100,
            turn_stage_hint="可以使用更亲密的表达",
            top3=[],
            variance_items=[],
            fixed_rules=[],
        )
        assert "可以使用更亲密的表达" in result
        assert "这是今天的第100轮对话" in result

    def test_no_time_slot_no_turn_no_top3_no_variance_no_rules(self):
        """全空输入 → 仅输出时间。"""
        result = _assemble_narrative(
            weekday="周四",
            current_time="20:29",
            time_slot_desc="",
            weather_desc=None,
            today_turn=0,
            turn_stage_hint=None,
            top3=[],
            variance_items=[],
            fixed_rules=[],
        )
        assert result == "现在时间是：周四，20:29。"


class TestTranslateIntegration:
    """translate 模式集成测试 — T-06."""

    def test_T06_translate_false_unchanged(self):
        """T-06: translate: false（默认）→ 保持旧格式输出。"""
        config = {
            "modules": {"translate": False},
            "time": {"format": "cn_full"},
            "context": {"rules": ["测试规则"]},
        }
        with patch("injector._load_config", return_value=config):
            result = injector.inject_context(
                session_id="test",
                user_message="你好",
                conversation_history=[],
                is_first_turn=True,
                model="test",
                platform="test",
            )
        assert result is not None
        assert "🕐" in result["context"]
        assert "测试规则" in result["context"]
        assert "现在时间是" not in result["context"]
        assert "当前用户状态是" not in result["context"]

    def test_translate_true_uses_narrative(self):
        """translate: true → context 以 narrative 格式开头。"""
        config = {
            "modules": {"translate": True},
            "time": {},
            "context": {"rules": ["🌿 感知表达自然化"]},
            "variance": {},
        }
        with patch("injector._load_config", return_value=config):
            result = injector.inject_context(
                session_id="test",
                user_message="你好",
                conversation_history=[],
                is_first_turn=True,
                model="test",
                platform="test",
            )
        assert result is not None
        assert "现在时间是" in result["context"]
        assert "当前用户状态是" not in result["context"]  # ev 未启用
        assert "感知表达自然化" in result["context"]

    def test_translate_debug_includes_narrative(self):
        """translate + debug 同时开启 → debug 块末尾包含转译结果。"""
        config = {
            "modules": {"translate": True, "debug": True},
            "time": {},
            "context": {"rules": ["测试规则"]},
            "variance": {},
            "debug": {"detail": "compact"},
        }
        with patch("injector._load_config", return_value=config):
            result = injector.inject_context(
                session_id="test",
                user_message="你好",
                conversation_history=[],
                is_first_turn=True,
                model="test",
                platform="test",
            )
        assert result is not None
        debug_block = injector._PENDING_DEBUG_BLOCK
        assert debug_block is not None
        assert "🔮 [转译结果]" in debug_block
        assert "现在时间是" in debug_block
        assert "测试规则" in debug_block


class TestCleanVarianceItem:
    """_clean_variance_item() 单元测试。"""

    def test_removes_emoji_prefix(self):
        """去除 emoji 前缀。"""
        assert _clean_variance_item("🦊 蓬松的大狐尾") == "蓬松的大狐尾"
        assert _clean_variance_item("💬 温柔感强") == "温柔感强"

    def test_suffix_preserved(self):
        """「的肢体语言表达」后缀不再被剥离——保留原样。"""
        result = _clean_variance_item("蓬松的大狐尾的肢体语言表达")
        assert result == "蓬松的大狐尾的肢体语言表达"

    def test_no_change_when_clean(self):
        """无需清理时原样返回。"""
        assert _clean_variance_item("蓬松的大狐尾") == "蓬松的大狐尾"
        assert _clean_variance_item("温柔感强") == "温柔感强"

    def test_emoji_removed_suffix_preserved(self):
        """去除 emoji 前缀，保留后缀。"""
        result = _clean_variance_item("🦊 蓬松的大狐尾的肢体语言表达")
        assert result == "蓬松的大狐尾的肢体语言表达"


class TestExpressionVectorTop3:
    """expression_vector.py top3() 方法测试。"""

    def test_top3_basic(self):
        """基本功能：排序后返回 top 3，跳过 0 分维度。"""
        from expression_vector import _ExpressionVector

        ev = _ExpressionVector(
            {"dimensions": {
                "work": ["code"],
                "play": ["game"],
                "intimacy": ["warm"],
                "care": ["help"],
            }},
            "test",
        )
        ev.vectors = {"work": 16.0, "play": 2.0, "intimacy": 7.0, "care": 0.0}
        result = ev.top3(n=3, trend=False)
        assert len(result) == 3
        assert result[0][0] == "工作投入"
        assert result[0][1] == 16
        assert result[1][0] == "亲密温度"
        assert result[2][0] == "轻松玩乐"

    def test_top3_with_trend(self):
        """趋势计算：比较上轮值。"""
        from expression_vector import _ExpressionVector

        ev = _ExpressionVector(
            {"dimensions": {"work": ["code"]}},
            "test",
        )
        ev.vectors = {"work": 16.0}
        ev.vector_history.append({"vectors": {"work": 10.0}})
        result = ev.top3(n=1, trend=True)
        assert result[0][2] == "↑"

    def test_top3_trend_down(self):
        """趋势下降。"""
        from expression_vector import _ExpressionVector

        ev = _ExpressionVector(
            {"dimensions": {"work": ["code"]}},
            "test",
        )
        ev.vectors = {"work": 5.0}
        ev.vector_history.append({"vectors": {"work": 10.0}})
        result = ev.top3(n=1, trend=True)
        assert result[0][2] == "↓"

    def test_top3_trend_flat(self):
        """趋势平稳。"""
        from expression_vector import _ExpressionVector

        ev = _ExpressionVector(
            {"dimensions": {"work": ["code"]}},
            "test",
        )
        ev.vectors = {"work": 10.0}
        ev.vector_history.append({"vectors": {"work": 10.0}})
        result = ev.top3(n=1, trend=True)
        assert result[0][2] == "→"

    def test_top3_less_than_n(self):
        """维度少于 n 个时返回实际数量。"""
        from expression_vector import _ExpressionVector

        ev = _ExpressionVector(
            {"dimensions": {"work": ["code"]}},
            "test",
        )
        ev.vectors = {"work": 16.0}
        result = ev.top3(n=5, trend=False)
        assert len(result) == 1

    def test_top3_no_history_trend(self):
        """无历史记录时趋势基于 0.0 比较。"""
        from expression_vector import _ExpressionVector

        ev = _ExpressionVector(
            {"dimensions": {"work": ["code"]}},
            "test",
        )
        ev.vectors = {"work": 16.0}
        result = ev.top3(n=1, trend=True)
        assert result[0][2] == "↑"

    def test_top3_zero_skipped(self):
        """分值为 0 的维度不返回。"""
        from expression_vector import _ExpressionVector

        ev = _ExpressionVector(
            {"dimensions": {"work": ["code"], "play": ["game"]}},
            "test",
        )
        ev.vectors = {"work": 0.0, "play": 0.0}
        result = ev.top3(n=3, trend=False)
        assert len(result) == 0
