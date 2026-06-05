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
    _get_weather_data,
    _weather_context,
    _weather_context_for_narrative,
)


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
        mock_geocode.return_value = None
        result = _get_weather_data({"location": "不存在的城市", "cache_ttl_minutes": 30})
        assert result is not None
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
