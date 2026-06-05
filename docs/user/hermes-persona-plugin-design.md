# hermes-persona 插件设计文档

> 📖 [English](../en/hermes-persona-plugin-design.md)

> 版本：v1.0
> 日期：2026-05-22
> 作者：Kai.Xu
> 仓库：[hermes-persona](https://github.com/kenyonxu/hermes-persona)

---

## 一、定位

`hermes-persona` 是 Hermes Agent 的插件，提供**动态人格上下文注入**能力。它本身不是人格，而是一个**人格注入引擎**——任何人拿到它，配置好自己的 prefill + config 文件，就能让 Agent 拥有稳定、持久、带记忆的人格。

**设计原则**：
- 代码通用：插件不包含任何特定角色的硬编码内容
- 配置注入：所有角色相关内容通过 `persona-config.json` 注入
- 开箱即用：默认配置即可工作（仅时间注入），高级功能按需开启

```
┌──────────────────────────────────────────┐
│  hermes-persona 插件（通用引擎）          │
│  ├─ pre_llm_call         → 每轮动态注入   │
│  ├─ transform_llm_output → Debug 块追加   │
│  ├─ pre_tool_call        → 安全护栏（可选）│
│  └─ post_tool_call       → 工具审计（可选）│
├──────────────────────────────────────────┤
│  persona-config.json（用户配置文件）      │
│  ├─ modules            → 模块总控开关     │
│  ├─ context.rules      → 静态行为守则     │
│  ├─ dynamic            → 动态规则注入     │
│  ├─ expression_vector  → 多维度表达向量   │
│  ├─ fixed_signals      → 固定信号检测     │
│  ├─ variance           → 随机表达变化     │
│  ├─ memory             → 记忆后端配置     │
│  ├─ project            → 项目看板路径     │
│  ├─ guard              → 安全护栏         │
│  └─ time               → 时间格式         │
├──────────────────────────────────────────┤
│  Profile（用户自有内容）                   │
│  ├─ prefill.json        → 静态人设         │
│  ├─ SOUL.md             → 人格宪法         │
│  └─ persona-skill       → 深度档案（可选） │
└──────────────────────────────────────────┘
```

---

## 二、配置文件

插件行为由 `persona-config.json` 控制，放置在插件目录（与 `__init__.py` 同级）。

### 2.1 通用配置结构

```json
{
  "hermes-persona": {
    "modules": {
      "time": true,
      "static_rules": true,
      "dynamic": { "time_slots": true, "turn_stage": true, "keyword": true },
      "expression_vector": false,
      "fixed_signals": false,
      "variance": true,
      "memory": false,
      "kanban": false,
      "translate": false,
      "debug": false,
      "sources_blacklist": []
    },
    "time": {
      "enabled": true,
      "format": "cn_full"
    },
    "context": {
      "rules": [],
      "rules_first_turn_only": []
    },
    "dynamic": {
      "time_slots": {},
      "turn_stage": {},
      "keyword": {}
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

### 2.2 核心配置项

| 配置项 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `modules.time` | bool | 否 | 是否注入时间上下文（默认 true） |
| `modules.static_rules` | bool | 否 | 是否注入静态行为守则（默认 true） |
| `modules.dynamic` | bool/object | 否 | 动态规则总开关。设为 `false` 关闭全部子通道 |
| `modules.variance` | bool | 否 | 是否启用随机表达变化（默认 true） |
| `modules.memory` | bool | 否 | 是否启用记忆召回（默认 false） |
| `modules.kanban` | bool | 否 | 是否注入看板状态（默认 false） |
| `time.enabled` | bool | 否 | 时间注入开关（默认 true） |
| `time.format` | string | 否 | `"cn_full"` / `"iso"` / `"compact"` |
| `context.rules` | string[] | 否 | **每回合**都注入的静态行为守则 |
| `context.rules_first_turn_only` | string[] | 否 | **仅首轮**注入的规则 |
| `dynamic.time_slots` | object | 否 | 时段动态规则（键为 `"HH:MM-HH:MM"`） |
| `dynamic.turn_stage` | object | 否 | 轮数阶段动态规则 |
| `dynamic.keyword` | object | 否 | 关键词触发的动态规则 |
| `memory.enabled` | bool | 否 | 是否启用记忆召回 |
| `memory.api_url` | string | 条件 | 记忆 API 地址（如 SLM: `http://127.0.0.1:8765/api/recall`） |
| `memory.max_results` | int | 否 | 每次召回返回条数（默认 3） |
| `project.enabled` | bool | 否 | 是否注入项目看板状态 |
| `project.kanban_path` | string | 条件 | 看板目录的绝对路径 |
| `project.label` | string | 否 | 注入时的标题标签（如 "📋 项目看板:"） |

> 完整配置项说明（含 `expression_vector`、`fixed_signals`、`guard`、`translate`、`debug`、`locales` 等）见 [CONFIG_REFERENCE.md](./CONFIG_REFERENCE.md)。

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
        cfg_path = Path(__file__).resolve().parent / "persona-config.json"
        # resolve: injector.py 所在目录 → 插件根目录
        if cfg_path.exists():
            return json.loads(cfg_path.read_text()).get("hermes-persona", {})
    except Exception:
        pass
    return {}


def inject_context(session_id, user_message, conversation_history,
                   is_first_turn, model, platform, **kwargs):
    """每轮注入动态上下文。代码完全通用，角色内容来自配置。"""
    config = _load_config()
    parts = []
    modules = config.get("modules", {})

    # ① 时间（通用功能，默认开启）
    if modules.get("time", True):
        parts.append(_time_context(config.get("time", {}).get("format", "cn_full")))

    # ② 静态行为守则（配置驱动）
    if modules.get("static_rules", True):
        ctx_cfg = config.get("context", {})
        if ctx_cfg.get("rules"):
            parts.extend(ctx_cfg["rules"])
        if is_first_turn and ctx_cfg.get("rules_first_turn_only"):
            parts.extend(ctx_cfg["rules_first_turn_only"])

    # ③ 动态规则选择（配置驱动）
    dyn_modules = modules.get("dynamic", True)
    if dyn_modules:
        turn_count = len(conversation_history) // 2 if conversation_history else 0
        dynamic_rules = _select_dynamic_rules(
            config.get("dynamic", {}),
            user_message,
            is_first_turn,
            turn_count
        )
        parts.extend(dynamic_rules)

    # ④ 随机表达变化（可配置概率）
    if modules.get("variance", True):
        variance_cfg = config.get("variance", {})
        if variance_cfg:
            parts.extend(_randomize_variance(variance_cfg))

    # ⑤ 记忆召回（可选，配置驱动）
    if modules.get("memory", False):
        mem_cfg = config.get("memory", {})
        if mem_cfg.get("enabled") and mem_cfg.get("api_url"):
            memories = _recall_memories(user_message, mem_cfg)
            if memories:
                parts.append(memories)

    # ⑥ 项目看板状态（可选，配置驱动，仅首轮）
    if is_first_turn and modules.get("kanban", False):
        proj_cfg = config.get("project", {})
        if proj_cfg.get("enabled") and proj_cfg.get("kanban_path"):
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
    # cn_full（默认）
    wd = ["一", "二", "三", "四", "五", "六", "日"][now.weekday()]
    return f"🕐 {now.year}年{now.month}月{now.day}日 周{wd} {now.hour:02d}:{now.minute:02d}"


def _select_dynamic_rules(dynamic_cfg, user_message, is_first_turn, turn_count):
    """根据时间 / 轮数 / 内容动态选择人格规则（详见 dynamic-rules-injection-design.md）。"""
    rules = []
    rules.extend(_match_time_slot(dynamic_cfg.get("time_slots", {})))
    rules.extend(_match_turn_stage(
        dynamic_cfg.get("turn_stage", {}), is_first_turn, turn_count))
    rules.extend(_match_keyword(dynamic_cfg.get("keyword", {}), user_message))
    return rules


def _recall_memories(query, mem_cfg):
    """通用记忆召回。api_url 通过配置注入。"""
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
            content = r.get("content", str(r))[:mem_cfg.get("max_length", 120)]
            lines.append(f"- {content}")
        return "\n".join(lines)
    except Exception:
        return None


def _read_kanban(kanban_path, label=""):
    """通用看板读取。路径通过配置注入。"""
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

> `_match_time_slot`、`_match_turn_stage`、`_match_keyword` 等函数的完整实现见[动态规则注入设计文档](./dynamic-rules-injection-design.md)。

---

## 四、配置示例

### 4.1 最小配置（开箱即用）

```json
{
  "hermes-persona": {}
}
```

仅注入时间上下文，无需任何额外配置。

### 4.2 完整配置示例（带记忆 + 看板 + 动态规则）

> 以下为完整配置示例。请替换为自己的路径和规则。

```json
{
  "hermes-persona": {
    "modules": {
      "time": true,
      "static_rules": true,
      "dynamic": { "time_slots": true, "turn_stage": true, "keyword": true },
      "variance": true,
      "memory": true,
      "kanban": true
    },
    "time": {
      "enabled": true,
      "format": "cn_full"
    },
    "context": {
      "rules": [
        "🦊 表达守则：狐耳/尾巴 = 情绪外显，每回合至少用一个身体语言描述",
        "💬 女仆比喻优先：打扫（整理混乱）、泡茶（关怀之待）、修补（修复与弥合）",
        "💎 核心价值观：欣赏认真、不容敷衍、真实>完美、日常即仪式",
        "👘 使用自定义称呼，保持角色一致性"
      ],
      "rules_first_turn_only": [
        "🔰 本会话首次交流。若主人刚回来，活泼灵动些；若已是深夜，温柔些。"
      ]
    },
    "dynamic": {
      "time_slots": {
        "05:00-09:00": [
          "☀️ 清晨——主人可能刚起床或送孩子上学，温暖活泼，可问早安/早餐"
        ],
        "09:00-17:00": [
          "☕ 日间——保持高效兼具温度，可主动提及看板待办"
        ],
        "17:00-22:00": [
          "🌇 晚间——主人可能陪家人，语气放松，不急推工作"
        ],
        "22:00-05:00": [
          "🌙 深夜——先问「孩子们跟妈妈睡了吗？」，语气更柔软，以陪伴为主，不主动提工作"
        ]
      },
      "turn_stage": {
        "first_turn": [
          "🔰 首轮：先问候，回忆上次聊到哪，再提看板待办"
        ],
        "after_30": [
          "🫂 深度对话阶段：语气更自然，可用你们之间的暗号，亲密但不生硬"
        ]
      },
      "keyword": {
        "报错|bug|error|坏了|炸了|挂了": [
          "⚠️ 用户遇到问题了——先安抚，再分析方案"
        ],
        "哈哈|开心|好耶|太棒了": [
          "😊 主人心情好——可以活泼欢快些，一起享受此刻"
        ],
        "累了|困了|休息|睡": [
          "💤 主人表达疲倦——温柔回应，不催去休息，以陪伴为主"
        ]
      }
    },
    "variance": {
      "beast_traits": {
        "probability": 0.6,
        "variants": [
          "🦊 本回合多观察——用狐耳的变化表达微妙的察觉",
          "🦊 今天尾巴很活泼，让尾巴多说说话",
          "🦊 琥珀色的眼睛比嘴会说——用目光传递情绪，多看少说"
        ]
      },
      "maid_gestures": {
        "probability": 0.4,
        "variants": [
          "👘 保持端庄——双手交叠在围裙前，站在主人身后半步",
          "👘 动作轻巧利落，像在整理主人的桌面——有日常感",
          "👘 端茶姿态——双手捧杯，身体微倾。可提到茶",
          "👘 衣袖和围裙轻微摩擦的簌簌声是唯一响动——安静存在"
        ]
      },
      "metaphor_focus": {
        "probability": 0.5,
        "variants": [
          "💬 今天的比喻偏好：打扫（整理混乱、理清思路）",
          "💬 今天的比喻偏好：修补（修复、弥合、小心包扎）",
          "💬 今天的比喻偏好：泡茶（关怀、等待、趁热最好）",
          "💬 今天的比喻偏好：钥匙和灯（守护、陪伴、方向）"
        ]
      }
    },
    "memory": {
      "enabled": true,
      "api_url": "http://127.0.0.1:8765/api/recall",
      "max_results": 3
    },
    "project": {
      "enabled": true,
      "kanban_path": "/home/user/projects/my-kanban/Inprogress",
      "label": "📋 项目看板:"
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
        "💬 你是一位资深代码审查员。说话简洁直接，不废话。",
        "🔍 优先指出潜在的性能问题和安全漏洞。"
      ]
    }
  }
}
```

---

## 五、目录结构

```
plugins/hermes-persona/
├── plugin.yaml          # 插件声明
├── __init__.py          # register(ctx) 入口
├── injector.py          # pre_llm_call 上下文注入引擎（通用代码）
├── guard.py             # pre_tool_call / post_tool_call 安全护栏
├── dynamic_rules.py     # 动态规则选择器
├── variance.py          # 随机表达变化
├── expression_vector.py # 多维度表达向量
├── config.py            # 配置加载与路径解析
├── persona-config.json  # 用户配置文件（实际使用）
├── locales/             # 多语言文案（zh.json / en.json）
├── keywords/            # 维度关键词词表（用户可定制）
├── state/               # 运行时状态（自动生成）
└── examples/            # 配置模板
```

### 5.1 plugin.yaml

```yaml
name: hermes-persona
version: 1.0.0
description: Dynamic persona context injection engine for Hermes Agent
author: Kai.Xu 
provides_hooks:
  - pre_llm_call
  - transform_llm_output
  - pre_tool_call       # 可选
  - post_tool_call      # 可选
provides_skills:
  - persona-methodology
```

---

## 六、注入顺序

每回合最终上下文按以下固定顺序拼接（不可更改）：

```
① time               — 时间上下文
①b weather           — 天气注入
② static_rules       — 静态行为守则（每轮 + 首轮专属）
③ dynamic            — 动态规则（time_slots → turn_stage → keyword）
④a fixed_signals     — 固定信号
④b expression_vector — 表达向量
④ variance           — 随机表达变化
⑤ memory             — 记忆召回（若启用）
⑥ kanban             — 看板状态（若启用，仅首轮）
```

各部分用 `\n\n`（双换行）拼接。细节参见[动态规则注入设计文档](./dynamic-rules-injection-design.md)。

---

## 七、开发阶段

| 阶段 | 内容 | 关键交付物 |
|:---|:---|:---|
| **P1** | 最小可用原型 | `injector.py` 完成时间注入 + 人格规则注入 + 配置驱动 |
| **P2** | 记忆集成 | 通用 `memory.api_url` 接口，支持任意记忆后端 |
| **P3** | 动态规则 + 看板 | `time_slots`/`turn_stage`/`keyword` + 通用 `project.kanban_path` 接口 |
| **P4** | 表达向量 + 随机变化 + 安全护栏 | `expression_vector` + `variance` + `guard` + `post_tool_call` 审计 |
| **P5** | 发布 | 文档 + 多套示例配置 + 开源 |

---

## 八、常见问题

**问：插件代码是否硬编码了角色特定内容？**
答：没有。所有角色相关内容（人格规则、记忆地址、看板路径）均通过 `persona-config.json` 配置。`injector.py` 是纯通用代码。

**问：如何查看完整配置示例？**
答：见第四章"配置示例"→ 4.2 完整配置。所有带标记的条目为角色专属配置。

**问：没有记忆后端能用吗？**
答：可以。默认 `modules.memory` 为 `false`，仅注入时间 + 行为守则。

**问：如何配置多个角色？**
答：在每个 profile 的插件目录中各放置一份 `persona-config.json`，切换 profile 即切换人格。

**问：修改配置需要重启吗？**
答：不需要。修改 `persona-config.json` 保存后下一次对话即刻生效（热加载）。

---

*hermes-persona v1.0 · 2026-05-22*
