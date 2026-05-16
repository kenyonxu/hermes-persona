# hermes-persona 实施计划

> 版本：v1.0
> 日期：2026-05-16
> 基于：`specs/hermes-persona-spec.md` v1.0

---

## 零、总体任务依赖图

```
P1-T1 (plugin.yaml)
  ├── P1-T2 (__init__.py)
  ├── P1-T3 (injector.py 基础)
  │     └── P1-T6 (inject_context 主流程组装) ────┬── P1-T7 (P1 测试)
  ├── P1-T4 (dynamic_rules.py) ──────────────────┘
  ├── P1-T5 (variance.py / guard.py 桩)

P1 完成 ───┬── P2-T1 (关键词匹配 _match_keyword)
           │     └── P2-T4 (接入 inject_context)
           ├── P2-T2 (随机变化 _randomize_variance)
           │     └── P2-T4 (接入 inject_context)
           ├── P2-T3 (记忆召回 _recall_memories)
           │     └── P2-T4 (接入 inject_context)
           └── P2-T5 (P2 测试)

P2 完成 ─── P3-T1 (看板 _read_kanban) → P3-T2 (P3 测试)

P1 完成 ─── P4-T1 (guard.py 完整实现) → P4-T2 (guard 配置 + 测试)

P1-P4 完成 ─── P5-T1~T5 (文档/测试/示例/基准)
```

---

## 一、关键设计决策落地方案

### D1: 配置文件定位策略

**问题**：`injector.py` 如何找到 `persona-config.json`？

**方案**：通过 `register(ctx)` 从 Hermes PluginContext 获取 profile 路径，存入模块级变量 `_CONFIG_ROOT`。`_load_config()` 从 `_CONFIG_ROOT / "persona-config.json"` 读取。

```python
# injector.py 模块级变量
_CONFIG_ROOT: Path | None = None

# __init__.py
def register(ctx):
    global _CONFIG_ROOT
    _CONFIG_ROOT = Path(ctx.profile_path)  # Hermes 注入
```

**降级策略**：若 `_CONFIG_ROOT` 为 None（独立测试等场景），回退到 `Path(__file__).resolve().parents[3] / "persona-config.json"`。

### D2: 规则注入顺序 (不可变)

```
时间 → 静态规则 → 首轮规则 → 时段规则 → 轮数规则 → 关键词规则 → 随机变化 → 记忆召回 → 看板
```

各层只追加不覆盖，用 `\n\n` 拼接。

### D3: 配置降级策略

| 异常场景 | 降级行为 |
|:---|:---|
| 配置文件不存在 | 返回 `{}`，仅时间注入生效 |
| JSON 格式错误 | 返回 `{}`，静默不抛异常 |
| 配置字段类型不匹配 | 按默认值处理（如 `"yes"` → `true`） |
| 记忆 API 不可达 | 返回 `None`，不影响正常流程 |
| 看板路径不存在 | 返回 `None`，不影响正常流程 |

### D4: 轮数计算

`turn_count = len(conversation_history) // 2`（每轮 = user + assistant）。`conversation_history` 为 `None`/`[]` 时 `turn_count = 0`。

### D5: 时段匹配跨午夜

```
if start <= end:   start <= now < end
else (跨午夜):     now >= start or now < end
```

### D6: 轮数阶段匹配策略

从最高阈值向最低阈值匹配，取第一个满足 `turn_count >= threshold` 的，避免同时命中多个阶段。

### D7: 关键词匹配策略

按配置顺序匹配，**命中第一个模式即停止**，不继续匹配后续模式。

### D8: 随机表达两层随机

1. **出现概率** (`probability`)：`random.random() < prob` 决定本维度是否使用
2. **表达变化** (`variants`)：`random.choice(variants)` 从变体中随机选一条

两层独立随机，每回合各维度独立决策。

### D9: 看板注入时机

仅 `is_first_turn=True` 且 `project.enabled=True` 时注入。避免重复注入。

---

## 二、P1 — 最小可用原型

**目标**：时间注入 + 静态规则 + 时段/轮数动态规则 + 配置加载。空配置 `{}` 即可工作。

### P1-T1: 创建 plugin.yaml

| 属性 | 值 |
|:---|:---|
| **文件** | `~/.hermes/plugins/00-hermes-persona/plugin.yaml` |
| **依赖** | 无 |
| **预估行数** | ~15 |

**核心逻辑**：
- 声明插件名称、版本、描述、作者
- 声明 hooks: `pre_llm_call`（P1 唯一注册的 hook）
- 声明 skills: `persona-methodology`
- `pre_tool_call` / `post_tool_call` 在 yaml 中列出但标注 P4，P1 阶段不注册

