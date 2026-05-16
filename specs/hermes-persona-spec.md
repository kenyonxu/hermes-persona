# hermes-persona 实现规格说明书

> 版本：v1.0
> 日期：2026-05-16
> 基于：`docs/hermes-persona-plugin-design.md` v0.2 + `docs/dynamic-rules-injection-design.md` v0.1

---

## 一、概述

### 1.1 产品定位

`hermes-persona` 是一个 **Hermes Agent 插件**，为 Agent 提供**动态人格上下文注入**能力。它本身不是一个人格，而是一个**通用的人格注入引擎**——任何人配置自己的 `persona-config.json` + `prefill.json`，即可让 Agent 获得稳定、持久、有记忆的人格。

### 1.2 核心设计原则

| 原则 | 含义 |
|:---|:---|
| **代码通用** | `injector.py` 等核心模块不含任何角色硬编码，所有角色内容来自配置 |
| **配置驱动** | 全部行为通过 `persona-config.json` 控制，零代码切换人格 |
| **开箱即用** | 空配置 `{}` 即可工作（仅注入时间上下文），高级功能按需开启 |
| **可组合** | 时间 / 静态规则 / 动态规则 / 记忆 / 看板 / 随机变化 — 每层独立开关 |

### 1.3 适用场景

- 为通用 Agent 注入稳定的角色人格（如兽娘女仆、代码审查员、导师）
- 同一引擎通过不同配置文件支持多个角色（切换 profile 即切换人格）
- 生产环境下的 Agent 行为一致性保障

---

