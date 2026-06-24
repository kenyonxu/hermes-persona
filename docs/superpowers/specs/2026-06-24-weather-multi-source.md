# SPEC: 天气多数据源

> 日期：2026-06-24 | 状态：Draft | 分支：待定
> 用户故事：`docs/dev/US-weather-multi-source.md`
> 关联 SPEC：`docs/superpowers/specs/2026-06-23-fix-weather-data-reliability.md`（P0 校验层）
> 对比测试脚本：`scripts/weather-compare/compare.py`

---

## 1. 问题概述

天气模块 v1 依赖单一数据源 Open-Meteo，存在以下痛点：

| # | 问题 | 影响 |
|---|------|------|
| A | Open-Meteo 对深圳持续返回雷暴码（code=95），实测无雷暴 | 用户看见「雷暴」误报，虽校验层可标记但无替代源 |
| B | 单一源不可用时只能回退过期缓存，无实时交叉校验能力 | API 故障时用户获取的是可能已过时的数据 |
| C | 深度用户无法选择自己信任的天气源（和风、OpenWeather 等） | 无法获取分钟级降水、灾害预警等高级数据 |
| D | 新增数据源需修改核心管道代码，无扩展点 | 每加一个源都要改 `_get_weather_data`，维护成本高 |

P0 校验层（`_validate_weather`）已能检测可疑数据并标记，但缺乏**替代数据源**来完成闭环——检测到问题后没有更好的数据可以注入。

---

## 2. 设计目标

1. **零配置默认体验**：新用户只需填写 `location`，系统自动使用 Open-Meteo（主力）+ wttr.in（交叉校验），开箱即用
2. **Provider 抽象层**：定义统一的 Provider 接口，新增数据源只需实现接口，不改核心管道
3. **深度用户可选源**：支持和风天气（qweather）、OpenWeather、心知天气（seniverse）三个 keyed 源
4. **key 不入配置文件**：所有 API key 通过环境变量传入，防止 git 误提交
5. **校验层与 provider 解耦**：`_validate_weather` 对所有源生效，不限于 Open-Meteo
6. **向后兼容**：现有 `weather.location` / `detail` / `label` / `cache_ttl_minutes` 配置不加任何字段即可正常工作

---

## 3. 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| Provider 抽象方式 | 鸭子类型协议（`WeatherProvider` 基类），无 ABC 注册 | 与项目其他模块（variance.py / expression_vector.py）风格一致，轻量无依赖 |
| 默认双源策略 | Open-Meteo（主力）+ wttr.in（交叉校验） | 两者都免费无需 key，wttr.in 对深圳实测准确 |
| 交叉校验触发条件 | `_validate_weather` 返回 suspicious=True 时自动触发 fallback | 避免每轮双 API 调用，日常只调主力源 |
| key 管理 | 环境变量 `QWEATHER_KEY` / `OWM_KEY` / `SENIVERSE_KEY` | 配置文件只存 provider 选择，key 不入文件 |
| keyed 源加载方式 | 惰性导入（首次使用时 import 对应模块） | 避免未安装可选依赖时阻塞启动 |
| provider 失败处理 | 静默降级：primary → fallback → 缓存 → None | fail-open 原则，任何源失败不阻断注入链 |
| 配置结构 | `weather.providers` 子节，缺省时使用默认双源 | 向后兼容，不填 = 自动 |
| wttr.in 数据归一化 | Provider 内部完成，对外输出统一 dict 格式 | `_get_weather_data` 无需感知源差异 |

---

## 4. 架构设计

### 4.1 Provider 抽象层

