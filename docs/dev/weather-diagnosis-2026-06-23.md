# 天气模块诊断报告

> **日期**: 2026-06-23 | **诊断人**: 知惠 | **版本**: hermes-persona weather v1.x

## 一、问题现象

| # | 现象 | 发现时间 | 严重程度 |
|---|------|----------|:---:|
| 1 | `state/weather_cache.json` 停在 2026-06-05 北京数据，TTL 30min 但 **17 天未更新** | 6/22 午夜 | 🔴 |
| 2 | Open-Meteo 深圳早间返回 `code=95`（雷暴），实际大晴天 | 6/22 早 | 🟡 |

## 二、根因分析

### 2.1 缓存写静默失败

**位置**: `weather.py → _write_cache()`

```python
# 当前逻辑（简化）
def _write_cache(self, data):
    try:
        with open(cache_path, 'w') as f:
            json.dump(data, f)
    except OSError:
        pass  # ← OSError 被吞，无日志、无回退
```

**问题链**:
1. `_write_cache` 写入失败时 `OSError` 被静默吞掉
2. 后续 `_get_cached` 永远读到旧缓存（6/5 数据）
3. 每次调用 API 成功获取新数据 → 写缓存失败 → 下次又读旧缓存
4. 无限循环：API 正常 → 写失败 → 读旧数据 → 过期重调 API → 写失败 → …

**排查方向**:
- 写权限？`state/` 目录 owner 是否与运行进程一致
- 并发写入锁？Hermes cron + 手动调用是否同时写同一文件
- 磁盘空间？

### 2.2 单数据源风险

**当前**: 仅 Open-Meteo API（免费、无 key）

**Open-Meteo 已知问题**:
- 免费端点 `weather_code` 对强对流天气（雷暴、骤雨）召回偏高
- 深圳 6/22 早间：API 返回 code=95（雷暴），实际晴空万里
- 深夜时段 API 不稳定，偶发超时或空响应

**后果**:
- 天气上下文注入错误的场景触发（"外面雷暴" → 主人看到的是晴天）
- 降低用户对 persona 系统的信任度

## 三、修复方案

### 方案 A：多数据源切换（推荐）

```
WeatherProvider (抽象)
├── OpenMeteoProvider     # 保留，免费兜底
├── QWeatherProvider       # 和风天气（国内精准）
└── FallbackChain         # OpenMeteo → 和风 → 缓存兜底
```

**流程**:
1. 先调 Open-Meteo（免费）
2. 结果校验：若天气码与实际不符判断逻辑（如深圳夏季 code=95 且时间 > 10:00 → 大概率误报），fallback 到和风
3. 和风再失败 → 使用上次有效缓存（打"数据可能不准确"标记）

**代价**: 和风 API 需要 key（免费额度 1000次/天，足够）

### 方案 B：仅修缓存 + 加数据源校验（最小修改）

1. 修复 `_write_cache`：OSError 记录日志 + 重试 3 次 + 降级到 `/tmp/weather_fallback.json`
2. 加 `_validate_weather`：对 Open-Meteo 返回做基础合理性检查（如 code=95 + 小时>10 → 标为"可疑"）
3. 可疑数据注入时追加 `（天气数据可能不准确）`

**代价**: 不解决单源误报根因，只打补丁

### 推荐方案

**短期（本周）**: 方案 B — 修复缓存写入（OSError 不吞）+ 可疑标记

**中期（下周）**: 方案 A — 和风 API 接入，双源校验

## 四、影响范围

| 模块 | 影响 |
|------|------|
| `weather.py → _weather_context()` | 注入 LLM 的天气文本可能不准 |
| `state/weather_cache.json` | 缓存文件为问题现场，勿删 |
| 用户侧 | 知惠早/晚报中天气描述不准确，场景触发词（雷暴/雨天）误匹配 |

## 五、验证步骤

1. 删除 `state/weather_cache.json`，触发重新获取
2. 确认新缓存写入成功（文件 mtime 更新 + 内容为当前城市数据）
3. `python -m pytest tests/test_weather.py -v` 全部通过
4. 实际调用一次，检查注入的系统提示中天气是否与实际一致

## 六、相关文件

- `weather.py` — 天气获取 + 缓存逻辑
- `tests/test_weather.py` — 天气模块测试
- `state/weather_cache.json` — 缓存文件（问题现场）
- `docs/superpowers/specs/2026-06-05-weather-module-design.md` — 设计 spec
- `docs/superpowers/plans/2026-06-05-weather-module.md` — 实现 plan

---

# 七、深度逻辑诊断（续：基于 live profile 复勘）

> **补充时间**: 2026-06-23 23:05 | **诊断人**: Codex
>
> 第一~六节基于**仓库目录** `state/weather_cache.json` 推断问题。经核查，
> 实际运行的 live profile 位于
> `~/.hermes/profiles/zhihui/plugins/hermes-persona/`，与仓库代码逐字节相同，
> 但缓存文件指向**完全不同的路径**。以下用 live 证据修正前文结论，并补充
> 代码级新发现。

