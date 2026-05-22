# SPEC-011: expression_vector / fixed_signals 模块开关接入

**文档编号:** SPEC-011
**对应 US:** US-001（模块化总控开关的遗漏修复）
**版本:** 1.0
**日期:** 2026-05-22
**作者:** Kai.Xu
**状态:** 📋 待审阅

---

## 目录

1. [概述](#1-概述)
2. [根因分析](#2-根因分析)
3. [架构设计](#3-架构设计)
4. [代码改动清单](#4-代码改动清单)
5. [向后兼容策略](#5-向后兼容策略)
6. [测试策略](#6-测试策略)
7. [审批检查清单](#7-审批检查清单)

---

## 1. 概述

### 1.1 问题

`persona-config.json` 的 `modules` 节中声明了 `expression_vector: true` 和 `fixed_signals: true`，README §1 的模块表中也将它们列为可独立开关的模块。但实际运行时二者**完全不经过 `_is_enabled()` 守卫**：

- `expression_vector` 的启用判断走 `ev_cfg.get("enabled", False)`，直接读 `config.expression_vector.enabled`
- `fixed_signals` 的三个子功能各自检查自己的 `enabled` 字段，没有任何总开关

根本原因：SPEC-001 实施时遗漏了这两个模块的注册和守卫接入。这是实现遗漏（bug），不是设计意图。

### 1.2 范围

| 范围 | 说明 |
|:---|:---|
| **涉及** | `_MODULE_REGISTRY` 新增两条目、`inject_context()` 两处新增 `_is_enabled()` 守卫、README modules 表恢复、测试 |
| **不涉及** | `guard.py`、`dynamic_rules.py`、`variance.py`、`expression_vector.py` 内部逻辑 |
| **不涉及** | `_resolve_modules()` / `_is_enabled()` 核心逻辑（已正确，无需改动） |

---

## 2. 根因分析

SPEC-001 的 `_MODULE_REGISTRY` 定义了 8 个模块条目，但缺少 `expression_vector` 和 `fixed_signals`。对照当前注入流程中实际存在的 8 个功能模块：

| 模块 | 注册表中 | `_is_enabled()` 守卫 | 实际启用判断 |
|:---|:---|:---|:---|
| `time` | ✅ | ✅ | — |
| `static_rules` | ✅ | ✅ | — |
| `dynamic` | ✅ | ✅ | — |
| `variance` | ✅ | ✅ | — |
| `expression_vector` | ❌ | ❌ | `ev_cfg.get("enabled", False)` |
| `fixed_signals` | ❌ | ❌ | 各子信号独立 `enabled` |
| `memory` | ✅ | ✅ | — |
| `kanban` | ✅ | ✅ | — |
| `translate` | ✅ | ✅ | — |
| `debug` | ✅ | ✅ | — |

`expression_vector` 和 `fixed_signals` 是注入流程中实际运行的模块，却在注册表中缺席——用户的 `modules` 开关对它们无效。

---

## 3. 架构设计

### 3.1 `_MODULE_REGISTRY` 新增条目

```python
"expression_vector": {
    "description": "多维度表达向量追踪与注入",
    "default": False,
    "phase": 4,
    "legacy_key": "expression_vector",
    "legacy_path": ("expression_vector", "enabled"),
},
"fixed_signals": {
    "description": "固定信号检测（消息长度 / 回复间隔 / 每日轮数）",
    "default": True,
    "phase": 4,  # 与 expression_vector 同为第④阶段
    "legacy_key": None,
    "legacy_path": None,
},
```

**设计决策：**

- `expression_vector.default = False`：与当前 `ev_cfg.get("enabled", False)` 一致。memory 级的大型功能，默认关闭。
- `fixed_signals.default = True`：三个轻量检测（消息长度、回复间隔、每日轮数），当前始终运行，保持默认开启。旧格式中无顶层 `enabled` 字段，`legacy_key` 为 None。
- `phase = 4`：两者在注入顺序中均位于 phase 4（④a fixed_signals, ④b expression_vector）。

### 3.2 守卫接入点

```
inject_context() 流程:
  ① time           ← _is_enabled(modules, "time")
  ② static_rules   ← _is_enabled(modules, "static_rules")
  ③ dynamic        ← _has_any_dynamic(modules)
  ④a fixed_signals ← _is_enabled(modules, "fixed_signals")   [NEW]
  ④b expr_vector   ← _is_enabled(modules, "expression_vector") [NEW]
  ⑤ variance       ← _is_enabled(modules, "variance")
  ⑥ memory         ← _is_enabled(modules, "memory")
  ⑦ kanban         ← _is_enabled(modules, "kanban")
  ⑧ translate      ← _is_enabled(modules, "translate")
  ⑨ debug          ← _is_enabled(modules, "debug")
```

### 3.3 `fixed_signals` 守卫的边界

`fixed_signals` 在 translate 模式下有特殊行为——它不仅注入 hint，还承担两个"基础设施"职责：

1. **`_daily_turn_count_hint()` → 提取 `_today_turn`**：translate 模式的 `_turn_stage_hint` 依赖此值
2. **`_reply_gap_hint()` + `_save_reply_timing()`**：写入 `reply_timing.json`，供后续轮次的 reply_gap 检测使用

**设计决策**：`modules.fixed_signals = False` 时，跳过所有 fixed_signal 逻辑（包括 hint 注入和副作用）。理由：

- 如果关闭了 fixed_signals，就不应该产生任何 fixed_signal 相关的状态变更
- translate 模式下 `_today_turn` 缺位 → 回退为 0，`turn_stage` 仅匹配 `first_turn`
- `reply_timing` 不保存 → 下一轮的 reply_gap 检测自然无数据，静默跳过
- 这是模块开关的应有语义：关闭 = 完全不存在

> 如果未来发现 translate + fixed_signals 关闭的组��需要解耦（例如 reply_timing 保存应该独立于 fixed_signals 开关），可以在后续 SPEC 中将 `_save_reply_timing()` 提升为基础设施层。本次修复保持简单——开关控制整体模块。

---

## 4. 代码改动清单

### 4.1 `injector.py`

| # | 改动点 | 类型 | 说明 |
|:---|:---|:---|:---|
| 4.1.1 | `_MODULE_REGISTRY` 新增 `expression_vector` | 新增 | 见 §3.1，插在 `variance` 之前（按 phase 排序） |
| 4.1.2 | `_MODULE_REGISTRY` 新增 `fixed_signals` | 新增 | 见 §3.1，插在 `expression_vector` 之前 |
| 4.1.3 | `inject_context()` — ④a 块包裹 `_is_enabled()` | 修改 | `if _is_enabled(modules, "fixed_signals"):` 包裹 fixed_cfg 整块（translate 和非 translate 两条路径均包在内） |
| 4.1.4 | `inject_context()` — ④b 块包裹 `_is_enabled()` | 修改 | 将现有的 `if ev_cfg.get("enabled", False):` 替换为 `if _is_enabled(modules, "expression_vector") and ev_cfg.get("enabled", False):` |

### 4.2 `README.md`

| # | 改动点 | 类型 | 说明 |
|:---|:---|:---|:---|
| 4.2.1 | §1 modules 表恢复 `expression_vector` / `fixed_signals` 行 | 回退 | 恢复审核时移除的两行 |
| 4.2.2 | §1 JSON 示例恢复两行 | 回退 | 恢复审核时移除的两行 |

---

## 5. 向后兼容策略

### 5.1 兼容性矩阵

| 配置文件状态 | 行为 |
|:---|:---|
| **新格式 `modules` 中有 `expression_vector: false`** | 表达式向量关闭（新行为生效） |
| **新格式 `modules` 中有 `fixed_signals: false`** | 固定信号关闭（新行为生效） |
| **无 `modules` 键，旧格式有 `expression_vector.enabled: true`** | `_resolve_modules()` 从旧格式合成 → `modules["expression_vector"] = True` |
| **无 `modules` 键，旧格式无 `expression_vector` 节** | `_resolve_modules()` 回退 default → `modules["expression_vector"] = False` |
| **无 `modules` 键，无旧格式 `fixed_signals` 顶层 `enabled`** | `_resolve_modules()` 回退 default → `modules["fixed_signals"] = True` |

### 5.2 旧格式映射

| 旧格式路径 | modules 键 | 默认值 |
|:---|:---|:---|
| `config["expression_vector"]["enabled"]` | `modules["expression_vector"]` | `False` |
| （无旧格式顶层开关） | `modules["fixed_signals"]` | `True` |

### 5.3 expression_vector 的双重检查

```python
# 两步检查：模块开关 AND 功能开关必须同时为 True
if _is_enabled(modules, "expression_vector") and ev_cfg.get("enabled", False):
    ...
```

这样设计是为了兼容：即使旧格式合成 `modules["expression_vector"] = True`，实际的 `expression_vector.enabled` 仍有机会为 `False`。两个开关是 AND 关系——类似于 `dynamic` 的父开关 + 子通道结构。

---

## 6. 测试策略

### 6.1 新增测试用例

测试文件：`tests/test_modules_switch.py`（追加）

| TC-ID | 用例 | 输入 | 期望 |
|:---|:---|:---|:---|
| INT-EV-01 | expression_vector 模块开关关闭 | `modules.expression_vector = False`, `expression_vector.enabled = True` | EV 不初始化、不注入 |
| INT-EV-02 | expression_vector 功能开关关闭 | `modules.expression_vector = True`, `expression_vector.enabled = False` | EV 不初始化 |
| INT-EV-03 | expression_vector 均开启 | 两者均为 True | EV 正常初始化并注入 |
| INT-FS-01 | fixed_signals 模块开关关闭 | `modules.fixed_signals = False`，子信号均 enabled | 三个信号均不注入，translate 模式不提取 turn |
| INT-FS-02 | fixed_signals 模块开关开启 | `modules.fixed_signals = True` | 行为与当前一致（子信号各自判断） |
| BC-EV-01 | 旧格式 expression_vector.enabled 合成 | config 无 modules，有 `expression_vector.enabled: True` | `_resolve_modules()` 合成 `modules["expression_vector"] = True` |

### 6.2 运行测试

```bash
python -m pytest tests/test_modules_switch.py -v
python -m pytest tests/ -v  # 全量回归
```

---

## 7. 审批检查清单

- [ ] **根因确认** (§2)：expression_vector 和 fixed_signals 确实未接入 `_is_enabled()`？
- [ ] **注册表设计** (§3.1)：`default` 值（EV=False, FS=True）是否与当前行为一致？
- [ ] **fixed_signals 边界** (§3.3)：关闭后是否也应该停止 reply_timing 保存？（当前设计：是）
- [ ] **双重检查** (§5.3)：expression_vector 的 `_is_enabled() AND ev_cfg.enabled` 逻辑是否合理？
- [ ] **代码改动范围** (§4)：仅 2 个文件（injector.py + README.md），确认无遗漏？
- [ ] **下一步**：审批通过后直接实施（改动量小，不需要单独 PLAN）。

---

*Kai.Xu · 2026-05-22 · SPEC-011 v1.0 · 待审阅*