```
weather.py
  ├── WeatherProvider (协议类)
  │     • name: str               # 标识符，如 "openmeteo" / "wttr" / "qweather"
  │     • requires_key: bool      # 是否需要 API key
  │     • fetch(lat, lon) → dict | None   # 获取天气原始数据
  │     • geocode(location) → (lat, lon) | None  # 城市名→坐标
  │     • normalize(raw) → dict   # 原始响应 → 统一格式
  │
  ├── OpenMeteoProvider(WeatherProvider)     # 现有逻辑迁移
  ├── WttrProvider(WeatherProvider)          # P1 新增
  ├── QWeatherProvider(WeatherProvider)      # P3 新增
  ├── OpenWeatherProvider(WeatherProvider)   # P3 新增
  └── SeniverseProvider(WeatherProvider)     # P3 新增
```

统一输出格式（所有 provider 的 `fetch()` 返回此结构）：

```python
{
    "temperature": float,   # °C
    "humidity": float,      # %
    "weather_code": int,    # 统一为 WMO 码
    "wind_speed": float,    # km/h
}
```

> **注意：** 此格式是 Provider 的对外输出格式（`fetch()` 返回值），也是管道内部传递的"裸数据"。写入缓存和返回给 `_format_weather` 的完整结构还包含 `source`、`suspicious`、`cross_validated`、`location` 等元数据字段——具体见 §6.4 中 `full_data` 的组装。

### 4.2 wttr.in 接入细节

wttr.in 是 Igor Chubin 维护的免费命令行天气服务，无需 API key。

**API 端点：**
```
GET https://wttr.in/{lat},{lon}?format=j1
```

**响应结构（关键字段映射）：**

| wttr.in 字段 | 路径 | → 统一字段 | 转换 |
|-------------|------|-----------|------|
| 温度 | `current_condition[0].temp_C` | `temperature` | `int()` |
| 湿度 | `current_condition[0].humidity` | `humidity` | `int()` |
| 风速 | `current_condition[0].windspeedKmph` | `wind_speed` | `int()` |
| 天气码 | `current_condition[0].weatherCode` | `weather_code` | wttr.in 使用 WMO 码与其一致，**但在其响应中字段名是 `weatherCode` 且值为字符串**，需 `int()` 归一化 |

**错误处理：**
- HTTP 非 200 → 返回 None
- JSON 解析失败 → 返回 None
- `current_condition` 为空数组 → 返回 None
- 超时 5 秒 → 返回 None
- wttr.in 对无效坐标返回 404 或 HTML 错误页 → 检测 Content-Type 不是 JSON → 返回 None

**geocoding：** wttr.in 自身不提供 geocoding。Provider 的 `geocode()` 方法复用 Open-Meteo geocoding API（`geocoding-api.open-meteo.com`），这是独立于天气 API 的服务，不构成单点依赖。

### 4.3 默认零配置流程

```
用户配置:
{
  "weather": {
    "location": "深圳"
  }
}
```

内部自动行为（等价于 `providers: {primary: "openmeteo", fallback: "wttr"}`）：

```
_get_weather_data(config)
  │
  ├─ location 为空 → 返回 None
  ├─ 读缓存 → _should_refresh() → False → 返回缓存
  │
  ├─ _should_refresh() → True
  │   │
  │   ├─ 1. primary: OpenMeteoProvider.fetch(lat, lon)
  │   │   ├─ 成功 → _validate_weather(data)
  │   │   │   ├─ suspicious=False → 直接注入 ✅
  │   │   │   └─ suspicious=True →
  │   │   │       2. fallback: WttrProvider.fetch(lat, lon)
  │   │   │          ├─ 成功 → 交叉校验
  │   │   │          │   ├─ 交叉校验通过（天气码相同 **且** 温差 ≤ 5°C）→ 注入（标注「双源确认」）
  │   │   │          │   └─ 不一致 → 注入 wttr.in 数据 + 标注「来自 wttr.in」
  │   │   │          └─ 失败 → 注入 Open-Meteo + 标注「数据可能不准确」
  │   │   │
  │   │   └─ 失败 →
  │   │       2. WttrProvider.fetch(lat, lon)
  │   │          ├─ 成功 → 注入 + 标注「来自备用源」
  │   │          └─ 失败 → 回退缓存 + 标注「数据可能不准确」
  │   │
  │   └─ 写缓存 → 返回 full_data
```

