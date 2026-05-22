<h3 align="center">
  <a href="README.md">简体中文</a> · <a href="README_EN.md">English</a>
</h3>
<p align="center">— ✦ —</p>

# hermes-persona

> A universal personality context injection engine for Hermes Agent — code-agnostic, config-driven, and ready to use out of the box

## Project Overview

`hermes-persona` is a Hermes Agent plugin that dynamically injects personality context before each LLM call via the **pre_llm_call hook**. Time awareness, behavioral rules, scenario triggers, expression variance, memory recall, and project board status are woven into the system prompt — all driven by `persona-config.json`. Switching characters requires zero code changes.

**Core Principles**:

- **Config-Driven**: All behavior is defined via JSON; the code itself is fully generic
- **Independent Modules**: Each feature can be toggled on/off independently, mix and match as needed
- **Graceful Degradation**: Missing configs, format errors, and unreachable external APIs are all handled silently without disrupting the Agent

---

## Quick Start

### 1. Install

```bash
# One-liner: install from GitHub and enable
hermes plugins install kenyonxu/hermes-persona --enable

# Verify installation
hermes plugins list | grep persona
```

### 2. Minimal Config (5-Minute Setup)

Create `persona-config.json` in the plugin directory:

```json
{
  "hermes-persona": {}
}
```

**That's it.** An empty config `{}` enables time injection, so the Agent perceives the current time before every turn:

```
2026年5月22日 周五 11:30
```

> Hot Reload: After the initial setup, modifying `persona-config.json` takes effect immediately — no restart needed.

### 3. Add Custom Rules

```json
{
  "hermes-persona": {
    "context": {
      "rules": [
        "You are a friendly, professional AI assistant",
        "Please answer all questions in Chinese",
        "Keep responses concise, under 200 characters"
      ]
    }
  }
}
```

### 4. Verify

After installing and restarting the Hermes gateway (first time only), send a message and the Agent's system prompt will automatically include the rules above.

---

## Configuration Guide

The top-level config is always wrapped in the `"hermes-persona"` key. The following sections cover each functional module.

### 1. Module Master Switches (`modules`)

