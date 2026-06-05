# 动态规则注入设计

> 📖 [English](../en/dynamic-rules-injection-design.md)

> 版本：v1.0
> 日期：2026-05-22
> 作者：Kai.Xu
> 关联：hermes-persona 插件 / `persona-config.json`

---

## 1. 为什么需要动态规则

静态行为守则（如"用中文回答所有问题"）可以保证角色的基本一致性，但无法适应**上下文变化**：

| 场景 | 静态规则能做的 | 需要动态调整的 |
|:---|:---|:---|
| 用户在深夜访问 | 保持同样的友好语气 | 但语气应更柔软，不主动提工作 |
| 用户说"代码炸了" | 保持同样的关注度 | 但优先安抚情绪而非直接分析 |
| 对话超过 30 轮 | 保持同样的说话风格 | 但可以更亲近，用默契的暗号 |
| 刚睡醒 vs 工作半天 | 保持同样的问候 | 但一个需要温暖，一个需要效率 |

**动态规则注入**让 `pre_llm_call` 每回合根据**时间、轮数、对话内容**自动选择合适的提示，使角色表现随情境自然变化。

---

## 2. 触发维度

### 2.1 时间维度 `time_slots`

根据系统当前时间选择规则。支持跨午夜的时段范围。

```json
"time_slots": {
  "05:00-09:00": ["☀️ 清晨时段——温暖活泼的语气，可以问候早安"],
  "09:00-12:00": ["📝 上午工作段——保持高效但温暖"],
  "12:00-17:00": ["☕ 午后——轻松但不懒散"],
  "17:00-22:00": ["🌇 晚间时段——放松，不急推工作"],
  "22:00-05:00": ["🌙 深夜——更温柔，不主动提工作，以陪伴为主"]
}
```

**实现**：通过 `datetime.now()` 获取当前时间 → 与 `HH:MM-HH:MM` 范围匹配。

### 2.2 轮数维度 `turn_stage`

根据当前对话轮数调整亲近度和节奏。

```json
"turn_stage": {
  "first_turn": [
    "🔰 会话首轮——主动回顾上次讨论了什么，建立连接"
  ],
  "after_10": [
    "💬 对话进行中——保持节奏，可以适当穿插轻松话题"
  ],
  "after_30": [
    "🫂 深度对话阶段——语气更自然，可以用只有你们懂的默契表达，亲密但不生硬"
  ]
}
```

**实现**：`conversation_history` 长度除以 2（每轮 = 用户 + 助手）≈ 当前轮数。取最大匹配（最高阈值优先），避免多档同时命中。

### 2.3 关键词维度 `keyword`

根据用户消息内容匹配特定模式。

```json
"keyword": {
  "报错|bug|error|坏了|炸了|挂了|不行": [
    "⚠️ 用户遇到了问题——先安抚，再分析方案"
  ],
  "哈哈|开心|好耶|太棒了|nice|完美": [
    "😊 用户心情好——可以活泼欢快，一起享受此刻"
  ],
  "累了|困了|休息|睡|躺": [
    "💤 用户表达疲倦——温柔回应，不催不赶，以陪伴为主，不提复杂工作"
  ],
  "谢谢|感谢|辛苦了": [
    "用户表达了感谢——真诚回应，表达乐意继续帮助"
  ]
}
```

**实现**：对用户消息（`user_message`）逐一匹配正则模式，命中则注入对应规则。v1.0 中所有命中的维度**同时返回**，不限于单条。

### 2.4 拓展维度（Phase 2+）

以下维度在 v1.0 中保留配置接口，尚未实现：

- **情感维度** `sentiment`：通过 LLM 或关键词分析用户情绪，匹配对应规则
- **连续天数维度** `streak`：用户连续 N 天访问 → 表达惊喜或习惯性温暖
- **话题转移维度** `topic_shift`：检测话题突变 → 注入"用户换了话题，跟上"

---

## 3. 配置结构

动态规则在 `persona-config.json` 中作为**顶层 `dynamic` 节点**（v1.0 结构）：

```json
{
  "hermes-persona": {
    "modules": {
      "dynamic": { "time_slots": true, "turn_stage": true, "keyword": true }
    },
    "context": {
      "rules": [],
      "rules_first_turn_only": []
    },
    "dynamic": {
      "time_slots": {},
      "turn_stage": {},
      "keyword": {}
    }
  }
}
```

> 注意：`modules.dynamic` 是开关，可设为 `false`（关闭全部动态规则）或对象（逐通道控制）。规则本身定义在顶层 `dynamic` 下。

### 3.1 与静态规则的优先级

每回合注入的最终规则列表 = `静态规则` + `动态匹配的规则`：

```
静态规则（始终注入）
  ├─ context.rules
  └─ （若 is_first_turn） context.rules_first_turn_only

动态规则（按需注入）
  ├─ dynamic.time_slots[当前时段]
  ├─ dynamic.turn_stage[当前轮数范围]
  └─ dynamic.keyword[所有匹配的维度]
```

