# 天气上下文注入模块 实施计划

> **For agentic workers:** 使用 superpowers:subagent-driven-development 或 superpowers:executing-plans 来实施此计划。步骤使用 checkbox (`- [ ]`) 语法追踪。

**Goal:** 在 hermes-persona 中新增独立 weather 模块，通过 Open-Meteo API 获取天气并注入到每轮 LLM 上下文

**Architecture:** 新建 `weather.py` 独立模块（遵循 variance.py 模式），通过文件缓存减少 API 调用，`_should_refresh()` 作为统一决策点。修改 `injector.py` 集成调用，支持直接注入和 translate 转译两种模式。

**Tech Stack:** Python 3.10+, urllib (标准库), Open-Meteo API (免费无需 Key), pytest

**Spec:** `docs/superpowers/specs/2026-06-05-weather-module-design.md`

---

## 文件结构

| 文件 | 角色 |
|------|------|
| `weather.py` | 天气模块核心：API 调用、缓存读写、格式化、决策逻辑 |
| `injector.py` | 集成层：导入、注册、调用、debug 摘要、narrative 拼装 |
| `persona-config.json` | 仓库模板：新增 `modules.weather` + `weather` 配置节 |
| `tests/test_weather.py` | 天气模块单元测试（纯函数 + mock） |
| `tests/test_injector.py` | 集成测试：注入链、translate、debug |

**不修改**：`__init__.py`、`config.py`、`guard.py`、`locales/`

---

## Chunk 1: weather.py 核心模块

### Task 1.1: 纯函数 — WMO 码映射 + 风力转换 + 缓存读写 + 决策

**Files:**
- Create: `weather.py`
- Create: `tests/test_weather.py`

- [ ] **Step 1: 编写测试 — 全部纯函数**

创建 `tests/test_weather.py`：

