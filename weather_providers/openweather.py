"""OpenWeather provider — 需要 OWM_KEY 环境变量。

API: https://api.openweathermap.org/data/2.5/weather
"""

import json
import os
import urllib.request
import urllib.parse

from weather import WeatherProvider

_OWM_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


class OpenWeatherProvider(WeatherProvider):
    """OpenWeather 数据源 — 全球覆盖，免费 100 万次/月。

    环境变量：OWM_KEY
    """

    name = "openweather"
    requires_key = True
    env_var = "OWM_KEY"

    def fetch(self, lat: float, lon: float) -> dict | None:
        """OpenWeather API → 统一格式 dict。"""
        key = os.environ.get(self.env_var, "").strip()
        if not key:
            return None

        try:
            params = urllib.parse.urlencode({
                "lat": str(lat),
                "lon": str(lon),
                "appid": key,
                "units": "metric",
            })
            url = f"{_OWM_WEATHER_URL}?{params}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                return self.normalize(raw)
        except Exception:
            return None

    def normalize(self, raw: dict) -> dict | None:
        """OpenWeather 响应 → 统一格式 dict。"""
        try:
            main = raw["main"]
            weather_list = raw["weather"]
            wind = raw.get("wind", {})

            weather_code = weather_list[0]["id"] if weather_list else 0
            temperature = float(main["temp"])
            humidity = float(main["humidity"])
            # OpenWeather 风速单位 m/s → km/h
            wind_speed_ms = float(wind.get("speed", 0))
            wind_speed_kmh = wind_speed_ms * 3.6

            return {
                "temperature": temperature,
                "humidity": humidity,
                "weather_code": weather_code,
                "wind_speed": wind_speed_kmh,
            }
        except (KeyError, ValueError, TypeError, IndexError):
            return None
