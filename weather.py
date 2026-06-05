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
    full_data = None
    try:
        lat = cache.get("latitude") if cache and cache.get("location") == location else None
        lon = cache.get("longitude") if cache and cache.get("location") == location else None

        if lat is None or lon is None:
            coords = _geocode(location)
            if coords is None:
                # 回退旧缓存仅当 location 一致（避免返回错误城市数据）
                if cache and cache.get("location") == location:
                    return cache
                return None
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
    except Exception:
        return cache if cache else None

    # 缓存写入失败不影响数据返回（fail-open）
    try:
        _write_cache(None, full_data)
    except Exception:
        pass
    return full_data


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