```python
"""Tests for weather.py — pure functions and mocked integration."""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from weather import (
    _weather_code_to_cn,
    _wind_speed_to_beaufort,
    _format_weather,
    _format_weather_narrative,
    _should_refresh,
    _read_cache,
    _write_cache,
)


# ── _weather_code_to_cn ────────────────────────────────────────────────

class TestWeatherCodeToCn:
    def test_clear_sky(self):
        assert _weather_code_to_cn(0) == ("晴", "☀️")

    def test_cloudy(self):
        for code in (1, 2, 3):
            assert _weather_code_to_cn(code) == ("多云", "⛅")

    def test_fog(self):
        for code in (45, 48):
            assert _weather_code_to_cn(code) == ("雾", "🌫")

    def test_drizzle(self):
        for code in (51, 53, 55):
            assert _weather_code_to_cn(code) == ("毛毛雨", "🌧")

    def test_freezing_drizzle(self):
        for code in (56, 57):
            assert _weather_code_to_cn(code) == ("冻毛毛雨", "🌧")

    def test_rain(self):
        for code in (61, 63, 65):
            assert _weather_code_to_cn(code) == ("雨", "🌧")

    def test_freezing_rain(self):
        for code in (66, 67):
            assert _weather_code_to_cn(code) == ("冻雨", "🌧")

    def test_snow(self):
        for code in (71, 73, 75):
            assert _weather_code_to_cn(code) == ("雪", "🌨")

    def test_snow_grains(self):
        assert _weather_code_to_cn(77) == ("雪粒", "🌨")

    def test_rain_showers(self):
        for code in (80, 81, 82):
            assert _weather_code_to_cn(code) == ("阵雨", "🌦")

    def test_snow_showers(self):
        for code in (85, 86):
            assert _weather_code_to_cn(code) == ("阵雪", "🌨")

    def test_thunderstorm(self):
        for code in (95, 96, 99):
            assert _weather_code_to_cn(code) == ("雷暴", "⛈")

    def test_unknown_code_fallback(self):
        assert _weather_code_to_cn(999) == ("未知", "🌡")
        assert _weather_code_to_cn(-1) == ("未知", "🌡")


# ── _wind_speed_to_beaufort ────────────────────────────────────────────

class TestWindSpeedToBeaufort:
    @pytest.mark.parametrize("kmh,expected", [
        (0, 0), (0.5, 0), (1, 1), (5, 1),
        (6, 2), (11, 2), (12, 3), (19, 3),
        (20, 4), (28, 4), (29, 5), (38, 5),
        (39, 6), (49, 6), (50, 7), (61, 7),
        (62, 8), (74, 8), (75, 9), (88, 9),
        (89, 10), (102, 10), (103, 11), (117, 11),
        (118, 12), (200, 12),
    ])
    def test_beaufort_conversion(self, kmh, expected):
        assert _wind_speed_to_beaufort(kmh) == expected


# ── _format_weather ─────────────────────────────────────────────────────

class TestFormatWeather:
    def test_brief_mode(self):
        data = {"weather_code": 0, "temperature": 26.3, "humidity": 45,
                "wind_speed": 20.0, "location": "北京"}
        result = _format_weather(data, "brief", "🌤")
        assert result == "🌤 北京 晴 26°C"

    def test_full_mode(self):
        data = {"weather_code": 61, "temperature": 18.0, "humidity": 80,
                "wind_speed": 30.0, "location": "上海"}
        # 61 → 雨, 30 km/h → Beaufort 5
        result = _format_weather(data, "full", "🌤")
        assert result == "🌤 上海 雨 18°C 湿度80% 风力5级"

    def test_unknown_detail_falls_back_to_brief(self):
        data = {"weather_code": 0, "temperature": 20.0, "humidity": 50,
                "wind_speed": 5.0, "location": "test"}
        result = _format_weather(data, "invalid", "🌤")
        assert "湿度" not in result


# ── _format_weather_narrative ──────────────────────────────────────────

class TestFormatWeatherNarrative:
    def test_brief_narrative(self):
        data = {"weather_code": 0, "temperature": 26.3, "humidity": 45,
                "wind_speed": 20.0}
        result = _format_weather_narrative(data, "brief")
        assert result == "晴，26°C"

    def test_full_narrative(self):
        data = {"weather_code": 61, "temperature": 18.0, "humidity": 80,
                "wind_speed": 30.0}
        # 61 → 雨, 30 km/h → Beaufort 5
        result = _format_weather_narrative(data, "full")
        assert result == "雨，18°C，湿度80%，风力5级"


# ── _should_refresh ────────────────────────────────────────────────────

class TestShouldRefresh:
    def test_no_cache_returns_true(self):
        assert _should_refresh(None, {"cache_ttl_minutes": 30}, "北京") is True

    def test_empty_cache_returns_true(self):
        assert _should_refresh({}, {"cache_ttl_minutes": 30}, "北京") is True

    def test_expired_cache_returns_true(self):
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        cache = {"location": "北京", "fetched_at": old_time}
        assert _should_refresh(cache, {"cache_ttl_minutes": 30}, "北京") is True

    def test_valid_cache_returns_false(self):
        recent = datetime.now(timezone.utc).isoformat()
        cache = {"location": "北京", "fetched_at": recent}
        assert _should_refresh(cache, {"cache_ttl_minutes": 30}, "北京") is False

    def test_location_changed_returns_true(self):
        recent = datetime.now(timezone.utc).isoformat()
        cache = {"location": "北京", "fetched_at": recent}
        assert _should_refresh(cache, {"cache_ttl_minutes": 30}, "上海") is True

    def test_default_ttl_when_not_configured(self):
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        cache = {"location": "北京", "fetched_at": old_time}
        assert _should_refresh(cache, {}, "北京") is False

    def test_corrupt_fetched_at_returns_true(self):
        """损坏的 fetched_at 应触发刷新（fail-open）。"""
        cache = {"location": "北京", "fetched_at": "not-a-date"}
        assert _should_refresh(cache, {"cache_ttl_minutes": 30}, "北京") is True


# ── _read_cache / _write_cache ─────────────────────────────────────────

class TestCacheReadWrite:
    def test_write_and_read_roundtrip(self):
        tmpdir = tempfile.mkdtemp()
        cache_path = Path(tmpdir) / "weather_cache.json"
        data = {
            "location": "北京", "latitude": 39.9, "longitude": 116.4,
            "weather_code": 0, "temperature": 26.3,
            "humidity": 45, "wind_speed": 12.5,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_cache(cache_path, data)
        result = _read_cache(cache_path)
        assert result is not None
        assert result["location"] == "北京"
        assert result["temperature"] == 26.3

    def test_read_corrupt_json_returns_none(self):
        tmpdir = tempfile.mkdtemp()
        cache_path = Path(tmpdir) / "weather_cache.json"
        cache_path.write_text("not valid json{{{", encoding="utf-8")
        assert _read_cache(cache_path) is None

    def test_read_empty_dict_file_returns_none(self):
        tmpdir = tempfile.mkdtemp()
        cache_path = Path(tmpdir) / "weather_cache.json"
        cache_path.write_text("{}", encoding="utf-8")
        assert _read_cache(cache_path) is None

    def test_read_missing_file_returns_none(self):
        assert _read_cache(Path("/nonexistent/weather_cache.json")) is None
```

- [ ] **Step 2: 运行测试验证全部失败**

```bash
python -m pytest tests/test_weather.py -v
```

预期：全部 FAIL（模块不存在）

- [ ] **Step 3: 实现 weather.py — 纯函数 + 缓存 + 格式化**

创建 `weather.py`：

