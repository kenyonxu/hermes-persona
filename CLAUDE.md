# CLAUDE.md — hermes-persona Claude Code 代理指南

> 当 Claude Code（CC）被派到本仓库执行任务时，自动加载此文件。

## 项目定位

hermes-persona 是 Hermes Agent 的人格注入插件（MIT 开源）。通过 `pre_llm_call` hook 在每轮 LLM 调用前注入人格上下文。

## 分支规约

**永远不要在 `master` 上直接改代码！**

| 分支类型 | 命名 | 说明 |
|---------|------|------|
| feature | `feature/{US号}-{关键词}` | 新功能开发 |
| fix | `fix/{简短描述}` | Bug 修复 |
| docs | `master` 直接提交 | 纯文档（US/SPEC/PLAN） |

**工作流：**

```
US 审批 → 切 feature 分支 → SPEC → PLAN → CODE → 测试通过 → PR → master
```

- 代码改动 = 切分支 + PR 合并。
- `docs/dev/` 下的 US/SPEC/PLAN 文档可以在 master 上直接写。
- 当前活跃分支：以 `git branch --show-current` 为准

## 工程文档规范

所有新功能的工程文档放在 `docs/dev/` 下，遵循三阶段：

| 阶段 | 文件名 | 内容 |
|------|--------|------|
| 1. User Story | `US-{001}-{标题}.md` | As a... I want... So that... + 验收标准 |
| 2. SPEC | `SPEC-{001}-{标题}.md` | 架构设计 + 接口 + 改动清单 + 测试策略 |
| 3. PLAN | `PLAN-{001}-{标题}.md` | 分步实施计划 + 时间估算 |

## 开发命令

```bash
# 运行所有测试
python -m pytest tests/ -v

# 仅运行某个测试文件
python -m pytest tests/test_modules_switch.py -v

# 代码风格
# Python 3.10+, PEP 8, 所有公开函数有 docstring
```

## 核心架构

```
inject_context() 注入顺序（不可变）：
  ① _time_context()          → 时间感知
  ② _inject_static_rules()   → 静态规则
  ③ _select_dynamic_rules()  → 动态规则（time_slots→turn_stage→keyword）
  ④ _randomize_variance()    → 随机变化
  ⑤ _recall_memories()       → 记忆召回
  ⑥ _read_kanban()           → 看板注入（仅首轮）
```

- 异常处理：fail-open，任何模块失败不阻断后续
- 配置驱动：`persona-config.json`
- 不要改 `guard.py`（独立的安全护栏体系）

## 语言

请始终使用中文回答用户的问题和请求。