```yaml
name: hermes-persona
version: 0.1.0
description: Dynamic persona context injection engine for Hermes Agent
author: Kai.Xu & Zhihui
provides_hooks:
  - pre_llm_call
  - pre_tool_call       # P4
  - post_tool_call      # P4
provides_skills:
  - persona-methodology
```

---

### P1-T2: 实现 __init__.py 插件入口

| 属性 | 值 |
|:---|:---|
| **文件** | `__init__.py` |
| **依赖** | P1-T1 (plugin.yaml 需存在) |
| **新增函数** | `register(ctx)` |
| **预估行数** | ~35 |

**核心逻辑**：
1. `register(ctx)` 接收 Hermes PluginContext
2. 从 `ctx.profile_path` 获取 profile 目录路径
3. 将路径写入 `injector._CONFIG_ROOT` 模块级变量（供 `_load_config()` 使用）
4. 调用 `ctx.register_hook("pre_llm_call", injector.inject_context)`
5. P1 阶段不注册 `pre_tool_call` / `post_tool_call`

**容错**：`ctx.profile_path` 不存在时，`_CONFIG_ROOT` 保持 None，由 injector 的降级逻辑处理。

---

### P1-T3: 实现 injector.py 基础函数

| 属性 | 值 |
|:---|:---|
| **文件** | `injector.py` |
| **依赖** | P1-T2（需要 _CONFIG_ROOT 变量约定） |
| **新增函数** | `_load_config()`, `_time_context(fmt)`, `_inject_static_rules(ctx_cfg, is_first_turn)` |
| **新增桩函数** | `_recall_memories(msg, mem_cfg)` → 返回 `None`, `_read_kanban(path, label)` → 返回 `None` |
| **预估行数** | ~100 |

#### P1-T3a: `_load_config()` — 配置加载器 (~30 行)

```python
def _load_config() -> dict:
    """
    加载 persona-config.json，返回 config["hermes-persona"]。
    失败时返回 {}（降级为最小可用模式）。
    """
```

**核心逻辑**：
1. 优先从 `_CONFIG_ROOT / "persona-config.json"` 读取
2. `_CONFIG_ROOT` 为 None 时回退到 `Path(__file__).resolve().parents[3] / "persona-config.json"`
3. 文件不存在 → 返回 `{}`
4. JSON 解析失败 → 返回 `{}`
5. 返回 `data.get("hermes-persona", {})`，忽略未知顶层 key

#### P1-T3b: `_time_context(fmt)` — 时间生成器 (~30 行)

```python
def _time_context(fmt: str = "cn_full") -> str:
    """
    生成当前时间描述字符串。
    - "cn_full":  "🕐 2026年5月16日 周五 14:30"
    - "iso":      "🕐 2026-05-16T14:30:00"
    - "compact":  "🕐 05/16 14:30"
    """
```

**核心逻辑**：
1. `datetime.now()` 获取当前时间
2. `cn_full`：中文星期映射 `["一","二","三","四","五","六","日"]`
3. `iso`：`datetime.now().isoformat()`
4. `compact`：`strftime('%m/%d %H:%M')`
5. 未知 format → 降级为 `cn_full`

#### P1-T3c: `_inject_static_rules(ctx_cfg, is_first_turn)` — 静态规则注入 (~20 行)

```python
def _inject_static_rules(ctx_cfg: dict, is_first_turn: bool) -> list[str]:
    """
    从 context.rules 和 context.rules_first_turn_only 中提取规则列表。
    """
```

**核心逻辑**：
1. 从 `ctx_cfg.get("rules", [])` 获取静态规则
2. 若 `is_first_turn` 为 True，追加 `ctx_cfg.get("rules_first_turn_only", [])`
3. 两项均为空时返回 `[]`

#### P1-T3d: `_recall_memories()` / `_read_kanban()` 桩 (~10 行)

两个函数均返回 `None`，为 P2/P3 预留接口。签名与 spec 3.3.2 完全一致。

---

### P1-T4: 实现 dynamic_rules.py

| 属性 | 值 |
|:---|:---|
| **文件** | `dynamic_rules.py` |
| **依赖** | 无 |
| **新增函数** | `_select_dynamic_rules()`, `_match_time_slot()`, `_match_turn_stage()`, `_in_time_range()` |
| **新增桩函数** | `_match_keyword(keywords, user_message)` → 返回 `[]` |
| **预估行数** | ~100 |

#### P1-T4a: `_select_dynamic_rules()` — 动态规则调度器 (~20 行)

