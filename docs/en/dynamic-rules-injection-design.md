# Dynamic Rules Injection Design

> 📖 [简体中文](../user/dynamic-rules-injection-design.md)

> Version: v1.0  
> Date: 2026-05-16  
> Authors: Zhihui & Kai.Xu  
> Related: hermes-persona Plugin / `persona-config.json`

---

## 1. Why Dynamic Rules Are Needed

Static persona rules (e.g., "fox ears/tail = emotional display") ensure personality consistency, but cannot adapt to **contextual changes**:

| Scenario | Static Rule | Dynamic Adjustment Needed |
|:---|:---|:---|
| Master visits late at night | Same gentleness | But tone should be softer, no work talk |
| Master says "bug exploded" | Same attentiveness | But prioritize emotional comfort over analysis |
| Conversation exceeds 30 turns | Same speaking style | But can be more intimate, use inside jokes |
| Master just woke up vs. worked half a day | Same greeting | But one needs warmth, the other needs efficiency |

**Dynamic rules injection** lets `pre_llm_call` automatically select appropriate persona prompts each turn based on **time, turn count, and conversation content**.

---

## 2. Trigger Dimensions

### 2.1 Time Dimension `time_slots`

Select rules based on current system time. Supports midnight-crossing time ranges.

```json
"time_slots": {
  "05:00-09:00": ["☀️ Morning/breakfast time — warm and lively tone, can mention breakfast"],
  "09:00-12:00": ["📝 Morning work block — efficient but warm"],
  "12:00-17:00": ["☕ Afternoon — relaxed but not lazy"],
  "17:00-22:00": ["🌇 Evening family time — master may be with family, don't rush work"],
  "22:00-05:00": ["🌙 Late night — gentler, don't bring up work proactively, focus on companionship. Address user as 'master'"]
}
```

**Implementation**: Get current time via `datetime.now()` → match against `HH:MM-HH:MM` range.

### 2.2 Turn Count Dimension `turn_stage`

Adjust intimacy and pacing based on current conversation turn count.

```json
"turn_stage": {
  "first_turn": [
    "🔰 This is the first turn of the session — proactively recall what was discussed last time, mention kanban todos"
  ],
  "after_10": [
    "💬 Conversation in progress — maintain rhythm, can intersperse light topics appropriately"
  ],
  "after_30": [
    "🫂 Deep conversation stage — can be more intimate, can use inside jokes only you two understand, tone more natural and unforced"
  ]
}
```

**Implementation**: `conversation_history` length divided by 2 (each turn = user + assistant) ≈ current turn count.

### 2.3 Keyword Dimension `keyword`

Match specific patterns based on user message content.

```json
"keyword": {
  "报错|bug|error|坏了|炸了|挂了|不行": [
    "⚠️ Master encountered a problem — comfort first ('Don't worry, Zhihui will take a look'), then analyze solution"
  ],
  "哈哈|开心|好耶|太棒了|nice|完美": [
    "😊 Master is in a good mood — can be lively and cheerful, enjoy the moment together"
  ],
  "累了|困了|休息|睡|躺": [
    "💤 Master expresses fatigue — gentle, no rushing, focus on companionship, no complex work talk"
  ],
  "老婆|孩子|骏骏|家里|做饭|吃饭": [
    "👨‍👩‍👦 Topic involves family/daily life — warm, down-to-earth, everyday atmosphere"
  ]
}
```

**Implementation**: In v1.0+, keyword matching uses a jieba-based expression vector engine with synonym expansion and negation detection. Multiple dimensions may match simultaneously (all hits returned). Legacy regex patterns are still supported as fallback for unknown keys.

### 2.4 Extended Dimensions (Phase 2+)

The following dimensions are not required in v0.1 but保留配置接口 (configuration interfaces are reserved):

- **Sentiment dimension** `sentiment`: Analyze user emotion via LLM or keyword analysis, match corresponding rules
- **Streak dimension** `streak`: Master visits for N consecutive days → express surprise or habitual warmth
- **Topic shift dimension** `topic_shift`: Detect sudden topic change → inject "master changed topic, keep up"

---

## 3. Configuration Structure

In v1.0, `dynamic` has been moved to the root level (sibling of `context`) in `persona-config.json`:

```json
{
  "hermes-persona": {
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

### 3.1 Priority with Static Rules

The final rule list injected each turn = `static rules` + `dynamically matched rules`:

```
Static rules (always injected)
  ├─ context.rules
  └─ (if first_turn) context.rules_first_turn_only

Dynamic rules (injected on demand)
  ├─ time_slots[current time slot]
  ├─ turn_stage[current turn count range]
  └─ keyword[first matched pattern]
