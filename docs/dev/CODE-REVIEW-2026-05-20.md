# hermes-persona 全面代码审查报告

> 审查日期：2026-05-20 | 审查范围：根目录 .py / tests/ / scripts/ / plugin.yaml
> 当前分支：feature/001-module-switch | 测试结果：232 passed

---

## 🔴 严重问题

### CR-001 — benchmark.py 导入路径断裂（禁止合并）

**文件：** `scripts/benchmark.py:25`
**状态：** 🔴 阻断

```python
from hermes_persona import injector  # noqa: E402
```

目录扁平化（`dcb2e3f`）后 `hermes_persona/` 目录已不存在，导入失败：

```
ModuleNotFoundError: No module named 'hermes_persona'
```

**修复：** 改为 `import injector`。

---

### CR-002 — `_fmt_variance_status()` 死代码 + 内部逻辑缺陷

**文件：** `injector.py:348-367`
**状态：** 🔴 功能缺陷 + 无用代码

该函数定义后**从未被任何调用方引用**（grep 全部 .py 文件仅找到定义）。此外，其内部循环体仅含 `continue` 语句，`variance_items` 永远为空列表，即使被调用也必定返回 `"无注入"`。

```python
variance_items = []
for part in parts:
    if not isinstance(part, str):
        continue
    if part.startswith("🕐") or part.startswith("📝") or part.startswith("📋"):
        continue
    if part.startswith("🕐 [") or part.startswith("💬 ["):
        continue
    # ← 这里从未向 variance_items 追加任何内容
if variance_items:  # 永远为 False
    ...
return "无注入"
```

SPEC-001 曾规划此函数用于 Debug 摘要，但实际 `_debug_summary()` 实现采用了内联逻辑（`②a Fixed signals` / `②b Expression vector`），此函数被遗弃。

**修复：** 删除此函数，或修复循环逻辑后接入 `_debug_summary()`。

---

### CR-003 — `_daily_turn_count_hint()` 中 `{profile}` 占位符未替换

**文件：** `injector.py:489-493`
**状态：** 🔴 运行时缺陷

```python
raw_path = dc_cfg.get(
    "storage_path",
    "~/.hermes/profiles/{profile}/state/daily_turn_count.json",
)
storage_path = Path(raw_path).expanduser()
```

对比 `expression_vector.py:52` 中 `_ExpressionVector.__init__()` 正确处理了 `{profile}` 替换：

```python
if profile_path:
    raw_path = raw_path.replace("{profile}", str(profile_path))
```

`_daily_turn_count_hint()` 缺失此替换逻辑：`{profile}` 会作为字面量出现在文件系统路径中（如 `~/.hermes/profiles/{profile}/state/daily_turn_count.json`），不同 profile 的数据写入同一文件，导致每日轮数计数紊乱。

**修复：** 从 kwargs 提取 profile_path 参数并执行 `{profile}` 替换。

---

### CR-004 — `TestCodeGeneric` 测试虚通过（零覆盖）

**文件：** `tests/test_injector.py:216-226`
**状态：** 🔴 假阴性测试

```python
py_files = glob.glob("hermes_persona/**/*.py", recursive=True)
for py_file in py_files:
    content = Path(py_file).read_text(encoding="utf-8")
    assert term not in content, ...
```

目录扁平化后 `hermes_persona/` 不存在，`glob` 返回空列表，循环体从不执行，所有 parametrized 断言**永远通过但不检查任何文件**。

**修复：** 将 glob 模式改为 `*.py` 以匹配扁平结构。

---

## 🟡 建议改进

### CR-005 — guard.py 未检查工具参数，路径穿越防护缺失

**文件：** `guard.py:55-103`
**说明：** `check_tool_call(tool_name, args, **kwargs)` 接收 `args` 参数但完全未使用。防护仅基于 `tool_name` 的正则匹配。

- 若 `tool_name` 值为 `"Write"`（不含参数），`args` 中的 `{"file_path": "../../.bashrc"}` 完全不会被检查。
- 当前测试用 `"Bash(rm -rf /)"` 作为 tool_name，说明 Hermes 运行时可能将命令拼入 tool_name，但并不覆盖所有场景。