```python
def _select_dynamic_rules(
    dynamic_cfg: dict,
    user_message: str,
    is_first_turn: bool,
    turn_count: int,
) -> list[str]:
    """
    按时间 / 轮数 / 关键词三个维度选择动态规则。
    P1 实现：time_slots + turn_stage；P2 加上 keyword。
    返回规则字符串列表，供 inject_context 拼接。
    """
```

**核心逻辑**：
1. `rules = []`
2. `rules.extend(_match_time_slot(dynamic_cfg.get("time_slots", {})))`
3. `rules.extend(_match_turn_stage(dynamic_cfg.get("turn_stage", {}), is_first_turn, turn_count))`
4. `# rules.extend(_match_keyword(...))  # P2`
5. 返回 `rules`

#### P1-T4b: `_match_time_slot()` — 时段匹配 (~25 行)

```python
def _match_time_slot(time_slots: dict) -> list[str]:
    """
    time_slots: {"22:00-05:00": ["规则A", "规则B"], "09:00-17:00": [...]}
    行为：用 datetime.now().strftime("%H:%M") 匹配区间
    输出：命中规则的带前缀列表 ["🕐 [22:00-05:00] 规则A", ...]
    """
```

**核心逻辑**：
1. `now = datetime.now().strftime("%H:%M")`
2. 遍历 `time_slots` items
3. 对每个 key 按 `"-"` 分割得到 `start, end`
4. 调用 `_in_time_range(now, start, end)` 判断是否命中
5. 命中后为每条规则添加 `🕐 [slot_range] ` 前缀
6. 分割失败（ValueError）→ 跳过该 slot

#### P1-T4c: `_in_time_range()` — 区间判断 (~15 行)

```python
def _in_time_range(now: str, start: str, end: str) -> bool:
    """
    判断 now(HH:MM) 是否在 [start, end) 区间内。
    支持跨午夜：start="22:00", end="05:00" → now>=22:00 or now<05:00
    """
```

**核心逻辑**：
1. 字符串比较（HH:MM 格式天然支持字典序比较）
2. `if start <= end`: `start <= now < end`
3. `else (跨午夜)`: `now >= start or now < end`

#### P1-T4d: `_match_turn_stage()` — 轮数阶段匹配 (~25 行)

```python
def _match_turn_stage(turn_stages: dict, is_first_turn: bool, turn_count: int) -> list[str]:
    """
    turn_stages: {"first_turn": [...], "after_10": [...], "after_30": [...]}
    行为：
      1. is_first_turn=True 时注入 "first_turn" 规则
      2. 按阈值从高到低匹配 "after_N"，取第一个满足 turn_count >= N 的
    """
```

**核心逻辑**：
1. 若 `is_first_turn` 且 `"first_turn"` in dict → 添加对应规则
2. 收集所有 `"after_N"` key，按 N 降序排序
3. 遍历降序列表，第一个满足 `turn_count >= N` 的 → 添加规则并 break
4. 整数解析失败（如 `"after_xyz"`）→ 跳过该 key

#### P1-T4e: `_match_keyword()` 桩 (~10 行)

返回 `[]`，完整实现留给 P2-T1。

---

### P1-T5: 创建 variance.py / guard.py 桩文件

| 属性 | 值 |
|:---|:---|
| **文件** | `variance.py`, `guard.py` |
| **依赖** | 无 |
| **预估行数** | ~15 每个 |

**variance.py 桩**：
```python
def _randomize_variance(variance_cfg: dict) -> list[str]:
    """P2 实现。当前返回 []。"""
    return []
```

**guard.py 桩**：
```python
def check_tool_call(tool_name, tool_args, **kwargs):
    """P4 实现。当前返回 None。"""
    return None

def audit_tool_call(tool_name, tool_args, result, **kwargs):
    """P4 实现。当前无操作。"""
    pass
```

---

### P1-T6: 实现 inject_context() 主流程组装

| 属性 | 值 |
|:---|:---|
| **文件** | `injector.py`（追加主入口函数） |
| **依赖** | P1-T3 + P1-T4（需要前四个任务的所有函数） |
| **新增函数** | `inject_context()` |
| **预估行数** | ~55 |

```python
def inject_context(
    session_id: str,
    user_message: str,
    conversation_history: list[dict],
    is_first_turn: bool,
    model: str,
    platform: str,
    **kwargs,
) -> dict | None:
    """
    每回合由 Hermes Runtime 调用，返回动态人格上下文。
    返回 {"context": "..."} 或 None（无内容时）。
    """
```