**降级链：** primary → fallback → 缓存 → 注入（带标注）。绝不返回 None 只要有旧缓存或任一级成功。

### 4.4 深度用户可选源配置

```json
{
  "weather": {
    "location": "深圳",
    "providers": {
      "primary": "qweather",
      "fallback": "openweather"
    }
  }
}
```

支持的 provider 标识符：

| 标识符 | 需要 key？ | 环境变量 | 亮点 |
|--------|:---:|------|------|
| `openmeteo` | ❌ | — | 全球覆盖，免费 10k/天，默认主力 |
| `wttr` | ❌ | — | 免费无限制，默认 fallback |
| `qweather` | ✅ | `QWEATHER_KEY` | 国内精准，分钟级降水，免费 1k/天 |
| `openweather` | ✅ | `OWM_KEY` | 全球覆盖，免费 100 万次/月 |
| `seniverse` | ✅ | `SENIVERSE_KEY` | 气象局授权，无限调用 |

**key 检查逻辑：**
- `provider.requires_key == True` 时，检查对应环境变量
- 环境变量不存在或为空 → 该 provider 不可用，**静默回退到默认 openmeteo**
- 环境变量存在 → 正常调用
- 不检查 key 有效性（不做预验证调用），由 API 返回错误自然触发降级

**`providers` 缺省行为：**
- 不填 → `primary: "openmeteo"`, `fallback: "wttr"`（默认零配置）
- 只填 `primary` → fallback 自动设为 `wttr`
- 只填 `fallback` → primary 保持 `openmeteo`

### 4.5 `_validate_weather` 与多源集成点

校验层独立于 provider，位置不变——在 `_get_weather_data` 中 primary 返回后调用：

```python
# 伪代码
primary_data = primary_provider.fetch(lat, lon)
if primary_data and not _validate_weather(primary_data, config.get("validation")):
    return primary_data  # 直接注入，不触发 fallback

if primary_data and _validate_weather(primary_data, ...):
    fallback_data = fallback_provider.fetch(lat, lon)
    if fallback_data:
        # 交叉校验逻辑
        ...
```

关键原则：
- `_validate_weather` 不变，对所有 provider 输出执行相同规则
- 校验触发 fallback 的阈值不变（雷暴+低风 / code 无效 / temp None）
- keyed provider 同样走校验——付费源也可能返回异常数据

---

## 5. 配置结构变更

### 5.1 `persona-config.json` 的 `weather` 节

```json
{
  "weather": {
    "location": "深圳",
    "detail": "brief",
    "cache_ttl_minutes": 30,
    "label": "🌤",
    "validation": {
      "thunderstorm_wind_check": true
    },
    "providers": {
      "primary": "openmeteo",
      "fallback": "wttr"
    }
  }
}
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `providers` | object | `{"primary":"openmeteo","fallback":"wttr"}` | 数据源配置，缺省使用默认双源 |
| `providers.primary` | string | `"openmeteo"` | 主力源标识符 |
| `providers.fallback` | string | `"wttr"` | 备用源标识符（校验失败或主力不可用时启用） |

向后兼容：`providers` 整个节可选，缺省时完全等效于显式填写默认值。现有 `location` / `detail` / `label` / `cache_ttl_minutes` / `validation` 字段不变。

### 5.2 环境变量

| 变量名 | 对应 provider | 说明 |
|--------|--------------|------|
| `QWEATHER_KEY` | `qweather` | 和风天气 API key |
| `OWM_KEY` | `openweather` | OpenWeatherMap API key |
| `SENIVERSE_KEY` | `seniverse` | 心知天气 API key |

key 从 `os.environ.get()` 读取，不落入任何文件。仓库 `.gitignore` 已排除 `.env` 文件（如使用 dotenv 加载）。

---

## 6. 详细改动

### 6.1 `weather.py` — Provider 抽象层（P2）

新增 `WeatherProvider` 协议类（鸭子类型，不使用 ABC）：

```python
class WeatherProvider:
    """天气数据源协议。

    子类实现 fetch() 和 normalize()。geocode() 有默认实现
    （复用 Open-Meteo geocoding API）。
    """

    name: str = ""
    requires_key: bool = False

    def geocode(self, location: str) -> tuple[float, float] | None:
        """城市名 → (lat, lon)。默认使用 Open-Meteo geocoding API。"""
        # 复用现有 _geocode() 实现

    def fetch(self, lat: float, lon: float) -> dict | None:
        """获取天气原始数据 → 统一格式 dict，失败返回 None。"""
        raise NotImplementedError

    def normalize(self, raw: dict) -> dict | None:
        """Provider 原始响应 → 统一格式 dict。子类必须实现。"""
        raise NotImplementedError
