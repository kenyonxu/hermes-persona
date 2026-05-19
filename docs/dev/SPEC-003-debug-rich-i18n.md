# SPEC-003: Debug 面板增强 — 详细模式 + 国际化

**版本**: v1.0  
**日期**: 2026-05-19  
**作者**: 知惠 (zhihui)  
**类型**: 功能增强（已有模块改进，无架构变更）

---

## 1. 背景

US-002 完成后，debug 面板通过 `transform_llm_output` hook 可靠地拼接到 LLM 回复末尾，不再污染上下文。当前 debug 输出为紧凑模式：

```
🔧 [Debug] 本轮注入:
  ① 🕐 时间已注入
  ② 📜 8条静态规则
  ③ ⚡ time_slots: on / turn_stage: off / keyword: on
  ④a 📏⏱️ 固定信号已注入
  ④b 📊 care:2 eros:0 future:0 intimacy:0 play:0 work:0
  ④ 🎲 2条变化
  ⑤ 🧠 已停用
  ⑥ 📋 无数据
```

两个改进方向：
- **详细模式**：增加每模块的细节（触发了什么、为什么、delta），方便开发调试
- **国际化**：支持中英双语，为公开发布准备

---

## 2. 功能需求

### 2.1 显示模式切换

新增 `debug.detail` 配置键：

```json
"debug": {
  "enabled": true,
  "visible": true,
  "detail": "compact"   // "compact" | "detailed"
}
```

| 模式 | 行为 |
|------|------|
| `compact` | 当前格式（默认，向后兼容） |
| `detailed` | 每模块展开子行，显示触发细节 |

### 2.2 详细模式内容

#### ④a 固定信号 — 详细

```
④a 📏⏱️ 固定信号 (3/3触发)
  📏 message_length: len=3 < threshold=50 → 触发
  🎵 reply_gap: 已启用（未触发）
     last_reply: 2026-05-19 19:25:32 (gap=0.5min, threshold=30min)
  📊 daily_turn_count: 42 → 触发
     today: 2026-05-19, count=42
```

#### ④b 表达向量 — 详细

```
④b 📊 表达向量 | 第174轮
  care: 2→3 (+1)  ← 命中: "吃饭"(1) / 衰减: intimacy(-1.5) play(-1)
  eros: 0 (无命中)
  future: 0→1 (+1) ← 命中: "以后"(1)
  intimacy: 3 (无命中)
  play: 0 (无命中)
  work: 5→6 (+1)  ← 命中: "spec"(1)
```

#### ④ 随机变化 — 详细

```
④ 🎲 随机变化 (2/3抽中)
  ✓ fox_girl_body_language (prob=0.6): "🦊 狐耳与狐尾联动的肢体语言表达"
  ✗ maid_body_language (prob=0.6): 未抽中
  ✗ metaphor_of_the_day (prob=0.3): 未抽中
```

### 2.3 国际化 (i18n)

#### 配置

```json
"language": "zh"   // "zh" | "en" | "auto"
```

- `zh`：中文输出
- `en`：英文输出
- `auto`：从 `time.format` 推断（`cn_full` → zh，`iso` → en）

#### 翻译文件结构

```
hermes_persona/
└── locales/
    ├── zh.json    # 中文翻译
    └── en.json    # 英文翻译
```

#### 翻译范围

所有 debug 输出的固定文本（模块名、状态描述、触发说明）。

