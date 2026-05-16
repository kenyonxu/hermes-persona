# hermes-persona 配置参考

> 完整 `persona-config.json` 配置项说明——类型、默认值、描述、示例

---

## 配置结构概览

```json
{
  "hermes-persona": {
    "time": { ... },
    "context": {
      "rules": [ ... ],
      "rules_first_turn_only": [ ... ],
      "dynamic": {
        "time_slots": { ... },
        "turn_stage": { ... },
        "keywords": { ... }
      }
    },
    "variance": { ... },
    "memory": { ... },
    "project": { ... },
    "guard": { ... }
  }
}
```

所有配置均位于 `"hermes-persona"` 键下。空配置 `{}` 即可正常工作。

---

## 1. `time` — 时间注入

控制每轮对话前注入的当前时间信息。

| 字段 | 类型 | 默认值 | 描述 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `true` | 是否注入时间上下文。关闭后不再显示时间。 |
| `format` | `string` | `"cn_full"` | 时间格式。可选值见下方。 |

### `format` 取值

| 值 | 示例输出 | 说明 |
|:---|:---|:---|
| `"cn_full"` | `🕐 2026年5月16日 周五 14:30` | 中文完整格式（默认） |
| `"iso"` | `🕐 2026-05-16T14:30:00` | ISO 8601 格式 |
| `"compact"` | `🕐 05/16 14:30` | 紧凑数字格式 |

> 未知 format 值自动降级为 `"cn_full"`。

### 示例

```json
{
  "hermes-persona": {
    "time": {
      "enabled": true,
      "format": "cn_full"
    }
  }
}
```

关闭时间注入：

```json
{
  "hermes-persona": {
    "time": {
      "enabled": false
    }
  }
}
```

---

## 2. `context` — 上下文规则

控制每轮注入的人格规则，包含静态和动态两个子维度。

### 2.1 `context.rules` — 静态规则

| 字段 | 类型 | 默认值 | 描述 |
|:---|:---|:---|:---|
| `rules` | `string[]` | `[]` | 每回合都注入的静态人格规则。始终追加到上下文末尾。 |

### 2.2 `context.rules_first_turn_only` — 首轮专属规则

| 字段 | 类型 | 默认值 | 描述 |
|:---|:---|:---|:---|
| `rules_first_turn_only` | `string[]` | `[]` | 仅在会话首轮（`is_first_turn=true`）注入的规则。适合开场寒暄等一次性提示。 |

### 2.3 `context.dynamic` — 动态规则

根据运行时条件（时间、轮数、关键词）自动选择的规则。

#### 2.3.1 `time_slots` — 时段规则

| 字段 | 类型 | 默认值 | 描述 |
|:---|:---|:---|:---|
| `time_slots` | `object` | `{}` | 时段规则映射。key 为 `"HH:MM-HH:MM"` 格式的时段范围，value 为该时段注入的规则列表。支持跨午夜区间。 |

**匹配规则**：当前时间处于 `[start, end)` 区间内时命中。对于跨午夜区间（如 `"22:00-05:00"`），使用 `now >= start OR now < end` 逻辑。

**注入格式**：`🕐 [时段范围] 规则内容`

**示例**：

```json
{
  "time_slots": {
    "22:00-05:00": [
      "深夜时段，回复更加温柔安静",
      "别忘了提醒用户早点休息"
    ],
    "09:00-17:00": [
      "工作时间，回复应保持专业高效"
    ]
  }
}
```

若当前时间为 `02:30`，注入：
```
🕐 [22:00-05:00] 深夜时段，回复更加温柔安静
🕐 [22:00-05:00] 别忘了提醒用户早点休息
```

#### 2.3.2 `turn_stage` — 轮数规则

| 字段 | 类型 | 默认值 | 描述 |
|:---|:---|:---|:---|
| `turn_stage` | `object` | `{}` | 轮数规则映射。支持两个维度的 key：`"first_turn"` 和 `"after_N"`。 |

| Key | 匹配条件 | 说明 |
|:---|:---|:---|
| `"first_turn"` | `is_first_turn=true` | 会话首轮注入 |
| `"after_N"` | `turn_count >= N` | 第 N 轮起注入（N 为整数，如 `"after_10"`） |

**匹配规则**：
- `first_turn` 在首轮时注入
- `after_N` 按阈值从高到低匹配，取第一个满足 `turn_count >= N` 的规则

> `turn_count = len(conversation_history) // 2`，即用户和 Agent 之间的对话轮数。

**示例**：

```json
{
  "turn_stage": {
    "first_turn": ["首次交流，建立友好的对话氛围"],
    "after_10": ["对话已进行一段时间，保持上下文连贯"],
    "after_30": ["这是一个较长的对话，适时总结和确认"]
  }
}
```

