# FIX-001: transform_llm_output debug 块未拼接到 LLM 输出末尾

**日期**: 2026-05-19  
**作者**: Kai.Xu  
**关联**: [SPEC-003](./SPEC-003-debug-rich-i18n.md)

---

## 1. 现象

`plugin.yaml` 声明了 `transform_llm_output` 钩子，Python 侧注册也正确，但 `debug` 开启后，没有任何调试摘要被拼接到 LLM 回复末尾——用户连指令文本都看不到。

## 2. 诊断过程

### 2.1 钩子注册

`hermes-persona` 侧注册正确（[injector.py:35-36](../../hermes_persona/injector.py)）：

```python
ctx.register_hook("pre_llm_call", injector.inject_context)
ctx.register_hook("transform_llm_output", injector.transform_llm_output)
```

`hermes-agent` 侧调用正确（[conversation_loop.py:3941-3960](../../../hermes-agent/agent/conversation_loop.py)）：`transform_llm_output` 在工具调用循环结束后触发，"first non-empty string wins" 语义替换 `final_response`。

### 2.2 数据流追踪

`inject_context`（`pre_llm_call`）设置 `_PENDING_DEBUG_BLOCK` → `transform_llm_output` 读取并拼接。两个函数在同一模块内共享模块级变量，不存在进程隔离问题。

### 2.3 定位

关键点在 `inject_context` 的 `visible` 判断逻辑：

```python
debug_cfg = modules.get("debug", {})
visible = isinstance(debug_cfg, dict) and debug_cfg.get("visible", False)
```

## 3. 根因

两重 Bug：

### Bug 1：布尔 `true` 被错误路由到系统提示

用户写成 `"debug": true`（布尔值）时：

- `isinstance(True, dict)` → `False` → `visible = False`
- debug 摘要被 `parts.append(summary)` **注入到系统提示**，LLM 看得到但用户看不到
- `_PENDING_DEBUG_BLOCK` 保持 `None` → `transform_llm_output` 返回 `None` → 无拼接

只有写成 `"debug": {"visible": true}` 才走可靠路径。

### Bug 2：`_debug_summary` 返回格式错误

当 `visible=True` 时，`_debug_summary` 返回的是**要求 LLM 回显的提示指令**，而不是干净的调试摘要。该指令被直接拼接到用户输出，格式完全不对。

### 根因本质

`visible` 参数是旧方案的遗留——旧方案有两个路径：

- `visible=True`：包装回显指令 → 注入系统提示 → LLM 回显（不可靠）
- `visible=False`：清洁摘要 → 注入系统提示 → 内部备忘

新方案（`_PENDING_DEBUG_BLOCK` + `transform_llm_output`）直接拼接，绕过 LLM。「内部备忘」路径已无存在价值——不想看 debug 直接关掉即可。

## 4. 修复方案

移除 `visible` 参数，统一路径：`debug` 启用 → `_PENDING_DEBUG_BLOCK` → `transform_llm_output` 拼接。禁用即什么都不做。

### 修改清单

| 文件 | 位置 | 修改 |
|------|------|------|
| `hermes_persona/injector.py` | `_debug_summary()` | 删除 `debug_cfg`/`visible` 局部变量；删除 `if visible: return 回显指令` 分支；始终返回 `"\n".join(lines)` |
| `hermes_persona/injector.py` | `inject_context()` §7 | 删除 `visible` 判断 + `parts.append` 分支；`debug` 启用即写 `_PENDING_DEBUG_BLOCK`（12 行 → 4 行） |
| `tests/test_modules_switch.py` | `TestDebugMode` | `test_debug_enabled_appends_summary` 和 `test_debug_memory_disabled_shows_stopped` 从检查 `result["context"]` 改为检查 `_PENDING_DEBUG_BLOCK` |

### 修复后代码

```python
# 7. Debug summary → stored to _PENDING_DEBUG_BLOCK, appended by transform_llm_output
global _PENDING_DEBUG_BLOCK
_PENDING_DEBUG_BLOCK = None
if _is_enabled(modules, "debug"):
    _PENDING_DEBUG_BLOCK = f"\n\n---\n{_debug_summary(modules, parts, var_count=var_count)}"
```

```python
def _debug_summary(modules: dict, parts: list[str], var_count: int = 0) -> str:
    """Generate a human-readable injection summary for debug mode.

    The summary is formatted for direct display. When debug is enabled,
    it is appended to the LLM output by transform_llm_output.
    """
    lines = ["🔧 [Debug] 本轮注入:"]
    # ... build lines ...
    return "\n".join(lines)
```

## 5. 行为变化

| 配置 | 修复前 | 修复后 |
|------|--------|--------|
| `"debug": true` | 注入系统提示（用户不可见） | 拼接到 LLM 输出末尾 |
| `"debug": {"visible": true}` | 拼接回显指令（格式错误） | 拼接到 LLM 输出末尾 |
| `"debug": {"visible": false}` | 注入系统提示 | 拼接到 LLM 输出末尾 |
| `"debug": false` | 禁用 | 禁用（不变） |

`visible` 子键不再需要，将被忽略。所有 `debug: true` 的变体行为统一。

## 6. 验证

```bash
python -m pytest tests/ -v    # 232 passed
python -m pytest /home/kai-remote/github/hermes-agent/tests/test_transform_llm_output_hook.py -v  # 6 passed
```
