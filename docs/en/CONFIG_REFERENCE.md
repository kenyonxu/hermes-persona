# hermes-persona Configuration Reference

> 📖 [简体中文](../user/CONFIG_REFERENCE.md)

> Complete `persona-config.json` field reference — v1.0, covering all modules

---

## Configuration Structure Overview

```json
{
  "hermes-persona": {
    "modules": { ... },
    "time": { ... },
    "context": { ... },
    "dynamic": { ... },
    "expression_vector": { ... },
    "fixed_signals": { ... },
    "variance": { ... },
    "memory": { ... },
    "project": { ... },
    "guard": { ... }
  }
}
```

All configuration resides under the `"hermes-persona"` key. An empty config `{}` works out of the box.

---

## 1. `modules` — Module Master Switch

Controls enable/disable for each functional module. Disabled modules are not executed at all.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `time` | `boolean` | `true` | Time context injection |
| `static_rules` | `boolean` | `true` | Static behavior rules injection |
| `dynamic` | `boolean` or `object` | `true` | Dynamic rules master switch. Set to `false` to disable all sub-channels. |
| `dynamic.time_slots` | `boolean` | `true` | Time slot sub-channel |
| `dynamic.turn_stage` | `boolean` | `true` | Turn stage sub-channel |
| `dynamic.keyword` | `boolean` | `true` | Keyword trigger sub-channel |
| `expression_vector` | `boolean` | `false` | Multi-dimensional expression vector (requires `expression_vector.enabled` as well) |
| `fixed_signals` | `boolean` | `true` | Fixed signal detection (message length / reply gap / daily turn count) |
| `variance` | `boolean` | `true` | Random expression variation |
| `memory` | `boolean` | `false` | External memory recall (requires `pip install httpx`) |
| `kanban` | `boolean` | `false` | Kanban status injection (first turn only) |
| `translate` | `boolean` | `false` | Injection rule narrative translation |
| `debug` | `boolean` or `object` | `false` | Debug detailed mode |
| `sources_blacklist` | `string[]` | `[]` | Source filter list |

> Missing keys in `modules` are automatically backfilled from legacy format or registry defaults — a missing key will never cause a module to silently disable.

### Example

```json
{
  "modules": {
    "time": true,
    "static_rules": true,
    "dynamic": { "time_slots": true, "turn_stage": false, "keyword": true },
    "expression_vector": true,
    "fixed_signals": true,
    "variance": true,
    "memory": false,
    "kanban": true,
    "translate": true,
    "debug": { "enabled": false, "detail": "detailed" },
    "sources_blacklist": ["cron", "api_server", "webhook"]
  }
}
```

---

## 2. `time` — Time Injection

Controls the current time information injected before each turn. In translate mode, time is woven into the persona narrative as natural language.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `true` | Whether to inject time context |
| `format` | `string` | `"cn_full"` | Time format. See available values below. |

### `format` Values

| Value | Example Output | Description |
|:---|:---|:---|
| `"cn_full"` | `🕐 2026年5月16日 周五 14:30` | Full Chinese format (default) |
| `"iso"` | `🕐 2026-05-16T14:30:00` | ISO 8601 |
| `"compact"` | `🕐 05/16 14:30` | Compact numeric format |

Unknown format values automatically fall back to `"cn_full"`.

### Example

```json
{
  "time": {
    "enabled": true,
    "format": "cn_full"
  }
}
```

---

## 3. `context` — Static Rules

User-defined behavior rules injected through two channels.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `rules` | `string[]` | `[]` | Static rules injected every turn |
| `rules_first_turn_only` | `string[]` | `[]` | Rules injected only on the first turn of a session |

### Example

```json
{
  "context": {
    "rules": [
      "Answer all questions in Chinese",
      "Keep responses concise, under 200 words",
      "Maintain a friendly, professional tone"
    ],
    "rules_first_turn_only": [
      "At session start, automatically review recent context"
    ]
  }
}
```

---

## 4. `dynamic` — Dynamic Rules

Behavior directives automatically selected based on runtime conditions (time, turn count, keywords). Three sub-channels, each independently controllable.