- 首轮：注入 `"first_turn"` 规则
- 第 15 轮：注入 `"after_10"` 规则（>=10 但 <30）
- 第 35 轮：注入 `"after_30"` 规则（>=30 优先于 >=10）

#### 2.3.3 `keywords` — 关键词规则

| 字段 | 类型 | 默认值 | 描述 |
|:---|:---|:---|:---|
| `keywords` | `object` | `{}` | 关键词规则映射。key 为正则表达式模式，value 为命中后注入的规则。按配置顺序匹配，命中第一个即停止。 |

**注入格式**：`💬 [正则模式] 规则内容`

**示例**：

```json
{
  "keywords": {
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

用户消息 "系统坏了怎么办" → 命中第一个模式 → 注入两条规则。

---

## 3. `variance` — 随机表达变化

为每轮对话随机添加表达变化，打破机械感。

| 字段 | 类型 | 默认值 | 描述 |
|:---|:---|:---|:---|
| `variance` | `object` | `{}` | 随机变化维度映射。key 为维度名称，value 为包含 `probability` 和 `variants` 的对象。 |

### 维度字段

| 字段 | 类型 | 必填 | 描述 |
|:---|:---|:---|:---|
| `probability` | `number` | 是 | 本维度每回合出现的概率，取值范围 `0.0` ~ `1.0` |
| `variants` | `string[]` | 是 | 表达变体列表。命中后从列表中随机选择一条。 |

**随机机制**（两层随机）：
1. **出现概率**：`random.random() < probability` 决定本回合是否使用该维度
2. **变体选择**：从 `variants` 中 `random.choice` 选取一条

### 示例

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
        "今天的意象：编织与缝合",
        "今天的画面：细雨落在窗台"
      ]
    }
  }
}
```

每回合平均注入 1-2 条随机变体。

---

## 4. `memory` — 记忆召回

从外部记忆 API 召回与当前对话相关的记忆。

| 字段 | 类型 | 默认值 | 描述 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | 是否启用记忆召回。 |
| `api_url` | `string` | `""` | 记忆 API 端点 URL。`enabled=true` 时必填。 |
| `max_results` | `integer` | `3` | 每次召回的最大条数，范围 1~20。 |

**API 协议**：

插件以用户消息为 query，向 `api_url` 发送 POST 请求：

```json
// Request
{"query": "用户消息文本", "limit": 3}

// Expected Response
{"results": ["记忆片段1", "记忆片段2", ...]}
```

**注入格式**：
```
📝 相关记忆:
- 记忆片段1
- 记忆片段2
```

**降级行为**：
- `httpx` 不可用时 → 静默跳过
- API 不可达或超时（3s）时 → 静默跳过
- API 返回非 200 状态码 → 静默跳过
- 每条记忆截断至 120 字符

### 示例

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

## 5. `project` — 项目看板

在首轮对话中注入项目看板状态。

| 字段 | 类型 | 默认值 | 描述 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | 是否注入项目看板状态。 |
| `kanban_path` | `string` | `""` | 看板目录的绝对路径。`enabled=true` 时必填。 |
| `label` | `string` | `"📋 项目状态:"` | 注入时的标题标签。 |

**读取逻辑**：
1. 仅在 `is_first_turn=true` 时调用
2. 扫描 `kanban_path` 下所有 `*.md` 文件
3. 读取每个文件，提取包含 `"优先级:"` 的首行
4. 格式化为 `"- {文件名}: {优先级行}"`，最多 5 项

**降级行为**：
- 目录不存在 → 静默跳过
- 目录为空 / 无 `.md` 文件 → 静默跳过
- 文件读取失败 → 跳过该文件，继续处理其他文件

### 示例

```json
{
  "project": {
    "enabled": true,
    "kanban_path": "/home/user/projects/my-app/kanban",
    "label": "📋 当前任务:"
  }
}
```

首轮注入效果：
```
📋 当前任务:
- add-auth: 优先级: P0 🔴
- fix-login: 优先级: P1 🟡
- refactor-db: 优先级: P2 🟢
```

---

## 6. `guard` — 安全护栏

工具调用前的安全检查与调用后的审计日志。

### 6.1 顶层字段

| 字段 | 类型 | 默认值 | 描述 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | 是否启用安全护栏。关闭时所有工具调用直接放行。 |
| `rules` | `object` | `{}` | 护栏规则配置。 |
| `audit` | `object` | `{}` | 审计日志配置。 |

### 6.2 `rules` — 护栏规则

#### `rules.blocked` — 阻止列表

