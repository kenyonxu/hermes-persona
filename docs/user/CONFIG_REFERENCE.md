# hermes-persona 配置参考

> 📖 [English](../en/CONFIG_REFERENCE.md)

> 完整 `persona-config.json` 配置项说明——v1.0，覆盖全部模块

---

## 配置结构概览

```json
{
  "hermes-persona": {
    "modules": { ... },
    "time": { ... },
    "weather": { ... },
    "context": { ... },
    "dynamic": { ... },
    "expression_vector": { ... },
    "fixed_signals": { ... },
    "variance": { ... },
    "memory": { ... },
    "project": { ... },
    "guard": { ... }
  }
}
```

所有配置均位于 `"hermes-persona"` 键下。空配置 `{}` 即可正常工作。

---

## 1. `modules` — 模块总控开关

控制每个功能模块的启用/禁用。关闭的模块完全不执行。

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `time` | `boolean` | `true` | 时间上下文注入 |
| `weather` | `boolean` | `false` | 天气上下文注入（需配置 `weather.location`） |
| `static_rules` | `boolean` | `true` | 静态行为守则注入 |
| `dynamic` | `boolean` 或 `object` | `true` | 动态规则总开关。设为 `false` 关闭全部子通道。 |
| `dynamic.time_slots` | `boolean` | `true` | 时段规则子通道 |
| `dynamic.turn_stage` | `boolean` | `true` | 轮数阶段子通道 |
| `dynamic.keyword` | `boolean` | `true` | 关键词触发子通道 |
| `expression_vector` | `boolean` | `false` | 多维度表达向量（需同时开启 `expression_vector.enabled`） |
| `fixed_signals` | `boolean` | `true` | 固定信号检测（消息长度 / 回复间隔 / 每日轮数） |
| `variance` | `boolean` | `true` | 随机表达变化 |
| `memory` | `boolean` | `false` | 外部记忆召回（需 `pip install httpx`） |
| `kanban` | `boolean` | `false` | 看板状态注入（仅首轮） |
| `translate` | `boolean` | `false` | 注入规则转译模式 |
| `debug` | `boolean` 或 `object` | `false` | Debug 详细模式 |
| `sources_blacklist` | `string[]` | `[]` | 来源过滤列表 |

> `modules` 中缺失的键会自动从旧格式或默认值补全，不会因缺键导致模块静默关闭。

### 示例

```json
{
  "modules": {
    "time": true,
    "weather": false,
    "static_rules": true,
    "dynamic": { "time_slots": true, "turn_stage": false, "keyword": true },
    "expression_vector": true,
    "fixed_signals": true,
    "variance": true,
    "memory": false,
    "kanban": true,
    "translate": true,
    "debug": { "enabled": false, "detail": "detailed" },
    "sources_blacklist": ["cron", "api_server", "webhook"]
  }
}
```

---

## 2. `time` — 时间注入

控制每轮对话前注入的当前时间信息。translate 模式下时间以自然语言形式拼入人格自述。

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `true` | 是否注入时间上下文 |
| `format` | `string` | `"cn_full"` | 时间格式，可选值见下方 |

### `format` 取值

| 值 | 示例输出 | 说明 |
|:---|:---|:---|
| `"cn_full"` | `🕐 2026年5月16日 周五 14:30` | 中文完整格式（默认） |
| `"iso"` | `🕐 2026-05-16T14:30:00` | ISO 8601 |
| `"compact"` | `🕐 05/16 14:30` | 紧凑数字格式 |

未知 format 值自动降级为 `"cn_full"`。

### 示例

```json
{
  "time": {
    "enabled": true,
    "format": "cn_full"
  }
}
```

---

## weather — 天气注入

通过 Open-Meteo 免费 API 获取指定城市的实时天气，注入到每轮对话上下文。支持文件缓存减少 API 调用。

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `location` | `string` | `""` | 城市名（中文）。为空时不注入天气 |
| `detail` | `string` | `"brief"` | `"brief"` 仅温度 + 天气描述；`"full"` 含湿度 + 风力等级 |
| `cache_ttl_minutes` | `integer` | `30` | 文件缓存有效期（分钟），过期后重新调用 API |
| `label` | `string` | `"🌤"` | 直接注入模式下的前缀 emoji（translate 模式下不使用） |

### 示例

```json
{
  "weather": {
    "location": "北京",
    "detail": "brief",
    "cache_ttl_minutes": 30,
    "label": "🌤"
  }
}
```

