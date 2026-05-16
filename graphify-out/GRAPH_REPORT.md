# Graph Report - hermes-persona  (2026-05-16)

## Corpus Check
- 20 files · ~15,618 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 600 nodes · 655 edges · 43 communities (23 shown, 20 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 81 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2b3d654b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]

## God Nodes (most connected - your core abstractions)
1. `inject_context()` - 21 edges
2. `_randomize_variance()` - 16 edges
3. `TestRandomizeVariance` - 14 edges
4. `三、各角色简要设定摘要` - 14 edges
5. `阿格莱雅（Aglaea）—— 原始素材收集` - 14 edges
6. `_match_keyword()` - 12 edges
7. `TestMatchKeyword` - 11 edges
8. `_recall_memories()` - 11 edges
9. `_in_time_range()` - 11 edges
10. `_match_turn_stage()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `test_normal_slot_match()` --calls--> `_match_time_slot()`  [INFERRED]
  tests/test_dynamic_rules.py → hermes_persona/dynamic_rules.py
- `test_cross_midnight_match_at_night()` --calls--> `_match_time_slot()`  [INFERRED]
  tests/test_dynamic_rules.py → hermes_persona/dynamic_rules.py
- `test_cross_midnight_match_at_edge()` --calls--> `_match_time_slot()`  [INFERRED]
  tests/test_dynamic_rules.py → hermes_persona/dynamic_rules.py
- `test_no_match()` --calls--> `_match_time_slot()`  [INFERRED]
  tests/test_dynamic_rules.py → hermes_persona/dynamic_rules.py
- `test_selects_time_slot_and_turn_stage()` --calls--> `_select_dynamic_rules()`  [INFERRED]
  tests/test_dynamic_rules.py → hermes_persona/dynamic_rules.py

## Communities (43 total, 20 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (37): inject_context(), _inject_static_rules(), Persona context injector: config loading, time generation, rule assembly.  Core, P3 stub. Read project kanban status from the filesystem.      Currently returns, Assemble and return the full persona context for this turn.      Called by the H, Generate a time-description string for the current moment.      Supported format, Extract static rules from context configuration.      - context.rules: injected, _read_kanban() (+29 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (29): _match_keyword(), _match_time_slot(), Dynamic rule selection: time slots, turn stages, and keyword matching.  P1 imple, Match user message against keyword regex patterns.      Args:         keywords:, Select dynamic rules by time / turn-stage / keyword dimensions.      Injection o, Match current time against configured time slots.      time_slots: {"22:00-05:00, _select_dynamic_rules(), P1 tests for hermes_persona.dynamic_rules — time slots, turn stages, in-time-ran (+21 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (42): 1.1 产品定位, 1.2 核心设计原则, 1.3 适用场景, 2.1 整体架构图, 2.2 数据流, 2.3 目录结构, 2.4 Profile 目录结构 (用户侧), 4.1 完整 `persona-config.json` Schema (+34 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (39): 3.0 主线：审判/考验, 3.0 主线：浴场对话, 一、基础资料, 七、人际关系（摘录）, 三、背景故事（时间线）, 与万敌（Mydei）, 与开拓者（Trailblazer）, 与开拓者的交集（3.0 主线） (+31 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (37): code:block1 (P1-T1 (plugin.yaml)), code:python (# injector.py 模块级变量), code:block21 (第1轮: P1-T1, P1-T4, P1-T5  (无依赖，可并行)), code:block3 (时间 → 静态规则 → 首轮规则 → 时段规则 → 轮数规则 → 关键词规则 → 随机变化 → 记忆召回 → 看板), code:block4 (if start <= end:   start <= now < end), D1: 配置文件定位策略, D2: 规则注入顺序 (不可变), D3: 配置降级策略 (+29 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (36): 2.1 时间维度 `time_slots`, 2.2 轮数维度 `turn_stage`, 2.3 关键词维度 `keyword`, 2.4 扩展维度（Phase 2+）, 3.1 与静态规则的优先级, 4.1 主调度器, 4.2 动态规则选择器, 5.1 为什么需要随机性 (+28 more)

### Community 6 - "Community 6"
Cohesion: 0.06
Nodes (32): 3.1 身份层级, 3.2 性格关键词, 3.3 在外观, 5.1 方法论演示：阿格莱雅（Aglaea）, 5.2 映射前后对比, 5.3.1 第四步详解：分层收敛, 5.3 通用方法论模板, 5.4 两翼：Prompt Engineering × Harness Engineering (+24 more)

### Community 7 - "Community 7"
Cohesion: 0.06
Nodes (30): 3.0 版本, 3.1 版本, 3.2 版本, 3.3 版本, 3.5 版本, 3.7 版本, 一、基础信息面板, 七、关键性格矩阵 (+22 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (17): _randomize_variance(), Select random expression variants from each configured category.      Args:, P2 tests for hermes_persona.variance — two-layer randomization., random.choice picks from the given variants., Each selected variant is converted to str., Empty variance config returns []., Non-dict category values are skipped., probability=0 means the category is never selected. (+9 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (28): code:python (def _match_time_slot(time_slots: dict) -> list[str]:), code:python (def _in_time_range(now: str, start: str, end: str) -> bool:), code:python (def _match_turn_stage(turn_stages: dict, is_first_turn: bool), code:python (def _randomize_variance(variance_cfg: dict) -> list[str]:), code:python (def check_tool_call(tool_name, tool_args, **kwargs):), code:yaml (name: hermes-persona), code:python (def _load_config() -> dict:), code:python (def _time_context(fmt: str = "cn_full") -> str:) (+20 more)

### Community 10 - "Community 10"
Cohesion: 0.07
Nodes (28): 01 缇宝（Tribios）—— 命运的三子, 02 刻律德菈（Cerydra）—— 执棋的君主, 03 Terravox —— 震地之龙, 04 海瑟音（Helektra）—— 抚浪的骑士, 05 风堇（Hyacinthia）—— 光之愈者, 06 白厄（Phainon / Khaslana）—— 无名英雄, 07 那刻夏（Anaxagoras / Anaxa）—— 殁世的学士, 08 阿格莱雅（Aglaea）—— 金织 (+20 more)

### Community 11 - "Community 11"
Cohesion: 0.09
Nodes (22): 2.1 通用配置结构, 2.2 配置项说明, 4.1 最小配置（开箱即用）, 4.2 知惠完整配置 🦊, 4.3 通用用户配置（无记忆后端）, 5.1 plugin.yaml, code:block1 (┌──────────────────────────────────────────┐), code:json ({) (+14 more)

### Community 12 - "Community 12"
Cohesion: 0.11
Nodes (16): _load_config(), Load persona-config.json and return the "hermes-persona" sub-tree.      Returns, inject_context_defaults(), mock_load_config_empty(), Shared test fixtures for hermes_persona tests., Create a temporary directory and point _CONFIG_ROOT at it., Write persona-config.json into the temp config root., Patch _load_config to always return {}. (+8 more)

### Community 13 - "Community 13"
Cohesion: 0.15
Nodes (11): _in_time_range(), Check if now (HH:MM) falls within [start, end).      Supports cross-midnight: st, 10:00 is inside [09:00, 17:00)., 09:00 is inside [09:00, 17:00) — inclusive lower bound., 17:00 is NOT inside [09:00, 17:00) — exclusive upper bound., 18:00 is outside [09:00, 17:00)., 02:00 is inside [22:00, 05:00) — cross-midnight., 23:30 is inside [22:00, 05:00) — cross-midnight. (+3 more)

### Community 14 - "Community 14"
Cohesion: 0.15
Nodes (11): Recall relevant memories from an external memory API.      Args:         user_me, _recall_memories(), memory.enabled=false → returns None., enabled=True but no api_url → returns None., memory.enabled=true + valid api_url → injects memory content., Results longer than 120 chars are truncated., Non-200 status code → returns None., Empty results list → returns None. (+3 more)

### Community 15 - "Community 15"
Cohesion: 0.15
Nodes (11): _match_turn_stage(), Match turn-based rules against the current conversation stage.      turn_stages:, first_turn rules are injected when is_first_turn=True., first_turn rules are NOT injected when is_first_turn=False., At turn_count=35, after_30 matches, not after_10., At turn_count=12, after_10 matches., At turn_count=10, after_10 matches (turn_count >= threshold)., At turn_count=5 with only after_10, nothing matches. (+3 more)

### Community 16 - "Community 16"
Cohesion: 0.11
Nodes (18): code:block1 (amphoreus-personas/), code:json ({), hermes-persona — Agent 人格化方法论与插件工程, License, 一、Persona 提取四步法, 三、角色分类与 Agent 特性映射, 世界观核心设定（翁法罗斯）, 二、Persona 配置要素 (+10 more)

### Community 17 - "Community 17"
Cohesion: 0.11
Nodes (16): 3.1 plugin.yaml, 3.2 `__init__.py` — 插件入口, 3.3.1 主入口 `inject_context()`, 3.3.2 内部函数一览, 3.3 `injector.py` — 上下文注入引擎, 3.4.1 接口定义, 3.4.2 子函数, 3.4 `dynamic_rules.py` — 动态规则选择器 (+8 more)

### Community 18 - "Community 18"
Cohesion: 0.14
Nodes (13): code:block1 (amphoreus-personas/), hermes-agent-guide, License, 免责声明, 数据来源, 目录结构, 项目简介, code:bash (# 1. 安装插件) (+5 more)

### Community 19 - "Community 19"
Cohesion: 0.18
Nodes (11): code:python (def _load_guard_config() -> dict:), code:json ("guard": {), code:python (def check_tool_call(tool_name: str, tool_args: dict, **kwarg), code:python (def audit_tool_call(tool_name: str, tool_args: dict, result:), code:python (ctx.register_hook("pre_tool_call", guard.check_tool_call)), P4-T1: 实现 guard.py 完整逻辑, P4-T1a: `_load_guard_config()` (~20 行), P4-T1b: `check_tool_call()` (~50 行) (+3 more)

### Community 20 - "Community 20"
Cohesion: 0.33
Nodes (5): audit_tool_call(), check_tool_call(), Safety guard and audit — P4 stubs.  P4 will implement:   - check_tool_call: pre_, P4 implementation. Currently returns None (allow all)., P4 implementation. Currently a no-op.

### Community 21 - "Community 21"
Cohesion: 0.67
Nodes (3): hermes-persona: Dynamic persona context injection engine for Hermes Agent.  Usag, Register the hermes-persona plugin with the Hermes runtime.      - Stores the pr, register()

## Knowledge Gaps
- **335 isolated node(s):** `P1 tests for hermes_persona.dynamic_rules — time slots, turn stages, in-time-ran`, `10:00 is inside [09:00, 17:00).`, `09:00 is inside [09:00, 17:00) — inclusive lower bound.`, `17:00 is NOT inside [09:00, 17:00) — exclusive upper bound.`, `18:00 is outside [09:00, 17:00).` (+330 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `inject_context()` connect `Community 0` to `Community 8`, `Community 1`, `Community 12`, `Community 14`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Why does `_select_dynamic_rules()` connect `Community 1` to `Community 0`, `Community 15`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Why does `_randomize_variance()` connect `Community 8` to `Community 0`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Are the 12 inferred relationships involving `inject_context()` (e.g. with `test_empty_config_returns_time_context()` and `test_time_disabled()`) actually correct?**
  _`inject_context()` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `_randomize_variance()` (e.g. with `.test_empty_config_returns_empty()` and `.test_probability_zero_never_appears()`) actually correct?**
  _`_randomize_variance()` has 13 INFERRED edges - model-reasoned connections that need verification._
- **What connects `P1 tests for hermes_persona.dynamic_rules — time slots, turn stages, in-time-ran`, `10:00 is inside [09:00, 17:00).`, `09:00 is inside [09:00, 17:00) — inclusive lower bound.` to the rest of the system?**
  _335 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.06 - nodes in this community are weakly interconnected._