```

### 6.2 `weather.py` — OpenMeteoProvider（P2 迁移）

将现有 `_geocode` / `_fetch_weather` 逻辑迁移到 `OpenMeteoProvider` 类：

```python
class OpenMeteoProvider(WeatherProvider):
    name = "openmeteo"
    requires_key = False

    def fetch(self, lat, lon):
        # 现有 _fetch_weather() 逻辑迁移至此
        ...

    def normalize(self, raw):
        # Open-Meteo 已经是统一格式，直接返回
        return raw
```

现有模块级函数 `_geocode()` 和 `_fetch_weather()` 保留为向后兼容的薄包装，内部委托给 OpenMeteoProvider。

### 6.3 `weather.py` — WttrProvider（P1）

```python
_WTTR_URL = "https://wttr.in"

class WttrProvider(WeatherProvider):
    name = "wttr"
    requires_key = False

    def fetch(self, lat: float, lon: float) -> dict | None:
        """wttr.in API → 统一格式 dict。"""
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
        """wttr.in JSON → 统一格式。"""
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
```

### 6.4 `weather.py` — `_get_weather_data` 改造（P2）

核心管道从硬编码调用改为通过 provider 调度：

```python
def _get_weather_data(config: dict) -> dict | None:
    """获取天气原始数据（provider 调度 + 缓存 + 校验 + fallback）。"""
    location = config.get("location", "").strip()
    if not location:
        return None

    cache = _read_cache()
    if not _should_refresh(cache, config, location):
        if "suspicious" not in cache:
            cache["suspicious"] = _validate_weather(cache, config.get("validation"))
        if "source" not in cache:
            cache["source"] = "openmeteo"
        _LAST_DEBUG_STATE.update(cache_state="有效-跳过", api_state="未调用")
        return cache

    # 解析 provider 配置
    providers_cfg = config.get("providers", {})
    primary_name = providers_cfg.get("primary", "openmeteo")
    fallback_name = providers_cfg.get("fallback", "wttr")

    primary = _get_provider(primary_name)
    fallback = _get_provider(fallback_name)

    # 获取坐标（复用缓存坐标或 geocode）
    lat, lon = _resolve_coords(cache, location)

    if lat is None:
        _LAST_DEBUG_STATE.update(cache_state="失败-回退缓存" if cache else "无缓存", api_state="失败")
        return cache if cache else None

    # 主力源
    result = _try_provider(primary, lat, lon, config, "primary")
    if result:
        return result

    # 主力源可疑或失败 → 获取原始数据用于交叉校验
    primary_raw = None
    if primary and result is None:
        try:
            primary_raw = primary.fetch(lat, lon)
        except Exception:
            pass

    # 备用源（含交叉校验）
    result = _try_provider(fallback, lat, lon, config, "fallback", primary_raw)
    if result:
        return result

    # 最终回退
    if cache:
        cache["suspicious"] = True
        if "source" not in cache:
            cache["source"] = "openmeteo"
        _LAST_DEBUG_STATE.update(cache_state="失败-回退缓存", api_state="双源失败")
        return cache

    _LAST_DEBUG_STATE.update(cache_state="无缓存", api_state="双源失败")
    return None
