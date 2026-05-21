# SPEC-006: 表达向量维度可自定义 + 关键词匹配引擎升级

> 创建日期: 2026-05-21
> 来源: Brainstorming 05-21 上午 · 主人+知惠协作设计
> 状态: 设计完成，待主人审查

---

## 1. 概述

### 1.1 目标

将表达向量从**硬编码六维**升级为**用户可自定义维度**的通用引擎，同时将关键词匹配从裸子串匹配升级为**中文分词 + 同义词展开 + 否定检测**的精确匹配流水线。

### 1.2 动机

- 当前六维关键词硬编码在 `expression_vector.py` 中，用户无法增删维度和自定义关键词
- `persona-config.json` 中关键词列表过长（150+ 词），文件臃肿不易编辑
- `_count_keyword()` 使用裸 `.count()` 子串匹配——`"process".count("PR") → 1` 误命中
- 没有同义词支持——`"推送"` 无法匹配 `"push"`
- 没有否定处理——`"不想抱抱"` 被当作 intimacy 命中

### 1.3 范围

本次 SPEC 覆盖：

| 模块 | 内容 |
|------|------|
| **配置层** | dimensions 自定义格式、关键词外置文件、同义词外置文件 |
| **引擎层** | 匹配流水线重构（分词→同义词→否定→精确匹配） |
| **加载层** | 注册时加载 + 热加载命令 |
| **命令层** | 斜杠命令 `/hermes-persona reload keywords` |

不覆盖：NL 转义（数值→自然语言）、Embedding 语义兜底（L4）。

---

## 2. 配置设计

### 2.1 dimensions 格式

`persona-config.json` → `expression_vector.dimensions` 改为 dict of dict：

```json
"expression_vector": {
  "dimensions": {
    "work": {
      "label": "工作投入",
      "keywords_path": "keywords/work.json",
      "score_rules": [1, -0.5, 1, 0.95]
    },
    "intimacy": {
      "label": "亲密温度",
      "keywords": ["抱抱", "亲亲", "贴贴", "蹭蹭"],
      "score_rules": [1, -0.15, 3, 0.95]
    }
  },
  "synonyms_path": "keywords/synonyms.json",
  "reset": "session",
  "storage_path": "..."
}
```

**要点：**
- `dimensions` 的 key 为维度名（如 `work`、`intimacy`），value 为维度配置对象
- 每个维度必含 `label`（用于未来 NL 转义）和 `score_rules`
- 关键词支持两种写法：`keywords`（内联数组）或 `keywords_path`（外置文件路径）
- `synonyms_path` 指向同义词映射文件，加载时翻转构建双向查找
- 维度数量由用户决定，引擎遍历 `dimensions` dict 自动识别

### 2.2 关键词文件

`keywords/work.json`：

```json
{
  "keywords": [
    "代码", "架构", "Bug", "Debug", "PR", "测试", "重构",
    "修复", "commit", "push", "部署", "review", "git",
    "分支", "合并", "看板", "task", "CC", "工蜂", "子代理",
    "审查", "方案", "设计", "SPEC", "PLAN", "实现",
    "terminal", "ssh", "配置", "plugin", "hermes-persona"
  ]
}
```

格式：纯 JSON 数组，无嵌套结构。

### 2.3 同义词文件

`keywords/synonyms.json`：

```json
{
  "推送": "push",
  "PR": "pull request",
  "嗦粉": "吃饭",
  "世缘图": "世缘录"
}
```

格式：`"原文 → 目标词"` 映射。加载后翻转，使同义词也能被逆向命中（例如 `"push"` 也能匹配到 work 维度的 `"推送"`）。

---

## 3. 匹配引擎设计

### 3.1 流水线

```
用户消息
  │
  ▼
┌─────────────┐
│ 预处理层     │ ① jieba 分词
│              │ ② synonyms 展开（同义词映射）
│              │ ③ 否定检测（向前扫 N 字内的否定词）
└──────┬──────┘
       │ tokens[] + 否定区间[]
       ▼
┌─────────────┐
│ 匹配层       │ 对每个维度：
│              │   遍历 keywords
│              │   精确匹配 token（非子串）
│              │   检查是否在否定区间内
│              │   命中 → +score
└──────┬──────┘
       │
       ▼
  命中计数 → update() 加减分
```

### 3.2 关键改进对比

| 现在 | 改后 |
|------|------|
| `"process".count("PR")` → 误命中 | jieba 分词 → `["process"]`，`"PR"` 不匹配 |
| `"不想抱抱"` → +intimacy | 否定检测 → 跳过 |
| `"推送"` → 不命中 `"push"` | synonym 展开 → 命中 |
| `.count()` 子串匹配 | 分词后精确 token 匹配 |

### 3.3 否定检测规则

- 否定词表：`不` / `没` / `别` / `无`
- 扫描窗口：关键词前 3 个 token
- 逻辑：若否定词出现在窗口内 → 该命中不计分