**建议：** 在 blocked 规则中加入可选的 `arg_patterns` 字段（如 `{"arg": "file_path", "pattern": r"\.\.[/\\\\]"}`），对参数值进行路径穿越检测。

---

### CR-006 — `_PENDING_DEBUG_BLOCK` 全局状态非线程安全

**文件：** `injector.py:27,743-746`
**说明：** `_PENDING_DEBUG_BLOCK` 是模块级 `global` 变量，在 `inject_context()` 中设置，在 `transform_llm_output()` 中消费。若两个并发调用交叉执行，debug 块可能写入错误的 session 回复。

当前 Hermes 为单 session 运行时不存在此问题，但作为插件库应标注线程不安全假设。

**建议：** 在 docstring 中显式声明 "not thread-safe"，或未来改为 session-keyed dict。

---

### CR-007 — `_resolve_modules()` 过度宽泛的异常捕获

**文件：** `injector.py:143-144`
**说明：** `except Exception: return {}` 会静默吞掉编程错误（如 `KeyError`、`TypeError`），使问题难以诊断。该函数仅做字典操作，预期不会出现无法预料的异常类型。

**建议：** 将 `except Exception` 收紧为 `except (TypeError, KeyError, AttributeError)`。

---

### CR-008 — dynamic_rules.py 缺失 `from __future__ import annotations`

**文件：** `dynamic_rules.py:1`
**说明：** 其他 5 个 .py 文件均包含此行，`dynamic_rules.py` 是唯一的遗漏。不影响运行（Python 3.10+），但破坏了代码风格一致性。

**建议：** 添加 `from __future__ import annotations`。

---

### CR-009 — `_debug_summary()` 内联 import

**文件：** `injector.py:391`

```python
ev_hit = any("📊 [表达向量]" in p for p in parts)
if ev_hit:
    import re  # ← 函数体内 import
```

此处 `import re` 应移至文件顶部。`re` 是标准库，且在 `dynamic_rules.py` / `guard.py` 中已使用。内联 import 为热路径引入不必要的条件 import 开销。

**建议：** 将 `import re` 移至文件顶部。

---

### CR-010 — 审计日志多进程并发写入无保护

**文件：** `guard.py:160-161`
**说明：** `audit_tool_call()` 每次调用都执行 `open(log_path, "a")` 然后 `f.write()`。操作系统对 `O_APPEND` 的原子性保证仅适用于单次 `write()` 调用 ≤ `PIPE_BUF` 字节，但两个进程同时 `open`+`write`+`close` 仍可能导致行交错。对安全审计场景不可接受。

**建议：** 使用 `fcntl.flock()` 文件锁或改用每条日志独立文件（如每日轮转）。

---

### CR-011 — `_read_kanban()` 的 `split("\n")[0]` 对空文件行为边界

**文件：** `injector.py:611`

```python
first_line = md_file.read_text(encoding="utf-8").split("\n")[0].strip()
```

空文件读取后 `split("\n")` 返回 `[""]`，`[0]` 取到 `""`，`strip()` 返回 `""`，`if "优先级:" in ""` 为 False → 跳过。行为正确但依赖非显而易见的逻辑链。

**建议：** 不改行为，但加一行注释说明空文件安全。

---

### CR-012 — conftest.py 注释残留旧路径名

**文件：** `tests/conftest.py:1`
**说明：** 模块 docstring 仍写 `"Shared test fixtures for hermes_persona tests."`，扁平化后已不准确。

**建议：** 改为 `"Shared test fixtures for hermes-persona tests."` 或直接删除。

---

### CR-013 — `transform_llm_output` 诊断探针应予移除

**文件：** `injector.py:772-779`

```python
# ── DIAGNOSTIC PROBE ── remove after hook confirmed working
try:
    with open("/tmp/transform_llm_trace.txt", "a") as f:
        f.write(f"CALLED|session={session_id}|pending={'YES' if _PENDING_DEBUG_BLOCK else 'NO'}\n")
except Exception:
    pass
# ── END PROBE ──
```

