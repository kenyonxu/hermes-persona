<h3 align="center">
  <a href="DESIGN.md">简体中文</a> · <a href="DESIGN_EN.md">English</a>
</h3>
<p align="center">— ✦ —</p>

# DESIGN_EN.md — hermes-persona Architecture Decisions

## Core Philosophy

**Code is generic; configuration drives everything.** The plugin contains no role-specific content. All personas are defined through `persona-config.json` — switching roles is as simple as replacing the configuration file.

## Why Plugin Hooks?

The Hermes Agent Plugin Hook mechanism provides three key points:

| Hook | Purpose | Decision |
|------|---------|----------|
| `pre_llm_call` | Injects context before every LLM call | **The core of the persona engine** — ensures calibration on every turn |
| `on_session_start` | New session initialization | Load config + validate format |
| `on_session_end` | Session cleanup | Record audit logs (if enabled) |

The reason for choosing `pre_llm_call` over modifying the system prompt directly:

1. **Hot-reload**: Changes to `persona-config.json` take effect immediately on the next turn, no restart required
2. **Isolation**: Persona injection is separate from Hermes core prompts — no cross-contamination
3. **Safe degradation**: Hook exceptions do not prevent the Agent from continuing to run

## Why JSON Instead of YAML for Configuration?

1. JSON is the default format in the Hermes Agent ecosystem (with the exception of prefill.json and config.yaml)
2. JSON has strict structural constraints, reducing format ambiguity
3. The user base is more familiar with JSON (JavaScript/TypeScript developers are the majority)

## File Layout

All user-editable JSON configuration and runtime state files live under the plugin directory:

```
plugins/hermes-persona/
├── persona-config.json          ← The only config file users need to edit
├── keywords/                    ← Dimension keywords (7 JSON files, user-customizable)
├── locales/                     ← Multi-language templates (en.json / zh.json)
├── state/                       ← Auto-generated at runtime (expression_vector / daily_turn_count)
└── examples/                    ← Templates (new users copy these)
```

**Path Resolution Strategy**: `config.py` provides a public `_resolve_config_path()` function with a three-tier fallback:
1. Plugin directory (new convention, preferred)
2. `_CONFIG_ROOT` (legacy profile root directory, backward-compatible)
3. Caller-side handling (e.g., repo root fallback)

Both `injector.py` and `guard.py` use this function to load config, avoiding duplicate path resolution logic. State files (`expression_vector.json`, `daily_turn_count.json`) are written to `state/` by default; if state files exist at the legacy path, they are auto-read and migrated on the first `save()` call.

## Module Design

| Module | Config Node | Design Rationale |
|--------|-------------|------------------|
| Time Awareness | `time` | Basic context, cost < 1ms |
| Weather | `weather` | Real-time weather via Open-Meteo API with file-based caching, fail-open |
| Static Rules | `context.rules` | Hard constraints applied every turn — role identity, language taboos |
| First-Turn Only | `context.rules_first_turn_only` | Prevents opening lines from repeating every turn |
| Time-Slot Dynamic | `dynamic.time_slots` | The same role should behave differently at different times of day |
| Turn-Stage Dynamic | `dynamic.turn_stage` | Naturally deepen tone over long conversations |
| Keyword Matching | `dynamic.keywords` | Scene-driven, injected on demand — saves tokens |
| Fixed Signals | `fixed_signals` | Auto-detection: message length, reply gap, daily turn count |
| Expression Vector | `expression_vector` | Multi-dimensional topic tracking with score decay |
| Random Variance | `variance` | Breaks mechanical feel; different expressions for the same scene |
| Memory Recall | `memory` | Pluggable external memory API |
| Project Board Injection | `project` | Injects project context on the first turn |
| Safety Guardrails | `guard` | Tool call interception + audit logs |

## Degradation Strategy

```
Missing config      → Silently skip that module
JSON format error   → Catch exception, log it, do not affect the Agent
External API timeout → 3s timeout, mark as unavailable on failure
Module exception    → Independent try/except, no cascading crashes
```

**Core Principle**: The persona engine is an enhancement layer, not a dependency layer. Under no circumstances should the Agent's conversational functionality be interrupted due to engine failure.

## Token Budget

Estimated tokens injected per `inject_context()` call:

| Scenario | Rule Count | Tokens |
|----------|-----------|--------|
| Minimal config (time only) | 1 | ~30 |
| Typical role (static + 1 time slot + 1 keyword) | 5-8 | ~150-250 |
| Full-featured (all modules enabled) | 15+ | ~500-800 |

All dynamic rules use scene-driven triggers, avoiding "burning tokens on every rule every turn." Hard constraints go in prefill (injected every turn); soft tonal adjustments go in persona-config (triggered on demand).
