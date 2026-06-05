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
| 注入时机 | 每轮检查，条件注入 | 缓存过期或 location 变更时重新获取 API，缓存有效时每轮持续注入 |
| 模块归属 | 独立模块 | `_MODULE_REGISTRY` 中注册 `weather` |
| 代码组织 | 独立文件 | `weather.py`，遵循 variance.py / expression_vector.py 模式 |
| 转译支持 | 完整支持 | `_assemble_narrative()` 新增天气参数 |

## 3. 配置结构

### 3.1 开关机制

天气模块在 `_MODULE_REGISTRY` 中 `"default": False`。用户必须在 `modules` 字典中显式设置 `"weather": true` 才能启用。由 `_is_enabled(modules, "weather")` 裁决，与现有 `time`、`kanban` 等模块的开关方式一致。

### 3.2 `modules` 条目

```json
{
  "hermes-persona": {
    "modules": {
      "weather": true
    }
  }
}
```

### 3.3 `weather` 配置节

```json
{
  "hermes-persona": {
    "weather": {
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
| `location` | string | "" | 城市名（中文或英文），Open-Meteo geocoding API 支持。为空时模块不注入 |
| `detail` | string | "brief" | `"brief"` → `🌤 北京 晴 26°C`；`"full"` → `🌤 北京 晴 26°C 湿度45% 风力3级` |
| `cache_ttl_minutes` | int | 30 | 文件缓存有效期（分钟） |
| `label` | string | "🌤" | 注入前缀 emoji/标签 |

### 3.4 `_MODULE_REGISTRY` 条目

```python
"weather": {
    "description": "天气上下文注入",
    "default": False,        # 默认关闭，需在 modules 中显式开启
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
   GET https://api.open-meteo.com/v1/forecast?latitude={lat}&lon={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m
   ```
   返回 `{current: {temperature_2m (°C), relative_humidity_2m (%), weather_code (WMO), wind_speed_10m (km/h)}}`

### 4.2 每轮缓存判断流程

```
_weather_context(config) → str | None
  │
  ├─ location 为空 → 返回 None
  │
  ├─ 读取 state/weather_cache.json
  │   ├─ location 变更 → 清除坐标缓存，走 API
  │   ├─ 缓存有效（未过期）→ 从缓存格式化 → 返回格式化字符串
  │   └─ 缓存过期或不存在 → 走 API
  │
  ├─ API 调用
  │   ├─ 无坐标缓存 → geocoding API（获取坐标 + 缓存坐标）
  │   ├─ weather API → 天气数据
  │   ├─ 写入缓存文件
  │   └─ 返回格式化字符串
  │
  └─ 任何 API/IO 失败 → 返回 None（fail-open，不阻断注入链）
```

**设计要点**：缓存有效时直接从缓存格式化并返回——不调用 API 做 weather_code 比较。API 仅在缓存过期/location 变更/无缓存时调用。在 TTL 窗口内，天气上下文随每轮持续注入（与 time 模块行为一致），不会只注入一次后消失。

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

缓存包含坐标字段，避免每次 geocoding（除非 location 变更）。`wind_speed` 存储原始值（km/h），格式化时转换为 Beaufort 风力等级。

### 4.4 风力等级转换

Open-Meteo 返回 `wind_speed_10m`（km/h），`full` 模式下需转换为中文"风力 N 级"（Beaufort scale）：

| 风速 (km/h) | Beaufort | 中文描述 |
|-------------|----------|---------|
| 0-1 | 0 | 无风 |
| 1-5 | 1 | 微风 |
| 6-11 | 2 | 轻风 |
| 12-19 | 3 | 软风 |
| 20-28 | 4 | 和风 |
| 29-38 | 5 | 清风 |
| 39-49 | 6 | 强风 |
| 50-61 | 7 | 劲风 |
| 62-74 | 8 | 大风 |
| 75-88 | 9 | 烈风 |
| 89-102 | 10 | 狂风 |
| 103-117 | 11 | 暴风 |
| ≥118 | 12 | 飓风 |

`brief` 模式不输出风力信息。

### 4.5 WMO Weather Code 映射

Open-Meteo 返回 WMO 天气码，需映射为中文描述。未列出的码回退为 `"未知"` + 默认图标 `🌡`：

| WMO Code | 中文 | 图标 |
|----------|------|------|
| 0 | 晴 | ☀️ |
| 1, 2, 3 | 多云 | ⛅ |
| 45, 48 | 雾 | 🌫 |
| 51, 53, 55 | 毛毛雨 | 🌧 |
| 56, 57 | 冻毛毛雨 | 🌧 |
| 61, 63, 65 | 雨 | 🌧 |
| 66, 67 | 冻雨 | 🌧 |
| 71, 73, 75 | 雪 | 🌨 |
| 77 | 雪粒 | 🌨 |
| 80, 81, 82 | 阵雨 | 🌦 |
| 85, 86 | 阵雪 | 🌨 |
| 95, 96, 99 | 雷暴 | ⛈ |
| *其他* | 未知 | 🌡 |

### 4.6 HTTP 请求

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

天气模块每轮都执行 `_weather_context()`，完整注入行为：

| 场景 | 行为 |
|------|------|
| 首次调用（无缓存） | API 获取 → 写缓存 → 注入天气 |
| 缓存有效（未过期） | 从缓存格式化 → 注入天气 |
| 缓存过期 | API 重新获取 → 更新缓存 → 注入天气 |
| location 变更 | 清除旧坐标 → 重新 geocoding → 获取天气 → 注入 |
| API 失败（有旧缓存） | 使用旧缓存数据 → 注入天气（过期缓存作为 fallback） |
| API 失败（无缓存） | 返回 None（本轮不注入，不阻断后续模块） |
| location 为空 | 返回 None（未配置则不注入） |

**与 time 模块一致**：天气在每轮对话中持续可见。TTL 窗口内使用缓存数据，过期后自动刷新。

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

天气描述自然融入时间行。根据 `weather.detail` 模式输出不同：

**brief 模式转译：**
```
现在时间是：周五，10:30。当地天气：晴，26°C。☕ 上午——照常陪主人闲聊即可。
```

**full 模式转译：**
```
现在时间是：周五，10:30。当地天气：晴，26°C，湿度45%，风力3级。☕ 上午——照常陪主人闲聊即可。
```

当 `weather_desc` 为 None 时不输出天气段落。

### 6.3 weather.py 双输出函数

| 函数 | 输出 | 用途 |
|------|------|------|
| `_weather_context(config)` | `🌤 北京 晴 26°C` | 直接注入模式 |
| `_weather_context_for_narrative(config)` | `晴，26°C，湿度45%` | translate 转译模式 |

两个函数均调用同一个内部函数 `_get_weather_data(config)` 获取原始数据（共享缓存+API逻辑），仅格式化不同。

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
      缓存: 有效-跳过 / 已过期-刷新 / 无缓存-新建 / 失败-回退
      API: 未调用(缓存有效) / 正常 / 失败
  ...
```

## 8. 文件改动清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `weather.py` | **新建** | 天气模块核心：API 调用、缓存管理、格式化 |
| `injector.py` | 修改 | 导入 weather 模块（`from weather import _weather_context, _weather_context_for_narrative`），注册到 `_MODULE_REGISTRY`，添加注入调用点，更新 `_assemble_narrative()` 签名和实现，更新 `_debug_summary()` |
| `persona-config.json` | 修改 | 仓库根目录模板文件，新增 `modules.weather` 和 `weather` 配置节。用户需在各自 profile 的配置中同步添加 |
| `locales/zh.json` | 修改 | 新增天气相关 locale 字符串 |
| `locales/en.json` | 修改 | 同上英文版本 |
| `tests/test_weather.py` | **新建** | 天气模块单元测试 |
| `tests/test_injector.py` | 修改 | 补充天气注入集成测试 |
| `tests/conftest.py` | 可能修改 | 新增天气相关 fixtures（临时 state 目录等） |

**注意**：`__init__.py` 无需修改。遵循现有模式（`variance.py` / `expression_vector.py`），`injector.py` 直接从 `weather` 模块导入。

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
        "🌤 北京 晴 26°C" or None（API失败且无缓存/未配置location）
    """

def _weather_context_for_narrative(config: dict) -> str | None:
    """获取天气上下文字符串（转译格式）。

    Returns:
        "晴，26°C，湿度45%" or None
    """

# 内部共享函数
def _get_weather_data(config: dict) -> dict | None:
    """获取天气原始数据（共享缓存+API逻辑）。
    
    _weather_context 和 _weather_context_for_narrative 均调用此函数。
    
    Returns:
        dict with temperature/humidity/weather_code/wind_speed/location or None
    """

def _geocode(location: str) -> tuple[float, float] | None:
    """城市名 → (lat, lon)，失败返回 None"""

def _fetch_weather(lat: float, lon: float) -> dict | None:
    """Open-Meteo 天气 API → dict with temperature/humidity/weather_code/wind_speed"""

def _weather_code_to_cn(code: int) -> str:
    """WMO 天气码 → 中文描述，未知码回退 "未知"（纯函数，可直接测试）"""

def _wind_speed_to_beaufort(kmh: float) -> int:
    """风速 km/h → Beaufort 等级（0-12），纯函数"""

def _format_weather(data: dict, detail: str, label: str) -> str:
    """数据 → 直接注入格式字符串"""

def _format_weather_narrative(data: dict, detail: str) -> str:
    """数据 → 转译格式字符串（不含 emoji label，不含城市名）"""

def _read_cache(cache_path: Path) -> dict | None:
    """读缓存文件，解析失败返回 None"""

def _write_cache(cache_path: Path, data: dict) -> None:
    """写缓存文件，IO 失败静默忽略"""

def _should_refresh(cache: dict, config: dict, location: str) -> bool:
    """判断是否需要刷新：过期 / location 变更 / 缓存不存在（纯函数，可直接测试）"""
```

## 10. 测试策略

### 10.1 纯函数测试（无需 mock）

| 函数 | 测试内容 |
|------|---------|
| `_weather_code_to_cn` | 各种 WMO 码映射正确性，边界值，未知码回退为"未知" |
| `_wind_speed_to_beaufort` | 各风速区间 → Beaufort 等级正确性，边界值 |
| `_format_weather` | brief/full 两种格式输出 |
| `_format_weather_narrative` | 转译格式输出，brief/full 两种 |
| `_should_refresh` | 过期/未过期/location 变更/无缓存/缓存文件损坏 的判断 |

### 10.2 Mock 测试

| 函数 | 测试场景 |
|------|---------|
| `_get_weather_data` | ① 首次调用 → API 成功 → 写入缓存 → 返回 dict |
| | ② 缓存未过期 → 从缓存返回 dict（不调 API） |
| | ③ 缓存过期 → API 成功 → 更新缓存 → 返回 dict |
| | ④ location 变更 → 重新 geocoding → 获取天气 |
| | ⑤ API 失败 + 有旧缓存 → 返回旧缓存数据（fallback） |
| | ⑥ API 失败 + 无缓存 → 返回 None（fail-open） |
| | ⑦ 缓存文件 JSON 损坏 → 视为无缓存 → 走 API |
| | ⑧ location 为空 → 返回 None |
| `_weather_context` | 正常格式化 + None 传播（从 `_get_weather_data`） |
| `_weather_context_for_narrative` | 正常格式化 + None 传播，验证转译格式 |

### 10.3 集成测试

| 函数 | 测试内容 |
|------|---------|
| `inject_context` | weather 模块开关 → 注入/不注入 |
| | translate 模式下的天气拼装（brief 和 full 两种 detail） |
| | debug compact/detailed 模式下的天气摘要 |
| | weather 模块在注入链中的位置（紧接 time 之后） |

## 11. 风险与限制

| 风险 | 缓解措施 |
|------|---------|
| Open-Meteo 服务不可用 | fail-open + 过期缓存 fallback；可后续扩展多 API |
| 国内网络波动 | 5 秒超时 + fail-open |
| Open-Meteo 免费额度（10k/天） | 每 30 分钟最多一次 API 调用，远低于限额 |
| 城市名 geocoding 失败 | 返回 None，不注入（可后续手动配置经纬度绕过） |
| 缓存文件 JSON 损坏 | `_read_cache` 解析失败返回 None → 视为无缓存，重新请求 API |
| 缓存文件并发读写 | 当前单会话运行，非线程安全可接受。后续统一缓存层中解决 |
| injector.py 继续膨胀 | 独立 `weather.py`，injector.py 只加 ~25 行调用代码 |

## 12. 后续扩展（不在本次范围）

- 统一内存缓存层（将 state/ 下的文件缓迁移到统一缓存机制，解决并发问题）
- 多 API fallback（OpenWeatherMap 等）
- 手动坐标配置（跳过 geocoding）
- 天气预报（多日预报注入）
- 自定义天气文案模板
