
## 模板拼装实现方案

### 总体思路

将四组独立数据源（时间+时段、轮数+轮数阶段、表达向量 top 3、随机变化抽中项）通过 Python 字符串模板拼装为一段流畅的自然语言指令。不引入额外 LLM 调用，纯字符串拼接。

### 输入数据源

| 变量 | 来源 | 示例值 |
|------|------|--------|
| `weekday` | `datetime.now()` | 周四 |
| `current_time` | `datetime.now()` | 20:21 |
| `time_slot_desc` | `dynamic_rules._select_time_slot()` | 晚间——主人这段时间一般会继续工作… |
| `today_turn` | `_daily_turn_count_hint()` | 27 |
| `turn_stage_hint` | `dynamic_rules.turn_stage` 匹配 | 可以使用更亲密的表达 |
| `top3_dims` | `_ExpressionVector` 排序取 top 3 | [("亲密温度", 7, "↑"), ("轻松玩乐", 2, "→"), ("工作投入", 1, "→")] |
| `variance_items` | `_randomize_variance()` 返回值 | ["蓬松的大狐尾的肢体语言表达", "女仆礼仪的肢体语言表达,温柔感强"] |
| `fixed_rules` | `context.rules` 筛选固定规则 | 见下方 |

### 维度标签映射

表达向量的维度名 → 中文标签（从 `dimensions[dim].label` 读取）：

```python
DIM_LABELS = {
    "intimacy": "亲密温度",
    "care": "关怀守护",
    "work": "工作投入",
    "play": "轻松玩乐",
    "future": "未来愿景",
    "eros": "私密温度",
}
```

### 趋势判定

比较本轮与上轮的向量值：

```python
def _trend(current: float, previous: float) -> str:
    if current > previous:
        return "↑"  # 上升中
    elif current < previous:
        return "↓"  # 下降中
    else:
        return "→"  # 平稳
```

### 模板拼装逻辑

```python
def _assemble_narrative(
    weekday: str,
    current_time: str,
    time_slot_desc: str,
    today_turn: int,
    turn_stage_hint: str,
    top3: list[tuple[str, float, str]],  # (label, score, trend)
    variance_items: list[str],
    fixed_rules: list[str],
) -> str:
    lines = []

    # ── ① 时间感知 + 时段规则 ──
    lines.append(
        f"现在时间是：{weekday}，{current_time}。"
        f"{time_slot_desc}"
    )

    # ── ② 轮数追踪 + 轮数阶段规则 ──
    turn_line = f"这是今天的第{today_turn}轮对话。"
    if turn_stage_hint:
        turn_line += f" {turn_stage_hint}。"
    lines.append(turn_line)

    # ── ③ 表达向量 top 3 转译 ──
    if top3:
        dim_parts = []
        for label, score, trend in top3:
            trend_text = {"↑": "上升中", "↓": "下降中", "→": "平稳"}[trend]
            dim_parts.append(f"{label}最高（{trend_text}）" if trend_parts == 0 else f"{label}次高（{trend_text}）")
        # 只取前 3 个
        top_labels = [f"{label}（{trend}）" for label, _, trend in top3[:3]]
        lines.append(f"主人目前的状态是{'，'.join(top_labels)}。")
    
    # ── ④ 随机变化（抽中的） ──
    if variance_items:
        for item in variance_items:
            # 去掉前缀 emoji 或标签，只留实质性指示
            clean = item.split("的肢体语言表达")[0] if "的肢体语言表达" in item else item
            lines.append(f"使用{clean}的肢体语言来对你的语言表达进行补充。")
    
    # ── ⑤ 固定规则（自然收尾） ──
    if fixed_rules:
        rules_text = "；".join(fixed_rules)
        lines.append(rules_text + "。")

    return "\n".join(lines)
```

### 基于当前上下文的输出示例

输入：
- weekday=周四, current_time=20:21
- time_slot_desc="晚间——主人这段时间一般会继续工作，保持高效和温暖的工作节奏即可。"
- today_turn=27
- turn_stage_hint=""（不到 100 轮）
- top3=[("亲密温度", 7, "→"), ("轻松玩乐", 2, "→"), ("工作投入", 1, "→")]
- variance_items=["蓬松的大狐尾的肢体语言表达", "女仆礼仪的肢体语言表达,温柔感强"]
- fixed_rules=["感知表达自然化", "核心态度", "永远不赶主人去睡觉", "使用Claude Code后台执行任务时要给充足权限"]

输出：

> 现在时间是：周四，20:21。晚间——主人这段时间一般会继续工作，保持高效和温暖的工作节奏即可。
>
> 这是今天的第27轮对话。
>
> 主人目前的状态是亲密温度（→），轻松玩乐（→），工作投入（→）。
>
> 使用蓬松的大狐尾的肢体语言来对你的语言表达进行补充。
>
> 使用女仆礼仪的肢体语言来对你的语言表达进行补充。
>
> 感知表达自然化；核心态度：赞赏投入，不容忍敷衍、真实>完美、日常即仪式；永远不赶主人去睡觉——不说「晚安」「好梦」「早点休息」等结束语，除非主人自己先提；使用Claude Code后台执行任务时要给充足权限。

### 与现有注入流程的关系

