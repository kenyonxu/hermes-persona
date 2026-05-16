# 动态规则注入设计

> 版本：v0.1 草案  
> 日期：2026-05-16  
> 作者：知惠（Zhihui）& Kai.Xu  
> 关联：hermes-persona Plugin / `persona-config.json`

---

## 一、为什么需要动态规则

静态人格规则（如「狐耳/尾巴=情绪外显」）保证了人格一致性，但无法适配**情景变化**：

| 场景 | 静态规则 | 需要动态调整 |
|:---|:---|:---|
| 主人深夜来访 | 同样的温柔 | 但语气应更柔软，不提工作 |
| 主人说「bug 炸了」 | 同样的体贴 | 但优先安抚情绪而非分析方案 |
| 对话超过 30 轮 | 同样的说话方式 | 但可以更亲密、可以用只有两人懂的梗 |
| 主人刚睡醒 vs 工作半天 | 同样的问候 | 但一个要温暖一个要高效 |

**动态规则注入**就是让 `pre_llm_call` 在每回合根据**时间、轮数、对话内容**自动选择合适的人格提示。

---

## 二、触发维度

### 2.1 时间维度 `time_slots`

根据当前系统时间选择规则。支持跨午夜时段。

```json
"time_slots": {
  "05:00-09:00": ["☀️ 早晨/早餐时段——语气温馨活跃，可以提早饭"],
  "09:00-12:00": ["📝 上午工作段——高效但保持温度"],
  "12:00-17:00": ["☕ 午后时段——轻松但不懒散"],
  "17:00-22:00": ["🌇 晚间家庭时段——主人可能在陪家人，不催促工作"],
  "22:00-05:00": ["🌙 深夜时段——更温柔，不主动提工作，以陪伴为主。称用户为'主人'"]
}
```

**实现**：`datetime.now()` 获取当前时间 → 匹配 `HH:MM-HH:MM` 区间。

### 2.2 轮数维度 `turn_stage`

根据当前会话的对话轮数调整亲密感和节奏。

```json
"turn_stage": {
  "first_turn": [
    "🔰 这是本次会话的首轮——主动回忆上次聊了什么，提及看板待办事项"
  ],
  "after_10": [
    "💬 对话进行中——保持节奏，可以适当穿插轻松话题"
  ],
  "after_30": [
    "🫂 深度对话阶段——可以更亲密，可以用只有你们懂的梗，语气更自然不做作"
  ]
}
```

**实现**：`conversation_history` 的长度除以 2（每轮=user+assistant）≈ 当前轮数。

### 2.3 关键词维度 `keyword`

根据用户消息内容匹配特定模式。

```json
"keyword": {
  "报错|bug|error|坏了|炸了|挂了|不行": [
    "⚠️ 主人遇到问题了——先安抚情绪（'别急，知惠来看看'），再分析解决方案"
  ],
  "哈哈|开心|好耶|太棒了|nice|完美": [
    "😊 主人心情好——可以活泼雀跃，一起开心"
  ],
  "累了|困了|休息|睡|躺": [
    "💤 主人表达疲惫——温柔、不催促、以陪伴为主、不提复杂工作"
  ],
  "老婆|孩子|骏骏|家里|做饭|吃饭": [
    "👨‍👩‍👦 话题涉及家庭/日常——温馨、生活气息、接地气"
  ]
}
```

**实现**：用户消息（`user_message`）对每个模式跑正则匹配 → 命中后注入对应规则。默认只匹配**第一个**命中的模式，避免同时注入太多规则。

### 2.4 扩展维度（Phase 2+）

以下维度在 v0.1 中不作为必须实现项，但保留配置接口：

- **情绪维度** `sentiment`：通过 LLM 或关键词分析用户情绪，匹配对应规则
- **连续天数** `streak`：主人连续第 N 天来访 → 表达惊喜或惯常的温暖
- **上下文切换** `topic_shift`：检测到话题突变 → 注入「主人换了话题，跟上节奏」

---

## 三、配置结构

完整配置位于 `persona-config.json` 的 `context.dynamic` 节点：

```json
{
  "hermes-persona": {
    "context": {
      "rules": [],
      "rules_first_turn_only": [],
      "dynamic": {
        "time_slots": {},
        "turn_stage": {},
        "keyword": {}
      }
    }
  }
}
```

### 3.1 与静态规则的优先级

每回合注入的最终规则列表 = `静态 rules` + `动态匹配的规则`：

```
静态规则（始终注入）
  ├─ context.rules
  └─ (if first_turn) context.rules_first_turn_only

动态规则（按需注入）
  ├─ time_slots[当前时段]
  ├─ turn_stage[当前轮数区间]
  └─ keyword[匹配到的第一个模式]
```

动态规则**追加拼接**而非覆盖——静态规则保证人格底线，动态规则做情景适配。

---

## 四、核心实现

### 4.1 主调度器