### 缓存策略

- 缓存路径：`state/weather_cache.json`（插件目录下）
- `_should_refresh()` 统一决策：缓存不存在 / TTL 过期 / location 变更 / fetched_at 损坏 → 重新调用 API
- geocoding 坐标可复用：同一城市无需重复查询
- API 失败回退：有旧缓存则返回过期数据；无缓存则静默跳过（fail-open）

---

## 3. `context` — 静态规则

用户自定义的行为守则，分两种通道注入。

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `rules` | `string[]` | `[]` | 每回合都注入的静态规则 |
| `rules_first_turn_only` | `string[]` | `[]` | 仅会话首轮注入的规则 |

### 示例

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

## 4. `dynamic` — 动态规则

根据运行时条件（时间、轮数、关键词）自动选择的行为指引。三个子通道独立可控。

### 4.1 `time_slots` — 时段规则

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `time_slots` | `object` | `{}` | 键为 `"HH:MM-HH:MM"` 格式的时段范围，值为规则文本数组。支持跨午夜区间。 |

**匹配规则**：当前时间落入 `[start, end)` 区间时命中。跨午夜区间（如 `"22:00-05:00"`）使用 `now >= start OR now < end` 逻辑。每天第一个匹配的时段生效。

**注入格式**：`🕐 [时段范围] 规则内容`

```json
{
  "time_slots": {
    "22:00-05:00": [
      "深夜时段，回复更加温柔安静"
    ],
    "09:00-17:00": [
      "工作时间，回复应保持专业高效"
    ]
  }
}
```

### 4.2 `turn_stage` — 轮数阶段

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `turn_stage` | `object` | `{}` | 键为 `"first_turn"` 或 `"after_N"`（N 为整数），值为规则文本数组。 |

| Key | 匹配条件 | 说明 |
|:---|:---|:---|
| `"first_turn"` | `is_first_turn=true` | 会话首轮 |
| `"after_N"` | 轮数 ≥ N | 取最大匹配（最高阈值优先） |

**轮数来源**：
- 非 translate 模式：`会话消息数 / 2`
- translate 模式：每日跨会话累积轮数（跨日自动归零）

```json
{
  "turn_stage": {
    "first_turn": ["首次交流，建立友好的对话氛围"],
    "after_10": ["对话已进行一段时间，保持上下文连贯"],
    "after_30": ["深度对话阶段，适时总结和确认"]
  }
}
```

### 4.3 `keyword` — 关键词触发

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `keyword` | `object` | `{}` | 键为正则表达式或维度名，值为命中后注入的规则数组。 |

所有匹配的维度同时返回（all-matches），不限于单条。用户消息命中越多维度，注入的规则越多。

**注入格式**：`💬 [正则/维度名] 规则内容`

```json
{
  "keyword": {
    "报错|bug|error|崩溃|挂了": [
      "检测到用户遇到了问题，优先排查而非解释",
      "先给临时方案，再分析根因"
    ],
    "哈哈|开心|笑|乐": [
      "用户情绪积极，保持轻松氛围"
    ]
  }
}
```

---

## 5. `expression_vector` — 多维度表达向量

自动追踪对话话题分布，引导 Agent 根据当前对话走向自然调节表达风格。

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | 是否启用（需与 `modules.expression_vector` 同时为 true） |
| `dimensions` | `object` | `{}` | 维度定义映射。键为维度名，值为维度配置对象。 |
| `reset` | `string` | `"session"` | 重置策略：`"session"` / `"daily"` / `"none"` |
| `storage_path` | `string` | `""` | 状态文件路径。空字符串使用默认路径。 |

### 维度配置字段

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `label` | `string` | 维度显示名称 |
| `keywords_path` | `string` | 关键词词表 JSON 文件路径（相对于插件目录） |
| `keywords` | `string[]` | 或直接内联关键词列表（与 `keywords_path` 二选一） |
| `score_rules` | `number[4]` | `[命中加分, 未中扣分, 权重, 衰减因子]` |

```json
{
  "expression_vector": {
    "enabled": true,
    "dimensions": {
      "work": {
        "label": "工作",
        "keywords_path": "keywords/work.json",
        "score_rules": [1, -0.5, 2, 0.95]
      },
      "casual": {
        "label": "闲聊",
        "keywords_path": "keywords/casual.json",
        "score_rules": [1, -1, 1, 0.95]
      }
    },
    "reset": "session",
    "storage_path": "state/expression_vector.json"
  }
}
```