```python
"""Weather context provider: Open-Meteo API + file-based cache.

Provides weather information for persona context injection.
Fail-open on any API/IO error — never blocks the injection chain.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# WMO Weather Code → (中文描述, 图标)
# ---------------------------------------------------------------------------

_WMO_CODE_MAP: dict[tuple[int, ...], tuple[str, str]] = {
    (0,): ("晴", "☀️"),
    (1, 2, 3): ("多云", "⛅"),
    (45, 48): ("雾", "🌫"),
    (51, 53, 55): ("毛毛雨", "🌧"),
    (56, 57): ("冻毛毛雨", "🌧"),
    (61, 63, 65): ("雨", "🌧"),
    (66, 67): ("冻雨", "🌧"),
    (71, 73, 75): ("雪", "🌨"),
    (77,): ("雪粒", "🌨"),
    (80, 81, 82): ("阵雨", "🌦"),
    (85, 86): ("阵雪", "🌨"),
    (95, 96, 99): ("雷暴", "⛈"),
}

_WMO_FALLBACK: tuple[str, str] = ("未知", "🌡")


def _weather_code_to_cn(code: int) -> tuple[str, str]:
    """WMO 天气码 → (中文描述, 图标)。未知码回退 ("未知", "🌡")。"""
    for codes, result in _WMO_CODE_MAP.items():
        if code in codes:
            return result
    return _WMO_FALLBACK


# ---------------------------------------------------------------------------
# Beaufort wind scale (km/h → level 0-12)
# ---------------------------------------------------------------------------

_BEAUFORT_THRESHOLDS: list[tuple[float, int]] = [
    (0, 0),
    (1, 1), (6, 2), (12, 3), (20, 4),
    (29, 5), (39, 6), (50, 7), (62, 8),
    (75, 9), (89, 10), (103, 11), (118, 12),
]


def _wind_speed_to_beaufort(kmh: float) -> int:
    """风速 km/h → Beaufort 等级（0-12）。"""
    level = 0
    for threshold, beaufort in _BEAUFORT_THRESHOLDS:
        if kmh >= threshold:
            level = beaufort
    return level


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _format_weather(data: dict, detail: str, label: str) -> str:
    """原始天气数据 → 直接注入格式字符串。

    brief: "🌤 北京 晴 26°C"
    full:  "🌤 北京 晴 26°C 湿度45% 风力3级"
    """
    cn_desc, _ = _weather_code_to_cn(data["weather_code"])
    temp = round(data["temperature"])
    loc = data.get("location", "")

    base = f"{label} {loc} {cn_desc} {temp}°C"

    if detail == "full":
        humidity = data.get("humidity", 0)
        wind_kmh = data.get("wind_speed", 0)
        beaufort = _wind_speed_to_beaufort(wind_kmh)
        return f"{base} 湿度{humidity}% 风力{beaufort}级"

    return base


def _format_weather_narrative(data: dict, detail: str) -> str:
    """原始天气数据 → 转译格式字符串（不含 emoji label，不含城市名）。

    brief: "晴，26°C"
    full:  "晴，26°C，湿度45%，风力3级"
    """
    cn_desc, _ = _weather_code_to_cn(data["weather_code"])
    temp = round(data["temperature"])

    base = f"{cn_desc}，{temp}°C"

    if detail == "full":
        humidity = data.get("humidity", 0)
        wind_kmh = data.get("wind_speed", 0)
        beaufort = _wind_speed_to_beaufort(wind_kmh)
        return f"{base}，湿度{humidity}%，风力{beaufort}级"

    return base


# ---------------------------------------------------------------------------
# File-based cache
# ---------------------------------------------------------------------------

_CACHE_DIR = Path(__file__).resolve().parent / "state"
_CACHE_FILE = _CACHE_DIR / "weather_cache.json"


def _read_cache(cache_path: Path | None = None) -> dict | None:
    """读缓存文件，解析失败或不存在返回 None。"""
    path = cache_path or _CACHE_FILE
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data:
            return data
        return None
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(cache_path: Path | None, data: dict) -> None:
    """写缓存文件，IO 失败静默忽略。"""
    path = cache_path or _CACHE_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _should_refresh(cache: dict | None, config: dict, location: str) -> bool:
    """统一决策点：是否需要调用 API 刷新天气数据。

    返回 True 的条件（任一满足）：
    - 缓存不存在（cache 为 None 或空 dict 或无 fetched_at）
    - TTL 过期（fetched_at 距今超过 cache_ttl_minutes）
    - location 变更（缓存中的 location 与当前配置不一致）
    - fetched_at 损坏（解析失败）→ fail-open 触发刷新
    """
    if not cache or not cache.get("fetched_at"):
        return True

    # location 变更（含运行时热更新场景）
    if cache.get("location") != location:
        return True

    # TTL 过期
    ttl_minutes = config.get("cache_ttl_minutes", 30)
    try:
        fetched = datetime.fromisoformat(cache["fetched_at"])
        elapsed = (datetime.now(timezone.utc) - fetched).total_seconds() / 60.0
        return elapsed >= ttl_minutes
    except (ValueError, TypeError):
        return True  # 损坏的 fetched_at → fail-open 刷新
```

- [ ] **Step 4: 运行测试验证全部通过**

```bash
python -m pytest tests/test_weather.py -v
```

- [ ] **Step 5: 提交**

```bash
git add weather.py tests/test_weather.py
git commit -m "feat(weather): 纯函数 — WMO码映射、Beaufort转换、格式化、缓存读写、_should_refresh 决策"
```

### Task 1.2: API 调用 + 数据管道 + 公开入口

**Files:**
- Modify: `weather.py`
- Modify: `tests/test_weather.py`

- [ ] **Step 1: 编写 mock 测试**

在 `tests/test_weather.py` 末尾追加：

