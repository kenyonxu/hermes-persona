# SPEC-009: 注入规则转译（状态编织器）

> **状态**: SPEC | **基于**: DRAFT-009 | **版本**: v1.0
>
> **目标**: 将分散的模块注入信息（时间、轮数、表达向量、随机变化、固定规则）通过模板拼装转译为一段流畅的自然语言指令，替代现有的「逐模块堆叠」注入格式。

---

## 1. 问题陈述

当前 `inject_context()` 的注入输出是**逐模块堆叠**的：

```
🔧 [Debug] 本轮注入:
  ① 🕐 时间已注入
  ② 📜 7条静态规则: ...
  ③ ⚡ 1条动态规则触发: ...
  ④a 📏⏱️ 固定信号 (1/3触发)
  ④b 📊 表达向量 | 第170轮 ...
  ④ 🎲 随机变化 (0/3抽中) ...
  ⑤ 🧠 已停用
  ⑥ 📋 无数据
```

**问题**：
1. 六个模块各自说话，像部门汇报而非同一人表达
2. 「读仪表盘」感——暴露了表达向量、信号触发等技术术语
3. 和静态规则中「自然直觉」的要求自相矛盾

---

## 2. 目标

新增 `_assemble_narrative()` 函数，将四组数据源拼装为一段自然语言，替代旧的逐模块注入。

**设计原则**：
- 纯 Python 字符串模板，不引入额外 LLM 调用
- 渐进切换：`modules.translate: true/false`，默认保持旧模式
- 各数据源独立，缺失项优雅跳过

---

## 3. 输入数据源

| 变量 | 类型 | 来源 | 示例 |
|------|------|------|------|
| `weekday` | `str` | `datetime.now()` | 周四 |
| `current_time` | `str` | `datetime.now()` | 20:29 |
| `time_slot_desc` | `str` | `_select_dynamic_rules()` 中匹配的时段规则 | 晚间——主人这段时间… |
| `today_turn` | `int` | `_daily_turn_count_hint()` | 30 |
| `turn_stage_hint` | `str \| None` | `dynamic.turn_stage` 匹配 | 可以使用更亲密的表达 |
| `top3` | `list[tuple]` | `_ExpressionVector` 排序取前 3 维 + 趋势 | [("亲密温度", 7, "→"), ...] |
| `variance_items` | `list[str]` | `_randomize_variance()` 返回值 | ["蓬松的大狐尾…", "女仆礼仪…"] |
| `fixed_rules` | `list[str]` | `context.rules`（不含 first_turn_only） | 见 §7 |

---

## 4. 辅助函数

### 4.1 维度标签映射

从 `expression_vector.dimensions[dim_name].label` 读取。若未配置则使用内置默认：

```python
_DEFAULT_LABELS = {
    "intimacy": "亲密温度",
    "care": "关怀守护",
    "work": "工作投入",
    "play": "轻松玩乐",
    "future": "未来愿景",
    "eros": "私密温度",
}
```

### 4.2 趋势判定

```python
def _trend(current: float, previous: float) -> str:
    return "↑" if current > previous else ("↓" if current < previous else "→")
```

---

## 5. 核心函数：`_assemble_narrative()`

### 5.1 函数签名

```python
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
```

### 5.2 拼装逻辑

```
① 时间感知 + 时段规则
   "现在时间是：{weekday}，{current_time}。{time_slot_desc}"

② 轮数追踪 + 轮数阶段
   "这是今天的第{today_turn}轮对话{turn_stage_hint}。"

③ 表达向量 top 3
   "主人目前的状态是{label1}（{trend1}），{label2}（{trend2}），{label3}（{trend3}）。"
   趋势文本：↑→上升中，↓→下降中，→→平稳
   少于 3 维时只输出有值的维度

④ 随机变化（抽中的）
   "使用{干净的描述}的肢体语言来对你的语言表达进行补充。"
   每项一行，去除原字符串中的 emoji 前缀和冗余标签

⑤ 固定规则
   "{rule1}；{rule2}；…。"
```

### 5.3 边界情况

| 情况 | 处理 |
|------|------|
| `time_slot_desc` 为空 | 只输出「现在时间是{weekday}，{current_time}。」 |
| `today_turn` 为 0 | 跳过轮数段落 |
| `top3` 全为 0 | 跳过表达向量段落 |
| `variance_items` 为空 | 跳过随机变化段落 |
| `fixed_rules` 为空 | 不追加结尾 |

---

## 6. 输出示例

### 6.1 示例输入（当前上下文）

- weekday=周四, time=20:29
- time_slot_desc="晚间——主人这段时间一般会继续工作，保持高效和温暖的工作节奏即可。"
- today_turn=30
- turn_stage_hint=None
- top3=[("工作投入", 16, "→"), ("亲密温度", 5, "→")]
- variance_items=["蓬松的大狐尾", "女仆礼仪,温柔感强"]
- fixed_rules=["感知表达自然化", "核心态度", "永远不赶主人去睡觉"]