> 维度数量和名称完全由用户自定，每个维度对应一个独立的关键词词表文件。

---

## 6. `fixed_signals` — 固定信号检测

三种基于消息特征的自动检测，不依赖配置规则。

### 6.1 `message_length` — 消息长度

用户消息过短时注入简洁回应提示。

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | 是否启用 |
| `threshold` | `integer` | `50` | 字符数阈值。消息长度 < threshold 时触发。 |

### 6.2 `reply_gap` — 回复间隔

用户长时间未回复后回归时注入欢迎提示。

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | 是否启用 |
| `threshold_minutes` | `integer` | `30` | 间隔分钟阈值 |
| `storage_path` | `string` | `""` | 最后回复时间文件路径 |

### 6.3 `daily_turn_count` — 每日轮数

跨会话累积当日对话轮数，可设深度互动阈值。

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | 是否启用 |
| `thresholds` | `object` | `{}` | 阈值映射。键为标签名，值为轮数阈值。 |
| `storage_path` | `string` | `""` | 轮数状态文件路径 |

> 轮数每日跨会话累积，跨日自动归零。非对话来源（见 §11）不参与计数。

```json
{
  "fixed_signals": {
    "message_length": { "enabled": true, "threshold": 50 },
    "reply_gap": { "enabled": true, "threshold_minutes": 30 },
    "daily_turn_count": {
      "enabled": true,
      "thresholds": { "morning": 10, "familiar": 50 }
    }
  }
}
```

---

## 7. `variance` — 随机表达变化

以可配置的概率随机触发变体条目。典型用途：角色特有的肢体语言、口癖、比喻风格。

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `<category>` | `object` | — | 任意命名的维度，包含 `probability` 和 `variants`。 |

### 维度字段

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `probability` | `number` | 是 | 触发概率，取值范围 `0.0` ~ `1.0` |
| `variants` | `string[]` | 是 | 变体列表。触发时随机抽取一条。 |

**随机机制**（两层）：
1. `random() < probability` 决定本回合是否触发该维度
2. 触发后从 `variants` 中 `random.choice` 选取一条

```json
{
  "variance": {
    "body_language": {
      "probability": 0.6,
      "variants": [
        "今天尾巴很活泼，让尾巴多说说话",
        "耳朵轻轻抖动了一下",
        "尾巴缓缓摆动，正在认真思考"
      ]
    },
    "metaphor": {
      "probability": 0.3,
      "variants": [
        "今天的比喻：钥匙与灯",
        "今天的意象：编织与缝合"
      ]
    }
  }
}
```

---

## 8. `memory` — 记忆召回

从外部记忆 API 召回与当前对话相关的记忆。需要 `pip install httpx`。

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | 是否启用 |
| `api_url` | `string` | `""` | 记忆 API 端点 URL |
| `max_results` | `integer` | `3` | 每次召回最大条数 |
| `max_length` | `integer` | `120` | 每条记忆截断至该长度（字符） |

**API 协议**：POST 请求，body 为 `{"query": "...", "limit": N}`，期望响应 `{"results": [...]}`。

**降级行为**：httpx 不可用 / API 不可达 / 超时（3s）/ 非 200 状态 → 静默跳过。

```json
{
  "memory": {
    "enabled": true,
    "api_url": "http://127.0.0.1:8765/api/recall",
    "max_results": 5
  }
}
```

---

## 9. `project` — 项目看板

首轮注入外部看板状态，帮助 Agent 感知项目上下文。

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | 是否启用 |
| `kanban_path` | `string` | `""` | 看板目录的绝对路径 |
| `label` | `string` | `"📋 项目状态:"` | 注入时的标题标签 |

**读取逻辑**：仅在首轮调用，扫描 `kanban_path` 下所有 `*.md` 文件，提取含 `"优先级:"` 的首行，最多 5 项。

```json
{
  "project": {
    "enabled": true,
    "kanban_path": "/home/user/projects/my-app/kanban",
    "label": "📋 当前任务:"
  }
}
```

---

## 10. `guard` — 安全护栏

工具调用前的安全检查与调用后的审计日志。

### 10.1 顶层字段

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | 是否启用安全护栏 |
| `rules` | `object` | `{}` | 护栏规则配置 |
| `audit` | `object` | `{}` | 审计日志配置 |