```python
# ── _get_weather_data (mock) ───────────────────────────────────────────

from weather import _get_weather_data, _weather_context, _weather_context_for_narrative


class TestGetWeatherData:
    def test_location_empty_returns_none(self):
        assert _get_weather_data({"location": ""}) is None
        assert _get_weather_data({}) is None

    @patch("weather._read_cache")
    @patch("weather._should_refresh")
    def test_cache_valid_returns_cached_data(self, mock_refresh, mock_read):
        mock_read.return_value = {
            "location": "北京", "temperature": 26.3, "humidity": 45,
            "weather_code": 0, "wind_speed": 12.5,
        }
        mock_refresh.return_value = False
        result = _get_weather_data({"location": "北京", "cache_ttl_minutes": 30})
        assert result is not None
        assert result["temperature"] == 26.3

    @patch("weather._write_cache")
    @patch("weather._fetch_weather")
    @patch("weather._geocode")
    @patch("weather._read_cache")
    @patch("weather._should_refresh")
    def test_first_call_fetches_and_caches(self, mock_refresh, mock_read,
                                            mock_geocode, mock_fetch, mock_write):
        mock_read.return_value = None
        mock_refresh.return_value = True
        mock_geocode.return_value = (39.9, 116.4)
        mock_fetch.return_value = {
            "temperature": 26.3, "humidity": 45, "weather_code": 0, "wind_speed": 12.5,
        }
        result = _get_weather_data({"location": "北京", "cache_ttl_minutes": 30})
        assert result is not None
        assert result["temperature"] == 26.3
        mock_geocode.assert_called_once_with("北京")
        mock_fetch.assert_called_once_with(39.9, 116.4)
        mock_write.assert_called_once()

    @patch("weather._write_cache")
    @patch("weather._fetch_weather")
    @patch("weather._read_cache")
    @patch("weather._should_refresh")
    def test_geocode_cache_reused(self, mock_refresh, mock_read, mock_fetch, mock_write):
        """缓存中有坐标时跳过 geocoding 直接调天气 API。"""
        mock_read.return_value = {
            "location": "北京", "latitude": 39.9, "longitude": 116.4,
        }
        mock_refresh.return_value = True
        mock_fetch.return_value = {
            "temperature": 20.0, "humidity": 60, "weather_code": 1, "wind_speed": 5.0,
        }
        result = _get_weather_data({"location": "北京", "cache_ttl_minutes": 30})
        assert result is not None
        mock_fetch.assert_called_once_with(39.9, 116.4)

    @patch("weather._read_cache")
    @patch("weather._should_refresh")
    def test_api_fail_with_old_cache_fallback(self, mock_refresh, mock_read):
        """API 失败但有旧缓存时回退。"""
        mock_read.return_value = {
            "location": "北京", "temperature": 26.3, "humidity": 45,
            "weather_code": 0, "wind_speed": 12.5, "fetched_at": "2026-01-01T00:00:00",
        }
        mock_refresh.return_value = True
        with patch("weather._geocode", side_effect=Exception("network error")):
            result = _get_weather_data({"location": "北京", "cache_ttl_minutes": 30})
        assert result is not None
        assert result["temperature"] == 26.3

    @patch("weather._read_cache")
    @patch("weather._should_refresh")
    def test_api_fail_no_cache_returns_none(self, mock_refresh, mock_read):
        mock_read.return_value = None
        mock_refresh.return_value = True
        with patch("weather._geocode", side_effect=Exception("network error")):
            result = _get_weather_data({"location": "北京", "cache_ttl_minutes": 30})
        assert result is None

    @patch("weather._fetch_weather")
    @patch("weather._geocode")
    @patch("weather._read_cache")
    @patch("weather._should_refresh")
    def test_corrupt_cache_triggers_api(self, mock_refresh, mock_read,
                                          mock_geocode, mock_fetch):
        """缓存 JSON 损坏时视为无缓存，走 API。"""
        mock_read.return_value = None
        mock_refresh.return_value = True
        mock_geocode.return_value = (39.9, 116.4)
        mock_fetch.return_value = {
            "temperature": 20.0, "humidity": 60, "weather_code": 1, "wind_speed": 5.0,
        }
        result = _get_weather_data({"location": "北京", "cache_ttl_minutes": 30})
        assert result is not None
        mock_geocode.assert_called_once()

    @patch("weather._fetch_weather")
    @patch("weather._geocode")
    @patch("weather._read_cache")
    @patch("weather._should_refresh")
    def test_geocode_returns_none_fallback(self, mock_refresh, mock_read,
                                             mock_geocode, mock_fetch):
        """geocoding 返回 None（城市未找到）→ 回退旧缓存。"""
        mock_read.return_value = {
            "location": "北京", "temperature": 26.3, "humidity": 45,
            "weather_code": 0, "wind_speed": 12.5,
        }
        mock_refresh.return_value = True
        mock_geocode.return_value = None  # 城市未找到
        result = _get_weather_data({"location": "不存在的城市", "cache_ttl_minutes": 30})
        assert result is not None  # 回退旧缓存
        mock_fetch.assert_not_called()

    @patch("weather._fetch_weather")
    @patch("weather._geocode")
    @patch("weather._read_cache")
    @patch("weather._should_refresh")
    def test_geocode_none_no_cache_returns_none(self, mock_refresh, mock_read,
                                                   mock_geocode, mock_fetch):
        """geocoding 返回 None 且无旧缓存 → 返回 None。"""
        mock_read.return_value = None
        mock_refresh.return_value = True
        mock_geocode.return_value = None
        result = _get_weather_data({"location": "不存在的城市", "cache_ttl_minutes": 30})
        assert result is None
        mock_fetch.assert_not_called()

    @patch("weather._write_cache")
    @patch("weather._fetch_weather")
    @patch("weather._geocode")
    @patch("weather._read_cache")
    @patch("weather._should_refresh")
    def test_write_cache_failure_still_returns_data(self, mock_refresh, mock_read,
                                                      mock_geocode, mock_fetch, mock_write):
        """缓存写入失败时仍应返回天气数据（fail-open）。"""
        mock_read.return_value = None
        mock_refresh.return_value = True
        mock_geocode.return_value = (39.9, 116.4)
        mock_fetch.return_value = {
            "temperature": 20.0, "humidity": 60, "weather_code": 1, "wind_speed": 5.0,
        }
        mock_write.side_effect = OSError("disk full")
        result = _get_weather_data({"location": "北京", "cache_ttl_minutes": 30})
        assert result is not None
        assert result["temperature"] == 20.0


# ── _weather_context / _weather_context_for_narrative ──────────────────

class TestWeatherContextPublic:
    @patch("weather._get_weather_data")
    def test_weather_context_formats_direct(self, mock_get):
        mock_get.return_value = {
            "weather_code": 0, "temperature": 26.3, "humidity": 45,
            "wind_speed": 12.5, "location": "北京",
        }
        result = _weather_context({"location": "北京", "detail": "brief", "label": "🌤"})
        assert result == "🌤 北京 晴 26°C"

    @patch("weather._get_weather_data")
    def test_weather_context_returns_none_when_data_is_none(self, mock_get):
        mock_get.return_value = None
        assert _weather_context({"location": "北京"}) is None

    @patch("weather._get_weather_data")
    def test_weather_context_for_narrative(self, mock_get):
        mock_get.return_value = {
            "weather_code": 1, "temperature": 22.0, "humidity": 55,
            "wind_speed": 30.0,
        }
        result = _weather_context_for_narrative({"detail": "full"})
        # 1 → 多云, 30 km/h → Beaufort 5
        assert result == "多云，22°C，湿度55%，风力5级"

    @patch("weather._get_weather_data")
    def test_weather_context_for_narrative_returns_none(self, mock_get):
        mock_get.return_value = None
        assert _weather_context_for_narrative({"location": "北京"}) is None
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_weather.py::TestGetWeatherData tests/test_weather.py::TestWeatherContextPublic -v
```