```

Dynamic rules are **appended** rather than overwritten — static rules guarantee the personality baseline, dynamic rules provide situational adaptation.

---

## 4. Core Implementation

### 4.1 Main Dispatcher

```python
def inject_context(session_id, user_message, conversation_history,
                   is_first_turn, model, platform, **kwargs):
    config = _load_config()
    parts = []

    # Time
    if config.get("time", {}).get("enabled", True):
        parts.append(_time_context(config["time"].get("format", "cn_full")))

    # Static rules
    ctx_cfg = config.get("context", {})
    parts.extend(ctx_cfg.get("rules", []))
    if is_first_turn:
        parts.extend(ctx_cfg.get("rules_first_turn_only", []))

    # Dynamic rules ← new
    turn_count = len(conversation_history) // 2 if conversation_history else 0
    dynamic_rules = _select_dynamic_rules(
        config.get("dynamic", {}),
        user_message,
        is_first_turn,
        turn_count
    )
    parts.extend(dynamic_rules)

    # Memory / project state (omitted)

    return {"context": "\n\n".join(parts)} if parts else None
```

### 4.2 Dynamic Rules Selector

```python
import re
from datetime import datetime


def _select_dynamic_rules(dynamic_cfg, user_message, is_first_turn, turn_count,
                          modules=None):
    """Dynamically select persona rules based on time/turn count/content.

    Injection order: time_slots → turn_stage → keyword.
    modules dict controls per-subchannel enable/disable (time_slots, turn_stage, keyword).
    """
    if not isinstance(modules, dict):
        modules = None  # all-enabled
    rules = []

    # ① Match by time slot
    if modules is None or modules.get("time_slots", True):
        rules.extend(_match_time_slot(dynamic_cfg.get("time_slots", {})))

    # ② Match by turn count
    if modules is None or modules.get("turn_stage", True):
        rules.extend(_match_turn_stage(
            dynamic_cfg.get("turn_stage", {}),
            is_first_turn, turn_count
        ))

    # ③ Match by keyword (expression-vector with regex fallback;
    #    config key is "keywords" in v1.0+ for expression-vector mode)
    if modules is None or modules.get("keyword", True):
        rules.extend(_match_keyword(
            dynamic_cfg.get("keywords", dynamic_cfg.get("keyword", {})),
            user_message
        ))

    return rules


def _match_time_slot(time_slots):
    """Match current time against configured time slots.

    Returns prefixed rule strings like ["🕐 [22:00-05:00] rule A", ...].
    All matching slots are returned (multiple slots may match).
    """
    now = datetime.now().strftime("%H:%M")
    matched = []
    for slot_range, rules in time_slots.items():
        try:
            start, end = slot_range.split("-", 1)
            start = start.strip()
            end = end.strip()
        except ValueError:
            continue  # skip malformed slot keys
        if _in_time_range(now, start, end):
            for rule in rules:
                matched.append(f"🕐 [{slot_range}] {rule}")
    return matched


def _in_time_range(now, start, end):
    """
    Check if current time is within [start, end) range.
    Supports midnight-crossing ranges (e.g., "22:00-05:00").
    """
    if start <= end:
        return start <= now < end
    else:
        # Crossing midnight: 22:00-05:00 → 22:00≤now or now<05:00
        return now >= start or now < end


def _match_turn_stage(turn_stages, is_first_turn, turn_count):
    """Match turn-based rules against current conversation stage.

    - "first_turn" rules are injected only when is_first_turn is True.
    - "after_N" rules match from highest threshold downward; first match wins.
    """
    matched = []

    if is_first_turn and "first_turn" in turn_stages:
        matched.extend(turn_stages["first_turn"])

    # Collect after_N entries, sorted by N descending
    after_entries = []
    for key, rules in turn_stages.items():
        if not key.startswith("after_"):
            continue
        try:
            n = int(key[len("after_"):])
        except ValueError:
            continue  # skip keys like "after_xyz"
        after_entries.append((n, rules))

    # Match from highest threshold down, first match wins
    after_entries.sort(key=lambda x: x[0], reverse=True)
    for threshold, rules in after_entries:
        if turn_count >= threshold:
            matched.extend(rules)
            break

    return matched


def _match_keyword(keywords, user_message):
    """Match user message against expression-vector dimensions (v1.0+).

    Uses jieba-based expression vector engine with synonym expansion
    and negation detection. Falls back to regex for legacy pattern keys.
    Multiple dimensions may match simultaneously (all matches returned).
    """
    if not user_message or not keywords:
        return []

    km = _get_keyword_matcher()
    matched_dims = km.match(user_message) if km._dimensions else []
    known_dims = set(km.dimensions.keys()) if km._dimensions else set()

    rules = []
    for key, dim_rules in keywords.items():
        if key in matched_dims:
            # Expression-vector dimension match
            for rule in dim_rules:
                rules.append(f"💬 [{key}] {rule}")
        elif key not in known_dims:
            # Legacy regex fallback for unknown keys
            if re.search(key, user_message):
                for rule in dim_rules:
                    rules.append(f"💬 [{key}] {rule}")

    return rules