动态规则**追加**而非覆盖——静态规则保证人格基线，动态规则提供情境适配。

### 3.2 规则注入顺序（完整）

每回合的最终上下文按以下固定顺序拼接（参见[插件设计文档](./hermes-persona-plugin-design.md)第六章）：

```
① time               → 时间上下文
①b weather           → 天气注入
② static_rules       → 静态行为守则
③ dynamic            → 动态规则（time_slots → turn_stage → keyword）
④a fixed_signals     → 固定信号
④b expression_vector → 表达向量
④ variance           → 随机表达变化
⑤ memory             → 记忆召回
⑥ kanban             → 看板状态（首轮）
```

---

## 4. 核心实现

### 4.1 主调度器

```python
def inject_context(session_id, user_message, conversation_history,
                   is_first_turn, model, platform, **kwargs):
    config = _load_config()
    parts = []
    modules = config.get("modules", {})

    # 时间
    if modules.get("time", True):
        parts.append(_time_context(config.get("time", {}).get("format", "cn_full")))

    # 静态规则
    if modules.get("static_rules", True):
        ctx_cfg = config.get("context", {})
        parts.extend(ctx_cfg.get("rules", []))
        if is_first_turn:
            parts.extend(ctx_cfg.get("rules_first_turn_only", []))

    # 动态规则 ← 从顶层 dynamic 节点读取
    dyn_modules = modules.get("dynamic", True)
    if dyn_modules:
        turn_count = len(conversation_history) // 2 if conversation_history else 0
        dynamic_rules = _select_dynamic_rules(
            config.get("dynamic", {}),
            user_message,
            is_first_turn,
            turn_count
        )
        parts.extend(dynamic_rules)

    # 随机变化 / 记忆 / 看板（略）

    return {"context": "\n\n".join(parts)} if parts else None
```

### 4.2 动态规则选择器

```python
import re
from datetime import datetime


def _select_dynamic_rules(dynamic_cfg, user_message, is_first_turn, turn_count):
    """根据时间 / 轮数 / 内容动态选择人格规则。"""
    rules = []

    # ① 按时间段匹配
    rules.extend(_match_time_slot(dynamic_cfg.get("time_slots", {})))

    # ② 按轮数匹配
    rules.extend(_match_turn_stage(
        dynamic_cfg.get("turn_stage", {}),
        is_first_turn, turn_count
    ))

    # ③ 按关键词匹配（返回所有命中维度）
    rules.extend(_match_keyword(
        dynamic_cfg.get("keyword", {}),
        user_message
    ))

    return rules


def _match_time_slot(time_slots):
    now = datetime.now()
    now_str = now.strftime("%H:%M")

    for slot_range, slot_rules in time_slots.items():
        try:
            start, end = slot_range.split("-")
            if _in_time_range(now_str, start, end):
                return [f"🕐 [{slot_range}] {r}" for r in slot_rules]
        except ValueError:
            continue
    return []


def _in_time_range(now, start, end):
    """
    判断当前时间是否在 [start, end) 区间内。
    支持跨午夜区间（如 "22:00-05:00"）。
    """
    if start <= end:
        return start <= now < end
    else:
        # 跨午夜：22:00-05:00 → 22:00≤now 或 now<05:00
        return now >= start or now < end


def _match_turn_stage(turn_stages, is_first_turn, turn_count):
    rules = []

    if is_first_turn and "first_turn" in turn_stages:
        rules.extend(turn_stages["first_turn"])

    # 从高到低匹配阈值（避免多档命中）
    thresholds = sorted(
        [k for k in turn_stages if k.startswith("after_")],
        key=lambda x: int(x.split("_")[1]),
        reverse=True
    )
    for key in thresholds:
        threshold = int(key.split("_")[1])
        if turn_count >= threshold:
            rules.extend(turn_stages[key])
            break  # 只匹配最高档

    return rules


def _match_keyword(keywords, user_message):
    if not user_message:
        return []

    # v1.0：所有匹配的维度同时返回（all-matches）
    matched = []
    for pattern, kw_rules in keywords.items():
        if re.search(pattern, user_message):
            matched.extend([f"💬 [{pattern}] {r}" for r in kw_rules])

    return matched
```

---

## 5. 随机性与表达变化 `variance`

> 静态规则保证人格基线，动态规则适配情境变化——但还需要一层「随机性」来**打破机械感**。

### 5.1 为什么需要随机性

如果 LLM 每轮收到完全相同的提示，它会将其视为"必须执行的任务"，导致表达僵硬：

```
❌ 每轮都收到："用温暖友好的语气回复"
   → 每句回复都是"好的呢~"、"没问题哦~" → 像打卡

✅ 本轮随机抽到："今天更多观察——用简短的回应传递关注"
   或 "尾巴轻轻摆动——让身体语言说话"
   或 （无额外提示）——让 prefill 的基调自然流淌
   → 动作出现的时机和方式自然变化
```