- [ ] **Step 3: 实现 API 调用 + 数据管道 + 公开入口**

在 `weather.py` 末尾追加：

```python
# ---------------------------------------------------------------------------
# Open-Meteo API
# ---------------------------------------------------------------------------

_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


def _geocode(location: str) -> tuple[float, float] | None:
    """城市名 → (lat, lon)，失败返回 None。"""
    try:
        params = urllib.parse.urlencode({
            "name": location,
            "count": "1",
            "language": "zh",
        })
        url = f"{_GEOCODING_URL}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "hermes-persona/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results")
            if results and len(results) > 0:
                r = results[0]
                return (float(r["latitude"]), float(r["longitude"]))
            return None
    except Exception:
        return None


def _fetch_weather(lat: float, lon: float) -> dict | None:
    """Open-Meteo 天气 API → dict，失败返回 None。"""
    try:
        params = urllib.parse.urlencode({
            "latitude": str(lat),
            "longitude": str(lon),
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
        })
        url = f"{_WEATHER_URL}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "hermes-persona/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            current = data.get("current", {})
            return {
                "temperature": current.get("temperature_2m", 0),
                "humidity": current.get("relative_humidity_2m", 0),
                "weather_code": current.get("weather_code", 0),
                "wind_speed": current.get("wind_speed_10m", 0),
            }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core data pipeline
# ---------------------------------------------------------------------------


def _get_weather_data(config: dict) -> dict | None:
    """获取天气原始数据（共享缓存+API逻辑）。

    _weather_context 和 _weather_context_for_narrative 均调用此函数。

    Returns:
        dict with temperature/humidity/weather_code/wind_speed/location or None
    """
    location = config.get("location", "").strip()
    if not location:
        return None

    cache = _read_cache()

    if not _should_refresh(cache, config, location):
        return cache

    # 需要刷新 → 调 API
    try:
        lat = cache.get("latitude") if cache and cache.get("location") == location else None
        lon = cache.get("longitude") if cache and cache.get("location") == location else None

        if lat is None or lon is None:
            coords = _geocode(location)
            if coords is None:
                return cache if cache else None
            lat, lon = coords

        weather = _fetch_weather(lat, lon)
        if weather is None:
            return cache if cache else None

        now_iso = datetime.now(timezone.utc).isoformat()
        full_data = {
            "location": location,
            "latitude": lat,
            "longitude": lon,
            "weather_code": weather["weather_code"],
            "temperature": weather["temperature"],
            "humidity": weather["humidity"],
            "wind_speed": weather["wind_speed"],
            "fetched_at": now_iso,
        }
        _write_cache(None, full_data)
        return full_data
    except Exception:
        return cache if cache else None


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def _weather_context(config: dict) -> str | None:
    """获取天气上下文字符串（直接注入格式）。

    Returns:
        "🌤 北京 晴 26°C" or None（API失败且无缓存/未配置location）
    """
    data = _get_weather_data(config)
    if data is None:
        return None
    detail = config.get("detail", "brief")
    label = config.get("label", "🌤")
    return _format_weather(data, detail, label)


def _weather_context_for_narrative(config: dict) -> str | None:
    """获取天气上下文字符串（转译格式）。

    Returns:
        "晴，26°C，湿度45%" or None
    """
    data = _get_weather_data(config)
    if data is None:
        return None
    detail = config.get("detail", "brief")
    return _format_weather_narrative(data, detail)
```