### 4.1 `time_slots` — Time Slot Rules

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `time_slots` | `object` | `{}` | Keys are time ranges in `"HH:MM-HH:MM"` format; values are arrays of rule text. Supports overnight ranges. |

**Matching logic**: A slot matches when the current time falls within `[start, end)`. For overnight ranges (e.g. `"22:00-05:00"`), the logic is `now >= start OR now < end`. The first matching slot of the day takes effect.

**Injection format**: `🕐 [time range] rule content`

```json
{
  "time_slots": {
    "22:00-05:00": [
      "Late night — respond more gently and quietly"
    ],
    "09:00-17:00": [
      "Working hours — keep responses professional and efficient"
    ]
  }
}
```

### 4.2 `turn_stage` — Turn Stage Rules

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `turn_stage` | `object` | `{}` | Keys are `"first_turn"` or `"after_N"` (where N is an integer); values are arrays of rule text. |

| Key | Match Condition | Description |
|:---|:---|:---|
| `"first_turn"` | `is_first_turn=true` | First turn of a session |
| `"after_N"` | turn count >= N | Takes the maximum matching threshold (highest N first) |

**Turn count source**:
- Non-translate mode: `conversation_message_count / 2`
- Translate mode: daily cumulative turn count across sessions (resets at midnight)

```json
{
  "turn_stage": {
    "first_turn": ["First interaction — establish a friendly tone"],
    "after_10": ["Conversation has been going for a while — maintain context continuity"],
    "after_30": ["Deep conversation stage — summarize and confirm when appropriate"]
  }
}
```

### 4.3 `keyword` — Keyword Trigger Rules

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `keyword` | `object` | `{}` | Keys are regex patterns or dimension names; values are arrays of rules injected on match. |

All matching dimensions are returned simultaneously (all-matches), not limited to a single match. The more dimensions a user message hits, the more rules are injected.

**Injection format**: `💬 [regex/dimension name] rule content`

```json
{
  "keyword": {
    "报错|bug|error|崩溃|挂了": [
      "User is experiencing an issue — prioritize troubleshooting over explanation",
      "Offer a temporary workaround first, then analyze the root cause"
    ],
    "哈哈|开心|笑|乐": [
      "User is in a positive mood — keep the atmosphere light"
    ]
  }
}
```

---

## 5. `expression_vector` — Multi-Dimensional Expression Vector

Automatically tracks conversation topic distributions and guides the Agent to naturally adjust expression style based on the current conversation trajectory.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | Whether to enable (must also set `modules.expression_vector` to `true`) |
| `dimensions` | `object` | `{}` | Dimension definitions. Keys are dimension names; values are dimension config objects. |
| `reset` | `string` | `"session"` | Reset strategy: `"session"` / `"daily"` / `"none"` |
| `storage_path` | `string` | `""` | State file path. Empty string uses the default path. |

### Dimension Config Fields

| Field | Type | Description |
|:---|:---|:---|
| `label` | `string` | Dimension display name |
| `keywords_path` | `string` | Path to a keyword vocabulary JSON file (relative to plugin directory) |
| `keywords` | `string[]` | Alternatively, inline keyword list (mutually exclusive with `keywords_path`) |
| `score_rules` | `number[4]` | `[hit_bonus, miss_penalty, weight, decay_factor]` |

```json
{
  "expression_vector": {
    "enabled": true,
    "dimensions": {
      "work": {
        "label": "Work",
        "keywords_path": "keywords/work.json",
        "score_rules": [1, -0.5, 2, 0.95]
      },
      "casual": {
        "label": "Casual",
        "keywords_path": "keywords/casual.json",
        "score_rules": [1, -1, 1, 0.95]
      }
    },
    "reset": "session",
    "storage_path": "state/expression_vector.json"
  }
}
```

> The number and names of dimensions are entirely user-defined. Each dimension maps to an independent keyword vocabulary file.

---

## 6. `fixed_signals` — Fixed Signal Detection

Three types of automatic detection based on message characteristics, independent of configured rules.

### 6.1 `message_length` — Message Length

Injects a brevity hint when user messages are too short.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | Whether to enable |
| `threshold` | `integer` | `50` | Character count threshold. Triggers when message length < threshold. |

### 6.2 `reply_gap` — Reply Gap