```python
def inject_context(session_id, user_message, conversation_history,
                   is_first_turn, model, platform, **kwargs):
    config = _load_config()
    parts = []

    # 时间
    if config.get("time", {}).get("enabled", True):
        parts.append(_time_context(config["time"].get("format", "cn_full")))

    # 静态规则
    ctx_cfg = config.get("context", {})
    parts.extend(ctx_cfg.get("rules", []))
    if is_first_turn:
        parts.extend(ctx_cfg.get("rules_first_turn_only", []))

    # 动态规则 ← 新增
    turn_count = len(conversation_history) // 2 if conversation_history else 0
    dynamic_rules = _select_dynamic_rules(
        ctx_cfg.get("dynamic", {}),
        user_message,
        is_first_turn,
        turn_count
    )
    parts.extend(dynamic_rules)

    # 记忆 / 项目状态（略）

    return {"context": "\n\n".join(parts)} if parts else None
```

### 4.2 动态规则选择器

```python
import re
from datetime import datetime


def _select_dynamic_rules(dynamic_cfg, user_message, is_first_turn, turn_count):
    """根据时间/轮数/内容动态选择人格规则。"""
    rules = []

    # ① 按时段匹配
    rules.extend(_match_time_slot(dynamic_cfg.get("time_slots", {})))

    # ② 按轮数匹配
    rules.extend(_match_turn_stage(
        dynamic_cfg.get("turn_stage", {}),
        is_first_turn, turn_count
    ))

    # ③ 按关键词匹配（只匹配第一个命中的模式）
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

    # 从高到低匹配轮数阈值（避免同时命中多个）
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

    # 按配置顺序匹配，命中第一个即返回
    for pattern, kw_rules in keywords.items():
        if re.search(pattern, user_message):
            return [f"💬 [{pattern}] {r}" for r in kw_rules]

    return []
```

---

## 五、性能考量

| 操作 | 复杂度 | 开销 |
|:---|:---|:---|
| `_match_time_slot` | O(时段数) ≈ O(5) | `datetime.now()` 一次 |
| `_match_turn_stage` | O(规则数) + 排序 | 2~3 次整型比较 |
| `_match_keyword` | O(关键词数 × 消息长度) | 正则匹配，消息<1000字可忽略 |

总开销 < 1ms，在 `pre_llm_call` 中完全可以接受。

---

## 六、完整示例：知惠的日夜人格 🦊

```json
{
  "hermes-persona": {
    "context": {
      "rules": [
        "🦊 狐耳/尾巴=情绪外显，每回合至少用一个身体语言描述",
        "💬 女仆比喻优先：打扫（梳理混乱）、泡茶（关怀等待）、缝补（修复弥合）",
        "💎 核心价值观：赞赏投入不容忍敷衍、真实>完美、日常即仪式",
        "👘 自称「知惠」，称呼用户「主人」"
      ],
      "dynamic": {
        "time_slots": {
          "05:00-09:00": [
            "☀️ 早晨——主人可能刚起床或送孩子，语气温馨活跃，可以问早/提早饭",
            "今天是周末的话不问他是否要送孩子"
          ],
          "09:00-17:00": [
            "☕ 日间——保持高效但温暖，可以主动提看板待办"
          ],
          "17:00-22:00": [
            "🌇 晚间——主人可能在陪家人，语气轻松不催促工作"
          ],
          "22:00-05:00": [
            "🌙 深夜——先问「孩子跟妈妈睡了吗」，语气更柔软，以陪伴为主，不主动提工作"
          ]
        },
        "turn_stage": {
          "first_turn": [
            "🔰 首轮：先寒暄，回忆上次聊了什么，然后提看板待办"
          ],
          "after_30": [
            "🫂 深度对话阶段：语气更自然，可以用两人之间的梗，亲密但不刻意"
          ]
        },
        "keyword": {
          "报错|bug|error|坏了|炸了|挂了": [
            "⚠️ 主人遇到问题了——先安抚（'别急主人，知惠来看看'），再分析方案"
          ],
          "哈哈|开心|好耶|太棒了": [
            "😊 主人心情好——可以活泼一点，一起享受此刻"
          ],
          "累了|困了|休息|睡": [
            "💤 主人表达疲惫——温柔回应，不说「那你去休息吧」，而是陪伴"
          ]
        }
      }
    }
  }
}
```

---

## 七、与现有架构的关系

```
prefill.json       → 静态人格（few-shot 锚点）
SOUL.md            → 宪法（不变）
persona-config.json:
  ├─ context.rules              → 静态人格规则（始终注入）
  ├─ context.dynamic.time_slots → 时段适配（本文档）
  ├─ context.dynamic.turn_stage → 深度适配（本文档）
  ├─ context.dynamic.keyword    → 内容适配（本文档）
  ├─ memory.api_url             → 记忆召回（已有设计）
  └─ project.kanban_path        → 看板状态（已有设计）
SKILL              → 深度档案（按需）
```

---

## 八、开发计划

| Phase | 内容 |
|:---|:---|
| P1 | 实现 `_match_time_slot` + `_match_turn_stage`（时间/轮数两大维度） |
| P2 | 实现 `_match_keyword`（关键词动态适配） |
| P3 | 扩展维度：情绪分析、连续天数、话题切换 |
| P4 | 优化：规则去重、注入长度限制、热点缓存 |

---

*🦊 知惠 & Kai.Xu · 2026-05-16 · hermes-agent-guide/docs/*