Each feature module can be toggled independently. Disabled modules are skipped entirely during injection.

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
      "expression_vector": true,
      "fixed_signals": true,
      "memory": false,
      "kanban": true,
      "translate": true,
      "sources_blacklist": ["cron", "api_server", "webhook", "msgraph_webhook"]
    }
  }
}
```

**Field Reference**:

| Module | Type | Description |
|--------|------|-------------|
| `time` | bool | Time awareness injection |
| `static_rules` | bool | Static behavioral rule injection |
| `dynamic.time_slots` | bool | Time-slot rules (late night / morning etc.) |
| `dynamic.turn_stage` | bool | Turn-stage rules based on conversation length |
| `dynamic.keyword` | bool | Keyword-triggered rules |
| `variance` | bool | Random expression variance |
| `expression_vector` | bool | Multi-dimensional expression vector (requires `expression_vector.enabled` as well) |
| `fixed_signals` | bool | Fixed signal detection (message length / reply gap / daily turn count) |
| `memory` | bool | External memory recall (requires `pip install httpx`) |
| `kanban` | bool | Project board status injection (first turn only) |
| `translate` | bool | Injection narrative translation mode (see section 9) |
| `sources_blacklist` | list | Source filtering (see section 10) |

---

### 2. Time Awareness (`time`)

Injects the current date and time on every turn. The Agent can distinguish morning from late night, or mention specific times in greetings.

```json
{
  "time": {
    "enabled": true,
    "format": "cn_full"
  }
}
```

| Parameter | Value | Output Example |
|-----------|-------|----------------|
| `format` | `"cn_full"` | `2026年5月22日 周五 11:30` |

> When `translate` mode is enabled, the time is woven into the personality narrative as natural language rather than injected as a standalone line.

---

### 3. Static Rules (`context`)

User-defined behavioral rules, injected via two channels:

- **`rules`**: Injected on every turn
- **`rules_first_turn_only`**: Injected only on the first turn of a session

```json
{
  "context": {
    "rules": [
      "Answer all questions in Chinese",
      "Keep responses concise, under 200 characters",
      "Maintain a friendly, professional tone"
    ],
    "rules_first_turn_only": [
      "Automatically review recent context at the start of the session"
    ]
  }
}
```

---

### 4. Dynamic Rules (`dynamic`)

Dynamically selects guidance rules based on the current context. Three sub-channels:

#### 4.1 Time-Slot Rules (`time_slots`)

Inject different behavioral guidance based on time of day. Keys are time ranges, values are arrays of rule text.

```json
{
  "dynamic": {
    "time_slots": {
      "06:00-09:00": ["Keep your tone fresh and energetic, feel free to mention last night's rest"],
      "09:00-12:00": ["Stay efficient but warm in your companionship"],
      "22:00-05:00": ["Softer tone, focus on companionship, avoid bringing up work"]
    }
  }
}
```

#### 4.2 Turn-Stage Rules (`turn_stage`)

Automatically switches stages based on cumulative daily conversation turns. Keys are `after_<count>`, triggered when the turn count reaches the threshold.

```json
{
  "dynamic": {
    "turn_stage": {
      "first_turn": ["Session starting, keep tone fresh"],
      "after_100": ["Deep conversation phase, tone can be more natural"],
      "after_300": ["Deep conversation phase: expressions can be more intimate, proactively share thoughts"]
    }
  }
}
```

- `first_turn`: First turn only
- `after_N`: Triggers when turn count >= N, matches the largest threshold reached
- **Non-translate mode**: Turn count = current session turns (`message count / 2`)
- **Translate mode**: Turn count = cumulative daily turns across sessions, resets at day boundary

#### 4.3 Keyword Triggers (`keyword`)

Injects rules when the user message matches specified keywords.

```json
{
  "dynamic": {
    "keyword": [
      {
        "pattern": "code|bug|architecture",
        "rules": ["Switch to technical analysis mode: break down the problem first, then provide the answer"]
      },
      {
        "pattern": "tired|exhausted|sleepy",
        "rules": ["Care mode: softer tone, avoid dense information output"]
      }
    ]
  }
}
```

- `pattern`: Regex pattern or dimension name; when matched, all `rules` entries are injected
- All matching dimensions return simultaneously (all-matches), not limited to a single hit

---

### 5. Multi-Dimensional Expression Vector (`expression_vector`)

Automatically tracks conversation topic distribution, guiding the Agent to naturally adjust its expression style based on the current conversational direction.

```json
{
  "expression_vector": {
    "enabled": true,
    "dimensions": {
      "technical": {
        "label": "Technical Discussion",
        "keywords_path": "keywords/technical.json",
        "score_rules": [1, -0.5, 2, 0.95]
      },
      "casual": {
        "label": "Casual Chat",
        "keywords_path": "keywords/casual.json",
        "score_rules": [1, -1, 1, 0.95]
      }
    },
    "reset": "session",
    "storage_path": "state/expression_vector.json"
  }
}
```

**Dimension Configuration**:

| Field | Description |
|-------|-------------|
| `label` | Display name for the dimension |
| `keywords_path` | Path to the keyword vocabulary file |
| `score_rules` | `[hit_bonus, miss_penalty, weight, decay_factor]` |

- Dimension count and names are fully user-defined
- Keyword vocabularies are standalone JSON files, one per dimension
- Scores decay automatically per session; cross-session strategy is configurable: `session` (reset per session) / `daily` / `none`

---

### 6. Fixed Signal Detection (`fixed_signals`)

Three automatic detection signals based on the message itself rather than config rules.

#### 6.1 Message Length (`message_length`)

Injects a brevity hint when the user message is too short.

```json
{
  "fixed_signals": {
    "message_length": { "enabled": true, "threshold": 50 }
  }
}
```

#### 6.2 Reply Gap (`reply_gap`)

Injects a welcome-back hint when the user returns after a long absence.

```json
{
  "fixed_signals": {
    "reply_gap": { "enabled": true, "threshold_minutes": 30 }
  }
}
```

#### 6.3 Daily Turn Count (`daily_turn_count`)

Accumulates daily conversation turns across sessions, with configurable deep-interaction thresholds.

```json
{
  "fixed_signals": {
    "daily_turn_count": {
      "enabled": true,
      "thresholds": { "morning": 10, "deep_companionship": 50 },
      "storage_path": "state/daily_turn_count.json"
    }
  }
}
```

- Turn count accumulates across sessions daily, resets at day boundary
- Non-conversational sources (see section 10) do not contribute to the count

---

### 7. Random Expression Variance (`variance`)

Triggers variant entries randomly with configurable probability. Typical use: character-specific **body language, speech quirks, metaphorical style, catchphrases**.

```json
{
  "variance": {
    "body_language": {
      "probability": 0.5,
      "variants": [
        "Unconsciously rubs the back of the neck — a nervous habit of the character",
        "Taps fingers twice on the desk, then stops"
      ]
    },
    "catchphrase": {
      "probability": 0.3,
      "variants": [
        "Today's catchphrase: Let's leave it at that~",
        "Today's catchphrase: That makes sense"
      ]
    }
  }
}
```

- `probability`: Trigger probability (0–1)
- `variants`: One randomly selected on each trigger
- **Entries should be self-contained, complete sentences** — the engine only does prefix-stripping pass-through, it does not lock down sentence patterns. Authors can iterate on content without modifying code.

---

### 8. Safety Guardrails (`guard`)

Pre-tool-call safety checks. Supports two rule types:

```json
{
  "guard": {
    "enabled": true,
    "audit": { "enabled": true, "log_path": "~/.hermes/profiles/default/audit.log" },
    "rules": {
      "blocked": [
        { "pattern": "rm -rf", "reason": "Recursive force delete has been blocked" }
      ],
      "require_confirmation": [
        { "pattern": "sudo", "reason": "sudo operations require user confirmation" },
        { "pattern": "git push.*--force", "reason": "Force push requires user confirmation" }
      ]
    }
  }
}
```

- `blocked`: Blocked outright, not sent to the LLM
- `require_confirmation`: Blocked with a prompt for user confirmation
- `audit`: All blocking and confirmation events are written to the audit log

---

### 9. Injection Narrative Translation (`translate`)

When enabled, the engine automatically translates internal rules (emoji-prefixed directives) into natural-language personality self-narrative. The LLM sees fluent "self-awareness" text rather than a checklist of instructions.

```json
{
  "modules": {
    "translate": true
  }
}
```

**Effect Comparison**:

- **Disabled**: The LLM receives scattered directives like `☀️ Morning — keep tone fresh` `🦊 fox ears twitch slightly`
- **Enabled**: The LLM receives a single flowing paragraph — "It is Friday morning, we have talked for 165 turns today..."

Translation template: time + turn count + status + random variance + behavioral rules → assembled into a single personality self-narrative.

> When translate is enabled, individual modules no longer output separate emoji-prefixed directive lines — everything is unified by `_assemble_narrative()` into a single natural-language paragraph. The `turn_stage` turn count source also switches to cumulative daily turns across sessions (read from the on-disk state file) rather than in-session turns.

---

### 10. Source Filtering (`sources_blacklist`)

Non-conversational sources (cron scheduled tasks, API calls, webhooks) only receive time context — they do not participate in turn counting, do not trigger dynamic rules, and do not receive personality injection.

```json
{
  "modules": {
    "sources_blacklist": ["cron", "api_server", "webhook", "msgraph_webhook"]
  }
}
```

- Filtered sources: receive only time context
- Non-filtered sources (discord, telegram, cli, and all other instant messaging platforms): receive full personality injection

---

### 11. Debug Detailed Mode (`debug`)

Don't want to guess what the engine is doing? With debug enabled, a full injection breakdown is appended to the end of each LLM response.

```json
{
  "modules": {
    "debug": { "enabled": true, "detail": "detailed" }
  }
}
```

| Parameter | Value | Description |
|-----------|-------|-------------|
| `enabled` | bool | Whether to enable |
| `detail` | `"basic"` / `"detailed"` | `detailed` shows the full injection breakdown (time slot, turn stage, expression vector scores, fixed signals, variance hits) |

> The debug block is appended to the LLM response via the `transform_llm_output` hook. It costs no extra tokens for "asking the LLM to self-report" and requires no LLM cooperation.
>
> **Known Limitation**: `_PENDING_DEBUG_BLOCK` uses module-level variable passing and is not thread-safe. No impact for single-session usage; debug blocks may interleave under multi-session concurrent scenarios.

---

### 12. Internationalization (`locales`)

Bilingual text support, extensible to more languages via locale files. Built-in support for Chinese and English.

```json
{
  "locales": "en"
}
```

Language packs are located in the `locales/` directory. To add a new language, simply create the corresponding JSON file.

---

### 13. Project Board Injection (`kanban`)

Injects external kanban/project-board status on the first turn, helping the Agent perceive project context.

```json
{
  "modules": {
    "kanban": true
  },
  "project": {
    "enabled": true,
    "kanban_path": "/path/to/your/kanban/directory",
    "label": "📋 Project Status:"
  }
}
```

> Only injected on the first turn; subsequent turns do not re-read.

---

## Full Feature Table

| # | Module | Config Key | Description |
|---|--------|-----------|-------------|
| 1 | Master Switch | `modules` | Independent toggles for all 13 modules |
| 2 | Time Awareness | `time` | Injects current date/time each turn; supports `cn_full` format |
| 3 | Static Rules | `context` | `rules` (every turn) + `rules_first_turn_only` (first turn) |
| 4 | Dynamic Rules | `dynamic` | Time-slot / turn-stage / keyword-triggered rule injection |
| 5 | Expression Vector | `expression_vector` | Multi-dimensional topic tracking with configurable `score_rules` and decay |
| 6 | Fixed Signals | `fixed_signals` | Auto-detection: message length, reply gap, daily turn count |
| 7 | Random Variance | `variance` | Probabilistic body language, catchphrases, speech quirks |
| 8 | Guardrails | `guard` | Tool-call safety: block / require-confirmation rules + audit logging |
| 9 | Translate | `translate` | Converts emoji-prefixed directives into natural-language self-narrative |
| 10 | Source Filter | `sources_blacklist` | Excludes non-conversational sources from personality injection |
| 11 | Debug | `debug` | Appends injection breakdown to LLM output (basic/detailed modes) |
| 12 | i18n | `locales` | Multi-language support via locale JSON files |
| 13 | Kanban | `project` | First-turn project board status injection |

---

## Directory Structure

```text
plugins/hermes-persona/
├── persona-config.json          ← The only config file users need to edit
├── keywords/                    ← Expression vector dimension vocabularies (user-defined)
│   └── *.json
├── locales/                     ← Multi-language templates
│   ├── en.json
│   └── zh.json
├── state/                       ← Auto-generated at runtime (do not version-control)
│   ├── expression_vector.json
│   └── daily_turn_count.json
└── examples/
    └── persona-config.json      ← Full config template
