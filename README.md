# hermes-persona

> 为 Hermes Agent 构建的通用人格上下文注入引擎——代码通用、配置驱动、开箱即用

## 项目简介

`hermes-persona` 是一个 Hermes Agent 插件，通过 `pre_llm_call` hook 在每轮 LLM 调用前动态注入人格上下文。时间感知、行为守则、场景触发、表达变化、记忆召回和看板状态被编织进系统提示——全部由 `persona-config.json` 驱动，切换角色无需改一行代码。

**核心原则**：
- **配置驱动**：所有行为由 JSON 定义，代码完全通用
- **模块独立**：每个功能可独立开关，按需组合
- **降级健壮**：配置缺失、格式错误、外部不可达等异常静默降级

---

## 快速开始

### 安装

```bash
hermes plugins install kenyonxu/hermes-persona --enable
hermes plugins list | grep persona   # 验证
```

### 最小配置

在插件目录下创建 `persona-config.json`：

```json
{
  "hermes-persona": {}
}
```

空对象即启用时间感知——Agent 每轮对话前感知当前时间。

> 💡 **热加载**：修改配置文件保存即生效，无需重启 Gateway。

---

## 配置指南

配置文件顶层始终包裹在 `"hermes-persona"` 键下。以下按功能模块逐一说明。

### 1. 模块总控开关（`modules`）

