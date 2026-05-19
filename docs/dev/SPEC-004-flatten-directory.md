# SPEC-004: hermes-persona 目录扁平化重构

> **状态**: 草案 | **优先级**: 🔴·P0 | **作者**: 知惠 (基于 CC 调研) | **日期**: 2026-05-20
>
> **关联**: [FIX-001](./FIX-001-transform-llm-output-debug.md) — 五层追踪最终定位到的根因

---

## 1. 问题陈述

### 1.1 双层目录陷阱

hermes-persona 存在致命的双层 `__init__.py` 结构：

```
hermes-persona/                  # ← Hermes 插件根目录
├── __init__.py                  # ← 外层空壳 (旧版，28行)
├── plugin.yaml                  #   无 module 字段，Hermes 默认加载根 __init__.py
├── hermes_persona/              # ← 内层子目录
│   ├── __init__.py              # ← 新版 register() (56行) — Hermes 永远碰不到！
│   ├── injector.py              #   含 transform_llm_output
│   ├── guard.py
│   ├── dynamic_rules.py
│   ├── expression_vector.py     #   US-002
│   └── variance.py
├── tests/
└── ...
```

### 1.2 问题链

1. `plugin.yaml` 无 `module` 字段 → Hermes 默认加载插件根 `__init__.py`
2. 外层 `__init__.py` 是旧版，只注册 `pre_llm_call` + `pre_tool_call` + `post_tool_call`
3. 内层 `hermes_persona/__init__.py` 的新版 `register()` 包含 `transform_llm_output` → **永远不会被 Hermes 调用**
4. 2026-05-19 花费五层追踪才定位到此根因（详见 FIX-001）

### 1.3 影响范围

- **transform_llm_output hook 不触发** — US-002 的 debug 块无法注入到 LLM 输出
- **双层维护噩梦** — 内层修改永远需要确认外层是否同步
- **新人陷阱** — 任何不了解历史的人都会在内层改代码，然后发现不生效

---

## 2. 目标架构

### 2.1 扁平化后目录树

```
hermes-persona/                  # ← Hermes 插件根目录（单层！）
├── __init__.py                  # ← 唯一入口 = 原 hermes_persona/__init__.py（减探针）
├── injector.py                  # ← 从 hermes_persona/ 搬上来
├── guard.py                     # ← 从 hermes_persona/ 搬上来
├── dynamic_rules.py             # ← 从 hermes_persona/ 搬上来
├── expression_vector.py         # ← 从 hermes_persona/ 搬上来
├── variance.py                  # ← 从 hermes_persona/ 搬上来
├── plugin.yaml                  #   无需改动（默认加载 __init__.py）
├── tests/
│   ├── __init__.py
│   ├── conftest.py              #   import 路径已更新
│   ├── test_dynamic_rules.py
│   ├── test_expression_vector.py
│   ├── test_fixed_signals.py
│   ├── test_guard.py
│   ├── test_injector.py
│   ├── test_modules_switch.py
│   └── test_variance.py
├── docs/
├── scripts/
├── examples/
└── ...
```

### 2.2 Hermes 加载流

```
Hermes Agent 启动
  → 扫描 plugins/ 目录
  → 找到 hermes-persona/
  → 读取 plugin.yaml (无 module 字段)
  → 默认加载 ./__init__.py  ← 现在就是唯一正确的版本
  → 调用 register(ctx)
      ├── pre_llm_call        → injector.inject_context()
      ├── transform_llm_output → injector.transform_llm_output()  ✅ 现在生效了！
      ├── pre_tool_call       → guard.check_tool_call()
      └── post_tool_call      → guard.audit_tool_call()
```

---

## 3. 变更清单

### 3.1 文件移动 (5个)

| # | 源路径 | 目标路径 | 说明 |
|---|--------|----------|------|
| 1 | `hermes_persona/injector.py` | `./injector.py` | 核心注入引擎 |
| 2 | `hermes_persona/guard.py` | `./guard.py` | 安全护栏 |
| 3 | `hermes_persona/dynamic_rules.py` | `./dynamic_rules.py` | 动态规则引擎 |
| 4 | `hermes_persona/expression_vector.py` | `./expression_vector.py` | US-002 表达向量 |
| 5 | `hermes_persona/variance.py` | `./variance.py` | 随机变化引擎 |

