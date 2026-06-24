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
# Data validation (logical consistency checks)
# ---------------------------------------------------------------------------

_THUNDERSTORM_CODES = (95, 96, 99)
# 雷暴通常伴随阵风（≥ 风力 3 级 = 12 km/h）
_MIN_THUNDERSTORM_WIND_KMH = 12


def _validate_weather(data: dict, validation_cfg: dict | None = None) -> bool:
    """校验天气数据逻辑自洽性。

    返回 True 表示数据可疑（suspicious）。校验规则可通过 validation_cfg
    逐条禁用。纯函数，不修改输入 data。

    规则：
    - 雷暴码 + 风力 < 12 km/h → 可疑（模型可能误判对流活动范围）
    - weather_code is None 或越界（不在 0-99 范围）→ 可疑
    - temperature is None → 可疑
    """
    cfg = validation_cfg or {}
    code = data.get("weather_code")
    wind = data.get("wind_speed")
    temp = data.get("temperature")

    # 雷暴风力矛盾（可禁用）
    if cfg.get("thunderstorm_wind_check", True):
        if (code in _THUNDERSTORM_CODES
                and isinstance(wind, (int, float)) and wind < _MIN_THUNDERSTORM_WIND_KMH):
            return True

    # 天气码无效
    if code is None or not isinstance(code, int) or not (0 <= code <= 99):
        return True

    # 温度缺失
    if temp is None:
        return True

    return False


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
    suspicious = data.get("suspicious", False)

    suffix = "（天气数据可能不准确）" if suspicious else ""
    base = f"{label} {loc} {cn_desc} {temp}°C{suffix}"

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
    suspicious = data.get("suspicious", False)

    suffix = "（天气数据可能不准确）" if suspicious else ""
    base = f"{cn_desc}，{temp}°C{suffix}"

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
_WTTR_URL = "https://wttr.in"


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
            # 任一字段缺失或 None → 视为 API 失败（触发 _get_weather_data 缓存回退）
            required = ["temperature_2m", "relative_humidity_2m",
                        "weather_code", "wind_speed_10m"]
            if not all(k in current and current[k] is not None for k in required):
                return None
            return {
                "temperature": current["temperature_2m"],
                "humidity": current["relative_humidity_2m"],
                "weather_code": current["weather_code"],
                "wind_speed": current["wind_speed_10m"],
            }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# wttr.in Provider (keyless fallback source)
# ---------------------------------------------------------------------------