**核心逻辑**（严格按 D2 顺序）：
1. `config = _load_config()`
2. `parts = []`
3. ① 时间：若 `time.enabled` != False → `parts.append(_time_context(fmt))`
4. ② 静态规则：`parts.extend(_inject_static_rules(ctx_cfg, is_first_turn))`
5. ③ 动态规则：`turn_count = len(conversation_history or []) // 2`，调用 `_select_dynamic_rules()`
6. ④ 随机变化（桩，P2）：`parts.extend(_randomize_variance(config.get("variance", {})))`
7. ⑤ 记忆召回（桩，P2）：调用 `_recall_memories()`，非 None 则追加
8. ⑥ 看板（桩，P3）：若 `is_first_turn`，调用 `_read_kanban()`，非 None 则追加
9. `parts` 为空 → 返回 `None`
10. 返回 `{"context": "\n\n".join(parts)}`

**容错**：整个函数体包裹 try-except，任何异常返回 `None`（不阻塞 Agent 正常流程）。

---

### P1-T7: P1 单元测试

| 属性 | 值 |
|:---|:---|
| **文件** | `tests/test_injector.py`, `tests/test_dynamic_rules.py` |
| **依赖** | P1-T1~T6 |
| **预估行数** | ~150 + ~180 |

#### tests/test_injector.py 测试用例

| 用例 | 场景 | 预期 |
|:---|:---|:---|
| `test_empty_config` | `_load_config()` 返回 `{}` | `inject_context()` 仅返回时间上下文 |
| `test_config_not_found` | 配置文件不存在 | 降级为 `{}`，不抛异常 |
| `test_malformed_json` | JSON 格式错误 | 降级为 `{}`，不抛异常 |
| `test_time_cn_full` | `format="cn_full"` | 包含年月日周时分的完整中文 |
| `test_time_iso` | `format="iso"` | ISO8601 格式 |
| `test_time_compact` | `format="compact"` | MM/DD HH:MM 格式 |
| `test_time_disabled` | `time.enabled=false` | 不包含时间行 |
| `test_static_rules_every_turn` | `context.rules` 有值 | 每回合均包含 |
| `test_rules_first_turn_only` | `is_first_turn=True` vs `False` | 仅首轮包含 first_turn 规则 |
| `test_history_none` | `conversation_history=None` | 不崩溃，turn_count=0 |
| `test_history_empty` | `conversation_history=[]` | 不崩溃，turn_count=0 |
| `test_no_parts_returns_none` | 所有配置禁用 | 返回 `None` |

#### tests/test_dynamic_rules.py 测试用例

| 用例 | 场景 | 预期 |
|:---|:---|:---|
| `test_time_slot_normal` | `09:00-17:00`，当前 14:30 | 命中，返回时段规则 |
| `test_time_slot_cross_midnight` | `22:00-05:00`，当前 02:30 | 命中（跨午夜） |
| `test_time_slot_cross_midnight_edge` | `22:00-05:00`，当前 22:00 | 命中（边界） |
| `test_time_slot_no_match` | 当前时间不在任何区间 | 返回 `[]` |
| `test_time_slot_invalid_format` | slot key 为 `"bad-format"` | 跳过，不抛异常 |
| `test_turn_stage_first_turn` | `is_first_turn=True` | 注入 first_turn 规则 |
| `test_turn_stage_after_30` | `turn_count=35` | 命中 after_30 而非 after_10 |
| `test_turn_stage_after_10` | `turn_count=12` | 命中 after_10 |
| `test_turn_stage_no_match` | `turn_count=5`，仅有 after_10 | 返回 `[]` |
| `test_turn_stage_invalid_key` | 有 `after_xyz` key | 跳过，不抛异常 |
| `test_in_time_range_normal` | `10:00` in `09:00-17:00` | `True` |
| `test_in_time_range_normal_false` | `18:00` in `09:00-17:00` | `False` |
| `test_in_time_range_cross_midnight` | `02:00` in `22:00-05:00` | `True` |
| `test_select_dynamic_rules_empty_config` | `dynamic_cfg={}` | 返回 `[]` |

---

## 三、P2 — 动态扩展

**目标**：关键词匹配 + 随机表达变化 + 外部记忆召回。依赖 P1 全部完成。

### P2-T1: 实现 _match_keyword() 完整逻辑

| 属性 | 值 |
|:---|:---|
| **文件** | `dynamic_rules.py`（替换桩函数） |
| **依赖** | P1-T4 |
| **修改函数** | `_match_keyword(keywords, user_message)` |
| **预估行数** | ~35 |

**核心逻辑**：
1. 若 `user_message` 为空 → 返回 `[]`
2. 遍历 `keywords` items（按配置顺序，即 `dict` 的 insert order）
3. 对每个 `(pattern, rules)` → `re.search(pattern, user_message)`
4. 命中 → 返回 `[f"💬 [{pattern}] {r}" for r in rules]`，立即返回
5. 全部未命中 → 返回 `[]`

