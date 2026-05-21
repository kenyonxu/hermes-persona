# Changelog

All notable changes to hermes-persona will be documented in this file.

## [Unreleased] — feature/001-module-switch

### Added

#### US-002: Expression Vector + FuzzyUtility Layer (`@546cd0e`)
- **Expression vector engine** (`hermes_persona/expression_vector.py`): multi-dimensional keyword-matching system with per-dimension score-rules (hit-score, miss-penalty, weight), automatic decay, and disk persistence.
- **Six configurable dimensions** in default persona-config: `intimacy` (50 keywords, ×3), `care` (44 keywords, ×2), `work` (50 keywords, ×1), `play` (33 keywords, ×1), `eros` (44 keywords, ×5), and `future` (17 keywords, ×1).
- **FuzzyUtility injection**: each turn, the expression vector scores are injected as `📊 [表达向量] <dim>:<score> ...` into the system prompt, enabling the LLM to modulate its tone naturally based on conversation topic distribution.
- **Session persistence**: vector state survives gateway restarts; policy-based reset (`session` / `daily` / `none`).

#### Fixed Signals (US-002 ④a)
- **`message_length`**: short user messages (< threshold chars) trigger `📏 消息较短`.
- **`reply_gap`**: long intervals (> threshold minutes) trigger `🎵 欢迎回来`.
- **`daily_turn_count`**: cross-session daily turn counter with date-aware auto-reset; thresholds at 10 ("morning") and 50 ("deep companionship day").

#### Debug: Reliable Post-Injection via `transform_llm_output`
- **New hook**: registered `transform_llm_output` in the plugin. When `debug.visible=true`, the debug summary is stored in a module-level variable during `pre_llm_call` and appended to the LLM's response via `transform_llm_output` — **no LLM compliance required**. Eliminates the previous unreliable "ask LLM to echo" approach.
- **Dual-path design**: when `visible=false`, debug summary is still injected into system prompt as an internal memo (LLM reference only).

#### Persona-Config Enhancements (2026-05-19)
- **Body language channels**: replaced single-purpose variance categories with `fox_girl_body_language` (狐娘本能) and `maid_body_language` (女仆礼仪, 5 flavor tones: professional / close / gentle / elegant / erotic).
- **Expression vector keywords**: all five dimensions expanded from ~12 to 43–50 keywords each.
- **`future` dimension** added: 17 keywords for vision/aspiration detection.
- **Static rules updated**: body language instructions now require "狐娘本能 + 女仆礼仪, 各占其一或择一而用".
- **Care keywords**: added `回来` for return-detection.

### Fixed

- **Debug `④a` false negative**: fixed signal detection now also checks for `📊` prefix (daily_turn_count), excluding expression vector lines.
- **Debug `④` variance always showing "无注入"**: replaced heuristic detection with explicit `var_count` tracking from `inject_context`.
- **Plugin code sync: nested directory trap**: plugin's Python import path is `hermes_persona/hermes_persona/` (nested)—code updates must target the inner directory. All three deployment paths (git repo, profile plugins, profile sandbox) now correctly synced.

### Test Status
- **232/232 tests passing** (0.18s): 31 expression vector + 9 fixed signals + 9 integration + 183 baseline.

---

#### SPEC-008: JSON File Location Reorganization
- **Unified file layout**: all user-editable JSON configs and runtime state files consolidated under `plugins/hermes-persona/` — `persona-config.json`, `keywords/` (7 JSONs), `locales/` (en/zh), `state/` (expression_vector, daily_turn_count), `examples/`.
- **Three-layer fallback in `config.py`**: `_resolve_config_path()` resolves config path via plugin dir → `_CONFIG_ROOT` (legacy profile root) → caller fallback (repo root). `injector.py` and `guard.py` unified to use this single function.
- **State file default path migration**: `expression_vector.json` default from `~/.hermes/` to `state/`; `daily_turn_count.json` default from `~/.hermes/profiles/{profile}/state/` to `state/`.
- **Legacy state file fallback**: if new path has no state file but old default path does, read from old path and migrate to new path on first `save()`.
- **`.gitignore`**: added `state/` to prevent runtime-generated files from being committed.
- **Test coverage**: 13 new path-resolution tests (`test_config_paths.py`), total 346 passed.

---

#### US-001: Module Switch (completed prior)
- **Module registry** (`_MODULE_REGISTRY`): declarative control for 7 modules (time, static_rules, dynamic, variance, memory, kanban, debug).
- **Sub-channel control**: `dynamic.time_slots`, `dynamic.turn_stage`, `dynamic.keyword` independently switchable.
- **Backward compatibility**: legacy `time.enabled`, `memory.enabled`, `project.enabled` still work.
- **Debug mode**: `debug.enabled` + `debug.visible` flags with human-readable injection summary.
- **49 TDD tests** (module switch) + 131 pre-existing tests.

---

# 变更日志

所有 hermes-persona 的重要变更记录在此。

## [Unreleased] — feature/001-module-switch

### 新增

