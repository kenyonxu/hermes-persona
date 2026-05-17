# hermes-persona Configuration Reference

> Complete reference for all `persona-config.json` fields — types, defaults, descriptions, and examples

---

## Configuration Structure Overview

```json
{
  "hermes-persona": {
    "time": { ... },
    "context": {
      "rules": [ ... ],
      "rules_first_turn_only": [ ... ],
      "dynamic": {
        "time_slots": { ... },
        "turn_stage": { ... },
        "keywords": { ... }
      }
    },
    "variance": { ... },
    "memory": { ... },
    "project": { ... },
    "guard": { ... }
  }
}
```

All configuration resides under the `"hermes-persona"` key. An empty config `{}` works out of the box.

---

## 1. `time` — Time Injection

Controls whether and how current time information is injected before each turn.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `true` | Whether to inject time context. When disabled, no time is shown. |
| `format` | `string` | `"cn_full"` | Time format. See available values below. |

### `format` Values

| Value | Example Output | Description |
|:---|:---|:---|
| `"cn_full"` | `🕐 2026年5月16日 周五 14:30` | Full Chinese format (default) |
| `"iso"` | `🕐 2026-05-16T14:30:00` | ISO 8601 format |
| `"compact"` | `🕐 05/16 14:30` | Compact numeric format |

> Unknown format values automatically fall back to `"cn_full"`.

### Examples

```json
{
  "hermes-persona": {
    "time": {
      "enabled": true,
      "format": "cn_full"
    }
  }
}
```

Disable time injection:

```json
{
  "hermes-persona": {
    "time": {
      "enabled": false
    }
  }
}
```

---

## 2. `context` — Context Rules

Controls persona rules injected each turn, with both static and dynamic sub-dimensions.

### 2.1 `context.rules` — Static Rules

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `rules` | `string[]` | `[]` | Static persona rules injected every turn. Always appended to the end of context. |

### 2.2 `context.rules_first_turn_only` — First-Turn-Only Rules

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `rules_first_turn_only` | `string[]` | `[]` | Rules injected only on the first turn (`is_first_turn=true`). Useful for opening greetings and one-time prompts. |

### 2.3 `context.dynamic` — Dynamic Rules

Rules automatically selected based on runtime conditions (time, turn count, keywords).

#### 2.3.1 `time_slots` — Time Slot Rules

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `time_slots` | `object` | `{}` | Time slot rule mapping. Keys are time ranges in `"HH:MM-HH:MM"` format; values are lists of rules to inject for that slot. Supports overnight ranges. |

**Matching logic**: A slot matches when the current time falls within `[start, end)`. For overnight ranges (e.g. `"22:00-05:00"`), the logic is `now >= start OR now < end`.

**Injection format**: `🕐 [time range] rule content`

**Example**:

```json
{
  "time_slots": {
    "22:00-05:00": [
      "Late night — respond more gently and quietly",
      "Don't forget to remind the user to get some rest"
    ],
    "09:00-17:00": [
      "Working hours — keep responses professional and efficient"
    ]
  }
}
```

If current time is `02:30`, the following is injected:
```
🕐 [22:00-05:00] Late night — respond more gently and quietly
🕐 [22:00-05:00] Don't forget to remind the user to get some rest
```

#### 2.3.2 `turn_stage` — Turn Count Rules

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `turn_stage` | `object` | `{}` | Turn count rule mapping. Supports two key types: `"first_turn"` and `"after_N"`. |

| Key | Match Condition | Description |
|:---|:---|:---|
| `"first_turn"` | `is_first_turn=true` | Injected on the first turn of a session |
| `"after_N"` | `turn_count >= N` | Injected from turn N onward (N is an integer, e.g. `"after_10"`) |

**Matching logic**:
- `first_turn` is injected on the first turn
- `after_N` rules are matched from highest threshold to lowest; the first rule satisfying `turn_count >= N` is used

> `turn_count = len(conversation_history) // 2`, i.e. the number of back-and-forth exchanges between user and Agent.

**Example**:

```json
{
  "turn_stage": {
    "first_turn": ["First interaction — establish a friendly tone"],
    "after_10": ["Conversation has been going for a while — maintain context continuity"],
    "after_30": ["This is a long conversation — summarize and confirm understanding when appropriate"]
  }
}
```