### 3.4 同义词展开

- 加载时构建双向映射：`src→dst` 和 `dst→src`
- 预处理阶段：对于每个 token，若在 synonym 映射中，同时尝试匹配原词和目标词
- 例如 `"推送"` → 同时命中 work 维度的 `"push"` 和 `"推送"`

---

## 4. 加载逻辑

### 4.1 加载时机

```
register() → _load_config()
  └── (config 加载由 injector 完成，不涉及关键词文件)
  
inject_context() → _ExpressionVector(cfg, profile_path)
  └── _ExpressionVector.__init__()
      ├── 遍历 dimensions：
      │   ├── 有 keywords_path → 读外置 JSON 文件
      │   ├── 有 keywords → 用内联列表
      │   └── 都没有 → 该维度空关键词（不匹配任何内容）
      ├── 读 synonyms_path（dimensions 同级）→ 构建双向映射
      └── score_rules 优先读维度的内联字段，回退读顶层 score_rules
```

**设计决策（C1）：不引入独立的模块级缓存层。**

关键词的加载由 `_ExpressionVector.__init__()` 直接完成：
1. 每个维度配置中的 `keywords_path` 在构造函数内部解析并读取 JSON 文件
2. 内联 `keywords` 直接使用
3. 同义词映射 `synonyms.json` 也在构造函数内部读取
4. `_ExpressionVector` 实例持有自己的关键词副本

热加载时，`/hermes-persona reload keywords` 命令**重新构造 `_ExpressionVector` 实例**，新实例自动读取最新的关键词文件。无需模块级缓存层。

**理由：**
- 避免全局状态（`_KEYWORD_CACHE`）
- 构造函数直接管理自己的依赖（自包含）
- 热加载通过重新实例化自然实现
- `update()` 调用频繁（每轮），而构造函数只调用一次（每轮一次），磁盘 I/O 开销可接受

### 4.2 热加载

斜杠命令 `/hermes-persona reload keywords` 触发：
1. 重新执行上述加载流程
2. 刷新 `_KEYWORD_CACHE`
3. 下一次 `update()` 调用自动使用新关键词
4. 无需重启 Hermes

### 4.3 回退机制

| 情况 | 行为 |
|------|------|
| `keywords_path` 文件不存在 | 降级用内联 `keywords` |
| `keywords_path` + `keywords` 都没有 | 该维度退场（空关键词） |
| `synonyms_path` 文件不存在 | 空映射，不影响匹配 |
| JSON 解析失败 | 降级同上 |
| jieba 不可用 | 回退空格分词（英文）或单字分词（中文） |

---

## 5. 斜杠命令

### 5.1 注册

在 `__init__.py` → `register()` 中注册：

```python
ctx.register_command(
    name="hermes-persona",
    handler=_handle_persona_command,
    description="管理 hermes-persona 插件",
    args_hint="<reload|keywords|status> [维度]"
)
```

### 5.2 命令列表

| 命令 | 功能 |
|------|------|
| `/hermes-persona reload keywords` | 热加载关键词和同义词表 |
| `/hermes-persona keywords <维度>` | 列出某维度的当前关键词 |
| `/hermes-persona status` | 查看表达向量当前状态（六维值 + 加载信息） |

---

## 6. 兼容性

- **向后兼容**：若 `dimensions` 仍是旧格式（dict of list），自动迁移为 dict of dict
- **score_rules 迁移**：`score_rules` 优先在维度内部读取 `dimensions[dim_name]["score_rules"]`，读不到时回退顶层 `expression_vector.score_rules[dim_name]`。两种格式同时存在时内部字段优先
- **维度顺序无关**：引擎按 `dimensions` dict 的 key 顺序遍历，不依赖固定六维
- **现有向量历史**：`expression_vector.json` 中的历史数据不受影响——新维度加入后旧维度值保留，新维度从 0 开始
- **测试**：所有现有测试需保持通过，新增关键词匹配和配置加载的专项测试

---

## 7. 文件改动清单

| 文件 | 改动 |
|------|------|
| `persona-config.json` | dimensions 改为 dict of dict + 添加 synonyms_path |
| `keywords/*.json` | 新建：各维度关键词文件 + synonyms.json |
| `expression_vector.py` | 重构 `_count_keyword()` + 新增预处理/匹配函数 |
| `injector.py` | `_ExpressionVector` 实例化传递 keywords |
| `__init__.py` | 加载逻辑 + `register_command` |
| `tests/test_expression_vector.py` | 新增匹配升级测试 |
| `tests/test_keywords.py` | 新建：关键词加载/热加载测试 |

---

## 8. 后续迭代（不在本次范围）

- NL 转义：数值→自然语言（`label` 字段已预留）
- L4 Embedding 语义兜底
- `/hermes-persona keywords add/remove <维度> <关键词>` 在线编辑关键词

---

*🦊 知惠 执笔 · 2026-05-21 午间 · 设计案五节全过，凤凰单丛第五泡*