#### US-002: 表达向量 + FuzzyUtility 层 (`@546cd0e`)
- **表达向量引擎** (`hermes_persona/expression_vector.py`)：多维度关键词匹配系统，每维度独立 score-rules（命中分、未中扣分、权重），自动衰减，磁盘持久化。
- **六个可配置维度**：`intimacy` 亲密（50 关键词 ×3）、`care` 关怀（44 关键词 ×2）、`work` 工作（50 关键词 ×1）、`play` 轻松（33 关键词 ×1）、`eros` 情欲（44 关键词 ×5）、`future` 展望（17 关键词 ×1）。
- **FuzzyUtility 注入**：每轮将表达向量分数以 `📊 [表达向量] <维度>:<分数> ...` 格式注入系统提示，LLM 根据话题分布自然调节语气。
- **会话持久化**：向量状态跨 Gateway 重启保留；策略式重置（session / daily / none）。

#### 固定信号（US-002 ④a）
- **`message_length`**：短消息（< 阈值字数）触发 `📏 消息较短`。
- **`reply_gap`**：长间隔（> 阈值分钟数）触发 `🎵 欢迎回来`。
- **`daily_turn_count`**：跨会话每日轮数累积，日期跨越自动归零；阈值 10（"早晨"）和 50（"深度陪伴日"）。

#### Debug: 通过 `transform_llm_output` 实现可靠注入
- **新 hook**：注册 `transform_llm_output`。当 `debug.visible=true` 时，debug 摘要在 `pre_llm_call` 阶段存入模块变量，由 `transform_llm_output` 拼接到 LLM 回复末尾——**无需 LLM 自觉配合**。彻底消除之前"要求 LLM 原样 echo"的不可靠方案。
- **双路径设计**：`visible=false` 时，debug 摘要仍然注入系统提示作为内部备忘（仅供 LLM 参考）。

#### 人格配置增强（2026-05-19）
- **肢体语言通道**：用 `fox_girl_body_language`（狐娘本能）和 `maid_body_language`（女仆礼仪，五档风味：职业/亲近/温柔/优雅/色气）替代原来的单一 variance 分类。
- **表达向量关键词**：全部维度从 ~12 个关键词扩充至 43–50 个。
- **新增 `future` 维度**：17 个关键词用于愿景/展望检测。
- **静态规则更新**：肢体语言指令改为「狐娘本能 + 女仆礼仪，各占其一或择一而用」。
- **care 关键词**：添加「回来」用于归家检测。

### 修复

- **Debug `④a` 漏报**：固定信号检测现在也检查 `📊` 前缀（daily_turn_count），排除表达向量行。
- **Debug `④` variance 始终显示「无注入」**：用显式的 `var_count` 追踪替代启发式检测。
- **插件代码同步：嵌套目录陷阱**：插件的 Python import 路径为 `hermes_persona/hermes_persona/`（嵌套）——代码更新须针对内层目录。三个部署路径（git repo、profile plugins、profile sandbox）现已正确同步。

### 测试状态
- **232/232 测试通过**（0.18s）：31 表达向量 + 9 固定信号 + 9 集成 + 183 基线。

---

#### SPEC-008: JSON 文件位置整顿
- **统一文件布局**：所有用户可编辑的 JSON 配置和运行时状态文件统一到 `plugins/hermes-persona/` 下——`persona-config.json`、`keywords/`（7 个 JSON）、`locales/`（en/zh）、`state/`（expression_vector、daily_turn_count）、`examples/`。
- **三层 fallback**：`config.py` 新增 `_resolve_config_path()` 公共函数，按插件目录 → `_CONFIG_ROOT`（旧 profile 根目录）→ 调用方自行处理（repo 根目录）顺序解析配置路径。`injector.py` 和 `guard.py` 统一调用此函数。
- **状态文件默认路径迁移**：`expression_vector.json` 默认路径从 `~/.hermes/` 迁移到 `state/`；`daily_turn_count.json` 默认路径从 `~/.hermes/profiles/{profile}/state/` 迁移到 `state/`。
- **旧状态文件 fallback**：新路径不存在但旧默认路径存在时，读取旧路径数据，在首次 `save()` 时写入新路径实现自然迁移。
- **`.gitignore`**：追加 `state/`，防止运行时生成文件被提交。
- **测试覆盖**：13 个新增路径解析测试（`test_config_paths.py`），全量 346 passed。

---

#### US-001: 模块总控开关（先前已完成）
- **模块注册表** (`_MODULE_REGISTRY`)：7 个模块（time、static_rules、dynamic、variance、memory、kanban、debug）的声明式控制。
- **子通道控制**：`dynamic.time_slots`、`dynamic.turn_stage`、`dynamic.keyword` 独立开关。
- **向后兼容**：旧版 `time.enabled`、`memory.enabled`、`project.enabled` 仍然有效。
- **Debug 模式**：`debug.enabled` + `debug.visible` 标志，人类可读的注入摘要。
- **49 个 TDD 测试**（模块开关）+ 131 个已有测试。
