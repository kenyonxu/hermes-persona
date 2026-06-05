<h3 align="center">
  <a href="AGENTS.md">简体中文</a> · <a href="AGENTS_EN.md">English</a>
</h3>
<p align="center">— ✦ —</p>

# AGENTS.md — hermes-persona 贡献者指南

## 项目简介

hermes-persona 是 Hermes Agent 的人格注入插件。通过 `pre_llm_call` hook，在每轮 LLM 调用前将时间、角色规则、场景触发、随机变化编织进系统提示。代码完全通用，人格完全由 `persona-config.json` 配置驱动。

## 快速导航

| 文件 | 作用 |
|------|------|
| `README.md` | 5 分钟上手指南 |
| `DESIGN.md` | 架构决策文档 |
| `plugin.yaml` | 插件元数据 |
| `hermes_persona/` | 插件源码 |
| `tests/` | 131 个测试用例 |
| `docs/` | 配置参考 + 角色示例 + 阿格莱雅实战 |
| `docs/dev/` | 工程文档（User Story → SPEC → PLAN） |

## 开发流程

### 运行测试

```bash
cd hermes-persona
python -m pytest tests/ -v
```

覆盖核心模块：静态规则注入、动态规则（时段/轮数/关键词）、随机变化、记忆召回、安全护栏。

### 分支与 PR

**内部团队分支规约：**

| 分支类型 | 命名 | 从哪出 | 合回哪 | 例子 |
|---------|------|--------|--------|------|
| **feature** | `feature/{US号}-{关键词}` | `master` | `master` (via PR) | `feature/001-module-switch` |
| **fix** | `fix/{简短描述}` | `master` | `master` (via PR) | `fix/turn-count-overflow` |
| **docs** | 直接在 `master` 上改 | — | — | `docs/dev/US-001.md` |

**工作流：**

```
US 审批 → 切 feature 分支 → SPEC → PLAN → CODE → 测试通过
                                                    │
                                          master ← PR 合并
```

- `master` 分支保持稳定，对用户可运行。
- 代码改动永远在 feature/fix 分支上进行，合并走 PR。
- `docs/dev/` 下的纯文档（US/SPEC）可在 master 上直接提交。

**外部贡献者：**

1. Fork 仓库
2. 从 `master` 创建 feature 分支：`feature/your-feature-name`
3. 修改代码
4. 确保测试通过：`python -m pytest tests/ -v`
5. 提交 PR

### 代码风格

- Python 3.10+
- 遵循 PEP 8
- 所有公开函数均有 docstring

## 插件架构

```
pre_llm_call hook
  ↓
inject_context()
  ├── _time_context()            → ① 时间感知
  ├── _weather_context()         → ①b 天气注入
  ├── _inject_static_rules()     → ② 静态规则（每轮注入）
  ├── _select_dynamic_rules()    → ③ 动态规则（时段/轮数/关键词）
  ├── _fixed_signals             → ④a 固定信号
  ├── _expression_vector         → ④b 表达向量
  ├── _randomize_variance()      → ④ 随机变化
  ├── _recall_memories()         → ⑤ 记忆召回
  └── _read_kanban()             → ⑥ 看板注入（仅首轮）
  ↓
系统提示上下文
```

所有模块独立开关（通过 `modules` 配置），异常静默降级——一个模块失败不影响其他模块和 Agent 正常运行。

## 常见贡献

- **新的角色示例**：在 docs/EXAMPLES.md 添加新角色
- **新的动态规则类型**：在 `hermes_persona/dynamic_rules.py` 实现
- **Bug 修复**：附带复现测试用例

## License

MIT
