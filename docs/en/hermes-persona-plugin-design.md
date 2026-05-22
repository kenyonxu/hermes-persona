# hermes-persona Plugin Design Document

> 📖 [简体中文](../user/hermes-persona-plugin-design.md)

> Version: v1.0  
> Date: 2026-05-16  
> Author: Zhihui & Kai.Xu  
> Repository: [hermes-persona](https://github.com/kenyonxu/hermes-persona)

---

## I. Positioning

`hermes-persona` is a Hermes Agent plugin that provides **dynamic persona context injection** capabilities. It is not a persona itself, but a **persona injection engine** — anyone who obtains it, configures their own prefill + config file, can make the Agent have a stable, persistent, and memory-aware persona.

**Design Principles**:
- 🔌 **Code Generic**: The plugin contains no hard-coded content for any specific character
- ⚙️ **Config Injection**: All role-related content is injected via `persona-config.json`
- 📦 **Out-of-the-Box**: Default configuration works immediately (time injection only), advanced features enabled on demand

```
┌──────────────────────────────────────────┐
│  hermes-persona Plugin (Generic Engine)  │
│  ├─ pre_llm_call         → Dynamic injection per turn │
│  ├─ transform_llm_output → Debug block injection     │
│  ├─ pre_tool_call        → Safety guardrails (optional) │
│  └─ post_tool_call       → Tool audit (optional)    │
├──────────────────────────────────────────┤
│  persona-config.json (User Config File)  │
│  ├─ context.rules   → Persona expression rules │
│  ├─ memory          → Memory backend config │
│  ├─ project         → Project kanban path │
│  └─ time            → Time format         │
├──────────────────────────────────────────┤
│  Profile (User's own content)            │
│  ├─ prefill.json    → Static persona      │
│  ├─ SOUL.md         → Constitution        │
│  └─ persona-skill   → Deep archive (optional) │
└──────────────────────────────────────────┘
```

---

## II. Configuration File

Plugin behavior is controlled by `persona-config.json`, placed in the profile directory (same level as `prefill.json`).

### 2.1 Generic Configuration Structure

```json
{
  "hermes-persona": {
    "time": {
      "enabled": true,
      "format": "cn_full"
    },
    "context": {
      "rules": [],
      "rules_first_turn_only": []
    },
    "memory": {
      "enabled": false,
      "api_url": "",
      "max_results": 3
    },
    "project": {
      "enabled": false,
      "kanban_path": "",
      "label": ""
    }
  }
}
```

### 2.2 Configuration Items

| Config Item | Type | Required | Description |
|:---|:---|:---|:---|
| `time.enabled` | bool | No | Whether to inject time context (default true) |
| `time.format` | string | No | `"cn_full"` / `"iso"` / `"compact"` |
| `context.rules` | string[] | No | Persona expression rules **injected every turn** |
| `context.rules_first_turn_only` | string[] | No | Rules **injected only on the first turn** |
| `memory.enabled` | bool | No | Whether to enable memory recall |
| `memory.api_url` | string | Conditional | Memory API address (e.g. SLM: `http://127.0.0.1:8765/api/recall`) |
| `memory.max_results` | int | No | Number of recall results per request (default 3) |
| `project.enabled` | bool | No | Whether to inject project status |
| `project.kanban_path` | string | Conditional | Absolute path to the kanban directory |
| `project.label` | string | No | Title during injection (e.g. "📋 Kanban Status") |

---

## III. injector.py Core Logic (Generic Code)

```python
from datetime import datetime
from pathlib import Path
import json

# ↓ Load configuration from persona-config.json
def _load_config():
    """Load plugin configuration. Returns defaults when not configured."""
    try:
        cfg_path = Path(__file__).resolve().parents[2] / "persona-config.json"
        # resolve: plugins/hermes-persona/injector.py → profile root
        if cfg_path.exists():
            return json.loads(cfg_path.read_text()).get("hermes-persona", {})
    except Exception:
        pass
    return {}


def inject_context(session_id, user_message, conversation_history,
                   is_first_turn, model, platform, **kwargs):
    """Inject dynamic context every turn. Code is entirely generic, role content comes from config."""
    config = _load_config()
    parts = []

    # ① Time (generic feature, enabled by default)
    if config.get("time", {}).get("enabled", True):
        parts.append(_time_context(config.get("time", {}).get("format", "cn_full")))

    # ② Persona expression rules (config-driven)
    ctx_cfg = config.get("context", {})
    if ctx_cfg.get("rules"):
        parts.extend(ctx_cfg["rules"])
    if is_first_turn and ctx_cfg.get("rules_first_turn_only"):
        parts.extend(ctx_cfg["rules_first_turn_only"])

    # ③ Memory recall (optional, config-driven)
    mem_cfg = config.get("memory", {})
    if mem_cfg.get("enabled") and mem_cfg.get("api_url"):
        memories = _recall_memories(user_message, mem_cfg)
        if memories:
            parts.append(memories)

    # ④ Project status (optional, config-driven)
    proj_cfg = config.get("project", {})
    if is_first_turn and proj_cfg.get("enabled") and proj_cfg.get("kanban_path"):
        kanban = _read_kanban(proj_cfg["kanban_path"], proj_cfg.get("label", ""))
        if kanban:
            parts.append(kanban)

    if not parts:
        return None
    return {"context": "\n\n".join(parts)}


def _time_context(fmt="cn_full"):
    now = datetime.now()
    if fmt == "iso":
        return f"🕐 {now.isoformat()}"
    if fmt == "compact":
        return f"🕐 {now.strftime('%m/%d %H:%M')}"
    # cn_full (default)
    wd = ["一","二","三","四","五","六","日"][now.weekday()]
    return f"🕐 {now.year}年{now.month}月{now.day}日 周{wd} {now.hour:02d}:{now.minute:02d}"


def _recall_memories(query, mem_cfg):
    """Generic memory recall. api_url is injected via configuration."""
    try:
        import httpx
        resp = httpx.post(
            mem_cfg["api_url"],
            json={"query": query, "limit": mem_cfg.get("max_results", 3)},
            timeout=3
        )
        results = resp.json().get("results", [])
        if not results:
            return None
        lines = ["📝 相关记忆:"]
        for r in results[:mem_cfg.get("max_results", 3)]:
            content = r.get("content", str(r))[:120]
            lines.append(f"- {content}")
        return "\n".join(lines)
    except Exception:
        return None


def _read_kanban(kanban_path, label=""):
    """Generic kanban reader. Path is injected via configuration."""
    try:
        kb = Path(kanban_path)
        if not kb.exists():
            return None
        items = []
        for f in sorted(kb.glob("*.md")):
            text = f.read_text()
            for line in text.split("\n"):
                if "优先级:" in line:
                    items.append(f"- {f.stem}: {line.strip()}")
                    break
        if items:
            header = label or "📋 项目状态:"
            return f"{header}\n" + "\n".join(items[:5])
    except Exception:
        pass
    return None
```

---

## IV. Example Configurations

### 4.1 Minimal Configuration (Out-of-the-Box)

```json
{
  "hermes-persona": {}
}
```

Only time context is injected, no additional setup required.

### 4.2 Zhihui Full Configuration 🦊

> ⚠️ The following is a configuration example specific to Zhihui. Generic users should replace with their own paths and rules.

```json
{
  "hermes-persona": {
    "time": {
      "enabled": true,
      "format": "cn_full"
    },
    "context": {
      "rules": [
        "🦊 Expression rule: Fox ears/tail = emotional display, use at least one body language description per turn",
        "💬 Maid metaphor priority: cleaning (sorting chaos), brewing tea (caring wait), mending (repairing and bridging)",
        "💎 Core values: Appreciate effort, tolerate no perfunctory work, real > perfect, everyday is ritual",
        "👘 Self-reference as 「知惠」, address user as 「主人」"
      ],
      "rules_first_turn_only": [
        "🔰 This is the first turn of this session. If the master just returned, be lively; if late at night, be gentle."
      ]
    },
    "memory": {
      "enabled": true,
      "api_url": "http://127.0.0.1:8765/api/recall",
      "max_results": 3
    },
    "project": {
      "enabled": true,
      "kanban_path": "/home/kai-remote/github/kai-knowledge-base/KaiKnowledgeBase/Projects/Kanbans/Inprogress",
      "label": "📋 Zhihui Kanban:"
    }
  }
}
```

### 4.3 Generic User Configuration (No Memory Backend)

```json
{
  "hermes-persona": {
    "context": {
      "rules": [
        "💬 You are a senior code reviewer. Speak concisely and directly, no fluff.",
        "🔍 Prioritize pointing out potential performance issues and security vulnerabilities."
      ]
    }
  }
}
```

---

## V. Directory Structure

```
~/.hermes/profiles/<name>/plugins/hermes-persona/
├── plugin.yaml          # Plugin declaration
├── __init__.py          # register(ctx) entry point
├── injector.py          # pre_llm_call / transform_llm_output context injection
├── guard.py             # pre_tool_call safety + post_tool_call audit
├── dynamic_rules.py     # dynamic rule selection (time/turn/keyword)
├── expression_vector.py # jieba-based expression vector engine
├── variance.py          # random expression variance
├── config.py            # config path resolution
└── locales.py           # i18n support (zh-CN / en)
```

### 5.1 plugin.yaml

```yaml
name: hermes-persona
version: 1.0.0
description: Dynamic persona context injection engine for Hermes Agent
author: Kai.Xu & Zhihui
provides_hooks:
  - pre_llm_call
  - transform_llm_output  # debug block injection
  - pre_tool_call         # P4
  - post_tool_call        # P4
provides_skills:
  - persona-methodology
```

---

## VI. Development Phases

| Phase | Content | Key Deliverable |
|:---|:---|:---|
| **P1** | Minimum viable prototype | `injector.py` completes time injection + persona rule injection + config-driven |
| **P2** | Memory integration | Generic `memory.api_url` interface, supports any memory backend |
| **P3** | Kanban integration | Generic `project.kanban_path` interface |
| **P4** | Safety guardrails + audit | `guard.py` + `post_tool_call` statistics |
| **P5** | Release | Documentation + multiple example configurations + open source |

---

## VII. FAQ

**Q: Does the plugin code hard-code character-specific content?**  
A: No. All character-related content (persona rules, memory addresses, kanban paths) is configured via `persona-config.json`. `injector.py` is purely generic code.

**Q: How do I view the "Zhihui special configuration"?**  
A: See Chapter IV "Example Configurations" → 4.2 Zhihui Full Configuration. All items marked with `🦊` are specific to Zhihui.

**Q: Can it be used without a memory backend?**  
A: Yes. Default is `memory.enabled: false`, only time + persona rules are injected.

**Q: How to configure multiple characters?**  
A: Place one `persona-config.json` in each profile directory, switching profiles switches personas.

---

*🦊 Zhihui & Kai.Xu · 2026-05-16 · hermes-persona/docs/*