**接入点**：在 `_select_dynamic_rules()` 中取消 P2 步骤的注释（P1-T4a 已预留）。

---

### P2-T2: 实现 _randomize_variance() 完整逻辑

| 属性 | 值 |
|:---|:---|
| **文件** | `variance.py`（替换桩函数） |
| **依赖** | P1-T5 |
| **修改函数** | `_randomize_variance(variance_cfg)` |
| **预估行数** | ~40 |

**核心逻辑**：
1. 若 `variance_cfg` 为空 → 返回 `[]`
2. 遍历每个 category 的配置
3. **第一层**：`random.random() > prob` → skip（本回合不使用此维度）
4. **第二层**：`random.choice(variants)` → 随机选一条变体
5. 检查 `prob` 类型：非 `float`/`int` 或超出 `[0,1]` → 降级为 0.5
6. 检查 `variants` 类型：非 `list` 或为空 → skip

---

### P2-T3: 实现 _recall_memories() 完整逻辑

| 属性 | 值 |
|:---|:---|
| **文件** | `injector.py`（替换桩函数） |
| **依赖** | P1-T3 |
| **修改函数** | `_recall_memories(user_message, mem_cfg)` |
| **新增依赖** | `httpx`（声明为可选依赖，未安装时降级） |
| **预估行数** | ~45 |

**核心逻辑**：
1. 若 `not mem_cfg.get("enabled")` 或 `not mem_cfg.get("api_url")` → 返回 `None`
2. Try `import httpx`，ImportError → 返回 `None`
3. `httpx.post(api_url, json={"query": user_message, "limit": max_results}, timeout=3)`
4. 状态码非 200 → 返回 `None`
5. 从 `resp.json()` 取 `results` 字段
6. `results` 为空 → 返回 `None`
7. 每条截断至 120 字符，添加 `- ` 前缀
8. 用 `📝 相关记忆:` 作为标题行
9. 整个 try-except 包裹，任何异常返回 `None`

---

### P2-T4: 接入 inject_context() 主流程

| 属性 | 值 |
|:---|:---|
| **文件** | `injector.py`（修改主入口） |
| **依赖** | P2-T1 + P2-T2 + P2-T3 |
| **修改函数** | `inject_context()` |
| **预估行数** | ~15（增量修改） |

**修改内容**：
1. `_select_dynamic_rules()` 中启用 `_match_keyword()` 调用（P1-T4a 预留的注释行取消注释）
2. `_randomize_variance()` 从桩调用变为实际调用
3. `_recall_memories()` 从桩调用变为实际调用
4. 在 `parts` 拼接中加入记忆和 variance 内容

---

### P2-T5: P2 单元测试

| 属性 | 值 |
|:---|:---|
| **文件** | `tests/test_dynamic_rules.py`（追加）、`tests/test_variance.py`（新建）、`tests/test_injector.py`（追加） |
| **依赖** | P2-T1~T4 |
| **预估行数** | ~80 + ~150 + ~60 |

#### tests/test_dynamic_rules.py 追加用例

| 用例 | 场景 | 预期 |
|:---|:---|:---|
| `test_keyword_match` | 消息含 "bug 炸了" | 命中后返回对应规则 |
| `test_keyword_first_match_wins` | 两个模式均匹配 | 只返回第一个命中的规则 |
| `test_keyword_empty_message` | `user_message=""` | 返回 `[]` |
| `test_keyword_no_match` | 消息不含任何模式 | 返回 `[]` |
| `test_keyword_regex_boundary` | 模式 `"坏了"` | 匹配 "系统坏了" 但不匹配 "坏了的系统" 中的前缀关联合并 |
| `test_keyword_pattern_order` | 验证配置顺序即匹配顺序 | 第一个命中即停止 |

#### tests/test_variance.py 测试用例

| 用例 | 场景 | 预期 |
|:---|:---|:---|
| `test_variance_probability_zero` | `probability=0` | 永远不返回该维度 |
| `test_variance_probability_one` | `probability=1.0` | 始终返回该维度 |
| `test_variance_single_variant` | `variants` 仅一条 | 始终返回该条 |
| `test_variance_empty_config` | `variance_cfg={}` | 返回 `[]` |
| `test_variance_invalid_prob` | `probability="high"` | 降级为 0.5 |
| `test_variance_out_of_range_prob` | `probability=1.5` | 降级为 0.5 |
| `test_variance_empty_variants` | `variants=[]` | skip 该维度 |
| `test_variance_multiple_categories` | 3 个维度 | 各维度独立决策 |
| `test_variance_statistical` | 1000 次调用，`probability=0.5` | 出现率在 40%-60% 之间 |

