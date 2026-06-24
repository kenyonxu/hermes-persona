"""心知天气 provider — 需要 SENIVERSE_KEY 环境变量。

API: https://api.seniverse.com/v3/weather/now.json
"""

import json
import os
import urllib.request
import urllib.parse

from weather import WeatherProvider

_SENIVERSE_WEATHER_URL = "https://api.seniverse.com/v3/weather/now.json"

# 心知天气 code → WMO 码映射表
_SV_TO_WMO: dict[int, int] = {
    0: 0,    # 晴
    1: 1,    # 多云
    2: 3,    # 阴
    3: 80,   # 阵雨
    4: 95,   # 雷阵雨
    5: 96,   # 雷阵雨伴有冰雹
    6: 85,   # 雨夹雪
    7: 61,   # 小雨
    8: 63,   # 中雨
    9: 65,   # 大雨
    10: 65,  # 暴雨
    13: 71,  # 小雪
    14: 73,  # 中雪
    15: 75,  # 大雪
    18: 45,  # 雾
    19: 66,  # 冻雨
    20: 45,  # 沙尘暴
    29: 45,  # 浮尘
    30: 45,  # 扬沙
    31: 45,  # 强沙尘暴
}


class SeniverseProvider(WeatherProvider):
    """心知天气数据源 — 气象局授权，无限调用。

    环境变量：SENIVERSE_KEY
    """

    name = "seniverse"
    requires_key = True
    env_var = "SENIVERSE_KEY"

    def fetch(self, lat: float, lon: float) -> dict | None:
        """心知天气 API → 统一格式 dict。"""
        key = os.environ.get(self.env_var, "").strip()
        if not key:
            return None

        try:
            params = urllib.parse.urlencode({
                "key": key,
                "location": f"{lat}:{lon}",
            })
            url = f"{_SENIVERSE_WEATHER_URL}?{params}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                return self.normalize(raw)
        except Exception:
            return None

    def normalize(self, raw: dict) -> dict | None:
        """心知天气响应 → 统一格式 dict。"""
        try:
            results = raw["results"]
            if not results:
                return None
            now = results[0]["now"]
            code = int(now["code"])
            wmo_code = _SV_TO_WMO.get(code, 0)
            return {
                "temperature": float(now["temperature"]),
                "humidity": float(now.get("humidity", 0)),
                "weather_code": wmo_code,
                "wind_speed": float(now.get("wind_speed", 0)),
            }
        except (KeyError, ValueError, TypeError, IndexError):
            return None
