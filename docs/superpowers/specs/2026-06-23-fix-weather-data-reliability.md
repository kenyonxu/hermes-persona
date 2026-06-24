# SPEC: 天气数据可靠性修复

> 日期：2026-06-23 | 状态：Draft | 分支：`fix/weather-data-reliability`
> 诊断文档：`docs/dev/weather-diagnosis-2026-06-23.md`（第七节）
> 设计 spec（天气模块原设计）：`docs/superpowers/specs/2026-06-05-weather-module-design.md`

---

## 1. 问题概述

天气模块 v1 已上线运行，但存在四类数据可靠性缺陷，在 live profile
（`~/.hermes/profiles/zhihui/`）中实际触发：

| # | 缺陷 | 现场证据 | 严重程度 |
|---|------|----------|:---:|
| A | Open-Meteo 对深圳持续返回雷暴码（code=95），实际无雷暴 | live 缓存 `weather_code=95, wind_speed=10`（风力仅 2 级），6/22 早间 + 6/23 晚间两次复现 | 🔴 P0 |
| B | `_fetch_weather` 字段缺失时静默默认为 0，`weather_code` 缺失变成「晴」 | 代码 [weather.py:213-218](../../weather.py:213) | 🔴 P1 |
| C | debug 摘要在注入后重读缓存，刚刷新的缓存被标为「有效-跳过」 | 代码 [injector.py:1422-1436](../../injector.py:1422) | 🟡 P2 |
| D | API 返回 `weather_code: null` 时穿透到格式化，注入「未知 🌡」无降级提示 | `_weather_code_to_cn(None)` 走 fallback | 🟡 P2 |

诊断报告中的「缓存 17 天未更新」（原问题 #1）经核实为**误诊**——指向了仓库
的缓存文件而非 live profile 的缓存，运行时缓存刷新正常，不在本 SPEC 范围内。

---

## 2. 修复目标

1. **P0**：检测 Open-Meteo 雷暴码误报（雷暴码 + 低风力 = 逻辑不自洽），在注入
   时标记「（天气数据可能不准确）」，不阻断注入
2. **P1**：`_fetch_weather` 字段缺失/None 时返回 None，走 `_get_weather_data`
   的缓存回退路径，杜绝静默零值失真
3. **P2**：debug 摘要在注入时采集缓存/API 状态，不再事后重读缓存
4. **P2**：API 返回 null 值时与字段缺失同等处理（被 P1 修复覆盖）

**不在本 SPEC 范围**：多数据源（和风天气）接入、`_write_cache` 防御性硬化、
缓存并发锁——这些是后续优化，当前 fail-open 机制已足够。

---

## 3. 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 校验层位置 | `_validate_weather()`，独立纯函数 | 遵循 `_should_refresh()` 模式：纯函数 + 可独立测试 |
| 校验触发时机 | `_get_weather_data()` 中 API 返回后、写缓存前 | 既能标记新数据，也能在缓存回退时复检旧数据 |
| 可疑数据处理 | 标记但注入，追加「（天气数据可能不准确）」 | fail-open 原则：宁可标注可疑也不阻断天气上下文 |
| 字段校验方式 | 显式检查 `is not None`，移除 `.get(key, 0)` 默认值 | 源头拦截，让 None/缺失走 API 失败路径 |
| debug 采集方式 | 在 `_weather_context()` 调用点用模块级变量传递状态 | 避免 `inject_context()` 与 weather 模块的状态耦合 |
| 配置开关 | `weather.validation` 子节，可逐条禁用规则 | 遵循模块独立开关哲学，允许高级用户调校 |

---

## 4. 数据流变更

### 4.1 `_get_weather_data()` 新增校验环节

```
_get_weather_data(config)
  │
  ├─ location 为空 → 返回 None
  ├─ 读缓存
  ├─ _should_refresh() → False → 返回缓存（新增：附带 _validate_weather 结果）
  │
  ├─ _should_refresh() → True → 调 API
  │   ├─ geocode → (lat, lon)
  │   ├─ _fetch_weather() → dict（P1：字段缺失→返回 None→回退缓存）
  │   ├─ 组装 full_data
  │   └─ ✦ _validate_weather(full_data) → 标记 suspicious
  │
  ├─ 写缓存（full_data + suspicious 标记持久化）
  └─ 返回 full_data
```

### 4.2 校验规则（`_validate_weather`）

纯函数，输入天气数据 dict + 校验配置，返回 `suspicious: bool`：

| 规则 | 条件 | 判定 |
|------|------|------|
| 雷暴风力矛盾 | `weather_code in (95,96,99)` 且 `wind_speed < 12`（< 风力 3 级） | suspicious=True |
| 天气码无效 | `weather_code is None` 或不在 0-99 范围 | suspicious=True |
| 温度异常缺失 | `temperature is None` | suspicious=True |

`suspicious` 标记写入缓存（`"suspicious": true`），供格式化函数读取。

### 4.3 格式化输出变更

`_format_weather` 和 `_format_weather_narrative` 新增 `suspicious` 参数：