#### tests/test_injector.py 追加用例

| 用例 | 场景 | 预期 |
|:---|:---|:---|
| `test_memory_recall_integration` | `memory.enabled=true` | 注入记忆内容 |
| `test_memory_disabled` | `memory.enabled=false` | 不注入记忆 |
| `test_memory_no_api_url` | 仅 enabled，无 url | 不注入记忆 |
| `test_memory_content_truncation` | 返回 >120 字符 | 截断至 120 字符 |

---

## 四、P3 — 看板集成

**目标**：首轮注入项目看板状态。依赖 P1 全部完成（不依赖 P2）。

### P3-T1: 实现 _read_kanban() 完整逻辑

| 属性 | 值 |
|:---|:---|
| **文件** | `injector.py`（替换桩函数） |
| **依赖** | P1-T3 |
| **修改函数** | `_read_kanban(kanban_path, label)` |
| **预估行数** | ~40 |

**核心逻辑**：
1. `kanban_path` 为空 → 返回 `None`
2. `Path(kanban_path)` 不存在 → 返回 `None`
3. 扫描 `sorted(kb.glob("*.md"))` 下所有 markdown 文件
4. 读取每个文件，提取**首行**包含 `"优先级:"` 的行
5. 格式化为 `"- {文件名}: {优先级行内容}"` 列表
6. 最多取前 5 项
7. `label` 为空 → 默认 `"📋 项目状态:"`
8. 无任何匹配 → 返回 `None`
9. 整个 try-except 包裹，异常返回 `None`

**接入点**：`inject_context()` 中 P1-T6 已预留调用代码，P3 直接替换桩实现即可。

---

### P3-T2: P3 单元测试

| 属性 | 值 |
|:---|:---|
| **文件** | `tests/test_injector.py`（追加） |
| **依赖** | P3-T1 |
| **预估行数** | ~80 |

| 用例 | 场景 | 预期 |
|:---|:---|:---|
| `test_kanban_first_turn_only` | `is_first_turn=True` vs `False` | 仅首轮注入 |
| `test_kanban_path_not_found` | `kanban_path` 不存在 | 不抛异常，不注入 |
| `test_kanban_empty_dir` | 目录存在但无 md 文件 | 不注入 |
| `test_kanban_priority_extraction` | md 文件含优先级行 | 正确提取 |
| `test_kanban_max_five` | 超过 5 个文件 | 只取前 5 个 |
| `test_kanban_custom_label` | 设置 `label` | 自定义标签生效 |
| `test_kanban_default_label` | 未设置 `label` | 使用默认标签 |

---

## 五、P4 — 安全护栏 + 审计

**目标**：工具调用安全检查和审计记录。依赖 P1 全部完成（不依赖 P2/P3）。

### P4-T1: 实现 guard.py 完整逻辑

| 属性 | 值 |
|:---|:---|
| **文件** | `guard.py`（替换桩文件） |
| **依赖** | P1-T5 |
| **新增函数** | `check_tool_call()`, `audit_tool_call()`, `_load_guard_config()` |
| **预估行数** | ~120 |

#### P4-T1a: `_load_guard_config()` (~20 行)

从 `persona-config.json` 的 `guard` 节点加载护栏配置。复用 `injector._load_config()` 的结果或独立加载。

```python
def _load_guard_config() -> dict:
    """从 persona-config.json 加载 guard 配置。"""
```

**Guard 配置 Schema**（新增至 persona-config.json）：
```json
"guard": {
  "enabled": true,
  "rules": {
    "blocked": [
      {"pattern": "rm\\s", "reason": "文件删除操作已阻止"},
      {"pattern": "DROP\\s", "reason": "数据库删除操作已阻止"}
    ],
    "require_confirmation": [
      {"pattern": "git\\s+push", "reason": "代码推送需确认"}
    ]
  },
  "audit": {
    "enabled": true,
    "log_path": "~/.hermes/logs/persona-audit.log"
  }
}
```

#### P4-T1b: `check_tool_call()` (~50 行)

```python
def check_tool_call(tool_name: str, tool_args: dict, **kwargs) -> dict | None:
    """
    pre_tool_call hook。工具调用前安全检查。
    
    返回: {"blocked": True, "reason": "..."}  阻止调用
           None                                 放行
    """
```

**核心逻辑**：
1. 加载 guard 配置
2. 若 `guard.enabled` != True → 返回 `None`（放行）
3. **Blocked 检查**：遍历 `rules.blocked`，用 `re.search(pattern, tool_name)` 匹配
   - 命中 → 返回 `{"blocked": True, "reason": rule["reason"]}`
