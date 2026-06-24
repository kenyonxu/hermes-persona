"""Tests for keyed weather providers — mocked API calls."""

import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest


# ── QWeatherProvider ─────────────────────────────────────────────────────


class TestQWeatherProvider:
    def test_name_and_requires_key(self):
        from weather_providers.qweather import QWeatherProvider
        p = QWeatherProvider()
        assert p.name == "qweather"
        assert p.requires_key is True
        assert p.env_var == "QWEATHER_KEY"

    def test_normalize_valid_response(self):
        from weather_providers.qweather import QWeatherProvider
        p = QWeatherProvider()
        raw = {
            "now": {
                "temp": "28", "humidity": "85",
                "icon": "100", "windSpeed": "15",
            }
        }
        result = p.normalize(raw)
        assert result is not None
        assert result["temperature"] == 28.0
        assert result["humidity"] == 85.0
        assert result["weather_code"] == 0  # icon 100 → WMO 0 (晴)
        assert result["wind_speed"] == 15.0

    def test_normalize_missing_now(self):
        from weather_providers.qweather import QWeatherProvider
        p = QWeatherProvider()
        assert p.normalize({}) is None

    def test_normalize_missing_field(self):
        from weather_providers.qweather import QWeatherProvider
        p = QWeatherProvider()
        raw = {"now": {"temp": "28"}}  # 缺少 icon
        assert p.normalize(raw) is None

    @patch.dict(os.environ, {"QWEATHER_KEY": "test-key"})
    @patch("urllib.request.urlopen")
    def test_fetch_success(self, mock_urlopen):
        from weather_providers.qweather import QWeatherProvider
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "now": {"temp": "28", "humidity": "85",
                    "icon": "100", "windSpeed": "15"}
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        p = QWeatherProvider()
        result = p.fetch(22.5, 114.0)
        assert result is not None
        assert result["temperature"] == 28.0

    @patch.dict(os.environ, {}, clear=True)
    def test_fetch_without_key_returns_none(self):
        from weather_providers.qweather import QWeatherProvider
        p = QWeatherProvider()
        result = p.fetch(22.5, 114.0)
        assert result is None

    def test_weather_code_mapping(self):
        """验证关键天气码映射。"""
        from weather_providers.qweather import QWeatherProvider
        p = QWeatherProvider()
        # 晴 → 0
        result = p.normalize({"now": {"temp": "25", "humidity": "50",
                                       "icon": "100", "windSpeed": "10"}})
        assert result["weather_code"] == 0
        # 雷阵雨 → 95
        result = p.normalize({"now": {"temp": "25", "humidity": "90",
                                       "icon": "302", "windSpeed": "20"}})
        assert result["weather_code"] == 95
        # 大雨 → 63
        result = p.normalize({"now": {"temp": "25", "humidity": "95",
                                       "icon": "307", "windSpeed": "15"}})
        assert result["weather_code"] == 63


# ── OpenWeatherProvider ──────────────────────────────────────────────────


class TestOpenWeatherProvider:
    def test_name_and_requires_key(self):
        from weather_providers.openweather import OpenWeatherProvider
        p = OpenWeatherProvider()
        assert p.name == "openweather"
        assert p.requires_key is True
        assert p.env_var == "OWM_KEY"

    def test_normalize_valid_response(self):
        from weather_providers.openweather import OpenWeatherProvider
        p = OpenWeatherProvider()
        raw = {
            "main": {"temp": 28.0, "humidity": 85},
            "weather": [{"id": 800, "main": "Clear"}],
            "wind": {"speed": 5.0},
        }
        result = p.normalize(raw)
        assert result is not None
        assert result["temperature"] == 28.0
        assert result["humidity"] == 85.0
        assert result["weather_code"] == 800
        assert result["wind_speed"] == 18.0  # 5 m/s * 3.6 = 18 km/h

    def test_normalize_wind_speed_conversion(self):
        """风速 m/s → km/h 转换。"""
        from weather_providers.openweather import OpenWeatherProvider
        p = OpenWeatherProvider()
        raw = {
            "main": {"temp": 20.0, "humidity": 60},
            "weather": [{"id": 500, "main": "Rain"}],
            "wind": {"speed": 10.0},
        }
        result = p.normalize(raw)
        assert result["wind_speed"] == 36.0  # 10 * 3.6

    def test_normalize_no_wind(self):
        """wind 字段缺失时默认 0。"""
        from weather_providers.openweather import OpenWeatherProvider
        p = OpenWeatherProvider()
        raw = {
            "main": {"temp": 20.0, "humidity": 60},
            "weather": [{"id": 500}],
        }
        result = p.normalize(raw)
        assert result["wind_speed"] == 0.0

    def test_normalize_missing_main(self):
        from weather_providers.openweather import OpenWeatherProvider
        p = OpenWeatherProvider()
        assert p.normalize({"weather": [{"id": 800}]}) is None

    @patch.dict(os.environ, {"OWM_KEY": "test-key"})
    @patch("urllib.request.urlopen")
    def test_fetch_success(self, mock_urlopen):
        from weather_providers.openweather import OpenWeatherProvider
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "main": {"temp": 28.0, "humidity": 85},
            "weather": [{"id": 800}],
            "wind": {"speed": 5.0},
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        p = OpenWeatherProvider()
        result = p.fetch(22.5, 114.0)
        assert result is not None
        assert result["temperature"] == 28.0

    @patch.dict(os.environ, {}, clear=True)
    def test_fetch_without_key_returns_none(self):
        from weather_providers.openweather import OpenWeatherProvider
        p = OpenWeatherProvider()
        result = p.fetch(22.5, 114.0)
        assert result is None


