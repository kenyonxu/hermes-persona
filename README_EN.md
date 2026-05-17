# hermes-persona

> A universal personality context injection engine for Hermes Agent — code-agnostic, config-driven, and ready to use out of the box

## Project Overview

`hermes-persona` is a Hermes Agent plugin that dynamically injects personality context before each LLM call. Through the **pre_llm_call hook**, it weaves time awareness, static rules, dynamic rules (time-slot / turn-based / keyword), random expression variance, memory recall, and project board status into the Agent's system prompt.

**Core Features**:

- **Code-Agnostic**: Contains no character-specific content; all personalities are driven by `persona-config.json`
- **Config-Driven**: All behavior is defined via JSON configuration; switching characters only requires swapping config files
- **Graceful Degradation**: Missing configs, format errors, and unreachable external APIs are all handled silently without disrupting the Agent
- **Composable**: Seven functional modules with independent toggles, mix and match as needed

## Quick Start

### 1. Install

```bash
# One-liner: install from GitHub and enable
hermes plugins install kenyonxu/hermes-persona --enable

# Verify installation
hermes plugins list | grep persona
```

### 2. Minimal Config (5-Minute Setup)

Create `persona-config.json` in your profile directory:

```json
{
  "hermes-persona": {}
}
```

**That's it**. An empty config `{}` enables time injection, so the Agent perceives the current time before every turn:

```
🕐 2026年5月16日 周五 14:30
```

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

> 💡 **Hot Reload**: After this, modifying `persona-config.json` takes effect immediately — no restart needed.

### 5. Advanced Features Overview

| Module | Config Node | Description |
|:---|:---|:---|
| Time Awareness | `time` | Injects current time each turn, supports three formats |
| Static Rules | `context.rules` | Rules injected every turn |
| First-Turn Rules | `context.rules_first_turn_only` | Rules injected only on the first turn |
| Time-Slot Rules | `dynamic.time_slots` | Rules that switch based on time of day (e.g., late-night mode) |
| Turn-Stage Rules | `dynamic.turn_stage` | Rules that switch based on conversation length (e.g., long-conversation summary) |
| Keyword Matching | `dynamic.keywords` | Rules injected when user message matches keywords |
| Random Variance | `variance` | Adds random stylistic variation to responses |
| Memory Recall | `memory` | Recalls relevant memories from an external memory API |
| Project Board | `project` | Injects project board status on the first turn |
| Safety Guardrails | `guard` | Tool-call safety checks + audit logging |

## Documentation Index

| Document | Contents |
|:---|:---|
| [Config Reference](docs/CONFIG_REFERENCE.md) | Complete configuration reference — types, defaults, examples |
| [Multi-Character Examples](docs/EXAMPLES.md) | 3 fully working persona-config.json examples — Black Cat Luna / Code Reviewer / General Assistant |
| [Aglaea Case Study](docs/CASE_STUDY_AGLAEA.md) | A complete tutorial converting Honkai: Star Rail lore into a five-layer personality slot |
| [Plugin Design](docs/hermes-persona-plugin-design.md) | Architecture design document |
| [Design Decisions](DESIGN.md) | DESIGN.md: why the system is designed this way |
| [Dynamic Rule Injection](docs/dynamic-rules-injection-design.md) | Three-dimensional personality adaptation via time / turn count / keywords |

## FAQ

**Q: Where do I put the config file?**
A: Place it in the Hermes profile directory, e.g., `~/.hermes/profiles/default/persona-config.json`. The plugin automatically picks up `ctx.profile_path` via `register(ctx)`.

**Q: Does it apply to all profiles after installation?**
A: It depends on the context where the install command was executed:
- `hermes plugins install ... --enable` (without `-p`) → global, applies to all profiles
- `hermes -p <name> plugins install ... --enable` (with `-p`) → applies only to the specified profile
Check the effective scope with: `cat ~/.hermes/config.yaml` or `cat ~/.hermes/profiles/<name>/config.yaml`, look under `plugins:` → `enabled:` list.

**Q: What is the minimal configuration?**
A: `{"hermes-persona": {}}` — an empty object is enough to enable time awareness with zero config overhead.

**Q: How do I switch character personalities?**
A: Simply replace the contents of `persona-config.json`; no code changes required. See [Multi-Character Examples](docs/EXAMPLES.md).

**Q: Will a config error crash the Agent?**
A: No. All exceptions are caught and silently degraded. Missing config files, JSON syntax errors, and type mismatches will not disrupt normal Agent flow.

**Q: What do I need for memory recall?**
A: A compatible HTTP POST API. After configuring `memory.api_url`, the plugin sends `{"query": "...", "limit": N}` requests. If you don't need memory features, simply keep `memory.enabled: false`.

**Q: How is performance?**
A: A single `inject_context()` call takes < 5 ms (excluding external API calls). Minimal config (time injection only) takes < 1 ms.

**Q: Which Hermes versions are supported?**
A: Any Hermes version that provides `pre_llm_call` / `pre_tool_call` / `post_tool_call` hooks.

## License

MIT License — plugin code and documentation.