```
# 正常
🌤 深圳 晴 26°C

# 可疑
🌤 深圳 雷暴 28°C（天气数据可能不准确）
```

转译模式同理：
```
# 正常
当地天气：晴，26°C。

# 可疑
当地天气：雷暴，28°C（天气数据可能不准确）。
```

---

## 5. 详细改动

### 5.1 `weather.py` — `_fetch_weather` 字段完整性校验（P1 + P2）

```python
def _fetch_weather(lat: float, lon: float) -> dict | None:
    """Open-Meteo 天气 API → dict，字段缺失返回 None。"""
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
            # P1: 任一字段缺失或 None → 视为 API 失败
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
```

关键变更：`.get(key, 0)` → 显式 `current[key]` + 前置完整性检查。

### 5.2 `weather.py` — 新增 `_validate_weather`（P0）

```python
_THUNDERSTORM_CODES = (95, 96, 99)
# 雷暴通常伴随阵风（≥ 风力 3 级 = 12 km/h）
_MIN_THUNDERSTORM_WIND_KMH = 12


def _validate_weather(data: dict, validation_cfg: dict | None = None) -> bool:
    """校验天气数据逻辑自洽性。

    返回 True 表示数据可疑（suspicious）。校验规则可通过 validation_cfg
    逐条禁用。纯函数，不修改输入 data。

    规则：
    - 雷暴码 + 风力 < 12 km/h → 可疑（模型可能误判对流活动范围）
    - weather_code is None 或越界 → 可疑
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
```

### 5.3 `weather.py` — `_get_weather_data` 集成校验

在组装 `full_data` 后、写缓存前插入校验：

```python
        full_data = {
            "location": location,
            "latitude": lat,
            "longitude": lon,
            "weather_code": weather["weather_code"],
            "temperature": weather["temperature"],
            "humidity": weather["humidity"],
            "wind_speed": weather["wind_speed"],
            "fetched_at": now_iso,
            "suspicious": _validate_weather(weather, config.get("validation")),
        }
```

缓存命中路径同样标记：
```python
    if not _should_refresh(cache, config, location):
        # 缓存可能无 suspicious 字段（旧缓存）→ 补校验
        if "suspicious" not in cache:
            cache["suspicious"] = _validate_weather(cache, config.get("validation"))
        return cache
```

### 5.4 `weather.py` — 格式化函数追加可疑标记

```python
def _format_weather(data: dict, detail: str, label: str) -> str:
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
```

`_format_weather_narrative` 同理追加 suffix。

### 5.5 `injector.py` — debug 摘要状态采集修复（P2）

**问题**：当前在注入流程后重读缓存判断 `_should_refresh`，时序导致误报。

**方案**：在 `_weather_context()` 调用时采集状态，通过模块级变量传递。

`weather.py` 新增：
```python
# 模块级状态缓存，供 debug 摘要读取
_LAST_DEBUG_STATE: dict[str, str] = {}


def _get_debug_state() -> dict[str, str]:
    """返回上次 _weather_context/_for_narrative 调用的 debug 状态。"""
    return dict(_LAST_DEBUG_STATE)
```

`_get_weather_data` 中在关键分支记录状态：
```python
    if not _should_refresh(cache, config, location):
        _LAST_DEBUG_STATE.update(cache_state="有效-跳过", api_state="未调用")
        ...
    # API 成功后
    _LAST_DEBUG_STATE.update(cache_state="已刷新", api_state="正常")
    # API 失败回退
    _LAST_DEBUG_STATE.update(cache_state="失败-回退缓存", api_state="失败")
```

`injector.py` [injector.py:1422](../../injector.py:1422) 改为读取该状态：
```python
            if weather_injected:
                from weather import _get_debug_state
                weather_debug = _get_debug_state()
                weather_debug["injected"] = "true"
            else:
                weather_debug = {
                    "cache_state": "API失败", "api_state": "失败", "injected": "false",
                }
```

---

## 6. 配置变更

`persona-config.json` 的 `weather` 节新增 `validation` 子节（可选）：

```json
{
  "weather": {
    "location": "深圳",
    "detail": "brief",
    "cache_ttl_minutes": 30,
    "label": "🌤",
    "validation": {
      "thunderstorm_wind_check": true
    }
  }
}
```

`validation` 缺省时全部规则启用（安全默认）。`thunderstorm_wind_check` 是当前
唯一可配置规则，后续扩展时新增 key。

---

## 7. 缓存结构变更

`weather_cache.json` 新增 `suspicious` 字段：

```json
{
  "location": "深圳",
  "latitude": 22.54554,
  "longitude": 114.0683,
  "weather_code": 95,
  "temperature": 27.9,
  "humidity": 91,
  "wind_speed": 10.0,
  "fetched_at": "2026-06-23T14:55:35+00:00",
  "suspicious": true
}
```

旧缓存（无 `suspicious` 字段）在读取时由 `_get_weather_data` 补充校验，
向后兼容。

---

## 8. 文件改动清单