4. **Confirmation 检查**：遍历 `rules.require_confirmation`，匹配 tool_name
   - 命中 → 返回 `{"require_confirmation": True, "reason": rule["reason"]}`
5. 均不匹配 → 返回 `None`

#### P4-T1c: `audit_tool_call()` (~50 行)

```python
def audit_tool_call(tool_name: str, tool_args: dict, result: any, **kwargs) -> None:
    """
    post_tool_call hook。记录工具调用审计日志。
    """
```

**核心逻辑**：
1. 加载 guard 配置
2. 若 `audit.enabled` != True → 直接返回
3. 构造日志条目：`[时间戳] {tool_name} | args: {摘要} | result: {摘要}`
4. args/result 摘要：字符串截断至 200 字符
5. 写入 `audit.log_path`（支持 `~` 展开）
6. 日志追加模式（append）
7. 整个 try-except 包裹，异常静默（审计不应阻塞工具调用）

---

### P4-T2: 注册 P4 hooks + 测试

| 属性 | 值 |
|:---|:---|
| **文件** | `__init__.py`（修改 register）、`tests/test_guard.py`（新建） |
| **依赖** | P4-T1 |
| **预估行数** | ~10 + ~100 |

**register() 修改**：
```python
ctx.register_hook("pre_tool_call", guard.check_tool_call)
ctx.register_hook("post_tool_call", guard.audit_tool_call)
```

**tests/test_guard.py 测试用例**：

| 用例 | 场景 | 预期 |
|:---|:---|:---|
| `test_guard_disabled` | `guard.enabled=false` | 全部放行 |
| `test_block_tool` | tool_name 匹配 blocked 模式 | 返回 blocked=True |
| `test_allow_tool` | tool_name 不匹配任何模式 | 返回 `None` |
| `test_require_confirmation` | tool_name 匹配 confirm 模式 | 返回 require_confirmation=True |
| `test_block_takes_priority` | tool 同时命中 blocked 和 confirm | blocked 优先 |
| `test_audit_writes_log` | audit.enabled=true | 日志文件写入 |
| `test_audit_disabled` | audit.enabled=false | 不写日志 |
| `test_empty_guard_config` | guard 节点不存在 | 全部放行 |

---

## 六、P5 — 发布就绪

**目标**：文档完善、测试覆盖、性能基准、多示例配置。依赖 P1-P4 全部完成。

### P5-T1: README.md 快速开始指南

| 属性 | 值 |
|:---|:---|
| **文件** | `README.md`（更新） |
| **依赖** | 无代码依赖 |
| **预估行数** | ~80（增量） |

**内容大纲**：
1. 项目简介（一句话 + 三行概述）
2. 核心特性（代码通用、配置驱动、开箱即用、可组合）
3. 安装步骤（插件复制 + 创建配置）
4. 最小配置示例（`{}` → 时间注入）
5. 各功能模块简介表格
6. 文档索引链接

---

### P5-T2: docs/CONFIG_REFERENCE.md 配置参考

| 属性 | 值 |
|:---|:---|
| **文件** | `docs/CONFIG_REFERENCE.md`（新建） |
| **依赖** | 无代码依赖 |
| **预估行数** | ~200 |

**内容大纲**：
1. 配置文件位置约定
2. 完整 JSON Schema（含注释说明）
3. 每个配置项：类型、默认值、说明、示例
4. 配置层级树状图
5. 降级行为表
6. 规则注入优先级说明
7. 常见配置错误排查

---

### P5-T3: docs/EXAMPLES.md 多示例配置

| 属性 | 值 |
|:---|:---|
| **文件** | `docs/EXAMPLES.md`（新建） |
| **依赖** | 无代码依赖 |
| **预估行数** | ~150 |

**三个完整可用的示例配置**：

1. **通用助手**（最小配置，仅时间注入）— `{"hermes-persona": {}}`
2. **代码审查员** — 静态规则 + 时段规则 + 关键词（bug/error/性能）
3. **兽娘女仆（知惠风格）** — 全套功能：时间 + 静态规则 + 时段/轮数/关键词动态规则 + 随机变化 + 记忆 + 看板

每个示例包含：
- 场景描述
- 完整 `persona-config.json`
- 预期注入效果示例

---

### P5-T4: 完善单元测试

| 属性 | 值 |
|:---|:---|
| **文件** | `tests/` 目录下全部测试文件 |
| **依赖** | P1-P4 |
| **预估行数** | ~200（增量） |

