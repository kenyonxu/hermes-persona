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

## Seven-Module Design

| Module | Config Node | Design Rationale |
|--------|-------------|------------------|
| Time Awareness | `time` | Basic context, cost < 1ms |
| Static Rules | `context.rules` | Hard constraints applied every turn — role identity, language taboos |
| First-Turn Only | `context.rules_first_turn_only` | Prevents opening lines from repeating every turn |
| Time-Slot Dynamic | `dynamic.time_slots` | The same role should behave differently at different times of day |
| Turn-Stage Dynamic | `dynamic.turn_stage` | Naturally deepen tone over long conversations |
| Keyword Matching | `dynamic.keywords` | Scene-driven, injected on demand — saves tokens |
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