| 字段 | 类型 | 默认值 | 描述 |
|:---|:---|:---|:---|
| `blocked` | `array` | `[]` | 阻止规则列表。匹配到的工具调用将被直接阻止。 |

每条规则包含：

| 字段 | 类型 | 描述 |
|:---|:---|:---|
| `pattern` | `string` | 正则表达式，匹配工具名称 |
| `reason` | `string` | 阻止原因说明 |

匹配后返回：`{"blocked": true, "reason": "..."}`

#### `rules.require_confirmation` — 确认列表

| 字段 | 类型 | 默认值 | 描述 |
|:---|:---|:---|:---|
| `require_confirmation` | `array` | `[]` | 需确认规则列表。匹配到的工具调用将触发确认提示，但不阻止。 |

每条规则结构与 `blocked` 相同。匹配后返回：`{"require_confirmation": true, "reason": "..."}`

> **匹配优先级**：`blocked` 规则优先于 `require_confirmation` 规则。即先检查阻止列表，未匹配时才检查确认列表。

### 6.3 `audit` — 审计日志

| 字段 | 类型 | 默认值 | 描述 |
|:---|:---|:---|:---|
| `enabled` | `boolean` | `false` | 是否启用审计日志。 |
| `log_path` | `string` | `""` | 日志文件路径。支持 `~` 展开。 |

**日志格式**：
```
[ISO时间戳] 工具名 | args: 参数摘要 | result: 结果摘要
```

参数和结果均截断至 200 字符。日志以追加模式写入，目录不存在时自动创建。

### 示例

```json
{
  "guard": {
    "enabled": true,
    "rules": {
      "blocked": [
        {"pattern": "rm\\s", "reason": "文件删除操作已阻止"},
        {"pattern": "DROP\\s", "reason": "数据库删除操作已阻止"},
        {"pattern": "git\\s+push\\s+.*--force", "reason": "禁止强制推送"}
      ],
      "require_confirmation": [
        {"pattern": "git\\s+push", "reason": "代码推送需确认"},
        {"pattern": "Write", "reason": "文件写入需确认"}
      ]
    },
    "audit": {
      "enabled": true,
      "log_path": "~/.hermes/logs/persona-audit.log"
    }
  }
}
```

---

## 7. 规则注入顺序

每回合最终上下文按以下固定顺序拼接（不可更改）：

```
最终 context =
  time_context()                          # 1. 时间注入
  + context.rules                         # 2. 静态规则（每回合）
  + (if first_turn) rules_first_turn_only # 3. 首轮专属规则
  + dynamic.time_slots[当前时段]            # 4. 时段动态规则
  + dynamic.turn_stage[当前轮数]            # 5. 轮数动态规则
  + dynamic.keywords[匹配到的模式]          # 6. 关键词动态规则
  + variance[随机选中的维度]                # 7. 随机表达变化
  + recall_memories()                     # 8. 记忆召回 (if enabled)
  + (if first_turn) read_kanban()         # 9. 看板状态 (if enabled, first_turn only)
```

各部分用 `\n\n`（双换行）拼接。

---

## 8. 配置兼容性

| 场景 | 行为 |
|:---|:---|
| 配置文件不存在 | 降级为空配置 `{}` |
| JSON 格式错误 | 降级为空配置 `{}` |
| 根键 `"hermes-persona"` 缺失 | 降级为空配置 `{}` |
| 字段类型不匹配 | 使用默认值（如 `"yes"` → 视为 `true`） |
| 必填字段缺失 | 该功能模块静默关闭（如 `memory.api_url` 缺失 → 不启用记忆） |
| 未知配置键 | 忽略，不报错 |
| 配置文件版本更新 | 新字段在旧版插件中忽略 |

---

## 9. 最小配置

```json
{"hermes-persona": {}}
```

等价于：时间注入开启（`cn_full` 格式）、无静态规则、无动态规则、无随机变化、无记忆召回、无看板注入、无安全护栏。

注入效果：
```
🕐 2026年5月16日 周五 14:30
```

---

## 10. 完整配置骨架

```json
{
  "hermes-persona": {
    "time": {
      "enabled": true,
      "format": "cn_full"
    },
    "context": {
      "rules": [],
      "rules_first_turn_only": [],
      "dynamic": {
        "time_slots": {},
        "turn_stage": {},
        "keywords": {}
      }
    },
    "variance": {},
    "memory": {
      "enabled": false,
      "api_url": "",
      "max_results": 3
    },
    "project": {
      "enabled": false,
      "kanban_path": "",
      "label": ""
    },
    "guard": {
      "enabled": false,
      "rules": {
        "blocked": [],
        "require_confirmation": []
      },
      "audit": {
        "enabled": false,
        "log_path": ""
      }
    }
  }
}
```