- [ ] **Step 4: 运行全量 weather 测试**

```bash
python -m pytest tests/test_weather.py -v
```

- [ ] **Step 5: 提交**

```bash
git add weather.py tests/test_weather.py
git commit -m "feat(weather): API调用、数据管道、公开入口 — 含完整 mock 测试覆盖"
```

---

## Chunk 2: injector.py 集成

### Task 2.1: 导入 + 注册 + 注入调用点

**Files:**
- Modify: `injector.py`

- [ ] **Step 1: 添加导入**

在 `injector.py` 的 `from variance import _randomize_variance` 之后添加：

```python
from weather import _weather_context, _weather_context_for_narrative
```

- [ ] **Step 2: 注册 weather 模块**

在 `_MODULE_REGISTRY` 的 `"time"` 条目之后插入：

```python
    "weather": {
        "description": "天气上下文注入",
        "default": False,
        "phase": 1,
        "legacy_key": None,
        "legacy_path": None,
    },
```

- [ ] **Step 3: 添加 translate 模式数据容器**

在 `inject_context()` 的 translate 数据容器声明区域，找到 `_filtered_rules: list[str] = []` 行，在其后追加：

```python
        _weather_desc: str | None = None
```

- [ ] **Step 4: 添加注入调用点（紧跟 time 块之后）**

在 time 注入块（`# 1. Time context` 区域）之后，static_rules 块之前，插入：

```python
        # 1b. Weather context
        if _is_enabled(modules, "weather"):
            weather_cfg = config.get("weather", {})
            if _translate_mode:
                _weather_desc = _weather_context_for_narrative(weather_cfg)
            else:
                weather_text = _weather_context(weather_cfg)
                if weather_text:
                    parts.append(weather_text)
```

- [ ] **Step 5: 更新 `_assemble_narrative()` 调用**

找到 `narrative = _assemble_narrative(...)` 调用，添加 `weather_desc=_weather_desc` 参数。

- [ ] **Step 6: 提交**

```bash
git add injector.py
git commit -m "feat(weather): 集成 weather 模块到注入链 — 导入、注册、调用点"
```

### Task 2.2: 更新 `_assemble_narrative()` + `_debug_summary()`

**Files:**
- Modify: `injector.py`

- [ ] **Step 1: 更新 `_assemble_narrative()` 签名和实现**

修改函数签名，新增 `weather_desc: str | None` 参数。在函数体第一段（时间行拼装）中加入天气：

```python
def _assemble_narrative(
    weekday: str,
    current_time: str,
    time_slot_desc: str,
    weather_desc: str | None,
    today_turn: int,
    turn_stage_hint: str | None,
    top3: list[tuple[str, float, str]],
    variance_items: list[str],
    fixed_rules: list[str],
) -> str:
    """将分散的模块注入数据拼装为一段流畅的自然语言指令。

    各数据源独立，缺失项优雅跳过。
    weather_desc 为 None 时不输出天气段落。
    """
    lines: list[str] = []

    # ── ① 时间感知 + 时段规则 + 天气 ──
    time_line = f"现在时间是：{weekday}，{current_time}。"
    if weather_desc:
        time_line += f" 当地天气：{weather_desc}。"
    if time_slot_desc:
        time_line += f" {time_slot_desc}"
    lines.append(time_line)

    # ②-⑤ 后续段落保持不变
    ...
```

保留第 987-1010 行的其余逻辑不变。

- [ ] **Step 2: 更新 compact debug 摘要**

在 `_debug_summary()` compact 分支中，time 行之后插入：

```python
    # ①b Weather
    if _is_enabled(modules, "weather"):
        if any(p.startswith("🌤") for p in parts):
            lines.append("  ① 🌤 天气已注入")
        else:
            lines.append("  ① 🌤 未配置/API失败")
    else:
        lines.append("  ① 🌤 已停用")
```