| 文件 | 操作 | 改动量 | 说明 |
|------|------|--------|------|
| `weather.py` | 修改 | ~60 行 | `_validate_weather` 新增、`_fetch_weather` 字段校验、格式化追加 suffix、debug 状态采集、`_get_debug_state` |
| `injector.py` | 修改 | ~15 行 | debug 摘要改为读 `_get_debug_state()`，删除事后重读缓存逻辑 |
| `persona-config.json` | 修改 | ~4 行 | `weather` 节新增 `validation` 子节（仓库模板） |
| `tests/test_weather.py` | 修改 | ~50 行 | `_validate_weather` 测试、`_fetch_weather` 缺失字段测试、格式化 suffix 测试、debug 状态测试 |
| `tests/test_injector.py` | 修改 | ~15 行 | debug 摘要天气状态准确性测试 |

**不修改**：`__init__.py`、`config.py`、`guard.py`、`locales/`、`dynamic_rules.py`。

---

## 9. 测试策略

### 9.1 `_validate_weather` 纯函数测试（新增）

| 场景 | 输入 | 期望 |
|------|------|------|
| 雷暴 + 低风力 | code=95, wind=10 | suspicious=True |
| 雷暴 + 正常风力 | code=95, wind=20 | suspicious=False |
| 雷暴风力检查禁用 | code=95, wind=10, cfg=`{"thunderstorm_wind_check": false}` | suspicious=False |
| code=None | code=None | suspicious=True |
| code 越界 | code=999 | suspicious=True |
| 温度 None | temperature=None | suspicious=True |
| 正常数据 | code=0, temp=26, wind=12 | suspicious=False |

### 9.2 `_fetch_weather` 字段校验测试（新增）

| 场景 | mock API 返回 | 期望 |
|------|---------------|------|
| 字段完整 | 正常 current 对象 | 返回 dict |
| weather_code 缺失 | current 无 `weather_code` key | 返回 None |
| weather_code 为 null | `"weather_code": null` | 返回 None |
| temperature 缺失 | current 无 `temperature_2m` | 返回 None |

### 9.3 格式化 suffix 测试（新增）

| 场景 | 输入 | 期望输出 |
|------|------|----------|
| 正常 brief | code=0, suspicious=False | `🌤 深圳 晴 26°C` |
| 可疑 brief | code=95, suspicious=True | `🌤 深圳 雷暴 28°C（天气数据可能不准确）` |
| 正常 narrative | code=0, suspicious=False | `晴，26°C` |
| 可疑 narrative | code=95, suspicious=True | `雷暴，28°C（天气数据可能不准确）` |

### 9.4 debug 状态测试（新增）

| 场景 | mock | 期望 `_get_debug_state()` |
|------|------|--------------------------|
| 缓存有效 | `_should_refresh`→False | `cache_state="有效-跳过"` |
| API 刷新成功 | API 正常返回 | `cache_state="已刷新", api_state="正常"` |
| API 失败回退 | API 异常 + 有旧缓存 | `cache_state="失败-回退缓存"` |

### 9.5 回归测试

现有 70 个 weather 测试全部应保持通过（`_format_weather` 签名变更需更新
现有测试，追加 `suspicious` 字段到测试数据 dict 中）。

---

## 10. 验收标准

1. live profile（深圳）获取天气后，若 code=95 且 wind<12，注入文本包含
   「（天气数据可能不准确）」
2. Open-Meteo 返回字段缺失时，天气回退到旧缓存而非注入「晴 0°C」
3. debug 摘要准确反映本轮实际行为（刷新→「已刷新」，缓存命中→「有效-跳过」）
4. 旧缓存（无 `suspicious` 字段）读取时自动补校验，不报错
5. `python -m pytest tests/ -v` 全部通过（含新增测试）
6. 验证命令：
   ```bash
   # 清缓存触发刷新，检查新缓存含 suspicious 字段
   rm state/weather_cache.json
   python -c "from weather import _weather_context; print(_weather_context({'location':'深圳','detail':'brief','label':'🌤'}))"
   # 预期输出包含或不含「（天气数据可能不准确）」取决于实际 code/wind
   ```

---

## 11. 风险与限制

| 风险 | 缓解 |
|------|------|
| 风力阈值 12 km/h 可能误判真实雷暴 | `validation.thunderstorm_wind_check` 可配置关闭；阈值集中为常量便于调校 |
| `_validate_weather` 规则不足（其他误报类型） | 规则列表可扩展，当前覆盖最痛点（雷暴误报）；多数据源是长期方案 |
| 模块级 `_LAST_DEBUG_STATE` 非线程安全 | 与现有 `state/` 文件缓存一致，单会话模型下可接受；后续统一缓存层解决 |
| 格式化签名变更影响现有测试 | `suspicious` 从 data dict 读取，有默认值 False，最小化破坏 |

---

## 12. 后续扩展（不在本 SPEC 范围）

- 多数据源 fallback（和风天气 API）——`_validate_weather` 为其提供触发点
- `_write_cache` OSError 日志化（P3 防御性硬化）
- 缓存并发读写锁——统一缓存层
- 更多校验规则（如温度/湿度季节合理性、日变化幅度）
