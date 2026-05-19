"""Tests for expression vector — _ExpressionVector class.

Covers: update algorithm, reset strategies, disk persistence,
injection formatting, and edge cases.
Per SPEC-002 §10.2 ~ §10.5: TC-IDs EV-01~14, RS-01~06, PERS-01~08, FMT-01~03.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from expression_vector import _ExpressionVector


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
        """EV-06: 连续 3 次命中 work → 3.0。"""
        for _ in range(3):
            ev.update("写代码", "s1")
        assert ev.vectors["work"] == 3.0

    def test_EV07_hit_then_miss_mix(self, ev):
        """EV-07: 2 命中 + 3 未命中（work: [1, -0.5, 1]）→ 0.5。"""
        ev.update("写代码", "s1")  # work += 1 → 1
        ev.update("写代码", "s1")  # work += 1 → 2
        ev.update("天气真好", "s1")  # work += -0.5 → 1.5
        ev.update("去散步", "s1")    # work += -0.5 → 1.0
        ev.update("好开心", "s1")    # work += -0.5 → 0.5
        assert ev.vectors["work"] == pytest.approx(0.5)

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
        """RS-01: session 策略，同一 session 不清零。"""
        ev.update("写代码", "s1")  # work += 1
        assert ev.vectors["work"] == 1.0
        ev.update("写代码", "s1")      # 同 session，不清零 → work += 1
        assert ev.vectors["work"] == 2.0

    def test_RS02_session_new_session_resets(self, ev):
        """RS-02: session 策略，新 session 清零后重新累积。"""
        ev.update("写代码", "s1")
        assert ev.vectors["work"] == 1.0
        # 切换 session → 清零后重新累加
        ev.update("写代码", "s2")
        assert ev.vectors["work"] == 1.0  # 从 0 重新开始

    def test_RS03_daily_same_day_no_reset(self, tmp_ev_path):
        """RS-03: daily 策略，同日不清零。"""
        cfg = {
            "dimensions": {"work": ["代码"]},
            "reset": "daily",
            "storage_path": str(tmp_ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.update("代码", "s1")
        ev.update("代码", "s1")
        assert ev.vectors["work"] == 2.0

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
            "reset": "none",
            "storage_path": str(tmp_ev_path),
        }
        ev = _ExpressionVector(cfg)
        ev.update("代码", "s1")
        ev.save()

        ev2 = _ExpressionVector(cfg)
        ev2.load()
        ev2.update("代码", "s2")  # 新 session → none 策略不清零
        assert ev2.vectors["work"] == 2.0

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
        cfg = {"dimensions": {"work": ["代码"]}, "storage_path": str(tmp_ev_path)}
        ev = _ExpressionVector(cfg)
        ev.update("写代码", "s1")
        ev.update("写代码", "s1")
        ev.save()

        cfg2 = {
            "dimensions": {"work": ["代码"], "future": ["愿景"]},
            "storage_path": str(tmp_ev_path),
        }
        ev2 = _ExpressionVector(cfg2)
        ev2.load()
        assert ev2.vectors["work"] == 2.0   # 保留
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
        """FMT-03: 浮点值四舍五入。work=1.5 → int(round(1.5)) = 2。"""
        ev.update("代码", "s1")    # work += 1 → 1.0
        ev.update("代码", "s1")    # work += 1 → 2.0
        ev.update("天气好", "s1")  # work += -0.5 → 1.5
        assert ev.vectors["work"] == pytest.approx(1.5)
        result = ev.format_inject(1)
        assert "work:2" in result  # round(1.5) = 2