## 7.1 勘误：问题 #1「缓存 17 天未更新」指向了错误的文件

### 证据

| 路径 | location | weather_code | fetched_at (Beijing) | 年龄 |
|------|----------|:-----------:|----------------------|------|
| 仓库 `state/weather_cache.json` | 北京 | 1 | 2026-06-05 14:28 | **18 天** |
| **live** `~/.hermes/profiles/zhihui/.../state/weather_cache.json` | **深圳** | **95** | **2026-06-23 22:55** | **0.2 小时** |

live 缓存 10 分钟前刚写入，深圳数据，TTL=30min 运转正常。仓库里那份 6/5
的北京缓存是开发遗留，**运行时根本不会读到**。

### 根因：缓存路径解析

```python
# weather.py:117-118
_CACHE_DIR = Path(__file__).resolve().parent / "state"
_CACHE_FILE = _CACHE_DIR / "weather_cache.json"
```

路径相对 `weather.py` 自身位置解析。运行时加载的是 live profile 下的
`weather.py`，所以缓存落在 live profile 的 `state/`。仓库目录只是 git 工作区，
不是运行时加载点。第一节的「OSError 被吞 → 无限循环」推论**无法用 live
证据支持**。

### 结论

| 结论 | 说明 |
|------|------|
| 问题 #1（缓存停 17 天） | ❌ **勘误**：诊断看错了文件。live 缓存正常刷新 |
| `_write_cache` 静默吞 OSError | ⚠️ 仍是**代码隐患**，但不是当前故障根因。建议作为防御性硬化保留，优先级降至 P3 |

## 7.2 确认：问题 #2「code=95 雷暴误报」仍在持续

### live 缓存现场（fetched 0.2 小时前）

```json
{
  "location": "深圳",
  "latitude": 22.54554, "longitude": 114.0683,
  "weather_code": 95,
  "temperature": 27.9, "humidity": 91, "wind_speed": 10.0,
  "fetched_at": "2026-06-23T14:55:35+00:00"
}
```

`weather_code=95`（雷暴）在 **6/22 早间** 和 **6/23 晚间** 都出现 →
**持续性误报，非偶发**。这是当前真正的 P0 问题。

### 为什么 Open-Meteo 对深圳持续返回 95

Open-Meteo 的 `current.weather_code` 是**数值模型对网格点瞬时条件的解读**，
不是实测雷达。关键特性：

- 网格分辨率约 9-11 km。深圳这种尺度内**任意位置**有对流活动，整个网格点
  都可能被标为雷暴码。
- 6 月下旬华南季风期，高湿（本例 humidity=91）+ 高 CAPE 环境，模型倾向给出
  对流性天气码（95/96/99），**即使你所在的具体位置头顶没打雷**。
- `wind_speed=10 km/h`（风力 2 级）与「正在雷暴」的预期明显矛盾——真正的
  雷暴通常伴随阵风。这是一个可编程校验的**逻辑不自洽信号**。

**核心判断**：code=95 不是 Open-Meteo 的 bug，是免费数据源的固有精度边界。
**修复方向是交叉校验而非责怪数据源**。

## 7.3 代码级新发现（weather.py / injector.py 逐行）

以下三个问题在仓库与 live profile 的代码中**完全一致**（diff 为空）。

### 7.3.1 🔴 `_fetch_weather` 静默零值默认（weather.py:213-218）

```python
current = data.get("current", {})
return {
    "temperature": current.get("temperature_2m", 0),      # 缺失 → 0°C
    "humidity": current.get("relative_humidity_2m", 0),   # 缺失 → 0%
    "weather_code": current.get("weather_code", 0),       # 缺失 → 0 = "晴"
    "wind_speed": current.get("wind_speed_10m", 0),       # 缺失 → 0 km/h
}
```

**问题**：如果 Open-Meteo 返回的 `current` 对象结构变化（字段重命名、
部分缺失、降级响应），`weather_code` 会静默变成 `0`（晴），`temperature`
变成 `0°C`。结果是**在最恶劣的天气里注入「晴 0°C」**，且无任何告警。

更隐蔽的情况：若 API 返回 `"weather_code": null`（key 存在但值为 null），
`dict.get(key, default)` 返回的是 `None` 而非默认值 `0`，会穿透到
`_weather_code_to_cn(None)`（见 7.3.3）。

**影响**：高。一旦触发，注入的天气完全失真且 fail-open 机制无法察觉。

### 7.3.2 🟡 debug 摘要双重读缓存时序竞争（injector.py:1422-1436）

```python
# 天气已在 1139-1146 行通过 _weather_context() 注入完毕（可能刚调过 API 刷新缓存）
...
from weather import _read_cache, _should_refresh
cache = _read_cache()                              # ← 此时读到的已是刷新后的新缓存
if _should_refresh(cache, weather_cfg, location):  # ← 新缓存当然"有效"→ 返回 False
    weather_debug = {"cache_state": "已过期-刷新"...}
else:
    weather_debug = {"cache_state": "有效-跳过", "api_state": "未调用"...}  # ← 撒谎
```