### 3.2 文件修改 (1个)

| # | 文件 | 变更 |
|---|------|------|
| 1 | `./__init__.py` | **替换**为内层新版内容，**同时移除**两段 DIAGNOSTIC PROBE |

#### 需要移除的探针代码

```python
# ❌ 删除 — DIAGNOSTIC PROBE 1
    try:
        with open("/tmp/register_trace.txt", "a") as f:
            f.write(f"BEFORE transform_llm_output | ...")
    except Exception:
        pass

# ❌ 删除 — DIAGNOSTIC PROBE 2
    try:
        with open("/tmp/register_trace.txt", "a") as f:
            f.write(f"AFTER transform_llm_output | ...")
    except Exception:
        pass
```

### 3.3 源码内相对导入修改 (~5处)

扁平化后模块之间不再通过 `hermes_persona` 包引用，相对导入需改为同级直接导入：

| 文件 | 当前 | 改为 |
|------|------|------|
| `injector.py` | `from .dynamic_rules import ...` | `from dynamic_rules import ...` |
| `injector.py` | `from .expression_vector import ...` | `from expression_vector import ...` |
| `injector.py` | `from .variance import ...` | `from variance import ...` |
| `guard.py` | `from .injector import ...` | `from injector import ...` |

> **注意**: 上述为预估引用模式，实际变更以 `grep "from \." hermes_persona/*.py` 扫描结果为准。需在 PLANNING 阶段逐文件确认。

### 3.4 文件删除 (1个目录)

| # | 路径 | 说明 |
|---|------|------|
| 1 | `hermes_persona/` 整个目录 | 源码搬空后删除（含旧 `__pycache__/`） |

### 3.5 不变更

- `plugin.yaml` — 无 `module` 字段，默认行为不变
- `tests/` 目录结构不变
- `docs/`, `scripts/`, `examples/` 不变

---

## 4. 测试路径迁移矩阵

### 4.1 引用统计

CC 调研结果：测试文件中约 **86处** `hermes_persona.xxx` 引用，分布在 7 个测试文件中。

### 4.2 迁移模式对照表

| 当前引用模式 | 扁平化后 | 示例 |
|-------------|----------|------|
| `import hermes_persona.injector as injector` | `import injector` | conftest.py L9 |
| `import hermes_persona.injector as mod` | `import injector as mod` | conftest.py L37 |
| `import hermes_persona.guard as guard` | `import guard` | test_guard.py |
| `from hermes_persona.injector import inject_context` | `from injector import inject_context` | test_injector.py |
| `from hermes_persona.dynamic_rules import ...` | `from dynamic_rules import ...` | test_dynamic_rules.py |
| `from hermes_persona.variance import ...` | `from variance import ...` | test_variance.py |
| `from hermes_persona.expression_vector import ...` | `from expression_vector import ...` | test_expression_vector.py |

### 4.3 逐文件迁移清单

| 测试文件 | 预估引用数 | 主要变更 |
|---------|:---------:|---------|
| `tests/conftest.py` | 2 | `import hermes_persona.injector` → `import injector` |
| `tests/test_injector.py` | ~30 | 所有 `hermes_persona.injector` → `injector` |
| `tests/test_guard.py` | ~10 | `hermes_persona.guard` → `guard` |
| `tests/test_dynamic_rules.py` | ~15 | `hermes_persona.dynamic_rules` → `dynamic_rules` |
| `tests/test_variance.py` | ~10 | `hermes_persona.variance` → `variance` |
| `tests/test_expression_vector.py` | ~10 | `hermes_persona.expression_vector` → `expression_vector` |
| `tests/test_modules_switch.py` | ~5 | `hermes_persona.*` → `*` |
| `tests/test_fixed_signals.py` | ~4 | `hermes_persona.*` → `*` |

