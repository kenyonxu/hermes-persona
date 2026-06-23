# Hermes Desktop/TUI 插件发现修复 SPEC

> 核实日期：2026-06-22 | 核实工具：Codex (GLM 5.2) | 诊断文档：docs/2026-06-21-desktop-tui-plugin-silent-failure.md

---

## 核实结论：原诊断不成立

原诊断将失效归因于 `tui_gateway/server.py` L2004-2018 的"条件调用 `discover_plugins()`"。实测推翻：

1. `model_tools.py` L196-199 存在**模块级 `discover_plugins()` 副作用**——首次 import 即触发
2. TUI 路径实际调用了 `discover_plugins()`，persona 能被发现
3. L2004-2018 负责的是按名解析 plugin toolset，与 persona 的 hook 注册无关

---

## 真根因：幂等锁存 × HERMES_HOME 时序

```
┌─────────────────────────────────────────────────┐
│ PluginManager._discovered  ← 进程级锁存（TRUE后永不再扫）│
│ 首次 import model_tools 触发扫描 → 锁定当前 HERMES_HOME │
└─────────────────────────────────────────────────┘
```

- **TUI**：长生命多会话进程。首个 `_make_agent` 可能触发在默认 home → persona 不在默认 home → 永久失效
- **Gateway**：单 profile 进程，启动期一次性发现 → 命中正确 home → 正常

---

## 修复方案

仅改 `tui_gateway/server.py` 一个文件：

在 `_make_agent` 顶部添加 home 变更感知：

```python
_home = get_hermes_home()
if _home != _last_discovery_home:
    discover_plugins(force=True)
    _last_discovery_home = _home
```

实测三段会话（默认→zhihui→默认）persona 加载性正确翻转，同 home 不重复重扫。

---

## 验收标准

1. Desktop/TUI 下 persona 注入生效（时间、天气、规则全部出现）
2. 多次切换 profile 后 persona 仍正确加载
3. 同 profile 多次对话不重复触发 `force`
4. Gateway 行为不受影响
5. 单 session 性能无退化

---

## 影响范围

- 仅 `tui_gateway/server.py` 一个文件
- 不影响 Gateway、CLI、插件 API
- 并发：当前 TUI 单活跃会话模型下安全

---

## 与原诊断差异

| 维度 | 原诊断 | Codex 核实 |
|------|--------|-----------|
| 根因 | 条件调用 `discover_plugins()` | 进程级锁存 + HOME 时序 |
| 修法 | 无条件调用 | `force=True` + HOME 变更检测 |
| 有效性 | 无效（幂等短路） | 已验证通过 |
