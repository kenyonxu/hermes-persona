# AGENTS_EN.md — hermes-persona Contributor Guide

## Project Overview

hermes-persona is a personality injection plugin for Hermes Agent. Through the `pre_llm_call` hook, it weaves time awareness, role rules, scene triggers, and random variations into the system prompt before each LLM call. The code is fully generic; the personality is entirely driven by `persona-config.json` configuration.

## Quick Navigation

| File | Purpose |
|------|---------|
| `README.md` | 5-minute quickstart guide |
| `DESIGN.md` | Architecture decision records |
| `plugin.yaml` | Plugin metadata |
| `hermes_persona/` | Plugin source code |
| `tests/` | 131 test cases |
| `docs/` | Configuration reference + role examples + Aglaea walkthrough |

## Development Workflow

### Running Tests

```bash
cd hermes-persona
python -m pytest tests/ -v
```

Covers core modules: static rule injection, dynamic rules (time-of-day / turn-count / keyword), random variance, memory recall, and safety guardrails.

### Branching & PRs

1. Fork the repository
2. Create a feature branch from `main`: `feat/your-feature-name`
3. Make your changes
4. Ensure tests pass: `python -m pytest tests/ -v`
5. Submit a PR

### Code Style

- Python 3.10+
- Follow PEP 8
- All public functions must have docstrings

## Plugin Architecture

```
pre_llm_call hook
  ↓
inject_context()
  ├── get_time()          → Time awareness
  ├── get_static_rules()  → Static rules (injected every turn)
  ├── get_dynamic_rules() → Dynamic rules (time-of-day / turn-count / keyword)
  ├── get_variance()      → Random variation
  ├── recall_memories()   → Memory recall
  └── get_project_state() → Kanban injection
  ↓
System prompt context
```

All modules have independent switches and fail silently — a failure in one module does not affect other modules or normal Agent operation.

## Common Contributions

- **New role examples**: Add a new role in docs/EXAMPLES.md
- **New dynamic rule types**: Implement in `hermes_persona/dynamic_rules.py`
- **Bug fixes**: Include a reproduction test case

## License

MIT