### 10.2 `rules.blocked` — 阻止列表

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `pattern` | `string` | 正则表达式，匹配工具名称 |
| `reason` | `string` | 阻止原因说明 |

匹配后返回 `{"blocked": true, "reason": "..."}`。

### 10.3 `rules.require_confirmation` — 确认列表

结构同 `blocked`。匹配后返回 `{"require_confirmation": true, "reason": "..."}`。

> `blocked` 优先于 `require_confirmation` 匹配。

### 10.4 `audit` — 审计日志

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | 是否启用审计日志 |
| `log_path` | `string` | `""` | 日志文件路径，支持 `~` 展开 |

```json
{
  "guard": {
    "enabled": true,
    "audit": { "enabled": true, "log_path": "~/.hermes/logs/persona-audit.log" },
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

---

## 11. `sources_blacklist` — 来源过滤

非对话来源（cron 定时任务、API 调用、webhook）仅注入时间，不参与轮数计数、不触发动态规则、不注入人格。

在 `modules` 中配置：

```json
{
  "modules": {
    "sources_blacklist": ["cron", "api_server", "webhook", "msgraph_webhook"]
  }
}
```

---

## 12. `translate` — 注入规则转译

开启后，引擎将内部规则（emoji 标记的指令）自动转译为自然语言人格自述，LLM 看到的是流畅的「自我意识」而非指令清单。

在 `modules` 中配置：

```json
{
  "modules": {
    "translate": true
  }
}
```

**效果**：各模块不再独立输出带 emoji 标记的指令行，统一由 `_assemble_narrative()` 编织为一段自然语言段落。`turn_stage` 的轮数来源也切换为每日跨会话累积轮数。

---

## 13. `debug` — Debug 详细模式

每轮 LLM 回复末尾追加注入全貌，帮助排查配置问题。

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | 是否启用 |
| `detail` | `string` | `"compact"` | `"compact"`（摘要统计）或 `"detailed"`（逐模块分解） |

通过 `transform_llm_output` hook 追加到 LLM 回复末尾，不消耗额外 LLM token。

> 已知限制：debug 块使用模块级变量传递，非线程安全。单会话运行时无影响。

在 `modules` 中配置：

```json
{
  "modules": {
    "debug": { "enabled": true, "detail": "detailed" }
  }
}
```

---

## 14. `locales` — 国际化

双语文案支持，可通过 locale 文件扩展更多语言。

| 字段 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `language` | `string` | `"auto"` | `"zh"` / `"en"` / `"auto"`（根据 time.format 推断） |

```json
{
  "language": "zh"
}
```

语言包位于 `locales/` 目录。添加新语言只需新建对应 JSON 文件。

---

## 15. 规则注入顺序

每回合最终上下文按以下固定顺序拼接（不可更改）：

```
① time             — 时间上下文（translate 模式时跳过独立行）
①b weather         — 天气注入（translate 模式时融入叙事）
② static_rules     — 静态规则（每轮 + 首轮专属）
③ dynamic          — 动态规则（time_slots → turn_stage → keyword）
④a fixed_signals   — 固定信号（消息长度 → 回复间隔 → 每日轮数）
④b expression_vector — 多维度表达向量
⑤ variance         — 随机表达变化
⑥ memory           — 记忆召回（若启用）
⑦ kanban           — 看板状态（若启用，仅首轮）
⑧ translate        — 转译为散文叙事（代替以上模块输出）
⑨ debug            — Debug 摘要（追加到 LLM 回复末尾）
```

各部分用 `\n\n`（双换行）拼接。

---

## 16. 配置兼容性

| 场景 | 行为 |
|:---|:---|
| 配置文件不存在 | 降级为空配置 `{}` |
| JSON 格式错误 | 降级为空配置 `{}` |
| 根键 `"hermes-persona"` 缺失 | 降级为空配置 `{}` |
| `modules` 缺键 | 从旧格式 legacy_path 或 registry default 补全 |
| 未知配置键 | 忽略，不报错 |
| 必填字段缺失 | 该功能静默关闭 |

---

## 17. 最小配置

```json
{"hermes-persona": {}}
```

等价于：时间注入开启（`cn_full` 格式）、静态规则/动态规则/随机变化默认开启、表达向量/记忆/看板/转译默认关闭。

注入效果：
```
🕐 2026年5月16日 周五 14:30
```
