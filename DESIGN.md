<h3 align="center">
  <a href="DESIGN.md">简体中文</a> · <a href="DESIGN_EN.md">English</a>
</h3>
<p align="center">— ✦ —</p>

# DESIGN.md — hermes-persona 架构决策

## 核心理念

**代码通用，配置驱动。** 插件不包含任何角色特定内容。所有人格通过 `persona-config.json` 定义，切换角色只需替换配置文件。

## 为什么用 Plugin Hooks？

Hermes Agent 的 Plugin Hook 机制提供了三个关键点：

| Hook | 用途 | 决策 |
|------|------|------|
| `pre_llm_call` | 每次 LLM 调用前注入上下文 | **人格引擎的核心**——确保每轮都被校准 |
| `on_session_start` | 新会话初始化 | 加载配置 + 验证格式 |
| `on_session_end` | 会话结束时清理 | 记录审计日志（如果启用） |

选择 `pre_llm_call` 而非修改系统提示的原因是：

1. **热加载**：修改 `persona-config.json` 后下一次对话即刻生效，无需重启
2. **隔离性**：人格注入与 Hermes 核心提示分离，互不污染
3. **降级安全**：hook 异常不影响 Agent 继续运行

## 为什么配置要用 JSON 而非 YAML？

1. Hermes Agent 生态中 JSON 是默认格式（prefill.json、config.yaml 除外）
2. JSON 有严格的结构约束，减少格式歧义
3. 用户群体更熟悉 JSON（JavaScript/TypeScript 开发者占多数）

## 文件布局

所有用户可编辑的 JSON 配置和运行时状态文件统一在插件目录下：

```
plugins/hermes-persona/
├── persona-config.json          ← 用户唯一需要手改的配置文件
├── keywords/                    ← 维度关键词（7 个 JSON，用户可定制）
├── locales/                     ← 多语言模板（en.json / zh.json）
├── state/                       ← 运行时自动生成（expression_vector / daily_turn_count）
└── examples/                    ← 模板（新用户复制用）
```

**路径解析策略**：`config.py` 提供 `_resolve_config_path()` 公共函数，三层 fallback：
1. 插件目录（新规范，优先）
2. `_CONFIG_ROOT`（旧规范 profile 根目录，向后兼容）
3. 调用方自行处理（如 repo 根目录 fallback）

`injector.py` 和 `guard.py` 统一通过此函数加载配置，避免重复维护多套路径逻辑。状态文件（`expression_vector.json`、`daily_turn_count.json`）默认写入 `state/`，若旧路径存在状态文件则自动读取并在首次 `save()` 时迁移到新路径。

## 七大模块设计

| 模块 | 配置节点 | 设计理由 |
|------|---------|---------|
| 时间感知 | `time` | 基础上下文，成本 < 1ms |
| 静态规则 | `context.rules` | 每轮生效的硬约束——角色身份、语言禁忌 |
| 首轮专属 | `context.rules_first_turn_only` | 避免开场白每轮重复 |
| 时段动态 | `dynamic.time_slots` | 同一角色在不同时段应有不同表现 |
| 轮数动态 | `dynamic.turn_stage` | 长对话中自然深化语气 |
| 关键词匹配 | `dynamic.keywords` | 场景驱动，按需注入——省 token |
| 随机变化 | `variance` | 打破机械感，同一场景不同表达 |
| 记忆召回 | `memory` | 可插拔的外部记忆 API |
| 看板注入 | `project` | 首轮注入项目上下文 |
| 安全护栏 | `guard` | 工具调用拦截 + 审计日志 |

## 降级策略

```
配置缺失  → 静默跳过该模块
JSON 格式错误 → 捕获异常，记录日志，不影响 Agent
外部 API 超时 → 超时 3s，失败后标记为不可用
模块异常 → 独立 try/except，不级联崩溃
```

**核心原则**：人格引擎是增强层，不是依赖层。任何情况下，Agent 的对话功能不因引擎故障而中断。

## Token 预算

单次 `inject_context()` 注入的 token 估算：

| 场景 | 规则数 | Token |
|------|--------|-------|
| 最小配置（仅时间） | 1 | ~30 |
| 典型角色（静态 + 1 时段 + 1 关键词） | 5-8 | ~150-250 |
| 全功能（全部模块启用） | 15+ | ~500-800 |

所有动态规则使用场景驱动触发，避免「所有规则每轮都烧 token」。硬约束放 prefill（每轮注入），软色调放 persona-config（按需触发）。
