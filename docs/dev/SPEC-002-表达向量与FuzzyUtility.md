# SPEC-002: 表达向量与 FuzzyUtility 层

**文档编号:** SPEC-002
**对应 US:** US-002 v1.0
**版本:** 1.0
**日期:** 2026-05-18
**作者:** 知惠（Zhihui）
**审阅:** Kai.Xu
**状态:** 📋 待审阅

---

## 目录

1. [概述](#1-概述)
2. [架构设计](#2-架构设计)
3. [Config Schema](#3-config-schema)
4. [核心算法](#4-核心算法)
5. [固定规则信号](#5-固定规则信号)
6. [Session turn 注入逻辑](#6-session-turn-注入逻辑)
7. [与现有模块的关系](#7-与现有模块的关系)
8. [代码改动清单](#8-代码改动清单)
9. [错误处理与兜底](#9-错误处理与兜底)
10. [测试策略](#10-测试策略)
11. [实施阶段拆分](#11-实施阶段拆分)
12. [审批检查清单](#12-审批检查清单)

---

## 1. 概述

### 1.1 目标

在 `persona-config.json` 中新增 `expression_vector` 配置节，实现一个**多维度、自衰减、用户可控**的表达向量系统（Fuzzy Utility 层）。通过关键词匹配 N 个维度，按分数规则累加/衰减，每轮将当前向量值注入 LLM 上下文，使 Agent 的表达底色能平滑地随对话内容漂移。

同时将两个固定层信号（消息长度、回复间隔）纳入本轮落地，与表达向量同属 FuzzyUtility 层。

### 1.2 范围

| 范围 | 说明 |
|:---|:---|
| **涉及** | `expression_vector.py` 新模块、`injector.py` 注入链扩展、`persona-config.json` 新增 section、磁盘持久化、消息长度/回复间隔信号、session turn 注入 |
| **不涉及** | `modules` 体系变更（表达向量使用独立 `enabled` 字段）、`dynamic_rules.py` 改动、`guard.py`、双向量对比（远景） |

### 1.3 术语表

| 术语 | 定义 |
|:---|:---|
| 表达向量 | 一个 dict[str, float]，key 是维度名（用户配置），value 是当前累积分数 |
| 维度 | `dimensions` 中的一个 key，代表一种表达底色方向 |
| 命中 | 用户消息中出现某维度关键词列表中的词 |
| 自衰减 | 未命中的维度按 `[未命中扣分 × 权重]` 降低分数 |
| Fuzzy Utility 层 | 介于 Rule-Based（开关）和 Pure Utility（导航仪）之间的软提示层 |

---

## 2. 架构设计

### 2.1 注入顺序（扩展后）

```
inject_context() 注入顺序（不可变）：

time_context        → ① 🕐 时间感知
static_rules        → ② 📜 静态规则（骨骼）
dynamic_rules       → ③ ⚡ 关键词 → 模式切换（Rule-Based）
fixed_signals       → ④a 📏⏱️ 固定层信号（消息长度 + 回复间隔）    ← 🆕
expression_vector   → ④b 📊 表达向量（Fuzzy Utility）             ← 🆕
variance            → ⑤ 🎲 随机变奏
memory              → ⑥ 🧠 记忆召回
kanban              → ⑦ 📋 看板（仅首轮）
debug               → ⑧ 🔧 调试摘要
```

**关键设计决策：** 固定层信号（④a）和表达向量（④b）在 `dynamic_rules`（③）之后、`variance`（⑤）之前注入。模式切换是开关（即时命中），表达底色是指南针（累积漂移），两者互补。

### 2.2 模块关系图

```
persona-config.json
  │
  ├─ expression_vector section ──────┐
  │   enabled                        │
  │   dimensions                     ▼
  │   score_rules           expression_vector.py
  │   reset                  ┌─────────────────────┐
  │   storage_path           │ _ExpressionVector    │
  │                          │   .update(msg)       │
  │                          │   .load() / .save()  │
  │                          │   .format_inject()   │
  │                          │   .should_reset()    │
  │                          └────────┬────────────┘
  │                                   │
  │                          ┌────────▼────────────┐
  │                          │ storage_path         │
  │                          │ expression_vector.json│
  │                          └─────────────────────┘
  │
  ├─ fixed_signals section ──────────┐
  │   message_length.enabled         ▼
  │   message_length.threshold  injector.py
  │   reply_gap.enabled        ┌──────────────────────┐
  │   reply_gap.threshold      │ _message_length_hint()│
  │   reply_gap.storage_path   │ _reply_gap_hint()     │
  │                            └──────────────────────┘
  │
  └─ (现有 modules, time, context, dynamic, ...)
```

### 2.3 数据流（单轮完整流程）

```
inject_context() 被调用
  │
  ├─ config = _load_config()
  ├─ modules = _resolve_modules(config)
  │
  ├─ ①~③ 现有模块（不变）
  │
  ├─ ④a 固定层信号 ─────────────────────────────────────────
  │     │
  │     ├─ _message_length_hint(user_message, fixed_cfg)
  │     │    len(user_message) < threshold → "📏 消息较短"
  │     │    否则 → None
  │     │
  │     ├─ _reply_gap_hint(fixed_cfg)
  │     │    读取 last_reply_at → 计算间隔
  │     │    间隔 > threshold → "🎵 欢迎回来"
  │     │    否则 → None
  │     │
  │     └─ 更新 last_reply_at = now() → 写回磁盘
  │
  ├─ ④b 表达向量 ──────────────────────────────────────────
  │     │
  │     ├─ ev_cfg = config.get("expression_vector", {})
  │     ├─ if not ev_cfg.get("enabled"): skip
  │     │
  │     ├─ ev = _ExpressionVector(ev_cfg)
  │     │    ├─ .load()           → 从磁盘读取向量状态
  │     │    │   └─ should_reset() → 检查 reset 策略，决定是否清零
  │     │    ├─ .update(msg)      → 关键词匹配 + 累加/衰减
  │     │    ├─ .save()           → 写回磁盘
  │     │    └─ .format_inject(turn_count) → 格式化注入文本
  │     │
  │     └─ parts.append(ev.format_inject(turn_count))
  │
  ├─ ⑤~⑧ 现有模块（不变）
  │
  └─ return {"context": "\n\n".join(parts)}
```

---

## 3. Config Schema

### 3.1 `expression_vector` 完整配置

```json
{
  "hermes-persona": {
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
    }
  }
}
```

### 3.2 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|:---|:---|:---|:---|:---|
| `enabled` | bool | 否 | `false` | 总开关。关掉 = 不追踪不注入，完全不影响现有功能 |
| `dimensions` | dict[str, list[str]] | 是（enabled=true 时） | `{}` | N 个维度的关键词列表。key 即维度名，value 为关键词数组。维度数量和名称完全由用户决定 |
| `score_rules` | dict[str, [number, number, number]] | 否 | 每维默认 `[1, -0.5, 1]` | `[命中得分, 未命中扣分, 权重]`，对每个维度独立配置 |
| `reset` | "session" \| "daily" \| "none" | 否 | `"session"` | 重置策略。session=新会话清零，daily=每日零点清零，none=不自动清零 |
| `storage_path` | string | 否 | `"~/.hermes/expression_vector.json"` | 磁盘暂存路径。支持 `{profile}` 占位符替换 |

### 3.3 `score_rules` 设计意图

```
[命中得分, 未命中扣分, 权重]
```

| 维度 | 命中 | 未命中 | 权重 | 行为特征 |
|:---|:---|:---|:---|:---|
| work | +1 | -0.5 | ×1 | 平潮——缓慢累积、缓慢消退 |
| future | +1 | -1 | ×1 | 平衡——不提就自然下沉 |
| intimacy | +1 | -0.5 | ×3 | 温火——高信号、高粘性 |

**计算公式：**

```
每轮每个维度：
  if 消息命中该维度的任一关键词:
    score += 命中得分 × 权重
  else:
    score += 未命中扣分 × 权重
  score = max(0, score)  // 永不跌破 0
```

### 3.4 `fixed_signals` 配置

```json
{
  "hermes-persona": {
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
    }
  }
}
```

#### 3.4.1 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|:---|:---|:---|:---|:---|
| `message_length.enabled` | bool | 否 | `false` | 消息长度信号开关 |
| `message_length.threshold` | int | 否 | `50` | 字符数阈值，低于此值触发提示 |
| `reply_gap.enabled` | bool | 否 | `false` | 回复间隔信号开关 |
| `reply_gap.threshold_minutes` | int | 否 | `30` | 间隔阈值（分钟），超过此值触发提示 |
| `reply_gap.storage_path` | string | 否 | `"~/.hermes/reply_timing.json"` | 暂存 `last_reply_at` 的路径 |

### 3.5 向后兼容

| 配置状态 | 行为 |
|:---|:---|
| 不配置 `expression_vector` | 插件正常运行，不追踪不注入（完全可选） |
| 不配置 `fixed_signals` | 插件正常运行，不注入固定层信号 |
| `expression_vector.enabled: false` | 不追踪不注入，但配置仍可保留（方便随时开启） |
| `expression_vector` 存在但 `dimensions` 为空 | 向量始终为空，注入格式显示全零值 |

**`expression_vector` 不属于 `modules` 体系**——它有独立的 `enabled` 字段，不走 `_is_enabled()` / `_MODULE_REGISTRY` 路径。

---

## 4. 核心算法

### 4.1 新模块：`hermes_persona/expression_vector.py`

#### 4.1.1 数据结构

```python
# 磁盘持久化格式（JSON）
{
  "version": 1,
  "session_id": "abc-123",
  "last_updated": "2026-05-18T22:30:00",
  "vectors": {
    "work": 8.0,
    "future": 3.0,
    "intimacy": 2.5
  }
}
```

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `version` | int | 数据格式版本号，当前固定为 `1` |
| `session_id` | string | 最近一次更新的 session_id，用于 `"session"` 重置策略 |
| `last_updated` | string | ISO 格式时间戳，用于 `"daily"` 重置策略 |
| `vectors` | dict[str, float] | 每个维度的当前累积分数 |

#### 4.1.2 `_ExpressionVector` 类

```python
class _ExpressionVector:
    """表达向量引擎：关键词匹配 → 累加/衰减 → 磁盘持久化 → 格式化注入。"""

    def __init__(self, cfg: dict):
        """
        Args:
            cfg: expression_vector 配置节（config["expression_vector"]）。
        """
        self.dimensions: dict[str, list[str]]   # 维度名 → 关键词列表
        self.score_rules: dict[str, tuple]       # 维度名 → (hit, miss, weight)
        self.reset_policy: str                    # "session" | "daily" | "none"
        self.storage_path: Path                   # 磁盘路径（已替换占位符）
        self.vectors: dict[str, float]            # 当前向量值
        self._session_id: str | None              # 当前会话 ID
        self._last_updated: datetime | None       # 最近更新时间
```

#### 4.1.3 初始化伪代码

```python
def __init__(self, cfg: dict, profile_path: str | None = None):
    # 1. 解析 dimensions（key 即维度名）
    self.dimensions = {}
    for dim_name, keywords in cfg.get("dimensions", {}).items():
        if isinstance(keywords, list):
            self.dimensions[dim_name] = [str(k) for k in keywords]

    # 2. 解析 score_rules，缺失维度用默认值 [1, -0.5, 1]
    self.score_rules = {}
    default_rule = (1, -0.5, 1)
    for dim_name in self.dimensions:
        raw = cfg.get("score_rules", {}).get(dim_name, [1, -0.5, 1])
        if isinstance(raw, (list, tuple)) and len(raw) == 3:
            self.score_rules[dim_name] = (
                float(raw[0]),   # hit_score
                float(raw[1]),   # miss_penalty
                float(raw[2]),   # weight
            )
        else:
            self.score_rules[dim_name] = default_rule

    # 3. 重置策略
    self.reset_policy = cfg.get("reset", "session")
    if self.reset_policy not in ("session", "daily", "none"):
        self.reset_policy = "session"

    # 4. 存储路径（替换 {profile} 占位符）
    raw_path = cfg.get(
        "storage_path",
        "~/.hermes/expression_vector.json"
    )
    if profile_path:
        raw_path = raw_path.replace("{profile}", str(profile_path))
    self.storage_path = Path(raw_path).expanduser()

    # 5. 初始化向量（全部为 0.0）
    self.vectors = {dim: 0.0 for dim in self.dimensions}
    self._session_id = None
    self._last_updated = None
```

#### 4.1.4 `update()` 算法伪代码

```python
def update(self, user_message: str, session_id: str) -> None:
    """根据用户消息更新所有维度分数。

    Args:
        user_message: 用户当前消息文本。
        session_id:   当前会话 ID，用于 session 重置策略。
    """
    # 1. 检查重置策略
    if self.should_reset(session_id):
        self.vectors = {dim: 0.0 for dim in self.dimensions}
        self._session_id = session_id

    # 2. 逐维度处理
    msg_lower = user_message.lower() if user_message else ""
    for dim_name, keywords in self.dimensions.items():
        hit_score, miss_penalty, weight = self.score_rules[dim_name]

        # 检查是否命中（任一关键词出现在消息中，大小写不敏感）
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

#### 4.1.5 `should_reset()` 伪代码

```python
def should_reset(self, current_session_id: str) -> bool:
    """检查是否需要重置向量。

    Returns:
        True 表示本轮应清零向量。
    """
    if self.reset_policy == "none":
        return False

    if self.reset_policy == "session":
        # session_id 变化 → 清零
        if self._session_id is None:
            return False  # 首次加载，不需要重置
        return current_session_id != self._session_id

    if self.reset_policy == "daily":
        # 日期变化 → 清零
        if self._last_updated is None:
            return False
        now = datetime.now()
        return now.date() > self._last_updated.date()

    return False
```

#### 4.1.6 磁盘读写

```python
def load(self) -> None:
    """从磁盘加载向量状态。文件不存在或格式错误时保持初始值。"""
    try:
        if not self.storage_path.is_file():
            return  # 文件不存在 → 使用初始零值

        data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            return  # 版本不匹配 → 使用初始零值

        # 恢复向量值（只恢复当前配置中存在的维度）
        saved_vectors = data.get("vectors", {})
        for dim_name in self.dimensions:
            if dim_name in saved_vectors:
                val = saved_vectors[dim_name]
                self.vectors[dim_name] = max(0.0, float(val))

        self._session_id = data.get("session_id")
        ts = data.get("last_updated")
        if ts:
            self._last_updated = datetime.fromisoformat(ts)
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return  # 任何错误 → 保持初始零值


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
        pass  # 磁盘写入失败 → 静默降级（本轮值有效但不持久化）
```

#### 4.1.7 注入格式化

```python
def format_inject(self, turn_count: int) -> str:
    """格式化表达向量为注入文本。

    Args:
        turn_count: 当前会话轮数。

    Returns:
        格式如："📊 [表达向量] work:8 future:3 intimacy:2 | 第 22 轮"
        向量值为 0 时仍显示（0 本身具有信号意义）。
    """
    # 按维度名排序，保证输出稳定
    dim_parts = [
        f"{name}:{int(round(val))}"
        for name, val in sorted(self.vectors.items())
    ]
    dim_str = " ".join(dim_parts)
    return f"📊 [表达向量] {dim_str} | 第 {turn_count} 轮"
```

---

## 5. 固定规则信号

### 5.1 消息长度 `_message_length_hint()`

```python
def _message_length_hint(user_message: str, fixed_cfg: dict) -> str | None:
    """检查消息长度，短消息注入提示。

    Args:
        user_message: 用户当前消息文本。
        fixed_cfg: fixed_signals.message_length 配置节。

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

### 5.2 回复间隔 `_reply_gap_hint()`

```python
def _reply_gap_hint(fixed_cfg: dict) -> tuple[str | None, float]:
    """检查回复间隔，长时间未回复注入欢迎回来提示。

    Args:
        fixed_cfg: fixed_signals 配置节。

    Returns:
        (hint_text_or_None, now_timestamp)
        hint_text: "🎵 欢迎回来" 或 None
        now_timestamp: 当前 Unix 时间戳（秒），用于写回 last_reply_at
    """
    rg_cfg = fixed_cfg.get("reply_gap", {})
    if not rg_cfg.get("enabled", False):
        return None, time.time()

    threshold_minutes = rg_cfg.get("threshold_minutes", 30)
    if not isinstance(threshold_minutes, (int, float)):
        threshold_minutes = 30

    now = time.time()
    raw_path = rg_cfg.get(
        "storage_path",
        "~/.hermes/reply_timing.json"
    )
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
        pass  # 读取失败 → 不注入提示，不阻断流程

    return hint, now
```

### 5.3 回复间隔写回

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

    raw_path = rg_cfg.get(
        "storage_path",
        "~/.hermes/reply_timing.json"
    )
    storage_path = Path(raw_path).expanduser()

    try:
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"last_reply_at": now_ts}
        storage_path.write_text(
            json.dumps(data), encoding="utf-8"
        )
    except OSError:
        pass  # 写入失败 → 静默降级
```

---

## 6. Session turn 注入逻辑

### 6.1 Turn 计算方式

Session turn 数已在 `inject_context()` 中计算：

```python
turn_count = len(conversation_history or []) // 2
```

**不重复计算**——复用现有逻辑，只在表达向量注入时一并格式化输出。

### 6.2 注入格式

表达向量与 session turn 合并在同一行注入：

```
📊 [表达向量] work:8 future:3 intimacy:2 | 第 22 轮
```

- `work`/`future`/`intimacy` 为维度名（由用户配置决定，不硬编码）
- 数值为 `int(round(score))`（四舍五入取整）
- 维度名按字母序排列，保证输出稳定
- turn 数直接追加在同一行末尾，用 `|` 分隔

### 6.3 向量值为 0 的语义

0 值具有信号意义——代表「今天/本次会话没提过」，不是「缺失」。因此：

- 向量值为 0 时仍然显示（如 `work:0 future:0 intimacy:0`）
- 不做「值为 0 则省略」的过滤
- LLM 自行判断如何解读 0 值

---

## 7. 与现有模块的关系

### 7.1 modules 体系 vs expression_vector

| 特性 | modules 体系（US-001） | expression_vector（US-002） |
|:---|:---|:---|
| 开关机制 | `_is_enabled(modules, key)` | 独立 `expression_vector.enabled` 字段 |
| 注册 | `_MODULE_REGISTRY` | **不注册**——独立配置节 |
| 注入逻辑 | 在 `injector.py` 中用守卫包裹 | 调用 `_ExpressionVector` 实例方法 |
| 配置位置 | `config["modules"]["xxx"]` | `config["expression_vector"]` |
| 依赖关系 | 无 | 无（完全独立） |

**设计决策：** 表达向量不属于 `modules` 体系。理由：

1. `modules` 管理 Rule-Based 层的注入模块（开/关），表达向量是 Fuzzy Utility 层（软提示）
2. 表达向量有自己的持久化、状态管理、生命周期，与 Rule-Based 模块有本质区别
3. 保持 `modules` 注册表简洁——注册的是注入步骤，不是注入层

### 7.2 Debug Mode 兼容

Debug Mode 摘要中需追加表达向量的状态行：

```
  ④b 📊 work:8 future:3 intimacy:2
```

### 7.3 不受影响的模块

| 模块 | 原因 |
|:---|:---|
| `dynamic_rules.py` | 表达向量的关键词匹配是独立的，不走 `_match_keyword()` 路径 |
| `variance.py` | 随机变奏在表达向量之后执行，无依赖 |
| `guard.py` | 安全护栏有独立体系，不在注入链路中 |
| `memory` / `kanban` | 表达向量不影响记忆和看板的逻辑 |

---

## 8. 代码改动清单

### 8.1 `hermes_persona/expression_vector.py` — 新建

| # | 函数/类 | 行数估算 | 说明 |
|:---|:---|:---|:---|
| 8.1.1 | `_ExpressionVector.__init__()` | ~30 | 解析配置、初始化向量 |
| 8.1.2 | `_ExpressionVector.update()` | ~25 | 关键词匹配 + 累加/衰减 |
| 8.1.3 | `_ExpressionVector.should_reset()` | ~15 | 重置策略判断 |
| 8.1.4 | `_ExpressionVector.load()` | ~20 | 磁盘读取 |
| 8.1.5 | `_ExpressionVector.save()` | ~15 | 磁盘写入 |
| 8.1.6 | `_ExpressionVector.format_inject()` | ~10 | 格式化注入文本 |

**总计：~115 行**

### 8.2 `hermes_persona/injector.py` — 修改

| # | 改动点 | 改动类型 | 关键逻辑 |
|:---|:---|:---|:---|
| 8.2.1 | 新增 `import time` | 新增 | 用于 `_reply_gap_hint()` |
| 8.2.2 | 新增 `from .expression_vector import _ExpressionVector` | 新增 | 导入表达向量模块 |
| 8.2.3 | 新增 `_message_length_hint()` | 新增 | 消息长度信号，§5.1 |
| 8.2.4 | 新增 `_reply_gap_hint()` | 新增 | 回复间隔信号，§5.2 |
| 8.2.5 | 新增 `_save_reply_timing()` | 新增 | 回复间隔写回，§5.3 |
| 8.2.6 | `inject_context()` 步骤④a — 固定层信号注入 | 新增 | 在步骤③之后、④b之前插入 |
| 8.2.7 | `inject_context()` 步骤④b — 表达向量注入 | 新增 | 在④a之后、⑤之前插入 |
| 8.2.8 | `_debug_summary()` — 追加④a/④b状态行 | 修改 | Debug 摘要新增固定信号和表达向量行 |
| 8.2.9 | `inject_context()` — turn_count 提前计算 | 修改 | turn_count 在步骤③已计算，步骤④b复用 |

### 8.3 `inject_context()` 改动后核心结构（伪代码）

```python
def inject_context(session_id, user_message, conversation_history,
                   is_first_turn, model, platform, **kwargs):
    try:
        config = _load_config()
        modules = _resolve_modules(config)
        parts: list[str] = []

        # ① Time context
        if _is_enabled(modules, "time"):
            ...

        # ② Static rules
        if _is_enabled(modules, "static_rules"):
            ...

        # ③ Dynamic rules
        if _has_any_dynamic(modules):
            turn_count = len(conversation_history or []) // 2
            ...
        else:
            turn_count = len(conversation_history or []) // 2

        # ─── ④a 固定层信号 ─────────────────── 新增 ──
        fixed_cfg = config.get("fixed_signals", {})
        hint = _message_length_hint(user_message, fixed_cfg)
        if hint:
            parts.append(hint)

        gap_hint, now_ts = _reply_gap_hint(fixed_cfg)
        if gap_hint:
            parts.append(gap_hint)
        _save_reply_timing(fixed_cfg, now_ts)
        # ────────────────────────────────────────────

        # ─── ④b 表达向量 ───────────────────── 新增 ──
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
                pass  # fail-open：表达向量失败不阻断
        # ────────────────────────────────────────────

        # ⑤ Random variance
        if _is_enabled(modules, "variance"):
            ...

        # ⑥ Memory recall
        if _is_enabled(modules, "memory"):
            ...

        # ⑦ Kanban status (first-turn only)
        if is_first_turn and _is_enabled(modules, "kanban"):
            ...

        non_debug_count = len(parts)

        # ⑧ Debug summary
        if _is_enabled(modules, "debug"):
            parts.append(_debug_summary(modules, parts))

        if non_debug_count == 0:
            return None
        return {"context": "\n\n".join(parts)}
    except Exception:
        traceback.print_exc()
        return None
```

### 8.4 `examples/persona-config.json` — 新增 section

追加 `expression_vector` 和 `fixed_signals` 配置示例。

### 8.5 不改动的文件

| 文件 | 原因 |
|:---|:---|
| `hermes_persona/__init__.py` | Hook 注册不受影响 |
| `hermes_persona/dynamic_rules.py` | 表达向量关键词匹配独立于 Rule-Based |
| `hermes_persona/variance.py` | 无依赖 |
| `hermes_persona/guard.py` | 独立安全护栏体系 |

---

## 9. 错误处理与兜底

### 9.1 原则

> **Fail-open。** 表达向量或固定信号的任何失败都不阻断人格注入链路。

### 9.2 异常场景与降级策略

| 场景 | 降级行为 | 理由 |
|:---|:---|:---|
| `expression_vector` 配置缺失 | 完全跳过，不注入 | 向后兼容 |
| `expression_vector.enabled: false` | 完全跳过 | 用户显式关闭 |
| `dimensions` 为空 `{}` | 向量始终为 0，注入 `📊 [表达向量] | 第 N 轮` | 配置有效但无维度 |
| `score_rules` 缺失某维度 | 使用默认值 `[1, -0.5, 1]` | 容错 |
| `score_rules` 值格式错误 | 使用默认值 `[1, -0.5, 1]` | 容错 |
| `storage_path` 目录不存在 | `save()` 自动创建父目录 | 用户友好 |
| `storage_path` 写入失败 | 静默降级（本轮值有效但不持久化） | fail-open |
| `storage_path` 读取失败（格式错误、权限等） | 使用初始零值 | 不影响本轮计算 |
| `storage_path` JSON 格式不匹配 | 使用初始零值（版本号检查） | 前向兼容 |
| `update()` 计算异常 | 整个表达向量块被 try/except 包裹，跳过 | 不阻断后续注入 |
| `reset` 值不合法 | 回退到 `"session"` | 防御性默认 |
| `fixed_signals` 配置缺失 | 完全跳过，不注入 | 向后兼容 |
| `reply_gap` 磁盘读取失败 | 不注入欢迎提示，不阻断 | fail-open |
| `reply_gap` 磁盘写入失败 | 静默降级 | 不阻断 |
| `message_length` threshold 非数字 | 使用默认值 `50` | 防御性默认 |
| 用户消息为 `None` 或空串 | 消息长度信号触发（`len("") < 50`）；表达向量全部维度未命中 | 边界处理 |
| `{profile}` 占位符无法替换 | `{profile}` 保留原样，路径可能无效 → 降级为不持久化 | 安全降级 |

### 9.3 关键实现要点

```python
# inject_context() 中表达向量注入的异常隔离
ev_cfg = config.get("expression_vector", {})
if ev_cfg.get("enabled", False):
    try:
        ev = _ExpressionVector(ev_cfg, profile_path=profile)
        ev.load()
        ev.update(user_message or "", session_id)
        ev.save()
        parts.append(ev.format_inject(turn_count))
    except Exception:
        pass  # 表达向量的任何异常 → 静默跳过
```

**注意：** 表达向量的 `try/except` 在 `inject_context()` 外层 `try/except` 之内，形成**双层保护**。即使内层 catch 遗漏，外层仍能兜底返回 `None`。

---

## 10. 测试策略

### 10.1 测试文件结构

```
tests/
├── __init__.py
├── conftest.py
├── test_injector.py               # 现有测试 + 新增固定信号/表达向量集成测试
├── test_dynamic_rules.py          # 不变
├── test_variance.py               # 不变
├── test_modules_switch.py         # 不变
├── test_expression_vector.py      # 🆕 表达向量单元测试
└── test_fixed_signals.py          # 🆕 固定信号单元测试
```

### 10.2 `_ExpressionVector` 单元测试

测试文件：`tests/test_expression_vector.py`

| TC-ID | 用例 | 输入 | 期望 |
|:---|:---|:---|:---|
| EV-01 | 单维度命中累加 | `dimensions={"work": ["代码"]}`, `score_rules={"work": [1, -0.5, 1]}`, msg="写代码" | `work == 1.0` |
| EV-02 | 单维度未命中衰减 | 同上，msg="今天天气不错" | `work == -0.5 → max(0, -0.5) == 0.0` |
| EV-03 | 多维度混合命中 | 3 维度配置，msg 含 work+intimacy 关键词 | work/命中, future/未命中, intimacy/命中 |
| EV-04 | 权重生效 | `score_rules={"intimacy": [1, -0.5, 3]}`, msg 含 intimacy 关键词 | `intimacy == 3.0`（1×3） |
| EV-05 | 分数不跌破 0 | 初始 0，未命中 | `== 0.0`（非负） |
| EV-06 | 连续命中累积 | 连续 3 次 update 命中 work | `work == 3.0`（1×1×3次） |
| EV-07 | 连续命中+未命中混合 | 2次命中 + 3次未命中（work: [1, -0.5, 1]） | `work == max(0, 2 - 1.5) == 0.5` |
| EV-08 | 维度数量可变 | `dimensions={"a": [...], "b": [...], "c": [...], "d": [...]}`（4维） | 4 个维度独立计算 |
| EV-09 | score_rules 缺失维度 | dimensions 有 "work"，score_rules 无 "work" | 使用默认 `[1, -0.5, 1]` |
| EV-10 | score_rules 格式错误 | `score_rules={"work": [1]}`（长度不足） | 使用默认 `[1, -0.5, 1]` |
| EV-11 | 空消息 | msg="" | 所有维度未命中 |
| EV-12 | None 消息 | msg=None | 所有维度未命中，不抛异常 |
| EV-13 | 大小写不敏感 | keywords=["Bug"], msg="fix this bug" | 命中 |
| EV-14 | 关键词为子串 | keywords=["架构"], msg="架构师说..." | 命中（子串匹配） |

### 10.3 重置策略测试

| TC-ID | 用例 | 策略 | 期望 |
|:---|:---|:---|:---|
| RS-01 | session 重置 — 同 session | "session", session_id 不变 | 不清零，持续累积 |
| RS-02 | session 重置 — 新 session | "session", session_id 变化 | 清零 |
| RS-03 | daily 重置 — 同日 | "daily", 日期未变 | 不清零 |
| RS-04 | daily 重置 — 跨日 | "daily", 日期变化 | 清零 |
| RS-05 | none — 永不清零 | "none" | 不清零，跨 session 持续累积 |
| RS-06 | 非法 reset 值 | "weekly" | 回退为 "session" |

### 10.4 磁盘持久化测试

| TC-ID | 用例 | 期望 |
|:---|:---|:---|
| PERS-01 | save + load 往返 | load 后向量值与 save 前一致 |
| PERS-02 | 文件不存在 → load | 使用初始零值，不抛异常 |
| PERS-03 | 文件内容 JSON 格式错误 → load | 使用初始零值 |
| PERS-04 | 文件 version 不匹配 → load | 使用初始零值 |
| PERS-05 | 配置新增维度 → load | 新维度初始 0，已有维度保留 |
| PERS-06 | 配置删除维度 → load | 已删维度不恢复 |
| PERS-07 | 磁盘写入失败（权限等） | 静默降级，不抛异常 |
| PERS-08 | 父目录不存在 → save | 自动创建 |

### 10.5 注入格式测试

| TC-ID | 用例 | 期望 |
|:---|:---|:---|
| FMT-01 | 标准格式 | `"📊 [表达向量] future:1 intimacy:8 work:3 \| 第 22 轮"`（按字母序） |
| FMT-02 | 全零 | `"📊 [表达向量] future:0 intimacy:0 work:0 \| 第 1 轮"` |
| FMT-03 | 浮点值四舍五入 | `work=2.6` → `work:3` |

### 10.6 固定信号测试

测试文件：`tests/test_fixed_signals.py`

| TC-ID | 用例 | 输入 | 期望 |
|:---|:---|:---|:---|
| FS-01 | 消息长度 < 阈值 | msg="好"（2 字符）, threshold=50 | 返回 `"📏 消息较短"` |
| FS-02 | 消息长度 ≥ 阈值 | msg=50 字符, threshold=50 | 返回 `None` |
| FS-03 | 消息长度信号关闭 | enabled=false | 返回 `None` |
| FS-04 | 回复间隔 > 阈值 | last_reply_at 为 60 分钟前, threshold=30 | 返回 `"🎵 欢迎回来"` |
| FS-05 | 回复间隔 ≤ 阈值 | last_reply_at 为 10 分钟前, threshold=30 | 返回 `None` |
| FS-06 | 首次对话无 last_reply_at 文件 | 文件不存在 | 返回 `None`（不注入欢迎回来） |
| FS-07 | 回复间隔信号关闭 | enabled=false | 返回 `None` |
| FS-08 | 磁盘文件损坏 | JSON 格式错误 | 返回 `None`，不抛异常 |
| FS-09 | 写回 last_reply_at | 调用 `_save_reply_timing()` | 文件存在且包含有效时间戳 |

### 10.7 集成测试

测试文件：`tests/test_injector.py`（追加）

| TC-ID | 用例 | 验证 |
|:---|:---|:---|
| INT-EV-01 | expression_vector.enabled=true | 注入结果含 `"📊 [表达向量]"` |
| INT-EV-02 | expression_vector.enabled=false | 注入结果不含 `"📊 [表达向量]"` |
| INT-EV-03 | 不配置 expression_vector | 插件正常运行，结果不含表达向量 |
| INT-EV-04 | 关键词命中后向量值变化 | 连续调用 2 次，第二次向量值 > 第一次 |
| INT-FS-01 | fixed_signals.message_length.enabled=true + 短消息 | 注入结果含 `"📏 消息较短"` |
| INT-FS-02 | fixed_signals.reply_gap.enabled=true + 长间隔 | 注入结果含 `"🎵 欢迎回来"` |
| INT-FS-03 | 不配置 fixed_signals | 插件正常运行 |
| INT-ALL-01 | 全部新功能 + 现有模块同时开启 | 注入顺序正确（固定信号→表达向量→variance→...） |
| INT-ALL-02 | 注入顺序验证 | 表达向量在 dynamic_rules 之后、variance 之前 |

### 10.8 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 仅运行表达向量测试
python -m pytest tests/test_expression_vector.py -v

# 仅运行固定信号测试
python -m pytest tests/test_fixed_signals.py -v

# 回归测试——确保不破坏现有功能
python -m pytest tests/test_modules_switch.py tests/test_dynamic_rules.py -v
```

---

## 11. 实施阶段拆分

### Phase 1: 表达向量核心（~150 行）

| Step | 任务 | 文件 | 依赖 |
|:---|:---|:---|:---|
| P1-T1 | 创建 `_ExpressionVector` 类骨架 | `expression_vector.py` | 无 |
| P1-T2 | 实现 `update()` 算法 | `expression_vector.py` | P1-T1 |
| P1-T3 | 实现 `load()` / `save()` 磁盘持久化 | `expression_vector.py` | P1-T1 |
| P1-T4 | 实现 `should_reset()` 重置策略 | `expression_vector.py` | P1-T1 |
| P1-T5 | 实现 `format_inject()` 格式化 | `expression_vector.py` | P1-T1 |
| P1-T6 | 表达向量单元测试（TC EV-01~14, RS-01~6, PERS-01~8, FMT-01~3） | `test_expression_vector.py` | P1-T1~T5 |

### Phase 2: 固定层信号（~50 行）

| Step | 任务 | 文件 | 依赖 |
|:---|:---|:---|:---|
| P2-T1 | 实现 `_message_length_hint()` | `injector.py` | 无 |
| P2-T2 | 实现 `_reply_gap_hint()` / `_save_reply_timing()` | `injector.py` | 无 |
| P2-T3 | 固定信号单元测试（TC FS-01~9） | `test_fixed_signals.py` | P2-T1~T2 |

### Phase 3: 注入链路集成（~40 行）

| Step | 任务 | 文件 | 依赖 |
|:---|:---|:---|:---|
| P3-T1 | `inject_context()` 接入固定信号（步骤④a） | `injector.py` | P2-T1~T2 |
| P3-T2 | `inject_context()` 接入表达向量（步骤④b） | `injector.py` | P1-T1~T5 |
| P3-T3 | `_debug_summary()` 追加④a/④b状态行 | `injector.py` | P3-T1~T2 |
| P3-T4 | 更新 `examples/persona-config.json` | `examples/` | P3-T1~T2 |
| P3-T5 | 集成测试（TC INT-EV-01~4, INT-FS-01~3, INT-ALL-01~2） | `test_injector.py` | P3-T1~T3 |

### Phase 4: 验收与清理

| Step | 任务 | 文件 | 依赖 |
|:---|:---|:---|:---|
| P4-T1 | 全量测试通过（`python -m pytest tests/ -v`） | - | P1~P3 |
| P4-T2 | 更新 CLAUDE.md 注入顺序说明（如有必要） | `CLAUDE.md` | P4-T1 |

### 阶段依赖关系

```
P1 (表达向量核心) ──┐
                     ├─→ P3 (注入链路集成) → P4 (验收)
P2 (固定层信号)  ───┘
```

P1 和 P2 无依赖关系，可并行开发。P3 依赖 P1 和 P2 全部完成。

---

## 12. 审批检查清单

请主人 Kai.Xu 逐项确认：

- [ ] **架构定位** (§2)：表达向量夹在 dynamic_rules 和 variance 之间——模式切换是开关，表达底色是指南针，两者互补。是否认同？
- [ ] **Config schema** (§3)：`expression_vector` 使用独立 `enabled` 字段，不走 `modules` 体系。维度名由用户配置决定（不硬编码）。是否合理？
- [ ] **核心算法** (§4)：`[命中得分 × 权重]` 累加、`[未命中扣分 × 权重]` 衰减、`max(0, score)` 不跌破 0。是否满意？
- [ ] **注入格式** (§6)：`📊 [表达向量] work:N future:N intimacy:N | 第 N 轮`。向量值用 int(round(score))，维度按字母序。是否合适？
- [ ] **固定层信号** (§5)：消息长度 < 50 字符 → "📏 消息较短"，回复间隔 > 30 分钟 → "🎵 欢迎回来"。阈值可配置。是否认同？
- [ ] **向后兼容** (§3.5)：不配置 `expression_vector` / `fixed_signals` 时完全不影响现有功能。是否确认？
- [ ] **modules 独立性** (§7)：表达向量不在 `_MODULE_REGISTRY` 中注册，使用独立 `enabled` 字段。是否合理？
- [ ] **测试覆盖** (§10)：表达向量（14+6+8+3 = 31 用例）、固定信号（9 用例）、集成（9 用例）。是否充分？
- [ ] **实施阶段** (§11)：P1 表达向量核心 / P2 固定信号 / P3 注入集成 / P4 验收。是否认同？
- [ ] **下一步**：审批通过后进入 PLAN 阶段（`docs/dev/PLAN-002-表达向量与FuzzyUtility.md`）。

---

*🦊 知惠 · 2026-05-18 · SPEC-002 v1.0（基于 US-002 v1.0）· 等待主人审阅*
