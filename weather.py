"""Weather context provider: Open-Meteo API + file-based cache.

Provides weather information for persona context injection.
Fail-open on any API/IO error — never blocks the injection chain.
"""

from __future__ import annotations

import importlib
import json
import os
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

    含数据源标注：
    - suspicious → "（天气数据可能不准确）"
    - source ≠ openmeteo → "（来源: {source}）"
    - cross_validated → "（双源确认）"
    """
    cn_desc, _ = _weather_code_to_cn(data["weather_code"])
    temp = round(data["temperature"])
    loc = data.get("location", "")
    suspicious = data.get("suspicious", False)
    source = data.get("source", "")
    cross_validated = data.get("cross_validated", False)

    suffix_parts = []
    if suspicious:
        suffix_parts.append("天气数据可能不准确")
    if source and source != "openmeteo":
        suffix_parts.append(f"来源: {source}")
    if cross_validated:
        suffix_parts.append("双源确认")

    suffix = f"（{'，'.join(suffix_parts)}）" if suffix_parts else ""
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

    含数据源标注（同 _format_weather）。
    """
    cn_desc, _ = _weather_code_to_cn(data["weather_code"])
    temp = round(data["temperature"])
    suspicious = data.get("suspicious", False)
    source = data.get("source", "")
    cross_validated = data.get("cross_validated", False)

    suffix_parts = []
    if suspicious:
        suffix_parts.append("天气数据可能不准确")
    if source and source != "openmeteo":
        suffix_parts.append(f"来源: {source}")
    if cross_validated:
        suffix_parts.append("双源确认")

    suffix = f"（{'，'.join(suffix_parts)}）" if suffix_parts else ""
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
# Weather Provider abstract layer
# ---------------------------------------------------------------------------


class WeatherProvider:
    """天气数据源协议。

    子类实现 fetch() 和 normalize()。geocode() 有默认实现
    （复用 Open-Meteo geocoding API）。
    """

    name: str = ""
    requires_key: bool = False

    def geocode(self, location: str) -> tuple[float, float] | None:
        """城市名 → (lat, lon)。默认使用 Open-Meteo geocoding API。"""
        return _geocode(location)

    def fetch(self, lat: float, lon: float) -> dict | None:
        """获取天气原始数据 → 统一格式 dict，失败返回 None。"""
        raise NotImplementedError

    def normalize(self, raw: dict) -> dict | None:
        """Provider 原始响应 → 统一格式 dict。子类必须实现。"""
        raise NotImplementedError


class OpenMeteoProvider(WeatherProvider):
    """Open-Meteo 天气数据源 — 免费，无需 API key。"""

    name = "openmeteo"
    requires_key = False

    def fetch(self, lat: float, lon: float) -> dict | None:
        """委托给模块级 _fetch_weather()。"""
        return _fetch_weather(lat, lon)

    def normalize(self, raw: dict) -> dict | None:
        """Open-Meteo 已输出统一格式，原样返回。"""
        return raw


# ---------------------------------------------------------------------------
# wttr.in Provider (keyless fallback source)
# ---------------------------------------------------------------------------


class WttrProvider(WeatherProvider):
    """wttr.in 天气数据源 — 免费，无需 API key。

    API 端点：https://wttr.in/{lat},{lon}?format=j1
    对无效坐标返回 HTML 错误页（Content-Type: text/html），需检测。
    """

    name: str = "wttr"
    requires_key: bool = False

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
# Provider registry + scheduling
# ---------------------------------------------------------------------------

# 内置 keyless provider 注册表（keyed provider 惰性导入后追加）
_PROVIDER_REGISTRY: dict[str, type[WeatherProvider]] = {
    "openmeteo": OpenMeteoProvider,
    "wttr": WttrProvider,
}


def _get_provider(name: str) -> WeatherProvider | None:
    """根据标识符获取 provider 实例。

    - 内置 keyless provider：直接实例化
    - keyed provider：检查环境变量，不存在则返回 None
    - 未知标识符：返回 None
    """
    cls = _PROVIDER_REGISTRY.get(name)
    if cls is None:
        return None

    instance = cls()
    if instance.requires_key:
        env_var = getattr(instance, "env_var", "")
        if env_var:
            key = os.environ.get(env_var, "").strip()
            if not key:
                return None
    return instance

def _register_keyed_providers() -> None:
    """惰性导入并注册 keyed provider（仅当环境变量存在时）。

    模块加载时自动调用。导入失败（模块不存在/依赖缺失）静默忽略，
    不阻塞启动。
    """
    for env_var, module_name, provider_cls in [
        ("QWEATHER_KEY", "weather_providers.qweather", "QWeatherProvider"),
        ("OWM_KEY", "weather_providers.openweather", "OpenWeatherProvider"),
        ("SENIVERSE_KEY", "weather_providers.seniverse", "SeniverseProvider"),
    ]:
        if os.environ.get(env_var, "").strip():
            try:
                mod = importlib.import_module(module_name)
                cls = getattr(mod, provider_cls)
                _PROVIDER_REGISTRY[cls.name] = cls
            except (ImportError, AttributeError):
                pass


# 模块加载时惰性注册 keyed provider
_register_keyed_providers()