**问题**：debug 摘要在注入流程**之后**重新读缓存并判断 `_should_refresh`。
如果本轮刚执行了 API 刷新，此时缓存已是最新 → `_should_refresh` 返回 False →
debug 标记为「有效-跳过 / API 未调用」，**与本轮实际行为相反**。

**影响**：debug 输出在**最需要它的时候**（缓存刚刷新、需确认 API 是否被调）
恰好给出错误信息。低危，但会严重误导排查——**这可能正是第一节误入
「缓存写失败」方向的原因之一**。

### 7.3.3 🟡 None 值穿透 `_weather_code_to_cn`（weather.py:68-73 + 207-218）

当 API 返回 `"weather_code": null` 时，`_fetch_weather` 不走 except 分支
（HTTP 200 + JSON 合法），返回 `{"weather_code": None, ...}`。随后：

```python
def _weather_code_to_cn(code: int) -> tuple[str, str]:
    for codes, result in _WMO_CODE_MAP.items():
        if code in codes:        # None in (0,) → False，全部跳过
            return result
    return _WMO_FALLBACK          # → ("未知", "🌡")
```

最终注入「未知 🌡」。不崩溃，但注入了无意义内容。`_format_weather` 会输出
`🌤 深圳 未知 28°C`——温度还在，天气描述却丢了，且无降级提示。

## 7.4 修正后的问题优先级

| # | 问题 | 旧评级 | **新评级** | 依据 |
|---|------|:------:|:----------:|------|
| 2 | code=95 雷暴持续误报 | 🟡 | 🔴 **P0** | live 缓存证实持续存在，直接影响人格注入质量 |
| 7.3.1 | `_fetch_weather` 静默零值 | — | 🔴 **P1** | 潜在高危，API 字段变更即触发静默失真 |
| 7.3.2 | debug 双重读缓存撒谎 | — | 🟡 **P2** | 不影响注入，但误导排查 |
| 7.3.3 | None 穿透 weather_code | — | 🟡 **P2** | 边界情况，输出降级为「未知」 |
| 1 | 缓存停 17 天 | 🔴 | ⬜ **P3** | 勘误：看错文件。`_write_cache` 硬化保留 |

## 7.5 修正后的修复路线

### 第一步（P0）：数据可信度校验层 — `_validate_weather`

不依赖第二数据源，先榨干现有数据的逻辑自洽性：

```python
def _validate_weather(data: dict) -> tuple[dict, bool]:
    """校验天气数据逻辑自洽性。返回 (data, suspicious)。

    规则（可逐条开关）：
    - 雷暴码(95/96/99) + 风力 < 3 级(< 12 km/h) → 可疑（雷暴通常伴阵风）
    - weather_code 为 None → 可疑
    - temperature 缺失/为 None → 可疑
    """
```

可疑时在注入文本追加 `（天气数据可能不准确）`，不阻断注入。

### 第二步（P1）：`_fetch_weather` 字段完整性校验

```python
# 四个字段任一缺失或 None → 视为 API 失败，走 fallback
required = ["temperature_2m", "relative_humidity_2m", "weather_code", "wind_speed_10m"]
if not all(k in current and current[k] is not None for k in required):
    return None  # 触发 _get_weather_data 的缓存回退路径
```

### 第三步（P2）：debug 摘要改为在注入时采集状态

在 `_weather_context()` 调用处用变量记录 `cache_state` / `api_state`，
传入 debug 汇总，**不再事后重读缓存**。

### 第四步（P3）：多数据源（方案 A）

Open-Meteo 交叉校验仍可疑时，fallback 到和风天气 API。需 key（免费额度足够）。

## 7.6 待验证项

以下需要网络访问 Open-Meteo API 确认（当前沙箱无网络），建议手动执行：

1. 直接请求 Open-Meteo 深圳坐标，确认是否**当下仍返回 95**：
   ```
   curl "https://api.open-meteo.com/v1/forecast?latitude=22.54554&longitude=114.0683&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
   ```
2. 若仍为 95 但实际无雷暴 → 确认是网格精度问题，`_validate_weather` 的
   风力交叉校验即可覆盖。
3. 监控一周：记录每次 fetched 的 code，统计 95 出现频率，判断是系统性偏差
   还是季节性偏高。

## 7.7 补充：仓库配置 vs live 配置

| 维度 | 仓库 `persona-config.json` | **live** zhihui profile |
|------|---------------------------|------------------------|
| `modules.weather` | `false` | **`true`** |
| `weather.location` | `""`（空） | **`"深圳"`** |
| `state/weather_cache.json` | 北京 6/5（死数据） | 深圳 6/23 22:55（活跃） |

诊断天气问题时必须以 **live profile** 为准。仓库模板的 `weather: false`
是交付默认值，不代表运行状态。