- First turn: injects `"first_turn"` rules
- Turn 15: injects `"after_10"` rules (>=10 but <30)
- Turn 35: injects `"after_30"` rules (>=30 takes priority over >=10)

#### 2.3.3 `keywords` — Keyword Rules

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `keywords` | `object` | `{}` | Keyword rule mapping. Keys are regex patterns; values are rules injected on match. Patterns are evaluated in config order; the first match wins. |

**Injection format**: `💬 [regex pattern] rule content`

**Example**:

```json
{
  "keywords": {
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

User message "系统坏了怎么办" → matches the first pattern → injects both rules.

---

## 3. `variance` — Random Expression Variation

Adds random expression variations each turn to break mechanical monotony.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `variance` | `object` | `{}` | Random variation dimension mapping. Keys are dimension names; values are objects containing `probability` and `variants`. |

### Dimension Fields

| Field | Type | Required | Description |
|:---|:---|:---|:---|
| `probability` | `number` | Yes | Per-turn probability of this dimension appearing, range `0.0` ~ `1.0` |
| `variants` | `string[]` | Yes | List of expression variants. On hit, one is chosen at random. |

**Random mechanism** (two-layer):
1. **Appearance chance**: `random.random() < probability` decides whether this dimension is used this turn
2. **Variant selection**: `random.choice` picks one item from `variants`

### Example

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
        "Today's image: weaving and mending",
        "Today's scene: light rain on the windowsill"
      ]
    }
  }
}
```

On average, 1–2 random variants are injected per turn.

---

## 4. `memory` — Memory Recall

Recalls memories relevant to the current conversation from an external memory API.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | Whether to enable memory recall. |
| `api_url` | `string` | `""` | Memory API endpoint URL. Required when `enabled=true`. |
| `max_results` | `integer` | `3` | Maximum number of memories to recall per turn, range 1~20. |

**API Protocol**:

The plugin sends a POST request to `api_url` with the user message as the query:

```json
// Request
{"query": "user message text", "limit": 3}

// Expected Response
{"results": ["memory snippet 1", "memory snippet 2", ...]}
```

**Injection format**:
```
📝 Related memories:
- memory snippet 1
- memory snippet 2
```

**Fallback behavior**:
- `httpx` unavailable → silently skip
- API unreachable or timeout (3s) → silently skip
- API returns non-200 status → silently skip
- Each memory truncated to 120 characters

### Example

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

## 5. `project` — Project Kanban

Injects project kanban status on the first turn of a conversation.

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | Whether to inject project kanban status. |
| `kanban_path` | `string` | `""` | Absolute path to the kanban directory. Required when `enabled=true`. |
| `label` | `string` | `"📋 项目状态:"` | Title label used when injecting. |

**Read logic**:
1. Only called when `is_first_turn=true`
2. Scans all `*.md` files under `kanban_path`
3. Reads each file, extracts the first line containing `"优先级:"`
4. Formats as `"- {filename}: {priority line}"`, up to 5 items

**Fallback behavior**:
- Directory does not exist → silently skip
- Directory empty / no `.md` files → silently skip
- File read failure → skip that file, continue processing others

### Example

```json
{
  "project": {
    "enabled": true,
    "kanban_path": "/home/user/projects/my-app/kanban",
    "label": "📋 Current tasks:"
  }
}
```

First-turn injection result:
```
📋 Current tasks:
- add-auth: 优先级: P0 🔴
- fix-login: 优先级: P1 🟡
- refactor-db: 优先级: P2 🟢
```

---

## 6. `guard` — Safety Guardrails

Pre-call safety checks and post-call audit logging for tool invocations.

### 6.1 Top-Level Fields

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | Whether to enable safety guardrails. When disabled, all tool calls pass through directly. |
| `rules` | `object` | `{}` | Guardrail rule configuration. |
| `audit` | `object` | `{}` | Audit log configuration. |

### 6.2 `rules` — Guardrail Rules

#### `rules.blocked` — Block List

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `blocked` | `array` | `[]` | List of block rules. Matched tool calls are blocked outright. |

Each rule contains:

| Field | Type | Description |
|:---|:---|:---|
| `pattern` | `string` | Regex pattern matching the tool name |
| `reason` | `string` | Explanation for the block |

On match, returns: `{"blocked": true, "reason": "..."}`

#### `rules.require_confirmation` — Confirmation List

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `require_confirmation` | `array` | `[]` | List of confirmation rules. Matched tool calls trigger a confirmation prompt but are not blocked. |

Each rule has the same structure as `blocked`. On match, returns: `{"require_confirmation": true, "reason": "..."}`

> **Matching priority**: `blocked` rules take precedence over `require_confirmation` rules. The block list is checked first; only if no match is found does the confirmation list get evaluated.

### 6.3 `audit` — Audit Log

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | Whether to enable audit logging. |
| `log_path` | `string` | `""` | Log file path. Supports `~` expansion. |

**Log format**:
```
[ISO timestamp] tool_name | args: argument summary | result: result summary
```

Arguments and results are truncated to 200 characters. Logs are written in append mode; directories are created automatically if they don't exist.

### Example

```json
{
  "guard": {
    "enabled": true,
    "rules": {
      "blocked": [
        {"pattern": "rm\\s", "reason": "File deletion blocked"},
        {"pattern": "DROP\\s", "reason": "Database deletion blocked"},
        {"pattern": "git\\s+push\\s+.*--force", "reason": "Force push prohibited"}
      ],
      "require_confirmation": [
        {"pattern": "git\\s+push", "reason": "Code push requires confirmation"},
        {"pattern": "Write", "reason": "File write requires confirmation"}
      ]
    },
    "audit": {
      "enabled": true,
      "log_path": "~/.hermes/logs/persona-audit.log"
    }
  }
}
```

---

## 7. Rule Injection Order

The final context for each turn is assembled in the following fixed order (not configurable):

```
final context =
  time_context()                          # 1. Time injection
  + context.rules                         # 2. Static rules (every turn)
  + (if first_turn) rules_first_turn_only # 3. First-turn-only rules
  + dynamic.time_slots[current slot]      # 4. Time-slot dynamic rules
  + dynamic.turn_stage[current turn]      # 5. Turn-count dynamic rules
  + dynamic.keywords[matched pattern]     # 6. Keyword dynamic rules
  + variance[randomly selected dimension] # 7. Random expression variation
  + recall_memories()                     # 8. Memory recall (if enabled)
  + (if first_turn) read_kanban()         # 9. Kanban status (if enabled, first turn only)
```

All parts are joined with `\n\n` (double newline).

---

## 8. Configuration Compatibility

| Scenario | Behavior |
|:---|:---|
| Config file does not exist | Falls back to empty config `{}` |
| JSON syntax error | Falls back to empty config `{}` |
| Root key `"hermes-persona"` missing | Falls back to empty config `{}` |
| Field type mismatch | Uses default value (e.g. `"yes"` is treated as `true`) |
| Required field missing | That module is silently disabled (e.g. missing `memory.api_url` → memory disabled) |
| Unknown config key | Ignored, no error |
| Config version newer than plugin | New fields are ignored by older plugin versions |

---

## 9. Minimal Configuration

```json
{"hermes-persona": {}}
```

Equivalent to: time injection enabled (`cn_full` format), no static rules, no dynamic rules, no random variation, no memory recall, no kanban injection, no safety guardrails.

Injection result:
```
🕐 2026年5月16日 周五 14:30
```

---

## 10. Complete Configuration Skeleton

```json
{
  "hermes-persona": {
    "time": {
      "enabled": true,
      "format": "cn_full"
    },
    "context": {
      "rules": [],
      "rules_first_turn_only": [],
      "dynamic": {
        "time_slots": {},
        "turn_stage": {},
        "keywords": {}
      }
    },
    "variance": {},
    "memory": {
      "enabled": false,
      "api_url": "",
      "max_results": 3
    },
    "project": {
      "enabled": false,
      "kanban_path": "",
      "label": ""
    },
    "guard": {
      "enabled": false,
      "rules": {
        "blocked": [],
        "require_confirmation": []
      },
      "audit": {
        "enabled": false,
        "log_path": ""
      }
    }
  }
}
```