**zh.json 示例**：
```json
{
  "debug.header": "🔧 [Debug] 本轮注入:",
  "modules.time.injected": "时间已注入",
  "modules.time.stopped": "已停用",
  "modules.static_rules": "{count}条静态规则",
  "modules.static_rules.stopped": "已停用",
  "modules.dynamic": "{status}",
  "modules.dynamic.stopped": "已停用",
  "modules.fixed_signals.triggered": "固定信号 ({triggered}/{total}触发)",
  "modules.fixed_signals.none": "固定信号 (无触发)",
  "modules.expression_vector": "表达向量",
  "modules.expression_vector.hit": "命中: {keywords}({count})",
  "modules.expression_vector.decay": "衰减",
  "modules.expression_vector.no_hit": "无命中",
  "modules.variance": "随机变化 ({hit}/{total}抽中)",
  "modules.variance.none": "随机变化 (0条)",
  "modules.memory.stopped": "已停用",
  "modules.kanban.no_data": "无数据",
  "modules.kanban.stopped": "已停用",
  "signal.message_length.triggered": "len={len} < threshold={threshold} → 触发",
  "signal.message_length.idle": "len={len} >= threshold={threshold} → 未触发",
  "signal.reply_gap.triggered": "gap={gap}min > threshold={threshold}min → 触发",
  "signal.reply_gap.idle": "last_reply: {last_reply} (gap={gap}min, threshold={threshold}min)",
  "signal.daily_turn.triggered": "{count} → 触发",
  "signal.daily_turn.info": "today: {date}, count={count}",
  "variance.hit": "✓ {name} (prob={prob}): \"{chosen}\"",
  "variance.miss": "✗ {name} (prob={prob}): 未抽中"
}
```

### 2.4 兼容性

- `debug.detail` 省略时默认 `"compact"` — **完全向后兼容**
- `language` 省略时从 `time.format` 推断，无 `time.format` 时默认 `"zh"`
- 翻译文件缺失时回退到硬编码中文字符串（当前行为）

---

## 3. 非功能需求

### 3.1 性能
- 详细模式的字符串拼接开销 < 2ms（无需网络/磁盘 I/O）
- 翻译文件在插件注册时**预加载到内存**，不在每轮读磁盘

### 3.2 测试
- 新增 `test_debug_detailed.py`：验证详细模式各模块输出格式
- 新增 `test_locales.py`：验证中英文翻译键完整性 + 回退逻辑
- 新增 `test_config.py`：验证 `language: "auto"` 推断逻辑

### 3.3 不影响现有行为
- 232 个已有测试必须全部通过
- `detail: "compact"` 输出必须与当前完全一致

---

## 4. 排除范围

- 不做 token 计数显示（依赖外部 API，架构侵入）
- 不做 hook 耗时分析（需要 timing wrapper）
- 不做彩色/富文本输出（平台依赖）
- 不修改 `inject_context()` 的主流程逻辑

---

## 5. 关键文件

| 文件 | 改动类型 |
|------|---------|
| `hermes_persona/injector.py` → `_debug_summary()` | 重构为 compact/detailed 双模式 |
| `hermes_persona/injector.py` → `transform_llm_output()` | 无改动 |
| `hermes_persona/injector.py` → 新增 `_detailed_summary()` | 新函数 |
| `hermes_persona/locales/zh.json` | 新建 |
| `hermes_persona/locales/en.json` | 新建 |
| `hermes_persona/locales/__init__.py` | 新建（加载器） |
| `examples/persona-config.json` | 更新范例 |
| `tests/test_debug_detailed.py` | 新建 |
| `tests/test_locales.py` | 新建 |

---

## 6. 英文示例 (Detailed Mode Output)

```
🔧 [Debug] Turn Summary:
  ① 🕐 Time injected
  ② 📜 8 static rules
  ③ ⚡ time_slots: on / turn_stage: off / keyword: on
  ④a 📏⏱️ Fixed Signals (3/3 triggered)
    📏 message_length: len=3 < threshold=50 → triggered
    🎵 reply_gap: idle (gap=0.5min, threshold=30min)
    📊 daily_turn_count: 42 → triggered (today: 2026-05-19)
  ④b 📊 Expression Vector | turn 174
    care: 2→3 (+1)  ← hit: "dinner"(1)
    intimacy: 3 (none)
    work: 5 (none)
  ④ 🎲 Variance (2/3 rolled)
    ✓ fox_girl_body_language (p=0.6): "🦊 Ears and tail swayed in unison"
    ✗ maid_body_language (p=0.6): not rolled
    ✗ metaphor_of_the_day (p=0.3): not rolled
  ⑤ 🧠 Memory: stopped
  ⑥ 📋 Kanban: no data
```
