"""Tests for expression vector — _ExpressionVector class.

Covers: update algorithm, reset strategies, disk persistence,
injection formatting, and edge cases.
Per SPEC-002 §10.2 ~ §10.5: TC-IDs EV-01~14, RS-01~06, PERS-01~08, FMT-01~03.
"""

import json
import logging
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from expression_vector import (
    _ExpressionVector,
    _KeywordMatcher,
    _NEGATION_WORDS,
    _DIMENSION_FILES,
    _SYNONYMS_FILE,
    _RELOAD_KEYWORDS,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def ev_cfg_basic():
    """基础 3 维度配置。"""
    return {
        "dimensions": {
            "work": ["代码", "架构", "Bug", "PR", "测试"],
            "future": ["愿景", "未来", "规划"],
            "intimacy": ["陪伴", "累了", "温暖"],
        },
        "score_rules": {
            "work": [1, -0.5, 1],
            "future": [1, -1, 1],
            "intimacy": [1, -0.5, 3],
        },
        "reset": "session",
        "storage_path": "",  # 用 tmpdir 替换
    }


@pytest.fixture
def tmp_ev_path(tmp_path):
    """临时磁盘路径。"""
    return tmp_path / "expression_vector.json"


@pytest.fixture
def ev(ev_cfg_basic, tmp_ev_path):
    """基础配置 + 临时路径的 _ExpressionVector 实例。"""
    cfg = {**ev_cfg_basic, "storage_path": str(tmp_ev_path)}
    return _ExpressionVector(cfg)


# ── TestUpdateAlgorithm: EV-01 ~ EV-14 ────────────────────────────────────


class TestUpdateAlgorithm:
    """EV-01 ~ EV-14: update() 核心算法测试。"""

    def test_EV01_single_dimension_hit(self, ev):
        """EV-01: 单维度命中累加。msg='写代码' → work += 1×1 = 1.0"""
        ev.update("写代码", "s1")
        assert ev.vectors["work"] == 1.0

    def test_EV02_single_dimension_miss(self, ev):
        """EV-02: 单维度未命中衰减→0。msg='今天天气不错' → work += -0.5×1 → max(0, -0.5) = 0.0"""
        ev.update("今天天气不错", "s1")
        assert ev.vectors["work"] == 0.0

    def test_EV03_multi_dimension_mixed_hit(self, ev):
        """EV-03: 多维度混合命中。msg 含 work+intimacy 关键词。"""
        ev.update("写代码好累了想休息", "s1")
        assert ev.vectors["work"] == 1.0      # 命中 "代码"
        assert ev.vectors["future"] == 0.0     # 未命中 → max(0, -1) = 0
        assert ev.vectors["intimacy"] == 3.0   # 命中 "累了" × weight 3

    def test_EV04_weight_effect(self):
        """EV-04: 权重 ×3 生效。intimacy: hit=1, weight=3 → 3.0"""
        cfg = {
            "dimensions": {"intimacy": ["温暖"]},
            "score_rules": {"intimacy": [1, -0.5, 3]},
            "storage_path": "/tmp/nonexistent_ev.json",
        }
        ev = _ExpressionVector(cfg)
        ev.update("好温暖", "s1")
        assert ev.vectors["intimacy"] == 3.0  # 1 × 3

    def test_EV05_score_never_below_zero(self, ev):
        """EV-05: 所有维度分数 ≥ 0。"""
        ev.update("今天天气不错", "s1")
        for dim in ev.vectors:
            assert ev.vectors[dim] >= 0.0

    def test_EV06_consecutive_hits_accumulate(self, ev):
        """EV-06: 连续 3 次命中 work → 1+0.95+0.9025=2.8525（含 0.95 衰减）。"""
        for _ in range(3):
            ev.update("写代码", "s1")
        assert ev.vectors["work"] == pytest.approx(2.8525)

    def test_EV07_hit_then_miss_mix(self, ev):
        """EV-07: 2 命中 + 3 未命中，含 0.95 衰减 → 约 0.2456。"""
        ev.update("写代码", "s1")  # work: 1.0
        ev.update("写代码", "s1")  # work: 0.95 + 1.0 = 1.95
        ev.update("天气真好", "s1")  # work: 1.95*0.95 + (-0.5) = 1.3525
        ev.update("去散步", "s1")    # work: 1.3525*0.95 + (-0.5) = 0.784875
        ev.update("好开心", "s1")    # work: 0.784875*0.95 + (-0.5) = 0.2456
        assert ev.vectors["work"] == pytest.approx(0.2456, rel=1e-3)

    def test_EV08_variable_dimension_count(self):
        """EV-08: 4 维配置，维度数量可变。"""
        cfg = {
            "dimensions": {"a": ["x"], "b": ["y"], "c": ["z"], "d": ["w"]},
            "storage_path": "/tmp/nonexistent_ev.json",
        }
        ev = _ExpressionVector(cfg)
        ev.update("x y z w", "s1")
        assert len(ev.vectors) == 4
        for dim in ("a", "b", "c", "d"):
            assert ev.vectors[dim] == 1.0

    def test_EV09_missing_score_rules(self):
        """EV-09: score_rules 缺失 work 维度→默认 [1, -0.5, 1]。"""
        cfg = {
            "dimensions": {"work": ["代码"]},
            "storage_path": "/tmp/nonexistent_ev.json",
        }
        ev = _ExpressionVector(cfg)
        ev.update("写代码", "s1")
        assert ev.vectors["work"] == 1.0  # 默认 hit=1, weight=1

    def test_EV10_malformed_score_rules(self):
        """EV-10: score_rules 格式错误→默认值。"""
        cfg = {
            "dimensions": {"work": ["代码"]},
            "score_rules": {"work": [1]},  # 长度不足
            "storage_path": "/tmp/nonexistent_ev.json",
        }
        ev = _ExpressionVector(cfg)
        ev.update("写代码", "s1")
        assert ev.vectors["work"] == 1.0  # 回退默认

    def test_EV11_empty_message(self, ev):
        """EV-11: 空消息→全部未命中。"""
        ev.update("", "s1")
        for dim in ev.vectors:
            assert ev.vectors[dim] == 0.0

    def test_EV12_none_message(self, ev):
        """EV-12: None 消息→全部未命中，不抛异常。"""
        ev.update(None, "s1")
        for dim in ev.vectors:
            assert ev.vectors[dim] == 0.0

    def test_EV13_case_insensitive(self):
        """EV-13: 大小写不敏感。keywords=['Bug'], msg='fix this bug'。"""
        cfg = {
            "dimensions": {"work": ["Bug"]},
            "storage_path": "/tmp/nonexistent_ev.json",
        }
        ev = _ExpressionVector(cfg)
        ev.update("fix this bug", "s1")
        assert ev.vectors["work"] == 1.0

    def test_EV14_substring_match(self, ev):
        """EV-14: 关键词为子串也命中。msg='架构师说...' 含 '架构'。"""
        ev.update("架构师说...", "s1")
        assert ev.vectors["work"] == 1.0


# ── TestResetStrategy: RS-01 ~ RS-06 ──────────────────────────────────────


class TestResetStrategy:
    """RS-01 ~ RS-06: should_reset() 重置策略测试。"""

    def test_RS01_session_same_session_no_reset(self, ev):
        """RS-01: session 策略，同一 session 不清零。两次命中含 0.95 衰减→1.95。"""
        ev.update("写代码", "s1")  # work: 1.0
        assert ev.vectors["work"] == 1.0
        ev.update("写代码", "s1")      # 同 session，不清零 → work: 0.95+1.0=1.95
        assert ev.vectors["work"] == 1.95

    def test_RS02_session_new_session_resets(self, ev):
        """RS-02: session 策略，新 session 清零后重新累积。"""
        ev.update("写代码", "s1")
        assert ev.vectors["work"] == 1.0
        # 切换 session → 清零后重新累加
        ev.update("写代码", "s2")
        assert ev.vectors["work"] == 1.0  # 从 0 重新开始

    def test_RS03_daily_same_day_no_reset(self, tmp_ev_path):
        """RS-03: daily 策略，同日不清零。两次命中含 0.95 衰减→1.95。"""
        cfg = {
            "dimensions": {"work": ["代码"]},
            "score_rules": {"work": [1, -0.5, 1, 0.95]},
            "reset": "daily",
            "storage_path": str(tmp_ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.update("代码", "s1")
        ev.update("代码", "s1")
        assert ev.vectors["work"] == 1.95

    def test_RS04_daily_cross_day_resets(self, tmp_ev_path):
        """RS-04: daily 策略，跨日清零。"""
        cfg = {
            "dimensions": {"work": ["代码"]},
            "reset": "daily",
            "storage_path": str(tmp_ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.update("代码", "s1")
        assert ev.vectors["work"] == 1.0

        # 模拟跨日：手动设置 _last_updated 为昨天，保存后重新加载
        yesterday = datetime.now() - timedelta(days=1)
        ev._last_updated = yesterday
        ev.save()

        ev2 = _ExpressionVector(cfg)
        ev2.load()
        # 加载后发现 last_updated 是昨天 → daily 重置
        ev2.update("代码", "s1")
        assert ev2.vectors["work"] == 1.0  # 从 0 重新开始

    def test_RS05_none_never_resets(self, tmp_ev_path):
        """RS-05: none 策略，永不清零，跨 session 持续累积。"""
        cfg = {
            "dimensions": {"work": ["代码"]},
            "score_rules": {"work": [1, -0.5, 1, 0.95]},
            "reset": "none",
            "storage_path": str(tmp_ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.update("代码", "s1")
        ev.save()

        ev2 = _ExpressionVector(cfg)
        ev2.load()
        ev2.update("代码", "s2")  # 新 session → none 策略不清零
        assert ev2.vectors["work"] == 1.95

    def test_RS06_invalid_reset_value(self):
        """RS-06: 非法 reset 值→回退为 "session"。"""
        cfg = {
            "dimensions": {"work": ["代码"]},
            "reset": "weekly",
            "storage_path": "/tmp/nonexistent_ev.json",
        }
        ev = _ExpressionVector(cfg)
        assert ev.reset_policy == "session"


# ── TestDiskPersistence: PERS-01 ~ PERS-08 ────────────────────────────────


class TestDiskPersistence:
    """PERS-01 ~ PERS-08: load() / save() 磁盘持久化测试。"""

    def test_PERS01_save_load_roundtrip(self, ev, tmp_ev_path):
        """PERS-01: save + load 往返一致。"""
        ev.update("代码", "s1")
        ev.save()
        ev2 = _ExpressionVector({
            "dimensions": ev.dimensions,
            "score_rules": {"work": [1, -0.5, 1]},
            "storage_path": str(tmp_ev_path),
        })
        ev2.load()
        assert ev2.vectors["work"] == ev.vectors["work"]

    def test_PERS02_load_missing_file(self, tmp_ev_path):
        """PERS-02: 文件不存在→初始零值，不抛异常。"""
        cfg = {"dimensions": {"work": ["代码"]}, "storage_path": str(tmp_ev_path)}
        ev = _ExpressionVector(cfg)
        ev.load()
        assert ev.vectors["work"] == 0.0

    def test_PERS03_load_corrupt_json(self, tmp_ev_path):
        """PERS-03: JSON 格式错误→初始零值。"""
        tmp_ev_path.write_text("not json at all", encoding="utf-8")
        cfg = {"dimensions": {"work": ["代码"]}, "storage_path": str(tmp_ev_path)}
        ev = _ExpressionVector(cfg)
        ev.load()
        assert ev.vectors["work"] == 0.0

    def test_PERS04_load_version_mismatch(self, tmp_ev_path):
        """PERS-04: version 不匹配→初始零值。"""
        tmp_ev_path.write_text(
            json.dumps({"version": 99, "vectors": {"work": 5.0}}),
            encoding="utf-8",
        )
        cfg = {"dimensions": {"work": ["代码"]}, "storage_path": str(tmp_ev_path)}
        ev = _ExpressionVector(cfg)
        ev.load()
        assert ev.vectors["work"] == 0.0

    def test_PERS05_load_new_dimension_added(self, tmp_ev_path):
        """PERS-05: 配置新增维度→新维度初始 0，已有维度保留。"""
        cfg = {"dimensions": {"work": ["代码"]}, "score_rules": {"work": [1, -0.5, 1, 0.95]}, "storage_path": str(tmp_ev_path)}
        ev = _ExpressionVector(cfg)
        ev.update("写代码", "s1")
        ev.update("写代码", "s1")
        ev.save()

        cfg2 = {
            "dimensions": {"work": ["代码"], "future": ["愿景"]},
            "score_rules": {"work": [1, -0.5, 1, 0.95], "future": [1, -1, 1, 0.95]},
            "storage_path": str(tmp_ev_path),
        }
        ev2 = _ExpressionVector(cfg2)
        ev2.load()
        assert ev2.vectors["work"] == 1.95   # 保留（含 0.95 衰减）
        assert ev2.vectors["future"] == 0.0  # 新维度初始 0

    def test_PERS06_load_removed_dimension(self, tmp_ev_path):
        """PERS-06: 配置删除维度→已删维度不恢复。"""
        cfg = {
            "dimensions": {"work": ["代码"], "future": ["愿景"]},
            "storage_path": str(tmp_ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.update("代码愿景", "s1")
        ev.save()

        cfg2 = {"dimensions": {"work": ["代码"]}, "storage_path": str(tmp_ev_path)}
        ev2 = _ExpressionVector(cfg2)
        ev2.load()
        assert "future" not in ev2.vectors

    def test_PERS07_save_to_readonly_path(self):
        """PERS-07: 磁盘写入失败→静默降级，不抛异常。"""
        cfg = {
            "dimensions": {"work": ["代码"]},
            "storage_path": "/nonexistent/deep/path/ev.json",
        }
        ev = _ExpressionVector(cfg)
        ev.update("代码", "s1")
        ev.save()  # 不抛异常

    def test_PERS08_save_creates_parent_dir(self, tmp_path):
        """PERS-08: 父目录不存在→save() 自动创建。"""
        new_path = tmp_path / "sub" / "dir" / "ev.json"
        cfg = {"dimensions": {"work": ["代码"]}, "storage_path": str(new_path)}
        ev = _ExpressionVector(cfg)
        ev.update("代码", "s1")
        ev.save()
        assert new_path.is_file()


# ── TestFormatInject: FMT-01 ~ FMT-03 ────────────────────────────────────


class TestFormatInject:
    """FMT-01 ~ FMT-03: format_inject() 格式化输出测试。"""

    def test_FMT01_standard_format(self, ev):
        """FMT-01: 标准格式，维度按字母序。"""
        ev.update("代码陪伴愿景", "s1")
        result = ev.format_inject(22)
        # 按字母序: future < intimacy < work
        assert "📊 [表达向量]" in result
        assert "future:" in result
        assert "intimacy:" in result
        assert "work:" in result
        assert "| 第 22 轮" in result
        assert result.index("future:") < result.index("intimacy:")
        assert result.index("intimacy:") < result.index("work:")

    def test_FMT02_all_zeros(self, ev):
        """FMT-02: 全零值仍显示（0 具有信号意义）。"""
        result = ev.format_inject(1)
        assert "future:0" in result
        assert "intimacy:0" in result
        assert "work:0" in result
        assert "| 第 1 轮" in result

    def test_FMT03_float_rounding(self, ev):
        """FMT-03: 浮点值四舍五入。含 0.95 衰减→ work=1.3525 → int(round(1.3525)) = 1。"""
        ev.update("代码", "s1")    # work: 1.0
        ev.update("代码", "s1")    # work: 0.95 + 1.0 = 1.95
        ev.update("天气好", "s1")  # work: 1.95*0.95 + (-0.5) = 1.3525
        assert ev.vectors["work"] == pytest.approx(1.3525)
        result = ev.format_inject(1)
        assert "work:1" in result  # round(1.3525) = 1


# ── TestTraceLogging ─────────────────────────────────────────────────────


class TestTraceLogging:
    """trace 日志：update() 前后记录向量变化（DEBUG 级别）。"""

    def test_trace_logging(self, caplog, ev):
        """update 后 logger 在 DEBUG 级别输出变化的维度。"""
        caplog.set_level(logging.DEBUG, logger="hermes_tool_slimmer.expression_vector")

        ev.update("写代码", "s1")

        # 应包含 [EV] 前缀和变化的维度
        assert "[EV] update:" in caplog.text
        assert "session=s1" in caplog.text
        assert "work:" in caplog.text

    def test_trace_logging_no_change(self, caplog, ev):
        """空消息→所有维度从 0 衰减为 0（不变）→ 无日志。"""
        caplog.set_level(logging.DEBUG, logger="hermes_tool_slimmer.expression_vector")

        ev.update("", "s1")

        # 从 0 到 0，没有真正变化，不应输出日志
        assert "[EV] update:" not in caplog.text

    def test_trace_logging_level_respected(self, caplog, ev):
        """日志级别高于 DEBUG 时不输出。"""
        caplog.set_level(logging.INFO, logger="hermes_tool_slimmer.expression_vector")

        ev.update("写代码", "s1")

        assert "[EV] update:" not in caplog.text


# ── TestVectorHistory ────────────────────────────────────────────────────


class TestVectorHistory:
    """vector_history 持久化：追加 + 500 上限 + 往返恢复。"""

    def test_vector_history_appended_on_save(self, ev, tmp_ev_path):
        """每次 save() 追加一条历史记录。"""
        ev.update("代码", "s1")
        ev.save()

        ev.update("愿景", "s1")
        ev.save()

        # 重新加载，验证历史
        ev2 = _ExpressionVector({
            "dimensions": ev.dimensions,
            "score_rules": {"work": [1, -0.5, 1], "future": [1, -1, 1], "intimacy": [1, -0.5, 3]},
            "storage_path": str(tmp_ev_path),
        })
        ev2.load()
        assert len(ev2.vector_history) == 2
        assert ev2.vector_history[0]["turn"] == 1
        assert ev2.vector_history[1]["turn"] == 2
        assert ev2.vector_history[0]["session_id"] == "s1"
        assert "vectors" in ev2.vector_history[0]
        assert "time" in ev2.vector_history[0]

    def test_vector_history_500_limit(self, tmp_ev_path):
        """超过 500 条时，只保留最近的 500 条。"""
        cfg = {
            "dimensions": {"work": ["代码"]},
            "storage_path": str(tmp_ev_path),
        }
        ev = _ExpressionVector(cfg)

        for i in range(600):
            ev.update("代码", "s1")
            ev.save()

        ev2 = _ExpressionVector(cfg)
        ev2.load()
        assert len(ev2.vector_history) == 500
        # 最早应该是 turn 101（前 100 条被丢弃）
        assert ev2.vector_history[0]["turn"] == 101
        assert ev2.vector_history[-1]["turn"] == 600

    def test_vector_history_save_load_roundtrip(self, ev, tmp_ev_path):
        """历史记录 save+load 往返一致。"""
        ev.update("代码", "s1")
        ev.save()
        ev.update("愿景", "s1")
        ev.save()

        ev2 = _ExpressionVector({
            "dimensions": ev.dimensions,
            "score_rules": {"work": [1, -0.5, 1], "future": [1, -1, 1], "intimacy": [1, -0.5, 3]},
            "storage_path": str(tmp_ev_path),
        })
        ev2.load()
        assert ev2.vector_history[0]["vectors"]["work"] == 1.0
        assert ev2.vector_history[1]["vectors"]["future"] == 1.0
        assert ev2._turn_counter == 2


# ── TestVectorHistoryBackwardCompat ──────────────────────────────────────


class TestVectorHistoryBackwardCompat:
    """向后兼容：旧数据（无 vector_history 字段）可正常加载。"""

    def test_vector_history_backward_compat(self, tmp_ev_path):
        """旧格式 JSON（无 vector_history/turn_counter）初始化空历史。"""
        old_data = {
            "version": 1,
            "session_id": "old_sess",
            "last_updated": "2026-05-20T10:00:00",
            "vectors": {"work": 5.0},
        }
        tmp_ev_path.write_text(
            json.dumps(old_data, ensure_ascii=False),
            encoding="utf-8",
        )

        cfg = {
            "dimensions": {"work": ["代码"]},
            "storage_path": str(tmp_ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.load()

        # 旧数据正常加载
        assert ev.vectors["work"] == 5.0
        assert ev._session_id == "old_sess"
        # 无 history 字段→初始化为空
        assert len(ev.vector_history) == 0
        assert ev._turn_counter == 0


# ── TestBackgroundMessageFilter ────────────────────────────────────────────

from expression_vector import _is_background_message


class TestBackgroundMessageFilter:
    """消息过滤判定函数测试。"""

    def test_BG01_prefix_match(self):
        """BG-01: 前缀命中 → True"""
        msg = "[Kai.Xu] [IMPORTANT: Background process proc_abc completed ..."
        assert _is_background_message(msg) is True

    def test_BG02_density_match(self):
        """BG-02: 长度>500 + ≥2特征词 → True"""
        msg = "x" * 200 + "\nclaude -p 'test'\n" + "x" * 200 + "\nCommand: echo\n" + "x" * 200
        assert len(msg) > 500
        assert _is_background_message(msg) is True

    def test_BG03_boundary_exactly_two(self):
        """BG-03: 恰好2个特征词 → True（密度边界）"""
        msg = "x" * 300 + "\nclaude -p 'test'\nexit code: 0\n" + "x" * 300
        assert _is_background_message(msg) is True

    def test_BG04_normal_message(self):
        """BG-04: 正常消息 → False"""
        msg = "早上好～"
        assert _is_background_message(msg) is False

    def test_BG05_long_normal_message(self):
        """BG-05: 长但无特征词 → False"""
        msg = "代码" * 300  # 600 chars
        assert len(msg) > 500
        assert _is_background_message(msg) is False

    def test_BG06_single_signature_not_enough(self):
        """BG-06: 长度>500 但仅1个特征词 → False"""
        msg = "x" * 400 + "\nCommand: echo hello\n" + "x" * 200
        assert _is_background_message(msg) is False

    def test_BG07_short_background_prefix(self):
        """BG-07: 前缀命中无视长度限制"""
        msg = "[IMPORTANT: Background process done"
        assert _is_background_message(msg) is True

    def test_BG08_empty_message(self):
        """BG-08: 空消息 → False"""
        assert _is_background_message("") is False

    def test_BG09_skill_injection(self):
        """BG-09: [IMPORTANT: Skill obsidian injected 15000 chars... → True"""
        msg = "[IMPORTANT: The user has invoked the \"obsidian\" skill, indicating"
        assert _is_background_message(msg) is True

    def test_BG10_important_other_type(self):
        """BG-10: [IMPORTANT: 其他系统转发类型 → True"""
        msg = "[IMPORTANT: System notification — gateway restart required"
        assert _is_background_message(msg) is True


# ── TestKeywordCounting ────────────────────────────────────────────────────


class TestKeywordCounting:
    """词边界匹配 + 去重测试。"""

    def test_KW01_short_ascii_word_boundary_no_false_match(self, tmp_path):
        """KW-01: 'PR' 不匹配 'process approach'"""
        ev_path = tmp_path / "ev_kw1.json"
        cfg = {
            "dimensions": {"work": ["PR"]},
            "score_rules": {"work": [1, -0.5, 1]},
            "reset": "session",
            "storage_path": str(ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.update("process approach", "s1")
        assert ev.vectors["work"] == 0.0

    def test_KW02_short_ascii_word_boundary_true_match(self, tmp_path):
        """KW-02: 'PR' 匹配独立词 'review the PR please'"""
        ev_path = tmp_path / "ev_kw2.json"
        cfg = {
            "dimensions": {"work": ["PR"]},
            "score_rules": {"work": [1, -0.5, 1]},
            "reset": "session",
            "storage_path": str(ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.update("review the PR please", "s1")
        assert ev.vectors["work"] == 1.0

    def test_KW03_git_not_matches_legitimate(self, tmp_path):
        """KW-03: 'git' 不匹配 'legitimate'"""
        ev_path = tmp_path / "ev_kw3.json"
        cfg = {
            "dimensions": {"work": ["git"]},
            "score_rules": {"work": [1, -0.5, 1]},
            "reset": "session",
            "storage_path": str(ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.update("legitimate concern", "s1")
        assert ev.vectors["work"] == 0.0

    def test_KW04_chinese_still_substring(self, tmp_path):
        """KW-04: 中文仍用子串匹配"""
        ev_path = tmp_path / "ev_kw4.json"
        cfg = {
            "dimensions": {"work": ["代码"]},
            "score_rules": {"work": [1, -0.5, 1]},
            "reset": "session",
            "storage_path": str(ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.update("写代码测试", "s1")
        assert ev.vectors["work"] == 1.0

    def test_KW05_long_ascii_still_substring(self, tmp_path):
        """KW-05: 长英文短语(>4) 仍用子串匹配"""
        ev_path = tmp_path / "ev_kw5.json"
        cfg = {
            "dimensions": {"work": ["hermes-persona"]},
            "score_rules": {"work": [1, -0.5, 1]},
            "reset": "session",
            "storage_path": str(ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.update("hermes-persona 插件", "s1")
        assert ev.vectors["work"] == 1.0

    def test_KW06_duplicate_keywords_deduped(self, tmp_path):
        """KW-06: 重复关键词自动去重"""
        ev_path = tmp_path / "ev_kw6.json"
        cfg = {
            "dimensions": {"work": ["修复", "修复", "代码"]},
            "score_rules": {"work": [1, -0.5, 1]},
            "reset": "session",
            "storage_path": str(ev_path),
        }
        ev = _ExpressionVector(cfg)
        # 关键词列表应去重
        assert ev.dimensions["work"] == ["修复", "代码"]
        ev.update("修复了一个Bug，修复了测试", "s1")
        # "修复" 出现 2 次，但去重后只计 1 个关键词，hit_count = 2
        assert ev.vectors["work"] == 2.0


# ── TestDecay ──────────────────────────────────────────────────────────────


class TestDecay:
    """衰减机制测试。"""

    def test_DC01_decay_applied_before_hit(self, tmp_path):
        """DC-01: 衰减先于命中执行。work=10 → *0.5 → 5 + 命中1 = 6"""
        ev_path = tmp_path / "ev_dc1.json"
        cfg = {
            "dimensions": {"work": ["代码"]},
            "score_rules": {"work": [1, -0.5, 1, 0.5]},
            "reset": "session",
            "storage_path": str(ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.vectors["work"] = 10.0
        ev.update("写代码", "s1")
        assert ev.vectors["work"] == 6.0  # 10*0.5 + 1

    def test_DC02_decay_with_miss(self, tmp_path):
        """DC-02: 衰减 + 未命中：work=10 → *0.5 → 5 + (-0.5) = 4.5"""
        ev_path = tmp_path / "ev_dc2.json"
        cfg = {
            "dimensions": {"work": ["代码"]},
            "score_rules": {"work": [1, -0.5, 1, 0.5]},
            "reset": "session",
            "storage_path": str(ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.vectors["work"] = 10.0
        ev.update("天气不错", "s1")
        assert ev.vectors["work"] == 4.5

    def test_DC03_default_decay_is_095(self):
        """DC-03: 三元组自动补齐 decay_factor=0.95"""
        cfg = {
            "dimensions": {"work": ["代码"]},
            "score_rules": {"work": [1, -0.5, 1]},  # 旧格式
            "reset": "session",
            "storage_path": "",
        }
        ev = _ExpressionVector(cfg)
        assert ev.score_rules["work"] == (1.0, -0.5, 1.0, 0.95)

    def test_DC04_decay_one_turns_off(self, tmp_path):
        """DC-04: decay_factor=1.0 关闭衰减（旧行为保留）"""
        ev_path = tmp_path / "ev_dc4.json"
        cfg = {
            "dimensions": {"work": ["代码"]},
            "score_rules": {"work": [1, -0.5, 1, 1.0]},
            "reset": "session",
            "storage_path": str(ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.vectors["work"] = 10.0
        ev.update("写代码", "s1")
        # decay=1.0 → 不变 → + 命中 = 11
        assert ev.vectors["work"] == 11.0

    def test_DC05_decay_never_below_zero(self, tmp_path):
        """DC-05: 衰减+未命中后不低于 0"""
        ev_path = tmp_path / "ev_dc5.json"
        cfg = {
            "dimensions": {"work": ["代码"]},
            "score_rules": {"work": [1, -0.5, 1, 0.5]},
            "reset": "session",
            "storage_path": str(ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.vectors["work"] = 0.1
        ev.update("天气不错", "s1")
        assert ev.vectors["work"] == 0.0  # 0.1*0.5 + (-0.5) = -0.45 → max(0,)

# ═══════════════════════════════════════════════════════════════════════════════
# SPEC-006: _KeywordMatcher 测试（jieba 分词 + 同义词扩展 + 否定检测）
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def kw_keywords_dir():
    """Create a temporary keywords directory with test keyword files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        kd = Path(tmpdir)

        (kd / "care.json").write_text(
            json.dumps({"keywords": ["吃饭", "饿", "下厨", "累", "散步"]}),
            encoding="utf-8",
        )

        (kd / "work.json").write_text(
            json.dumps({"keywords": ["代码", "Bug", "Debug", "测试", "部署", "merge"]}),
            encoding="utf-8",
        )

        (kd / "play.json").write_text(
            json.dumps({"keywords": ["游戏", "好玩", "音乐", "放松"]}),
            encoding="utf-8",
        )

        (kd / "synonyms.json").write_text(
            json.dumps({
                "推送": "push",
                "提交": "commit",
                "合并": "merge",
                "问题": "Bug",
                "缺陷": "Bug",
                "部署上线": "部署",
                "发布": "deploy",
                "单元测试": "测试",
                "集成测试": "测试",
            }),
            encoding="utf-8",
        )

        yield kd


@pytest.fixture
def km(kw_keywords_dir):
    """Create a _KeywordMatcher from the temporary keywords directory."""
    return _KeywordMatcher(kw_keywords_dir)


# ---------------------------------------------------------------------------
# Construction & loading
# ---------------------------------------------------------------------------


class TestKeywordMatcherConstruction:
    def test_loads_dimensions(self, km):
        assert "care" in km.dimensions
        assert "work" in km.dimensions
        assert "play" in km.dimensions

    def test_dimension_keywords_are_frozenset(self, km):
        assert isinstance(km.dimensions["care"], frozenset)
        assert "吃饭" in km.dimensions["care"]
        assert "下厨" in km.dimensions["care"]

    def test_nonexistent_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            _KeywordMatcher(Path("/nonexistent/keywords/dir"))

    def test_empty_dir_does_not_crash(self, tmp_path):
        km = _KeywordMatcher(tmp_path)
        assert km.dimensions == {}
        assert km.match("hello") == []

    def test_malformed_json_skipped(self, tmp_path):
        (tmp_path / "care.json").write_text("not json", encoding="utf-8")
        (tmp_path / "work.json").write_text(
            json.dumps({"keywords": ["代码"]}), encoding="utf-8"
        )
        km = _KeywordMatcher(tmp_path)
        assert "care" not in km.dimensions
        assert "work" in km.dimensions

    def test_missing_keywords_key(self, tmp_path):
        (tmp_path / "care.json").write_text(
            json.dumps({"something_else": []}), encoding="utf-8"
        )
        km = _KeywordMatcher(tmp_path)
        assert "care" not in km.dimensions


# ---------------------------------------------------------------------------
# Synonym mapping
# ---------------------------------------------------------------------------


class TestKeywordMatcherSynonyms:
    def test_bidirectional_mapping(self, km):
        sm = km.synonym_map
        assert "推送" in sm
        push_cluster = sm["推送"]
        assert "push" in push_cluster
        assert "推送" in sm["push"]

    def test_synonym_cluster_merging(self, km):
        sm = km.synonym_map
        bug_cluster = sm["Bug"]
        assert "问题" in bug_cluster
        assert "缺陷" in bug_cluster
        assert "Bug" in bug_cluster

    def test_synonym_self_inclusion(self, km):
        sm = km.synonym_map
        for word, synonyms in sm.items():
            assert word in synonyms, f"{word} not in its own synonym set"

    def test_no_synonyms_file(self, tmp_path):
        (tmp_path / "care.json").write_text(
            json.dumps({"keywords": ["吃饭"]}), encoding="utf-8"
        )
        km = _KeywordMatcher(tmp_path)
        assert km.synonym_map == {}

    def test_malformed_synonyms_json(self, tmp_path):
        (tmp_path / "care.json").write_text(
            json.dumps({"keywords": ["吃饭"]}), encoding="utf-8"
        )
        (tmp_path / "synonyms.json").write_text("bad json", encoding="utf-8")
        km = _KeywordMatcher(tmp_path)
        assert km.synonym_map == {}


# ---------------------------------------------------------------------------
# Matching — dimension-based
# ---------------------------------------------------------------------------


class TestKeywordMatcherMatchDimensions:
    def test_direct_keyword_match(self, km):
        result = km.match("我去写代码了")
        assert "work" in result

    def test_no_match(self, km):
        result = km.match("今天天气真好")
        assert result == []

    def test_empty_message(self, km):
        assert km.match("") == []

    def test_multiple_dimensions(self, km):
        result = km.match("写代码写累了想听音乐放松一下")
        assert "work" in result
        assert "care" in result
        assert "play" in result

    def test_deploy_synonym_match(self, km):
        result = km.match("准备部署上线了")
        assert "work" in result

    def test_bug_synonym_match(self, km):
        result = km.match("有个问题需要修复")
        assert "work" in result

    def test_jieba_segmentation(self, km):
        result = km.match("今晚我要下厨做饭")
        assert "care" in result


# ---------------------------------------------------------------------------
# Negation detection
# ---------------------------------------------------------------------------


class TestKeywordMatcherNegation:
    def test_simple_negation(self, kw_keywords_dir):
        (kw_keywords_dir / "care.json").write_text(
            json.dumps({"keywords": ["累"]}), encoding="utf-8"
        )
        km = _KeywordMatcher(kw_keywords_dir)
        result = km.match("我不累")
        assert "care" not in result

    def test_negation_within_window(self, kw_keywords_dir):
        (kw_keywords_dir / "care.json").write_text(
            json.dumps({"keywords": ["散步", "累"]}), encoding="utf-8"
        )
        km = _KeywordMatcher(kw_keywords_dir)
        result = km.match("今天不想去散步")
        assert "care" not in result

    def test_keyword_without_negation_still_matches(self, kw_keywords_dir):
        (kw_keywords_dir / "care.json").write_text(
            json.dumps({"keywords": ["累"]}), encoding="utf-8"
        )
        km = _KeywordMatcher(kw_keywords_dir)
        result = km.match("今天很累")
        assert "care" in result

    def test_multiple_keywords_one_negated(self, kw_keywords_dir):
        (kw_keywords_dir / "care.json").write_text(
            json.dumps({"keywords": ["饿", "累"]}), encoding="utf-8"
        )
        km = _KeywordMatcher(kw_keywords_dir)
        result = km.match("我不饿但是很累")
        assert "care" in result  # matched via "累"


# ---------------------------------------------------------------------------
# Substring fallback matching
# ---------------------------------------------------------------------------


class TestKeywordMatcherSubstringFallback:
    def test_substring_match_for_multichar_keywords(self, kw_keywords_dir):
        (kw_keywords_dir / "work.json").write_text(
            json.dumps({"keywords": ["重构"]}), encoding="utf-8"
        )
        km = _KeywordMatcher(kw_keywords_dir)
        result = km.match("这个模块需要重构一下")
        assert "work" in result

    def test_single_char_keyword_still_matches(self, kw_keywords_dir):
        (kw_keywords_dir / "care.json").write_text(
            json.dumps({"keywords": ["饭"]}), encoding="utf-8"
        )
        km = _KeywordMatcher(kw_keywords_dir)
        result = km.match("吃饭")
        assert "care" in result


# ---------------------------------------------------------------------------
# Hot reload
# ---------------------------------------------------------------------------


class TestKeywordMatcherHotReload:
    def test_reload_flag_triggers_reload(self, kw_keywords_dir):
        import expression_vector as evm

        (kw_keywords_dir / "care.json").write_text(
            json.dumps({"keywords": ["吃饭"]}), encoding="utf-8"
        )

        km = _KeywordMatcher(kw_keywords_dir)
        assert "care" in km.dimensions
        assert "吃饭" in km.dimensions["care"]

        (kw_keywords_dir / "care.json").write_text(
            json.dumps({"keywords": ["散步", "喝水"]}), encoding="utf-8"
        )

        evm._RELOAD_KEYWORDS = True
        result = km.match("我想喝水")
        assert "care" in result
        assert evm._RELOAD_KEYWORDS is False

    def test_reload_without_flag_uses_cached(self, kw_keywords_dir):
        import expression_vector as evm
        evm._RELOAD_KEYWORDS = False

        (kw_keywords_dir / "care.json").write_text(
            json.dumps({"keywords": ["吃饭"]}), encoding="utf-8"
        )
        km = _KeywordMatcher(kw_keywords_dir)

        (kw_keywords_dir / "care.json").write_text(
            json.dumps({"keywords": ["新关键词"]}), encoding="utf-8"
        )

        result = km.match("吃饭了")
        assert "care" in result


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestKeywordMatcherProperties:
    def test_dimensions_property_returns_copy(self, km):
        dims = km.dimensions
        dims["new"] = frozenset()
        assert "new" not in km.dimensions

    def test_synonym_map_property_returns_copy(self, km):
        sm = km.synonym_map
        sm["new_word"] = set()
        assert "new_word" not in km.synonym_map


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestKeywordMatcherHelpers:
    def test_char_pos_to_token_idx_start(self):
        idx = _KeywordMatcher._char_pos_to_token_idx(["hello", "world"], 0)
        assert idx == 0

    def test_char_pos_to_token_idx_middle(self):
        idx = _KeywordMatcher._char_pos_to_token_idx(["hello", "world"], 6)
        assert idx == 1

    def test_char_pos_to_token_idx_out_of_range(self):
        idx = _KeywordMatcher._char_pos_to_token_idx(["hello", "world"], 100)
        assert idx is None

    def test_negation_words_not_empty(self):
        assert len(_NEGATION_WORDS) > 0
        assert "不" in _NEGATION_WORDS
        assert "没" in _NEGATION_WORDS

    def test_dimension_files_list(self):
        assert "care.json" in _DIMENSION_FILES
        assert "work.json" in _DIMENSION_FILES


# ---------------------------------------------------------------------------
# Integration: _match_keyword with expression vectors
# ---------------------------------------------------------------------------


class TestMatchKeywordWithExpressionVector:
    """Tests for _match_keyword using dimension-based matching."""

    def test_dimension_key_triggers_rules(self, kw_keywords_dir):
        from dynamic_rules import _match_keyword, _get_keyword_matcher
        import dynamic_rules as dr

        old_km = dr._km
        dr._km = _KeywordMatcher(kw_keywords_dir)

        try:
            keywords = {"work": ["工作模式启动"]}
            result = _match_keyword(keywords, "发现一个Bug需要处理")
            assert len(result) >= 1
            assert "💬 [work] 工作模式启动" in result
        finally:
            dr._km = old_km

    def test_dimension_key_no_match_returns_empty(self, kw_keywords_dir):
        import dynamic_rules as dr
        old_km = dr._km
        dr._km = _KeywordMatcher(kw_keywords_dir)

        try:
            keywords = {"work": ["工作模式"]}
            result = dr._match_keyword(keywords, "今天天气真好")
            assert result == []
        finally:
            dr._km = old_km

    def test_legacy_regex_fallback(self, kw_keywords_dir):
        import dynamic_rules as dr
        old_km = dr._km
        dr._km = _KeywordMatcher(kw_keywords_dir)

        try:
            keywords = {"xyz_pattern_123": ["匹配到陌生模式"]}
            result = dr._match_keyword(keywords, "xyz_pattern_123 is here")
            assert "💬 [xyz_pattern_123] 匹配到陌生模式" in result
        finally:
            dr._km = old_km

    def test_legacy_regex_no_match(self, kw_keywords_dir):
        import dynamic_rules as dr
        old_km = dr._km
        dr._km = _KeywordMatcher(kw_keywords_dir)

        try:
            keywords = {"no_match_pattern": ["规则"]}
            result = dr._match_keyword(keywords, "hello world")
            assert result == []
        finally:
            dr._km = old_km

    def test_multiple_dimensions_all_return_rules(self, kw_keywords_dir):
        import dynamic_rules as dr
        old_km = dr._km
        dr._km = _KeywordMatcher(kw_keywords_dir)

        try:
            keywords = {
                "work": ["工作规则"],
                "care": ["关怀规则"],
            }
            result = dr._match_keyword(keywords, "写代码写累了")
            assert "💬 [work] 工作规则" in result
            assert "💬 [care] 关怀规则" in result
        finally:
            dr._km = old_km

    def test_mixed_dimension_and_legacy(self, kw_keywords_dir):
        import dynamic_rules as dr
        old_km = dr._km
        dr._km = _KeywordMatcher(kw_keywords_dir)

        try:
            keywords = {
                "work": ["工作规则"],
                r"mystery_pattern": ["遗留规则"],
            }
            result = dr._match_keyword(keywords, "部署遇到mystery_pattern")
            assert "💬 [work] 工作规则" in result
            assert "💬 [mystery_pattern] 遗留规则" in result
        finally:
            dr._km = old_km

    def test_negated_dimension_not_in_result(self, kw_keywords_dir):
        (kw_keywords_dir / "care.json").write_text(
            json.dumps({"keywords": ["累"]}), encoding="utf-8"
        )
        import dynamic_rules as dr
        old_km = dr._km
        dr._km = _KeywordMatcher(kw_keywords_dir)

        try:
            keywords = {"care": ["关怀规则"]}
            result = dr._match_keyword(keywords, "我不累")
            assert result == []
        finally:
            dr._km = old_km
