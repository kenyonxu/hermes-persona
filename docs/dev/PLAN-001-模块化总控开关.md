# PLAN-001: 模块化总控开关 — 实施计划

**文档编号:** PLAN-001
**对应 US:** US-001
**对应 SPEC:** SPEC-001
**版本:** 1.1
**日期:** 2026-05-18
**修订:** v1.1 新增 Debug Mode 实施步骤（对应 SPEC-001 v1.1 §2.5）
**作者:** 知惠（Zhihui）
**审阅:** Kai.Xu
**状态:** 📋 待审阅

---

## 目录

1. [总体时间估算](#1-总体时间估算)
2. [实施步骤](#2-实施步骤)
    - [Step 0: 环境准备与基线验证](#step-0-环境准备与基线验证)
    - [Step 1: 测试先行 — 编写 test_modules_switch.py](#step-1-测试先行--编写-test_modules_switchpy)
    - [Step 2: 实现 _MODULE_REGISTRY 常量](#step-2-实现-_module_registry-常量)
    - [Step 3: 实现 _resolve_modules()](#step-3-实现-_resolve_modules)
    - [Step 4: 实现 _is_enabled()](#step-4-实现-_is_enabled)
    - [Step 5: 实现 _has_any_dynamic()](#step-5-实现-_has_any_dynamic)
    - [Step 6: 修改 inject_context() 六个注入步骤](#step-6-修改-inject_context-六个注入步骤)
    - [Step 7: 修改 _select_dynamic_rules() 子通道控制](#step-7-修改-_select_dynamic_rules-子通道控制)
    - [Step 8: 更新 examples/persona-config.json](#step-8-更新-examplespersona-configjson)
    - [Step 9: 全量回归测试](#step-9-全量回归测试)
    - [Step 10: 更新 dynamic_rules.py 测试（可选补充）](#step-10-更新-dynamic_rulespy-测试可选补充)
    - [Step 11: 实现 Debug Mode（v1.1 新增）](#step-11-实现-debug-modev11-新增)
3. [风险点与回滚方案](#3-风险点与回滚方案)
4. [验证检查清单](#4-验证检查清单)

---

## 1. 总体时间估算

| 步骤 | 内容 | 预估时间 |
|:---|:---|:---|
| Step 0 | 环境准备与基线验证 | 5 min |
| Step 1 | 编写 test_modules_switch.py（TDD） | 45 min |
| Step 2 | 实现 _MODULE_REGISTRY | 5 min |
| Step 3 | 实现 _resolve_modules() | 10 min |
| Step 4 | 实现 _is_enabled() | 5 min |
| Step 5 | 实现 _has_any_dynamic() | 5 min |
| Step 6 | 修改 inject_context() 六个步骤 | 15 min |
| Step 7 | 修改 _select_dynamic_rules() | 10 min |
| Step 8 | 更新 examples/persona-config.json | 5 min |
| Step 9 | 全量回归测试 | 10 min |
| Step 10 | 补充测试 + 收尾 | 10 min |
| Step 11 | 实现 Debug Mode（_debug_summary + 辅助函数 + 测试） | 20 min |
| **合计** | | **~2 小时 15 分钟** |

---

## 2. 实施步骤

### Step 0: 环境准备与基线验证

**目标：** 确保当前分支代码干净，所有现有测试通过。

**操作：**

```bash
# 确认在 feature/001-module-switch 分支
git branch --show-current
# 期望: feature/001-module-switch

# 运行全部测试，确认基线通过
python -m pytest tests/ -v
# 期望: 全部 PASSED
```

**验证标准：**
- `git status` 显示干净工作区
- `python -m pytest tests/ -v` 全部通过，0 failure

**回滚：** 无需回滚（尚未改动代码）

---

### Step 1: 测试先行 — 编写 test_modules_switch.py

**目标：** 按照 SPEC §6 测试矩阵，编写所有测试用例。此时代码尚未改动，所有新测试应 **FAIL**（红色阶段）。

**文件：** `tests/test_modules_switch.py`（新建）

#### 1.1 导入与 fixtures

```python
"""Tests for module switch system — _MODULE_REGISTRY, _resolve_modules,
_is_enabled, _has_any_dynamic, and integration tests for each module."""

from unittest.mock import patch

import pytest

import hermes_persona.injector as injector
```

无需额外 fixture，复用 `conftest.py` 中的 `temp_config_root`、`write_config`、`inject_context_defaults`。

#### 1.2 测试类清单

| 测试类 | 对应 SPEC 测试组 | 用例数 | 说明 |
|:---|:---|:---|:---|
| `TestModuleRegistry` | — | 2 | 验证注册表结构和完整性（含 debug 模块） |
| `TestResolveModules` | §6.1.1 (RES-01~07) | 7 | `_resolve_modules()` 单元测试 |
| `TestIsEnabled` | §6.1.2 (IS-01~06) | 6 | `_is_enabled()` 单元测试 |
| `TestHasAnyDynamic` | §6.1.3 (DYN-01~05) | 5 | `_has_any_dynamic()` 单元测试 |
| `TestModuleSwitchIntegration` | §6.1.4 (INT-01~15) | 15 | 每个模块 on/off 集成测试 |
| `TestDebugMode` | §6.1.4 (INT-16~19) | 4 | Debug Mode 开关与摘要验证 |
| `TestBackwardCompatibility` | §6.1.5 (BC-01~05) | 5 | 向后兼容集成测试 |
| `TestEdgeCases` | §6.1.6 (EDGE-01~04) | 4 | 边界测试 |

**共 ~48 个测试用例。**

#### 1.3 关键测试实现要点

**`TestModuleRegistry`：**
```python
class TestModuleRegistry:
    def test_all_expected_modules_registered(self):
        """_MODULE_REGISTRY 必须包含 7 个模块键（含 debug）。"""
        registry = injector._MODULE_REGISTRY
        expected_keys = {"time", "static_rules", "dynamic", "variance", "memory", "kanban", "debug"}
        assert set(registry.keys()) == expected_keys

    def test_each_module_has_required_fields(self):
        """每个注册项必须包含 description, default, phase 字段。"""
        for key, meta in injector._MODULE_REGISTRY.items():
            assert "description" in meta, f"{key} missing description"
            assert "default" in meta, f"{key} missing default"
            assert "phase" in meta, f"{key} missing phase"
```

**`TestResolveModules` — 关键用例：**
```python
class TestResolveModules:
    def test_new_format_priority(self):
        """modules 键存在时直接使用，不读取旧格式。"""
        ...

    def test_legacy_synthesis_time_disabled(self):
        """旧格式 time.enabled=false → modules["time"]=False。"""
        ...

    def test_legacy_synthesis_project_to_kanban(self):
        """旧格式 project.enabled=true → modules["kanban"]=True。"""
        ...

    def test_empty_config_falls_back_to_defaults(self):
        """config={} → 所有模块使用 _MODULE_REGISTRY 的 default 值。"""
        ...
```

**`TestModuleSwitchIntegration` — 关键用例：**
```python
class TestModuleSwitchIntegration:
    def test_time_disabled_no_time_context(self):
        """modules.time=false → 结果不含 🕐。"""
        with patch("hermes_persona.injector._load_config", return_value={
            "modules": {"time": False},
            "time": {"format": "cn_full"},
        }):
            result = injector.inject_context(**defaults)
            if result is not None:
                assert "🕐" not in result["context"]

    def test_static_rules_disabled_no_rules(self):
        """modules.static_rules=false，context.rules 有内容 → 不含规则。"""
        ...

    def test_dynamic_parent_disabled(self):
        """modules.dynamic=false → 不含任何 dynamic 规则。"""
        ...

    def test_dynamic_only_time_slots_disabled(self):
        """仅关 time_slots，turn_stage + keyword 仍生效。"""
        ...

    def test_memory_disabled_not_called(self):
        """modules.memory=false → _recall_memories 不被调用。"""
        with patch("hermes_persona.injector._recall_memories") as mock_recall:
            ...

    def test_kanban_disabled_not_injected(self):
        """is_first_turn=True, modules.kanban=false → 不含看板。"""
        ...

    def test_all_modules_disabled_returns_none(self):
        """全部关闭 → inject_context 返回 None。"""
        ...
```

**`TestDebugMode` — 关键用例（v1.1 新增）：**
```python
class TestDebugMode:
    def test_debug_disabled_no_summary(self):
        """modules.debug=false（默认）→ context 中不含 🔧 [Debug]。"""
        ...

    def test_debug_enabled_appends_summary(self):
        """modules.debug=true → context 末尾含 🔧 [Debug] 本轮注入:，且包含①~⑥行。"""
        ...

    def test_debug_only_all_modules_off_returns_none(self):
        """全部模块关闭，仅 debug 开启 → 返回 None（debug 摘要不参与空判断）。"""
        ...

    def test_debug_memory_disabled_shows_stopped(self):
        """debug=true, memory=false → 摘要中 memory 行显示 🧠 已停用。"""
        ...
```

**`TestBackwardCompatibility` — 关键用例：**
```python
class TestBackwardCompatibility:
    def test_legacy_time_enabled_false_works(self):
        """无 modules 键，time.enabled=false → time 不注入。"""
        config = {"time": {"enabled": False}}
        ...

    def test_legacy_memory_enabled_true_works(self):
        """无 modules 键，memory.enabled=true → memory 被调用。"""
        ...

    def test_modules_wins_over_legacy(self):
        """同时有 modules.time=true 和 time.enabled=false → modules 优先。"""
        config = {
            "modules": {"time": True},
            "time": {"enabled": False},
        }
        ...
```

#### 1.4 操作

```bash
# 创建测试文件
touch tests/test_modules_switch.py
# 写入所有 48 个测试用例

# 验证测试文件可以被 pytest 发现（预期全部 FAIL）
python -m pytest tests/test_modules_switch.py -v
# 期望: 大量 FAILED（因为函数尚未实现）
```

**验证标准：**
- 测试文件可被 pytest 发现（无 import 错误）
- 所有新测试 FAIL（红色阶段），而非 ERROR（语法/导入错误不算）
- 现有测试仍全部 PASS（`tests/test_injector.py`、`tests/test_dynamic_rules.py` 等不受影响）

---

### Step 2: 实现 _MODULE_REGISTRY 常量

**目标：** 在 `injector.py` 中添加模块注册表常量，使 Step 1 的 `TestModuleRegistry` 测试通过。

**文件：** `hermes_persona/injector.py`

**位置：** 在 `_CONFIG_ROOT` 之后、`_load_config()` 之前（约第 20 行之后）

**改动内容：** 新增常量（~30 行）

```python
# ---------------------------------------------------------------------------
# Module registry
# ---------------------------------------------------------------------------

_MODULE_REGISTRY: dict[str, dict] = {
    "time": {
        "description": "时间上下文注入",
        "default": True,
        "phase": 1,
        "legacy_key": "time",
        "legacy_path": ("time", "enabled"),
    },
    "static_rules": {
        "description": "静态规则注入（context.rules + rules_first_turn_only）",
        "default": True,
        "phase": 2,
        "legacy_key": None,
        "legacy_path": None,
    },
    "dynamic": {
        "description": "动态规则总开关（任一子通道开启时才进入）",
        "default": True,
        "phase": 3,
        "legacy_key": None,
        "legacy_path": None,
    },
    "variance": {
        "description": "随机表达变化注入",
        "default": True,
        "phase": 4,
        "legacy_key": None,
        "legacy_path": None,
    },
    "memory": {
        "description": "记忆召回注入",
        "default": False,
        "phase": 5,
        "legacy_key": "memory",
        "legacy_path": ("memory", "enabled"),
    },
    "kanban": {
        "description": "看板状态注入（仅首轮）",
        "default": False,
        "phase": 6,
        "legacy_key": "project",
        "legacy_path": ("project", "enabled"),
    },
    "debug": {
        "description": "Debug Mode — 在注入上下文末尾追加人类可读的注入摘要",
        "default": False,
        "phase": 7,
        "legacy_key": None,
        "legacy_path": None,
    },
}
```

**验证标准：**
```bash
python -m pytest tests/test_modules_switch.py::TestModuleRegistry -v
# 期望: 2 passed
```

---

### Step 3: 实现 _resolve_modules()

**目标：** 实现新/旧格式配置解析函数。使 `TestResolveModules` 测试组通过。

**文件：** `hermes_persona/injector.py`

**位置：** 在 `_MODULE_REGISTRY` 之后、`_load_config()` 之后（约第 51 行之后）

**改动内容：** 新增函数（~25 行）

```python
def _resolve_modules(config: dict) -> dict:
    """解析 modules 配置，优先新格式，回退旧格式合成。

    返回值始终为 dict（保证调用方无需判空）。
    """
    try:
        modules = config.get("modules")
        if isinstance(modules, dict):
            return modules

        synthesized: dict[str, bool] = {}
        for key, meta in _MODULE_REGISTRY.items():
            lp = meta.get("legacy_path")
            if lp:
                section = config.get(lp[0])
                if isinstance(section, dict):
                    synthesized[key] = section.get(lp[1], meta["default"])
                else:
                    synthesized[key] = meta["default"]
            else:
                synthesized[key] = meta["default"]
        return synthesized
    except Exception:
        return {}
```

**验证标准：**
```bash
python -m pytest tests/test_modules_switch.py::TestResolveModules -v
# 期望: 7 passed
```

---

### Step 4: 实现 _is_enabled()

**目标：** 实现模块开关查询函数。使 `TestIsEnabled` 测试组通过。

**文件：** `hermes_persona/injector.py`

**位置：** 在 `_resolve_modules()` 之后

**改动内容：** 新增函数（~10 行）

```python
def _is_enabled(modules: dict, key: str) -> bool:
    """判断指定模块是否启用。

    Args:
        modules: _resolve_modules() 返回的开关字典。
        key:    模块键名。

    Returns:
        bool: 模块是否启用。key 不在 modules 中时回退注册表 default。
              key 不在注册表中时返回 True（fail-open）。
    """
    if key in modules:
        val = modules[key]
        if isinstance(val, dict):
            return True
        return bool(val)
    return _MODULE_REGISTRY.get(key, {}).get("default", True)
```

**验证标准：**
```bash
python -m pytest tests/test_modules_switch.py::TestIsEnabled -v
# 期望: 6 passed
```

---

### Step 5: 实现 _has_any_dynamic()

**目标：** 实现 dynamic 子通道聚合判断函数。使 `TestHasAnyDynamic` 测试组通过。

**文件：** `hermes_persona/injector.py`

**位置：** 在 `_is_enabled()` 之后

**改动内容：** 新增函数（~15 行）

```python
def _has_any_dynamic(modules: dict) -> bool:
    """判断 dynamic 模块的子通道中是否至少有一个开启。

    仅当父开关和至少一个子通道同时开启时返回 True。
    """
    if not _is_enabled(modules, "dynamic"):
        return False

    dyn = modules.get("dynamic", {})
    if isinstance(dyn, dict):
        return (
            dyn.get("time_slots", True)
            or dyn.get("turn_stage", True)
            or dyn.get("keyword", True)
        )
    return True
```

**验证标准：**
```bash
python -m pytest tests/test_modules_switch.py::TestHasAnyDynamic -v
# 期望: 5 passed
```

---

### Step 6: 修改 inject_context() 六个注入步骤

**目标：** 为 `inject_context()` 每个注入步骤添加 `_is_enabled()` / `_has_any_dynamic()` 守卫。使 `TestModuleSwitchIntegration` 和 `TestBackwardCompatibility` 测试组通过。

**文件：** `hermes_persona/injector.py`

**位置：** `inject_context()` 函数体内

**改动详情：**

#### 6.1 在 `config = _load_config()` 之后插入 modules 解析

```python
# 原代码（约第 230 行）:
config = _load_config()
parts: list[str] = []

# 改为:
config = _load_config()
modules = _resolve_modules(config)          # ← 新增
parts: list[str] = []
```

#### 6.2 Step ① Time — 替换旧开关

```python
# 原代码（约第 233-237 行）:
time_cfg = config.get("time", {})
if time_cfg.get("enabled", True) is not False:
    fmt = time_cfg.get("format", "cn_full")
    parts.append(_time_context(fmt))

# 改为:
if _is_enabled(modules, "time"):
    time_cfg = config.get("time", {})
    fmt = time_cfg.get("format", "cn_full")
    parts.append(_time_context(fmt))
```

#### 6.3 Step ② Static Rules — 新增守卫

```python
# 原代码（约第 239-241 行）:
ctx_cfg = config.get("context", {})
parts.extend(_inject_static_rules(ctx_cfg, is_first_turn))

# 改为:
if _is_enabled(modules, "static_rules"):
    ctx_cfg = config.get("context", {})
    parts.extend(_inject_static_rules(ctx_cfg, is_first_turn))
```

#### 6.4 Step ③ Dynamic Rules — 替换守卫 + 传入 modules

```python
# 原代码（约第 243-253 行）:
turn_count = len(conversation_history or []) // 2
dynamic_cfg = config.get("dynamic", {})
parts.extend(
    _select_dynamic_rules(
        dynamic_cfg,
        user_message,
        is_first_turn,
        turn_count,
    )
)

# 改为:
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

#### 6.5 Step ④ Variance — 新增守卫

```python
# 原代码（约第 255-256 行）:
parts.extend(_randomize_variance(config.get("variance", {})))

# 改为:
if _is_enabled(modules, "variance"):
    parts.extend(_randomize_variance(config.get("variance", {})))
```

#### 6.6 Step ⑤ Memory — 替换内联检查

```python
# 原代码（约第 258-262 行）:
mem_cfg = config.get("memory", {})
memories = _recall_memories(user_message, mem_cfg)
if memories is not None:
    parts.append(memories)

# 改为:
if _is_enabled(modules, "memory"):
    mem_cfg = config.get("memory", {})
    memories = _recall_memories(user_message, mem_cfg)
    if memories is not None:
        parts.append(memories)
```

**注意：** `_recall_memories()` 内部仍有自己的 `enabled` / `api_url` 检查。`modules.memory` 关闭时整块跳过，开启时 `_recall_memories()` 内部再做细粒度检查。这形成两层防护。

#### 6.7 Step ⑥ Kanban — 合并 + 替换守卫

```python
# 原代码（约第 264-273 行）:
if is_first_turn:
    project_cfg = config.get("project", {})
    if project_cfg.get("enabled"):
        kanban = _read_kanban(
            project_cfg.get("kanban_path", ""),
            project_cfg.get("label", ""),
        )
        if kanban is not None:
            parts.append(kanban)

# 改为:
if is_first_turn and _is_enabled(modules, "kanban"):
    project_cfg = config.get("project", {})
    kanban = _read_kanban(
        project_cfg.get("kanban_path", ""),
        project_cfg.get("label", ""),
    )
    if kanban is not None:
        parts.append(kanban)
```

#### 6.8 Step ⑦ Debug — 末尾追加摘要 + 空判断修正（v1.1 新增）

```python
# 在步骤⑥ kanban 之后、return 之前插入:

# 记录非 debug 内容的数量（用于空判断）
non_debug_count = len(parts)

# ⑦ Debug summary（不参与空判断，默认关闭）
if _is_enabled(modules, "debug"):
    parts.append(_debug_summary(modules, parts))

# 空判断基于非 debug 内容（debug 摘要不参与）
if non_debug_count == 0:
    return None
return {"context": "\n\n".join(parts)}
```

**关键设计点：**
- `non_debug_count = len(parts)` 在 debug 注入前记录，确保 debug 摘要不参与空判断。
- 若所有模块关闭仅 debug 开启 → `non_debug_count == 0` → 返回 `None`（符合 SPEC §2.5.4）。
- 若正常模块有注入 + debug 开启 → context 末尾追加摘要。

**验证标准：**
```bash
python -m pytest tests/test_modules_switch.py::TestModuleSwitchIntegration -v
python -m pytest tests/test_modules_switch.py::TestDebugMode -v
python -m pytest tests/test_modules_switch.py::TestBackwardCompatibility -v
# 期望: 15 + 4 + 5 = 24 passed

---

### Step 7: 修改 _select_dynamic_rules() 子通道控制

**目标：** 在 `_select_dynamic_rules()` 中添加 `modules` 参数和子通道守卫。使相关的集成测试和 dynamic_rules 子通道测试通过。

**文件：** `hermes_persona/dynamic_rules.py`

**改动详情：**

#### 7.1 函数签名增加 modules 参数

```python
# 原代码（约第 10-15 行）:
def _select_dynamic_rules(
    dynamic_cfg: dict,
    user_message: str,
    is_first_turn: bool,
    turn_count: int,
) -> list[str]:

# 改为:
def _select_dynamic_rules(
    dynamic_cfg: dict,
    user_message: str,
    is_first_turn: bool,
    turn_count: int,
    modules: dict | None = None,       # ← 新增
) -> list[str]:
```

#### 7.2 三个子通道添加守卫

```python
# 原代码（约第 21-27 行）:
rules: list[str] = []
rules.extend(_match_time_slot(dynamic_cfg.get("time_slots", {})))
rules.extend(
    _match_turn_stage(dynamic_cfg.get("turn_stage", {}), is_first_turn, turn_count)
)
rules.extend(_match_keyword(dynamic_cfg.get("keywords", {}), user_message))
return rules

# 改为:
rules: list[str] = []

# time_slots — modules 未传入时默认开启
if modules is None or modules.get("time_slots", True):
    rules.extend(_match_time_slot(dynamic_cfg.get("time_slots", {})))

# turn_stage — modules 未传入时默认开启
if modules is None or modules.get("turn_stage", True):
    rules.extend(
        _match_turn_stage(dynamic_cfg.get("turn_stage", {}), is_first_turn, turn_count)
    )

# keyword — modules 未传入时默认开启
if modules is None or modules.get("keyword", True):
    rules.extend(_match_keyword(dynamic_cfg.get("keywords", {}), user_message))

return rules
```

**关键设计点：** `modules is None` 条件确保现有测试（不传 `modules` 参数）行为完全不变。

**验证标准：**
```bash
# 现有 dynamic_rules 测试必须全部通过（modules=None 路径）
python -m pytest tests/test_dynamic_rules.py -v

# 子通道开关集成测试也必须通过
python -m pytest tests/test_modules_switch.py -v -k "dynamic"
# 期望: 全部 PASSED
```

---

### Step 8: 更新 examples/persona-config.json

**目标：** 在示例配置文件中添加 `modules` 键，展示新格式用法。

**文件：** `examples/persona-config.json`

**改动内容：** 在 `"hermes-persona"` 顶层新增 `"modules"` 键，位于 `"time"` 之前。

```json
"modules": {
  "time": true,
  "static_rules": true,
  "dynamic": {
    "time_slots": true,
    "turn_stage": true,
    "keyword": true
  },
  "variance": true,
  "memory": false,
  "kanban": true,
  "debug": false
},
```

**注意：** `memory` 默认 `false`（匹配旧配置行为），`kanban` 改为 `true`（展示使用示例）。其余默认 `true`。旧格式的 `time.enabled`、`memory.enabled`、`project.enabled` 保留不动（向后兼容）。

**验证标准：**
- JSON 格式合法（可用 `python -m json.tool` 验证）
- 加载后 `modules` 键存在且格式正确
- 向后兼容测试 BC-05（使用当前配置文件内容）仍通过

---

### Step 9: 全量回归测试

**目标：** 确保所有新增测试通过，且所有现有测试不受影响。

**操作：**

```bash
# 运行全部测试
python -m pytest tests/ -v

# 期望输出:
# - tests/test_injector.py    全部 PASSED
# - tests/test_dynamic_rules.py 全部 PASSED
# - tests/test_variance.py     全部 PASSED（如存在）
# - tests/test_guard.py        全部 PASSED（如存在）
# - tests/test_modules_switch.py 全部 ~48 PASSED
```

**验证标准：**
- 0 failure
- 0 error
- 现有测试无回归

---

### Step 10: 更新 dynamic_rules.py 测试（可选补充）

**目标：** 为 `_select_dynamic_rules()` 的子通道开关添加专项测试，覆盖 `modules` 参数传入时的行为。

**文件：** `tests/test_dynamic_rules.py`

**改动内容：** 在 `TestSelectDynamicRules` 类中新增 3 个测试用例：

```python
def test_dynamic_with_subchannel_modules_disabled(self):
    """modules 传入时，关闭 time_slots 则跳过 _match_time_slot。"""
    ...

def test_dynamic_with_all_subchannels_disabled(self):
    """modules 传入时全部子通道关闭 → 返回 []。"""
    ...

def test_dynamic_with_modules_none_backward_compat(self):
    """modules=None 时行为与不改动前完全一致（向后兼容）。"""
    ...
```

**验证标准：**
- 新增 3 个测试全部通过
- 现有 dynamic_rules 测试不受影响

---

### Step 11: 实现 Debug Mode（v1.1 新增）

**目标：** 实现 Debug Mode 的 `_debug_summary()` 函数 + 四个辅助函数，修改 `inject_context()` 末尾追加 debug 摘要，补充 INT-16~19 测试用例。

**预计时间：** ~20 min

---

#### 11a: 实现 `_debug_summary()` + 四个辅助函数

**文件：** `hermes_persona/injector.py`

**位置：** 在 `_has_any_dynamic()` 之后（Step 5 之后）、`inject_context()` 之前

**改动内容：** 新增 5 个私有函数（~70 行）

**1) `_debug_summary(modules: dict, parts: list[str]) -> str`** — 主函数

```python
def _debug_summary(modules: dict, parts: list[str]) -> str:
    """基于 modules 状态和 parts 内容，生成人类可读的注入摘要。

    输出格式（每行一个模块的状态）：
        🔧 [Debug] 本轮注入:
          ① 🕐 时间已注入 / 已停用
          ② 📜 N条静态规则 / 已停用
          ③ ⚡ time_slots: on / turn_stage: on → after_30 / keyword: off
          ④ 🎲 fox_ears: on / fox_tail: off / metaphor: off
          ⑤ 🧠 已注入 / 已停用
          ⑥ 📋 Ace Music: P0 / Clef: P0 / ...（前2条摘要）
    """
    lines = ["🔧 [Debug] 本轮注入:"]

    # ① Time
    if _is_enabled(modules, "time"):
        lines.append("  ① 🕐 时间已注入")
    else:
        lines.append("  ① 🕐 已停用")

    # ② Static rules — 统计 parts 中规则行数
    if _is_enabled(modules, "static_rules"):
        rule_count = _count_static_rules_in_parts(parts)
        lines.append(f"  ② 📜 {rule_count}条静态规则")
    else:
        lines.append("  ② 📜 已停用")

    # ③ Dynamic — 子通道状态
    if _is_enabled(modules, "dynamic"):
        dyn = modules.get("dynamic", {})
        sub_status = _fmt_dynamic_sub_status(dyn)
        lines.append(f"  ③ ⚡ {sub_status}")
    else:
        lines.append("  ③ ⚡ 已停用")

    # ④ Variance — 逐分类状态
    if _is_enabled(modules, "variance"):
        var_status = _fmt_variance_status(parts)
        lines.append(f"  ④ 🎲 {var_status}")
    else:
        lines.append("  ④ 🎲 已停用")

    # ⑤ Memory
    if _is_enabled(modules, "memory"):
        lines.append("  ⑤ 🧠 已注入")
    else:
        lines.append("  ⑤ 🧠 已停用")

    # ⑥ Kanban
    if _is_enabled(modules, "kanban"):
        kanban_status = _fmt_kanban_debug(parts)
        lines.append(f"  ⑥ 📋 {kanban_status}")
    else:
        lines.append("  ⑥ 📋 已停用")

    return "\n".join(lines)
```

**2) 四个辅助函数：**

| 函数 | 职责 | 实现要点 |
|:---|:---|:---|
| `_count_static_rules_in_parts(parts)` | 统计 parts 中由 `_inject_static_rules()` 产生的条目数 | 遍历 parts，计数非空且非 emoji 标记的行（规则行不含 emoji 前缀） |
| `_fmt_dynamic_sub_status(dyn_dict)` | 格式化子通道状态字符串 | 输出如 `"time_slots: on / turn_stage: on → after_30 / keyword: off"`；若 dyn 为 bool 则直接显示 on/off |
| `_fmt_variance_status(parts)` | 从 parts 中提取实际注入的 variance 分类 | 解析 variance 输出行（如 `🦊 狐狸耳朵微微动了动`），提取分类名并格式化开关状态 |
| `_fmt_kanban_debug(parts)` | 从 parts 中提取看板条目并截取前 2 条显示摘要 | 找到 kanban 输出块（以 `📋` 开头的行），提取项目名和状态，截取前 2 条 |

**关键设计约束：**
- 所有辅助函数是纯函数，不访问文件系统或网络。
- 辅助函数不抛异常——任何解析失败返回降级字符串（如 `"on"` / `"off"` / `"无数据"`）。
- `_debug_summary()` 本身不修改 `parts`——只读取。

**验证标准：**
```bash
# 此时 _debug_summary 尚未被 inject_context 调用，需通过单独导入验证函数存在
python -c "from hermes_persona.injector import _debug_summary, _count_static_rules_in_parts, _fmt_dynamic_sub_status, _fmt_variance_status, _fmt_kanban_debug; print('OK')"
# 期望: OK（无 ImportError）
```

---

#### 11b: 修改 `inject_context()` 末尾追加 debug 摘要 + 空判断修正

**目标：** 在 `inject_context()` 中所有注入步骤完成后，根据 `modules.debug` 决定是否追加 debug 摘要。同时修正空判断逻辑——debug 摘要不参与 parts 是否为空的判断。

**文件：** `hermes_persona/injector.py`

**改动内容：** 修改 `inject_context()` 末尾（已在 Step 6.8 中预埋了伪代码，此步骤实现之）

```python
# 在步骤⑥ kanban 之后、现有 return 之前：

# 记录非 debug 内容的数量（用于空判断）
non_debug_count = len(parts)

# ⑦ Debug summary（不参与空判断，默认关闭）
if _is_enabled(modules, "debug"):
    parts.append(_debug_summary(modules, parts))

# 空判断基于非 debug 内容
if non_debug_count == 0:
    return None
return {"context": "\n\n".join(parts)}
```

**注意：** Step 6.8 已规划了此处的伪代码结构，本步骤实现确切逻辑。原有 `if not parts: return None` 已被替换为 `if non_debug_count == 0: return None`。

**验证标准：**
```bash
python -m pytest tests/test_modules_switch.py::TestDebugMode -v
# 期望: 4 passed（INT-16~19）
```

---

#### 11c: 补充 debug 测试用例（INT-16 ~ INT-19）

**目标：** 确认 Step 1 中预写的 4 个 `TestDebugMode` 测试用例全部通过。

**操作：**
```bash
# 运行 debug 专项测试
python -m pytest tests/test_modules_switch.py::TestDebugMode -v
```

**4 个用例清单：**

| TC-ID | 用例 | 验证 |
|:---|:---|:---|
| INT-16 | debug 关闭无摘要（默认） | `"debug": False` → context 不含 `"🔧 [Debug]"` |
| INT-17 | debug 开启追加摘要 | `"debug": True`，部分模块开启 → context 末尾含 `"🔧 [Debug] 本轮注入:"`，且包含各模块状态行（①~⑥） |
| INT-18 | 全部模块关闭，仅 debug 开启 | 所有模块 off，`"debug": True` → 返回 `None`（debug 摘要不参与空判断） |
| INT-19 | debug 开启且记忆关闭 | `"debug": True`, `"memory": False` → 摘要中 memory 行显示 `"🧠 已停用"` |

**验证标准：**
- INT-16~19 全部 PASSED
- 全量回归无影响（运行 `python -m pytest tests/ -v` 确认）

---

## 3. 风险点与回滚方案

### 3.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|:---|:---|:---|:---|
| `modules is None` 守卫写错导致旧调用方崩溃 | 低 | 高 | `_select_dynamic_rules` 中 `modules is None` 先检查；现有测试覆盖 |
| 旧格式合成逻辑遗漏边界情况 | 中 | 中 | BC-01~05 向后兼容测试覆盖所有旧格式路径 |
| `_is_enabled` 对 dict 类型的处理不当 | 低 | 低 | `isinstance(val, dict)` 提前拦截，视为 True |
| memory 两层防护导致行为不一致 | 低 | 低 | `modules.memory=false` 跳过整块，`modules.memory=true` 时内部 `_recall_memories` 仍检查 `enabled` |
| 全部模块关闭后 `inject_context` 返回 None 的影响 | 低 | 低 | Hook 框架已处理 `None` 返回值；EDGE-04 测试覆盖 |
| Debug 摘要参与空判断 → 仅 debug 开启时错误返回有效 context | 中 | 中 | `non_debug_count` 在 debug 注入前记录；INT-18 专门测试此边界 |
| Debug 辅助函数解析 parts 失败抛异常 | 低 | 低 | 所有辅助函数内部 try/except，降级返回字符串；不影响正常注入 |

### 3.2 回滚方案

所有改动集中在 2 个源文件和 2 个测试文件：

| 回滚方式 | 操作 |
|:---|:---|
| **Git 回滚** | `git checkout -- hermes_persona/injector.py hermes_persona/dynamic_rules.py examples/persona-config.json` |
| **删除新文件** | `rm tests/test_modules_switch.py` |
| **完整回滚** | `git stash` 或 `git reset --hard HEAD` |

**关键安全边界：**
- `guard.py` 完全未触碰
- `__init__.py` 中的 Hook 注册逻辑不变
- 注入顺序（Step ①~⑥）不变，Step ⑦ debug 追加只读不修改已有 parts
- `inject_context()` 外层 `try/except` 不变
- Debug 辅助函数均为纯函数，fail-open，解析失败降级返回字符串

---

## 4. 验证检查清单

实施完成后的最终验证：

### 4.1 自动化测试

- [ ] `python -m pytest tests/ -v` — 全部 PASSED，0 failure
- [ ] 新测试 `test_modules_switch.py` — ~48 个用例全部 PASSED
- [ ] Debug 测试 `TestDebugMode` — INT-16~19 全部 PASSED
- [ ] 现有测试 `test_injector.py` — 全部 PASSED（无回归）
- [ ] 现有测试 `test_dynamic_rules.py` — 全部 PASSED（无回归）

### 4.2 手动验证

- [ ] `persona-config.json` JSON 格式合法
- [ ] 用无 `modules` 的旧配置文件加载，行为不变
- [ ] 用有 `modules` 的新配置文件加载，新格式优先
- [ ] 关闭 time → 无 `🕐` 输出
- [ ] 关闭 static_rules → 无规则输出
- [ ] 关闭 dynamic（整体）→ 无动态规则
- [ ] 仅关闭 dynamic.turn_stage → time_slots + keyword 仍工作
- [ ] 关闭 memory → `_recall_memories` 不被调用
- [ ] 关闭 kanban → 首轮也不注入看板
- [ ] 全部关闭 → `inject_context` 返回 None（不崩溃）
- [ ] **Debug 关闭（默认）→ context 中无 `🔧 [Debug]` 字样**
- [ ] **Debug 开启 → context 末尾含 `🔧 [Debug] 本轮注入:` + ①~⑥ 行**
- [ ] **全部模块关闭 + debug 开启 → 返回 None（debug 摘要不参与空判断）**
- [ ] **Debug 摘要中各模块状态与实际 modules 开关一致**

### 4.3 代码审查

- [ ] `_MODULE_REGISTRY` 的 `default` 值符合 SPEC §2.1 设计决策（含 `debug.default = False`）
- [ ] `_resolve_modules()` 异常时返回 `{}`（fail-open）
- [ ] `_is_enabled()` 未知 key 返回 True（fail-open）
- [ ] `_select_dynamic_rules()` 的 `modules=None` 条件确保向后兼容
- [ ] `inject_context()` 注入顺序不变（①→⑥），debug 在最后追加（⑦）
- [ ] `_debug_summary()` 为纯函数，不修改 `parts`，不访问 I/O
- [ ] `non_debug_count` 在 debug 注入前记录，空判断基于此值（非 `len(parts)`）
- [ ] 四个 debug 辅助函数均有 try/except 降级保护，解析失败不抛异常

---

*🦊 知惠 · 2026-05-18 · PLAN-001 v1.1（新增 Debug Mode 实施步骤）· 等待主人审阅*