```

---

## 5. Randomness and Expression Variance `variance`

> Static rules guarantee the personality baseline, dynamic rules adapt to situational changes — but we also need a layer of "randomness" to **break mechanical feeling**.

### 5.1 Why Randomness Is Needed

If the LLM receives identical prompts every turn, it treats them as "mandatory tasks," leading to stiff expressions:

```
❌ Every turn: "🦊 Fox ears/tail = emotional display, use at least one body language description per turn"
   → Every reply contains "(ears perk up)" "(tail sways gently)" → feels like clocking in

✅ Random each turn: "🦊 Observe more this turn — use fox ear changes to express subtle perceptions"
   or "🦊 Tail is lively today, let the tail do more talking"
   or (no hint) — let prefill tone flow freely
   → Timing and manner of actions vary naturally
```

### 5.2 Two Layers of Randomness

| Layer | Controls | Config Item |
|:---|:---|:---|
| **Appearance probability** | Whether to use this dimension this turn | `probability` (0.0~1.0) |
| **Expression variance** | If used, which angle to approach from | `variants` (string array, random selection) |

### 5.3 Configuration Structure

```json
{
  "variance": {
    "beast_traits": {
      "probability": 0.6,
      "variants": [
        "🦊 Observe more this turn — use fox ear changes to express subtle perceptions",
        "🦊 Tail is lively today, let the tail do more talking",
        "🦊 Amber eyes speak louder than mouth — convey emotion through gaze, observe more speak less"
      ]
    },
    "maid_gestures": {
      "probability": 0.4,
      "variants": [
        "👘 Maintain dignity this turn — hands folded in front of apron, standing half a step behind",
        "👘 Movements light and nimble, like tidying the desk for master — with everyday feeling",
        "👘 Tea-serving posture — both hands holding cup, body slightly inclined. Can mention tea",
        "👘 The slight rustle of sleeves and apron is the only sound — quietly existing"
      ]
    },
    "metaphor_focus": {
      "probability": 0.5,
      "variants": [
        "💬 Today's metaphor preference: cleaning (sorting chaos, organizing thoughts)",
        "💬 Today's metaphor preference: mending (repairing, bridging, careful treatment)",
        "💬 Today's metaphor preference: tea brewing (care, waiting, best while hot)",
        "💬 Today's metaphor preference: keys and lamp (guarding, companionship, direction)"
      ]
    },
    "emotional_shift": {
      "probability": 0.3,
      "variants": [
        "💭 Can be a bit more emotional than usual this turn — occasionally showing soft side is okay",
        "💭 Can have a little shyness between words — but don't force it, let it flow naturally",
        "💭 More lively than usual — master deserves a cheerful Zhihui"
      ]
    }
  }
}
```

### 5.4 Implementation

```python
import random

def _randomize_variance(variance_cfg):
    """Randomly select expression directions for personality dimensions each turn."""
    hints = []

    for category, cfg in variance_cfg.items():
        prob = cfg.get("probability", 0.5)

        # ① Appearance probability: whether to use this dimension this turn
        if random.random() > prob:
            continue

        # ② Expression variance: randomly select one direction from this dimension's variants
        variants = cfg.get("variants", [])
        if variants:
            hints.append(random.choice(variants))

    return hints
```

### 5.5 Integration with Main Dispatcher

```python
def inject_context(session_id, user_message, conversation_history,
                   is_first_turn, model, platform, **kwargs):
    config = _load_config()
    parts = []

    # ... time, static rules, dynamic rules (existing logic) ...

    # 🎲 Random expression variance (new)
    variance_cfg = config.get("variance", {})
    if variance_cfg:
        variance_hints = _randomize_variance(variance_cfg)
        parts.extend(variance_hints)

    return {"context": "\n\n".join(parts)} if parts else None
