# hermes-persona

> 为 Hermes Agent 构建的通用人格上下文注入引擎——代码通用、配置驱动、开箱即用

## 项目简介

`hermes-persona` 是一个 Hermes Agent 插件，在每轮 LLM 调用前动态注入人格上下文。它通过 **pre_llm_call hook** 将时间感知、静态规则、动态规则（时段/轮数/关键词）、随机表达变化、记忆召回和看板状态编织进 Agent 的系统提示。

**核心特性**：

- **代码通用**：不包含任何角色特定内容，所有人格通过 `persona-config.json` 配置
- **配置驱动**：JSON 配置文件定义全部行为，切换角色只需切换配置文件
- **降级健壮**：配置缺失、格式错误、外部 API 不可达等异常均静默降级，不影响 Agent 正常运行
- **可组合**：七大功能模块独立开关，按需组合

## 快速开始

### 1. 安装

```bash
# 一行命令，从 GitHub 安装并启用
hermes plugins install kenyonxu/hermes-persona --enable

# 验证安装
hermes plugins list | grep persona
```

### 2. 最小配置（5 分钟上手）

在 profile 目录下创建 `persona-config.json`：

```json
{
  "hermes-persona": {}
}
```

**仅此而已**。空配置 `{}` 会启动时间注入，Agent 每轮对话前都会感知当前时间：

```
🕐 2026年5月16日 周五 14:30
```

### 3. 添加自定义规则

```json
{
  "hermes-persona": {
    "context": {
      "rules": [
        "你是一个友好、专业的AI助手",
        "请用中文回答所有问题",
        "回答保持简洁，不超过200字"
      ]
    }
  }
}
```

### 4. 验证

安装并重启 Hermes gateway 后（仅首次需要），发送一条消息，Agent 的系统提示中将自动包含上述规则。

> 💡 **热加载**：之后修改 `persona-config.json` 保存即生效，无需再次重启。

### 5. 进阶功能一览

| 模块 | 配置节点 | 说明 |
|:---|:---|:---|
| 时间感知 | `time` | 每轮注入当前时间，支持三种格式 |
| 静态规则 | `context.rules` | 每轮固定注入的规则 |
| 首轮专属规则 | `context.rules_first_turn_only` | 仅首轮注入 |
| 时段动态规则 | `dynamic.time_slots` | 按时间段切换规则（如深夜模式） |
| 轮数动态规则 | `dynamic.turn_stage` | 按对话轮数切换规则（如长对话总结） |
| 关键词匹配 | `dynamic.keywords` | 用户消息命中关键词时注入特定规则 |
| 随机表达变化 | `variance` | 为回复添加随机风格变化 |
| 记忆召回 | `memory` | 从外部记忆 API 召回相关记忆 |
| 看板注入 | `project` | 首轮注入项目看板状态 |
| 安全护栏 | `guard` | 工具调用安全检查 + 审计日志 |

## 文档索引

| 文档 | 内容 |
|:---|:---|
| [配置参考](docs/CONFIG_REFERENCE.md) | 完整配置项说明——类型、默认值、示例 |
| [多角色示例](docs/EXAMPLES.md) | 3 个完整可用的 persona-config.json 示例——黑猫 Luna / 代码审查员 / 通用助手 |
| [阿格莱雅实战](docs/CASE_STUDY_AGLAEA.md) | 从星穹铁道 Lore 到五层人格槽位的完整转化教程 |
| [插件设计](docs/hermes-persona-plugin-design.md) | 架构设计文档 |
| [架构决策](DESIGN.md) | DESIGN.md：为什么这样设计 |
| [动态规则注入](docs/dynamic-rules-injection-design.md) | 时间/轮数/关键词三维动态人格适配 |

## 常见问题

**Q: 配置文件放哪里？**
A: 放在 Hermes profile 目录下，如 `~/.hermes/profiles/default/persona-config.json`。插件通过 `register(ctx)` 自动获取 `ctx.profile_path`。

**Q: 安装后所有 profile 都生效吗？**
A: 取决于安装命令执行时的上下文：
- `hermes plugins install ... --enable`（不带 `-p`）→ 全局生效，所有 profile 共享
- `hermes -p <name> plugins install ... --enable`（带 `-p`）→ 仅对指定 profile 生效
查看当前生效范围：`cat ~/.hermes/config.yaml` 或 `cat ~/.hermes/profiles/<name>/config.yaml`，找到 `plugins:` → `enabled:` 列表。

**Q: 最小配置是什么？**
A: `{"hermes-persona": {}}`——空对象即可启用时间感知，零配置开销。

**Q: 如何切换角色人格？**
A: 只需替换 `persona-config.json` 文件内容，无需修改任何代码。参见 [多角色示例](docs/EXAMPLES.md)。

**Q: 配置错误会不会导致 Agent 崩溃？**
A: 不会。所有异常均被捕获并静默降级。配置文件不存在、JSON 格式错误、字段类型不匹配等情况均不影响 Agent 正常流程。

**Q: 记忆召回需要什么？**
A: 需要一个兼容的 HTTP POST API。配置 `memory.api_url` 后，插件会发送 `{"query": "...", "limit": N}` 请求。无需记忆功能时保持 `memory.enabled: false` 即可。

**Q: 性能如何？**
A: 单次 `inject_context()` 调用 < 5ms（不含外部 API 调用）。最小配置（仅时间注入）< 1ms。

**Q: 支持哪些 Hermes 版本？**
A: 支持提供 `pre_llm_call` / `pre_tool_call` / `post_tool_call` hooks 的 Hermes 版本。

## 许可

MIT License — 插件代码与文档。