- [ ] **Step 3: 更新 detailed debug 摘要**

在 `_detailed_summary()` 中 time 行之后插入：

```python
    # ①b Weather
    if _is_enabled(modules, "weather"):
        weather_parts = [p for p in parts if p.startswith("🌤")]
        weather_info = debug_context.get("weather", {})
        if weather_parts:
            lines.append(f"  ① 🌤 {weather_parts[0]}")
            cache_state = weather_info.get("cache_state", "未知")
            api_state = weather_info.get("api_state", "未知")
            lines.append(f"      缓存: {cache_state}")
            lines.append(f"      API: {api_state}")
        else:
            lines.append("  ① 🌤 未配置/API失败")
    else:
        lines.append("  ① 🌤 已停用")
```

- [ ] **Step 4: 在 `inject_context()` 中收集 weather debug 状态**

在 debug_context 组装区域（`_PENDING_DEBUG_BLOCK` 设置之前），新增 weather 状态收集：

```python
        # 收集 weather debug 状态（用于 detailed 模式）
        weather_debug: dict[str, str] = {}
        if _is_enabled(modules, "weather"):
            weather_cfg = config.get("weather", {})
            location = weather_cfg.get("location", "").strip()
            if not location:
                weather_debug = {"cache_state": "未配置", "api_state": "-"}
            else:
                # 通过判断 parts 中是否有天气行区分状态
                weather_injected = any(p.startswith("🌤") for p in parts)
                if weather_injected:
                    # 检查是否走了 API（通过 _should_refresh 间接推断）
                    from weather import _read_cache, _should_refresh
                    cache = _read_cache()
                    if _should_refresh(cache, weather_cfg, location):
                        weather_debug = {
                            "cache_state": "已过期-刷新" if cache else "无缓存-新建",
                            "api_state": "已调用",
                        }
                    else:
                        weather_debug = {"cache_state": "有效-跳过", "api_state": "未调用"}
                else:
                    weather_debug = {"cache_state": "API失败", "api_state": "失败"}
```

然后在 `debug_context` dict 中添加 `"weather": weather_debug`。

- [ ] **Step 5: 提交**

```bash
git add injector.py
git commit -m "feat(weather): 更新 _assemble_narrative 转译和 debug 摘要（compact+detailed）"
```

---

## Chunk 3: 配置

### Task 3.1: persona-config.json 模板

**Files:**
- Modify: `persona-config.json`

- [ ] **Step 1: 更新仓库模板**

在 `modules` 节中添加（默认关闭）：

```json
      "weather": false,
```

在 `hermes-persona` 根级，`time` 配置节之后添加：

```json
    "weather": {
      "location": "",
      "detail": "brief",
      "cache_ttl_minutes": 30,
      "label": "🌤"
    },
```

注意：locales 文件不需要修改——debug 摘要使用内联中/英文字符串，与现有 variance/fixed_signals 模块风格一致。

- [ ] **Step 2: 提交**

```bash
git add persona-config.json
git commit -m "feat(weather): 添加 weather 配置节到仓库模板"
```

---

## Chunk 4: 集成测试

### Task 4.1: inject_context 集成测试

**Files:**
- Modify: `tests/test_injector.py`

- [ ] **Step 1: 编写集成测试**

在 `tests/test_injector.py` 末尾追加：