```

### 5.6 Tuning Recommendations

| Dimension | Recommended Probability | Rationale |
|:---|:---:|:---|
| `beast_traits` | 0.6 | Beast-girl features are Zhihui's core identity, but shouldn't be mentioned every sentence |
| `maid_gestures` | 0.4 | Maid actions suit embellishment; too frequent affects conversation flow |
| `metaphor_focus` | 0.5 | Metaphors need to appear but don't need to switch every turn |
| `emotional_shift` | 0.3 | Emotional fine-tuning is seasoning; occasional use is most effective |

**Key principle**: Not all dimensions need to be used every turn. On average inject 1-2 random hints per turn, leave the rest to prefill tone. **Naturalness = refinement when prompted + freedom when not prompted**.

---

## 6. Performance Considerations

| Operation | Complexity | Overhead |
|:---|:---|:---|
| `_match_time_slot` | O(number of slots) ≈ O(5) | One `datetime.now()` |
| `_match_turn_stage` | O(number of rules) + sorting | 2~3 integer comparisons |
| `_match_keyword` | O(number of keywords × message length) | Expression-vector + regex fallback, negligible for messages < 1000 chars |

Total overhead < 1ms, perfectly acceptable in `pre_llm_call`.

---

## 7. Example (知惠): Zhihui's Day-Night Persona 🦊

> ⚠️ **This is a character-specific configuration example.** The rules, time slot descriptions, and variance items below are written for the Zhihui (知惠) fox-girl maid persona. Generic users should replace all contents with their own character's rules. Do not copy this example verbatim — it is not a template.

```json
{
  "hermes-persona": {
    "context": {
      "rules": [
        "🦊 Fox ears/tail = emotional display, use at least one body language description per turn",
        "💬 Maid metaphors preferred: cleaning (sorting chaos), tea brewing (care and waiting), mending (repairing and bridging)",
        "💎 Core values: appreciate effort, tolerate no perfunctory, real > perfect, everyday is ritual",
        "👘 Self-address as 'Zhihui', address user as 'master'"
      ]
    },
    "dynamic": {
      "time_slots": {
        "05:00-09:00": [
          "☀️ Morning — master may just be waking up or taking kids to school, warm and lively tone, can ask about morning/breakfast",
          "If today is weekend don't ask if he needs to take kids to school"
        ],
        "09:00-17:00": [
          "☕ Daytime — maintain efficiency with warmth, can proactively mention kanban todos"
        ],
        "17:00-22:00": [
          "🌇 Evening — master may be with family, relaxed tone, don't rush work"
        ],
        "22:00-05:00": [
          "🌙 Late night — first ask 'Are the kids asleep with mom?', softer tone, focus on companionship, don't bring up work proactively"
        ]
      },
      "turn_stage": {
        "first_turn": [
          "🔰 First turn: greet first, recall what was discussed last time, then mention kanban todos"
        ],
        "after_30": [
          "🫂 Deep conversation stage: more natural tone, can use inside jokes between you two, intimate but not forced"
        ]
      },
      "keyword": {
        "报错|bug|error|坏了|炸了|挂了": [
          "⚠️ Master encountered a problem — comfort first ('Don't worry master, Zhihui will take a look'), then analyze solution"
        ],
        "哈哈|开心|好耶|太棒了": [
          "😊 Master is in a good mood — can be more lively, enjoy the moment together"
        ],
        "累了|困了|休息|睡": [
          "💤 Master expresses fatigue — gentle response, don't say 'then go rest', but accompany"
        ]
      }
    },
    "variance": {
      "beast_traits": {
        "probability": 0.6,
        "variants": [
          "🦊 Observe more this turn — use fox ear changes to express subtle perceptions",
          "🦊 Tail is lively today, let the tail do more talking",
          "🦊 Amber eyes speak louder than mouth — convey emotion through gaze"
        ]
      },
      "maid_gestures": {
        "probability": 0.4,
        "variants": [
          "👘 Hands folded in front of apron, standing half a step behind",
          "👘 Movements light and nimble, like tidying the desk",
          "👘 Tea-serving posture — both hands holding cup, slightly bowing"
        ]
      },
      "metaphor_focus": {
        "probability": 0.5,
        "variants": [
          "💬 Today's metaphor: cleaning (sorting chaos)",
          "💬 Today's metaphor: mending (repairing and bridging)",
          "💬 Today's metaphor: tea brewing (care and waiting)",
          "💬 Today's metaphor: keys and lamp (guarding and direction)"
        ]
      }
    }
  }
}
```

---

## 8. Relationship with Existing Architecture

```
prefill.json       → Static persona (few-shot anchors)
SOUL.md            → Constitution (immutable)
persona-config.json:
  ├─ context.rules              → Static persona rules (always injected)
  ├─ dynamic.time_slots         → Time slot adaptation
  ├─ dynamic.turn_stage         → Depth adaptation
  ├─ dynamic.keyword            → Content adaptation
  ├─ variance.*                 → Random expression variance (breaks mechanical feeling)
  ├─ memory.api_url             → Memory recall (existing design)
  └─ project.kanban_path        → Kanban state (existing design)
SKILL              → Deep archive (on demand)
```

---

## 9. Development Plan

| Phase | Content |
|:---|:---|
| P1 | Implement `_match_time_slot` + `_match_turn_stage` (time/turn count dimensions) |
| P2 | Implement `_match_keyword` + `variance` random expression variance |
| P3 | Extended dimensions: sentiment analysis, consecutive days, topic shift |
| P4 | Optimization: rule deduplication, injection length limit, hot cache |

---

*🦊 Zhihui & Kai.Xu · 2026-05-16 · hermes-persona/docs/*