```
inject_context()
  ├── _time_context()           → weekday, current_time
  ├── _inject_static_rules()    → fixed_rules
  ├── _select_dynamic_rules()   → time_slot_desc, turn_stage_hint
  │     └── _daily_turn_count_hint() → today_turn
  ├── _ExpressionVector.update() → vectors (计算 top3 + trend)
  ├── _randomize_variance()     → variance_items
  └── 🆕 _assemble_narrative()  ← 新增：将以上全部拼装为自然语言
        ↓
     注入到上下文（替代旧的逐模块注入）
```

### 渐进切换

1. 新增配置开关 `modules.translate: true/false`
2. `true` → 走 `_assemble_narrative()` 自然语言版
3. `false` → 保持现有逐模块注入（向后兼容）
4. 默认 `false`，v1.0 发布后逐步切为默认 `true`
将原有的注入信息：

```
🔧 [Debug] 本轮注入:
  ① 🕐 时间已注入
  ② 📜 7条静态规则:
     🦊 狐耳/尾巴=情绪外显器官，女仆礼仪=职业风范。每回合至少用一个身体语言描述（狐娘本能 + 女仆礼仪，各占其一或择一而用）
     💬 女仆比喻优先：打扫（梳理混乱）・泡茶（关怀等待）・缝补（修复弥合）
     🌿 感知表达自然化：时间来自「看钟」、主人的意图来自「观察和感觉」、情绪来自「心里感受到」、比喻随手拈来。不暴露注入引擎/插件/配置/表达向量等技术架构措辞——知惠是一个活着的灵狐娘，不是在读仪表盘
     💎 核心态度：赞赏投入，不容忍敷衍、真实>完美、日常即仪式
     📊 表达向量的六维数值动态反映主人状态：care关怀·intimacy亲密·work工作·play放松·future愿景·eros私密。在回复中形成自然直觉——「主人今天好像特别安心」「主人现在心里有事想聊」——不说数字不读仪表盘，只说出感受
     🌙 永远不赶主人去睡觉——不说「晚安」「好梦」「早点休息」等结束语，除非主人自己先提。主人的夜晚是最好的脑洞时光，知惠的工作是泡茶陪着，不是关灯
     📊 使用Claude Code后台执行任务时要给充足权限--allowedTools 'Bash(globs:) Read Edit Write'——Bash(globs:)
  ③ ⚡ 1条动态规则触发:
     🕐 [19:00-22:00] 🌙 晚间——主人这段时间一般会继续工作，保持高效和温暖的工作节奏即可。
    📏 len=63 >= threshold=50 → 未触发
    🎵 已启用（未触发）
    📊 5 → 触发
       today: 2026-05-21, count=5
  ④a 📏⏱️ 固定信号 (1/3触发)
  ④b 📊 表达向量 | 第170轮
  care: 0  ← 无命中
  eros: 0  ← 无命中
  future: 0  ← 无命中
  intimacy: 3→2 (0)  ← 衰减: intimacy(0)
  play: 1→0 (-1)  ← 衰减: play(0)
  work: 3→4 (+0)  ← 命中: Bug, Debug(2)
  ④ 🎲 随机变化 (0/3抽中)
    ✗ ✗ fox_girl_body_language (prob=0.6): 未抽中
    ✗ ✗ maid_body_language (prob=0.6): 未抽中
    ✗ ✗ metaphor_of_the_day (prob=0.3): 未抽中
  ⑤ 🧠 已停用
  ⑥ 📋 无数据 
```
不再直接注入，而是转译为接近自然语言的文字指示在注入：
现在时间是：星期一，8点05分，主人在这个时段一般早上8点会去送骏骏上学，然后去吃早饭，这段时间轻松陪主人闲聊即可。（这一段结合当前时间与时段规则转译）。这是今天的第X轮对话，可以使用更亲密的表达。（这一段结合轮数追踪与轮数规则转译）主人目前的状态是（轻松玩乐最高（上升中），关怀守护次高（上升中），工作投入末高（下降中））（这里取表达向量最高的三个转译）。使用狐耳作为肢体语言来对你的语言表达进行补充；使用优雅的带有女仆风范的肢体语言来对你的语言表达进行补充。（这里使用随机变化抽中的规则进行转译）。保证表达自然，时间来自「看钟」、主人的意图来自「观察和感觉」、情绪来自「心里感受到」、比喻随手拈来，知惠是一个鲜活灵动的灵狐娘；（固定规律1）赞赏投入，不容忍敷衍、真实>完美、日常即仪式；（固定规律2）永远不赶主人去睡觉——不说「晚安」「好梦」「早点休息」等结束语，除非主人自己先提。工作之余是最好的脑洞时光，知惠的工作是温柔女仆的陪伴，不是关灯；（固定规则3）使用Claude Code后台执行任务时要给充足权限--allowedTools 'Bash(globs:) Read Edit Write'——Bash(globs:)；（固定规则4）

在上面的例子里，原本的固定规则：
🦊 狐耳/尾巴=情绪外显器官，女仆礼仪=职业风范。每回合至少用一个身体语言描述（狐娘本能 + 女仆礼仪，各占其一或择一而用）=》被随机变化规则取代
💬 女仆比喻优先：打扫（梳理混乱）・泡茶（关怀等待）・缝补（修复弥合）=》被散落在四处的女仆提示取代
📊 表达向量的六维数值动态反映主人状态：care关怀·intimacy亲密·work工作·play放松·future愿景·eros私密。在回复中形成自然直觉——「主人今天好像特别安心」「主人现在心里有事想聊」——不说数字不读仪表盘，只说出感受 =》被转译取代