```python
# ── Weather integration ─────────────────────────────────────────────────

from unittest.mock import patch


class TestWeatherInjection:
    def test_weather_disabled_by_default(self, temp_config_root, write_config,
                                          inject_context_defaults):
        """weather 默认关闭，不注入天气。"""
        write_config({
            "hermes-persona": {
                "modules": {},
                "weather": {"location": "北京", "detail": "brief", "label": "🌤"},
            }
        })
        result = inject_context(**inject_context_defaults)
        if result:
            assert "🌤" not in result["context"]

    def test_weather_enabled_injects(self, temp_config_root, write_config,
                                      inject_context_defaults):
        """weather 开启且有 location 时注入天气。"""
        write_config({
            "hermes-persona": {
                "modules": {"weather": True, "time": True},
                "weather": {"location": "北京", "detail": "brief", "label": "🌤"},
                "time": {"enabled": True, "format": "cn_full"},
            }
        })
        with patch("weather._get_weather_data") as mock_get:
            mock_get.return_value = {
                "weather_code": 0, "temperature": 26.3, "humidity": 45,
                "wind_speed": 12.5, "location": "北京",
            }
            result = inject_context(**inject_context_defaults)
            assert result is not None
            assert "🌤" in result["context"]
            assert "北京" in result["context"]

    def test_weather_no_location_skips(self, temp_config_root, write_config,
                                        inject_context_defaults):
        """location 为空时不注入天气。"""
        write_config({
            "hermes-persona": {
                "modules": {"weather": True, "time": True},
                "weather": {"location": "", "detail": "brief", "label": "🌤"},
                "time": {"enabled": True, "format": "cn_full"},
            }
        })
        result = inject_context(**inject_context_defaults)
        if result:
            assert "🌤" not in result["context"]

    def test_weather_translate_mode(self, temp_config_root, write_config,
                                     inject_context_defaults):
        """translate 模式下天气融入自然语言。"""
        write_config({
            "hermes-persona": {
                "modules": {"weather": True, "time": True, "translate": True,
                            "dynamic": False},
                "weather": {"location": "北京", "detail": "brief", "label": "🌤"},
                "time": {"enabled": True, "format": "cn_full"},
                "context": {},
            }
        })
        with patch("weather._get_weather_data") as mock_get:
            mock_get.return_value = {
                "weather_code": 0, "temperature": 26.3, "humidity": 45,
                "wind_speed": 12.5, "location": "北京",
            }
            result = inject_context(**inject_context_defaults)
            assert result is not None
            assert "当地天气" in result["context"]
            assert "晴" in result["context"]

    def test_weather_injection_order(self, temp_config_root, write_config,
                                      inject_context_defaults):
        """天气在时间之后、静态规则之前注入。"""
        write_config({
            "hermes-persona": {
                "modules": {"weather": True, "time": True, "static_rules": True},
                "weather": {"location": "北京", "detail": "brief", "label": "🌤"},
                "time": {"enabled": True, "format": "cn_full"},
                "context": {"rules": ["测试规则"]},
            }
        })
        with patch("weather._get_weather_data") as mock_get:
            mock_get.return_value = {
                "weather_code": 0, "temperature": 26.3, "humidity": 45,
                "wind_speed": 12.5, "location": "北京",
            }
            result = inject_context(**inject_context_defaults)
            assert result is not None
            ctx = result["context"]
            time_pos = ctx.index("🕐")
            weather_pos = ctx.index("🌤")
            rule_pos = ctx.index("测试规则")
            assert time_pos < weather_pos < rule_pos

    def test_weather_debug_compact(self, temp_config_root, write_config,
                                    inject_context_defaults):
        """compact debug 模式显示天气注入状态。"""
        write_config({
            "hermes-persona": {
                "modules": {"weather": True, "time": True, "debug": True},
                "weather": {"location": "北京", "detail": "brief", "label": "🌤"},
                "time": {"enabled": True, "format": "cn_full"},
                "debug": {"detail": "compact"},
            }
        })
        with patch("weather._get_weather_data") as mock_get:
            mock_get.return_value = {
                "weather_code": 0, "temperature": 26.3, "humidity": 45,
                "wind_speed": 12.5, "location": "北京",
            }
            # inject_context sets _PENDING_DEBUG_BLOCK
            from injector import _PENDING_DEBUG_BLOCK
            import injector as inj
            # 直接调用以触发 debug block 设置
            inj.inject_context(**inject_context_defaults)
            debug_block = inj._PENDING_DEBUG_BLOCK
            assert debug_block is not None
            assert "🌤" in debug_block
```

注意：debug 测试验证 `_PENDING_DEBUG_BLOCK` 全局变量——当前代码架构下 debug 不直接返回在 `result["context"]` 中，而是通过 `transform_llm_output` hook 追加。测试直接检查 `injector._PENDING_DEBUG_BLOCK`。

- [ ] **Step 2: 运行集成测试**

```bash
python -m pytest tests/test_injector.py::TestWeatherInjection -v
```

- [ ] **Step 3: 修复问题并确保通过**

- [ ] **Step 4: 提交**

```bash
git add tests/test_injector.py
git commit -m "test(weather): 集成测试 — 开关、translate、注入顺序、debug摘要"
```

---

## Chunk 5: 全量测试 + 最终验证

### Task 5.1: 运行全量测试 + 手动验证

- [ ] **Step 1: 运行全部测试**

```bash
python -m pytest tests/ -v
```

确保所有已有测试仍然通过，新增测试全部通过。

- [ ] **Step 2: 手动验证 API 连接**

```bash
python -c "
from weather import _geocode, _fetch_weather
coords = _geocode('北京')
print(f'Coordinates: {coords}')
if coords:
    weather = _fetch_weather(*coords)
    print(f'Weather: {weather}')
"
```

预期：输出北京坐标和当前天气数据。

- [ ] **Step 3: 提交最终版本**

```bash
git add -A
git commit -m "feat(weather): 完成天气上下文注入模块 — 全部测试通过"
```

---

## 检查清单

- [ ] `weather.py` 所有函数有 docstring
- [ ] fail-open：任何异常不阻断注入链
- [ ] `_should_refresh` 统一决策：TTL + location变更 + 无缓存 + 损坏日期
- [ ] 文件缓存路径：`{plugin_dir}/state/weather_cache.json`
- [ ] translate 模式：天气自然融入 `_assemble_narrative` 时间行
- [ ] debug compact + detailed 都显示天气状态（含 cache/API 诊断）
- [ ] `persona-config.json` 仓库模板已更新
- [ ] 纯函数测试覆盖：WMO码、Beaufort、格式化、决策、缓存读写
- [ ] Mock 测试覆盖：API成功/失败、缓存命中/过期、geocode失败/None、缓存损坏、写入失败
- [ ] 集成测试覆盖：开关、translate、注入顺序、debug摘要
- [ ] 全部已有测试仍通过
