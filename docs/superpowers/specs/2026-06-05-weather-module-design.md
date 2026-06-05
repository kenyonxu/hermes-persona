# SPEC: 天气上下文注入模块

> 日期：2026-06-05 | 状态：Draft | 分支：develop

## 1. 概述

在 hermes-persona 插件中新增独立的 `weather` 模块，根据用户在 `persona-config.json` 中配置的 `location` 获取当地天气，并注入到每轮 LLM 调用的上下文中。与现有的 `time` 模块并列，共同提供环境感知能力。

## 2. 设计决策摘要

| 决策项 | 选择 | 说明 |
|--------|------|------|
| location 来源 | `persona-config.json` | 角色级配置，与 time 模块一致 |
| 天气 API | Open-Meteo | 免费、无需 API Key、国内可直连 |
| 注入格式 | 可配置 brief/full | `"detail"` 字段控制粒度 |
| 缓存策略 | 文件缓存 | `state/weather_cache.json`，可配置 TTL |
| 注入时机 | 每轮检查，条件注入 | 缓存过期或天气变化时才重新注入 |
| 模块归属 | 独立模块 | `_MODULE_REGISTRY` 中注册 `weather` |
| 代码组织 | 独立文件 | `weather.py`，遵循 variance.py / expression_vector.py 模式 |
| 转译支持 | 完整支持 | `_assemble_narrative()` 新增天气参数 |

## 3. 配置结构

### 3.1 `modules` 注册

```json
{
  "hermes-persona": {
    "modules": {
      "weather": true
    }
  }
}
```

### 3.2 `weather` 配置节

```json
{
  "hermes-persona": {
    "weather": {
      "enabled": true,
      "location": "北京",
      "detail": "brief",
      "cache_ttl_minutes": 30,
      "label": "🌤"
    }
  }
}
```

字段说明：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | true | 模块开关（降级时可由 modules.weather 覆盖） |
| `location` | string | "" | 城市名（中文或英文），Open-Meteo geocoding API 支持 |
| `detail` | string | "brief" | `"brief"` → `🌤 北京 晴 26°C`；`"full"` → `🌤 北京 晴 26°C 湿度45% 风力3级` |
| `cache_ttl_minutes` | int | 30 | 文件缓存有效期（分钟） |
| `label` | string | "🌤" | 注入前缀 emoji/标签 |

### 3.3 `_MODULE_REGISTRY` 条目

```python
"weather": {
    "description": "天气上下文注入",
    "default": False,        # 默认关闭，需主动开启
    "phase": 1,              # 和 time 同阶段
    "legacy_key": None,
    "legacy_path": None,
}
```

## 4. 数据流

### 4.1 API 调用链

Open-Meteo 需要经纬度，分两步调用：

1. **Geocoding API**（城市名 → 坐标）
   ```
   GET https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1&language=zh
   ```
   返回 `{results: [{latitude, longitude, name, country}]}`

2. **Weather API**（坐标 → 天气）
   ```
   GET https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m
   ```
   返回 `{current: {temperature_2m, relative_humidity_2m, weather_code, wind_speed_10m}}`

### 4.2 每轮缓存判断流程

```
_weather_context(config) → str | None
  │
  ├─ 读取 state/weather_cache.json
  │   ├─ location 变更 → 清缓存，走 API
  │   ├─ 未过期 + weather_code 未变 → 返回 None（本轮不重复注入）
  │   └─ 过期或不存在 → 走 API
  │
  ├─ API 调用
  │   ├─ 无缓存坐标 → geocoding API（获取坐标 + 缓存坐标）
  │   ├─ weather API → 天气数据
  │   ├─ 写入缓存文件
  │   └─ 返回格式化字符串
  │
  └─ 任何 API/IO 失败 → 返回 None（fail-open，不阻断注入链）
```

### 4.3 缓存文件结构 (`state/weather_cache.json`)

```json
{
  "location": "北京",
  "latitude": 39.9042,
  "longitude": 116.4074,
  "weather_code": 0,
  "temperature": 26.3,
  "humidity": 45,
  "wind_speed": 12.5,
  "fetched_at": "2026-06-05T10:30:00"
}
```

缓存包含坐标字段，避免每次 geocoding（除非 location 变更）。

### 4.4 WMO Weather Code 映射

Open-Meteo 返回 WMO 天气码，需映射为中文描述：

