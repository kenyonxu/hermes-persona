# PLAN-009: 注入规则转译（状态编织器）— 实施计划

**文档编号:** PLAN-009
**对应 SPEC:** SPEC-009
**对应 DRAFT:** DRAFT-009
**版本:** 1.0
**日期:** 2026-05-21
**作者:** 知惠（Zhihui）
**审阅:** Kai.Xu
**状态:** 📋 待审阅

---

## 目录

1. [总体时间估算](#1-总体时间估算)
2. [实施步骤](#2-实施步骤)
    - [Phase 0: 前置检查 — 测试基线确认](#phase-0-前置检查--测试基线确认)
    - [Phase 1: expression_vector.py — 新增 top3() 方法](#phase-1-expression_vectorpy--新增-top3-方法)
    - [Phase 2: injector.py — 新增 _assemble_narrative() 函数](#phase-2-injectorpy--新增-_assemble_narrative-函数)
    - [Phase 3: injector.py — 新增 _filter_fixed_rules() 筛选函数](#phase-3-injectorpy--新增-_filter_fixed_rules-筛选函数)
    - [Phase 4: dynamic_rules.py — 新增 raw 数据提取函数](#phase-4-dynamic_rulespy--新增-raw-数据提取函数)
    - [Phase 5: injector.py — inject_context() 新增 translate 分支](#phase-5-injectorpy--inject_context-新增-translate-分支)
    - [Phase 6: 测试 — 新建 tests/test_translate.py](#phase-6-测试--新建-teststest_translatepy)
    - [Phase 7: 全量验收 — 346+ passed](#phase-7-全量验收--346-passed)
    - [Phase 8: 文档更新 — README / CHANGELOG / 示例配置](#phase-8-文档更新--readme--changelog--示例配置)
3. [风险点与回滚方案](#3-风险点与回滚方案)
4. [验证检查清单](#4-验证检查清单)

---

## 1. 总体时间估算

| 步骤 | 内容 | 预估时间 |
|:---|:---|:---|
| Phase 0 | 前置检查 + 基线验证 | 5 min |
| Phase 1 | expression_vector.py 新增 top3() | 20 min |
| Phase 2 | injector.py 新增 _assemble_narrative() | 30 min |
| Phase 3 | injector.py 新增 _filter_fixed_rules() | 10 min |
| Phase 4 | dynamic_rules.py 新增 raw 数据提取函数 | 15 min |
| Phase 5 | inject_context() 新增 translate 分支 | 30 min |
| Phase 6 | 测试 — test_translate.py (T-01~T-08) | 45 min |
| Phase 7 | 全量验收 | 10 min |
| Phase 8 | 文档 + 示例配置更新 | 10 min |
| **合计** | | **~2 小时 45 分钟** |

---

## 2. 实施步骤

### Phase 0: 前置检查 — 测试基线确认

**目标：** 确认当前分支代码干净，所有 346 个测试通过，作为回归基线。

**操作：**

```bash
# 确认在 feature/001-module-switch 分支
git branch --show-current
# 期望: feature/001-module-switch

# 运行全部测试，记录基线
python -m pytest tests/ -v
# 期望: 346 passed, 0 failure

# 确认工作区干净
git status
# 期望: clean
```

**验证标准：**
- 346 passed, 0 failure, 0 error
- 工作区干净（无未提交改动）

**风险等级：** 无风险（尚未改动代码）

**回滚：** 无需回滚

---

### Phase 1: expression_vector.py — 新增 top3() 方法

**目标：** 为 `_ExpressionVector` 类新增 `top3(n=3, trend=True)` 公开方法，返回排序后的 top n 维度 + 趋势箭头。同时存储维度标签元数据，新增模块级默认标签常量和趋势判定辅助函数。

**文件：** `expression_vector.py`

#### 1.1 新增模块级常量 `_DEFAULT_LABELS`（约第 16 行之后）

**位置：** `_BG_SIGNATURE_THRESHOLD = 2` 之后、`_is_background_message()` 之前（约第 25 行后）

```python
# ── 维度标签默认映射 ─────────────────────────────────────────────────────────

_DEFAULT_LABELS: dict[str, str] = {
    "intimacy": "亲密温度",
    "care": "关怀守护",
    "work": "工作投入",
    "play": "轻松玩乐",
    "future": "未来愿景",
    "eros": "私密温度",
}
```

#### 1.2 新增模块级函数 `_trend()`（紧接 `_DEFAULT_LABELS` 之后）

```python
def _trend(current: float, previous: float) -> str:
    """比较当前值与上轮值，返回趋势箭头。

    Returns:
        "↑" — 上升中、"↓" — 下降中、"→" — 平稳
    """
    if current > previous:
        return "↑"
    elif current < previous:
        return "↓"
    else:
        return "→"
```

#### 1.3 修改 `__init__()` — 存储维度标签（约第 52-57 行）

**当前代码** (`expression_vector.py:54-57`)：
```python
self.dimensions: dict[str, list[str]] = {}
_dim_raw = cfg.get("dimensions", {})
_dim_meta: dict[str, dict] = {}  # 暂存 dict 格式的元数据
```

**改为**（新增 `self.dimension_labels` 属性）：
```python
self.dimensions: dict[str, list[str]] = {}
self.dimension_labels: dict[str, str] = {}  # 🆕 维度名 → 中文标签
_dim_raw = cfg.get("dimensions", {})
_dim_meta: dict[str, dict] = {}  # 暂存 dict 格式的元数据
```

并在循环体内（`_dim_meta[dim_name] = dim_val` 之后，约第 63 行）新增标签提取：

```python
elif isinstance(dim_val, dict):
    _dim_meta[dim_name] = dim_val
    # 提取 label（若配置了）
    label = dim_val.get("label", "")
    if label:
        self.dimension_labels[dim_name] = str(label)
```

> 旧格式 `{"work": ["kw1", "kw2"]}` 不含 label，此时回退到 `_DEFAULT_LABELS`。top3() 方法内处理此回退。

#### 1.4 新增 `top3()` 方法（`format_inject()` 之后，约第 293 行之后）

**位置：** `format_inject()` 方法之后、`_KeywordMatcher` 类之前（约第 294 行）

```python
def top3(self, n: int = 3, trend: bool = True) -> list[tuple[str, float, str]]:
    """返回排序后的 top n 维度信息。

    按向量值降序排列，取前 n 个。每个元素为 (label, score, trend_arrow)。
    trend_arrow 为空字符串当 trend=False 或无法计算趋势时。

    Args:
        n: 返回维度数量，默认 3。
        trend: 是否计算趋势箭头。为 True 时从 vector_history 取上轮值比较。

    Returns:
        list of (label, score, trend_arrow)。少于 n 个维度时有几个返回几个。
        若某维度分值为 0 则跳过（避免输出无意义维度）。
    """
    # 按值降序排序，过滤分值为 0 的维度
    sorted_dims = sorted(
        [(dim, val) for dim, val in self.vectors.items() if val > 0],
        key=lambda x: x[1],
        reverse=True,
    )[:n]

    # 获取上轮向量值（用于趋势计算）
    prev_vectors: dict[str, float] = {}
    if trend and self.vector_history:
        prev_vectors = self.vector_history[-1].get("vectors", {})

    result: list[tuple[str, float, str]] = []
    for dim_name, score in sorted_dims:
        # 获取标签：优先维度配置的 label → _DEFAULT_LABELS → dim_name 本身
        label = self.dimension_labels.get(dim_name)
        if not label:
            label = _DEFAULT_LABELS.get(dim_name, dim_name)

        arrow = ""
        if trend:
            prev_val = prev_vectors.get(dim_name, 0.0)
            arrow = _trend(score, prev_val)

        result.append((label, round(score), arrow))

    return result
```

**关键设计点：**
- 分值为 0 的维度不返回（避免「工作投入（→）」这种无意义输出）
- label 回退链：`dimension_labels[dim]` → `_DEFAULT_LABELS[dim]` → `dim` 名称本身
- `vector_history` 为空时（首次运行），趋势默认为 `"→"`（当前值与上一个 0.0 比较）
- `round(score)` 将浮点值四舍五入为整数，与 `format_inject()` 行为一致

**验证命令：**

```bash
# 单元验证 — 导入并检查新方法存在
python -c "
from expression_vector import _ExpressionVector, _DEFAULT_LABELS, _trend
print('_DEFAULT_LABELS:', _DEFAULT_LABELS)
print('_trend(5,3):', _trend(5, 3))
print('_trend(3,5):', _trend(3, 5))
print('_trend(4,4):', _trend(4, 4))
ev = _ExpressionVector({'dimensions': {'work': ['code'], 'play': ['game']}}, 'test')
ev.vectors = {'work': 16.0, 'play': 2.0}
print('top3:', ev.top3())
print('top3 no trend:', ev.top3(trend=False))
print('OK')
"
# 期望: OK，输出趋势箭头和行为符合预期

# 确认现有 expression_vector 测试无回归
python -m pytest tests/test_expression_vector.py -v
# 期望: 全部 PASSED
```

**风险等级：** 🟢 低 — 纯新增方法，不修改现有公开接口

**回滚：** `git checkout -- expression_vector.py`

---

### Phase 2: injector.py — 新增 _assemble_narrative() 函数

**目标：** 实现核心模板拼装函数，将四组数据源汇合为一段自然语言指令。

**文件：** `injector.py`

**位置：** 在 `_read_kanban()` 之后、`inject_context()` 之前（约第 919 行），新增「Narrative assembly」区块。

#### 2.1 新增 `_assemble_narrative()` 函数

```python
# ---------------------------------------------------------------------------
# Narrative assembly (translate mode)
# ---------------------------------------------------------------------------


def _assemble_narrative(
    weekday: str,
    current_time: str,
    time_slot_desc: str,
    today_turn: int,
    turn_stage_hint: str | None,
    top3: list[tuple[str, float, str]],
    variance_items: list[str],
    fixed_rules: list[str],
) -> str:
    """将分散的模块注入数据拼装为一段流畅的自然语言指令。

    各数据源独立，缺失项优雅跳过（不抛异常、不输出该段落）。

    Args:
        weekday: 星期几（如 "周四"）。
        current_time: 当前时间 HH:MM（如 "20:29"）。
        time_slot_desc: 匹配到的时段规则原始文本，可为空字符串。
        today_turn: 今日累计轮数，为 0 时跳过轮数段落。
        turn_stage_hint: 轮数阶段提示，可为 None。
        top3: 表达向量 top 3，每项 (label, score, trend_arrow)。
        variance_items: 随机变化抽中的变体文本列表。
        fixed_rules: 筛选后的固定规则文本列表。

    Returns:
        拼装后的自然语言字符串。
    """
    lines: list[str] = []

    # ── ① 时间感知 + 时段规则 ──
    if time_slot_desc:
        lines.append(f"现在时间是：{weekday}，{current_time}。{time_slot_desc}")
    else:
        lines.append(f"现在时间是：{weekday}，{current_time}。")

    # ── ② 轮数追踪 + 轮数阶段 ──
    if today_turn > 0:
        turn_line = f"这是今天的第{today_turn}轮对话。"
        if turn_stage_hint:
            turn_line += f" {turn_stage_hint}。"
        lines.append(turn_line)

    # ── ③ 表达向量 top 3 转译 ──
    if top3:
        top_labels = [f"{label}（{trend}）" for label, _, trend in top3]
        lines.append(f"主人目前的状态是{'，'.join(top_labels)}。")

    # ── ④ 随机变化（抽中的） ──
    if variance_items:
        for item in variance_items:
            # 去除 emoji 前缀和冗余标签，只保留实质性描述
            clean = _clean_variance_item(item)
            lines.append(f"使用{clean}的肢体语言来对你的语言表达进行补充。")

    # ── ⑤ 固定规则（自然收尾） ──
    if fixed_rules:
        rules_text = "；".join(fixed_rules)
        lines.append(rules_text + "。")

    return "\n\n".join(lines)
```

#### 2.2 新增 `_clean_variance_item()` 辅助函数

```python
def _clean_variance_item(item: str) -> str:
    """清理随机变化条目：去除 emoji 前缀和「的肢体语言表达」后缀。

    Args:
        item: _randomize_variance() 返回的原始条目，
              如 "蓬松的大狐尾的肢体语言表达"。

    Returns:
        清理后的描述文本，如 "蓬松的大狐尾"。
    """
    # 去除常见 emoji 前缀（🦊 等）
    cleaned = item
    for prefix in ("🦊 ", "💬 ", "📊 ", "🌿 ", "💎 ", "🌙 "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    # 去除「的肢体语言表达」后缀
    if "的肢体语言表达" in cleaned:
        cleaned = cleaned.split("的肢体语言表达")[0]
    return cleaned.strip()
```

**验证命令：**

```python
# python -c "
from injector import _assemble_narrative, _clean_variance_item

# 正常输入
result = _assemble_narrative(
    weekday='周四', current_time='20:29',
    time_slot_desc='晚间——主人这段时间一般会继续工作，保持高效和温暖的工作节奏即可。',
    today_turn=30, turn_stage_hint=None,
    top3=[('工作投入', 16, '→'), ('亲密温度', 5, '→')],
    variance_items=['蓬松的大狐尾', '女仆礼仪,温柔感强'],
    fixed_rules=['感知表达自然化', '核心态度', '永远不赶主人去睡觉'],
)
print(result)
# 期望: 五段输出，格式与 SPEC-009 §6.2 一致

# 空输入 — time_slot_desc 为空
result2 = _assemble_narrative(
    weekday='周四', current_time='20:29',
    time_slot_desc='', today_turn=0, turn_stage_hint=None,
    top3=[], variance_items=[], fixed_rules=[],
)
print(result2)
# 期望: 仅输出「现在时间是：周四，20:29。」
"
```

**风险等级：** 🟢 低 — 纯新增函数，不修改现有代码路径

**回滚：** 删除新增函数块即可

---

### Phase 3: injector.py — 新增 _filter_fixed_rules() 筛选函数

**目标：** 从 `context.rules` 中排除已被其他模块转译覆盖的规则（以 `🦊` / `💬` / `📊 表达向量` 开头的规则）。

**文件：** `injector.py`

**位置：** `_assemble_narrative()` 之后、`inject_context()` 之前（紧接 Phase 2 新增区块）

```python
def _filter_fixed_rules(rules: list[str]) -> list[str]:
    """筛选固定规则：排除已被转译模块覆盖的规则。

    排除条件（任一命中即排除）：
        - 以 🦊 开头  → 狐耳/尾巴规则，已被随机变化取代
        - 以 💬 开头  → 女仆比喻优先，已被散落提示取代
        - 以 📊 开头且包含「表达向量」 → 表达向量说明，已被 top3 取代

    Args:
        rules: _inject_static_rules() 返回的完整规则列表。

    Returns:
        筛选后的规则列表。
    """
    filtered: list[str] = []
    for rule in rules:
        if not isinstance(rule, str):
            continue
        if rule.startswith("🦊"):
            continue
        if rule.startswith("💬"):
            continue
        if rule.startswith("📊") and "表达向量" in rule:
            continue
        filtered.append(rule)
    return filtered
```

**关键设计点：**
- 按 emoji 前缀精确匹配，不依赖规则文本内容
- `📊 使用Claude Code后台执行任务时要给充足权限` 这条规则以 `📊` 开头但**不含「表达向量」**，不会被误排除
- 返回新列表，不修改原列表（纯函数）

**验证命令：**

```python
# python -c "
from injector import _filter_fixed_rules

rules = [
    '🦊 狐耳/尾巴=情绪外显器官...',
    '💬 女仆比喻优先...',
    '🌿 感知表达自然化...',
    '💎 核心态度...',
    '📊 表达向量的六维数值动态反映主人状态...',
    '📊 使用Claude Code后台执行任务时要给充足权限',
    '🌙 永远不赶主人去睡觉...',
]
filtered = _filter_fixed_rules(rules)
print('保留:', len(filtered), '条')
for r in filtered:
    print(f'  {r[:40]}...')
# 期望: 保留 4 条（🌿 💎 📊(CC) 🌙），排除 3 条（🦊 💬 📊(表达向量)）
"
```

**风险等级：** 🟢 低 — 纯新增函数

**回滚：** 删除新增函数块即可

---

### Phase 4: dynamic_rules.py — 新增 raw 数据提取函数

**目标：** 为 translate 分支提供「原始规则文本」（不含格式化前缀），与现有格式化输出并行存在。

**文件：** `dynamic_rules.py`

**原因：** 现有 `_match_time_slot()` 返回 `"🕐 [22:00-05:00] 规则文本"`（带前缀），translate 模式需要原始规则文本。同样，`_match_turn_stage()` 需要提取 turn_stage_hint。不修改现有函数以保持旧路径完全不变。

#### 4.1 新增 `_get_time_slot_desc()` 函数

**位置：** `_match_time_slot()` 之后（约第 94 行之后）

```python
def _get_time_slot_desc(time_slots: dict) -> str:
    """提取当前匹配时段的原始规则文本（不含格式化前缀）。

    与 _match_time_slot() 使用相同的时间匹配逻辑，但返回第一条匹配规则的
    原始文本而非格式化字符串。

    Args:
        time_slots: 时段配置字典 {"22:00-05:00": ["rule A", ...], ...}

    Returns:
        匹配到的第一条规则原始文本，无匹配时返回空字符串。
    """
    now = datetime.now().strftime("%H:%M")
    for slot_range, rules in time_slots.items():
        try:
            start, end = slot_range.split("-", 1)
            start = start.strip()
            end = end.strip()
        except ValueError:
            continue
        if _in_time_range(now, start, end):
            for rule in rules:
                return str(rule)  # 只返回第一条匹配的原始文本
    return ""
```

#### 4.2 新增 `_get_turn_stage_hint()` 函数

**位置：** `_match_turn_stage()` 之后（约第 140 行之后）

先读取 `_match_turn_stage()` 完整逻辑：

当前 `_match_turn_stage()` 返回类似 `"📊 [after_30] 可以使用更亲密的表达"` 的格式化字符串。translate 模式只需要提示文本本身。

```python
def _get_turn_stage_hint(
    turn_stages: dict, is_first_turn: bool, turn_count: int
) -> str | None:
    """提取当前轮数阶段的提示文本（不含格式化前缀）。

    与 _match_turn_stage() 使用相同的匹配逻辑，但返回提示文本本身。

    Args:
        turn_stages: 轮数阶段配置字典。
        is_first_turn: 是否为首轮。
        turn_count: 当前轮数。

    Returns:
        匹配到的阶段提示文本，无匹配时返回 None。
    """
    # first_turn
    if is_first_turn and "first_turn" in turn_stages:
        rules = turn_stages["first_turn"]
        if rules:
            return str(rules[0])

    # after_N — 解析 key 中的数字，找最大匹配
    stage_keys = []
    for key in turn_stages:
        if key == "first_turn":
            continue
        try:
            # 期望格式 "after_10", "after_30"
            num = int(key.replace("after_", ""))
            stage_keys.append((num, key))
        except (ValueError, AttributeError):
            continue

    stage_keys.sort(key=lambda x: x[0])
    matched_key = None
    for threshold, key in stage_keys:
        if turn_count >= threshold:
            matched_key = key

    if matched_key:
        rules = turn_stages[matched_key]
        if rules:
            return str(rules[0])

    return None
```

**关键设计点：**
- 两个新函数复用现有的 `_in_time_range()` 和轮数匹配逻辑，不重复实现
- 返回原始规则文本，调用方自行拼装
- 旧函数 `_match_time_slot()` / `_match_turn_stage()` 完全不改动

**验证命令：**

```bash
# 导入验证
python -c "
from dynamic_rules import _get_time_slot_desc, _get_turn_stage_hint
# 无匹配时返回空字符串 / None
assert _get_time_slot_desc({}) == ''
assert _get_turn_stage_hint({}, False, 100) is None
print('OK')
"

# 确认现有 dynamic_rules 测试无回归
python -m pytest tests/test_dynamic_rules.py -v
# 期望: 全部 PASSED
```

**风险等级：** 🟢 低 — 纯新增函数，不修改现有代码

**回滚：** `git checkout -- dynamic_rules.py`

---

### Phase 5: injector.py — inject_context() 新增 translate 分支

**目标：** 在 `inject_context()` 中根据 `modules.translate` 开关分流：`true` → 走 `_assemble_narrative()` 自然语言拼装，`false` → 保持现有逐模块注入不变。

**文件：** `injector.py`

**位置：** `inject_context()` 函数体内（约第 949-1192 行）

#### 5.1 修改 `_MODULE_REGISTRY` — 新增 translate 注册项（约第 93 行之后）

在 `"debug": {...}` 之后追加：

```python
    "translate": {
        "description": "注入规则转译 — 自然语言拼装替代逐模块堆叠",
        "default": False,
        "phase": 8,
        "legacy_key": None,
        "legacy_path": None,
    },
```

#### 5.2 修改 `inject_context()` 开头 — 提取全局时间变量（约第 950 行）

在 `config = _load_config()` 和 `modules = _resolve_modules(config)` 之后，新增时间变量的提前提取：

```python
        config = _load_config()
        modules = _resolve_modules(config)
        parts: list[str] = []

        # ── translate 模式：提前提取时间变量 ──
        _now = datetime.now()
        _weekday_cn = _WEEKDAY_CN[_now.weekday()]
        _current_time = _now.strftime("%H:%M")
        # ─────────────────────────────────────
```

> 注意：需要确认 `datetime` 已在文件顶部导入（当前已导入）。

#### 5.3 修改 Step ①~④ 之间的代码 — 提取 raw 数据 + 分流

核心思路：在 translate 模式下，不将各模块注入 parts，而是将数据暂存，最后通过 `_assemble_narrative()` 统一拼装。

**当前流程：**
```
① time → parts    ② static_rules → parts    ③ dynamic → parts
④a fixed_signals → parts    ④b expression_vector → parts
④ variance → parts    ⑤ memory → parts    ⑥ kanban → parts
⑦ debug → parts
```

**translate 模式流程：**
```
① ~ ④ 各模块 → 提取 raw 数据到局部变量（不放入 parts）
⑤ memory → parts（不受影响）
⑥ kanban → parts（不受影响）
translate 拼装 → parts 头部插入 narrative 段落
⑦ debug → parts（不受影响）
```

**具体改动：**

在 `inject_context()` 中，在 Step ① time 之前新增 translate 模式判断：

```python
        # ── 判断 translate 模式 ──
        _translate_mode = _is_enabled(modules, "translate")

        # translate 模式下的数据容器
        _time_slot_desc = ""
        _turn_stage_hint = None
        _today_turn = 0
        _top3: list[tuple[str, float, str]] = []
        _variance_items: list[str] = []
        _filtered_rules: list[str] = []
```

然后将 Step ①~④ 的代码包裹在 `if _translate_mode:` / `else:` 分支中。

> 为清晰起见，下面用「旧分支」（不改动）和「新分支」描述：

**Step ① Time — translate 分支不同：**

translate 模式下 `_time_context()` 仍然调用以保持 `format` 配置支持，但它返回的格式化字符串不直接加入 parts：

```python
        # 1. Time context
        if _is_enabled(modules, "time"):
            time_cfg = config.get("time", {})
            if _translate_mode:
                # translate 模式：只保持时间格式化行为，不加入 parts
                # weekday/current_time 已在前面从 _now 提取
                pass
            else:
                fmt = time_cfg.get("format", "cn_full")
                parts.append(_time_context(fmt))
```

**Step ② Static Rules — translate 模式下暂存筛选后规则：**

```python
        # 2. Static rules
        static_rules: list[str] = []
        if _is_enabled(modules, "static_rules"):
            ctx_cfg = config.get("context", {})
            static_rules = _inject_static_rules(ctx_cfg, is_first_turn)
            if _translate_mode:
                _filtered_rules = _filter_fixed_rules(static_rules)
            else:
                parts.extend(static_rules)
```

**Step ③ Dynamic Rules — translate 模式下用 raw 函数提取：**

```python
        # 3. Dynamic rules
        turn_count = len(conversation_history or []) // 2
        dynamic_rules: list[str] = []
        if _has_any_dynamic(modules):
            dynamic_cfg = config.get("dynamic", {})
            if _translate_mode:
                # translate 模式：用 raw 函数提取原始文本
                dyn_mod = modules.get("dynamic", {})
                if dyn_mod is None or not isinstance(dyn_mod, dict):
                    dyn_mod = {}
                if dyn_mod.get("time_slots", True):
                    _time_slot_desc = _get_time_slot_desc(
                        dynamic_cfg.get("time_slots", {})
                    )
                if dyn_mod.get("turn_stage", True):
                    _turn_stage_hint = _get_turn_stage_hint(
                        dynamic_cfg.get("turn_stage", {}),
                        is_first_turn,
                        turn_count,
                    )
            else:
                dynamic_rules = _select_dynamic_rules(
                    dynamic_cfg,
                    user_message,
                    is_first_turn,
                    turn_count,
                    modules=modules.get("dynamic", {}),
                )
                parts.extend(dynamic_rules)
```

> 需要新增 import：`from dynamic_rules import _get_time_slot_desc, _get_turn_stage_hint`

**Step ④a Fixed Signals — translate 模式下只提取 today_turn 原始值：**

```python
        # ─── ④a Fixed signals ────────────────────────────
        fixed_cfg = config.get("fixed_signals", {})

        if _translate_mode:
            # translate 模式：提取 today_turn 原始值
            turn_hint = _daily_turn_count_hint(
                fixed_cfg, profile_path=kwargs.get("profile_path", "")
            )
            if turn_hint:
                import re as _re
                _m = _re.search(r"今日第(\d+)轮", turn_hint)
                if _m:
                    _today_turn = int(_m.group(1))
        else:
            hint = _message_length_hint(user_message or "", fixed_cfg)
            if hint:
                parts.append(hint)
            gap_hint, now_ts = _reply_gap_hint(fixed_cfg)
            if gap_hint:
                parts.append(gap_hint)
            _save_reply_timing(fixed_cfg, now_ts)
            turn_hint = _daily_turn_count_hint(
                fixed_cfg, profile_path=kwargs.get("profile_path", "")
            )
            if turn_hint:
                parts.append(turn_hint)
```

> translate 模式下仍调用 `_daily_turn_count_hint()` 以保持计数器持久化（副作用），但从返回值中提取原始轮数。

**Step ④b Expression Vector — translate 模式下用 top3()：**

```python
        # ─── ④b Expression vector ─────────────────────────
        ev_cfg = config.get("expression_vector", {})
        debug_ev = {"enabled": False, "turn_count": 0, "dimensions": {}}
        if ev_cfg.get("enabled", False):
            try:
                profile = kwargs.get("profile_path", "")
                ev = _ExpressionVector(ev_cfg, profile_path=profile)
                ev.load()
                snapshot_before = dict(ev.vectors)
                if not _is_background_message(user_message or ""):
                    ev.update(user_message or "", session_id)
                # ... debug_ev 填充代码保持不变 ...
                ev.save()
                if _translate_mode:
                    _top3 = ev.top3(n=3, trend=True)
                else:
                    parts.append(ev.format_inject(turn_count))
            except Exception:
                pass
```

**Step ④ Variance — translate 模式下暂存原始值：**

```python
        # 4. Random variance
        var_count = 0
        var_results = []
        if _is_enabled(modules, "variance"):
            var_results = _randomize_variance(config.get("variance", {}))
            if _translate_mode:
                _variance_items = list(var_results)
            else:
                parts.extend(var_results)
                var_count = len(var_results)
```

**Step ⑤ Memory + ⑥ Kanban — 不受影响，保持原样**

**Step ⑦ 拼装 + Debug — 在 return 之前（约第 1186 行之前）：**

```python
        # ── translate 拼装 ──
        if _translate_mode:
            narrative = _assemble_narrative(
                weekday=_weekday_cn,
                current_time=_current_time,
                time_slot_desc=_time_slot_desc,
                today_turn=_today_turn,
                turn_stage_hint=_turn_stage_hint,
                top3=_top3,
                variance_items=_variance_items,
                fixed_rules=_filtered_rules,
            )
            # narrative 插入到 parts 最前面（memory/kanban 之前）
            parts.insert(0, narrative)

        # 7. Debug summary → stored to _PENDING_DEBUG_BLOCK（保持原样）
        ...
```

**完整改动汇总（injector.py）：**

| 行区域 | 改动 | 说明 |
|--------|------|------|
| ~99 | `_MODULE_REGISTRY` 新增 `translate` 项 | 注册 translate 开关 |
| ~952 | 新增 `_now` / `_weekday_cn` / `_current_time` | 提前提取时间变量 |
| ~954 | 新增 `_translate_mode` + 数据容器变量 | 分流判断 |
| ~957-960 | Step ① 包裹 translate 分支 | translate 模式跳过 format 注入 |
| ~963-968 | Step ② 包裹 translate 分支 | translate 模式用 _filter_fixed_rules |
| ~970-995 | Step ③ 包裹 translate 分支 | translate 模式用 raw 函数 |
| ~998-1020 | Step ④a 包裹 translate 分支 | translate 模式只提取 today_turn |
| ~1062-1103 | Step ④b 包裹 translate 分支 | translate 模式用 ev.top3() |
| ~1106-1114 | Step ④ 包裹 translate 分支 | translate 模式暂存 variance_items |
| ~1186 前 | 新增 translate 拼装 + parts.insert(0) | 将 narrative 插入 parts 头部 |

**关键设计约束：**
- translate 模式下，`parts` 的结构变为：`[narrative, memory, kanban]`（debug 由 transform 追加）
- `_daily_turn_count_hint()` 在 translate 模式下仍被调用，以保证轮数计数器的副作用（持久化）
- `_save_reply_timing()` 在 translate 模式下**未调用**。需要单独调用以保证 reply_timing.json 写入。**TODO：确认是否需要在 translate 分支中也调用 `_save_reply_timing()`**

**验证命令：**

```bash
# translate: false — 旧模式完全不变
python -m pytest tests/ -v
# 期望: 346 passed（无回归）

# translate: true — 快速冒烟测试
python -c "
import injector
# 直接调用 inject_context 不现实，但可验证 import 和函数存在
from injector import _assemble_narrative, _filter_fixed_rules
from dynamic_rules import _get_time_slot_desc, _get_turn_stage_hint
print('All imports OK')
"
```

**风险等级：** 🟡 中 — 涉及核心注入流程 `inject_context()` 的条件分支重构。旧分支代码一字不改，新分支通过 `_translate_mode` 变量隔离。

**回滚：** `git checkout -- injector.py`

---

### Phase 6: 测试 — 新建 tests/test_translate.py

**目标：** 覆盖 SPEC-009 §10 的全部 8 个测试用例（T-01~T-08）。

**文件：** `tests/test_translate.py`（新建）

#### 6.1 测试结构

```python
"""Tests for injection rule translation (narrative assembly) — SPEC-009."""

import pytest
from unittest.mock import patch, MagicMock

import injector as injector
from injector import (
    _assemble_narrative,
    _filter_fixed_rules,
    _clean_variance_item,
)


class TestAssembleNarrative:
    """_assemble_narrative() 单元测试 — T-01~T-05, T-08."""

    def test_T01_all_data_complete(self):
        """T-01: 全部数据完整 → 五个段落全部输出。"""
        ...

    def test_T02_empty_time_slot_desc(self):
        """T-02: time_slot_desc 为空 → 跳过时段描述，时间仍输出。"""
        ...

    def test_T03_top3_all_zero(self):
        """T-03: top3 为空（所有维度为 0）→ 跳过表达向量段落。"""
        ...

    def test_T04_empty_variance_items(self):
        """T-04: variance_items 为空 → 跳过随机变化段落。"""
        ...

    def test_T05_only_one_dimension(self):
        """T-05: 只有 1 个维度有值 → 只输出有值的维度。"""
        ...

    def test_T08_today_turn_zero(self):
        """T-08: today_turn=0 → 跳过轮数段落。"""
        ...


class TestFilterFixedRules:
    """_filter_fixed_rules() 单元测试 — T-07."""

    def test_T07_excludes_replaced_rules(self):
        """T-07: 🦊/💬/📊表达向量 规则被排除。"""
        ...

    def test_keep_cc_background_rule(self):
        """📊 使用Claude Code... 规则（不含「表达向量」）不被误排除。"""
        ...


class TestTranslateIntegration:
    """translate 模式集成测试 — T-06."""

    def test_T06_translate_false_unchanged(self):
        """T-06: translate: false → 保持旧格式输出。"""
        ...

    def test_translate_true_uses_narrative(self):
        """translate: true → context 以 narrative 格式开头。"""
        ...


class TestCleanVarianceItem:
    """_clean_variance_item() 单元测试。"""

    def test_removes_emoji_prefix(self):
        ...

    def test_removes_body_language_suffix(self):
        ...

    def test_no_change_when_clean(self):
        ...
```

#### 6.2 T-01 实现要点（全部数据完整）

```python
def test_T01_all_data_complete(self):
    """T-01: 全部数据完整 → 五个段落全部输出。"""
    result = _assemble_narrative(
        weekday="周四",
        current_time="20:29",
        time_slot_desc="晚间——主人这段时间一般会继续工作，保持高效和温暖的工作节奏即可。",
        today_turn=30,
        turn_stage_hint=None,
        top3=[("工作投入", 16, "→"), ("亲密温度", 5, "→")],
        variance_items=["蓬松的大狐尾", "女仆礼仪,温柔感强"],
        fixed_rules=["感知表达自然化", "核心态度", "永远不赶主人去睡觉"],
    )
    assert "现在时间是：周四，20:29" in result
    assert "晚间——主人这段时间一般会继续工作" in result
    assert "这是今天的第30轮对话" in result
    assert "主人目前的状态是" in result
    assert "工作投入（→）" in result
    assert "亲密温度（→）" in result
    assert "蓬松的大狐尾" in result
    assert "女仆礼仪" in result
    assert "感知表达自然化" in result
    assert "核心态度" in result
```

#### 6.3 T-06 实现要点（translate: false 集成测试）

```python
def test_T06_translate_false_unchanged(self):
    """T-06: translate: false（默认）→ 保持旧格式输出。"""
    config = {
        "modules": {"translate": False},
        "time": {"format": "cn_full"},
        "context": {"rules": ["测试规则"]},
    }
    with patch("injector._load_config", return_value=config):
        result = injector.inject_context(
            session_id="test",
            user_message="你好",
            conversation_history=[],
            is_first_turn=True,
            model="test",
            platform="test",
        )
    assert result is not None
    assert "🕐" in result["context"]  # 旧格式时间
    assert "测试规则" in result["context"]
    # 不应包含 narrative 格式
    assert "现在时间是" not in result["context"]
    assert "主人目前的状态是" not in result["context"]
```

#### 6.4 top3() 专项测试

```python
class TestExpressionVectorTop3:
    """expression_vector.py top3() 方法测试。"""

    def test_top3_basic(self):
        """基本功能：排序后返回 top 3。"""
        from expression_vector import _ExpressionVector
        ev = _ExpressionVector(
            {"dimensions": {
                "work": ["code"],
                "play": ["game"],
                "intimacy": ["warm"],
                "care": ["help"],
            }},
            "test",
        )
        ev.vectors = {"work": 16.0, "play": 2.0, "intimacy": 7.0, "care": 0.0}
        result = ev.top3(n=3, trend=False)
        # care=0 应被跳过
        assert len(result) == 3
        assert result[0][0] == "工作投入"  # label from _DEFAULT_LABELS
        assert result[0][1] == 16
        assert result[1][0] == "亲密温度"
        assert result[2][0] == "轻松玩乐"

    def test_top3_with_trend(self):
        """趋势计算：比较上轮值。"""
        from expression_vector import _ExpressionVector
        ev = _ExpressionVector(
            {"dimensions": {"work": ["code"]}},
            "test",
        )
        ev.vectors = {"work": 16.0}
        # 注入一条历史记录
        ev.vector_history.append({"vectors": {"work": 10.0}})
        result = ev.top3(n=1, trend=True)
        assert result[0][2] == "↑"  # 16 > 10

    def test_top3_less_than_n(self):
        """维度少于 n 个时返回实际数量。"""
        ...
```

#### 6.5 操作

```bash
# 创建测试文件
touch tests/test_translate.py
# 写入所有测试用例（T-01~T-08 + top3 专项 + clean 专项）

# 运行新测试（预期全部 FAIL 或部分 PASS，因为 _assemble_narrative 已在 Phase 2 实现）
python -m pytest tests/test_translate.py -v
```

**验证标准：**
- 所有 8 个 SPEC 用例 + 补充测试全部 PASSED
- 现有 346 个测试无回归

**风险等级：** 🟡 中 — 新建文件，T-06 涉及 `patch` mock 集成测试

**回滚：** `rm tests/test_translate.py`

---

### Phase 7: 全量验收 — 346+ passed

**目标：** 确保所有新增测试通过，且所有现有测试不受影响。

**操作：**

```bash
# 运行全部测试
python -m pytest tests/ -v

# 期望输出:
# - tests/test_translate.py      全部 PASSED（~15 个用例）
# - tests/test_injector.py       全部 PASSED（无回归）
# - tests/test_expression_vector.py 全部 PASSED（无回归）
# - tests/test_dynamic_rules.py  全部 PASSED（无回归）
# - tests/test_modules_switch.py 全部 PASSED（无回归）
# - 其余测试文件                  全部 PASSED（无回归）
# 总计: 361+ passed, 0 failure
```

**快速回归检查清单：**

```bash
# 1. translate: false — 旧行为不变
python -m pytest tests/test_injector.py tests/test_dynamic_rules.py tests/test_modules_switch.py -v

# 2. 表达向量测试 — top3() 不影响旧方法
python -m pytest tests/test_expression_vector.py -v

# 3. 新测试全部通过
python -m pytest tests/test_translate.py -v

# 4. 全量回归
python -m pytest tests/ -v
```

**验证标准：**
- 0 failure
- 0 error
- 现有 346 个测试无回归
- 新测试 ~15 个全部 PASSED

**风险等级：** 🟢 低 — 仅运行测试，不改动代码

**回滚：** 无需回滚（如有失败，退回到对应 Phase 修复）

---

### Phase 8: 文档更新 — README / CHANGELOG / 示例配置

**目标：** 更新项目文档和示例配置文件以反映新功能。

#### 8.1 更新 `examples/persona-config.json`

在 `modules` 块中新增 `translate` 开关（`"debug": false` 之后）：

```json
        "debug": false,
        "translate": false
```

#### 8.2 更新 `README.md`（如存在）

在模块开关说明表中新增一行：

```markdown
| `translate` | 注入规则转译 — 自然语言拼装替代逐模块堆叠 | `false` |
```

**风险等级：** 🟢 低 — 仅文档和示例配置

**回滚：** `git checkout -- examples/persona-config.json README.md`

---

## 3. 风险点与回滚方案

### 3.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|:---|:---|:---|:---|
| `_daily_turn_count_hint()` 在 translate 模式被调两次 | 中 | 中 | translate 模式只在 ④a 块内调用一次，通过正则提取 count |
| translate 模式下 `_save_reply_timing()` 未调用导致数据丢失 | 中 | 低 | translate 模式下 ④a 块走独立分支，需确认是否需要单独调用 `_save_reply_timing()` |
| `dimension_labels` 元数据存取遗漏旧格式维度 | 低 | 低 | top3() 有三重回退（label → _DEFAULT_LABELS → dim_name） |
| 旧分支被意外改动导致回归 | 低 | 高 | 旧分支代码一字不改，仅用 `if _translate_mode: ... else:` 包裹 |
| `parts.insert(0, narrative)` 打乱 debug 摘要解析顺序 | 低 | 低 | debug 摘要遍历 parts 搜索 marker，narrative 不含 emoji 前缀不会被误匹配 |
| `📊 使用Claude Code` 规则被误排除 | 低 | 中 | `_filter_fixed_rules()` 对 `📊` 规则加「表达向量」子条件，T-07 专项测试覆盖 |

### 3.2 回滚方案

所有改动集中在 4 个文件：

| 回滚方式 | 操作 |
|:---|:---|
| **完整回滚** | `git checkout -- injector.py expression_vector.py dynamic_rules.py examples/persona-config.json` |
| **删除新测试** | `rm tests/test_translate.py` |
| **Git 回滚** | `git stash` 或 `git reset --hard HEAD` |

**关键安全边界：**
- `guard.py` 完全未触碰
- `variance.py` 完全未触碰
- `__init__.py` 中的 Hook 注册逻辑不变
- 注入顺序：translate 模式下 narrative 插入 parts 头部，memory/kanban 在之后追加
- `inject_context()` 外层 `try/except` 不变
- translate 默认 `false`，零风险

---

## 4. 验证检查清单

实施完成后的最终验证：

### 4.1 自动化测试

- [ ] `python -m pytest tests/ -v` — 全部 PASSED（361+），0 failure
- [ ] `tests/test_translate.py` — T-01~T-08 全部 PASSED
- [ ] `tests/test_expression_vector.py` — 全部 PASSED（top3() 不影响旧测试）
- [ ] `tests/test_dynamic_rules.py` — 全部 PASSED（raw 函数不影响旧测试）
- [ ] `tests/test_injector.py` — 全部 PASSED（无回归）
- [ ] `tests/test_modules_switch.py` — 全部 PASSED（无回归）

### 4.2 SPEC 用例覆盖

- [ ] T-01: 全部数据完整 → 五个段落全部输出
- [ ] T-02: time_slot_desc 为空 → 跳过时段描述，时间仍输出
- [ ] T-03: top3 全为 0 → 跳过表达向量段落
- [ ] T-04: variance_items 为空 → 跳过随机变化段落
- [ ] T-05: 只有 1 个维度有值 → 只输出有值的维度
- [ ] T-06: translate: false → 保持旧格式输出
- [ ] T-07: 🦊/💬/📊表达向量 规则被排除
- [ ] T-08: today_turn=0 → 跳过轮数段落

### 4.3 手动验证

- [ ] translate: false（默认）→ 输出与改动前完全一致
- [ ] translate: true → 输出为自然语言段落格式
- [ ] translate: true + 部分模块关闭 → 对应段落跳过
- [ ] translate: true + debug: true → debug 摘要追加在 narrative 之后
- [ ] `examples/persona-config.json` JSON 格式合法
- [ ] `_filter_fixed_rules()` 正确保留 `📊 使用Claude Code` 规则

### 4.4 代码审查

- [ ] `top3()` 分值为 0 的维度不返回
- [ ] `top3()` label 回退链完整（label → _DEFAULT_LABELS → dim_name）
- [ ] `_trend()` 三态行为正确（↑/↓/→）
- [ ] `_assemble_narrative()` 五段落按顺序输出
- [ ] `_clean_variance_item()` 正确去除 emoji 前缀和「的肢体语言表达」后缀
- [ ] `_filter_fixed_rules()` 三条排除规则 + 📊 子条件
- [ ] `_get_time_slot_desc()` / `_get_turn_stage_hint()` 与原有匹配逻辑一致
- [ ] translate 分支中旧代码完全不变（仅用 if/else 包裹）
- [ ] `_daily_turn_count_hint()` 副作用在 translate 模式仍执行
- [ ] `_save_reply_timing()` 副作用确认（translate 模式是否需要单独调用）

---

*🦊 知惠 · 2026-05-21 · PLAN-009 v1.0 · 等待主人审阅*