> **实际数字需在 PLANNING 阶段用 `grep -c` 精确确认，并生成 sed 批量替换脚本。**

---

## 5. 风险与回滚

### 5.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|:--:|:--:|---------|
| 扁平化后 Hermes 加载失败 | 低 | 严重 | 先在测试环境验证 `register()` 可调用 |
| 测试 import 遗漏导致假通过 | 中 | 中 | 用 `pytest --import-mode=importlib` 强制重新加载 |
| 残留 `hermes_persona/` import 未清理 | 中 | 低 | PLANNING 阶段用 `grep -rn` 全量扫描 |
| 外部依赖 `hermes_persona` 包名 | 低 | 低 | 检查是否有其他 repo 引用此包名 |

### 5.2 回滚方案

```bash
# 两步回滚
git checkout HEAD~1 -- .                        # 恢复所有文件
git checkout HEAD~1 -- hermes_persona/          # 恢复子目录
# 验证
python -m pytest tests/ -v                      # 必须 232/232 PASSED
```

---

## 6. 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| 1 | `hermes_persona/` 目录不存在 | `ls hermes_persona/` 应报错 |
| 2 | 根目录存在 5 个源码文件 | `ls injector.py guard.py dynamic_rules.py expression_vector.py variance.py` |
| 3 | `__init__.py` 不含 DIAGNOSTIC PROBE | `grep -c "DIAGNOSTIC PROBE" __init__.py` = 0 |
| 4 | `__init__.py` 含 `transform_llm_output` 注册 | `grep "transform_llm_output" __init__.py` 有匹配 |
| 5 | **232 测试全部通过** | `python -m pytest tests/ -v` → 232 passed |
| 6 | `grep -rn "hermes_persona\." tests/` 返回空 | 无遗留旧路径引用 |
| 7 | `grep -rn "hermes_persona\." *.py` 返回空 | 根目录源码无旧路径引用 |

---

## 7. 关联影响

### 7.1 CI/CD

- `.github/workflows/` 中如有 `pip install -e .` 或 `python -m hermes_persona` 需调整
- 当前项目无 CI 配置文件，此项为 No-Op

### 7.2 部署

- `plugin.yaml` 无需改动 → Hermes 自动加载新结构
- 部署方式不变：整个 `hermes-persona/` 目录放入 `~/.hermes/profiles/<name>/plugins/`

### 7.3 文档

| 文档 | 是否需要更新 | 说明 |
|------|:--:|------|
| `README.md` | 否 | 未提及目录结构 |
| `DESIGN.md` | 否 | 架构描述不涉及物理布局 |
| `AGENTS.md` | 是 | "插件架构" 图中的路径需更新 |
| `docs/en/hermes-persona-plugin-design.md` | 是 | 如有路径引用需更新 |
| `docs/hermes-persona-plugin-design.md` | 是 | 同上 |

### 7.4 技能文件

- `hermes-persona` skill (知惠侧) 如包含路径引用需排查
- GitHub Actions 工作流如引用源码路径需更新

---

## 附录 A: 外层 vs 内层 __init__.py 对比

| 特征 | 外层 (将被替换) | 内层 (将搬到根目录) |
|------|:--:|:--:|
| 行数 | 34 | 56 |
| `transform_llm_output` 注册 | ❌ | ✅ |
| docstring 详细度 | 简略 | 完整 |
| import 方式 | `from .hermes_persona import` | `from . import` (包内) |
| DIAGNOSTIC PROBE | ❌ | ✅ (需移除) |
| `__all__` | `["register"]` | 无 |

## 附录 B: 相关文档

- [FIX-001: transform_llm_output debug 块不拼接](./FIX-001-transform-llm-output-debug.md) — 五层追踪诊断文档
- [SPEC-003: Debug 面板增强](./SPEC-003-debug-rich-i18n.md) — 详细模式 + 国际化
- [PLAN-002: 表达向量与FuzzyUtility](./PLAN-002-表达向量与FuzzyUtility.md) — US-002 实施计划

---

*🦊 知惠 执笔 · 2026-05-20 晨 · SPEC-004 · CC 调研 + 知惠成文*