| WMO Code | 中文 | 图标 |
|----------|------|------|
| 0 | 晴 | ☀️ |
| 1, 2, 3 | 多云 | ⛅ |
| 45, 48 | 雾 | 🌫 |
| 51, 53, 55 | 毛毛雨 | 🌧 |
| 61, 63, 65 | 雨 | 🌧 |
| 71, 73, 75 | 雪 | 🌨 |
| 77 | 雪粒 | 🌨 |
| 80, 81, 82 | 阵雨 | 🌦 |
| 85, 86 | 阵雪 | 🌨 |
| 95, 96, 99 | 雷暴 | ⛈ |

### 4.5 HTTP 请求

- 使用 Python 标准库 `urllib`（零外部依赖）
- 超时时间：5 秒
- 异常处理：fail-open，任何网络/解析错误返回 None

## 5. 注入行为

### 5.1 注入顺序

天气模块 phase=1，紧接 time 之后：

```
inject_context() 注入顺序：
  ① _time_context()          → 🕐 2026年6月5日 周五 10:30
  ①b _weather_context()      → 🌤 北京 晴 26°C         ← 新增
  ② _inject_static_rules()   → 静态规则
  ③ _select_dynamic_rules()  → 动态规则
  ...
```

### 5.2 条件注入逻辑

天气模块每轮都执行 `_weather_context()`，但不一定每轮都产生输出：

| 场景 | 行为 |
|------|------|
| 首次调用（无缓存） | API 获取 → 写缓存 → 注入天气 |
| 缓存未过期 + 天气未变 | 返回 None（本轮不注入） |
| 缓存未过期 + 天气已变 | API 重新获取 → 更新缓存 → 注入天气 |
| 缓存过期 | API 重新获取 → 更新缓存 → 注入天气 |
| location 变更 | 清除旧坐标 → 重新 geocoding → 重新获取天气 → 注入 |
| API 失败 | 返回 None（不注入，不阻断后续模块） |
| location 为空 | 返回 None（未配置则不注入） |

### 5.3 格式化输出

**brief 模式：**
```
🌤 北京 晴 26°C
```

**full 模式：**
```
🌤 北京 晴 26°C 湿度45% 风力3级
```

## 6. Translate 转译模式

### 6.1 `_assemble_narrative()` 签名变更

新增 `weather_desc: str | None` 参数：

```python
def _assemble_narrative(
    weekday: str,
    current_time: str,
    time_slot_desc: str,
    weather_desc: str | None,          # ← 新增
    today_turn: int,
    turn_stage_hint: str | None,
    top3: list[tuple[str, float, str]],
    variance_items: list[str],
    fixed_rules: list[str],
) -> str:
```

### 6.2 转译输出格式

天气描述自然融入时间行：

```
现在时间是：周五，10:30。当地天气：晴，26°C，湿度45%。☕ 上午——照常陪主人闲聊即可。
```

当 `weather_desc` 为 None 时不输出天气段落。

### 6.3 weather.py 双输出函数

| 函数 | 输出 | 用途 |
|------|------|------|
| `_weather_context(config)` | `🌤 北京 晴 26°C` | 直接注入模式 |
| `_weather_context_for_narrative(config)` | `晴，26°C，湿度45%` | translate 转译模式 |

两个函数共享同一套缓存+API逻辑，仅格式化不同。

### 6.4 `inject_context()` 中的分支

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

## 7. Debug 摘要

### 7.1 compact 模式

```
🔧 [Debug] 本轮注入:
  ① 🕐 时间已注入
  ① 🌤 天气已注入                ← "已停用" / "未配置" / "API失败"
  ② 📜 4条静态规则
  ...
```

### 7.2 detailed 模式

```
🔧 [Debug] 本轮注入:
  ① 🕐 时间已注入
  ① 🌤 天气: 北京 晴 26°C
      缓存: 已过期 / 未过期 / 无缓存
      API: 正常 / 失败
  ...
```

