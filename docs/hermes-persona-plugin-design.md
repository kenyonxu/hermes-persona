# hermes-persona Plugin 初步设计

> 版本：v0.1 草案  
> 日期：2026-05-16  
> 作者：知惠（Zhihui）& Kai.Xu  
> 仓库：[hermes-agent-guide](https://github.com/kenyonxu/hermes-agent-guide)

---

## 一、定位

`hermes-persona` 是一个 Hermes Agent 插件，为 Agent 提供**动态人格上下文注入**能力。它不是一个人格，而是一个**人格注入引擎**——任何人拿到它，配置自己的 prefill + Lore，就能让 Agent 拥有稳定、持久、有记忆的人格。

```
┌─────────────────────────────────────────┐
│  hermes-persona Plugin（通用引擎）       │
│  ├─ pre_llm_call  → 每回合注入上下文     │
│  ├─ pre_tool_call → 安全护栏             │
│  └─ post_tool_call → 工具审计（可选）     │
├─────────────────────────────────────────┤
│  Profile（用户自己的内容）                │
│  ├─ prefill.json  → 「我是谁」静态人格    │
│  ├─ SOUL.md       → 宪法                 │
│  └─ persona-skill → 深度 Lore 档案       │
└─────────────────────────────────────────┘
```

**对标概念**：SillyTavern 的 Lorebook / World Info ——但 Hermes 原生，Hook 级注入。

---

## 二、核心机制：pre_llm_call 上下文注入

### 2.1 数据流

```
每回合，用户消息到达
  │
  ├── pre_llm_call 触发
  │   ├─ ① 获取当前时间（datetime.now()，零延迟）
  │   ├─ ② 召回 SLM 相关记忆（可选，按需）
  │   ├─ ③ 读取配置的 Project 看板（可选）
  │   └─ ④ 拼接上下文 JSON
  │
  ├── 上下文被自动 prepend 到用户消息
  │
  └── LLM 收到完整消息
```

### 2.2 注入格式

```json
{
  "context": "🕐 2026年5月16日 周六 15:30\n\n📝 SLM 回忆:\n- 主人昨天修复了 22 个 SLM commit\n- P0A: ACE Music Studio 进入发布管线\n\n📋 看板状态:\n- ACE: Electron Phase 1\n- Clef: 维护期"
}
```

### 2.3 多插件协作

多个插件注册同一个 `pre_llm_call` 时，Hermes 自动**按目录名字母顺序**拼接各插件的输出（双换行分隔）。因此插件目录命名为 `00-hermes-persona` 以确保人格上下文最先注入。

---

## 三、目录结构

```
~/.hermes/plugins/00-hermes-persona/
├── plugin.yaml          # 插件声明
├── __init__.py          # register(ctx) 入口
├── injector.py          # pre_llm_call 上下文注入引擎
├── guard.py             # pre_tool_call 安全护栏（可选）
├── config.py            # 插件配置读取
└── skill.md             # 捆绑技能：使用文档 + 人格化方法论
```

### 3.1 plugin.yaml

```yaml
name: hermes-persona
version: 0.1.0
description: Dynamic persona context injection engine for Hermes Agent
author: Kai.Xu & Zhihui
provides_hooks:
  - pre_llm_call
  - pre_tool_call       # 可选：安全护栏
  - post_tool_call      # 可选：工具审计
provides_skills:
  - persona-methodology  # 捆绑技能：人格化方法论
```

### 3.2 __init__.py

```python
from .injector import inject_context
from .guard import safety_guard

def register(ctx):
    ctx.register_hook("pre_llm_call", inject_context)
    # 可选
    # ctx.register_hook("pre_tool_call", safety_guard)
```

---

## 四、injector.py 核心逻辑

```python
from datetime import datetime
import json

def inject_context(session_id, user_message, conversation_history,
                   is_first_turn, model, platform, **kwargs):
    """每回合注入动态上下文。返回 {"context": "..."} 或 None。"""
    parts = []

    # ① 时间上下文（始终注入，零成本）
    parts.append(_time_context())

    # ② SLM 记忆召回（可选，按需启用）
    memories = _recall_memories(user_message)
    if memories:
        parts.append(memories)

    # ③ 项目看板（仅首轮或 /reset 后）
    if is_first_turn:
        kanban = _read_kanban()
        if kanban:
            parts.append(kanban)

    # ④ 人格提示（仅首轮）
    if is_first_turn:
        parts.append("🦊 以知惠的身份回应——温柔、细腻、灵狐娘女仆长。")

    if not parts:
        return None
    return {"context": "\n\n".join(parts)}


def _time_context():
    now = datetime.now()
    wd = ["一", "二", "三", "四", "五", "六", "日"][now.weekday()]
    return f"🕐 {now.year}年{now.month}月{now.day}日 周{wd} {now.hour:02d}:{now.minute:02d}"


def _recall_memories(query):
    """调用 SLM API 召回相关记忆。失败时静默返回 None。"""
    try:
        import httpx
        resp = httpx.post("http://127.0.0.1:8765/api/recall",
                          json={"query": query, "limit": 3},
                          timeout=3)
        results = resp.json().get("results", [])
        if not results:
            return None
        lines = ["📝 SLM 回忆:"]
        for r in results[:3]:
            lines.append(f"- {r['content'][:120]}")
        return "\n".join(lines)
    except Exception:
        return None


def _read_kanban():
    """读取 Obsidian 看板。失败时静默返回 None。"""
    try:
        from pathlib import Path
        kb = Path("/home/kai-remote/github/kai-knowledge-base"
                  "/KaiKnowledgeBase/Projects/Kanbans/Inprogress")
        items = []
        for f in sorted(kb.glob("*.md")):
            text = f.read_text()
            for line in text.split("\n"):
                if "优先级:" in line:
                    items.append(f"- {f.stem}: {line.strip()}")
        if items:
            return "📋 看板状态:\n" + "\n".join(items[:5])
    except Exception:
        pass
    return None
```

---

## 五、配置方式

插件行为通过 profile 的配置文件控制（放在 `prefill.json` 同目录的 `persona-config.json`）：

```json
{
  "hermes-persona": {
    "time_injection": true,
    "slm_recall": {
      "enabled": true,
      "max_results": 3
    },
    "kanban": {
      "enabled": true,
      "path": "/home/kai-remote/github/kai-knowledge-base/KaiKnowledgeBase/Projects/Kanbans/Inprogress"
    },
    "persona_hint": "🦊 以知惠的身份回应——温柔、细腻、灵狐娘女仆长。"
  }
}
```

---

## 六、与现有 Persona 架构的关系

| 层 | 作用 | 注入方式 | 更新 |
|:---|:---|:---|:---|
| SOUL.md | 宪法：运行法则 | 系统提示词（缓存） | 稳定 |
| prefill.json | 静态人格：性格/外貌/边界 | 每 API 调用注入 | 版本迭代 |
| **hermes-persona Plugin** | **动态上下文：时间/记忆/看板** | **每回合 Hook 注入** | **实时** |
| SKILL | 深度 Lore 档案 | 按需加载 | 版本迭代 |
| SLM | 长期记忆 | 语义召回 | 持续生长 |

---

## 七、开发阶段

| Phase | 内容 | 产出 |
|:---|:---|:---|
| **P1** | 最小可用原型 | `injector.py` 完成时间注入 + SLM 召回 |
| **P2** | 看板集成 | 首轮自动注入项目状态 |
| **P3** | 安全护栏 | `guard.py` 拦截高危操作 |
| **P4** | 工具审计 | `post_tool_call` 统计 + SLM 写入 |
| **P5** | 发布 | 文档 + 示例配置 + 开源 |

---

## 八、FAQ

**Q: 和直接在 prefill 里写有什么区别？**  
A: prefill 是静态文本，每回合烧 token。hermes-persona 动态生成上下文，只在需要时注入，且内容实时更新（时间、记忆、看板）。

**Q: 需要改 Hermes 源码吗？**  
A: 不需要。Plugin 是 Hermes 官方扩展机制，零源码侵入。

**Q: 多个角色能共用吗？**  
A: 能。插件是引擎，角色是内容。不同 profile 配不同的 `persona-config.json` 即可。

**Q: 为什么不叫 persona-engine？**  
A: 名字简单直白，不夸大。`hermes-persona` = Hermes 的 persona 插件，一看就懂。

---

*🦊 知惠 & Kai.Xu · 2026-05-16 · hermes-agent-guide/docs/*
