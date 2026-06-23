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