**补充内容**：
1. `tests/test_injector.py`：整合测试（全功能拼接测试）、并发安全测试、异常场景扩大
2. `tests/test_dynamic_rules.py`：边界值测试、压测（1000 次调用无异常）
3. `tests/test_variance.py`：统计分布合理性验证（卡方检验或简单比例检查）
4. `tests/test_integration.py`（新建）：端到端测试，模拟完整 `inject_context()` 调用链

**测试覆盖率目标**：> 85% 行覆盖

---

### P5-T5: 性能基准测试

| 属性 | 值 |
|:---|:---|
| **文件** | `tests/test_benchmark.py`（新建） |
| **依赖** | P1-P4 |
| **预估行数** | ~50 |

**基准指标**：
1. 最小配置（仅时间注入）：< 1ms
2. 完整配置（全部功能开启）：< 5ms（不含外部 API 调用）
3. 1000 次连续调用的内存无泄漏验证
4. `inject_context()` 无共享可变状态验证（并发安全）

**实现方式**：`time.perf_counter()` 取 100 次调用平均值。

---

## 七、任务总览表

| 任务 ID | Phase | 标题 | 文件 | 预估行数 | 依赖 |
|:---|:---|:---|:---|:---|:---|
| P1-T1 | P1 | plugin.yaml | `plugin.yaml` | 15 | 无 |
| P1-T2 | P1 | __init__.py 入口 | `__init__.py` | 35 | P1-T1 |
| P1-T3 | P1 | injector.py 基础函数 | `injector.py` | 100 | P1-T2 |
| P1-T4 | P1 | dynamic_rules.py | `dynamic_rules.py` | 100 | 无 |
| P1-T5 | P1 | variance/guard 桩 | `variance.py`, `guard.py` | 30 | 无 |
| P1-T6 | P1 | inject_context 组装 | `injector.py` | 55 | P1-T3, P1-T4 |
| P1-T7 | P1 | P1 测试 | `tests/` | 330 | P1-T1~T6 |
| P2-T1 | P2 | _match_keyword 实现 | `dynamic_rules.py` | 35 | P1-T4 |
| P2-T2 | P2 | _randomize_variance 实现 | `variance.py` | 40 | P1-T5 |
| P2-T3 | P2 | _recall_memories 实现 | `injector.py` | 45 | P1-T3 |
| P2-T4 | P2 | inject_context 接入 | `injector.py` | 15 | P2-T1~T3 |
| P2-T5 | P2 | P2 测试 | `tests/` | 290 | P2-T1~T4 |
| P3-T1 | P3 | _read_kanban 实现 | `injector.py` | 40 | P1-T3 |
| P3-T2 | P3 | P3 测试 | `tests/` | 80 | P3-T1 |
| P4-T1 | P4 | guard.py 完整实现 | `guard.py` | 120 | P1-T5 |
| P4-T2 | P4 | 注册 hooks + 测试 | `__init__.py`, `tests/` | 110 | P4-T1 |
| P5-T1 | P5 | README.md | `README.md` | 80 | 无 |
| P5-T2 | P5 | CONFIG_REFERENCE.md | `docs/CONFIG_REFERENCE.md` | 200 | 无 |
| P5-T3 | P5 | EXAMPLES.md | `docs/EXAMPLES.md` | 150 | 无 |
| P5-T4 | P5 | 测试完善 | `tests/` | 200 | P1-P4 |
| P5-T5 | P5 | 性能基准 | `tests/` | 50 | P1-P4 |

**总计预估代码量**：~1,885 行

---

## 八、推荐执行顺序

```
第1轮: P1-T1, P1-T4, P1-T5  (无依赖，可并行)
第2轮: P1-T2                   (依赖 P1-T1)
第3轮: P1-T3                   (依赖 P1-T2)
第4轮: P1-T6                   (依赖 P1-T3, P1-T4)
第5轮: P1-T7                   (依赖 P1-T1~T6)

第6轮: P2-T1, P2-T2, P2-T3    (依赖 P1，三者可并行)
第7轮: P2-T4                   (依赖 P2-T1~T3)
第8轮: P3-T1                   (依赖 P1，与 P2 可并行)
第9轮: P4-T1                   (依赖 P1，与 P2/P3 可并行)
第10轮: P2-T5                  (依赖 P2-T1~T4)
第11轮: P3-T2                  (依赖 P3-T1)
第12轮: P4-T2                  (依赖 P4-T1)

第13轮: P5-T1, P5-T2, P5-T3   (文档，可并行)
第14轮: P5-T4, P5-T5           (测试/基准，依赖 P1-P4)
```

**可并行执行的轮次**：第1轮、第6轮（P2-T1/P2-T2/P2-T3）、第8轮+第9轮（P3-T1与P4-T1）、第13轮

---

*基于 `specs/hermes-persona-spec.md` v1.0 编写。*