def _resolve_coords(cache: dict | None, location: str) -> tuple[float | None, float | None]:
    """从缓存或 geocode 解析坐标。返回 (lat, lon) 或 (None, None)。"""
    if cache and cache.get("location") == location:
        lat = cache.get("latitude")
        lon = cache.get("longitude")
        if lat is not None and lon is not None:
            return lat, lon
    coords = _geocode(location)
    return coords if coords else (None, None)


def _try_provider(
    provider: WeatherProvider | None,
    lat: float,
    lon: float,
    config: dict,
    role: str,
    primary_data: dict | None = None,
) -> dict | None:
    """调用单个 provider，通过校验则返回数据。

    - provider 不可用（keyed 源缺少环境变量）→ 返回 None
    - API 成功 + 校验通过 → 写缓存，返回数据（suspicious=False）
    - API 成功 + 校验不通过：
        - role=="primary" → 返回 None（让管道走 fallback）
        - role=="fallback" → 写缓存，返回数据 + suspicious=True
        - role=="fallback" + primary_data 存在 → 调用 _cross_validate() 交叉校验
    - API 失败 → 返回 None
    """
    if provider is None:
        return None

    try:
        data = provider.fetch(lat, lon)
    except Exception:
        return None

    if data is None:
        return None

    suspicious = _validate_weather(data, config.get("validation"))

    if suspicious and role == "primary":
        # 主力源可疑 → 留给 fallback
        _LAST_DEBUG_STATE.update(
            cache_state=f"{provider.name}-可疑-待交叉校验", api_state="正常"
        )
        return None

    # 交叉校验（仅 fallback 角色 + 有 primary 数据时执行）
    cross_validated = False
    if role == "fallback" and primary_data is not None:
        if _cross_validate(primary_data, data):
            cross_validated = True
            _LAST_DEBUG_STATE.update(
                cache_state=f"{provider.name}-双源一致", api_state="正常"
            )
        else:
            _LAST_DEBUG_STATE.update(
                cache_state=f"{provider.name}-交叉校验不一致",
                api_state="正常",
                degradation_reason="交叉校验失败：两源天气码或温差超出阈值",
            )

    # 组装完整数据
    now_iso = datetime.now(timezone.utc).isoformat()
    full_data = {
        "location": config.get("location", "").strip(),
        "latitude": lat,
        "longitude": lon,
        "weather_code": data["weather_code"],
        "temperature": data["temperature"],
        "humidity": data["humidity"],
        "wind_speed": data["wind_speed"],
        "fetched_at": now_iso,
        "suspicious": suspicious,
        "cross_validated": cross_validated,
        "source": provider.name,
    }

    try:
        _write_cache(None, full_data)
    except Exception:
        pass

    # 仅在未通过交叉校验设置 debug 状态时更新
    if not cross_validated and not (role == "fallback" and primary_data is not None):
        _LAST_DEBUG_STATE.update(
            cache_state=f"{provider.name}-{'可疑' if suspicious else '正常'}",
            api_state="正常",
        )
    return full_data


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
    """获取天气原始数据（provider 调度 + 缓存 + 校验 + fallback）。

    _weather_context 和 _weather_context_for_narrative 均调用此函数。

    Returns:
        dict with temperature/humidity/weather_code/wind_speed/location/source or None
    """
    location = config.get("location", "").strip()
    if not location:
        return None

    cache = _read_cache()

    # ── 缓存命中路径 ──
    if not _should_refresh(cache, config, location):
        if "suspicious" not in cache:
            cache["suspicious"] = _validate_weather(cache, config.get("validation"))
        if "source" not in cache:
            cache["source"] = "openmeteo"
        _LAST_DEBUG_STATE.update(cache_state="有效-跳过", api_state="未调用")
        return cache

    # ── API 刷新路径（provider 调度管道）──
    providers_cfg = config.get("providers", {})
    primary_name = providers_cfg.get("primary", "openmeteo")
    fallback_name = providers_cfg.get("fallback", "wttr")

    primary = _get_provider(primary_name)
    fallback = _get_provider(fallback_name)

    # 解析坐标（fail-open：geocode 异常不阻断管道）
    try:
        lat, lon = _resolve_coords(cache, location)
    except Exception:
        lat, lon = None, None

    if lat is None:
        if cache and cache.get("location") == location:
            if "source" not in cache:
                cache["source"] = "openmeteo"
            _LAST_DEBUG_STATE.update(cache_state="失败-回退缓存", api_state="失败")
            return cache
        _LAST_DEBUG_STATE.update(cache_state="无缓存", api_state="失败")
        return None

    # ── 主力源 ──
    result = _try_provider(primary, lat, lon, config, "primary")
    if result:
        return result

    # 主力源可疑或失败 → 获取原始数据用于交叉校验
    primary_raw = None
    if primary:
        try:
            primary_raw = primary.fetch(lat, lon)
        except Exception:
            pass

    # ── 备用源（含交叉校验）──
    result = _try_provider(fallback, lat, lon, config, "fallback", primary_raw)
    if result:
        return result

    # ── 最终回退 ──
    if cache:
        cache["suspicious"] = True
        if "source" not in cache:
            cache["source"] = "openmeteo"
        _LAST_DEBUG_STATE.update(cache_state="失败-回退缓存", api_state="双源失败")
        return cache

    _LAST_DEBUG_STATE.update(cache_state="无缓存", api_state="双源失败")
    return None


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