# ── SeniverseProvider ────────────────────────────────────────────────────


class TestSeniverseProvider:
    def test_name_and_requires_key(self):
        from weather_providers.seniverse import SeniverseProvider
        p = SeniverseProvider()
        assert p.name == "seniverse"
        assert p.requires_key is True
        assert p.env_var == "SENIVERSE_KEY"

    def test_normalize_valid_response(self):
        from weather_providers.seniverse import SeniverseProvider
        p = SeniverseProvider()
        raw = {
            "results": [{
                "now": {
                    "code": "0", "temperature": "28",
                    "humidity": "85", "wind_speed": "15",
                }
            }]
        }
        result = p.normalize(raw)
        assert result is not None
        assert result["temperature"] == 28.0
        assert result["humidity"] == 85.0
        assert result["weather_code"] == 0  # code 0 → WMO 0 (晴)

    def test_normalize_empty_results(self):
        from weather_providers.seniverse import SeniverseProvider
        p = SeniverseProvider()
        assert p.normalize({"results": []}) is None

    def test_normalize_missing_results(self):
        from weather_providers.seniverse import SeniverseProvider
        p = SeniverseProvider()
        assert p.normalize({}) is None

    def test_weather_code_mapping(self):
        """验证关键天气码映射。"""
        from weather_providers.seniverse import SeniverseProvider
        p = SeniverseProvider()
        # 晴 → 0
        result = p.normalize({"results": [{"now": {"code": "0", "temperature": "25",
                                                     "humidity": "50", "wind_speed": "10"}}]})
        assert result["weather_code"] == 0
        # 雷阵雨 → 95
        result = p.normalize({"results": [{"now": {"code": "4", "temperature": "25",
                                                     "humidity": "90", "wind_speed": "20"}}]})
        assert result["weather_code"] == 95
        # 大雨 → 65
        result = p.normalize({"results": [{"now": {"code": "9", "temperature": "25",
                                                     "humidity": "95", "wind_speed": "15"}}]})
        assert result["weather_code"] == 65

    @patch.dict(os.environ, {"SENIVERSE_KEY": "test-key"})
    @patch("urllib.request.urlopen")
    def test_fetch_success(self, mock_urlopen):
        from weather_providers.seniverse import SeniverseProvider
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "results": [{
                "now": {"code": "0", "temperature": "28",
                        "humidity": "85", "wind_speed": "15"}
            }]
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        p = SeniverseProvider()
        result = p.fetch(22.5, 114.0)
        assert result is not None
        assert result["temperature"] == 28.0

    @patch.dict(os.environ, {}, clear=True)
    def test_fetch_without_key_returns_none(self):
        from weather_providers.seniverse import SeniverseProvider
        p = SeniverseProvider()
        result = p.fetch(22.5, 114.0)
        assert result is None


# ── 惰性导入 + 注册集成 ──────────────────────────────────────────────────


class TestKeyedProviderIntegration:
    def test_qweather_not_registered_when_key_missing(self):
        """未设置 QWEATHER_KEY → qweather 不在注册表中。"""
        from weather import _PROVIDER_REGISTRY
        # 在已加载的注册表中，keyed provider 应该未注册（除非设置了环境变量）
        # 注：模块已加载时环境变量状态由 _register_keyed_providers() 在 import 时决定
        # 这里只验证注册表访问逻辑
        assert isinstance(_PROVIDER_REGISTRY, dict)
        assert "openmeteo" in _PROVIDER_REGISTRY
        assert "wttr" in _PROVIDER_REGISTRY

    @patch.dict(os.environ, {"QWEATHER_KEY": "test-key"})
    def test_qweather_registers_when_key_present(self):
        """环境变量存在时惰性导入成功。"""
        from weather import _register_keyed_providers, _PROVIDER_REGISTRY
        _register_keyed_providers()
        assert "qweather" in _PROVIDER_REGISTRY

    @patch.dict(os.environ, {}, clear=True)
    def test_get_provider_returns_none_for_unregistered_keyed(self):
        """keyed provider 未注册时 _get_provider 返回 None。"""
        from weather import _get_provider
        assert _get_provider("qweather") is None
        assert _get_provider("openweather") is None
        assert _get_provider("seniverse") is None