每个功能模块可独立开关。关闭的模块完全不执行。

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
      "memory": false,
      "kanban": true,
      "translate": true,
      "sources_blacklist": ["cron", "api_server", "webhook", "msgraph_webhook"]
    }
  }
}
```

**字段说明**：

| 模块 | 类型 | 说明 |
|------|------|------|
| `time` | bool | 时间感知注入 |
| `static_rules` | bool | 静态行为守则注入 |
| `dynamic.time_slots` | bool | 时段规则（深夜/早晨等） |
| `dynamic.turn_stage` | bool | 轮数阶段规则 |
| `dynamic.keyword` | bool | 关键词触发规则 |
| `variance` | bool | 随机表达变化 |
| `memory` | bool | 外部记忆召回（需 `pip install httpx`） |
| `kanban` | bool | 看板状态注入（仅首轮） |
| `translate` | bool | 注入规则转译模式（见 §9） |
| `sources_blacklist` | list | 来源过滤（见 §10） |

---

### 2. 时间感知（`time`）

每轮自动注入当前日期时间。Agent 可据此区分早晨／深夜，或问候时提及具体时间。

```json
{
  "time": {
    "enabled": true,
    "format": "cn_full"
  }
}
```

| 参数 | 值 | 输出示例 |
|------|------|----------|
| `format` | `"cn_full"` | `2026年5月22日 周五 11:30` |

> 当 `translate` 模式开启时，时间以自然语言形式拼入人格自述，而非独立注入行。

---

### 3. 静态规则（`context`）

用户自定义的行为守则，分两种通道注入：

- **`rules`**：每轮必注
- **`rules_first_turn_only`**：仅会话第一轮注入

```json
{
  "context": {
    "rules": [
      "用中文回答所有问题",
      "回答简洁，不超过200字",
      "保持友好、专业的态度"
    ],
    "rules_first_turn_only": [
      "会话开始时自动回顾最近的上下文"
    ]
  }
}
```

---

### 4. 动态规则（`dynamic`）

根据当前上下文动态选择合适的指引规则。三个子通道：

#### 4.1 时段规则（`time_slots`）

按时间段注入不同的行为指引。键为时间范围，值为指引文本数组。

```json
{
  "dynamic": {
    "time_slots": {
      "06:00-09:00": ["语气清爽，可以提昨晚的休息情况"],
      "09:00-12:00": ["保持高效但温暖的陪伴"],
      "22:00-05:00": ["语气更柔软，以陪伴为主，不主动提工作"]
    }
  }
}
```

#### 4.2 轮数阶段（`turn_stage`）

根据每日累积对话轮数自动切换阶段。键为 `after_<轮数>`，当累积轮数达到阈值时触发。

```json
{
  "dynamic": {
    "turn_stage": {
      "first_turn": ["会话开始，语气清新"],
      "after_100": ["进入深度交流阶段，语气可更自然"],
      "after_300": ["深度对话阶段：表达可更亲密，主动分享想法"]
    }
  }
}
```

- `first_turn`：仅首轮
- `after_N`：轮数 ≥ N 时触发，取最大匹配
- **非 translate 模式**：轮数 = 当前会话轮数（`会话消息数 / 2`）
- **translate 模式**：轮数 = 每日跨会话累积轮数，跨日自动归零

#### 4.3 关键词触发（`keyword`）

用户消息命中指定关键词时注入对应规则。

```json
{
  "dynamic": {
    "keyword": [
      {
        "pattern": "代码|bug|架构",
        "rules": ["切换到技术分析模式，先拆解问题再给答案"]
      },
      {
        "pattern": "累了|好累|困了",
        "rules": ["关心模式：语气更柔软，不输出密集信息"]
      }
    ]
  }
}
```

- `pattern`：正则表达式或维度名，命中后注入 `rules` 中的所有条目
- 所有匹配的维度同时返回（all-matches），不限于单条

---

### 5. 多维度表达向量（`expression_vector`）

自动追踪对话话题分布，引导 Agent 根据当前对话走向自然调节表达风格。

```json
{
  "expression_vector": {
    "enabled": true,
    "dimensions": {
      "technical": { "label": "技术讨论", "keywords_path": "keywords/technical.json", "score_rules": [1, -0.5, 2, 0.95] },
      "casual":    { "label": "闲聊放松", "keywords_path": "keywords/casual.json",    "score_rules": [1, -1, 1, 0.95] }
    },
    "reset": "session",
    "storage_path": "state/expression_vector.json"
  }
}
```

**维度配置**：

| 字段 | 说明 |
|------|------|
| `label` | 维度显示名称 |
| `keywords_path` | 关键词词表文件路径 |
| `score_rules` | `[命中加分, 未中扣分, 权重, 衰减因子]` |

- 维度数量和名称完全由用户自定
- 关键词词表为独立 JSON 文件，每个维度一个
- 分数按会话自动衰减，跨会话策略可选：`session`（每会话归零）/ `daily` / `none`

---

### 6. 固定信号检测（`fixed_signals`）

三种自动检测信号，基于消息本身而非配置规则。

#### 6.1 消息长度（`message_length`）

用户消息过短时注入简洁回应提示。

```json
{
  "fixed_signals": {
    "message_length": { "enabled": true, "threshold": 50 }
  }
}
```

#### 6.2 回复间隔（`reply_gap`）

用户长时间未回复后回归时注入欢迎提示。

```json
{
  "fixed_signals": {
    "reply_gap": { "enabled": true, "threshold_minutes": 30 }
  }
}
```

#### 6.3 每日轮数（`daily_turn_count`）

跨会话累计当日对话轮数，可设深度互动阈值。

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

- 轮数每日跨会话累积，跨日自动归零
- 非对话来源（见 §10）不参与计数

---

### 7. 随机表达变化（`variance`）

以可配置的概率随机触发变体条目。典型用途：角色特有的**肢体语言、口癖、比喻风格、口头禅**。

```json
{
  "variance": {
    "body_language": {
      "probability": 0.5,
      "variants": [
        "不自觉地摸了摸后颈——这是角色紧张时的小动作",
        "手指在桌面上轻轻敲了两下，然后停住"
      ]
    },
    "catchphrase": {
      "probability": 0.3,
      "variants": [
        "今日口头禅：那就这样吧～",
        "今日口头禅：有道理呢"
      ]
    }
  }
}
```

- `probability`：触发概率（0-1）
- `variants`：触发时随机抽取一条
- **条目应为自包含完整句**——引擎只做去前缀 pass-through，不锁死句式。作者迭代内容无需改代码

---

### 8. 安全护栏（`guard`）

工具调用前的安全检查。支持两类规则：

```json
{
  "guard": {
    "enabled": true,
    "audit": { "enabled": true, "log_path": "~/.hermes/profiles/zhihui/audit.log" },
    "rules": {
      "blocked": [
        { "pattern": "rm -rf", "reason": "递归强制删除已被阻止" }
      ],
      "require_confirmation": [
        { "pattern": "sudo", "reason": "sudo 操作需要用户确认" },
        { "pattern": "git push.*--force", "reason": "强制推送需要用户确认" }
      ]
    }
  }
}
```

- `blocked`：直接阻止，不发送给 LLM
- `require_confirmation`：阻止并提示用户确认
- `audit`：所有拦截和确认事件写入审计日志

---

### 9. 注入规则转译（`translate`）

开启后，引擎将内部规则（emoji 标记的指令）自动转译为自然语言人格自述，LLM 看到的是流畅的「自我意识」而非指令清单。

```json
{
  "modules": {
    "translate": true
  }
}
```

**效果对比**：

- 关闭时：LLM 收到 `☀️ 早晨——语气清爽` `🦊 狐耳轻轻抖动` 等分散指令
- 开启时：LLM 收到一段流畅的散文——「现在是周五上午，今天已经聊了165轮…」

转译模板：时间 + 轮数 + 状态 + 随机变化 + 行为守则 → 拼装为单一人格自述。

> 开启 translate 后，各模块不再独立输出带 emoji 标记的指令行，统一由 `_assemble_narrative()` 编织为一段自然语言段落。`turn_stage` 的轮数来源也切换为每日跨会话累积轮数（从磁盘状态文件读取），而非会话内轮数。

---

### 10. 来源过滤（`sources_blacklist`）

非对话来源（cron 定时任务、API 调用、webhook）仅注入时间，不参与轮数计数、不触发动态规则、不注入人格。

```json
{
  "modules": {
    "sources_blacklist": ["cron", "api_server", "webhook", "msgraph_webhook"]
  }
}
```

- 被过滤的来源：只收到时间上下文
- 未被过滤的来源（discord、telegram、cli 等所有即时通讯平台）：完整人格注入

---

### 11. Debug 详细模式（`debug`）

不想猜测引擎做了什么？开启 debug 后，每轮 LLM 回复末尾会追加注入全貌。

```json
{
  "modules": {
    "debug": { "enabled": true, "detail": "detailed" }
  }
}
```

| 参数 | 值 | 说明 |
|------|------|------|
| `enabled` | bool | 是否启用 |
| `detail` | `"basic"` / `"detailed"` | `detailed` 显示完整注入分解（时段、轮数、表达向量分数、固定信号、随机变化命中） |

> Debug 块通过 `transform_llm_output` hook 追加到 LLM 回复末尾，不消耗额外 token 用于 "要求 LLM 自己输出"，也无需 LLM 自觉配合。
>
> **已知限制**：`_PENDING_DEBUG_BLOCK` 使用模块级变量传递，非线程安全。单会话运行时无影响；多会话并发场景下 debug 块可能串话。

---

### 12. 国际化（`locales`）

双语文案支持，可通过 locale 文件扩展更多语言。当前内置中英文。

```json
{
  "locales": "zh"
}
```

语言包位于 `locales/` 目录。添加新语言只需新建对应 JSON 文件。

---

### 13. 项目看板注入（`kanban`）

首轮注入外部看板状态，帮助 Agent 感知项目上下文。

```json
{
  "modules": {
    "kanban": true
  },
  "project": {
    "enabled": true,
    "kanban_path": "/path/to/your/kanban/directory",
    "label": "📋 项目状态:"
  }
}
```

> 💡 仅首轮注入，后续轮次不再重复读取。

---

## 目录结构

```
plugins/hermes-persona/
├── persona-config.json          ← 用户唯一需要手改的配置文件
├── keywords/                    ← 表达向量维度关键词（用户自定）
│   └── *.json
├── locales/                     ← 多语言模板
│   ├── en.json
│   └── zh.json
├── state/                       ← 运行时自动生成（不入版本控制）
│   ├── expression_vector.json
│   └── daily_turn_count.json
└── examples/
    └── persona-config.json      ← 完整配置模板
```

---

## 常见问题

**Q: 最小配置是什么？**
A: `{"hermes-persona": {}}`——空对象即可启用时间感知。

**Q: 配置错误会不会导致 Agent 崩溃？**
A: 不会。所有异常均被捕获并静默降级，不影响 Agent 正常流程。

**Q: 如何切换角色人格？**
A: 替换 `persona-config.json` 即可，无需修改任何代码。

**Q: 配置文件放哪里？**
A: 插件目录（推荐）：`~/.hermes/profiles/<name>/plugins/hermes-persona/persona-config.json`。也兼容旧路径（profile 根目录）。

**Q: 性能如何？**
A: 单次注入 < 5ms（不含外部 API）。仅时间注入 < 1ms。

**Q: 支持哪些 Hermes 版本？**
A: 支持提供 `pre_llm_call` / `pre_tool_call` / `post_tool_call` hooks 的版本。

---

## 许可

MIT License