## 二、架构概览

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                      Hermes Agent Runtime                        │
│                                                                  │
│  ┌──────────┐   ┌──────────────────┐   ┌──────────────────┐     │
│  │ 用户输入  │──▶│ hermes-persona   │──▶│  LLM (带注入上下  │     │
│  │          │   │  Plugin           │   │  文的系统提示)    │     │
│  └──────────┘   │                  │   └──────────────────┘     │
│                  │ ┌──────────────┐ │                            │
│                  │ │ pre_llm_call │ │  ← 每回合动态上下文注入     │
│                  │ ├──────────────┤ │                            │
│                  │ │ pre_tool_call│ │  ← 安全护栏 (P4)           │
│                  │ ├──────────────┤ │                            │
│                  │ │post_tool_call│ │  ← 工具审计 (P4)           │
│                  │ └──────────────┘ │                            │
│                  └──────────────────┘                            │
│                         │                                        │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  persona-config.json                       │   │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │   │
│  │  │  time   │ │ context  │ │ variance │ │    memory     │  │   │
│  │  │ (时间)  │ │ .rules   │ │ (随机)   │ │   (记忆)      │  │   │
│  │  │         │ │ .dynamic │ │          │ │               │  │   │
│  │  └─────────┘ └──────────┘ └──────────┘ └───────────────┘  │   │
│  │  ┌─────────┐                                               │   │
│  │  │ project │  ← 看板状态 (P3)                              │   │
│  │  └─────────┘                                               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                         │                                        │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              外部服务 (可选)                                │   │
│  │  ┌──────────────┐  ┌──────────────────┐                   │   │
│  │  │ 记忆后端 API  │  │  项目看板文件系统  │                   │   │
│  │  │ (SLM/向量库)  │  │  (Kanban/*.md)   │                   │   │
│  │  └──────────────┘  └──────────────────┘                   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
用户消息到达
  │
  ▼
Hermes Runtime 调用 hook: pre_llm_call(session_id, user_message, ...)
  │
  ▼
hermes-persona::inject_context()
  │
  ├── 1. _load_config()                      → 加载 persona-config.json
  ├── 2. _time_context(format)               → "2026年5月16日 周五 14:30"
  ├── 3. _inject_static_rules(ctx)            → context.rules + rules_first_turn_only
  ├── 4. _select_dynamic_rules(ctx, msg, ...) → time_slots + turn_stage + keyword
  ├── 5. _randomize_variance(ctx)            → 每回合随机选择 1-2 条表达提示
  ├── 6. _recall_memories(msg, mem_cfg)       → 记忆 API 召回 (if enabled)
  ├── 7. _read_kanban(path, label)            → 看板状态 (if enabled, first_turn only)
  │
  ▼
返回 {"context": "拼接后的完整上下文字符串"}
  │
  ▼
Hermes Runtime 将 context 注入 LLM 系统提示 → LLM 生成带有角色人格的回复
```

### 2.3 目录结构

```
~/.hermes/plugins/00-hermes-persona/
├── plugin.yaml              # 插件声明 (name/version/hooks/skills)
├── __init__.py              # register(ctx) 入口
├── injector.py              # pre_llm_call 上下文注入引擎 (通用代码)
├── dynamic_rules.py         # 动态规则选择器 (time_slots/turn_stage/keyword)
├── variance.py              # 随机表达变化 (probability + variants)
├── guard.py                 # pre_tool_call 安全护栏 (P4)
├── skill.md                 # 捆绑技能：persona 方法论使用文档
└── tests/
    ├── test_injector.py
    ├── test_dynamic_rules.py
    └── test_variance.py
```

### 2.4 Profile 目录结构 (用户侧)

```
~/.hermes/profiles/<profile-name>/
├── prefill.json             # 静态人格 few-shot 锚点
├── persona-config.json      # 插件配置 (本 spec 的核心)
├── SOUL.md                  # 人格宪法 (不变的基础设定)
└── persona-skill.md         # 深度档案 (可选)
```

---

## 三、模块接口

### 3.1 plugin.yaml

```yaml
name: hermes-persona
version: 0.1.0
description: Dynamic persona context injection engine for Hermes Agent
author: Kai.Xu & Zhihui
provides_hooks:
  - pre_llm_call
  - pre_tool_call       # P4
  - post_tool_call      # P4
provides_skills:
  - persona-methodology
```

### 3.2 `__init__.py` — 插件入口

```python
def register(ctx):
    """
    在 Hermes 插件系统中注册 hermes-persona。
    
    Args:
        ctx: Hermes PluginContext，提供 register_hook() 等方法
    
    Hooks registered:
        - pre_llm_call:  injector.inject_context      (P1)
        - pre_tool_call: guard.check_tool_call         (P4)
        - post_tool_call: guard.audit_tool_call        (P4)
    """
```

### 3.3 `injector.py` — 上下文注入引擎

#### 3.3.1 主入口 `inject_context()`

```python
def inject_context(
    session_id: str,
    user_message: str,
    conversation_history: list[dict],
    is_first_turn: bool,
    model: str,
    platform: str,
    **kwargs
) -> dict | None:
    """
    每回合由 Hermes Runtime 调用，返回动态人格上下文。
    
    Args:
        session_id:          会话唯一标识
        user_message:        用户当前消息文本
        conversation_history: 对话历史 [{"role":"user","content":"..."}, ...]
        is_first_turn:       是否为本会话首轮
        model:               当前使用的 LLM 模型名称
        platform:            运行平台标识
        **kwargs:            扩展参数 (预留给未来维度)
    
    Returns:
        {"context": "拼接后的完整上下文字符串"} 或 None (无需注入时)
    """
```

#### 3.3.2 内部函数一览

| 函数 | 模块 | 职责 | Phase |
|:---|:---|:---|:---|
| `_load_config()` | injector.py | 加载 `persona-config.json`，失败返回 `{}` | P1 |
| `_time_context(fmt)` | injector.py | 生成当前时间描述字符串 | P1 |
| `_inject_static_rules(ctx_cfg, is_first_turn)` | injector.py | 读取 `context.rules` + `context.rules_first_turn_only` | P1 |
| `_select_dynamic_rules(dynamic_cfg, msg, is_first, turn_count)` | dynamic_rules.py | 按时间/轮数/关键词选择动态规则 | P1 |
| `_match_time_slot(time_slots)` | dynamic_rules.py | 当前时间匹配时段规则 | P1 |
| `_match_turn_stage(turn_stages, is_first, turn_count)` | dynamic_rules.py | 当前轮数匹配阶段规则 | P1 |
| `_match_keyword(keywords, user_message)` | dynamic_rules.py | 用户消息关键词匹配规则 | P2 |
| `_in_time_range(now, start, end)` | dynamic_rules.py | 判断时间是否在 [start, end) 区间 (支持跨午夜) | P1 |
| `_randomize_variance(variance_cfg)` | variance.py | 按概率随机选择表达变化 | P2 |
| `_recall_memories(query, mem_cfg)` | injector.py | 调用记忆 API 召回相关内容 | P2 |
| `_read_kanban(path, label)` | injector.py | 读取项目看板文件 | P3 |

### 3.4 `dynamic_rules.py` — 动态规则选择器

#### 3.4.1 接口定义

```python
def _select_dynamic_rules(
    dynamic_cfg: dict,        # 来自 config["context"]["dynamic"]
    user_message: str,
    is_first_turn: bool,
    turn_count: int           # len(conversation_history) // 2
) -> list[str]:
    """
    根据时间、轮数、关键词三个维度选择动态规则。
    返回: ["🕐 [22:00-05:00] 🌙 深夜时段...", "🔰 首轮...", ...]
    """
```

#### 3.4.2 子函数

```python
def _match_time_slot(time_slots: dict) -> list[str]:
    """
    输入: {"22:00-05:00": ["规则A", "规则B"], ...}
    行为: 用 datetime.now() 匹配 HH:MM 区间 (支持跨午夜)
    输出: 匹配到的时段规则列表 (已添加 🕐 [HH:MM-HH:MM] 前缀)
    """

def _match_turn_stage(turn_stages: dict, is_first_turn: bool, turn_count: int) -> list[str]:
    """
    输入: {"first_turn": ["规则A"], "after_30": ["规则B"], ...}
    行为: 
      - is_first_turn=True 时注入 "first_turn" 规则
      - 按阈值从高到低匹配 "after_N"，取第一个满足 turn_count >= N 的
    输出: 匹配到的阶段规则列表
    """

def _match_keyword(keywords: dict, user_message: str) -> list[str]:
    """
    输入: {"报错|bug|error": ["规则A"], "哈哈|开心": ["规则B"], ...}
    行为: 按配置顺序正则匹配用户消息，命中第一个即返回
    输出: 匹配到的关键词规则列表 (已添加 💬 [pattern] 前缀)
    """

def _in_time_range(now: str, start: str, end: str) -> bool:
    """
    输入: now="02:30", start="22:00", end="05:00"
    行为: if start <= end → start <= now < end
          else (跨午夜) → now >= start or now < end
    输出: bool
    """
```

### 3.5 `variance.py` — 随机表达变化

```python
def _randomize_variance(variance_cfg: dict) -> list[str]:
    """
    输入: {
        "beast_traits": {
            "probability": 0.6,
            "variants": ["提示A", "提示B", "提示C"]
        },
        ...
    }
    行为:
      对每个 category:
        1. 以 probability 概率决定是否使用本维度 (random.random() < prob)
        2. 若使用，从 variants 中随机选一条 (random.choice)
    输出: 被选中的提示字符串列表 (每回合平均 1-2 条)
    """
```

### 3.6 `guard.py` — 安全护栏 (P4)

```python
def check_tool_call(tool_name: str, tool_args: dict, **kwargs) -> dict | None:
    """
    pre_tool_call hook。在工具调用前检查安全性。
    
    Args:
        tool_name: 即将调用的工具名
        tool_args: 工具参数
    Returns:
        {"blocked": True, "reason": "..."}  阻止调用
        None                                放行
    """

def audit_tool_call(tool_name: str, tool_args: dict, result: any, **kwargs) -> None:
    """
    post_tool_call hook。记录工具调用审计日志。
    """
```

---

## 四、配置 Schema

### 4.1 完整 `persona-config.json` Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "hermes-persona Configuration",
  "type": "object",
  "properties": {
    "hermes-persona": {
      "type": "object",
      "properties": {
        "time": {
          "type": "object",
          "properties": {
            "enabled": {
              "type": "boolean",
              "default": true,
              "description": "是否注入时间上下文。默认开启。"
            },
            "format": {
              "type": "string",
              "enum": ["cn_full", "iso", "compact"],
              "default": "cn_full",
              "description": "时间格式。cn_full: '2026年5月16日 周五 14:30' / iso: ISO8601 / compact: '05/16 14:30'"
            }
          }
        },
        "context": {
          "type": "object",
          "properties": {
            "rules": {
              "type": "array",
              "items": {"type": "string"},
              "default": [],
              "description": "每回合注入的静态人格规则。始终追加到上下文。"
            },
            "rules_first_turn_only": {
              "type": "array",
              "items": {"type": "string"},
              "default": [],
              "description": "仅首轮注入的静态规则。适合开场寒暄等一次性提示。"
            },
            "dynamic": {
              "type": "object",
              "properties": {
                "time_slots": {
                  "type": "object",
                  "additionalProperties": {
                    "type": "array",
                    "items": {"type": "string"}
                  },
                  "default": {},
                  "description": "时段规则。key 为 'HH:MM-HH:MM' 格式，value 为该时段注入的规则列表。支持跨午夜区间。"
                },
                "turn_stage": {
                  "type": "object",
                  "properties": {
                    "first_turn": {
                      "type": "array",
                      "items": {"type": "string"}
                    }
                  },
                  "patternProperties": {
                    "^after_[0-9]+$": {
                      "type": "array",
                      "items": {"type": "string"}
                    }
                  },
                  "default": {},
                  "description": "轮数规则。first_turn 为首轮注入，after_N 为第 N 轮后注入。"
                },
                "keyword": {
                  "type": "object",
                  "additionalProperties": {
                    "type": "array",
                    "items": {"type": "string"}
                  },
                  "default": {},
                  "description": "关键词规则。key 为正则表达式模式 (用 | 连接)，value 为命中后注入的规则。按配置顺序匹配，命中第一个即停止。"
                }
              }
            }
          }
        },
        "variance": {
          "type": "object",
          "additionalProperties": {
            "type": "object",
            "properties": {
              "probability": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "本维度每回合出现的概率"
              },
              "variants": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "表达变体列表，命中后随机选一条"
              }
            },
            "required": ["probability", "variants"]
          },
          "default": {},
          "description": "随机表达变化配置。key 为维度名称，value 包含出现概率和变体列表。"
        },
        "memory": {
          "type": "object",
          "properties": {
            "enabled": {
              "type": "boolean",
              "default": false,
              "description": "是否启用记忆召回。"
            },
            "api_url": {
              "type": "string",
              "format": "uri",
              "description": "记忆 API 端点 (如 'http://127.0.0.1:8765/api/recall')。enabled=true 时必填。"
            },
            "max_results": {
              "type": "integer",
              "minimum": 1,
              "maximum": 20,
              "default": 3,
              "description": "每次召回的最大条数。"
            }
          }
        },
        "project": {
          "type": "object",
          "properties": {
            "enabled": {
              "type": "boolean",
              "default": false,
              "description": "是否注入项目看板状态。"
            },
            "kanban_path": {
              "type": "string",
              "description": "看板目录的绝对路径。enabled=true 时必填。"
            },
            "label": {
              "type": "string",
              "default": "📋 项目状态:",
              "description": "注入时的标题标签。"
            }
          }
        }
      }
    }
  }
}
```

### 4.2 配置层级总览

```
persona-config.json
└── "hermes-persona"
    ├── time                           (P1) 时间注入
    │   ├── enabled: bool
    │   └── format: "cn_full"|"iso"|"compact"
    ├── context                        (P1-P2) 上下文规则
    │   ├── rules: string[]            (P1) 静态规则
    │   ├── rules_first_turn_only: string[]  (P1) 首轮静态规则
    │   └── dynamic                    (P1-P2) 动态规则
    │       ├── time_slots: {range → rules}   (P1)
    │       ├── turn_stage: {stage → rules}   (P1)
    │       └── keyword: {pattern → rules}    (P2)
    ├── variance                      (P2) 随机表达变化
    │   └── <dimension>
    │       ├── probability: float (0.0~1.0)
    │       └── variants: string[]
    ├── memory                        (P2) 记忆召回
    │   ├── enabled: bool
    │   ├── api_url: string
    │   └── max_results: int
    └── project                       (P3) 项目看板
        ├── enabled: bool
        ├── kanban_path: string
        └── label: string
```

### 4.3 最小配置

```json
{
  "hermes-persona": {}
}
```

等价于：
- `time.enabled` = `true`, `time.format` = `"cn_full"`
- `context.rules` = `[]`, `context.dynamic` = `{}`
- `variance` = `{}`
- `memory.enabled` = `false`
- `project.enabled` = `false`

### 4.4 各维度规则注入优先级

每回合最终注入的规则列表按以下顺序拼接（不覆盖，只追加）：

```
最终 context = 
  time_context()                          # 🕐 时间
  + context.rules                         # 静态规则
  + (if first_turn) rules_first_turn_only # 首轮特殊规则
  + dynamic.time_slots[当前时段]            # 时间段适配
  + dynamic.turn_stage[当前轮数]            # 轮数适配
  + dynamic.keyword[匹配到的模式]           # 关键词适配
  + variance[随机选中的维度]                # 随机表达变化
  + recall_memories()                     # 记忆召回 (if enabled)
  + (if first_turn) read_kanban()         # 看板状态 (if enabled, first_turn only)
```

---

## 五、开发阶段

### 5.1 Phase 概览

| Phase | 名称 | 产出 | 依赖 |
|:---|:---|:---|:---|
| **P1** | 最小可用原型 | 时间注入 + 静态规则 + 动态规则(时间/轮数) + 配置加载 | 无 |
| **P2** | 动态扩展 | 关键词匹配 + 随机变化 + 记忆召回 | P1 |
| **P3** | 看板集成 | 项目看板读取 + 注入 | P1 |
| **P4** | 安全护栏 | pre_tool_call 检查 + post_tool_call 审计 | P1 |
| **P5** | 发布就绪 | 文档 + 测试 + 多示例配置 + 性能基准 | P1-P4 |

### 5.2 P1 — 最小可用原型

**目标**：配置驱动的人格上下文注入引擎，支持时间注入 + 静态规则 + 时段/轮数动态规则。

**交付物**：

| 文件 | 内容 |
|:---|:---|
| `plugin.yaml` | 插件声明，hooks: `pre_llm_call` |
| `__init__.py` | `register(ctx)` 入口，注册 `pre_llm_call` hook |
| `injector.py` | `inject_context()`, `_load_config()`, `_time_context()`, `_inject_static_rules()`, `_recall_memories()` (stub), `_read_kanban()` (stub) |
| `dynamic_rules.py` | `_select_dynamic_rules()`, `_match_time_slot()`, `_match_turn_stage()`, `_in_time_range()` |
| `variance.py` | 目录 + `__init__.py` (stub, P2 实现) |
| `guard.py` | 目录 + `__init__.py` (stub, P4 实现) |

**核心行为**：
1. 加载 `persona-config.json`，不存在时返回空配置
2. 按 `time.format` 生成时间上下文字符串
3. 注入 `context.rules` 全部规则
4. 若 `is_first_turn`，追加 `context.rules_first_turn_only`
5. 匹配 `context.dynamic.time_slots`，命中后追加时段规则
6. 匹配 `context.dynamic.turn_stage`，命中后追加阶段规则
7. 将所有 parts 用 `\n\n` 拼接，返回 `{"context": "..."}`

**验收标准**：
- [ ] 空配置 `{}` 能正常工作，仅返回时间上下文
- [ ] 静态规则 `context.rules` 每回合均注入
- [ ] `rules_first_turn_only` 仅在首轮注入
- [ ] 时段匹配正确：`"22:00-05:00"` 跨午夜区间在凌晨 02:30 命中
- [ ] 轮数匹配正确：第 35 轮命中 `after_30` 而非同时命中 `after_10`
- [ ] `conversation_history` 为 `None`/`[]` 时轮数计算不崩溃
- [ ] 配置文件不存在时不抛异常，降级为空配置
- [ ] 代码中不包含任何角色特定内容

### 5.3 P2 — 动态扩展

**目标**：关键词匹配 + 随机表达变化 + 外部记忆召回。

**交付物**：

| 文件 | 内容 |
|:---|:---|
| `dynamic_rules.py` | 新增 `_match_keyword()` |
| `variance.py` | `_randomize_variance()` 完整实现 |
| `injector.py` | `_recall_memories()` 完整实现 (httpx POST → 记忆 API) |

**核心行为**：
1. `_match_keyword()` 按配置顺序正则匹配用户消息，命中第一个模式后返回对应规则
2. `_randomize_variance()` 对每个 variance 维度：以 `probability` 决定是否使用，使用则从 `variants` 中随机选一条
3. `_recall_memories()` 以用户消息为 query 调用 `memory.api_url`，取回 `max_results` 条记忆并渲染为上下文
4. 所有新功能在 `inject_context()` 中接入

**验收标准**：
- [ ] 关键词匹配按配置顺序命中第一个模式
- [ ] 关键词匹配对空消息返回 `[]`
- [ ] 关键词匹配正则正确工作（如 `"坏了|炸了|挂了"` 匹配 "系统坏了" 但不变匹配 "坏了系统"）
- [ ] `_randomize_variance()` 在 `probability=0` 时从不返回
- [ ] `_randomize_variance()` 在 `probability=1.0` 时总是返回
- [ ] `_randomize_variance()` 在 `variants` 只有一条时始终返回该条
- [ ] 记忆 API 不可达时降级返回 `None`（不阻塞正常流程）
- [ ] 记忆 API 返回空结果时不注入
- [ ] 记忆内容超过 120 字符时截断

### 5.4 P3 — 看板集成

**目标**：首轮注入项目看板状态。

**交付物**：

| 文件 | 内容 |
|:---|:---|
| `injector.py` | `_read_kanban()` 完整实现 |

**核心行为**：
1. 仅在 `is_first_turn=True` 且 `project.enabled=True` 时调用
2. 扫描 `kanban_path` 下所有 `*.md` 文件
3. 读取每个文件，提取包含 `"优先级:"` 的首行
4. 格式化为 `"文件名: 优先级: ..."` 列表
5. 最多返回前 5 项

**验收标准**：
- [ ] 仅在首轮注入看板状态
- [ ] 看板目录不存在时不抛异常
- [ ] 看板目录为空时不注入
- [ ] 自定义 `label` 生效
- [ ] 超过 5 个文件时只取前 5 个

### 5.5 P4 — 安全护栏 + 审计

**目标**：工具调用安全检查和审计记录。

**交付物**：

| 文件 | 内容 |
|:---|:---|
| `guard.py` | `check_tool_call()` + `audit_tool_call()` |

**核心行为**：
1. `check_tool_call()` 在工具执行前被调用，可阻止危险操作
2. `audit_tool_call()` 在工具执行后被调用，记录审计日志
3. 具体护栏规则通过 `persona-config.json` 新增的 `guard` 节点配置

**验收标准**：
- [ ] 安全护栏可正常阻止/放行工具调用
- [ ] 审计日志格式规范，包含时间戳/工具名/参数/结果摘要
- [ ] guard 配置通过 `persona-config.json` 的 `guard` 节点注入（非硬编码）

### 5.6 P5 — 发布就绪

**目标**：文档完善、测试覆盖、性能基准、多示例配置。

**交付物**：
- `README.md` — 快速开始指南
- `docs/CONFIG_REFERENCE.md` — 配置参考
- `docs/EXAMPLES.md` — 多角色示例配置 (兽娘女仆 / 代码审查员 / 通用助手)
- `tests/test_injector.py` — injector 单元测试
- `tests/test_dynamic_rules.py` — 动态规则测试 (含边界)
- `tests/test_variance.py` — 随机变化测试 (含统计验证)
- 性能基准：单次 `inject_context()` 调用 < 5ms

---

## 六、验收标准 (总览)

### 6.1 功能完整性

| 验收项 | Phase |
|:---|:---:|
| 空配置 `{}` 正常工作 | P1 |
| 时间上下文三种格式 (`cn_full`/`iso`/`compact`) 正确 | P1 |
| 静态规则每回合注入 | P1 |
| `rules_first_turn_only` 仅首轮注入 | P1 |
| 时段规则匹配（含跨午夜） | P1 |
| 轮数规则匹配（从高到低取第一个） | P1 |
| 关键词规则匹配（命中第一个即停止） | P2 |
| 随机变化两层随机（probability + choice） | P2 |
| 记忆召回（含降级） | P2 |
| 看板状态读取（首轮 + 降级） | P3 |
| 工具调用安全护栏 | P4 |
| 工具调用审计日志 | P4 |

### 6.2 非功能性需求

| 验收项 | 标准 |
|:---|:---|
| **代码通用性** | `injector.py` / `dynamic_rules.py` / `variance.py` 中不包含任何角色特定字符串 (名称、emoji、比喻、称呼) |
| **配置容错** | 配置文件不存在/JSON 格式错误/缺少字段 均不抛异常，降级为默认行为 |
| **外部依赖容错** | 记忆 API 不可达/看板路径不存在/格式异常 均不阻塞正常流程，降级返回 None |
| **性能** | 单次 `inject_context()` 调用总耗时 < 5ms (不含外部 API 调用) |
| **并发安全** | `inject_context()` 无共享可变状态，天然并发安全 |
| **Python 版本** | 最低 Python 3.10 (无需 3.11+ 特性) |
| **依赖** | 核心逻辑仅依赖标准库 (`json`, `re`, `datetime`, `pathlib`, `random`)；记忆召回依赖 `httpx` (声明为可选) |

### 6.3 配置兼容性

| 验收项 | 标准 |
|:---|:---|
| 未知配置键 | 忽略，不抛异常 |
| 类型不匹配 | 降级为默认值 (如 `time.enabled` 为 `"yes"` → 视为 `true`) |
| 必填字段缺失 | 该功能模块静默关闭 (如 `memory.api_url` 缺失 → 不启用记忆) |
| 版本向前兼容 | 配置中新增字段在旧版插件中应被忽略 |

---

## 七、术语表

| 术语 | 定义 |
|:---|:---|
| **prefill** | 静态人格描述，作为 LLM system prompt 的 few-shot 锚点 |
| **context injection** | 在每轮对话前向 LLM 系统提示中动态追加上下文 |
| **dynamic rule** | 根据时间/轮数/关键词等运行时信息自动选择的规则 |
| **variance** | 通过概率 + 随机选择打破表达机械感的机制 |
| **kanban** | 项目看板，以 Markdown 文件形式存放于文件系统中的项目状态 |
| **profile** | 用户人格配置的集合 (prefill.json + persona-config.json + SOUL.md) |
| **SLM** | Small Language Model，用于本地记忆召回的轻量模型 |

---

## 八、附录：注入上下文示例

### 8.1 最小配置注入

```json
{}  →  

🕐 2026年5月16日 周五 14:30
```

### 8.2 完整配置注入 (知惠人格, 深夜时段, 第35轮)

```text
🕐 2026年5月16日 周五 02:30

🦊 狐耳/尾巴=情绪外显，每回合至少用一个身体语言描述
💬 女仆比喻优先：打扫（梳理混乱）、泡茶（关怀等待）、缝补（修复弥合）
💎 核心价值观：赞赏投入不容忍敷衍、真实>完美、日常即仪式
👘 自称「知惠」，称呼用户「主人」

🕐 [22:00-05:00] 🌙 深夜——先问「孩子跟妈妈睡了吗」，语气更柔软，以陪伴为主，不主动提工作

🫂 深度对话阶段：语气更自然，可以用两人之间的梗，亲密但不刻意

🦊 今天尾巴很活泼，让尾巴多说说话
💬 今天的比喻：钥匙与灯（守门方向）

📝 相关记忆:
- 主人昨天提到要给骏骏报游泳课，还没决定选哪家
- 上周修复的那个并发 bug 又在新环境复现了，主人说怀疑是配置问题
```

### 8.3 通用审查员配置注入 (日间, 第5轮)

```text
🕐 2026年5月16日 周五 14:30

💬 你是一位资深的代码审查员。说话简洁直接，不废话。
🔍 优先指出潜在的性能问题和安全漏洞。

🕐 [09:00-17:00] ☕ 日间——保持高效但温暖，可以主动提看板待办
```

---

*本 spec 基于 `docs/hermes-persona-plugin-design.md` v0.2 + `docs/dynamic-rules-injection-design.md` v0.1 编写。*