Injects a welcome-back hint when the user returns after a long absence.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | Whether to enable |
| `threshold_minutes` | `integer` | `30` | Gap threshold in minutes |
| `storage_path` | `string` | `""` | File path for persisting last reply time |

### 6.3 `daily_turn_count` — Daily Turn Count

Accumulates daily conversation turns across sessions. Deep-interaction thresholds can be configured.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | Whether to enable |
| `thresholds` | `object` | `{}` | Threshold mapping. Keys are label names; values are turn count thresholds. |
| `storage_path` | `string` | `""` | Turn count state file path |

> Turn count accumulates across sessions within a single day and resets at midnight. Non-conversation sources (see section 11) do not count toward the total.

```json
{
  "fixed_signals": {
    "message_length": { "enabled": true, "threshold": 50 },
    "reply_gap": { "enabled": true, "threshold_minutes": 30 },
    "daily_turn_count": {
      "enabled": true,
      "thresholds": { "morning": 10, "familiar": 50 }
    }
  }
}
```

---

## 7. `variance` — Random Expression Variation

Randomly triggers variant entries with configurable probability. Typical use cases: character-specific body language, verbal tics, or metaphorical styles.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `<category>` | `object` | — | Arbitrarily named dimension containing `probability` and `variants`. |

### Dimension Fields

| Field | Type | Required | Description |
|:---|:---|:---|:---|
| `probability` | `number` | Yes | Trigger probability, range `0.0` ~ `1.0` |
| `variants` | `string[]` | Yes | Variant list. One is randomly selected on trigger. |

**Random mechanism** (two-layer):
1. `random() < probability` decides whether this dimension is triggered this turn
2. On trigger, `random.choice` picks one item from `variants`

```json
{
  "variance": {
    "body_language": {
      "probability": 0.6,
      "variants": [
        "Tail is very lively today — let the tail do more of the talking",
        "Ears twitched gently",
        "Tail swayed slowly, deep in thought"
      ]
    },
    "metaphor": {
      "probability": 0.3,
      "variants": [
        "Today's metaphor: key and lamp",
        "Today's image: weaving and mending"
      ]
    }
  }
}
```

---

## 8. `memory` — Memory Recall

Recalls memories relevant to the current conversation from an external memory API. Requires `pip install httpx`.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | Whether to enable |
| `api_url` | `string` | `""` | Memory API endpoint URL |
| `max_results` | `integer` | `3` | Maximum memories to recall per turn |
| `max_length` | `integer` | `120` | Truncate each memory to this length (characters) |

**API protocol**: POST request, body `{"query": "...", "limit": N}`, expects response `{"results": [...]}`.

**Fallback behavior**: httpx unavailable / API unreachable / timeout (3s) / non-200 status → silently skipped.

```json
{
  "memory": {
    "enabled": true,
    "api_url": "http://127.0.0.1:8765/api/recall",
    "max_results": 5
  }
}
```

---

## 9. `project` — Project Kanban

Injects external kanban status on the first turn to help the Agent perceive project context.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | Whether to enable |
| `kanban_path` | `string` | `""` | Absolute path to the kanban directory |
| `label` | `string` | `"📋 项目状态:"` | Title label used when injecting |

**Read logic**: Only called on the first turn. Scans all `*.md` files under `kanban_path`, extracts the first line containing `"优先级:"`, up to 5 items.

```json
{
  "project": {
    "enabled": true,
    "kanban_path": "/home/user/projects/my-app/kanban",
    "label": "📋 Current tasks:"
  }
}
```

---

## 10. `guard` — Safety Guardrails

Pre-call safety checks and post-call audit logging for tool invocations.

### 10.1 Top-Level Fields

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | Whether to enable safety guardrails |
| `rules` | `object` | `{}` | Guardrail rule configuration |
| `audit` | `object` | `{}` | Audit log configuration |

### 10.2 `rules.blocked` — Block List

| Field | Type | Description |
|:---|:---|:---|
| `pattern` | `string` | Regex pattern matching the tool name |
| `reason` | `string` | Explanation for the block |

On match returns: `{"blocked": true, "reason": "..."}`.

### 10.3 `rules.require_confirmation` — Confirmation List

Same structure as `blocked`. On match returns: `{"require_confirmation": true, "reason": "..."}`.