class WttrProvider:
    """wttr.in 天气数据源 — 免费，无需 API key。

    API 端点：https://wttr.in/{lat},{lon}?format=j1
    对无效坐标返回 HTML 错误页（Content-Type: text/html），需检测。
    """

    name: str = "wttr"
    requires_key: bool = False

    def geocode(self, location: str) -> tuple[float, float] | None:
        """城市名 → (lat, lon)。复用 Open-Meteo geocoding API。"""
        return _geocode(location)

    def fetch(self, lat: float, lon: float) -> dict | None:
        """wttr.in API → 统一格式 dict，失败返回 None。"""
        try:
            url = f"{_WTTR_URL}/{lat},{lon}?format=j1"
            req = urllib.request.Request(url, headers={"User-Agent": "hermes-persona/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                # wttr.in 错误时返回 HTML，检测 Content-Type
                content_type = resp.headers.get("Content-Type", "")
                if "json" not in content_type:
                    return None
                raw = json.loads(resp.read().decode("utf-8"))
                return self.normalize(raw)
        except Exception:
            return None

    def normalize(self, raw: dict) -> dict | None:
        """wttr.in JSON → 统一格式 dict。

        返回 {"temperature": float, "humidity": float,
               "weather_code": int, "wind_speed": float}
        或 None（字段缺失/类型错误）。
        """
        try:
            current = raw.get("current_condition", [])
            if not current:
                return None
            c = current[0]
            return {
                "temperature": int(c["temp_C"]),
                "humidity": int(c["humidity"]),
                "weather_code": int(c["weatherCode"]),
                "wind_speed": int(c["windspeedKmph"]),
            }
        except (KeyError, ValueError, TypeError, IndexError):
            return None


# ---------------------------------------------------------------------------
# Debug state (module-level, for debug summary in injector.py)
# ---------------------------------------------------------------------------

_LAST_DEBUG_STATE: dict[str, str] = {}


def _get_debug_state() -> dict[str, str]:
    """返回上次 _get_weather_data 调用采集的 debug 状态（供 debug 摘要读取）。

    避免 injector.py 在注入后重读缓存导致的时序误报。
    """
    return dict(_LAST_DEBUG_STATE)


# ---------------------------------------------------------------------------
# Cross-validation
# ---------------------------------------------------------------------------


def _cross_validate(primary_data: dict, fallback_data: dict) -> bool:
    """交叉校验两个数据源是否一致。

    对比 weather_code 是否相同 + 温差是否在 5°C 内。
    两个条件都满足（AND）才返回 True（两源一致）。
    """
    code_match = primary_data["weather_code"] == fallback_data["weather_code"]
    temp_close = abs(primary_data["temperature"] - fallback_data["temperature"]) <= 5
    return code_match and temp_close


# ---------------------------------------------------------------------------
# Core data pipeline
# ---------------------------------------------------------------------------


def _get_weather_data(config: dict) -> dict | None:
    """获取天气原始数据（共享缓存+API逻辑 + 双源 fallback）。

    _weather_context 和 _weather_context_for_narrative 均调用此函数。

    Returns:
        dict with temperature/humidity/weather_code/wind_speed/location/source or None
    """
    location = config.get("location", "").strip()
    if not location:
        return None

    cache = _read_cache()

    if not _should_refresh(cache, config, location):
        # 旧缓存可能无 suspicious / source 字段 → 补全
        if "suspicious" not in cache:
            cache["suspicious"] = _validate_weather(cache, config.get("validation"))
        if "source" not in cache:
            cache["source"] = "openmeteo"
        _LAST_DEBUG_STATE.update(cache_state="有效-跳过", api_state="未调用")
        return cache

    # 需要刷新 → 调 API（双源 fallback）
    full_data = None
    try:
        lat = cache.get("latitude") if cache and cache.get("location") == location else None
        lon = cache.get("longitude") if cache and cache.get("location") == location else None

        if lat is None or lon is None:
            coords = _geocode(location)
            if coords is None:
                # 回退旧缓存仅当 location 一致（避免返回错误城市数据）
                if cache and cache.get("location") == location:
                    if "source" not in cache:
                        cache["source"] = "openmeteo"
                    _LAST_DEBUG_STATE.update(cache_state="失败-回退缓存", api_state="失败")
                    return cache
                _LAST_DEBUG_STATE.update(cache_state="无缓存", api_state="失败")
                return None
            lat, lon = coords

        # ── 主力源：Open-Meteo ──
        primary_data = _fetch_weather(lat, lon)

        if primary_data is not None:
            suspicious = _validate_weather(primary_data, config.get("validation"))
            if not suspicious:
                # 主力源正常 → 直接使用
                weather = primary_data
                source = "openmeteo"
                cross_validated = False
                _LAST_DEBUG_STATE.update(cache_state="已刷新", api_state="正常")
            else:
                # 主力源可疑 → 尝试 wttr.in 交叉校验
                try:
                    wttr = WttrProvider()
                    wttr_data = wttr.fetch(lat, lon)
                    if wttr_data:
                        if _cross_validate(primary_data, wttr_data):
                            # 双源一致 → 用主力源数据，标记双源确认
                            weather = primary_data
                            source = "openmeteo"
                            cross_validated = True
                            suspicious = False
                            _LAST_DEBUG_STATE.update(
                                cache_state="已刷新-双源确认", api_state="正常"
                            )
                        else:
                            # 双源不一致 → 用 wttr.in 数据
                            weather = wttr_data
                            source = "wttr"
                            cross_validated = False
                            suspicious = False
                            _LAST_DEBUG_STATE.update(
                                cache_state="已刷新-wttr", api_state="正常"
                            )
                    else:
                        # wttr 也失败 → 保留主力源数据 + 标记可疑
                        weather = primary_data
                        source = "openmeteo"
                        cross_validated = False
                        _LAST_DEBUG_STATE.update(cache_state="已刷新", api_state="正常")
                except Exception:
                    weather = primary_data
                    source = "openmeteo"
                    cross_validated = False
                    _LAST_DEBUG_STATE.update(cache_state="已刷新", api_state="正常")
        else:
            # 主力源失败 → 尝试 wttr.in
            try:
                wttr = WttrProvider()
                wttr_data = wttr.fetch(lat, lon)
                if wttr_data:
                    weather = wttr_data
                    source = "wttr"
                    cross_validated = False
                    suspicious = False
                    _LAST_DEBUG_STATE.update(
                        cache_state="已刷新-wttr", api_state="正常"
                    )
                else:
                    # 双源失败 → 回退缓存或 None
                    if cache:
                        if "source" not in cache:
                            cache["source"] = "openmeteo"
                        cache["suspicious"] = True
                        _LAST_DEBUG_STATE.update(
                            cache_state="失败-回退缓存", api_state="双源失败"
                        )
                        return cache
                    _LAST_DEBUG_STATE.update(cache_state="无缓存", api_state="双源失败")
                    return None
            except Exception:
                if cache:
                    if "source" not in cache:
                        cache["source"] = "openmeteo"
                    cache["suspicious"] = True
                    _LAST_DEBUG_STATE.update(
                        cache_state="失败-回退缓存", api_state="双源失败"
                    )
                    return cache
                _LAST_DEBUG_STATE.update(cache_state="无缓存", api_state="双源失败")
                return None

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
            "suspicious": suspicious,
            "source": source,
            "cross_validated": cross_validated,
        }
    except Exception:
        if cache:
            if "source" not in cache:
                cache["source"] = "openmeteo"
        _LAST_DEBUG_STATE.update(
            cache_state="失败-回退缓存" if cache else "无缓存", api_state="失败"
        )
        return cache if cache else None

    # 缓存写入失败不影响数据返回（fail-open）
    try:
        _write_cache(None, full_data)
    except Exception:
        pass

    # 仅在不重复设置时更新（部分分支已在内部更新过 debug state）
    # 注意：full_data 的组装只在 primary 成功或 fallback 成功的分支中到达，
    # 此时 debug state 已经在各分支中设置，故此处不再覆盖。
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
