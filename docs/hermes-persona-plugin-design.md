# hermes-persona Plugin 设计文档

> 版本：v0.2 草案  
> 日期：2026-05-16  
> 作者：知惠（Zhihui）& Kai.Xu  
> 仓库：[hermes-agent-guide](https://github.com/kenyonxu/hermes-agent-guide)

---

## 一、定位

`hermes-persona` 是一个 Hermes Agent 插件，为 Agent 提供**动态人格上下文注入**能力。它不是一个人格，而是一个**人格注入引擎**——任何人拿到它，配置自己的 prefill + 配置文件，就能让 Agent 拥有稳定、持久、有记忆的人格。

**设计原则**：
- 🔌 **代码通用**：插件不包含任何特定角色的硬编码
- ⚙️ **配置注入**：所有角色相关内容通过 `persona-config.json` 配置
- 📦 **开箱即用**：默认配置即可工作（仅时间注入），高级功能按需开启

```
┌──────────────────────────────────────────┐
│  hermes-persona Plugin（通用引擎）        │
│  ├─ pre_llm_call  → 每回合动态注入         │
│  ├─ pre_tool_call → 安全护栏（可选）       │
│  └─ post_tool_call → 工具审计（可选）       │
├──────────────────────────────────────────┤
│  persona-config.json（用户配置文件）        │
│  ├─ context.rules   → 人格表达规则         │
│  ├─ memory          → 记忆后端配置         │
│  ├─ project         → 项目看板路径         │
│  └─ time            → 时间格式            │
├──────────────────────────────────────────┤
│  Profile（用户自己的内容）                  │
│  ├─ prefill.json    → 静态人格             │
│  ├─ SOUL.md         → 宪法                │
│  └─ persona-skill   → 深度档案（可选）      │
└──────────────────────────────────────────┘
```

---

## 二、配置文件

插件行为由 `persona-config.json` 控制，放在 profile 目录下（与 `prefill.json` 同级）。

### 2.1 通用配置结构

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

### 2.2 配置项说明

| 配置项 | 类型 | 必须 | 说明 |
|:---|:---|:---|:---|
| `time.enabled` | bool | 否 | 是否注入时间上下文（默认 true） |
| `time.format` | string | 否 | `"cn_full"` / `"iso"` / `"compact"` |
| `context.rules` | string[] | 否 | **每回合注入**的人格表达规则 |
| `context.rules_first_turn_only` | string[] | 否 | **仅首轮注入**的规则 |
| `memory.enabled` | bool | 否 | 是否启用记忆召回 |
| `memory.api_url` | string | 条件 | 记忆 API 地址（如 SLM: `http://127.0.0.1:8765/api/recall`） |
| `memory.max_results` | int | 否 | 每次召回条数（默认 3） |
| `project.enabled` | bool | 否 | 是否注入项目状态 |
| `project.kanban_path` | string | 条件 | 看板目录的绝对路径 |
| `project.label` | string | 否 | 注入时的标题（如 "📋 看板状态"） |

---

## 三、injector.py 核心逻辑（通用代码）

```python
from datetime import datetime
from pathlib import Path
import json

# ↓ 从 persona-config.json 加载配置
def _load_config():
    """加载插件配置。未配置时返回默认值。"""
    try:
        cfg_path = Path(__file__).resolve().parents[3] / "persona-config.json"
        # resolve: plugins/00-hermes-persona/injector.py → profile root
        if cfg_path.exists():
            return json.loads(cfg_path.read_text()).get("hermes-persona", {})
    except Exception:
        pass
    return {}


def inject_context(session_id, user_message, conversation_history,
                   is_first_turn, model, platform, **kwargs):
    """每回合注入动态上下文。代码完全通用，角色内容来自配置。"""
    config = _load_config()
    parts = []

    # ① 时间（通用功能，默认开启）
    if config.get("time", {}).get("enabled", True):
        parts.append(_time_context(config.get("time", {}).get("format", "cn_full")))

    # ② 人格表达规则（配置驱动）
    ctx_cfg = config.get("context", {})
    if ctx_cfg.get("rules"):
        parts.extend(ctx_cfg["rules"])
    if is_first_turn and ctx_cfg.get("rules_first_turn_only"):
        parts.extend(ctx_cfg["rules_first_turn_only"])

    # ③ 记忆召回（可选，配置驱动）
    mem_cfg = config.get("memory", {})
    if mem_cfg.get("enabled") and mem_cfg.get("api_url"):
        memories = _recall_memories(user_message, mem_cfg)
        if memories:
            parts.append(memories)

    # ④ 项目状态（可选，配置驱动）
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
    """通用记忆召回。api_url 由配置注入。"""
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
    """通用看板读取。路径由配置注入。"""
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

## 四、示例配置

### 4.1 最小配置（开箱即用）

```json
{
  "hermes-persona": {}
}
```

仅注入时间上下文，无需任何额外设置。

### 4.2 知惠完整配置 🦊

> ⚠️ 以下为知惠特有的配置示例。通用用户请替换为自己的路径和规则。

```json
{
  "hermes-persona": {
    "time": {
      "enabled": true,
      "format": "cn_full"
    },
    "context": {
      "rules": [
        "🦊 表达规则：狐耳/尾巴=情绪外显，每回合至少用一个身体语言描述",
        "💬 女仆比喻优先：打扫（梳理混乱）、泡茶（关怀等待）、缝补（修复弥合）",
        "💎 核心价值观：赞赏投入不容忍敷衍、真实>完美、日常即仪式",
        "👘 自称「知惠」，称呼用户「主人」"
      ],
      "rules_first_turn_only": [
        "🔰 这是本次会话的第一轮。如果主人刚回来，语气活跃；如果深夜，语气温柔。"
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
      "label": "📋 知惠看板:"
    }
  }
}
```

### 4.3 通用用户配置（无记忆后端）

```json
{
  "hermes-persona": {
    "context": {
      "rules": [
        "💬 你是一位资深的代码审查员。说话简洁直接，不废话。",
        "🔍 优先指出潜在的性能问题和安全漏洞。"
      ]
    }
  }
}
```

---

## 五、目录结构

```
~/.hermes/plugins/00-hermes-persona/
├── plugin.yaml          # 插件声明
├── __init__.py          # register(ctx) 入口
├── injector.py          # pre_llm_call 上下文注入引擎（通用代码）
├── guard.py             # pre_tool_call 安全护栏（可选）
└── skill.md             # 捆绑技能：使用文档
```

### 5.1 plugin.yaml

```yaml
name: hermes-persona
version: 0.1.0
description: Dynamic persona context injection engine for Hermes Agent
author: Kai.Xu & Zhihui
provides_hooks:
  - pre_llm_call
  - pre_tool_call       # 可选
  - post_tool_call      # 可选
provides_skills:
  - persona-methodology
```

---

## 六、开发阶段

| Phase | 内容 | 关键产出 |
|:---|:---|:---|
| **P1** | 最小可用原型 | `injector.py` 完成时间注入 + 人格规则注入 + 配置驱动 |
| **P2** | 记忆集成 | 通用 `memory.api_url` 接口，支持任意记忆后端 |
| **P3** | 看板集成 | 通用 `project.kanban_path` 接口 |
| **P4** | 安全护栏 + 审计 | `guard.py` + `post_tool_call` 统计 |
| **P5** | 发布 | 文档 + 多示例配置 + 开源 |

---

## 七、FAQ

**Q: 插件代码硬编码了角色特定内容吗？**  
A: 不。所有角色相关内容（人格规则、记忆地址、看板路径）都通过 `persona-config.json` 配置。`injector.py` 是纯通用代码。

**Q: 如何查看「知惠特殊配置」？**  
A: 见第四章「示例配置」→ 4.2 知惠完整配置。所有 `🦊` 标注的均为知惠特有。

**Q: 不使用记忆后端能用吗？**  
A: 能。默认 `memory.enabled: false`，仅注入时间 + 人格规则。

**Q: 多个角色如何配置？**  
A: 每个 profile 目录下放一份 `persona-config.json`，切换 profile 即切换人格。

---

*🦊 知惠 & Kai.Xu · 2026-05-16 · hermes-agent-guide/docs/*
