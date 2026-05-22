<h3 align="center">
  <a href="CHANGELOG.md">简体中文</a> · <a href="CHANGELOG_EN.md">English</a>
</h3>
<p align="center">— ✦ —</p>

# Changelog

## [1.0.0] — 2026-05-22

> First stable release. From modular engine to injection narrative translation, hermes-persona is production-ready.

### Added

- **Module Switch**: All injection modules can be toggled independently, including sub-channels of dynamic rules (time-slots / turn-stage / keyword). Legacy config keys are backward-compatible.
- **Time Awareness Injection**: Auto-detects time of day (early morning / morning / noon / afternoon / evening / night / late night, etc.) and injects corresponding behavioral cues.
- **Static Rules Injection**: User-defined behavioral rules with two channels — every-turn injection and first-turn-only injection.
- **Dynamic Rules System**: Time-slot auto-matching, turn-stage adaptation, keyword-triggered scene switching — all driven by user-defined rules.
- **Multi-Dimensional Expression Vector**: Users can define arbitrary keyword scoring dimensions. Scores track and decay per turn, guiding the LLM to naturally adjust expression style.
- **Fixed Signal Detection**: Message length awareness (short message → concise response), reply gap detection (long absence → welcome-back tone), daily turn accumulation (cross-session, auto-reset daily, configurable thresholds).
- **Random Expression Variance**: User-defined trigger probability and variant entries — ideal for defining character-specific body language, catchphrases, metaphorical styles, verbal tics, etc.
- **Injection Narrative Translation**: Internal rules are automatically translated into natural-language persona narration — template-assembled (time + turn count + state + variance + rules). The LLM sees flowing character self-description rather than instruction checklists.
- **Sources Filter**: Non-conversational sources (cron / API / webhook) receive time-only injection, skip turn counting, and do not trigger dynamic rules.
- **Debug Detailed Mode**: Full injection visualization — time slot, turn stage, expression vector scores, fixed signal triggers, variance hits. Appended to LLM output via `transform_llm_output` hook — no LLM self-reporting needed.
- **i18n**: Bilingual strings (zh / en) supported; extensible to more languages via locale files.
- **Safety Guardrails**: Dangerous operation blocking + sensitive operation confirmation with audit logging.
- **Project Kanban Injection**: External kanban status injected on the first turn, giving the LLM project context.

### Improved

- Variance entries support "direct text" — entries are self-contained complete sentences; the engine only does prefix-stripping pass-through without locking a fixed sentence pattern. Authors iterate content without code changes.
- Turn stage now uses daily accumulated turn count (cross-session) instead of per-session count — more accurately reflects daily interaction depth.
- Directory structure flattened — JSON config, keyword vocabularies, locale files, and runtime state are all consolidated under the plugin directory.
- Config/code separation: dead code removed, rule management fully delegated to the config layer.

### Fixed

- Day-of-week display format corrected.
- State file default path fallback — empty string no longer overrides the default.
- State file smooth migration from legacy path to new path.
- Fixed signal debug false-positive fix (prefix compatibility).
- Plugin code deployment path unified and synced.