```

`_cross_validate` 交叉校验函数：

```python
def _cross_validate(primary_data: dict, fallback_data: dict) -> bool:
    """交叉校验两个数据源是否一致。

    对比 weather_code 是否相同 + 温差是否在 5°C 内。
    两个条件都满足（AND）才返回 True（两源一致）。
    """
    code_match = primary_data["weather_code"] == fallback_data["weather_code"]
    temp_close = abs(primary_data["temperature"] - fallback_data["temperature"]) <= 5
    return code_match and temp_close
```

`_try_provider` 辅助函数：

```python
def _try_provider(provider, lat, lon, config, role, primary_data=None):
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
        _LAST_DEBUG_STATE.update(cache_state=f"{provider.name}-可疑-待交叉校验", api_state="正常")
        return None

    # 交叉校验（仅 fallback 角色 + 有 primary 数据时执行）
    cross_validated = False
    if role == "fallback" and primary_data is not None:
        if _cross_validate(primary_data, data):
            cross_validated = True
            _LAST_DEBUG_STATE.update(cache_state=f"{provider.name}-双源一致", api_state="正常")
        else:
            _LAST_DEBUG_STATE.update(
                cache_state=f"{provider.name}-交叉校验不一致",
                api_state="正常",
                degradation_reason="交叉校验失败：两源天气码或温差超出阈值"
            )

    # 组装完整数据
    full_data = {
        "location": config.get("location", "").strip(),
        "latitude": lat,
        "longitude": lon,
        "weather_code": data["weather_code"],
        "temperature": data["temperature"],
        "humidity": data["humidity"],
        "wind_speed": data["wind_speed"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
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
            api_state="正常"
        )
    return full_data
```

### 6.5 `weather.py` — Provider 注册与查找（P2）

```python
# Provider 注册表（标识符 → 类）
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
        env_var = instance.env_var  # 如 "QWEATHER_KEY"
        key = os.environ.get(env_var, "").strip()
        if not key:
            return None
    return instance
```

### 6.6 keyed provider 模块（P3）

独立文件组织，惰性导入：

```
weather.py                  # 核心管道 + Provider 基类 + keyless provider
weather_providers/
  __init__.py               # 空文件（包标记）
  qweather.py               # QWeatherProvider
  openweather.py            # OpenWeatherProvider
  seniverse.py              # SeniverseProvider
```

每个 keyed provider 模块提供 `register()` 函数，在 `weather.py` 初始化时调用以注册到 `_PROVIDER_REGISTRY`。

**和风天气示例（`weather_providers/qweather.py`）：**

```python
"""和风天气 provider — 需要 QWEATHER_KEY 环境变量。"""
import json
import os
import urllib.request
import urllib.parse
from weather import WeatherProvider

_QWEATHER_GEO_URL = "https://geoapi.qweather.com/v2/city/lookup"
_QWEATHER_WEATHER_URL = "https://devapi.qweather.com/v7/weather/now"


class QWeatherProvider(WeatherProvider):
    name = "qweather"
    requires_key = True
    env_var = "QWEATHER_KEY"

    def geocode(self, location):
        key = os.environ.get(self.env_var, "")
        try:
            params = urllib.parse.urlencode({"location": location, "key": key})
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

    def fetch(self, lat, lon):
        key = os.environ.get(self.env_var, "")
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

    def normalize(self, raw):
        try:
            now = raw["now"]
            # 和风天气码 → WMO 码映射
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
```

注册入口（在 `weather.py` 中惰性导入）：

```python
def _register_keyed_providers():
    """惰性导入并注册 keyed provider（仅当环境变量存在时）。"""
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
            except ImportError:
                pass
```

### 6.7 `weather.py` — `_format_weather` 增强（标注数据源）

格式化函数新增 `source` 和 `cross_validated` 信息：

```python
def _format_weather(data: dict, detail: str, label: str) -> str:
    # ... 现有逻辑 ...
    source = data.get("source", "")
    suspicious = data.get("suspicious", False)
    cross_validated = data.get("cross_validated", False)

    suffix_parts = []
    if suspicious:
        suffix_parts.append("天气数据可能不准确")
    if source and source != "openmeteo":
        suffix_parts.append(f"来源: {source}")
    if cross_validated:
        suffix_parts.append("双源确认")

    suffix = f"（{'，'.join(suffix_parts)}）" if suffix_parts else ""
    # ...
```

格式化输出示例：

```
# 默认正常
🌤 深圳 晴 26°C

# 交叉校验结果
🌤 深圳 多云 27°C（来源: wttr，双源确认）

# 可疑但回退
🌤 深圳 雷暴 28°C（天气数据可能不准确）
```

---

## 7. 缓存结构变更

`weather_cache.json` 新增 `source` 字段：

```json
{
  "location": "深圳",
  "latitude": 22.54554,
  "longitude": 114.0683,
  "weather_code": 1,
  "temperature": 27.9,
  "humidity": 85,
  "wind_speed": 14.0,
  "fetched_at": "2026-06-24T10:00:00+00:00",
  "suspicious": false,
  "source": "wttr"
}
```

旧缓存（无 `source` 字段）读取时默认视为 `"openmeteo"`，向后兼容。

---

## 8. 文件改动清单

| 文件 | 操作 | 改动量 | 说明 |
|------|------|--------|------|
| `weather.py` | 修改 | ~250 行 | Provider 基类 + OpenMeteoProvider + WttrProvider + `_get_weather_data` 改造 + provider 注册表 + `_try_provider` + `_format_weather` 增强 + 惰性导入 keyed provider |
| `weather_providers/__init__.py` | **新建** | ~3 行 | 包标记 |
| `weather_providers/qweather.py` | **新建** | ~80 行 | 和风天气 provider |
| `weather_providers/openweather.py` | **新建** | ~70 行 | OpenWeather provider |
| `weather_providers/seniverse.py` | **新建** | ~70 行 | 心知天气 provider |
| `injector.py` | 修改 | ~5 行 | debug 摘要追加 source 信息（可选优化） |
| `persona-config.json` | 修改 | ~5 行 | `weather` 节新增 `providers` 子节 |
| `tests/test_weather.py` | 修改 | ~150 行 | Provider 测试、多源 fallback 测试、交叉校验测试 |
| `tests/test_weather_providers.py` | **新建** | ~100 行 | keyed provider 测试（mock API + env var） |

**不修改**：`__init__.py`、`config.py`、`guard.py`、`locales/`。

---

## 9. 测试策略

### 9.1 Provider 纯函数测试（P2）

| 场景 | 输入 | 期望 |
|------|------|------|
| WttrProvider.normalize 正常 | wttr.in JSON 响应 | 返回统一格式 dict |
| WttrProvider.normalize 空 current_condition | `{"current_condition": []}` | 返回 None |
| WttrProvider.normalize 字段缺失 | 缺少 `temp_C` | 返回 None |
| OpenMeteoProvider.normalize | 已有格式数据 | 原样返回 |
| provider 注册表查找 "openmeteo" | `_get_provider("openmeteo")` | 返回 OpenMeteoProvider 实例 |
| provider 注册表查找 "unknown" | `_get_provider("unknown")` | 返回 None |
| keyed provider 缺 env var | `QWEATHER_KEY` 未设置 | `_get_provider("qweather")` 返回 None |

### 9.2 多源 fallback 流程测试（P1 + P2）

| 场景 | primary 结果 | fallback 结果 | 期望最终数据 |
|------|-------------|--------------|-------------|
| primary 正常 | 晴 26°C, suspicious=False | 不调用 | 注入 primary 数据，source="openmeteo" |
| primary 可疑，fallback 正常 | 雷暴 28°C, wind=10, suspicious=True | 多云 27°C | 注入 fallback 数据，source="wttr" |
| primary 失败，fallback 正常 | None（网络错误） | 晴 26°C | 注入 fallback 数据，source="wttr" |
| 双源失败，有缓存 | None | None | 注入旧缓存，suspicious=True |
| 双源失败，无缓存 | None | None | 返回 None |
| 用户选 keyed 源但缺 key | — | — | 静默回退到默认 openmeteo |

### 9.3 环境变量测试（P3）

| 场景 | 期望 |
|------|------|
| `QWEATHER_KEY` 已设置 | `_get_provider("qweather")` 返回有效实例 |
| `QWEATHER_KEY` 为空字符串 | `_get_provider("qweather")` 返回 None |
| `QWEATHER_KEY` 未设置 | `_get_provider("qweather")` 返回 None |

### 9.4 向后兼容测试

| 场景 | 期望 |
|------|------|
| 配置中无 `providers` 字段 | 行为等价于 `providers: {primary: "openmeteo", fallback: "wttr"}` |
| 配置中仅有 `location` | 完整双源 fallback 流程生效 |
| 旧缓存无 `source` 字段 | 读取时不报错，视为 "openmeteo" |
| `_weather_context` 返回值格式 | 与当前版本一致（向后兼容） |

### 9.5 回归测试

现有所有 weather 测试应全部通过（`tests/test_weather.py` 中 70+ 测试）。

---

## 10. 验收标准

1. **零配置验收**：仅配置 `"location": "深圳"`，天气正常注入。当 Open-Meteo 返回可疑数据时，自动触发 wttr.in 交叉校验
2. **交叉校验可视**：debug detailed 模式显示实际使用的数据源（`source` 字段 + `api_state`）
3. **key 隔离**：`persona-config.json` 中不含任何 API key，key 仅来自环境变量
4. **深度用户替换源**：设置 `QWEATHER_KEY` 环境变量 + `providers.primary: "qweather"` 后，天气数据来自和风
5. **优雅降级**：设置 `providers.primary: "qweather"` 但不设置 `QWEATHER_KEY` → 自动回退到 `openmeteo`，不影响注入
6. **向后兼容**：现有配置文件不加任何字段，行为与当前版本一致（除新增双源保护）
7. `python -m pytest tests/ -v` 全部通过（含新增 provider 测试）
8. 验证命令：
   ```bash
   # 默认零配置
   python -c "from weather import _weather_context; print(_weather_context({'location':'深圳','detail':'brief','label':'🌤'}))"
   # 预期：天气注入正常，source 自动选择

   # 强制双源失败验证回退
   # （mock 场景，需要通过测试覆盖）
   ```

---

## 11. 风险与限制

| 风险 | 缓解 |
|------|------|
| wttr.in 不稳定或下线 | 降级链确保 fallback → 缓存；wttr.in 已稳定运行 10+ 年 |
| wttr.in 坐标格式不一致 | 测试阶段对多个城市的坐标做对比验证 |
| keyed provider API 变更 | 每个 provider 独立 normalize() 函数，变更仅影响单个文件 |
| 双 API 调用增加延迟 | 仅 primary 可疑时才调用 fallback，日常仅一次 API 调用；两个 API 均 5 秒超时，最坏 10 秒 |
| provider 模块增加代码量 | 每个 keyed provider ~70-80 行，纯标准库无依赖；惰性导入避免启动开销 |
| 和风天气码 ≠ WMO 码 | 维护映射表，仅覆盖常见码，未知码默认为 0（晴）＋ 日志标记 |
| 环境变量泄露风险 | 明确文档强调 key 不入文件，`.gitignore` 已排除 `.env`；不实现 dotenv 自动加载（用户自行管理） |

---

## 12. 后续扩展（不在本 SPEC 范围）

- 多源交叉校验评分（贝叶斯融合）——当前仅二元对比
- IP 地理位置自动检测（无需填写 location）
- 天气预报（多日）注入
- Provider 健康度追踪（统计各源成功率，动态调整优先级）
- 自定义 provider 插件机制（用户提供 Python 文件实现 WeatherProvider）
