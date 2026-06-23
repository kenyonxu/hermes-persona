# Hermes Desktop/TUI 插件加载缺陷诊断

> 诊断日期：2026-06-21 18:26 | 诊断人：主人 Kai + 知惠
> 存档日期：2026-06-22
> 影响：hermes-persona 在 Hermes Desktop/TUI 环境下静默失效

---

## 现象

hermes-persona 在 Discord Gateway 环境下正常工作（天气注入、静态规则、动态规则、表达向量全部生效），但在 Hermes Desktop / TUI 环境下完全静默失效——系统提示中没有 persona 注入的任何内容。

---

## 根因

> **⚠️ 2026-06-22 Codex (GLM 5.2) 核实：以下原诊断不成立。真根因见 `docs/superpowers/specs/2026-06-22-fix-desktop-tui-plugin-discovery.md`**

**真根因（Codex 核实）**：`PluginManager._discovered` 是进程级锁存——首次 import `model_tools` 触发扫描后永久短路。TUI 是多会话长生命进程，首个 session 若用了默认 home → persona 不在默认 home → 永久失效。Gateway 正常是因为它是单 profile 进程。

**修复**：`tui_gateway/server.py` 的 `_make_agent` 顶部检测 HERMES_HOME 变化，变化时 `discover_plugins(force=True)`。

---

## ~~原诊断（已被推翻，仅供存档）~~

~~`tui_gateway/server.py` 第 2004-2018 行~~：

```python
if explicit and validate_toolset is not None:
    built_in = [name for name in explicit if validate_toolset(name)]
    unresolved = [name for name in explicit if name not in built_in]

    if unresolved:  # ← 只在有 unresolved toolsets 时才触发
        try:
            from hermes_cli.plugins import discover_plugins
            discover_plugins()
```

`discover_plugins()` 只在**显式设置了 toolsets 且有未解析项**时才被调用。而 Gateway（`gateway/run.py`）在构建 AIAgent 前**无条件**调用 `discover_plugins()`。

Hermes persona 插件通过 `plugin.yaml` 注册 `pre_llm_call` hook。如果 `discover_plugins()` 没被调用，插件的 hook 就不会注册到 Hermes 的 hook 系统中——persona 的所有模块（时间、天气、静态规则、动态规则、表达向量）全部静默失效。

---

## 修复方向

在 TUI/Desktop 的 AIAgent 构建前，无条件调用 `discover_plugins()`，与 Gateway 行为对齐。

参考 Gateway 的实现模式：`gateway/run.py` 中 `discover_plugins()` 的调用位置——在 agent 实例化之前，无条件执行。

---

## 相关文件

| 文件 | 位置 | 说明 |
|------|------|------|
| `tui_gateway/server.py` | L2004-2018 | 缺陷所在——条件调用 |
| `gateway/run.py` | agent 构建前 | 正确示范——无条件调用 |
| `hermes-persona/plugin.yaml` | hooks 声明 | 注册 pre_llm_call |
| `hermes_cli/plugins.py` | `discover_plugins()` | 插件发现入口 |

---

## 附加发现（同日诊断）

1. **`time.enabled=false` 是空操作**：`_is_enabled()` 只检查 `modules.time`，不检查 `time.enabled` 子字段
2. **两处插件位置**：`~/.hermes/plugins/00-proxy/`（全局）+ profile 专属目录——两者都需被 `discover_plugins()` 覆盖