## 8. 文件改动清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `weather.py` | **新建** | 天气模块核心：API 调用、缓存管理、格式化 |
| `injector.py` | 修改 | 导入 weather 模块，注册到 `_MODULE_REGISTRY`，添加注入调用点，更新 `_assemble_narrative()` 签名和实现，更新 `_debug_summary()` |
| `persona-config.json` | 修改 | 新增 `modules.weather` 和 `weather` 配置节 |
| `locales/zh.json` | 修改 | 新增天气相关 locale 字符串 |
| `locales/en.json` | 修改 | 同上英文版本 |
| `__init__.py` | 修改 | 导入 weather 模块 |
| `tests/test_weather.py` | **新建** | 天气模块单元测试 |
| `tests/test_injector.py` | 修改 | 补充天气注入集成测试 |
| `tests/conftest.py` | 可能修改 | 新增天气相关 fixtures（临时缓存目录等） |

## 9. weather.py 模块接口

```python
"""Weather context provider: Open-Meteo API + file-based cache.

Provides weather information for persona context injection.
Fail-open on any API/IO error — never blocks the injection chain.
"""

# 公开函数
def _weather_context(config: dict) -> str | None:
    """获取天气上下文字符串（直接注入格式）。

    Returns:
        "🌤 北京 晴 26°C" or None（缓存未过期/API失败/未配置）
    """

def _weather_context_for_narrative(config: dict) -> str | None:
    """获取天气上下文字符串（转译格式）。

    Returns:
        "晴，26°C，湿度45%" or None
    """

# 内部函数
def _geocode(location: str) -> tuple[float, float] | None:
    """城市名 → (lat, lon)，失败返回 None"""

def _fetch_weather(lat: float, lon: float) -> dict | None:
    """Open-Meteo 天气 API → dict with temperature/humidity/weather_code/wind_speed"""

def _weather_code_to_cn(code: int) -> str:
    """WMO 天气码 → 中文描述（纯函数，可直接测试）"""

def _format_weather(data: dict, location: str, detail: str, label: str) -> str | None:
    """数据 → 格式化字符串"""

def _format_weather_narrative(data: dict, detail: str) -> str:
    """数据 → 转译格式字符串"""

def _read_cache(cache_path: Path) -> dict | None:
    """读缓存文件，解析失败返回 None"""

def _write_cache(cache_path: Path, data: dict) -> None:
    """写缓存文件，IO 失败静默忽略"""

def _should_refresh(cache: dict, config: dict, location: str) -> bool:
    """判断是否需要刷新：过期 / location 变更"""
```

## 10. 测试策略

### 10.1 纯函数测试（无需 mock）

| 函数 | 测试内容 |
|------|---------|
| `_weather_code_to_cn` | 各种 WMO 码映射正确性，边界值 |
| `_format_weather` | brief/full 两种格式输出 |
| `_format_weather_narrative` | 转译格式输出 |
| `_should_refresh` | 过期/未过期/location 变更的判断 |

### 10.2 Mock 测试

| 函数 | 测试场景 |
|------|---------|
| `_weather_context` | ① 首次调用 → API 成功 → 写入缓存 → 返回字符串 |
| | ② 缓存未过期 → 返回 None（不注入） |
| | ③ 缓存过期 → API 成功 → 更新缓存 → 返回字符串 |
| | ④ location 变更 → 重新 geocoding → 获取天气 |
| | ⑤ API 失败 → 返回 None（fail-open） |
| | ⑥ location 为空 → 返回 None |
| `_weather_context_for_narrative` | 同上，验证返回格式为转译格式 |

### 10.3 集成测试

| 函数 | 测试内容 |
|------|---------|
| `inject_context` | weather 模块开关 → 注入/不注入 |
| | translate 模式下的天气拼装 |
| | debug compact/detailed 模式下的天气摘要 |
| | weather 模块在注入链中的位置（紧接 time 之后） |

## 11. 风险与限制

| 风险 | 缓解措施 |
|------|---------|
| Open-Meteo 服务不可用 | fail-open，不阻断注入链；可后续扩展多 API fallback |
| 国内网络波动 | 5 秒超时 + fail-open |
| 城市名 geocoding 失败 | 返回 None，不注入（可后续手动配置经纬度绕过） |
| 缓存文件损坏 | `_read_cache` 解析失败返回 None → 重新请求 API |
| injector.py 继续膨胀 | 独立 `weather.py`，injector.py 只加 ~25 行调用代码 |

## 12. 后续扩展（不在本次范围）

- 统一内存缓存层（将 state/ 下的文件缓迁移到统一缓存机制）
- 多 API fallback（OpenWeatherMap 等）
- 手动坐标配置（跳过 geocoding）
- 天气预报（多日预报注入）
- 自定义天气文案模板
