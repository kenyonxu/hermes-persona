# SPEC-001: 模块化总控开关

**文档编号:** SPEC-001
**对应 US:** US-001
**版本:** 1.1
**日期:** 2026-05-18
**修订:** v1.1 新增 Debug Mode（AC-6）
**作者:** 知惠（Zhihui）
**审阅:** Kai.Xu
**状态:** 📋 待审阅

---

## 目录

1. [概述](#1-概述)
2. [架构设计](#2-架构设计)
3. [数据结构设计](#3-数据结构设计)
4. [代码改动清单](#4-代码改动清单)
5. [向后兼容策略](#5-向后兼容策略)
6. [测试策略](#6-测试策略)
7. [错误处理与降级策略](#7-错误处理与降级策略)
8. [审批检查清单](#8-审批检查清单)

---

## 1. 概述

### 1.1 目标

在 `persona-config.json` 中建立集中式模块开关面板（`modules` 键），使运维者可以独立启用/禁用每一个注入模块，同时保持对旧配置格式的完全向后兼容。

### 1.2 范围

| 范围 | 说明 |
|:---|:---|
| **涉及** | `persona-config.json` 格式扩展、`injector.py` 开关守卫、`dynamic_rules.py` 子通道控制、模块注册表、测试 |
| **不涉及** | Hook 注册机制（`register()` 不变）、注入顺序（不变）、异常处理模式（不变） |
| **不涉及** | `guard.py` 安全护栏开关（guard 不在注入链路中，有其自身的 `enabled` 控制） |

### 1.3 被控模块一览

| 模块键 | 对应函数/逻辑 | 现有开关 | 所属阶段 |
|:---|:---|:---|:---|
| `time` | `_time_context()` | `time.enabled` ✅ | ① Time |
| `static_rules` | `_inject_static_rules()` | ❌ 无 | ② Static Rules |
| `dynamic` (父) | `_select_dynamic_rules()` | ❌ 无 | ③ Dynamic Rules |
| `dynamic.time_slots` | `_match_time_slot()` | ❌ 无 | ③a |
| `dynamic.turn_stage` | `_match_turn_stage()` | ❌ 无 | ③b |
| `dynamic.keyword` | `_match_keyword()` | ❌ 无 | ③c |
| `variance` | `_randomize_variance()` | ❌ 无 | ④ Variance |
| `memory` | `_recall_memories()` | `memory.enabled` ✅ | ⑤ Memory |
| `kanban` | `_read_kanban()` | `project.enabled` ✅ | ⑥ Kanban |
| `debug` | `_debug_summary()` | ❌ 无 | ⑦ Debug |

---

## 2. 架构设计

### 2.1 模块注册表

在 `hermes_persona/injector.py` 中新增模块级常量 `_MODULE_REGISTRY`，作为所有已注册模块的元信息中心。

```python
# 模块注册表：记录每个被 modules 键控制的模块元信息
_MODULE_REGISTRY: dict[str, dict] = {
    "time": {
        "description": "时间上下文注入",
        "default": True,
        "phase": 1,
        "legacy_key": "time",        # 旧格式 config.<legacy_key>.enabled
        "legacy_path": ("time", "enabled"),
    },
    "static_rules": {
        "description": "静态规则注入（context.rules + rules_first_turn_only）",
        "default": True,
        "phase": 2,
        "legacy_key": None,           # 无旧格式开关，默认开启
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
        "default": False,             # 兼容现有默认行为：memory 默认关闭
        "phase": 5,
        "legacy_key": "memory",
        "legacy_path": ("memory", "enabled"),
    },
    "kanban": {
        "description": "看板状态注入（仅首轮）",
        "default": False,             # 兼容现有默认行为：project 默认关闭
        "phase": 6,
        "legacy_key": "project",
        "legacy_path": ("project", "enabled"),
    },
    "debug": {
        "description": "Debug Mode — 在注入上下文末尾追加人类可读的注入摘要，帮助运维者快速定位问题",
        "default": False,
        "phase": 7,
        "legacy_key": None,
        "legacy_path": None,
    },
}
```

**设计决策说明：**

- `default` 值反映当前代码行为 — 不破坏现有部署的默认运行效果。
  - `time`、`static_rules`、`dynamic`、`variance` 当前总是运行 → default `True`
  - `memory` 当前 `enabled: false` → default `False`
  - `kanban` 当前 `enabled: false` → default `False`
  - `debug` 默认关闭，对用户透明 → default `False`
- `legacy_key` 指向旧格式中对应章节点（`config["time"]`、`config["memory"]`、`config["project"]`）的键名。
- `static_rules`、`dynamic`、`variance` 在旧格式中无开关，`legacy_key` 为 `None`，此时 `_is_enabled()` 返回其 `default` 值。

### 2.2 开关决策流程

```
inject_context() 被调用
  │
  ├─ _load_config() → config (hermes-persona 子树)
  │
  ├─ _resolve_modules(config) → modules (dict)
  │     │
  │     ├─ 若 config 顶层有 "modules" 键 → 直接使用（新格式）
  │     └─ 否则 → 从旧格式各章节提取 enabled 字段合成（兼容模式）
  │
  └─ 对每个注入步骤：
        │
        ├─ 步骤 ① _is_enabled(modules, "time") → False → 跳过 time
        ├─ 步骤 ② _is_enabled(modules, "static_rules") → False → 跳过 static_rules
        ├─ 步骤 ③ _has_any_dynamic(modules) → False → 整个 dynamic 块跳过
        │     ├─ 若 dynamic.time_slots 为 False → _match_time_slot() 不调用
        │     ├─ 若 dynamic.turn_stage 为 False → _match_turn_stage() 不调用
        │     └─ 若 dynamic.keyword 为 False → _match_keyword() 不调用
        ├─ 步骤 ④ _is_enabled(modules, "variance") → False → 跳过
        ├─ 步骤 ⑤ _is_enabled(modules, "memory") → False → 跳过
        ├─ 步骤 ⑥ _is_enabled(modules, "kanban") → False → 跳过
        └─ 步骤 ⑦ _is_enabled(modules, "debug") → True → 调用 _debug_summary()
               │                                   将摘要追加到 parts 末尾
               └─ → False → 跳过（默认行为）
```

### 2.3 动态规则子通道控制

动态规则模块采用**父开关 + 子开关**的二级结构：

```
modules.dynamic (bool 或 dict)
  ├─ 若为 False → 跳过整个 _select_dynamic_rules() 调用
  │                （time_slots、turn_stage、keyword 全部不执行）
  │
  └─ 若为 True 或 dict → 进入 _select_dynamic_rules()
       ├─ time_slots: False → 不调用 _match_time_slot()
       ├─ turn_stage: False → 不调用 _match_turn_stage()
       └─ keyword:   False → 不调用 _match_keyword()
```

**接口变更：** `_select_dynamic_rules()` 签名增加 `modules: dict` 参数，用于传入子通道开关。

```python
# 新签名
def _select_dynamic_rules(
    dynamic_cfg: dict,
    user_message: str,
    is_first_turn: bool,
    turn_count: int,
    modules: dict | None = None,   # ← 新增参数
) -> list[str]:
```

### 2.4 模块注册规范（新增模块的契约）

未来新增模块时，开发者必须完成三步：

1. **在 `_MODULE_REGISTRY` 中注册**：添加键名、描述、默认值、所属阶段、旧格式映射（如有）。
2. **在 `persona-config.json` 的 `modules` 下添加新键**：遵循 `snake_case` 命名。
3. **在 `inject_context()` 对应注入位置添加 `_is_enabled()` 守卫**：保持注入顺序不被打乱。

**命名规范：**
- 模块键名：`snake_case`（如 `static_rules`、`turn_stage`）
- 子通道键名：继承父模块的 `snake_case`（如 `dynamic.time_slots`）
- 与注入函数名保持语义对应，但不要求完全相同

### 2.5 Debug Mode（v1.1 新增）

Debug Mode 是一个特殊的「只读观察」模块——它不产生注入内容，而是在所有正常注入步骤完成后，将本轮注入情况以人类可读的摘要形式追加到 `parts` 末尾。

#### 2.5.1 设计原则

- **只读观察**：debug 不改变任何注入步骤的行为，仅报告「发生了什么」。
- **默认关闭**：`modules.debug` 默认为 `false`，对终端用户完全透明。
- **追加而非替代**：debug 摘要是 `parts.append()`，不是替换 `parts`。
- **零额外 I/O**：`_debug_summary()` 是纯函数，不访问文件系统或网络。

#### 2.5.2 `_debug_summary()` 函数规格

```python
def _debug_summary(modules: dict, parts: list[str]) -> str:
    """基于 modules 状态和 parts 内容，生成人类可读的注入摘要。

    Args:
        modules: _resolve_modules() 返回的开关字典。
        parts:   inject_context() 中已收集的注入片段列表。

    Returns:
        str: 格式化的 debug 摘要字符串，追加到 context 末尾。

    输出格式示例：
        🔧 [Debug] 本轮注入:
          ① 🕐 时间已注入
          ② 📜 7条静态规则
          ③ ⚡ time_slots: on / turn_stage: on → after_30 / keyword: off
          ④ 🎲 fox_ears: off / fox_tail: on / metaphor: off
          ⑤ 🧠 已停用
          ⑥ 📋 Ace Music: P0 / Clef: P0 / ...
    """
```

**输出格式规范：**

| 行 | 模块 | 内容来源 | 逻辑 |
|:---|:---|:---|:---|
| ① | time | `modules["time"]` | `True` → `"🕐 时间已注入"` / `False` → `"🕐 已停用"` |
| ② | static_rules | `len(parts)` 中 static_rules 贡献的行数 | `True` → `"📜 N条静态规则"` / `False` → `"📜 已停用"` |
| ③ | dynamic | `modules["dynamic"]` 子通道 | 逐子通道显示 on/off；若 `turn_stage` 为 on 且匹配到阶段名，追加 `→ after_30` |
| ④ | variance | `modules["variance"]` + parts 中 variance 内容 | 逐分类显示 on/off（如 `fox_ears: on` / `fox_tail: off`） |
| ⑤ | memory | `modules["memory"]` | `True` → `"🧠 已注入"` / `False` → `"🧠 已停用"` |
| ⑥ | kanban | `modules["kanban"]` + parts 中 kanban 内容 | `True` → 显示前 2 个看板条目摘要 / `False` → `"📋 已停用"` |

**实现伪代码：**

```python
def _debug_summary(modules: dict, parts: list[str]) -> str:
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

**辅助函数：**

| 函数 | 职责 |
|:---|:---|
| `_count_static_rules_in_parts(parts)` | 统计 parts 中由 `_inject_static_rules()` 产生的行数 |
| `_fmt_dynamic_sub_status(dyn_dict)` | 格式化子通道状态字符串，如 `"time_slots: on / turn_stage: on → after_30 / keyword: off"` |
| `_fmt_variance_status(parts)` | 从 parts 中提取实际注入的 variance 分类，格式化开关状态 |
| `_fmt_kanban_debug(parts)` | 从 parts 中提取看板条目并截取前 2 条显示摘要 |

#### 2.5.3 Debug 注入位置

Debug 摘要是 `inject_context()` 的**最后一步**，在所有注入模块完成之后、`parts` 拼接之前执行：

```
inject_context() 流程:
  ① _time_context()          → parts.append(...)
  ② _inject_static_rules()   → parts.extend(...)
  ③ _select_dynamic_rules()  → parts.extend(...)
  ④ _randomize_variance()    → parts.extend(...)
  ⑤ _recall_memories()       → parts.append(...)
  ⑥ _read_kanban()           → parts.append(...)
  ⑦ if debug:                → parts.append(_debug_summary(modules, parts))
  
  return {"context": "\n\n".join(parts)}
```

**重要约束：**
- Debug 摘要的生成不修改 `parts` 中已有内容——它只追加新元素。
- Debug 摘要的格式不受正常注入内容的影响——即使 parts 为空，debug 摘要仍按 modules 状态生成。
- Debug 摘要本身不计入正常注入内容——后续逻辑（如 `if not parts: return None`）需调整：debug 摘要不参与 `parts` 是否为空的判断。

#### 2.5.4 Debug 不参与空判断的修正

原有逻辑 `if not parts: return None` 需改为仅基于非 debug 内容判断：

```python
# 注入步骤 ①~⑥...
non_debug_count = len(parts)

# ⑦ Debug（不参与空判断）
if _is_enabled(modules, "debug"):
    parts.append(_debug_summary(modules, parts))

# 空判断基于非 debug 内容
if non_debug_count == 0:
    return None
return {"context": "\n\n".join(parts)}
```

---

## 3. 数据结构设计

### 3.1 `persona-config.json` 新格式

```json
{
  "hermes-persona": {
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

    "time": { "enabled": true, "format": "cn_full" },
    "context": { "rules": [...], "rules_first_turn_only": [...] },
    "dynamic": { "time_slots": {...}, "turn_stage": {...}, "keywords": {...} },
    "variance": {...},
    "memory": { "enabled": false, "api_url": "", "max_results": 3 },
    "project": { "enabled": false, "kanban_path": "", "label": "" }
  }
}
```

**规则：**

- `modules` 键位于 `hermes-persona` 顶层，与 `time`、`context`、`dynamic` 等并列。
- 每个模块的值可以是 `bool` 或 `dict`（仅 `dynamic` 支持 dict 子通道格式）。
- `modules.dynamic` 为 `bool` 时，作为整体开关（`false` 等效于所有子通道为 `false`）。
- `modules.dynamic` 为 `dict` 时，内部的 `time_slots`、`turn_stage`、`keyword` 各自独立。
- 未出现在 `modules` 中的键，`_is_enabled()` 回退到注册表中的 `default` 值。

### 3.2 `_resolve_modules()` 接口

```python
def _resolve_modules(config: dict) -> dict:
    """解析 modules 配置，优先新格式，回退旧格式合成。

    返回值始终为 dict，保证调用方无需判空。

    伪代码逻辑：
        if "modules" in config and config["modules"] is a dict:
            return config["modules"]  # 新格式，直接使用

        # 回退：从旧格式各章节提取 enabled 字段，合成 modules dict
        modules = {}
        for module_key, meta in _MODULE_REGISTRY.items():
            legacy_key = meta["legacy_key"]
            if legacy_key:
                legacy_section = config.get(legacy_key, {})
                if isinstance(legacy_section, dict):
                    modules[module_key] = legacy_section.get("enabled", meta["default"])
                else:
                    modules[module_key] = meta["default"]
            else:
                modules[module_key] = meta["default"]
        return modules
    """
```

### 3.3 `_is_enabled()` 接口契约

```python
def _is_enabled(modules: dict, key: str) -> bool:
    """判断指定模块是否启用。

    Args:
        modules: _resolve_modules() 返回的开关字典（保证非空）。
        key:    模块键名，必须在 _MODULE_REGISTRY 中已注册。

    Returns:
        bool: 模块是否启用。

    决策逻辑：
        1. 若 modules 中包含 key → 返回 modules[key]（bool 或真值判断）。
        2. 否则 → 返回 _MODULE_REGISTRY[key]["default"]。

    注意：
        - modules 可能来自旧格式合成，此时 dynamic 等无旧格式的模块
          使用 default 值。
        - 函数不抛出异常。key 不存在于注册表时返回 True（fail-open）。

    伪代码逻辑：
        if key in modules:
            val = modules[key]
            if isinstance(val, dict):
                return True  # dict 视为"有子通道配置"→ 父开关开启
            return bool(val)
        return _MODULE_REGISTRY.get(key, {}).get("default", True)
    """
```

### 3.4 `_has_any_dynamic()` 辅助函数

```python
def _has_any_dynamic(modules: dict) -> bool:
    """判断 dynamic 模块的子通道中是否至少有一个开启。

    仅当父开关和至少一个子通道同时开启时返回 True。

    伪代码逻辑：
        parent = _is_enabled(modules, "dynamic")
        if not parent:
            return False

        # dynamic 值为 dict 时，检查子通道
        dyn = modules.get("dynamic", {})
        if isinstance(dyn, dict):
            return (
                dyn.get("time_slots", True) or
                dyn.get("turn_stage", True) or
                dyn.get("keyword", True)
            )
        return True  # bool True → 所有子通道开启
    """
```

---

## 4. 代码改动清单

### 4.1 `hermes_persona/injector.py` — 主改动文件

| # | 改动点 | 改动类型 | 关键逻辑（伪代码） |
|:---|:---|:---|:---|
| 4.1.1 | 新增 `_MODULE_REGISTRY` 常量 | 新增 | 见 §2.1 完整定义 |
| 4.1.2 | 新增 `_resolve_modules()` 函数 | 新增 | 见 §3.2 伪代码 |
| 4.1.3 | 新增 `_is_enabled()` 函数 | 新增 | 见 §3.3 伪代码 |
| 4.1.4 | 新增 `_has_any_dynamic()` 函数 | 新增 | 见 §3.4 伪代码 |
| 4.1.5 | `inject_context()` — 开头调用 `_resolve_modules()` | 修改 | 在 `config = _load_config()` 之后、`parts = []` 之前插入 `modules = _resolve_modules(config)` |
| 4.1.6 | 步骤① Time — 包裹 `_is_enabled()` | 修改 | `if _is_enabled(modules, "time"):` 替换现有的 `if time_cfg.get("enabled", True) is not False:` |
| 4.1.7 | 步骤② Static Rules — 包裹 `_is_enabled()` | 修改 | `if _is_enabled(modules, "static_rules"):` 包裹现有 `_inject_static_rules()` |
| 4.1.8 | 步骤③ Dynamic Rules — 包裹 `_has_any_dynamic()` | 修改 | `if _has_any_dynamic(modules):` 包裹 `_select_dynamic_rules()`，同时传入 `modules=modules.get("dynamic", {})` |
| 4.1.9 | 步骤④ Variance — 包裹 `_is_enabled()` | 修改 | `if _is_enabled(modules, "variance"):` 包裹 `_randomize_variance()` |
| 4.1.10 | 步骤⑤ Memory — 包裹 `_is_enabled()` | 修改 | `if _is_enabled(modules, "memory"):` 替换现有的内联 `mem_cfg.get("enabled")` 检查 |
| 4.1.11 | 步骤⑥ Kanban — 包裹 `_is_enabled()` | 修改 | `if is_first_turn and _is_enabled(modules, "kanban"):` 替换现有的 `if is_first_turn:` + `project_cfg.get("enabled")` |
| 4.1.12 | 公开 API 导出（可选） | 修改 | `__init__.py` 已通过 `from . import injector` 导出 |
| 4.1.13 | 新增 `_debug_summary()` 函数 | 新增 | 见 §2.5.2 伪代码。纯函数，输入 modules + parts，输出格式化摘要字符串 |
| 4.1.14 | 新增 Debug 辅助函数 | 新增 | `_count_static_rules_in_parts()`、`_fmt_dynamic_sub_status()`、`_fmt_variance_status()`、`_fmt_kanban_debug()` 四个私有函数，见 §2.5.2 |
| 4.1.15 | `inject_context()` — 末尾追加 Debug 摘要 | 修改 | 在 return 之前，若 `_is_enabled(modules, "debug")` 则 `parts.append(_debug_summary(modules, parts))`；空判断基于非 debug 内容计数 |
| 4.1.16 | `inject_context()` — 空判断逻辑修正 | 修改 | 在步骤①之前记录 `non_debug_count`；最终 `if non_debug_count == 0: return None`，防止仅含 debug 摘要时返回有效值 |

**`inject_context()` 改动后的核心结构（伪代码）：**

```python
def inject_context(session_id, user_message, conversation_history,
                   is_first_turn, model, platform, **kwargs):
    try:
        config = _load_config()
        modules = _resolve_modules(config)          # ← 新增
        parts: list[str] = []

        # ① Time
        if _is_enabled(modules, "time"):            # ← 改为新守卫
            time_cfg = config.get("time", {})
            fmt = time_cfg.get("format", "cn_full")
            parts.append(_time_context(fmt))

        # ② Static rules
        if _is_enabled(modules, "static_rules"):    # ← 新增守卫
            ctx_cfg = config.get("context", {})
            parts.extend(_inject_static_rules(ctx_cfg, is_first_turn))

        # ③ Dynamic rules (子通道可控)
        if _has_any_dynamic(modules):               # ← 改为新守卫
            turn_count = len(conversation_history or []) // 2
            dynamic_cfg = config.get("dynamic", {})
            parts.extend(
                _select_dynamic_rules(
                    dynamic_cfg, user_message, is_first_turn, turn_count,
                    modules=modules.get("dynamic", {})  # ← 传入子通道开关
                )
            )

        # ④ Random variance
        if _is_enabled(modules, "variance"):        # ← 新增守卫
            parts.extend(_randomize_variance(config.get("variance", {})))

        # ⑤ Memory recall
        if _is_enabled(modules, "memory"):          # ← 改为新守卫
            mem_cfg = config.get("memory", {})
            memories = _recall_memories(user_message, mem_cfg)
            if memories is not None:
                parts.append(memories)

        # ⑥ Kanban status
        if is_first_turn and _is_enabled(modules, "kanban"):  # ← 改为新守卫
            project_cfg = config.get("project", {})
            kanban = _read_kanban(
                project_cfg.get("kanban_path", ""),
                project_cfg.get("label", ""),
            )
            if kanban is not None:
                parts.append(kanban)

        # 记录非 debug 内容的数量（用于空判断）
        non_debug_count = len(parts)

        # ⑦ Debug summary（不参与空判断，默认关闭）
        if _is_enabled(modules, "debug"):                     # ← 新增守卫
            parts.append(_debug_summary(modules, parts))

        if non_debug_count == 0:                              # ← 改为基于非 debug 内容
            return None
        return {"context": "\n\n".join(parts)}
    except Exception:
        traceback.print_exc()
        return None
```

### 4.2 `hermes_persona/dynamic_rules.py` — 子通道控制

| # | 改动点 | 改动类型 | 关键逻辑（伪代码） |
|:---|:---|:---|:---|
| 4.2.1 | `_select_dynamic_rules()` 签名增加 `modules` 参数 | 修改 | `def _select_dynamic_rules(dynamic_cfg, user_message, is_first_turn, turn_count, modules=None)` |
| 4.2.2 | time_slots 子通道守卫 | 修改 | `if modules is None or modules.get("time_slots", True):` 包裹 `_match_time_slot()` |
| 4.2.3 | turn_stage 子通道守卫 | 修改 | `if modules is None or modules.get("turn_stage", True):` 包裹 `_match_turn_stage()` |
| 4.2.4 | keyword 子通道守卫 | 修改 | `if modules is None or modules.get("keyword", True):` 包裹 `_match_keyword()` |

**注意：** `modules is None` 条件确保在不传 `modules` 参数的调用方（如测试中的直接调用）保持行为不变。

**改动后的 `_select_dynamic_rules()` 伪代码：**

```python
def _select_dynamic_rules(dynamic_cfg, user_message, is_first_turn,
                          turn_count, modules=None):
    rules: list[str] = []

    # time_slots — 若 modules 未传入则默认开启
    if modules is None or modules.get("time_slots", True):
        rules.extend(_match_time_slot(dynamic_cfg.get("time_slots", {})))

    # turn_stage — 若 modules 未传入则默认开启
    if modules is None or modules.get("turn_stage", True):
        rules.extend(
            _match_turn_stage(dynamic_cfg.get("turn_stage", {}),
                              is_first_turn, turn_count)
        )

    # keyword — 若 modules 未传入则默认开启
    if modules is None or modules.get("keyword", True):
        rules.extend(_match_keyword(dynamic_cfg.get("keywords", {}),
                                   user_message))

    return rules
```

### 4.3 `persona-config.json`（示例文件）

| # | 改动点 | 改动类型 | 说明 |
|:---|:---|:---|:---|
| 4.3.1 | `examples/persona-config.json` 新增 `modules` 键 | 新增 | 添加 §3.1 格式的 modules 块，默认所有模块开启 |

### 4.4 不改动的文件

| 文件 | 原因 |
|:---|:---|
| `hermes_persona/__init__.py` | Hook 注册不受模块开关影响（始终注册） |
| `hermes_persona/variance.py` | 仅在被调用时才执行，开关逻辑在 `injector.py` 侧 |
| `hermes_persona/guard.py` | 安全护栏有独立的 `guard.enabled` 配置，不在注入链路中 |

---

## 5. 向后兼容策略

### 5.1 兼容性矩阵

| 配置文件状态 | `inject_context()` 行为 |
|:---|:---|
| **有 `modules` 键** | 使用新格式 `modules` 决定开关；忽略旧格式 `time.enabled` / `memory.enabled` / `project.enabled` |
| **无 `modules` 键，有旧格式** | `_resolve_modules()` 从旧格式合成 modules 字典（见 §3.2 伪代码） |
| **既无 `modules` 也无旧格式** | 所有模块使用 `_MODULE_REGISTRY` 中的 `default` 值 |
| **`modules` 为空对象 `{}`** | 所有模块使用 `default` 值，等同于既无新格式也无旧格式 |
| **旧配置文件完全不改** | `_resolve_modules()` 自动合成，行为与升级前完全一致 |

### 5.2 旧格式 → 新格式迁移路径

**阶段 1（本 SPEC 实施后）：双格式兼容**
- 旧配置文件继续工作，`_resolve_modules()` 自动合成。
- 用户可选择性添加 `modules` 键，添加后新格式优先。

**阶段 2（未来大版本）：提供迁移脚本**
- 脚本 `scripts/migrate-config.py` 读取旧格式，生成带 `modules` 键的新格式。
- 在 CHANGELOG 中标注 `time.enabled` / `memory.enabled` / `project.enabled` 已 deprecated。

**阶段 3（远期）：移除旧格式支持**
- 当所有已知部署都已迁移后，移除 `_resolve_modules()` 中的旧格式合成逻辑。
- 要求 `modules` 键为必填项。

### 5.3 兼容性实现要点

```python
# _resolve_modules() 中的旧格式兼容逻辑（关键代码段）

# 核心原则：有 modules 直接用，没有则从旧格式合成
if isinstance(config.get("modules"), dict):
    return config["modules"]  # 新格式优先

# 合成模式：逐个模块检查旧格式
synthesized = {}
for key, meta in _MODULE_REGISTRY.items():
    lp = meta.get("legacy_path")
    if lp:
        # 走旧路径 config[section][enabled]
        section = config.get(lp[0], {})
        if isinstance(section, dict):
            synthesized[key] = section.get(lp[1], meta["default"])
        else:
            synthesized[key] = meta["default"]
    else:
        synthesized[key] = meta["default"]
return synthesized
```

**旧格式 → 新格式映射表：**

| 旧格式路径 | modules 键 | 默认值 |
|:---|:---|:---|
| `config["time"]["enabled"]` | `modules["time"]` | `True` |
| `config["memory"]["enabled"]` | `modules["memory"]` | `False` |
| `config["project"]["enabled"]` | `modules["kanban"]` | `False` |
| （无旧格式） | `modules["static_rules"]` | `True` |
| （无旧格式） | `modules["dynamic"]` / 子通道 | `True` / 子通道各 `True` |
| （无旧格式） | `modules["variance"]` | `True` |

### 5.4 特殊兼容场景

**场景：旧格式中 `memory.enabled: true`，但 `modules` 键不存在。**
→ `_resolve_modules()` 合成 `modules["memory"] = True`，行为与旧格式一致。

**场景：旧格式中 `time.enabled: false`，但 `modules` 键不存在。**
→ `_resolve_modules()` 合成 `modules["time"] = False`，time 不注入。

**场景：`modules` 存在但空的 `{}`。**
→ 所有模块回退到 `default` 值。这与旧格式配置中 `hermes-persona: {}` 的行为一致。

---

## 6. 测试策略

### 6.1 测试用例矩阵

测试文件：`tests/test_modules_switch.py`（新建）

#### 6.1.1 `_resolve_modules()` 单元测试

| TC-ID | 用例 | 输入 | 期望 |
|:---|:---|:---|:---|
| RES-01 | 新格式优先 | `config = {"modules": {"time": False}}` | `modules["time"] == False` |
| RES-02 | 旧格式合成 — time | `config = {"time": {"enabled": False}}` (无 modules) | `modules["time"] == False` |
| RES-03 | 旧格式合成 — memory | `config = {"memory": {"enabled": True}}` (无 modules) | `modules["memory"] == True` |
| RES-04 | 旧格式合成 — project→kanban | `config = {"project": {"enabled": True}}` (无 modules) | `modules["kanban"] == True` |
| RES-05 | 无配置回退 default | `config = {}` | 所有模块 = `_MODULE_REGISTRY[key]["default"]` |
| RES-06 | modules 为空对象 | `config = {"modules": {}}` | 所有模块 = default 值 |
| RES-07 | 旧格式缺失某个 section | `config = {"time": {"enabled": False}}` (无 memory/project) | `memory`/`kanban` = default 值 |

#### 6.1.2 `_is_enabled()` 单元测试

| TC-ID | 用例 | 输入 | 期望 |
|:---|:---|:---|:---|
| IS-01 | key 存在且为 True | `modules={"time": True}`, `key="time"` | `True` |
| IS-02 | key 存在且为 False | `modules={"time": False}`, `key="time"` | `False` |
| IS-03 | key 不存在，回退 default | `modules={}`, `key="time"` | `True` (default) |
| IS-04 | dynamic 为 dict → 父开关视为 True | `modules={"dynamic": {"time_slots": True}}` | `True` |
| IS-05 | dynamic 为 False → 父开关关闭 | `modules={"dynamic": False}` | `False` |
| IS-06 | 未知 key → fail-open 返回 True | `modules={}`, `key="nonexistent"` | `True` |

#### 6.1.3 `_has_any_dynamic()` 单元测试

| TC-ID | 用例 | 输入 | 期望 |
|:---|:---|:---|:---|
| DYN-01 | 全部子通道开启 | `modules={"dynamic": {"time_slots": True, "turn_stage": True, "keyword": True}}` | `True` |
| DYN-02 | 仅 time_slots 开启 | `modules={"dynamic": {"time_slots": True, "turn_stage": False, "keyword": False}}` | `True` |
| DYN-03 | 全部子通道关闭 | `modules={"dynamic": {"time_slots": False, "turn_stage": False, "keyword": False}}` | `False` |
| DYN-04 | 父开关为 False | `modules={"dynamic": False}` | `False` |
| DYN-05 | dynamic 为 True (bool) | `modules={"dynamic": True}` | `True` |

#### 6.1.4 模块开关集成测试 — 每个模块 on/off

| TC-ID | 模块 | 场景 | 验证方法 |
|:---|:---|:---|:---|
| INT-01 | `time` | 关闭后不注入 | patch `_load_config` 返回 `{"modules": {"time": False}, "time": {"format": "cn_full"}}`，断言结果不含 `"🕐"` 且不含时间字符串 |
| INT-02 | `time` | 开启后正常注入 | `"time": True`，断言含 `"🕐"` |
| INT-03 | `static_rules` | 关闭后不注入 | `"static_rules": False`，`context.rules` 有内容 → 断言不含规则文本 |
| INT-04 | `static_rules` | 开启后正常注入 | `"static_rules": True` → 断言含规则文本 |
| INT-05 | `dynamic`（父） | 全部关闭 | `"dynamic": False` → 断言不含任何 dynamic 规则 |
| INT-06 | `dynamic.time_slots` | 仅关 time_slots | `modules={"dynamic": {"time_slots": False, "turn_stage": True, "keyword": True}}` → 断言不含 time_slot 规则，含 turn_stage/keyword 规则 |
| INT-07 | `dynamic.turn_stage` | 仅关 turn_stage | `modules={"dynamic": {"time_slots": True, "turn_stage": False, "keyword": True}}` → 断言不含 turn_stage 规则，含其他 |
| INT-08 | `dynamic.keyword` | 仅关 keyword | `modules={"dynamic": {"time_slots": True, "turn_stage": True, "keyword": False}}` → 断言不含 keyword 规则，含其他 |
| INT-09 | `variance` | 关闭后不注入 | `"variance": False`，`variance` 配置有分类 → 断言不含随机变化文本 |
| INT-10 | `variance` | 开启后正常注入 | `"variance": True` → 可能注入（受 probability 影响），此处仅验证守卫不阻断 |
| INT-11 | `memory` | 关闭后不调用 recall | `"memory": False` → patch `_recall_memories` 验证未被调用 |
| INT-12 | `memory` | 开启后正常调用 | `"memory": True` → patch `_recall_memories` 验证被调用 |
| INT-13 | `kanban` | 关闭后不注入 | `is_first_turn=True`, `"kanban": False` → 断言不含看板内容 |
| INT-14 | `kanban` | 开启后正常注入 | `is_first_turn=True`, `"kanban": True` → 含看板内容 |
| INT-15 | `kanban` | 非首轮，开启也不注入 | `is_first_turn=False`, `"kanban": True` → 断言不含看板内容 |
| INT-16 | `debug` | 关闭后无摘要（默认） | `"debug": False` → 断言 context 中不含 `"🔧 [Debug]"` |
| INT-17 | `debug` | 开启后追加摘要 | `"debug": True`，部分模块开启 → 断言 context 末尾含 `"🔧 [Debug] 本轮注入:"`，且包含各模块状态行（①~⑥） |
| INT-18 | `debug` | 全部模块关闭，仅 debug 开启 | 所有模块 off，`"debug": True` → 断言返回 `None`（debug 摘要不参与空判断） |
| INT-19 | `debug` | 开启且记忆关闭 | `"debug": True`, `"memory": False` → 断言摘要中 memory 行显示 `"🧠 已停用"` |

#### 6.1.5 向后兼容集成测试

| TC-ID | 用例 | 验证 |
|:---|:---|:---|
| BC-01 | 旧格式 — time.enabled=false 生效 | config 无 modules，`time.enabled=False` → time 不注入 |
| BC-02 | 旧格式 — memory.enabled=true 生效 | config 无 modules，`memory.enabled=True` → memory 被调用 |
| BC-03 | 旧格式 — project.enabled=true 生效 | config 无 modules，`project.enabled=True` → kanban 注入 |
| BC-04 | 新旧混合 — modules 优先 | config 同时有 `modules.time=true` 和 `time.enabled=false` → time 注入（modules 优先） |
| BC-05 | 旧格式配置完全不改 | 使用 `examples/persona-config.json` 当前内容（无 modules）→ 行为不变 |

#### 6.1.6 边界测试

| TC-ID | 用例 | 验证 |
|:---|:---|:---|
| EDGE-01 | modules 为 None | 不发生 TypeError，退化到 default 行为 |
| EDGE-02 | modules 中包含非 bool 值 | 真值判断（如 `"time": 1` → 视为 True） |
| EDGE-03 | dynamic 子通道缺失部分键 | 缺失的键回退默认 True |
| EDGE-04 | 全部模块关闭 → inject_context 返回 None | 验证不抛异常，返回 None |

### 6.2 测试文件结构

```
tests/
├── __init__.py
├── conftest.py                    # 不变
├── test_injector.py               # 现有测试不变
├── test_dynamic_rules.py          # 现有测试 + 新增子通道开关测试
├── test_variance.py               # 不变
├── test_guard.py                  # 不变
└── test_modules_switch.py         # 新建：所有模块开关测试
```

### 6.3 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 仅运行模块开关测试
python -m pytest tests/test_modules_switch.py -v

# 运行向后兼容测试（确保不破坏现有行为）
python -m pytest tests/test_injector.py tests/test_dynamic_rules.py -v
```

---

## 7. 错误处理与降级策略

### 7.1 原则

> **Fail-open over fail-closed.** 开关系统本身的故障永远不应阻断人格注入。当无法确定模块开关状态时，默认开启（与当前行为一致）。

### 7.2 异常场景与降级策略

| 场景 | 降级行为 | 理由 |
|:---|:---|:---|
| `_load_config()` 返回 `{}` | 所有模块使用 `default` 值 | 文件缺失/损坏 → 最小可用模式 |
| `modules` 键存在但类型不是 dict | 忽略 malformed `modules`，回退旧格式合成 | 容忍格式错误 |
| `modules` 值为非标准类型（如 `"time": "yes"`） | `_is_enabled()` 用 `bool(val)` 做真值判断 | "yes" → True，"no" → False (Python 真值规则) |
| `modules` 中 dynamic 子通道是 bool 而非 dict | 在 `_select_dynamic_rules()` 中作真值判断，不访问 `.get()` | 防御性编程 |
| 未知模块键（注册表中不存在） | `_is_enabled()` 返回 `True` (fail-open) | 不阻断未知模块 |
| `_resolve_modules()` 自身抛异常 | `inject_context()` 的外层 `try/except` 捕获，返回 `None` | 现有异常处理不变 |
| `modules` 为 None | `_resolve_modules()` 返回空 dict `{}` | 防御性类型检查 |

### 7.3 关键降级逻辑实现

```python
def _resolve_modules(config: dict) -> dict:
    """安全解析 modules 配置，任何情况下都返回 dict。"""
    try:
        modules = config.get("modules")
        if isinstance(modules, dict):
            return modules  # 新格式，相信配置作者

        # 旧格式合成
        synthesized = {}
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
        # 极端情况：_MODULE_REGISTRY 损坏 → 返回空 dict
        # 下游 _is_enabled() 遇到 key 不在 dict 中时回退 default
        return {}
```

### 7.4 与现有异常模式的关系

- `inject_context()` 外层 `try/except` **不变**——继续捕获所有内部异常，返回 `None`。
- 模块开关系统**不引入新的异常路径**——所有新增函数都是纯字典查询，不执行 I/O。
- 模块开关系统**不改变各模块内部的异常处理**——`_recall_memories()`、`_read_kanban()` 等内部异常仍由自身 try/except 消化。

---

## 8. 审批检查清单

请主人 Kai.Xu 逐项确认：

- [ ] **架构设计** (§2)：模块注册表结构、开关决策流程、子通道控制方案是否合理？
- [ ] **数据结构** (§3)：`modules` 格式、`_is_enabled()` 契约、`_resolve_modules()` 合成逻辑是否完备？
- [ ] **`default` 值选择**：`memory` 默认 `False`、`kanban` 默认 `False`、其余默认 `True` 是否符合预期？（当前代码行为：memory 和 project 默认关，其余默认开）
- [ ] **代码改动范围** (§4)：是否认同 `guard.py` 不改动？（guard 不在注入链路，有自己的 `enabled`）
- [ ] **向后兼容** (§5)：旧格式合成逻辑是否覆盖了所有已部署场景？`time.enabled` / `memory.enabled` / `project.enabled` 的映射是否正确？
- [ ] **测试覆盖** (§6)：测试矩阵是否覆盖了所有模块 × 所有状态的组合？
- [ ] **命名规范**：`static_rules`（非 `static-rules`）、`turn_stage`（非 `turn-stage`）、kanban 用 `kanban` 而非 `project`（与旧格式章节名区分）——这些命名是否满意？
- [ ] **下一步**：审批通过后进入 PLAN 阶段（`docs/dev/PLAN-001-模块化总控开关.md`）。

---

## 附录 A: 模块开关状态机

```
                    ┌─────────────────────────────┐
                    │   _resolve_modules(config)   │
                    │   ┌───────────────────────┐  │
                    │   │ modules 键存在?        │  │
                    │   │  YES → 直接使用         │  │
                    │   │  NO  → 旧格式合成       │  │
                    │   └───────────────────────┘  │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │   返回 modules: dict          │
                    │   (保证非 None)              │
                    └─────────────┬───────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
    ┌─────▼─────┐          ┌──────▼──────┐         ┌─────▼─────┐
    │ _is_enabled│          │_has_any_    │         │ 子通道    │
    │ (modules,  │          │ dynamic(    │         │ modules   │
    │  key)      │          │  modules)   │         │ .get()    │
    │            │          │             │         │           │
    │ 简单模块   │          │ dynamic     │         │ time_slots│
    │ time       │          │ 整体开关     │         │ turn_stage│
    │ static     │          │             │         │ keyword   │
    │ variance   │          └─────────────┘         └───────────┘
    │ memory     │
    │ kanban     │
    └────────────┘
```

## 附录 B: 与本 US 不涉及的内容

以下内容**明确不在此 SPEC 范围内**，将在后续用户故事中处理：

| 内容 | 归属 |
|:---|:---|
| Rule-Based 模式切换 | 下一阶段（US-002 候选） |
| Utility-Based 模式切换 | 远期 |
| 本地小后端 — idle 感知 | 远期 |
| guard 模块开关 | guard 有独立 `enabled` 体系，不在注入链路中 |
| `persona-config.json` 的 JSON Schema 校验 | 独立改进项，非本次 scope |
| 热重载（不重启更新配置） | 独立改进项，非本次 scope |

---

*🦊 知惠 · 2026-05-18 · SPEC-001 v1.1（新增 Debug Mode）· 等待主人审阅*
