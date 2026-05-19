# PLAN-002: 表达向量与 FuzzyUtility 层 — 实施计划

**文档编号:** PLAN-002
**对应 US:** US-002 v1.0
**对应 SPEC:** SPEC-002 v1.0
**版本:** 1.0
**日期:** 2026-05-19
**作者:** CC (Claude Code)
**审阅:** 知惠 & Kai.Xu
**状态:** 📋 待审阅

---

## 目录

1. [总体时间估算](#1-总体时间估算)
2. [实施步骤](#2-实施步骤)
    - [Step 0: 环境准备与基线验证](#step-0-环境准备与基线验证)
    - [Step 1: 测试先行 — 编写 test_expression_vector.py](#step-1-测试先行--编写-test_expression_vectorpy)
    - [Step 2: 实现 _ExpressionVector 核心类](#step-2-实现-_expressionvector-核心类)
    - [Step 3: 测试先行 — 编写 test_fixed_signals.py](#step-3-测试先行--编写-test_fixed_signalspy)
    - [Step 4: 实现固定层信号函数](#step-4-实现固定层信号函数)
    - [Step 5: 注入链路集成 — inject_context() 扩展](#step-5-注入链路集成--inject_context-扩展)
    - [Step 6: 更新 _debug_summary()](#step-6-更新-_debug_summary)
    - [Step 7: 更新 examples/persona-config.json](#step-7-更新-examplespersona-configjson)
    - [Step 8: 编写集成测试](#step-8-编写集成测试)
    - [Step 9: 全量回归测试](#step-9-全量回归测试)
3. [风险点与回滚方案](#3-风险点与回滚方案)
4. [验证检查清单](#4-验证检查清单)

---

## 1. 总体时间估算

| 步骤 | 内容 | 预估时间 |
|:---|:---|:---|
| Step 0 | 环境准备与基线验证 | 5 min |
| Step 1 | 编写 test_expression_vector.py（TDD 红色阶段） | 30 min |
| Step 2 | 实现 _ExpressionVector 核心类（TDD 绿色阶段） | 25 min |
| Step 3 | 编写 test_fixed_signals.py（TDD 红色阶段） | 15 min |
| Step 4 | 实现固定层信号函数（TDD 绿色阶段） | 15 min |
| Step 5 | 注入链路集成 — inject_context() 扩展 | 20 min |
| Step 6 | 更新 _debug_summary() | 10 min |
| Step 7 | 更新 examples/persona-config.json | 5 min |
| Step 8 | 编写集成测试 | 20 min |
| Step 9 | 全量回归测试 + 收尾 | 10 min |
| **合计** | | **~2 小时 35 分钟** |

### 阶段依赖关系

```
Step 1 (EV 测试) → Step 2 (EV 实现) ──┐
                                       ├─→ Step 5 (注入链路) → Step 6 (debug) → Step 8 (集成测试) → Step 9 (回归)
Step 3 (FS 测试) → Step 4 (FS 实现) ──┘                                          ↑
                                                                   Step 7 (config)
```

Step 1→2 与 Step 3→4 可并行开发。Step 5 依赖两者全部完成。

---

## 2. 实施步骤

### Step 0: 环境准备与基线验证

**目标：** 确认当前分支、工作区状态、现有测试全部通过。

**操作：**

```bash
# 确认在 feature/001-module-switch 分支（或新切 feature/002-expression-vector）
git branch --show-current

# 运行全部测试，确认基线
python -m pytest tests/ -v
# 期望: 全部 PASSED

# 确认工作区干净
git status
```

**验证标准：**
- `python -m pytest tests/ -v` 全部通过，0 failure
- `git status` 干净

**回滚：** 无需回滚（尚未改动代码）

---

### Step 1: 测试先行 — 编写 test_expression_vector.py

**目标：** 按照 SPEC-002 §10.2~10.5 测试矩阵，编写表达向量全部单元测试。此时代码未写，所有测试应 **FAIL**（TDD 红色阶段）。

**文件：** `tests/test_expression_vector.py`（新建）

#### 1.1 导入与 fixture

```python
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
```

#### 1.2 Fixture

```python
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
```

#### 1.3 测试类清单

| 测试类 | 对应 SPEC TC-IDs | 用例数 | 说明 |
|:---|:---|:---|:---|
| `TestUpdateAlgorithm` | EV-01~14 | 14 | `update()` 核心算法 |
| `TestResetStrategy` | RS-01~06 | 6 | `should_reset()` 重置策略 |
| `TestDiskPersistence` | PERS-01~08 | 8 | `load()` / `save()` 磁盘读写 |
| `TestFormatInject` | FMT-01~03 | 3 | `format_inject()` 格式化输出 |

**共 31 个测试用例。**

#### 1.4 `TestUpdateAlgorithm` 实现（EV-01 ~ EV-14）

```python
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
        ev.update("写代码好累想休息", "s1")
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
            ev.update("代码架构", "s1")
        assert ev.vectors["work"] == 3.0

    def test_EV07_hit_then_miss_mix(self, ev):
        """EV-07: 2 命中 + 3 未命中（work: [1, -0.5, 1]）→ 0.5。"""
        ev.update("代码架构", "s1")  # work += 1 → 1
        ev.update("代码重构", "s1")  # work += 1 → 2
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
```

#### 1.5 `TestResetStrategy` 实现（RS-01 ~ RS-06）

```python
class TestResetStrategy:
    """RS-01 ~ RS-06: should_reset() 重置策略测试。"""

    def test_RS01_session_same_session_no_reset(self, ev):
        """RS-01: session 策略，同一 session 不清零。"""
        ev.update("代码代码", "s1")  # work += 2
        assert ev.vectors["work"] == 2.0
        ev.update("代码", "s1")      # 同 session，不清零
        assert ev.vectors["work"] == 3.0

    def test_RS02_session_new_session_resets(self, ev):
        """RS-02: session 策略，新 session 清零后重新累积。"""
        ev.update("代码代码", "s1")
        assert ev.vectors["work"] == 2.0
        # 切换 session → 清零后重新累加
        ev.update("代码代码", "s2")
        assert ev.vectors["work"] == 2.0  # 从 0 重新开始

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
```

#### 1.6 `TestDiskPersistence` 实现（PERS-01 ~ PERS-08）

```python
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
        ev.update("代码代码", "s1")
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
```

#### 1.7 `TestFormatInject` 实现（FMT-01 ~ FMT-03）

```python
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
```

#### 1.8 操作

```bash
# 创建测试文件
touch tests/test_expression_vector.py
# 写入全部 31 个测试用例

# 验证文件可被 pytest 发现（预期全部 FAIL / ERROR）
python -m pytest tests/test_expression_vector.py -v
# 期望: 大量 FAILED 或 ERROR（expression_vector 模块不存在）
```

**验证标准：**
- 测试文件被 pytest 发现（无语法错误）
- 所有 31 个测试 FAIL 或 ERROR
- 现有测试仍全部 PASS（`python -m pytest tests/ -v --ignore=tests/test_expression_vector.py`）

---

### Step 2: 实现 _ExpressionVector 核心类

**目标：** 创建 `hermes_persona/expression_vector.py`，实现完整的 `_ExpressionVector` 类，使 Step 1 的 31 个测试全部通过。

**文件：** `hermes_persona/expression_vector.py`（新建）

**预估行数：** ~115 行

#### 2.1 模块头部

```python
"""Expression vector engine for the FuzzyUtility layer.

Multi-dimensional, self-decaying, user-controllable soft-prompt system.
Keywords match dimensions, scores accumulate/decay per turn, and the
current vector values are injected into LLM context each turn.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
```

#### 2.2 `_ExpressionVector.__init__()`

```python
class _ExpressionVector:
    """表达向量引擎：关键词匹配 → 累加/衰减 → 磁盘持久化 → 格式化注入。"""

    def __init__(self, cfg: dict, profile_path: str | None = None):
        # 1. 解析 dimensions（key 即维度名）
        self.dimensions: dict[str, list[str]] = {}
        for dim_name, keywords in cfg.get("dimensions", {}).items():
            if isinstance(keywords, list):
                self.dimensions[dim_name] = [str(k) for k in keywords]

        # 2. 解析 score_rules，缺失维度用默认值 [1, -0.5, 1]
        self.score_rules: dict[str, tuple[float, float, float]] = {}
        default_rule = (1.0, -0.5, 1.0)
        for dim_name in self.dimensions:
            raw = cfg.get("score_rules", {}).get(dim_name, list(default_rule))
            if isinstance(raw, (list, tuple)) and len(raw) == 3:
                try:
                    self.score_rules[dim_name] = (
                        float(raw[0]),
                        float(raw[1]),
                        float(raw[2]),
                    )
                except (ValueError, TypeError):
                    self.score_rules[dim_name] = default_rule
            else:
                self.score_rules[dim_name] = default_rule

        # 3. 重置策略
        self.reset_policy: str = cfg.get("reset", "session")
        if self.reset_policy not in ("session", "daily", "none"):
            self.reset_policy = "session"

        # 4. 存储路径（替换 {profile} 占位符）
        raw_path = cfg.get(
            "storage_path", "~/.hermes/expression_vector.json"
        )
        if profile_path:
            raw_path = raw_path.replace("{profile}", str(profile_path))
        self.storage_path: Path = Path(raw_path).expanduser()

        # 5. 初始化向量（全部 0.0）
        self.vectors: dict[str, float] = {dim: 0.0 for dim in self.dimensions}
        self._session_id: str | None = None
        self._last_updated: datetime | None = None
```

#### 2.3 `update()`

```python
    def update(self, user_message: str | None, session_id: str) -> None:
        """根据用户消息更新所有维度分数。"""
        # 1. 检查重置策略
        if self.should_reset(session_id):
            self.vectors = {dim: 0.0 for dim in self.dimensions}

        # 2. 逐维度处理
        msg_lower = (user_message or "").lower()
        for dim_name, keywords in self.dimensions.items():
            hit_score, miss_penalty, weight = self.score_rules[dim_name]

            matched = any(
                kw.lower() in msg_lower
                for kw in keywords
                if kw  # 跳过空字符串
            )

            if matched:
                self.vectors[dim_name] += hit_score * weight
            else:
                self.vectors[dim_name] += miss_penalty * weight

            # 永不跌破 0
            self.vectors[dim_name] = max(0.0, self.vectors[dim_name])

        # 3. 更新元数据
        self._last_updated = datetime.now()
        self._session_id = session_id
```

#### 2.4 `should_reset()`

```python
    def should_reset(self, current_session_id: str) -> bool:
        """检查是否需要重置向量。"""
        if self.reset_policy == "none":
            return False

        if self.reset_policy == "session":
            if self._session_id is None:
                return False  # 首次加载不清零
            return current_session_id != self._session_id

        if self.reset_policy == "daily":
            if self._last_updated is None:
                return False
            return datetime.now().date() > self._last_updated.date()

        return False
```

#### 2.5 `load()` / `save()`

```python
    def load(self) -> None:
        """从磁盘加载向量状态。文件不存在或格式错误时保持初始值。"""
        try:
            if not self.storage_path.is_file():
                return

            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                return

            saved = data.get("vectors", {})
            for dim_name in self.dimensions:
                if dim_name in saved:
                    self.vectors[dim_name] = max(0.0, float(saved[dim_name]))

            self._session_id = data.get("session_id")
            ts = data.get("last_updated")
            if ts:
                self._last_updated = datetime.fromisoformat(ts)
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            return

    def save(self) -> None:
        """将向量状态写入磁盘。创建父目录（如果不存在）。"""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "version": 1,
                "session_id": self._session_id,
                "last_updated": (
                    self._last_updated.isoformat()
                    if self._last_updated
                    else None
                ),
                "vectors": self.vectors,
            }
            self.storage_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass  # 磁盘写入失败 → 静默降级
```

#### 2.6 `format_inject()`

```python
    def format_inject(self, turn_count: int) -> str:
        """格式化表达向量为注入文本。"""
        dim_parts = [
            f"{name}:{int(round(val))}"
            for name, val in sorted(self.vectors.items())
        ]
        dim_str = " ".join(dim_parts)
        return f"📊 [表达向量] {dim_str} | 第 {turn_count} 轮"
```

#### 2.7 验证

```bash
python -m pytest tests/test_expression_vector.py -v
# 期望: 31 passed

# 现有测试不受影响
python -m pytest tests/ -v --ignore=tests/test_expression_vector.py
# 期望: 全部 PASSED（无回归）
```

**验证标准：**
- 31 个表达向量测试全部 PASSED
- 现有测试 0 回归

---

### Step 3: 测试先行 — 编写 test_fixed_signals.py

**目标：** 按照 SPEC-002 §10.6 测试矩阵，编写固定层信号全部单元测试。TDD 红色阶段。

**文件：** `tests/test_fixed_signals.py`（新建）

#### 3.1 导入

```python
"""Tests for fixed signal functions — message length and reply gap hints.

Per SPEC-002 §10.6: TC-IDs FS-01~09.
"""

import json
import time
from pathlib import Path

import pytest

import injector as injector
```

#### 3.2 测试类清单

| 测试类 | 对应 SPEC TC-IDs | 用例数 | 说明 |
|:---|:---|:---|:---|
| `TestMessageLengthHint` | FS-01~03 | 3 | 消息长度信号 |
| `TestReplyGapHint` | FS-04~09 | 6 | 回复间隔信号 + 写回 |

**共 9 个测试用例。**

#### 3.3 `TestMessageLengthHint` 实现（FS-01 ~ FS-03）

```python
class TestMessageLengthHint:
    """FS-01 ~ FS-03: _message_length_hint() 测试。"""

    def test_FS01_short_message_returns_hint(self):
        """FS-01: 消息长度 < threshold → 返回 '📏 消息较短'。"""
        result = injector._message_length_hint(
            "好",
            {"message_length": {"enabled": True, "threshold": 50}},
        )
        assert result == "📏 消息较短"

    def test_FS02_message_at_threshold_returns_none(self):
        """FS-02: 消息长度 ≥ threshold → 返回 None。"""
        msg = "x" * 50
        result = injector._message_length_hint(
            msg,
            {"message_length": {"enabled": True, "threshold": 50}},
        )
        assert result is None

    def test_FS03_disabled_returns_none(self):
        """FS-03: enabled=false → 返回 None。"""
        result = injector._message_length_hint(
            "好",
            {"message_length": {"enabled": False}},
        )
        assert result is None
```

#### 3.4 `TestReplyGapHint` 实现（FS-04 ~ FS-09）

```python
class TestReplyGapHint:
    """FS-04 ~ FS-09: _reply_gap_hint() + _save_reply_timing() 测试。"""

    def test_FS04_gap_above_threshold(self, tmp_path):
        """FS-04: 间隔 > threshold → 返回 '🎵 欢迎回来'。"""
        storage = tmp_path / "timing.json"
        storage.write_text(
            json.dumps({"last_reply_at": time.time() - 3600}),  # 60 分钟前
            encoding="utf-8",
        )
        result, _ = injector._reply_gap_hint({
            "reply_gap": {
                "enabled": True,
                "threshold_minutes": 30,
                "storage_path": str(storage),
            },
        })
        assert result == "🎵 欢迎回来"

    def test_FS05_gap_below_threshold(self, tmp_path):
        """FS-05: 间隔 ≤ threshold → 返回 None。"""
        storage = tmp_path / "timing.json"
        storage.write_text(
            json.dumps({"last_reply_at": time.time() - 600}),  # 10 分钟前
            encoding="utf-8",
        )
        result, _ = injector._reply_gap_hint({
            "reply_gap": {
                "enabled": True,
                "threshold_minutes": 30,
                "storage_path": str(storage),
            },
        })
        assert result is None

    def test_FS06_no_timing_file(self, tmp_path):
        """FS-06: 文件不存在 → 返回 None（首次对话不欢迎回来）。"""
        storage = tmp_path / "nonexistent.json"
        result, _ = injector._reply_gap_hint({
            "reply_gap": {
                "enabled": True,
                "threshold_minutes": 30,
                "storage_path": str(storage),
            },
        })
        assert result is None

    def test_FS07_disabled_returns_none(self):
        """FS-07: enabled=false → 返回 None。"""
        result, _ = injector._reply_gap_hint({
            "reply_gap": {"enabled": False},
        })
        assert result is None

    def test_FS08_corrupt_file_returns_none(self, tmp_path):
        """FS-08: 文件损坏 → 返回 None，不抛异常。"""
        storage = tmp_path / "timing.json"
        storage.write_text("not json at all", encoding="utf-8")
        result, _ = injector._reply_gap_hint({
            "reply_gap": {
                "enabled": True,
                "threshold_minutes": 30,
                "storage_path": str(storage),
            },
        })
        assert result is None

    def test_FS09_save_reply_timing_writes_file(self, tmp_path):
        """FS-09: _save_reply_timing() 写回 last_reply_at。"""
        storage = tmp_path / "timing.json"
        now_ts = time.time()
        injector._save_reply_timing(
            {"reply_gap": {"enabled": True, "storage_path": str(storage)}},
            now_ts,
        )
        assert storage.is_file()
        data = json.loads(storage.read_text(encoding="utf-8"))
        assert abs(data["last_reply_at"] - now_ts) < 1.0
```

#### 3.5 操作

```bash
# 创建测试文件
touch tests/test_fixed_signals.py
# 写入全部 9 个测试用例

# 验证文件可被 pytest 发现（预期全部 FAIL）
python -m pytest tests/test_fixed_signals.py -v
# 期望: FAILED / ERROR（函数不存在）
```

**验证标准：**
- 测试文件被 pytest 发现
- 所有 9 个测试 FAIL 或 ERROR
- 现有测试不受影响

---

### Step 4: 实现固定层信号函数

**目标：** 在 `injector.py` 中新增三个固定层信号函数，使 Step 3 的 9 个测试通过。

**文件：** `hermes_persona/injector.py`

**前置依赖：** 无（可与 Step 2 并行）

#### 4.1 新增 import

**位置：** 第 10 行 `import traceback` 之后

```python
import time
```

#### 4.2 新增 `_message_length_hint()`

**位置：** 在 `injector.py` 中 `_debug_summary` 辅助函数区域之后、`_recall_memories` 之前（约第 366 行之后）

```python
# ---------------------------------------------------------------------------
# Fixed signal helpers
# ---------------------------------------------------------------------------


def _message_length_hint(user_message: str, fixed_cfg: dict) -> str | None:
    """检查消息长度，短消息注入提示。

    Args:
        user_message: 用户当前消息文本。
        fixed_cfg: fixed_signals 配置节。

    Returns:
        "📏 消息较短" 或 None。
    """
    ml_cfg = fixed_cfg.get("message_length", {})
    if not ml_cfg.get("enabled", False):
        return None

    threshold = ml_cfg.get("threshold", 50)
    if not isinstance(threshold, (int, float)):
        threshold = 50

    if len(user_message) < threshold:
        return "📏 消息较短"
    return None
```

#### 4.3 新增 `_reply_gap_hint()`

```python
def _reply_gap_hint(fixed_cfg: dict) -> tuple[str | None, float]:
    """检查回复间隔，长时间未回复注入欢迎回来提示。

    Args:
        fixed_cfg: fixed_signals 配置节。

    Returns:
        (hint_text_or_None, now_timestamp)
    """
    rg_cfg = fixed_cfg.get("reply_gap", {})
    if not rg_cfg.get("enabled", False):
        return None, time.time()

    threshold_minutes = rg_cfg.get("threshold_minutes", 30)
    if not isinstance(threshold_minutes, (int, float)):
        threshold_minutes = 30

    now = time.time()
    raw_path = rg_cfg.get("storage_path", "~/.hermes/reply_timing.json")
    storage_path = Path(raw_path).expanduser()

    hint = None
    try:
        if storage_path.is_file():
            data = json.loads(storage_path.read_text(encoding="utf-8"))
            last_reply_at = data.get("last_reply_at")
            if last_reply_at:
                gap_minutes = (now - float(last_reply_at)) / 60.0
                if gap_minutes > threshold_minutes:
                    hint = "🎵 欢迎回来"
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        pass

    return hint, now
```

#### 4.4 新增 `_save_reply_timing()`

```python
def _save_reply_timing(fixed_cfg: dict, now_ts: float) -> None:
    """将 last_reply_at 写回磁盘。

    Args:
        fixed_cfg: fixed_signals 配置节。
        now_ts: 当前时间戳（由 _reply_gap_hint 返回）。
    """
    rg_cfg = fixed_cfg.get("reply_gap", {})
    if not rg_cfg.get("enabled", False):
        return

    raw_path = rg_cfg.get("storage_path", "~/.hermes/reply_timing.json")
    storage_path = Path(raw_path).expanduser()

    try:
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"last_reply_at": now_ts}
        storage_path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass
```

#### 4.5 验证

```bash
python -m pytest tests/test_fixed_signals.py -v
# 期望: 9 passed

# 确认现有测试不受影响
python -m pytest tests/ -v --ignore=tests/test_expression_vector.py \
                         --ignore=tests/test_fixed_signals.py
# 期望: 全部 PASSED
```

---

### Step 5: 注入链路集成 — inject_context() 扩展

**目标：** 在 `inject_context()` 中插入步骤④a（固定信号）和④b（表达向量），修正 `turn_count` 计算位置。

**文件：** `hermes_persona/injector.py`

**前置依赖：** Step 2（`expression_vector.py` 已创建）+ Step 4（固定信号函数已就位）

#### 5.1 新增 import

**位置：** 第 15 行 `from .variance import _randomize_variance` 之后

```python
from .expression_vector import _ExpressionVector
```

#### 5.2 修正 turn_count 计算位置

**当前代码（第 512~525 行）：**

```python
        # 3. Dynamic rules (subchannel-controllable)
        if _has_any_dynamic(modules):
            turn_count = len(conversation_history or []) // 2
            dynamic_cfg = config.get("dynamic", {})
            parts.extend(
                _select_dynamic_rules(
                    dynamic_cfg,
                    user_message,
                    is_first_turn,
                    turn_count,
                    modules=modules.get("dynamic", {}),
                )
            )
```

**改为：**

```python
        # 3. Dynamic rules (subchannel-controllable)
        turn_count = len(conversation_history or []) // 2  # ← 提前，④b 复用
        if _has_any_dynamic(modules):
            dynamic_cfg = config.get("dynamic", {})
            parts.extend(
                _select_dynamic_rules(
                    dynamic_cfg,
                    user_message,
                    is_first_turn,
                    turn_count,
                    modules=modules.get("dynamic", {}),
                )
            )
```

**改动说明：** `turn_count` 计算从 `_has_any_dynamic` 块内提到块外。语义不变（值相同），仅时机提前，使步骤④b 可以复用。

#### 5.3 插入步骤④a — 固定层信号

**位置：** 在步骤③ dynamic rules 之后（原第 525 行）、步骤④ variance（原第 527 行）之前

```python
        # ─── ④a Fixed signals ────────────────────────────
        fixed_cfg = config.get("fixed_signals", {})
        hint = _message_length_hint(user_message or "", fixed_cfg)
        if hint:
            parts.append(hint)

        gap_hint, now_ts = _reply_gap_hint(fixed_cfg)
        if gap_hint:
            parts.append(gap_hint)
        _save_reply_timing(fixed_cfg, now_ts)
        # ──────────────────────────────────────────────────
```

#### 5.4 插入步骤④b — 表达向量

**位置：** 在步骤④a 之后、步骤⑤ variance 之前

```python
        # ─── ④b Expression vector (FuzzyUtility) ─────────
        ev_cfg = config.get("expression_vector", {})
        if ev_cfg.get("enabled", False):
            try:
                profile = kwargs.get("profile_path", "")
                ev = _ExpressionVector(ev_cfg, profile_path=profile)
                ev.load()
                ev.update(user_message or "", session_id)
                ev.save()
                parts.append(ev.format_inject(turn_count))
            except Exception:
                pass  # fail-open：表达向量失败不阻断后续注入
        # ──────────────────────────────────────────────────
```

**关键设计点：**
- `config.get("expression_vector", {})` — 不配置时返回空 dict，跳过注入
- `ev_cfg.get("enabled", False)` — 默认关闭，与 `modules` 体系独立
- 整块被独立 `try/except` 包裹，与 `inject_context()` 外层 `try/except` 形成**双层保护**
- `turn_count` 来自步骤③之前计算，步骤④b 复用

#### 5.5 inject_context() 改动后核心结构

```python
def inject_context(session_id, user_message, conversation_history,
                   is_first_turn, model, platform, **kwargs):
    try:
        config = _load_config()
        modules = _resolve_modules(config)
        parts: list[str] = []

        # ① Time context          (不变)
        # ② Static rules          (不变)

        # ③ Dynamic rules
        turn_count = len(conversation_history or []) // 2  # ← 提前
        if _has_any_dynamic(modules):
            ...

        # ④a Fixed signals        ← 🆕
        # ④b Expression vector    ← 🆕

        # ⑤ Random variance       (不变，原步骤④)
        # ⑥ Memory recall         (不变，原步骤⑤)
        # ⑦ Kanban status         (不变，原步骤⑥)

        non_debug_count = len(parts)
        # ⑧ Debug summary         (不变)
        ...
```

#### 5.6 验证

```bash
# 确认 inject_context 改动未破坏现有功能
python -m pytest tests/test_injector.py -v
python -m pytest tests/test_modules_switch.py -v

# 表达向量单元测试仍通过
python -m pytest tests/test_expression_vector.py -v

# 固定信号单元测试仍通过
python -m pytest tests/test_fixed_signals.py -v
```

---

### Step 6: 更新 _debug_summary()

**目标：** 在 Debug Mode 摘要中追加④a（固定信号）和④b（表达向量）的状态行。

**文件：** `hermes_persona/injector.py`

**改动位置：** `_debug_summary()` 函数体内，步骤③（Dynamic）和步骤④（Variance，原编号）之间。

#### 6.1 改动内容

**在步骤③ Dynamic 之后，追加两行：**

```python
        # ③ Dynamic
        if _is_enabled(modules, "dynamic"):
            dyn = modules.get("dynamic", {})
            sub_status = _fmt_dynamic_sub_status(dyn)
            lines.append(f"  ③ ⚡ {sub_status}")
        else:
            lines.append("  ③ ⚡ 已停用")

        # ─── 以下为新增 ─────────────────────────────────
        # ④a Fixed signals
        fixed_hit = any(
            p.startswith("📏") or p.startswith("🎵")
            for p in parts
        )
        lines.append(
            f"  ④a 📏⏱️ 固定信号{'已注入' if fixed_hit else '无触发'}"
        )

        # ④b Expression vector
        ev_hit = any("📊 [表达向量]" in p for p in parts)
        if ev_hit:
            # 提取向量值显示
            import re
            ev_part = next(p for p in parts if "📊 [表达向量]" in p)
            match = re.search(r"\[表达向量\] (.+?) \|", ev_part)
            if match:
                lines.append(f"  ④b 📊 {match.group(1)}")
            else:
                lines.append("  ④b 📊 已注入")
        else:
            lines.append("  ④b 📊 未启用")
        # ─────────────────────────────────────────────────

        # ④ Variance → 编号保持不变（使用 emoji 标识而非严格编号）
        if _is_enabled(modules, "variance"):
            ...
```

**设计说明：**
- 使用 `④a` / `④b` 标注新增层，与 SPEC-002 §2.1 一致
- 通过检查 `parts` 内容判断是否注入，而非重新解析配置（保持纯函数特性）
- `import re` 放在分支内而非模块顶部（仅在 debug 开启时使用）
- 固定信号检测用 `startswith` 而非正则（性能考虑）

#### 6.2 验证

```bash
# Debug 模式相关测试
python -m pytest tests/test_modules_switch.py::TestDebugMode -v

# 现有 inject 测试
python -m pytest tests/test_injector.py -v
```

---

### Step 7: 更新 examples/persona-config.json

**目标：** 在示例配置文件中添加 `expression_vector` 和 `fixed_signals` 配置节。

**文件：** `examples/persona-config.json`

**改动位置：** 在 `"hermes-persona"` 顶层，`"dynamic"` 键之后（约第 51 行）插入两个新 section。

#### 7.1 新增内容

在 `"keywords": {}` 的闭合括号之后、`"variance"` 之前插入：

```json
    "expression_vector": {
      "enabled": true,
      "dimensions": {
        "work": ["代码", "架构", "Bug", "PR", "测试", "重构", "commit", "push", "部署"],
        "future": ["愿景", "十年后", "梦想", "未来", "规划"],
        "intimacy": ["陪伴", "累了", "一起", "温暖"]
      },
      "score_rules": {
        "work": [1, -0.5, 1],
        "future": [1, -1, 1],
        "intimacy": [1, -0.5, 3]
      },
      "reset": "session",
      "storage_path": "~/.hermes/profiles/{profile}/state/expression_vector.json"
    },
    "fixed_signals": {
      "message_length": {
        "enabled": true,
        "threshold": 50
      },
      "reply_gap": {
        "enabled": true,
        "threshold_minutes": 30,
        "storage_path": "~/.hermes/profiles/{profile}/state/reply_timing.json"
      }
    },
```

#### 7.2 验证

```bash
# JSON 格式合法
python -m json.tool examples/persona-config.json > /dev/null
# 期望: 无错误输出

# 使用新配置文件的集成测试
python -m pytest tests/test_injector.py -v
```

---

### Step 8: 编写集成测试

**目标：** 按照 SPEC-002 §10.7 测试矩阵，在 `test_injector.py` 中追加端到端集成测试。

**文件：** `tests/test_injector.py`（追加）

#### 8.1 测试类清单

| 测试类 | 对应 SPEC TC-IDs | 用例数 | 说明 |
|:---|:---|:---|:---|
| `TestExpressionVectorIntegration` | INT-EV-01~04 | 4 | 表达向量集成 |
| `TestFixedSignalsIntegration` | INT-FS-01~03 | 3 | 固定信号集成 |
| `TestFullIntegration` | INT-ALL-01~02 | 2 | 全链路集成 |

**共 9 个集成测试。**

#### 8.2 `TestExpressionVectorIntegration` 实现

```python
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
        result = injector.inject_context(
            **inject_context_defaults, user_message="写代码"
        )
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
```

#### 8.3 `TestFixedSignalsIntegration` 实现

```python
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
        result = injector.inject_context(
            **inject_context_defaults, user_message="好"
        )
        assert result is not None
        assert "📏 消息较短" in result["context"]

    def test_INT_FS02_long_gap_welcome_back(
        self, temp_config_root, write_config, inject_context_defaults
    ):
        """INT-FS-02: 长间隔 → 注入含 '🎵 欢迎回来'。"""
        import time as _time
        timing_path = str(temp_config_root / "reply_timing.json")
        # 写入一个 60 分钟前的时间戳
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
```

#### 8.4 `TestFullIntegration` 实现

```python
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
        result = injector.inject_context(
            **inject_context_defaults, user_message="写代码"
        )
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
        result = injector.inject_context(
            **inject_context_defaults, user_message="写代码"
        )
        assert result is not None
        ctx = result["context"]

        # dynamic (含 "首次交流") 在 expression_vector 之前
        pos_dynamic = ctx.find("首次交流")
        pos_ev = ctx.find("📊 [表达向量]")
        assert pos_dynamic < pos_ev, (
            f"dynamic ({pos_dynamic}) 应在 expression_vector ({pos_ev}) 之前"
        )
```

#### 8.5 验证

```bash
python -m pytest tests/test_injector.py -v -k "ExpressionVector or FixedSignal or Full"
# 期望: 9 passed
```

---

### Step 9: 全量回归测试

**目标：** 确保所有新旧测试全部通过。

**操作：**

```bash
# 运行全部测试
python -m pytest tests/ -v

# 期望输出:
# - test_expression_vector.py  31 passed
# - test_fixed_signals.py       9 passed
# - test_injector.py           全部 passed（含 9 个新增集成测试）
# - test_modules_switch.py     全部 passed（无回归）
# - test_dynamic_rules.py      全部 passed（无回归）
# - test_variance.py           全部 passed（如存在）
# - test_guard.py              全部 passed（如存在）
```

**验证标准：**
- 0 failure
- 0 error
- 现有测试无回归

---

## 3. 风险点与回滚方案

### 3.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|:---|:---|:---|:---|
| `turn_count` 提前计算后动态规则行为变化 | 低 | 高 | 值相同，仅计算时机提前；`_has_any_dynamic` 为 False 时之前不计算但现在也计算了——不影响后续步骤（turn_count 仅用于传参和④b格式化） |
| 磁盘 I/O 阻塞 `inject_context()` | 中 | 高 | 所有磁盘操作在 `try/except` 内；`OSError` 静默降级；表达向量有独立 `try/except` 双层保护 |
| `expression_vector.json` 并发写入 | 低 | 中 | 单进程单线程场景（`pre_llm_call` 同步调用）；多实例部署需外部锁（本轮不涉及） |
| `{profile}` 占位符未替换 → 路径无效 | 低 | 低 | `expanduser()` 后路径可能仍含 `{profile}` → `save()`/`load()` 降级为不持久化，不抛异常 |
| 旧配置文件缺少新 section → 行为变化 | 低 | 高 | `config.get("expression_vector", {})` + `config.get("fixed_signals", {})` → 缺失返回空 dict，跳过注入 |
| Debug 摘要新增行破坏现有测试断言 | 中 | 中 | Debug Mode 默认关闭（`debug: false`），不影响正常路径；仅 `TestDebugMode` 测试涉及 |
| `_debug_summary` 中 `import re` 在分支内 | 低 | 低 | 每次调用仅 import 一次（Python 缓存）；且仅在 debug=true 时触发 |
| 新增 `import time` 影响模块加载 | 极低 | 极低 | `time` 是 Python 标准库，无副作用 |

### 3.2 回滚方案

所有改动集中在 3 个源文件、3 个测试文件、1 个配置文件：

| 回滚方式 | 操作 |
|:---|:---|
| **Git 回滚（源码）** | `git checkout -- hermes_persona/injector.py examples/persona-config.json` |
| **删除新文件** | `rm hermes_persona/expression_vector.py tests/test_expression_vector.py tests/test_fixed_signals.py` |
| **完整回滚** | `git stash` 或 `git reset --hard HEAD` |

**关键安全边界：**
- `guard.py` 完全未触碰
- `__init__.py` 中的 Hook 注册逻辑不变
- `dynamic_rules.py` 不变（本轮不涉及子通道改动）
- `variance.py` 不变
- `modules` 体系不变——`expression_vector` 使用独立 `enabled` 字段，不走 `_is_enabled()` 路径
- `inject_context()` 外层 `try/except` 不变

---

## 4. 验证检查清单

实施完成后的最终验证：

### 4.1 自动化测试

- [ ] `python -m pytest tests/ -v` — 全部 PASSED，0 failure
- [ ] `test_expression_vector.py` — 31 个用例全部 PASSED（EV-01~14, RS-01~06, PERS-01~08, FMT-01~03）
- [ ] `test_fixed_signals.py` — 9 个用例全部 PASSED（FS-01~09）
- [ ] `test_injector.py` 新增集成测试 — 9 个用例全部 PASSED（INT-EV-01~04, INT-FS-01~03, INT-ALL-01~02）
- [ ] `test_modules_switch.py` — 全部 PASSED（无回归）
- [ ] `test_dynamic_rules.py` — 全部 PASSED（无回归）
- [ ] `test_variance.py` — 全部 PASSED（如存在，无回归）

### 4.2 手动验证

- [ ] `expression_vector` 不配置时插件正常运行
- [ ] `expression_vector.enabled: true` + 发送含关键词消息 → 注入含 `📊 [表达向量]`
- [ ] `expression_vector.enabled: false` → 不注入表达向量
- [ ] 连续发送 3 次含 "代码" 的消息 → work 维度值为 3
- [ ] 新 session → 向量清零（`reset: "session"`）
- [ ] `fixed_signals.message_length.enabled: true` + 短消息（< 50 字符）→ 注入含 `📏 消息较短`
- [ ] `fixed_signals.reply_gap.enabled: true` + 长间隔（> 30 分钟）→ 注入含 `🎵 欢迎回来`
- [ ] `fixed_signals` 不配置时插件正常运行
- [ ] 注入顺序正确：dynamic → fixed_signals → expression_vector → variance
- [ ] Debug 摘要包含 ④a/④b 状态行
- [ ] `expression_vector.json` 磁盘文件正确创建和更新
- [ ] `reply_timing.json` 磁盘文件正确创建和更新
- [ ] `persona-config.json` JSON 格式合法

### 4.3 代码审查

- [ ] `_ExpressionVector` 不在 `_MODULE_REGISTRY` 中注册（独立体系）
- [ ] `expression_vector` 使用独立 `enabled` 字段，不走 `_is_enabled()` 路径
- [ ] `inject_context()` 中表达向量块被独立 `try/except` 包裹（双层保护）
- [ ] 固定信号函数内部已处理所有异常（`_message_length_hint` 无 I/O，`_reply_gap_hint` / `_save_reply_timing` 内部 catch）
- [ ] `turn_count` 在步骤③之前计算，步骤④b 复用，值语义不变
- [ ] 所有磁盘操作（`load`/`save`/`reply_timing`）fail-open
- [ ] `format_inject()` 维度按字母序排列（`sorted()`），数值用 `int(round())`
- [ ] `_debug_summary()` 追加④a/④b 行时使用 `startswith` 检测（纯函数，不修改 `parts`）
- [ ] `import time` 新增在模块顶部，`import re` 仅在 debug 分支内使用
- [ ] `from .expression_vector import _ExpressionVector` 在模块顶部

### 4.4 文件变更总览

| 文件 | 操作 | 预估改动 |
|:---|:---|:---|
| `hermes_persona/expression_vector.py` | 新建 | ~115 行 |
| `hermes_persona/injector.py` | 修改 | +~70 行（3 函数 + inject_context 扩展 + debug 扩展） |
| `examples/persona-config.json` | 修改 | +~25 行 |
| `tests/test_expression_vector.py` | 新建 | ~250 行（31 测试） |
| `tests/test_fixed_signals.py` | 新建 | ~100 行（9 测试） |
| `tests/test_injector.py` | 追加 | ~150 行（9 集成测试） |
| **合计** | | **~710 行新增** |

---

*CC · 2026-05-19 · PLAN-002 v1.0（基于 US-002 v1.0 + SPEC-002 v1.0）· 等待审阅*
