# US: 天气多数据源 — 零配置默认 + 可选高级源

> 日期：2026-06-24 | 状态：Draft | 关联 SPEC：`2026-06-23-fix-weather-data-reliability.md`

---

## 用户故事

**作为** hermes-persona 的普通用户，**我希望**天气功能开箱即用、不需要注册任何 API key，**以便**人物卡写好就能体验到天气上下文注入。

**作为** 深度用户，**我希望**可以配置自己信任的天气数据源，**以便**获得更精准的本地天气，或使用付费源获取分钟级降水、灾害预警等高级数据。

---

## 当前状态

| 项 | 状态 |
|----|------|
| 主力源 | Open-Meteo（免费，无 key） |
| 校验层 | `_validate_weather`（P0 已实现，待部署） |
| 问题 | Open-Meteo 对深圳持续返回雷暴码（code=95），校验层可拦截但无替代源 |
| 发现的第二 keyless 源 | wttr.in — 同免费、无 key，深圳实测准确 |

---

## 方案

### 默认体验（零配置）

```
weather:
  location: "深圳"
  # 什么都不填——以下自动生效
```

内部：

```
Open-Meteo（主力）
  ↓ _validate_weather 通过 → 直接注入
  ↓ 可疑（雷暴+弱风等）
    ↓ wttr.in（交叉校验）
      ↓ 一致 → 注入（标记为双源确认）
      ↓ 不一致 → 注入 wttr.in 结果 + 标注「已交叉校验」
      ↓ wttr.in 也失败 → 回退缓存 + 「数据可能不准确」
```

**用户感知**：填个城市名就行。校验和 fallback 全自动。

### 深度用户（可选配置）

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

支持的 provider：

| provider | 需要 key？ | 环境变量 | 亮点 |
|----------|:---:|------|------|
| `openmeteo` | ❌ | 无 | 默认主力 |
| `wttr` | ❌ | 无 | 默认 fallback |
| `qweather` | ✅ | `QWEATHER_KEY` | 国内精准，分钟级降水 |
| `openweather` | ✅ | `OWM_KEY` | 全球覆盖，免费 100 万次/月 |
| `seniverse` | ✅ | `SENIVERSE_KEY` | 气象局授权，无限调用 |

不填 `providers` → 默认 `openmeteo + wttr`。填了 → 按用户指定的来。key 通过环境变量传入，不写入配置文件（避免泄露）。

---

## 实现拆分

| 阶段 | 内容 | 依赖 |
|:---:|------|------|
| P0 | `_validate_weather` + 字段校验（已完成，待部署） | — |
| P1 | wttr.in 接入为第二 keyless 源 | P0 |
| P2 | 多 provider 抽象层（Provider 基类） | P1 |
| P3 | 和风天气 / OpenWeather 等 keyed provider | P2 |

P0→P1 之后，普通用户就已经有双源保护了。P2→P3 是给深度用户的额外选项。

---

## 设计约束

- **key 不入配置文件**：一律走环境变量，防止 git 误提交
- **provider 失败不阻断**：任一源失败 → 静默降级到下一源 → 最后兜底缓存 + 标注
- **校验层独立于 provider**：`_validate_weather` 对所有源生效，不只是 Open-Meteo
- **向后兼容**：现有 `weather.location` / `detail` / `label` 配置不变

---

## 验证方式

```bash
# 默认模式：零配置，双源自动
python -c "from weather import _weather_context; print(_weather_context({'location':'深圳'}))"

# 深度模式：指定 primary
python -c "
import os; os.environ['QWEATHER_KEY']='xxx'
from weather import _weather_context
print(_weather_context({'location':'深圳','providers':{'primary':'qweather'}}))
"
```

---

## 相关文件

- `docs/superpowers/specs/2026-06-23-fix-weather-data-reliability.md` — P0 修复 SPEC
- `docs/superpowers/specs/2026-06-05-weather-module-design.md` — 天气模块原始设计
- `scripts/weather-compare/compare.py` — 多源对比测试脚本