```

---

## Documentation Index

| Document | Contents |
|:---|:---|
| [Config Reference](docs/en/CONFIG_REFERENCE.md) | Complete configuration reference — types, defaults, examples |
| [Multi-Character Examples](docs/en/EXAMPLES.md) | 3 fully working persona-config.json examples — Black Cat Luna / Code Reviewer / General Assistant |
| [Aglaea Case Study](docs/en/CASE_STUDY_AGLAEA.md) | A complete tutorial converting Honkai: Star Rail lore into a five-layer personality slot |
| [Plugin Design](docs/en/hermes-persona-plugin-design.md) | Architecture design document |
| [Design Decisions](DESIGN_EN.md) | Why the system is designed this way |
| [Dynamic Rule Injection](docs/en/dynamic-rules-injection-design.md) | Three-dimensional personality adaptation via time / turn count / keywords |

---

## FAQ

**Q: Where do I put the config file?**
A: Place it in the plugin directory under your profile: `~/.hermes/profiles/<name>/plugins/hermes-persona/persona-config.json`. The plugin resolves the path via `ctx.profile_path` with a three-tier fallback: plugin dir → profile dir → auto-generate empty config.

**Q: Does it apply to all profiles after installation?**
A: It depends on the context where the install command was executed:
- `hermes plugins install ... --enable` (without `-p`) → global, applies to all profiles
- `hermes -p <name> plugins install ... --enable` (with `-p`) → applies only to the specified profile
Check the effective scope with: `cat ~/.hermes/config.yaml` or `cat ~/.hermes/profiles/<name>/config.yaml`, look under `plugins:` → `enabled:` list.

**Q: What is the minimal configuration?**
A: `{"hermes-persona": {}}` — an empty object is enough to enable time awareness with zero config overhead.

**Q: How do I switch character personalities?**
A: Simply replace the contents of `persona-config.json`; no code changes required. See [Multi-Character Examples](docs/en/EXAMPLES.md).

**Q: Will a config error crash the Agent?**
A: No. All exceptions are caught and silently degraded. Missing config files, JSON syntax errors, and type mismatches will not disrupt normal Agent flow.

**Q: What do I need for memory recall?**
A: A compatible HTTP POST API. After configuring `memory.api_url`, the plugin sends `{"query": "...", "limit": N}` requests. If you don't need memory features, simply keep `memory.enabled: false`.

**Q: How is performance?**
A: A single `inject_context()` call takes < 5 ms (excluding external API calls). Minimal config (time injection only) takes < 1 ms.

**Q: Which Hermes versions are supported?**
A: Any Hermes version that provides `pre_llm_call` / `pre_tool_call` / `post_tool_call` hooks.

**Q: What does the expression vector do?**
A: It tracks conversation topic distribution across user-defined dimensions (e.g., technical vs. casual). Each dimension has `score_rules: [hit_bonus, miss_penalty, weight, decay_factor]` — keywords in user messages boost or reduce scores, weighted and decayed over time. The Agent can then adjust its expression style based on the dominant dimension. Scores persist in `state/expression_vector.json` and reset according to the `reset` policy (`session`, `daily`, or `none`).

**Q: How does translate mode change the output?**
A: Without translate, the LLM receives individual emoji-prefixed directives (e.g., `☀️ Morning — keep tone fresh`). With translate enabled, these are assembled into a single natural-language paragraph via `_assemble_narrative()`: "It is Friday morning, we have talked for 165 turns today, your tone should be warm and attentive..." The LLM perceives a coherent "self-awareness" rather than a command checklist.

**Q: What do the debug modes show?**
A: Basic mode (`"basic"`) appends a summary of active modules. Detailed mode (`"detailed"`) shows the full injection breakdown: matched time slot, turn stage, expression vector scores per dimension, triggered fixed signals, which variance entries were selected, and all injected rule text. The debug block is appended to the LLM response via `transform_llm_output` — it costs no extra inference tokens.

**Q: How does source filtering work?**
A: The `sources_blacklist` lists message sources (e.g., `cron`, `api_server`, `webhook`) that should only receive time context. These sources do not trigger dynamic rules, do not accumulate turn counts, and do not receive personality injection. All other sources (discord, telegram, cli, etc.) receive full personality injection as normal. This prevents automated/non-conversational triggers from distorting turn counts or expression vector scores.

---

## License

MIT License — plugin code and documentation.