> `blocked` takes priority over `require_confirmation` matching.

### 10.4 `audit` — Audit Log

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | Whether to enable audit logging |
| `log_path` | `string` | `""` | Log file path. Supports `~` expansion. |

```json
{
  "guard": {
    "enabled": true,
    "audit": { "enabled": true, "log_path": "~/.hermes/logs/persona-audit.log" },
    "rules": {
      "blocked": [
        { "pattern": "rm -rf", "reason": "Recursive force deletion is blocked" }
      ],
      "require_confirmation": [
        { "pattern": "sudo", "reason": "sudo operations require user confirmation" },
        { "pattern": "git push.*--force", "reason": "Force push requires user confirmation" }
      ]
    }
  }
}
```

---

## 11. `sources_blacklist` — Source Filtering

Non-conversation sources (cron scheduled tasks, API calls, webhooks) only receive time injection. They do not participate in turn counting, do not trigger dynamic rules, and do not receive persona injection.

Configured within `modules`:

```json
{
  "modules": {
    "sources_blacklist": ["cron", "api_server", "webhook", "msgraph_webhook"]
  }
}
```

---

## 12. `translate` — Injection Narrative Translation

When enabled, the engine automatically translates internal rules (emoji-tagged directives) into natural-language persona self-description. The LLM sees a fluid "self-awareness" narrative rather than a list of instructions.

Configured within `modules`:

```json
{
  "modules": {
    "translate": true
  }
}
```

**Effect**: Each module no longer independently outputs emoji-tagged directive lines. Instead, `_assemble_narrative()` weaves them into a single natural language paragraph. The turn count source for `turn_stage` also switches to the daily cumulative turn count across sessions.

---

## 13. `debug` — Debug Detailed Mode

Appends a full injection overview at the end of each LLM reply to assist with configuration troubleshooting.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | Whether to enable |
| `detail` | `string` | `"compact"` | `"compact"` (summary statistics) or `"detailed"` (per-module breakdown) |

Appended to the LLM reply via the `transform_llm_output` hook — consumes no additional LLM tokens.

> Known limitation: the debug block uses module-level variables for transport and is not thread-safe. No impact under single-session operation.

Configured within `modules`:

```json
{
  "modules": {
    "debug": { "enabled": true, "detail": "detailed" }
  }
}
```

---

## 14. `locales` — Internationalization

Bilingual text support, with locale files enabling extension to additional languages.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `language` | `string` | `"auto"` | `"zh"` / `"en"` / `"auto"` (inferred from `time.format`) |

```json
{
  "language": "zh"
}
```

Language packs are located in the `locales/` directory. To add a new language, simply create the corresponding JSON file.

---

## 15. Rule Injection Order

The final context for each turn is assembled in the following fixed order (not configurable):

```
① time             — Time context (skipped as standalone line in translate mode)
② static_rules     — Static rules (every turn + first-turn-only)
③ dynamic          — Dynamic rules (time_slots -> turn_stage -> keyword)
④a fixed_signals   — Fixed signals (message_length -> reply_gap -> daily_turn_count)
④b expression_vector — Multi-dimensional expression vector
⑤ variance         — Random expression variation
⑥ memory           — Memory recall (if enabled)
⑦ kanban           — Kanban status (if enabled, first turn only)
⑧ translate        — Narrative translation (replaces output from modules above)
⑨ debug            — Debug summary (appended to end of LLM reply)
```

All parts are joined with `\n\n` (double newline).

---

## 16. Configuration Compatibility

| Scenario | Behavior |
|:---|:---|
| Config file does not exist | Falls back to empty config `{}` |
| JSON syntax error | Falls back to empty config `{}` |
| Root key `"hermes-persona"` missing | Falls back to empty config `{}` |
| `modules` missing keys | Backfilled from legacy path or registry defaults |
| Unknown config key | Ignored, no error |
| Required field missing | That function silently disables |

---

## 17. Minimal Configuration

```json
{"hermes-persona": {}}
```

Equivalent to: time injection enabled (`cn_full` format), static rules / dynamic rules / random variation defaults on, expression vector / memory / kanban / translate defaults off.

Injection result:
```
🕐 2026年5月16日 周五 14:30
```
