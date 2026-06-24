"""和风天气 provider — 需要 QWEATHER_KEY 环境变量。

API: https://devapi.qweather.com/v7/weather/now
Geo: https://geoapi.qweather.com/v2/city/lookup
"""

import json
import os
import urllib.request
import urllib.parse

from weather import WeatherProvider

_QWEATHER_GEO_URL = "https://geoapi.qweather.com/v2/city/lookup"
_QWEATHER_WEATHER_URL = "https://devapi.qweather.com/v7/weather/now"

# 和风天气 icon → WMO 码映射表
_QW_TO_WMO: dict[int, int] = {
    100: 0,   # 晴
    101: 1,   # 多云
    102: 2,   # 少云
    103: 3,   # 晴间多云
    104: 3,   # 阴
    300: 61,  # 阵雨
    301: 61,  # 强阵雨
    302: 95,  # 雷阵雨
    303: 95,  # 强雷阵雨
    304: 95,  # 雷阵雨伴有冰雹
    305: 51,  # 小雨
    306: 61,  # 中雨
    307: 63,  # 大雨
    308: 65,  # 暴雨
    309: 51,  # 毛毛雨
    400: 71,  # 小雪
    401: 73,  # 中雪
    402: 75,  # 大雪
    403: 75,  # 暴雪
    404: 85,  # 阵雪
    405: 73,  # 小雪
    406: 75,  # 中雪
    407: 75,  # 大雪
    500: 45,  # 薄雾
    501: 45,  # 雾
    502: 45,  # 霾
    503: 45,  # 扬沙
    504: 45,  # 浮尘
}


class QWeatherProvider(WeatherProvider):
    """和风天气数据源 — 国内精准，支持分钟级降水。

    环境变量：QWEATHER_KEY
    """

    name = "qweather"
    requires_key = True
    env_var = "QWEATHER_KEY"

    def geocode(self, location: str) -> tuple[float, float] | None:
        """城市名 → (lat, lon)。优先用和风 geocoding API，失败回退 Open-Meteo。"""
        key = os.environ.get(self.env_var, "").strip()
        if not key:
            return super().geocode(location)

        try:
            params = urllib.parse.urlencode({
                "location": location,
                "key": key,
            })
            url = f"{_QWEATHER_GEO_URL}?{params}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                locs = data.get("location", [])
                if locs:
                    return (float(locs[0]["lat"]), float(locs[0]["lon"]))
        except Exception:
            pass

        # 回退到 Open-Meteo geocoding
        return super().geocode(location)

    def fetch(self, lat: float, lon: float) -> dict | None:
        """和风天气 API → 统一格式 dict。"""
        key = os.environ.get(self.env_var, "").strip()
        if not key:
            return None

        try:
            params = urllib.parse.urlencode({
                "location": f"{lon},{lat}",
                "key": key,
            })
            url = f"{_QWEATHER_WEATHER_URL}?{params}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                return self.normalize(raw)
        except Exception:
            return None

    def normalize(self, raw: dict) -> dict | None:
        """和风天气响应 → 统一格式 dict。"""
        try:
            now = raw["now"]
            code = int(now["icon"])
            wmo_code = _QW_TO_WMO.get(code, 0)
            return {
                "temperature": float(now["temp"]),
                "humidity": float(now["humidity"]),
                "weather_code": wmo_code,
                "wind_speed": float(now["windSpeed"]),
            }
        except (KeyError, ValueError, TypeError):
            return None