注释明确标注 "remove after hook confirmed working"。现已进入稳定阶段，此探针应移除，避免生产环境写入 `/tmp`。

---

### CR-014 — `__init__.py` 中 `import guard` 存在隐式模块依赖

**文件：** `__init__.py:12` → `guard.py:31`

```
__init__.py → import guard
             → import injector (line 12)
guard.py    → from injector import _CONFIG_ROOT (line 31)
```

形成 `__init__` → `guard` → `injector` 的双向导入链。实际工作中 `injector` 先被 `__init__.py` 导入（line 13），`_CONFIG_ROOT` 在模块级已定义，所以 `guard.py` 的 import 可以工作。但这是脆弱的隐式依赖，未来重构可能触及。

**建议：** 将 `_CONFIG_ROOT` 提取到独立的 `config.py` 模块。

---

## 🟢 表扬

### CR-015 — 测试覆盖全面且系统性

232 个测试全部通过，覆盖：
- **模块开关系统**：30 个测试，含新格式/旧格式兼容/边界条件
- **注入器**：60+ 个测试，覆盖全部注入阶段和集成场景
- **表达向量**：20+ 个测试，含算法正确性/重置策略/持久化/格式化
- **动态规则**：30+ 个测试，含时间槽/轮次阶段/关键词匹配
- **安全护栏**：20+ 个测试，含 blocked/confirm/audit/边界条件
- **固定信号**：9 个测试，含消息长度/回复间隔/日轮数
- **方差**：12 个测试，含统计分布验证

### CR-016 — Fail-Open 设计哲学一致

每个模块的异常处理均遵循 "失败不阻断后续" 原则：
- `_load_config()` → `except` → `{}`
- `_recall_memories()` → `except` → `None`
- `_read_kanban()` → `except` → `None`
- `inject_context()` 顶层 → `except` → `None`
- `audit_tool_call()` → `except` → `pass`

正确选择——人格注入插件永远不应成为 Agent 的单点故障。

### CR-017 — 表达向量引擎设计精良

`expression_vector.py` 的 `_ExpressionVector` 类：
- 多维度关键词匹配 + 加权累加 + 自动衰减
- 三种重置策略（session/daily/none）
- 磁盘持久化含版本号校验
- 维度动态新增/删除的优雅处理
- 所有故障模式静默降级

### CR-018 — 配置向后兼容设计得当

`_resolve_modules()` 的新格式优先 + 旧格式合成的双通道设计，配合 7 个测试验证：

| 场景 | 行为 |
|------|------|
| `modules` key 存在 | 直接用新格式 |
| 无 `modules`，有 `time.enabled` | 合成 `modules["time"]` |
| 无 `modules`，有 `memory.enabled` | 合成 `modules["memory"]` |
| 无 `modules`，有 `project.enabled` | 合成 `modules["kanban"]` |
| 两者都有 | `modules` 获胜 |

### CR-019 — 代码命名规范清晰

函数命名遵循一致的约定：`_` 前缀表私有，动词精确（`_select_` / `_match_` / `_resolve_` / `_inject_`）。中英文注释混用虽然不传统，但在本项目场景下合理（中文面向中国用户，代码标识符保持英文）。

### CR-020 — plugin.yaml 声明完整

```yaml
provides_hooks:
  - pre_llm_call
  - transform_llm_output
  - pre_tool_call
  - post_tool_call
```

四个 hook 声明与实际注册完全一致。

---

## 统计摘要

| 严重度 | 数量 | 文件 |
|--------|------|------|
| 🔴 严重 | 4 | benchmark.py, injector.py, tests/test_injector.py |
| 🟡 建议 | 10 | guard.py, injector.py, dynamic_rules.py, __init__.py, conftest.py |
| 🟢 表扬 | 6 | 全部文件 |

### 修复优先级

1. **P0（阻断合并）：** CR-001（benchmark 导入断裂）
2. **P1（合并前修复）：** CR-003（`{profile}` 未替换）、CR-004（测试虚通过）
3. **P2（下个迭代）：** CR-002（死代码删除）、CR-013（诊断探针移除）
4. **P3（技术债）：** CR-005 ~ CR-012、CR-014