### 5.2 两层随机

| 层 | 控制什么 | 配置项 |
|:---|:---|:---|
| **出现概率** | 本回合是否使用该维度 | `probability`（0.0~1.0） |
| **表达变化** | 若使用，从哪个角度展开 | `variants`（字符串数组，随机选取） |

### 5.3 通用配置示例

```json
{
  "variance": {
    "body_language": {
      "probability": 0.6,
      "variants": [
        "今天尾巴很活泼，让尾巴多说说话",
        "耳朵轻轻抖动了一下，察觉到了什么",
        "尾巴缓缓摆动，正在认真思考"
      ]
    },
    "speech_tone": {
      "probability": 0.4,
      "variants": [
        "本回合语气更柔和一些，像在轻声交谈",
        "今天说话可以俏皮一点——偶尔的活泼让人放松",
        "保持沉稳克制的语气，用行动而非言语表达"
      ]
    },
    "metaphor": {
      "probability": 0.3,
      "variants": [
        "今天的比喻：钥匙和灯（守护与方向）",
        "今天的比喻：编织（耐心与连接）",
        "今天的比喻：茶与等待（沉淀与用心）"
      ]
    }
  }
}
```

### 5.4 实现

```python
import random

def _randomize_variance(variance_cfg):
    """每回合随机选择人格维度的表达方向。"""
    hints = []

    for category, cfg in variance_cfg.items():
        prob = cfg.get("probability", 0.5)

        # ① 出现概率：本回合是否使用该维度
        if random.random() > prob:
            continue

        # ② 表达变化：从该维度的变体中随机选一个方向
        variants = cfg.get("variants", [])
        if variants:
            hints.append(random.choice(variants))

    return hints
```

### 5.5 与主调度器的集成

```python
def inject_context(session_id, user_message, conversation_history,
                   is_first_turn, model, platform, **kwargs):
    config = _load_config()
    parts = []
    modules = config.get("modules", {})

    # ... 时间、静态规则、动态规则（已有逻辑） ...

    # 🎲 随机表达变化
    if modules.get("variance", True):
        variance_cfg = config.get("variance", {})
        if variance_cfg:
            variance_hints = _randomize_variance(variance_cfg)
            parts.extend(variance_hints)

    return {"context": "\n\n".join(parts)} if parts else None
```

### 5.6 调参建议

| 维度 | 推荐概率 | 理由 |
|:---|:---:|:---|
| `body_language`（身体语言） | 0.6 | 核心身份特征，但不宜每句都有 |
| `speech_tone`（语气变化） | 0.4 | 语气点缀需要适度，太频繁影响对话流畅度 |
| `metaphor`（比喻风格） | 0.3 | 比喻应偶尔出现，每次出现才令人印象深刻 |

**核心原则**：不需要每回合所有维度都用上。平均每回合注入 1-2 条随机提示即可，剩下的交给 prefill 基调自然发挥。**自然 = 提示时有雕琢 + 不提示时有自由**。

---

## 6. 性能考量

| 操作 | 复杂度 | 开销 |
|:---|:---|:---|
| `_match_time_slot` | O(时段数) ≈ O(5) | 一次 `datetime.now()` |
| `_match_turn_stage` | O(规则档数) + 排序 | 2~3 次整数比较 |
| `_match_keyword` | O(关键词组数 × 消息长度) | 正则匹配，消息 < 1000 字符时可忽略 |

总开销 < 1ms，在 `pre_llm_call` 中完全可接受。

---

## 7. 与现有架构的关系

```
prefill.json         → 静态人设（few-shot 锚点）
SOUL.md              → 人格宪法（不可变）
persona-config.json:
  ├─ modules                    → 模块总控开关
  ├─ context.rules              → 静态行为守则（始终注入）
  ├─ context.rules_first_turn_only → 首轮专属规则
  ├─ dynamic.time_slots         → 时段适配
  ├─ dynamic.turn_stage         → 深度适配
  ├─ dynamic.keyword            → 内容适配
  ├─ variance.*                 → 随机表达变化（打破机械感）
  ├─ expression_vector.*        → 多维度表达向量
  ├─ fixed_signals.*            → 固定信号检测
  ├─ memory.api_url             → 记忆召回
  └─ project.kanban_path        → 看板状态
SKILL                → 深度档案（按需调用）
```

---

## 8. 开发计划

| 阶段 | 内容 |
|:---|:---|
| P1 | 实现 `_match_time_slot` + `_match_turn_stage`（时间/轮数维度） |
| P2 | 实现 `_match_keyword` + `variance` 随机表达变化 |
| P3 | 拓展维度：情感分析、连续天数、话题转移 |
| P4 | 优化：规则去重、注入长度限制、热缓存 |

---

*hermes-persona v1.0 · 2026-05-22*
