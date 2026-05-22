# expression_vector / fixed_signals 模块开关接入 — 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 SPEC-001 遗漏——将 `expression_vector` 和 `fixed_signals` 接入模块开关系统，使 `modules` 配置中对它们的开关真正生效。

**Architecture:** 在 `_MODULE_REGISTRY` 中补注册两条目，在 `inject_context()` 中为两个模块加上 `_is_enabled()` 守卫。`expression_vector` 采用双重检查（模块开关 AND 功能开关）。`fixed_signals` 作为整块的总开关。改动仅限 `injector.py` 和 `README.md`。

**Tech Stack:** Python 3.10+, pytest

---

### Task 1: 注册表 + 守卫实现

**Files:**
- Modify: `injector.py:53-110`（`_MODULE_REGISTRY`）
- Modify: `injector.py:1098-1132`（④a fixed_signals 块）
- Modify: `injector.py:1201-1203`（④b expression_vector 块）

- [ ] **Step 1: 在 `_MODULE_REGISTRY` 中新增两个条目**

在 `_MODULE_REGISTRY` 的 `"variance"` 条目之前插入（按 phase 4 归组）：

```python
"fixed_signals": {
    "description": "固定信号检测（消息长度 / 回复间隔 / 每日轮数）",
    "default": True,
    "phase": 4,
    "legacy_key": None,
    "legacy_path": None,
},
"expression_vector": {
    "description": "多维度表达向量追踪与注入",
    "default": False,
    "phase": 4,
    "legacy_key": "expression_vector",
    "legacy_path": ("expression_vector", "enabled"),
},
```

- [ ] **Step 2: 用 `_is_enabled()` 包裹 fixed_signals 整块**

在 `inject_context()` 中，在 `fixed_cfg = config.get("fixed_signals", {})` 之前添加守卫，将 translate 和非 translate 两条路径全部包在 `if` 内：

```python
# ─── ④a Fixed signals ────────────────────────────
if _is_enabled(modules, "fixed_signals"):
    fixed_cfg = config.get("fixed_signals", {})

    if _translate_mode:
        # ... 现有 translate 模式 fixed_signals 逻辑保持不变 ...
    else:
        # ... 现有非 translate 模式 fixed_signals 逻辑保持不变 ...
# ──────────────────────────────────────────────────
```

- [ ] **Step 3: expression_vector 改用 `_is_enabled()` 守卫**

将现有的：
```python
if ev_cfg.get("enabled", False):
```
改为双重检查：
```python
if _is_enabled(modules, "expression_vector") and ev_cfg.get("enabled", False):
```

- [ ] **Step 4: 验证改动后的 `inject_context()` 结构**

确认注入顺序为：
```
① time
② static_rules
③ dynamic
④a fixed_signals   ← 新增守卫
④b expression_vector ← 改用 _is_enabled
⑤ variance
⑥ memory
⑦ kanban
⑧ translate (narrative assembly)
⑨ debug
```

### Task 2: 测试

**Files:**
- Modify: `tests/test_modules_switch.py`

- [ ] **Step 1: 添加 expression_vector 模块开关测试**

```python
def test_expression_vector_module_switch_off(self, write_config, inject_context_defaults):
    """INT-EV-01: modules.expression_vector=False 时不初始化 EV。"""
    write_config({
        "modules": {"expression_vector": False},
        "expression_vector": {
            "enabled": True,
            "dimensions": {
                "work": {"label": "工作", "keywords": ["代码"], "score_rules": [1, -0.5, 1, 0.95]}
            },
            "reset": "session",
            "storage_path": "",
        },
    })
    result = inject_context_defaults(user_message="写代码")
    # EV 不初始化，context 中无表达向量相关内容
    assert result is None or "表达向量" not in result.get("context", "")


def test_expression_vector_func_switch_off(self, write_config, inject_context_defaults):
    """INT-EV-02: modules 开但 expression_vector.enabled=False 时不初始化 EV。"""
    write_config({
        "modules": {"expression_vector": True},
        "expression_vector": {
            "enabled": False,
            "dimensions": {
                "work": {"label": "工作", "keywords": ["代码"], "score_rules": [1, -0.5, 1, 0.95]}
            },
            "reset": "session",
            "storage_path": "",
        },
    })
    result = inject_context_defaults(user_message="写代码")
    assert result is None or "表达向量" not in result.get("context", "")


def test_fixed_signals_module_switch_off(self, write_config, inject_context_defaults):
    """INT-FS-01: modules.fixed_signals=False 时跳过所有固定信号。"""
    write_config({
        "modules": {"fixed_signals": False},
        "fixed_signals": {
            "message_length": {"enabled": True, "threshold": 50},
            "reply_gap": {"enabled": True, "threshold_minutes": 30},
            "daily_turn_count": {"enabled": True, "thresholds": {"morning": 10}, "storage_path": ""},
        },
    })
    result = inject_context_defaults(user_message="hi", is_first_turn=True)
    context = result.get("context", "") if result else ""
    assert "消息较短" not in context
    assert "欢迎回来" not in context
    assert "今日第" not in context
```

- [ ] **Step 2: 运行新增测试确认失败**

```bash
python -m pytest tests/test_modules_switch.py::TestModuleSwitchIntegration::test_expression_vector_module_switch_off -v
python -m pytest tests/test_modules_switch.py::TestModuleSwitchIntegration::test_fixed_signals_module_switch_off -v
```
期望：FAIL（守卫尚未接入）

- [ ] **Step 3: 实施 Task 1 的代码改动后运行测试确认通过**

```bash
python -m pytest tests/test_modules_switch.py -v
```
期望：全部 PASS

- [ ] **Step 4: 全量回归**

```bash
python -m pytest tests/ -v
```
期望：全部 PASS

### Task 3: README 回退

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 恢复 §1 modules 表中的两行**

在 `variance` 和 `memory` 之间恢复：
```markdown
| `expression_vector` | bool | 多维度表达向量 |
| `fixed_signals` | bool | 固定信号检测 |
```

- [ ] **Step 2: 恢复 §1 JSON 示例中的两行**

在 `"variance": true,` 之后恢复：
```json
      "expression_vector": true,
      "fixed_signals": true,
```

### Task 4: 提交

- [ ] **Step 1: 提交所有改动**

```bash
git add injector.py tests/test_modules_switch.py README.md
git commit -m "$(cat <<'EOF'
fix: expression_vector / fixed_signals 接入模块开关系统

SPEC-001 遗漏修复：两个模块在 modules 配置中声明但未接入
_is_enabled() 守卫，用户开关不生效。在 _MODULE_REGISTRY 补注册，
inject_context() 加守卫。expression_vector 采用双重检查（模块开关
AND 功能开关），fixed_signals 作为整块总开关。
EOF
)"
```

---

*Kai.Xu · 2026-05-22 · PLAN-011*
