# PLAN-004: 目录扁平化重构 — 实施计划

**文档编号:** PLAN-004
**对应 SPEC:** SPEC-004
**版本:** 1.0
**日期:** 2026-05-20
**作者:** CC (Claude Code)
**审阅:** 知惠 & Kai.Xu
**状态:** 📋 待审阅

---

## 目录

1. [总体时间估算](#1-总体时间估算)
2. [实施步骤](#2-实施步骤)
    - [Phase 0: 环境准备与基线验证](#phase-0-环境准备与基线验证)
    - [Phase 1: 文件搬移 — 5 个源码文件上浮](#phase-1-文件搬移--5-个源码文件上浮)
    - [Phase 2: __init__.py 替换 + 探针清理](#phase-2-__init__py-替换--探针清理)
    - [Phase 3: 源码内相对导入改为同级导入](#phase-3-源码内相对导入改为同级导入)
    - [Phase 4: 测试文件 import 路径批量替换](#phase-4-测试文件-import-路径批量替换)
    - [Phase 5: 清理旧目录与残留缓存](#phase-5-清理旧目录与残留缓存)
    - [Phase 6: 文档与外部引用更新](#phase-6-文档与外部引用更新)
    - [Phase 7: 全量回归测试与验收](#phase-7-全量回归测试与验收)
3. [风险点与回滚方案](#3-风险点与回滚方案)
4. [验证检查清单](#4-验证检查清单)

---

## 1. 总体时间估算

| Phase | 内容 | 预估时间 |
|:---|:---|:---|
| Phase 0 | 环境准备与基线验证 | 5 min |
| Phase 1 | 文件搬移 — 5 个源码文件上浮 | 5 min |
| Phase 2 | `__init__.py` 替换 + DIAGNOSTIC PROBE 清理 | 10 min |
| Phase 3 | 源码内相对导入改为同级导入 | 10 min |
| Phase 4 | 测试文件 import 路径批量替换（~84 处） | 15 min |
| Phase 5 | 清理旧目录与 `__pycache__/` | 5 min |
| Phase 6 | 文档与 graphify 知识图谱更新 | 10 min |
| Phase 7 | 全量回归测试 232 PASSED + 验收 | 15 min |
| **合计** | | **~1 小时 15 分钟** |

### 阶段依赖关系

```
Phase 0 (基线) → Phase 1 (搬移) → Phase 2 (__init__.py) → Phase 3 (源码导入)
                                                                ↓
                                                          Phase 4 (测试路径)
                                                                ↓
Phase 5 (清理) ←─────────────────────────────────────────────────┘
       ↓
Phase 6 (文档) → Phase 7 (回归验收)
```

Phase 1~4 为连续操作链，不可并行。Phase 5/6 可并行。Phase 7 为最终验证门。

---

## 2. 实施步骤

### Phase 0: 环境准备与基线验证

**目标：** 确认分支正确、工作区干净、现有测试全量通过。

**操作：**

```bash
# 1. 确认分支
git branch --show-current
# 期望: feature/001-module-switch

# 2. 确认工作区干净
git status
# 期望: 无未提交变更（docs/dev/SPEC-004 除外）

# 3. 基线测试
python -m pytest tests/ -v
# 期望: 232 passed, 0 failure

# 4. 记录基线数据
grep -rc "hermes_persona\." tests/ > /tmp/baseline_imports.txt
# 用于 Phase 4 完成后对比确认
```

**验证标准：**
- `git branch --show-current` = `feature/001-module-switch`
- `python -m pytest tests/ -v` → 232 passed, 0 failure
- `hermes_persona/` 目录下有 6 个 `.py` 文件

**回滚：** 无需回滚（尚未改动代码）

---

### Phase 1: 文件搬移 — 5 个源码文件上浮

**目标：** 将 `hermes_persona/` 下 5 个业务模块源码文件移到项目根目录。

**文件清单：**

| # | 源路径 | 目标路径 | 大小 | 说明 |
|---|--------|----------|------|------|
| 1 | `hermes_persona/injector.py` | `./injector.py` | ~26KB | 核心注入引擎 |
| 2 | `hermes_persona/guard.py` | `./guard.py` | ~5KB | 安全护栏 |
| 3 | `hermes_persona/dynamic_rules.py` | `./dynamic_rules.py` | ~4KB | 动态规则引擎 |
| 4 | `hermes_persona/expression_vector.py` | `./expression_vector.py` | ~6KB | 表达向量 |
| 5 | `hermes_persona/variance.py` | `./variance.py` | ~1KB | 随机变化引擎 |

> **注意：** `hermes_persona/__init__.py` **不移动**。新 `__init__.py` 将在 Phase 2 中单独编写。
>
> **注意：** `hermes_persona/__pycache__/` **不移动**，将在 Phase 5 中随目录一同删除。

**操作：**

```bash
# 逐文件 git mv（保留 git 历史）
git mv hermes_persona/injector.py injector.py
git mv hermes_persona/guard.py guard.py
git mv hermes_persona/dynamic_rules.py dynamic_rules.py
git mv hermes_persona/expression_vector.py expression_vector.py
git mv hermes_persona/variance.py variance.py
```

**验证标准：**

```bash
# 确认 5 个文件已在根目录
ls injector.py guard.py dynamic_rules.py expression_vector.py variance.py
# 期望: 5 个文件全部存在

# 确认源位置已空（除 __init__.py 和 __pycache__）
ls hermes_persona/
# 期望: __init__.py __pycache__/（仅有残留，无 .py 模块文件）

# git status 显示 5 个 rename
git status
# 期望: 5 个 renamed: hermes_persona/xxx.py → xxx.py
```

**回滚：**

```bash
git checkout HEAD -- . && rm -f injector.py guard.py dynamic_rules.py expression_vector.py variance.py
```

---

### Phase 2: `__init__.py` 替换 + 探针清理

**目标：** 用内层新版 `__init__.py` 替换根目录旧版 `__init__.py`，**同时移除两段 DIAGNOSTIC PROBE**。

**操作步骤：**

#### 2.1 读取内层新版内容

内层 `hermes_persona/__init__.py` (56 行) 包含 `transform_llm_output` 注册，但有两段探针代码需要剥离。

#### 2.2 用新版内容覆写根目录 `__init__.py`，删除探针

**`__init__.py` 新内容（57 行 → ~44 行）：**

```python
"""hermes-persona: Dynamic persona context injection engine for Hermes Agent.

Usage:
    from . import register  # Hermes plugin root
    register(ctx)  # ctx is a Hermes PluginContext
"""

from __future__ import annotations

from pathlib import Path

import guard
import injector


def register(ctx) -> None:
    """Register the hermes-persona plugin with the Hermes runtime.

    - Stores the profile directory path (ctx.profile_path) for config loading.
    - Registers the pre_llm_call hook for persona context injection.
    - Registers transform_llm_output hook for reliable debug injection.
    - Registers pre_tool_call / post_tool_call hooks for safety guard (P4).

    Args:
        ctx: Hermes PluginContext with profile_path, register_hook, etc.
    """
    # Store profile path for config loading
    if hasattr(ctx, "profile_path") and ctx.profile_path:
        injector._CONFIG_ROOT = Path(ctx.profile_path)
    # else: _CONFIG_ROOT stays None → _load_config() uses fallback path

    # P1: persona context injection
    ctx.register_hook("pre_llm_call", injector.inject_context)

    # Debug: reliable post-injection via transform_llm_output
    ctx.register_hook("transform_llm_output", injector.transform_llm_output)

    # P4: safety guard
    ctx.register_hook("pre_tool_call", guard.check_tool_call)
    ctx.register_hook("post_tool_call", guard.audit_tool_call)
```

**关键变更（对比内层旧版）：**
- 删除 `from . import guard` / `from . import injector` → 改为 `import guard` / `import injector`（同级导入）
- 删除 `# ── DIAGNOSTIC PROBE ──` 两段（共 ~14 行）
- 删除 `# ── END PROBE ──` 标记行
- docstring 中 `from hermes_persona import register` → `from . import register`
- 保留完整 docstring 和 `transform_llm_output` 注册
- 删除 `__all__` 声明（内层新版无此字段）

#### 2.3 操作

```bash
# 方式 1: 直接写新文件（Phase 2 内容如上）
# 用 Write 工具覆写 __init__.py

# 方式 2: 先 git mv 内层 __init__.py 到根目录，再编辑
# git mv hermes_persona/__init__.py __init__.py.new
# 编辑 __init__.py.new → 删除探针 + 改 import → 替换原 __init__.py
```

**验证标准：**

```bash
# 1. 确认探针已清除
grep -c "DIAGNOSTIC PROBE" __init__.py
# 期望: 0

# 2. 确认 transform_llm_output 注册存在
grep "transform_llm_output" __init__.py
# 期望: 有匹配（register_hook 行）

# 3. 确认 import 方式为同级导入
grep "import" __init__.py
# 期望: import guard / import injector（非 from . 开头，非 from hermes_persona 开头）

# 4. 确认语法合法
python -c "import ast; ast.parse(open('__init__.py').read()); print('OK')"
# 期望: OK
```

**回滚：**

```bash
git checkout HEAD -- __init__.py
```

---

### Phase 3: 源码内相对导入改为同级导入

**目标：** 将 `injector.py` 和 `guard.py` 中从 `hermes_persona` 包内引用（`from .xxx`）改为同级模块直接导入（`from xxx`）。

**精确改动矩阵：**

| 文件 | 行 | 当前代码 | 改为 |
|------|----|---------|------|
| `injector.py` | 15 | `from .dynamic_rules import _select_dynamic_rules` | `from dynamic_rules import _select_dynamic_rules` |
| `injector.py` | 16 | `from .expression_vector import _ExpressionVector` | `from expression_vector import _ExpressionVector` |
| `injector.py` | 17 | `from .variance import _randomize_variance` | `from variance import _randomize_variance` |
| `guard.py` | 31 | `from .injector import _CONFIG_ROOT` | `from injector import _CONFIG_ROOT` |

> **注意：** `injector.py` 和 `guard.py` 内部的其他包引用（如 `from pathlib import Path`）不受影响。

**操作：**

```bash
# injector.py (3 处)
sed -i 's/from \.dynamic_rules import/from dynamic_rules import/g' injector.py
sed -i 's/from \.expression_vector import/from expression_vector import/g' injector.py
sed -i 's/from \.variance import/from variance import/g' injector.py

# guard.py (1 处)
sed -i 's/from \.injector import/from injector import/g' guard.py
```

**验证标准：**

```bash
# 1. 确认无残留相对导入
grep -rn "from \." injector.py guard.py
# 期望: 无输出

# 2. 确认无 hermes_persona 包引用残留
grep -rn "hermes_persona\." injector.py guard.py dynamic_rules.py expression_vector.py variance.py
# 期望: 无输出（排除注释/字符串中的可能引用）

# 3. 语法合法性校验
python -c "import ast; ast.parse(open('injector.py').read()); ast.parse(open('guard.py').read()); print('OK')"
# 期望: OK
```

**回滚：**

```bash
git checkout HEAD -- injector.py guard.py
```

---

### Phase 4: 测试文件 import 路径批量替换

**目标：** 将 7 个测试文件中所有 `hermes_persona.xxx` 引用替换为扁平化后的 `xxx` 直接引用。

**精确统计（不含 `__pycache__`）：**

| 文件 | 引用数 | 主要模式 |
|------|:---:|---------|
| `tests/test_injector.py` | 26 | `import hermes_persona.injector` / `from hermes_persona.injector import` / `patch("hermes_persona.injector.xxx")` |
| `tests/test_modules_switch.py` | 38 | 同上 + `patch("hermes_persona.dynamic_rules.datetime")` |
| `tests/test_dynamic_rules.py` | 10 | `from hermes_persona.dynamic_rules import` / `patch("hermes_persona.dynamic_rules.xxx")` |
| `tests/test_guard.py` | 4 | `from hermes_persona.guard import` / `patch("hermes_persona.guard.xxx")` |
| `tests/conftest.py` | 2 | `import hermes_persona.injector as injector` |
| `tests/test_variance.py` | 2 | `from hermes_persona.variance import` |
| `tests/test_expression_vector.py` | 1 | `from hermes_persona.expression_vector import` |
| `tests/test_fixed_signals.py` | 1 | `import hermes_persona.injector as injector` |
| **合计** | **84** | |

#### 4.1 精确 sed 替换脚本

**重要：** 必须按以下顺序执行，确保 `import hermes_persona.injector as injector` 在 `patch("hermes_persona.injector.xxx")` 之前被替换。但由于 sed 是行匹配，两种模式互不冲突，可安全并行执行。

```bash
# ============================================================
# 批量替换模式 1: import hermes_persona.xxx as xxx
#   import hermes_persona.injector as injector  →  import injector
# ============================================================
sed -i 's/import hermes_persona\.injector as injector/import injector/g' tests/*.py

# ============================================================
# 批量替换模式 2: from hermes_persona.xxx import ...
#   from hermes_persona.injector import inject_context  →  from injector import inject_context
# ============================================================
sed -i 's/from hermes_persona\.injector import/from injector import/g' tests/*.py
sed -i 's/from hermes_persona\.guard import/from guard import/g' tests/*.py
sed -i 's/from hermes_persona\.dynamic_rules import/from dynamic_rules import/g' tests/*.py
sed -i 's/from hermes_persona\.expression_vector import/from expression_vector import/g' tests/*.py
sed -i 's/from hermes_persona\.variance import/from variance import/g' tests/*.py

# ============================================================
# 批量替换模式 3: patch("hermes_persona.xxx.yyy")
#   patch("hermes_persona.injector.datetime")  →  patch("injector.datetime")
# ============================================================
sed -i 's/patch("hermes_persona\.injector\./patch("injector./g' tests/*.py
sed -i 's/patch("hermes_persona\.guard\./patch("guard./g' tests/*.py
sed -i 's/patch("hermes_persona\.dynamic_rules\./patch("dynamic_rules./g' tests/*.py
sed -i 's/patch("hermes_persona\.expression_vector\./patch("expression_vector./g' tests/*.py
sed -i 's/patch("hermes_persona\.variance\./patch("variance./g' tests/*.py

# ============================================================
# 批量替换模式 4: 残留的 hermes_persona.xxx（泛化兜底）
#   hermes_persona.injector.load_config  →  injector.load_config
# ============================================================
sed -i 's/hermes_persona\.injector/injector/g' tests/*.py
sed -i 's/hermes_persona\.guard/guard/g' tests/*.py
sed -i 's/hermes_persona\.dynamic_rules/dynamic_rules/g' tests/*.py
sed -i 's/hermes_persona\.expression_vector/expression_vector/g' tests/*.py
sed -i 's/hermes_persona\.variance/variance/g' tests/*.py

# ============================================================
# 清理 pycache 字节码文件（避免旧 .pyc 干扰新导入）
# ============================================================
find tests/__pycache__/ -name "*.pyc" -delete 2>/dev/null
```

> **设计说明：** sed 脚本分 4 层递进替换，模式 1~3 先精确处理高频模式，模式 4 作为兜底泛化替换。确保所有 `hermes_persona.*` 引用被替换。

**验证标准：**

```bash
# 1. 确认测试文件中无残留 hermes_persona. 引用
grep -rn "hermes_persona\." tests/ --include="*.py"
# 期望: 无输出

# 2. 确认导入语法合法（每个测试文件尝试导入）
python -c "
import tests.conftest
import guard
import injector
import dynamic_rules
import expression_vector
import variance
print('All imports OK')
"
# 期望: All imports OK

# 3. 运行一轮测试验证无导入错误
python -m pytest tests/ -v --co 2>&1 | head -20
# 期望: 收集到测试用例，无 ImportError
```

**回滚：**

```bash
git checkout HEAD -- tests/
```

---

### Phase 5: 清理旧目录与残留缓存

**目标：** 删除已搬空的 `hermes_persona/` 目录及 `__pycache__/` 缓存。

**操作：**

```bash
# 1. 确认 hermes_persona/ 目录内仅剩 __init__.py 和 __pycache__
ls -la hermes_persona/
# 期望: 仅 __init__.py + __pycache__（无模块 .py 文件）

# 2. 删除整个子目录
rm -rf hermes_persona/

# 3. 清理根目录可能遗留的 __pycache__
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# 4. 确认 cleanup
ls hermes_persona/ 2>&1
# 期望: ls: cannot access 'hermes_persona/': No such file or directory
```

**验证标准：**

```bash
# 1. hermes_persona/ 目录已不存在
test -d hermes_persona/ && echo "FAIL" || echo "PASS"
# 期望: PASS

# 2. 根目录有 5 个源码文件 + 1 个 __init__.py
ls injector.py guard.py dynamic_rules.py expression_vector.py variance.py __init__.py
# 期望: 6 个文件全部存在

# 3. 目录树结构正确
tree -L 1 -I '__pycache__|tests|docs|examples|scripts|.*'
# 期望: 根目录仅有顶级 Python 模块文件（无子目录）
```

**回滚：**

```bash
# 从 git 恢复整个子目录
git checkout HEAD -- hermes_persona/
```

---

### Phase 6: 文档与外部引用更新

**目标：** 更新所有引用 `hermes_persona.` 包名路径的外部文件。

#### 6.1 需要更新的文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `docs/hermes-persona-plugin-design.md` | 替换包路径 | 如有 `hermes_persona.` import 示例 |
| `docs/hermes-persona-plugin-design_en.md` | 同上 | 英文版文档 |
| `AGENTS.md` | 替换路径引用 | 如有架构图或 import 示例 |
| **所有 `docs/dev/US-*.md`** | 替换代码示例中的路径 | US-001/US-002 中的 import 示例 |
| **所有 `docs/dev/SPEC-*.md`** | 同上 | SPEC-001/002/003 中如有路径 |
| **所有 `docs/dev/PLAN-*.md`** | 同上 | PLAN-001/002 代码块中的路径 |
| **所有 `docs/dev/FIX-*.md`** | 同上 | FIX-001 中的诊断路径 |
| `graphify-out/` | `graphify update .`（重生成） | AST 知识图谱自动重建 |

#### 6.2 `docs/` 目录路径替换

```bash
# 全局扫描 docs/ 下所有 .md 文件
grep -rln "hermes_persona\." docs/ --include="*.md"

# 精确替换（仅 Python 代码块中的导入路径）
find docs/ -name "*.md" -exec sed -i \
    -e 's/hermes_persona\.injector/injector/g' \
    -e 's/hermes_persona\.guard/guard/g' \
    -e 's/hermes_persona\.dynamic_rules/dynamic_rules/g' \
    -e 's/hermes_persona\.expression_vector/expression_vector/g' \
    -e 's/hermes_persona\.variance/variance/g' \
    -e 's/from hermes_persona import/import/g' \
    -e 's/import hermes_persona/import/g' \
    {} +
```

#### 6.3 graphify 知识图谱更新

```bash
# 重新扫描代码生成知识图谱
cd /home/kai-remote/github/hermes-persona
graphify update .
```

**验证标准：**

```bash
# 1. docs/ 目录无残留旧路径引用
grep -rln "hermes_persona\." docs/ --include="*.md"
# 期望: 无输出（或仅 SPEC-004 自身描述"迁移前"路径的段落）

# 2. AGENTS.md 无旧路径
grep -rn "hermes_persona\." AGENTS.md 2>/dev/null
# 期望: 无输出

# 3. graphify-out/ 已更新
ls graphify-out/
# 期望: graph.json, GRAPH_REPORT.md 等文件时间戳为当前时间
```

**回滚：**

```bash
git checkout HEAD -- docs/ AGENTS.md graphify-out/
```

---

### Phase 7: 全量回归测试与验收

**目标：** 运行全部测试确认 232 PASSED，逐项验证 SPEC-004 验收标准。

#### 7.1 自动化测试

```bash
# 全量测试
python -m pytest tests/ -v

# 期望输出:
# - tests/test_injector.py          全部 PASSED
# - tests/test_dynamic_rules.py     全部 PASSED
# - tests/test_variance.py          全部 PASSED
# - tests/test_guard.py             全部 PASSED
# - tests/test_modules_switch.py    全部 PASSED
# - tests/test_expression_vector.py 全部 PASSED
# - tests/test_fixed_signals.py     全部 PASSED
# - 232 passed in X.XXs
```

#### 7.2 验收检查清单

```bash
# AC-1: hermes_persona/ 目录不存在
test ! -d hermes_persona/ && echo "PASS" || echo "FAIL"

# AC-2: 根目录 5 个源码文件存在
for f in injector.py guard.py dynamic_rules.py expression_vector.py variance.py; do
    test -f "$f" || echo "MISSING: $f"
done && echo "PASS"

# AC-3: __init__.py 不含 DIAGNOSTIC PROBE
grep -c "DIAGNOSTIC PROBE" __init__.py
test $(grep -c "DIAGNOSTIC PROBE" __init__.py) -eq 0 && echo "PASS" || echo "FAIL"

# AC-4: __init__.py 含 transform_llm_output 注册
grep -q "transform_llm_output" __init__.py && echo "PASS" || echo "FAIL"

# AC-5: 232 测试全部通过
python -m pytest tests/ -q
# 期望: 232 passed in ...

# AC-6: tests/ 中无残留 hermes_persona. 引用
grep -rn "hermes_persona\." tests/ --include="*.py" | grep -v __pycache__
test $? -ne 0 && echo "PASS" || echo "FAIL"

# AC-7: 根目录源码无旧路径引用
grep -rn "hermes_persona\." *.py 2>/dev/null
test $? -ne 0 && echo "PASS" || echo "FAIL"
```

**验证标准：**
- 全部 7 项 AC 通过
- `python -m pytest tests/ -v` → 232 passed, 0 failure, 0 error
- Hermes 加载流正确：`register()` 可正常调用

#### 7.3 手动冒烟测试

```python
# 验证 register() 函数可正常调用
from pathlib import Path

# 模拟 Hermes PluginContext
class MockCtx:
    profile_path = Path("/tmp/test_profile")
    hooks = {}

    def register_hook(self, name, func):
        self.hooks[name] = func

import __init__ as plugin
ctx = MockCtx()
plugin.register(ctx)

assert "pre_llm_call" in ctx.hooks
assert "transform_llm_output" in ctx.hooks
assert "pre_tool_call" in ctx.hooks
assert "post_tool_call" in ctx.hooks
print("OK: All 4 hooks registered")
```

---

## 3. 风险点与回滚方案

### 3.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|:---|:--:|:--:|:---|
| `sed` 过度匹配替换字符串常量/注释中的 `hermes_persona` | 低 | 低 | 代码中不存在以 `hermes_persona` 命名的变量/字符串；Phase 4 后逐文件验证 |
| 扁平化后 Python 模块查找失败（同名冲突） | 低 | 高 | 根目录无同名文件冲突；`__init__.py` 内 `import injector` 无障碍 |
| 测试中 `patch()` 目标字符串替换不完整 | 中 | 中 | sed 脚本分 4 层递进；第 4 层泛化兜底；全量测试覆盖 |
| Hermes 加载新结构失败 | 低 | 严重 | `plugin.yaml` 无 `module` 字段 → 默认行为完全一致；手工冒烟测试 |
| `__pycache__` 残留导致旧 import 缓存 | 中 | 中 | Phase 5 全校清理；`pytest --import-mode=importlib` 可用作保险 |
| 文档中引用路径替换不完整 | 低 | 低 | docs/ 仅代码块示例涉及；全局 grep 扫描确认 |
| 外部依赖此包名（其他 repo） | 极低 | 极低 | 此项目为独立插件，无外部引用；`plugin.yaml` 配置无 `module` 字段 |

### 3.2 回滚方案

**轻量回滚（单步撤销）：**

| 回滚范围 | 操作 |
|:---|:---|
| 仅源码 | `git checkout HEAD -- injector.py guard.py dynamic_rules.py expression_vector.py variance.py __init__.py` |
| 仅测试 | `git checkout HEAD -- tests/` |
| 仅文档 | `git checkout HEAD -- docs/ AGENTS.md graphify-out/` |
| 恢复旧目录 | `git stash pop` 或 `git checkout HEAD -- hermes_persona/` |

**完整回滚：**

```bash
# 方式 1: git reset（如果尚未 push）
git reset --hard HEAD

# 方式 2: git revert（如果已 push）
git revert HEAD

# 无论哪种方式，验证
python -m pytest tests/ -v
# 期望: 232 PASSED
```

### 3.3 安全边界

- `plugin.yaml` **完全未触碰** — Hermes 加载行为不变
- `guard.py` 功能代码不变 — 仅 `import` 路径 1 行改动
- 注入顺序（①~⑦）不变 — Phase 3/4 仅改 import 路径，不改业务逻辑
- Hook 注册逻辑不变 — `register()` 注册的四个 hook 完全一致
- 所有测试断言不变 — 仅 import 来源路径改变

---

## 4. 验证检查清单

实施完成后的最终验收：

### 4.1 文件结构

- [ ] `hermes_persona/` 目录已删除
- [ ] 根目录存在 `injector.py`、`guard.py`、`dynamic_rules.py`、`expression_vector.py`、`variance.py`
- [ ] 根目录存在 `__init__.py`（唯一入口）
- [ ] `plugin.yaml` 未修改

### 4.2 `__init__.py` 内容

- [ ] 无 DIAGNOSTIC PROBE 代码（`grep -c "DIAGNOSTIC PROBE" __init__.py` = 0）
- [ ] 含 `transform_llm_output` 注册（`grep "transform_llm_output" __init__.py` 有匹配）
- [ ] import 方式为同级导入（`import guard` / `import injector`）
- [ ] docstring 含完整用法说明
- [ ] `register()` 函数签名和逻辑完整

### 4.3 源码导入

- [ ] `injector.py` 中 3 处相对导入已改为同级导入
- [ ] `guard.py` 中 1 处相对导入已改为同级导入
- [ ] 所有 `.py` 文件语法合法（`python -c "import ast; ..."` 通过）

### 4.4 测试

- [ ] `python -m pytest tests/ -v` → 232 passed, 0 failure
- [ ] `grep -rn "hermes_persona\." tests/ --include="*.py"` → 无输出
- [ ] 无 ImportError / ModuleNotFoundError

### 4.5 文档

- [ ] `docs/dev/` 下所有 `.md` 文件中 Python 代码路径已更新
- [ ] `graphify-out/` 已有时间戳更新（`graphify update .` 已运行）

### 4.6 文件变更总览

| 文件 | 操作 | 说明 |
|:---|:---|:---|
| `injector.py` | 移动 + 修改 | `hermes_persona/` → 根目录；3 处 import 改同级 |
| `guard.py` | 移动 + 修改 | `hermes_persona/` → 根目录；1 处 import 改同级 |
| `dynamic_rules.py` | 移动 | `hermes_persona/` → 根目录 |
| `expression_vector.py` | 移动 | `hermes_persona/` → 根目录 |
| `variance.py` | 移动 | `hermes_persona/` → 根目录 |
| `__init__.py` | 替换 | 内层新版内容 - DIAGNOSTIC PROBE |
| `hermes_persona/__init__.py` | 删除 | 随目录一同删除 |
| `hermes_persona/` | 删除 | 整个目录 + `__pycache__/` |
| `tests/conftest.py` | 修改 | 2 处 import 路径 |
| `tests/test_injector.py` | 修改 | 26 处路径 |
| `tests/test_modules_switch.py` | 修改 | 38 处路径 |
| `tests/test_dynamic_rules.py` | 修改 | 10 处路径 |
| `tests/test_guard.py` | 修改 | 4 处路径 |
| `tests/test_variance.py` | 修改 | 2 处路径 |
| `tests/test_expression_vector.py` | 修改 | 1 处路径 |
| `tests/test_fixed_signals.py` | 修改 | 1 处路径 |
| `docs/dev/*.md` | 修改 | 路径引用更新 |
| `graphify-out/` | 更新 | `graphify update .` 重新生成 |
| `plugin.yaml` | **不变** | 无 `module` 字段，默认行为一致 |

---

*CC · 2026-05-20 · PLAN-004 v1.0（基于 SPEC-004 · 82/84 处测试引用精确匹配）· 等待审阅*