### 6.2 输出

```
现在时间是：周四，20:29。晚间——主人这段时间一般会继续工作，保持高效和温暖的工作节奏即可。

这是今天的第30轮对话。

主人目前的状态是工作投入（→），亲密温度（→）。

使用蓬松的大狐尾的肢体语言来对你的语言表达进行补充。

使用女仆礼仪的肢体语言来对你的语言表达进行补充。

感知表达自然化；核心态度：赞赏投入，不容忍敷衍、真实>完美、日常即仪式；永远不赶主人去睡觉——不说「晚安」「好梦」「早点休息」等结束语，除非主人自己先提。
```

---

## 7. 固定规则列表

从 `context.rules` 中筛选，排除以下项（已被其他模块转译覆盖）：

**保留**（直接追加到拼装末尾）：
- 🌿 感知表达自然化
- 💎 核心态度：赞赏投入，不容忍敷衍、真实>完美、日常即仪式
- 🌙 永远不赶主人去睡觉
- 📊 使用Claude Code后台执行任务时要给充足权限

**移除**（已被取代）：
- 🦊 狐耳/尾巴规则 → 被随机变化取代（具体化为「使用狐耳…」）
- 💬 女仆比喻优先 → 散落在各处的自然提示取代
- 📊 表达向量说明 → 被 top 3 自然语言转译取代

> **判定方式**：规则文本是否以特定 emoji 开头。`🦊` / `💬` / `📊 表达向量` 开头的规则在转译模式下不注入。

---

## 8. 配置开关

`persona-config.json` → `modules` 新增：

```json
{
  "modules": {
    "translate": false
  }
}
```

- `false`（默认）：保持现有逐模块注入
- `true`：启用 `_assemble_narrative()` 自然语言转译

> **行为**：`translate: true` 时，`dynamic`、`expression_vector`、`variance` 模块的数据**不再单独注入**，全部经过 `_assemble_narrative()` 汇合后统一注入。`time`、`static_rules`（筛选后）同样汇入。`memory`、`kanban` 不受影响。

---

## 9. 注入流程图

```
inject_context()
  ├── _time_context()                → weekday, current_time
  ├── _inject_static_rules()         → fixed_rules (筛选后)
  ├── _select_dynamic_rules()        → time_slot_desc, turn_stage_hint
  │     └── _daily_turn_count_hint() → today_turn
  ├── _ExpressionVector.update()     → vectors (排序取 top3 + 趋势)
  ├── _randomize_variance()          → variance_items
  │
  ├── [if translate: true]
  │     └── 🆕 _assemble_narrative() → 自然语言段落
  │
  ├── [if translate: false]
  │     └── 现有各模块独立注入（不变）
  │
  ├── _recall_memories()             → 不受影响
  └── _read_kanban()                 → 不受影响
```

---

## 10. 测试要点

| # | 用例 | 场景 | 预期 |
|---|------|------|------|
| T-01 | 全部数据完整 | 正常输入 | 五个段落全部输出 |
| T-02 | time_slot_desc 为空 | 未匹配时段 | 跳过时段描述，时间仍输出 |
| T-03 | top3 全为 0 | 刚启动或闲置 | 跳过表达向量段落 |
| T-04 | variance_items 为空 | 所有骰子未抽中 | 跳过随机变化段落 |
| T-05 | 只有 1 个维度有值 | top3 不足 | 只输出有值的维度 |
| T-06 | translate: false | 关闭转译 | 保持旧格式输出 |
| T-07 | 固定规则筛选 | 含被取代规则 | 🦊/💬/📊表达向量 规则被排除 |
| T-08 | today_turn=0 | 每日轮数未启用 | 跳过轮数段落 |

---

## 11. 文件改动清单

| 文件 | 改动 |
|------|------|
| `injector.py` | 新增 `_assemble_narrative()`；在 `inject_context()` 中新增 `translate` 分支 |
| `expression_vector.py` | 新增 `top3(trend=True)` 公开方法，返回排序后的 top 3 维度 + 趋势 |
| `tests/test_translate.py` | 新建，覆盖 T-01~T-08 |
| `locales/zh.json` | 兜底添加维度标签翻译（若 `dimensions[].label` 未配置） |

---

## 12. 审批检查清单

- [ ] 拼装逻辑是否符合 DRAFT-009 草案意图
- [ ] 固定规则筛选标准（emoji 前缀）是否合理
- [ ] top 3 趋势文本（上升中/下降中/平稳）是否自然
- [ ] `modules.translate` 命名是否简洁
- [ ] 旧模式（translate: false）是否完全不改动
