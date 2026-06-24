# 天气数据可靠性修复 实施计划

> **For agentic workers:** 使用 superpowers:subagent-driven-development 或 superpowers:executing-plans 来实施此计划。步骤使用 checkbox (`- [ ]`) 语法追踪。

**Goal:** 修复天气模块四类数据可靠性缺陷——雷暴码误报标记、字段缺失静默零值、debug 摘要时序误报、null 值穿透

**Architecture:** 在 `weather.py` 新增 `_validate_weather` 校验层 + `_fetch_weather` 字段完整性检查 + 格式化可疑标记 + debug 状态采集；`injector.py` 改为读取模块级 debug 状态

**Tech Stack:** Python 3.10+, pytest

**Spec:** `docs/superpowers/specs/2026-06-23-fix-weather-data-reliability.md`

---

## 文件结构

| 文件 | 角色 | 改动 |
|------|------|------|
| `weather.py` | 天气核心 | 新增 `_validate_weather`、`_get_debug_state`；改 `_fetch_weather`、`_get_weather_data`、两个格式化函数 |
| `injector.py` | 集成层 | debug 摘要改为读 `_get_debug_state()`，删除事后重读缓存逻辑 |
| `tests/test_weather.py` | 单元测试 | 新增校验/字段/格式化/debug 状态测试 |
| `persona-config.json` | 仓库模板 | `weather` 节新增 `validation` 子节 |

---

## Chunk 1: weather.py 核心修复

### Task 1.1: `_validate_weather` 纯函数 + 常量（P0）

**Files:** `weather.py`, `tests/test_weather.py`

- [x] 新增 `_THUNDERSTORM_CODES = (95, 96, 99)` 和 `_MIN_THUNDERSTORM_WIND_KMH = 12` 常量
- [x] 实现 `_validate_weather(data, validation_cfg) -> bool`：雷暴+低风力 / code 无效 / temp None 三条规则
- [x] 测试：雷暴低风力→True，雷暴正常风力→False，检查禁用→False，code None→True，code 越界→True，temp None→True，正常→False

### Task 1.2: `_fetch_weather` 字段完整性校验（P1 + P2）

**Files:** `weather.py`, `tests/test_weather.py`

- [x] 移除 `.get(key, 0)` 零值默认，改为 `required` 列表前置完整性检查
- [x] 任一字段缺失或 None → `return None`（触发 `_get_weather_data` 缓存回退）
- [x] 测试：字段完整→dict，weather_code 缺失→None，weather_code=null→None，temperature 缺失→None

### Task 1.3: 格式化函数追加可疑标记（P0）

**Files:** `weather.py`, `tests/test_weather.py`

- [x] `_format_weather`：从 `data.get("suspicious", False)` 读取，True 时追加「（天气数据可能不准确）」
- [x] `_format_weather_narrative`：同上，转译格式
- [x] 更新现有格式化测试数据，追加 `suspicious` 字段
- [x] 新增测试：正常 brief/full、可疑 brief/full、narrative 四种

### Task 1.4: `_get_weather_data` 集成校验 + debug 状态（P0 + P2）

**Files:** `weather.py`, `tests/test_weather.py`

- [x] 新增模块级 `_LAST_DEBUG_STATE: dict[str, str] = {}` 和 `_get_debug_state() -> dict`
- [x] API 成功后：`full_data["suspicious"] = _validate_weather(weather, config.get("validation"))`
- [x] 缓存命中路径：旧缓存无 suspicious 字段时补校验
- [x] 在三个分支（缓存有效 / API 成功 / API 失败回退）记录 `_LAST_DEBUG_STATE`
- [x] 测试：debug 状态准确性（三种场景）

---

## Chunk 2: injector.py debug 修复

### Task 2.1: debug 摘要改用 `_get_debug_state`（P2）

**Files:** `injector.py`, `tests/test_injector.py`

- [x] [injector.py:1422](../../injector.py:1422) 处：删除 `_read_cache` + `_should_refresh` 重读逻辑
- [x] 改为 `from weather import _get_debug_state; weather_debug = _get_debug_state(); weather_debug["injected"] = "true"`
- [x] 测试：debug 摘要天气状态准确性（mock `_get_debug_state`）

---

## Chunk 3: 配置 + 回归

### Task 3.1: persona-config.json 模板（仓库）

**Files:** `persona-config.json`

- [x] `weather` 节新增 `"validation": {"thunderstorm_wind_check": true}`

### Task 3.2: 回归测试

- [x] `python -m pytest tests/ -v` 全部通过
- [x] 现有 70 个 weather 测试无回归（格式化签名用默认值兼容）
