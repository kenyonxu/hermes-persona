# PLAN-006: 表达向量诊断增强 — 实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**文档编号:** PLAN-006
**对应 US:** US-002 v1.0
**对应 SPEC:** SPEC-005 v1.0
**版本:** 1.0
**日期:** 2026-05-20
**作者:** 知惠（Zhihui）
**审阅:** Kai.Xu
**状态:** 📋 待审阅

**Goal:** 修复表达向量系统三个叠加缺陷 — 消息过滤拦截后台进程通知、词边界匹配消除英文短词子串误命中、比例衰减防止向量无限增长。

**Architecture:** 改动集中在 `expression_vector.py`（新增 `_is_background_message()` 函数 + `_count_keyword()` 方法 + `update()` 衰减步骤 + `__init__` 去重/解析）和 `injector.py`（过滤调用点 + import 更新）。不影响 dynamic_rules / guard / variance 等其他模块。

**Tech Stack:** Python 3.10+, `re` 标准库, pytest

---

## 目录

1. [总体时间估算](#1-总体时间估算)
2. [实施步骤](#2-实施步骤)
   - [Task 1: 消息过滤 — 判定函数实现](#task-1-消息过滤--判定函数实现)
   - [Task 2: 消息过滤 — 调用点集成](#task-2-消息过滤--调用点集成)
   - [Task 3: 词边界匹配 + 去重](#task-3-词边界匹配--去重)
   - [Task 4: 衰减机制](#task-4-衰减机制)
   - [Task 5: Config 升级 + 现有测试修复](#task-5-config-升级--现有测试修复)
   - [Task 6: 全量回归验证](#task-6-全量回归验证)
3. [风险点与回滚方案](#3-风险点与回滚方案)
4. [验证检查清单](#4-验证检查清单)

---

## 1. 总体时间估算

| Task | 内容 | 预估时间 |
|:---|:---|:---|
| Task 1 | 消息过滤 — 判定函数 + 测试 | 20 min |
| Task 2 | 消息过滤 — injector.py 集成 + 测试 | 10 min |
| Task 3 | 词边界匹配 `_count_keyword()` + 去重 + 测试 | 25 min |
| Task 4 | 衰减机制 + 向后兼容 + 测试 | 25 min |
| Task 5 | Config 四元组升级 + 现有测试修复 | 20 min |
| Task 6 | 全量回归验证 | 10 min |
| **合计** | | **~1 小时 50 分钟** |

### 依赖关系

```
Task 1 (判定函数) → Task 2 (集成)
Task 3 (词边界)   → 独立，可与 Task 1/2 并行
Task 4 (衰减)     → 独立，可与 Task 1/2/3 并行
Task 5 (Config + 测试修复) → 依赖 Task 3 & 4
Task 6 (回归)     → 依赖所有前置 Task
```

---

## 2. 实施步骤

### Task 1: 消息过滤 — 判定函数实现

**目标:** 在 `expression_vector.py` 中实现 `_is_background_message()` 判定函数，带完整测试。

**Files:**
- Modify: `expression_vector.py:1-16`（模块顶部添加常量 + 函数）
- Modify: `tests/test_expression_vector.py`（新增测试类）

#### Step 1: 编写测试用例

在 `tests/test_expression_vector.py` 末尾追加 `TestBackgroundMessageFilter` 类：

```python
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
        msg = "知惠早～我来啦～"
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
```

- [ ] **Step 1: 编写测试用例**

#### Step 2: 运行测试确认失败

```bash
python -m pytest tests/test_expression_vector.py::TestBackgroundMessageFilter -v
# 期望: 8 个 FAIL（函数未定义或导入失败）
```

- [ ] **Step 2: 运行测试确认失败**

#### Step 3: 实现 `_is_background_message()`

在 `expression_vector.py` 模块顶部（`import` 之后、`_ExpressionVector` 类之前）添加：

```python
# ── 后台消息过滤 ───────────────────────────────────────────────────────────

_BG_PREFIX = "[IMPORTANT: Background process"
_BG_SIGNATURES = ["claude -p", "Command:", "Output:", "exit code"]
_BG_MIN_LENGTH = 500
_BG_SIGNATURE_THRESHOLD = 2


def _is_background_message(msg: str) -> bool:
    """判断是否为后台进程完成通知（不应计入表达向量）。

    规则 A：前缀子串匹配 — 消息中包含 "[IMPORTANT: Background process"
    规则 B：长度 + 特征词密度 — len > 500 且 ≥ 2 个特征词命中
    OR 连接，命中任一规则返回 True。
    任何异常返回 False（fail-open）。
    """
    try:
        if _BG_PREFIX in msg:
            return True
        if len(msg) > _BG_MIN_LENGTH:
            sig_hits = sum(1 for sig in _BG_SIGNATURES if sig in msg)
            if sig_hits >= _BG_SIGNATURE_THRESHOLD:
                return True
        return False
    except Exception:
        return False
```

- [ ] **Step 3: 实现判定函数**

#### Step 4: 运行测试确认通过

```bash
python -m pytest tests/test_expression_vector.py::TestBackgroundMessageFilter -v
# 期望: 8 个 PASSED
```

- [ ] **Step 4: 运行测试确认通过**

#### Step 5: Commit

```bash
git add expression_vector.py tests/test_expression_vector.py
git commit -m "feat: 新增 _is_background_message() 后台消息过滤判定函数"
```

- [ ] **Step 5: Commit**

---

### Task 2: 消息过滤 — 调用点集成

**目标:** 在 `injector.py` 的 expression_vector 调用点添加过滤判定，后台消息跳过整个 load→update→save 流程。

**Files:**
- Modify: `injector.py:18,695-707`
- Modify: `tests/test_injector.py`（新增后台消息跳过测试）

#### Step 1: 编写集成测试

在 `tests/test_injector.py` 的 `TestExpressionVectorIntegration` 类中追加（文件顶部需添加 `from expression_vector import _ExpressionVector`）：

```python
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
```

- [ ] **Step 1: 编写集成测试**

#### Step 2: 修改 injector.py

**a) 更新 import 行（L18）：**

```python
# 改动前:
from expression_vector import _ExpressionVector

# 改动后:
from expression_vector import _ExpressionVector, _is_background_message
```

**b) 在 ④b 段（L695-707）添加过滤判定：**

```python
# ─── ④b Expression vector (FuzzyUtility) ─────────
ev_cfg = config.get("expression_vector", {})
if ev_cfg.get("enabled", False):
    try:
        profile = kwargs.get("profile_path", "")
        if not _is_background_message(user_message or ""):
            ev = _ExpressionVector(ev_cfg, profile_path=profile)
            ev.load()
            ev.update(user_message or "", session_id)
            ev.save()
            parts.append(ev.format_inject(turn_count))
    except Exception:
        pass  # fail-open：表达向量失败不阻断后续注入
# ──────────────────────────────────────────────────
```

- [ ] **Step 2: 修改 injector.py**

#### Step 3: 运行测试确认通过

```bash
python -m pytest tests/test_injector.py::TestExpressionVectorIntegration::test_INT_EV05_background_message_skipped -v
# 期望: PASSED
```

- [ ] **Step 3: 运行测试确认通过**

#### Step 4: Commit

```bash
git add injector.py tests/test_injector.py
git commit -m "feat: injector.py 表达向量调用前添加后台消息过滤"
```

- [ ] **Step 4: Commit**

---

### Task 3: 词边界匹配 + 去重

**目标:** 新增 `_count_keyword()` 方法替代 `str.count()`，对 ASCII 短词（≤4 字符）使用 `\b` 词边界正则。同时 `__init__` 加载关键词时自动去重。

**Files:**
- Modify: `expression_vector.py:78-95`（`update()` 中 L83-87 替换 + `__init__` 去重）
- Modify: `tests/test_expression_vector.py`（新增测试类 + 现有测试更新）

#### Step 1: 编写测试用例

在 `tests/test_expression_vector.py` 中追加：

```python
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
```

- [ ] **Step 1a: 编写词边界匹配测试**

追加去重测试到同一类：

```python
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
```

- [ ] **Step 1b: 编写去重测试**

#### Step 2: 运行测试确认失败

```bash
python -m pytest tests/test_expression_vector.py::TestKeywordCounting -v
# 期望: FAIL（_count_keyword 尚未实现 / 去重未实现）
```

- [ ] **Step 2: 运行测试确认失败**

#### Step 3: 实现 `_count_keyword()` + 去重

**a) 在 `_ExpressionVector` 类中添加 `_count_keyword()` 方法（放在 `update()` 之后）：**

```python
# 注意：expression_vector.py 顶部需添加 `import re`（标准库）

def _count_keyword(self, text: str, keyword: str) -> int:
    """根据关键词类型自动选择匹配策略。

    ASCII 短词（≤4 字符）→ \\b 词边界正则，避免子串误命中
    中文 / 长英文短语 → str.count() 子串匹配
    """
    try:
        if keyword.isascii() and len(keyword) <= 4:
            pattern = re.compile(
                r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE
            )
            return len(pattern.findall(text))
        return text.count(keyword.lower())
    except Exception:
        # 正则编译失败 → fallback 子串匹配
        return text.count(keyword.lower())
```

**b) 修改 `update()` L83-87，替换 `msg_lower.count(kw.lower())`：**

```python
# 改动前:
hit_count = sum(
    msg_lower.count(kw.lower())
    for kw in keywords
    if kw
)

# 改动后:
hit_count = sum(
    self._count_keyword(msg_lower, kw)
    for kw in keywords
    if kw
)
```

**c) 修改 `__init__()`，加载关键词时自动去重（在解析 dimensions 处）：**

```python
# 改动前 (L25-27):
if isinstance(keywords, list):
    self.dimensions[dim_name] = [str(k) for k in keywords]

# 改动后:
if isinstance(keywords, list):
    self.dimensions[dim_name] = list(dict.fromkeys(str(k) for k in keywords))
```

- [ ] **Step 3: 实现 _count_keyword() + 去重**

#### Step 4: 运行新测试 + 受影响的旧测试

```bash
# 新测试
python -m pytest tests/test_expression_vector.py::TestKeywordCounting -v
# 期望: 全部 PASSED

# 受影响的旧测试（EV-14 子串匹配、EV-13 大小写）
python -m pytest tests/test_expression_vector.py::TestUpdateAlgorithm::test_EV13_case_insensitive \
  tests/test_expression_vector.py::TestUpdateAlgorithm::test_EV14_substring_match -v
# 期望: PASSED（这些测试在词边界逻辑下仍应通过）
```

- [ ] **Step 4: 运行测试确认通过**

#### Step 5: Commit

```bash
git add expression_vector.py tests/test_expression_vector.py
git commit -m "feat: 词边界匹配 _count_keyword() + 关键词自动去重"
```

- [ ] **Step 5: Commit**

---

### Task 4: 衰减机制

**目标:** 在 `update()` 中命中/未命中叠加之前，先执行 `vector *= decay_factor`。`__init__` 解析 `score_rules` 的第四元，旧格式三元组自动补齐 `0.95`。

**Files:**
- Modify: `expression_vector.py:68-95`（`update()` + `__init__` score_rules 解析）
- Modify: `tests/test_expression_vector.py`（新增测试）

#### Step 1: 编写测试用例

在 `tests/test_expression_vector.py` 中追加：

```python
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
```

- [ ] **Step 1: 编写衰减测试**

#### Step 2: 运行测试确认失败

```bash
python -m pytest tests/test_expression_vector.py::TestDecay -v
# 期望: FAIL
```

- [ ] **Step 2: 运行测试确认失败**

#### Step 3: 实现衰减机制

**a) 修改 `__init__()` score_rules 解析（L29-44），支持第四元：**

```python
# 改动前:
self.score_rules[dim_name] = (
    float(raw[0]),
    float(raw[1]),
    float(raw[2]),
)

# 改为解析四元组，缺失第四元自动补齐:
try:
    vals = [float(raw[0]), float(raw[1]), float(raw[2])]
    decay = float(raw[3]) if len(raw) >= 4 else 0.95
    self.score_rules[dim_name] = (vals[0], vals[1], vals[2], decay)
except (ValueError, TypeError):
    self.score_rules[dim_name] = default_rule
```

**b) 更新 `default_rule`（L31）：**

```python
# 改动前:
default_rule = (1.0, -0.5, 1.0)

# 改动后:
default_rule = (1.0, -0.5, 1.0, 0.95)
```

**c) 修改 `update()` 维度循环（L78-95），在命中/未命中之前添加衰减步骤：**

```python
for dim_name, keywords in self.dimensions.items():
    hit_score, miss_penalty, weight, decay_factor = self.score_rules[dim_name]

    # 🆕 比例衰减
    self.vectors[dim_name] *= decay_factor

    # 计算该维度关键词命中次数
    hit_count = sum(
        self._count_keyword(msg_lower, kw)
        for kw in keywords
        if kw
    )

    if hit_count > 0:
        self.vectors[dim_name] += hit_score * hit_count * weight
    else:
        self.vectors[dim_name] += miss_penalty * weight

    # 永不跌破 0
    self.vectors[dim_name] = max(0.0, self.vectors[dim_name])
```

- [ ] **Step 3: 实现衰减机制**

#### Step 4: 运行测试确认通过

```bash
# 新衰减测试
python -m pytest tests/test_expression_vector.py::TestDecay -v
# 期望: 5 个 PASSED

# 验证向后兼容（旧格式三元组）
python -m pytest tests/test_expression_vector.py::TestUpdateAlgorithm::test_EV09_missing_score_rules \
  tests/test_expression_vector.py::TestUpdateAlgorithm::test_EV10_malformed_score_rules -v
# 期望: PASSED
```

- [ ] **Step 4: 运行测试确认通过**

#### Step 5: Commit

```bash
git add expression_vector.py tests/test_expression_vector.py
git commit -m "feat: 表达向量衰减机制 — update() 先衰减后叠加，score_rules 四元组向后兼容"
```

- [ ] **Step 5: Commit**

---

### Task 5: Config 升级 + 现有测试修复

**目标:** 更新用户配置文件中的 `score_rules` 为四元组，并修复因衰减介入而变值的现有测试。

**Files:**
- Modify: `persona-config.json`（score_rules 四元组）
- Modify: `tests/test_expression_vector.py`（修复受衰减影响的数值断言）

#### Step 1: 更新 persona-config.json

编辑用户配置文件 `~/.hermes/profiles/zhihui/persona-config.json`，找到 `hermes-persona.expression_vector.score_rules`，将每个维度的三元组扩展为四元组，追加 `0.95`。

> **注意：** 该配置文件已包含完整的 6 维度 expression_vector 配置（含 score_rules）。实际只需将三元组改为四元组。如果配置不存在，则从 `examples/persona-config.json` 复制 expression_vector 节后升级。

```json
"score_rules": {
  "intimacy": [1, -0.15, 3, 0.95],
  "care":     [1, -0.5,  2, 0.95],
  "work":     [1, -0.5,  1, 0.95],
  "future":   [1, -1,    1, 0.95],
  "play":     [1, -1,    1, 0.95],
  "eros":     [1, -2,    5, 0.95]
}
```

同步更新 `examples/persona-config.json` 中的 `expression_vector.score_rules`（若该文件仅有 3 维度 work/future/intimacy，只升级现有维度的三元组为四元组，不新增维度）。

- [ ] **Step 1: 更新 persona-config.json**

#### Step 2: 识别受影响测试

运行全量测试，确认哪些测试因衰减介入失败：

```bash
python -m pytest tests/test_expression_vector.py -v 2>&1 | grep -E "PASSED|FAILED"
```

受影响的主要是依赖精确浮点值的测试（如 `test_EV07` 期望 `work == 0.5`，衰减后约 0.25）。

- [ ] **Step 2: 识别受影响测试**

#### Step 3: 修复受影响测试

对于每个受影响的测试，重新计算期望值（考虑 `decay_factor=0.95` 的衰减效果），更新断言。

**示例修复 — test_EV07：**

```python
# 改动前（无衰减）:
def test_EV07_hit_then_miss_mix(self, ev):
    ev.update("写代码测试", "s1")   # work: 2 命中
    ev.update("天气不错", "s1")     # work: miss
    ev.update("写架构", "s1")       # work: 1 命中
    assert ev.vectors["work"] == 0.5  # 2 - 0.5 + 1 = 2.5? 不对...
    # 实际: 0 + 2 = 2; 2 - 0.5 = 1.5; 1.5 + 1 = 2.5? 这是旧行为

# 改动后（有衰减）:
def test_EV07_hit_then_miss_mix(self, ev):
    ev.update("写代码测试", "s1")   # work: 0*0.95 + 2 = 2.0
    ev.update("天气不错", "s1")     # work: 2.0*0.95 + (-0.5) = 1.4
    ev.update("写架构", "s1")       # work: 1.4*0.95 + 1 = 2.33
    assert ev.vectors["work"] == pytest.approx(2.33, rel=1e-9)
```

> **注意：** 精确值需逐条手动计算。用 `pytest.approx()` 替代 `==` 比较浮点值，提升健壮性。

- [ ] **Step 3: 修复受影响测试**

#### Step 4: 运行全量测试确认

```bash
python -m pytest tests/test_expression_vector.py -v
# 期望: 全部 PASSED
```

- [ ] **Step 4: 运行全量测试确认**

#### Step 5: Commit

```bash
git add tests/test_expression_vector.py
# 如果 persona-config.json 在 git 跟踪内则一并提交:
# git add persona-config.json  # 按实际路径调整
git commit -m "fix: persona-config score_rules 四元组升级 + 现有测试适配衰减机制"
```

- [ ] **Step 5: Commit**

---

### Task 6: 全量回归验证

**目标:** 运行全部测试，确认无回归。

#### Step 1: 运行全部测试

```bash
python -m pytest tests/ -v
# 期望: 全部 PASSED
```

- [ ] **Step 1: 运行全量测试**

#### Step 2: 手动验证表达向量文件

```bash
# 观察 expression_vector.json 中 work 值是否不再异常
cat ~/.hermes/profiles/zhihui/state/expression_vector.json | python3 -m json.tool | grep -A2 work
```

- [ ] **Step 2: 手动验证**

#### Step 3: 检查 trace 日志

```bash
tail -20 /tmp/hermes_persona_trace.log
# 确认 inject_context 正常执行，无异常
```

- [ ] **Step 3: 检查 trace 日志**

#### Step 4: 最终 Commit（如有修正确认）

```bash
git status
# 确认工作区干净
```

- [ ] **Step 4: 确认工作区干净**

---

## 3. 风险点与回滚方案

| 风险 | 影响 | 缓解措施 | 回滚方式 |
|:---|:---|:---|:---|
| 衰减导致现有测试数值断言失败 | 测试红灯 | Task 5 逐条修复，用 `pytest.approx()` | `git revert` 最后一个 commit |
| 词边界正则遗漏合法命中 | 表达向量灵敏度下降 | 仅对 ≤4 字符 ASCII 词启用，中文不受影响 | 将 `len(keyword) <= 4` 改为 `<= 2` |
| 消息过滤误判正常消息 | 表达向量漏更新 | 双规则 OR，实测零误伤 | 提高 `_BG_MIN_LENGTH` 到 800 |
| 正则编译性能 | `re.compile()` 每轮每个关键词调用一次 | 短正则编译开销极小（<1μs） | 缓存编译后的 pattern 到 dict |

---

## 4. 验证检查清单

- [ ] `_is_background_message()` 正确拦截所有 6 种已知后台消息格式
- [ ] 正常消息零误伤（已验证实际数据）
- [ ] `"PR"` 不再匹配 `"process"`、`"approach"`
- [ ] `"git"` 不再匹配 `"legitimate"`
- [ ] 中文关键词（`"代码"`）保持子串匹配
- [ ] 长英文短语（`"hermes-persona"`）保持子串匹配
- [ ] 重复关键词自动去重（`"修复"` 只保留一个）
- [ ] 衰减默认 `0.95`，每轮先乘后叠加
- [ ] 旧格式三元组自动补齐 `decay_factor=0.95`
- [ ] `decay_factor=1.0` 等价于关闭衰减（旧行为保留）
- [ ] 全量测试 PASSED（232+ 条）
