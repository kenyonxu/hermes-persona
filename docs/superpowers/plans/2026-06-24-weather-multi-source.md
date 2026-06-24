# 天气多数据源 实施计划

> **For agentic workers:** 使用 superpowers:subagent-driven-development 或 superpowers:executing-plans 来实施此计划。步骤使用 checkbox (`- [ ]`) 语法追踪。

**Goal:** 为天气模块新增多数据源支持——wttr.in 作为第二 keyless 源提供零配置双源保护，Provider 抽象层统一数据源接口，深度用户可选和风/OpenWeather/心知天气

**Architecture:** 在 `weather.py` 中引入 `WeatherProvider` 协议类，将现有 Open-Meteo 逻辑迁移为 `OpenMeteoProvider`，新增 `WttrProvider`。`_get_weather_data` 从硬编码调用改造为 provider 调度管道（primary → fallback → 缓存）。keyed provider 按独立文件组织（`weather_providers/`），惰性导入。key 通过环境变量传入，不入配置文件。

**Tech Stack:** Python 3.10+, urllib (标准库), pytest

**Spec:** `docs/superpowers/specs/2026-06-24-weather-multi-source.md`

**前置条件:** P0 校验层（`_validate_weather` + `_fetch_weather` 字段完整性 + debug 状态采集）已实现并部署

---

## 文件结构

| 文件 | 角色 | 改动 |
|------|------|------|
| `weather.py` | 天气核心 | Provider 基类 + OpenMeteoProvider + WttrProvider + `_get_weather_data` 改造 + provider 注册表 + `_try_provider` + `_format_weather` 增强 |
| `weather_providers/__init__.py` | 包标记 | 新建 |
| `weather_providers/qweather.py` | 和风天气 provider | 新建 |
| `weather_providers/openweather.py` | OpenWeather provider | 新建 |
| `weather_providers/seniverse.py` | 心知天气 provider | 新建 |
| `injector.py` | 集成层 | debug 摘要追加 source 信息（可选优化） |
| `persona-config.json` | 仓库模板 | `weather` 节新增 `providers` 子节 |
| `tests/test_weather.py` | 单元测试 | Provider 测试、多源 fallback 测试、交叉校验测试 |
| `tests/test_weather_providers.py` | keyed provider 测试 | 新建 |

**不修改**：`__init__.py`、`config.py`、`guard.py`、`locales/`。

---

## Chunk 1: wttr.in Provider（P1 — 第二 keyless 源）

> **依赖**：P0 校验层已完成
> **目标**：普通用户获得双源保护——Open-Meteo 可疑/不可用时自动走 wttr.in

### Task 1.1: WttrProvider 实现 + normalize

**Files:** `weather.py`, `tests/test_weather.py`

- [ ] **Step 1: 了解 wttr.in API 格式**

  wttr.in API 端点：`https://wttr.in/{lat},{lon}?format=j1`
  
  响应关键路径：
  ```json
  {
    "current_condition": [{
      "temp_C": "28",
      "humidity": "85",
      "windspeedKmph": "15",
      "weatherCode": "116"
    }]
  }
  ```
  
  注意：wttr.in 对无效坐标返回 HTML 错误页（Content-Type: text/html），需检测。

- [ ] **Step 2: 编写 WttrProvider 测试**

  在 `tests/test_weather.py` 中追加：

  ```python
  # ── WttrProvider ───────────────────────────────────────────────────────

  from weather import WttrProvider


  class TestWttrProviderNormalize:
      def test_normalize_valid_response(self):
          provider = WttrProvider()
          raw = {
              "current_condition": [{
                  "temp_C": "28",
                  "humidity": "85",
                  "windspeedKmph": "15",
                  "weatherCode": "116",
              }]
          }
          result = provider.normalize(raw)
          assert result is not None
          assert result["temperature"] == 28
          assert result["humidity"] == 85
          assert result["weather_code"] == 116
          assert result["wind_speed"] == 15

      def test_normalize_empty_current_condition(self):
          provider = WttrProvider()
          result = provider.normalize({"current_condition": []})
          assert result is None

      def test_normalize_missing_field(self):
          provider = WttrProvider()
          raw = {
              "current_condition": [{
                  "temp_C": "28",
                  "humidity": "85",
                  # windspeedKmph 缺失
              }]
          }
          result = provider.normalize(raw)
          assert result is None

      def test_normalize_missing_current_condition(self):
          provider = WttrProvider()
          result = provider.normalize({})
          assert result is None

      def test_name_and_requires_key(self):
          provider = WttrProvider()
          assert provider.name == "wttr"
          assert provider.requires_key is False


  class TestWttrProviderFetch:
      @patch("weather.urllib.request.urlopen")
      def test_fetch_success(self, mock_urlopen):
          mock_response = MagicMock()
          mock_response.headers = {"Content-Type": "application/json"}
          mock_response.read.return_value = json.dumps({
              "current_condition": [{
                  "temp_C": "28", "humidity": "85",
                  "windspeedKmph": "15", "weatherCode": "116",
              }]
          }).encode()
          mock_urlopen.return_value.__enter__.return_value = mock_response

          provider = WttrProvider()
          result = provider.fetch(22.5, 114.0)
          assert result is not None
          assert result["temperature"] == 28

      @patch("weather.urllib.request.urlopen")
      def test_fetch_html_error_response(self, mock_urlopen):
          """wttr.in 错误时返回 HTML，应返回 None。"""
          mock_response = MagicMock()
          mock_response.headers = {"Content-Type": "text/html"}
          mock_response.read.return_value = b"<html>Error</html>"
          mock_urlopen.return_value.__enter__.return_value = mock_response

          provider = WttrProvider()
          result = provider.fetch(22.5, 114.0)
          assert result is None

      @patch("weather.urllib.request.urlopen")
      def test_fetch_network_error(self, mock_urlopen):
          mock_urlopen.side_effect = urllib.error.URLError("timeout")
          provider = WttrProvider()
          result = provider.fetch(22.5, 114.0)
          assert result is None
  ```

- [ ] **Step 3: 实现 WttrProvider**

  在 `weather.py` 的 Provider 区域新增 `WttrProvider` 类（见 SPEC 6.3）。

  关键实现要点：
  - `fetch()` 中检测 `Content-Type` 含 `json` 才解析
  - `normalize()` 中 `current_condition[0]` 所有字段用 `int()` 归一化
  - 顶层缺少 `current_condition` 或为空数组 → 返回 None
  - `geocode()` 继承基类默认实现（复用 Open-Meteo geocoding）

- [ ] **Step 4: 运行 WttrProvider 测试验证通过**

  ```bash
  python -m pytest tests/test_weather.py::TestWttrProviderNormalize tests/test_weather.py::TestWttrProviderFetch -v
  ```

- [ ] **Step 5: 手动验证 wttr.in API 连通性**

  ```bash
  python -c "
  from weather import WttrProvider
  p = WttrProvider()
  # 深圳坐标
  coords = p.geocode('深圳')
  print(f'坐标: {coords}')
  if coords:
      data = p.fetch(*coords)
      print(f'天气: {data}')
  "
  ```

  预期：输出深圳坐标和当前天气数据（风速/温度/湿度/天气码）

- [ ] **Step 6: 提交**

  ```bash
  git add weather.py tests/test_weather.py
  git commit -m "feat(weather): WttrProvider — wttr.in 第二 keyless 源接入"
  ```

### Task 1.2: `_get_weather_data` 接入双源 fallback（硬编码方式）

> **注意**：此阶段先不引入 Provider 抽象层，以最小改动实现双源 fallback。Provider 抽象在 P2 阶段统一重构。

**Files:** `weather.py`, `tests/test_weather.py`

- [ ] **Step 1: 编写双源 fallback 测试**

  在 `tests/test_weather.py` 中追加：

  ```python
  # ── 双源 fallback 测试 ──────────────────────────────────────────────────


  class TestMultiSourceFallback:
      @patch("weather.WttrProvider.fetch")
      @patch("weather._fetch_weather")
      def test_primary_normal_no_fallback(self, mock_fetch, mock_wttr_fetch):
          """主力源正常时，不调用 wttr.in。"""
          mock_fetch.return_value = {
              "temperature": 26.0, "humidity": 45,
              "weather_code": 0, "wind_speed": 15.0,
          }
          result = _get_weather_data({"location": "深圳", "cache_ttl_minutes": 30})
          assert result is not None
          assert result["weather_code"] == 0
          assert result["source"] == "openmeteo"
          mock_wttr_fetch.assert_not_called()

      @patch("weather.WttrProvider.fetch")
      @patch("weather._fetch_weather")
      def test_primary_suspicious_fallback_used(self, mock_fetch, mock_wttr_fetch):
          """主力源返回可疑数据（雷暴+低风），走 wttr.in fallback。"""
          mock_fetch.return_value = {
              "temperature": 27.9, "humidity": 91,
              "weather_code": 95, "wind_speed": 10.0,  # 雷暴 + 低风 → 可疑
          }
          mock_wttr_fetch.return_value = {
              "temperature": 28.0, "humidity": 85,
              "weather_code": 1, "wind_speed": 14.0,  # wttr 显示多云
          }
          result = _get_weather_data({"location": "深圳", "cache_ttl_minutes": 30})
          assert result is not None
          assert result["weather_code"] == 1  # 用了 wttr.in 的数据
          assert result["source"] == "wttr"
          mock_wttr_fetch.assert_called_once()

      @patch("weather.WttrProvider.fetch")
      @patch("weather._fetch_weather")
      def test_primary_fails_fallback_used(self, mock_fetch, mock_wttr_fetch):
          """主力源失败，走 wttr.in fallback。"""
          mock_fetch.return_value = None  # Open-Meteo 失败
          mock_wttr_fetch.return_value = {
              "temperature": 28.0, "humidity": 85,
              "weather_code": 1, "wind_speed": 14.0,
          }
          result = _get_weather_data({"location": "深圳", "cache_ttl_minutes": 30})
          assert result is not None
          assert result["source"] == "wttr"

      @patch("weather.WttrProvider")
      @patch("weather._fetch_weather")
      @patch("weather._geocode")
      @patch("weather._read_cache")
      @patch("weather._should_refresh")
      def test_both_fail_cache_fallback(self, mock_refresh, mock_read,
                                         mock_geocode, mock_fetch, mock_wttr_class):
          """双源失败 → 回退旧缓存。"""
          mock_read.return_value = {
              "location": "深圳", "temperature": 26.0, "humidity": 45,
              "weather_code": 0, "wind_speed": 15.0,
              "fetched_at": "2026-06-24T00:00:00",
          }
          mock_refresh.return_value = True
          mock_geocode.return_value = (22.5, 114.0)
          mock_fetch.return_value = None  # primary 失败
          mock_wttr_provider = MagicMock()
          mock_wttr_provider.fetch.return_value = None  # fallback 也失败
          mock_wttr_class.return_value = mock_wttr_provider

          result = _get_weather_data({"location": "深圳", "cache_ttl_minutes": 30})
          assert result is not None
          assert result["weather_code"] == 0  # 回退到旧缓存
          assert result.get("suspicious") is True  # 标记可疑

      @patch("weather.WttrProvider")
      @patch("weather._fetch_weather")
      @patch("weather._geocode")
      @patch("weather._read_cache")
      @patch("weather._should_refresh")
      def test_both_fail_no_cache_returns_none(self, mock_refresh, mock_read,
                                                mock_geocode, mock_fetch, mock_wttr_class):
          """双源失败 + 无缓存 → 返回 None。"""
          mock_read.return_value = None
          mock_refresh.return_value = True
          mock_geocode.return_value = (22.5, 114.0)
          mock_fetch.return_value = None
          mock_wttr_provider = MagicMock()
          mock_wttr_provider.fetch.return_value = None
          mock_wttr_class.return_value = mock_wttr_provider

          result = _get_weather_data({"location": "深圳", "cache_ttl_minutes": 30})
          assert result is None
  ```

- [ ] **Step 2: 运行测试验证失败**

  ```bash
  python -m pytest tests/test_weather.py::TestMultiSourceFallback -v
  ```

- [ ] **Step 3: 改造 `_get_weather_data` 加入双源 fallback**

  在现有 `_get_weather_data` 的 API 调用段，primary 返回后插入校验 + fallback 逻辑：

  ```python
  # 在 _fetch_weather(lat, lon) 返回 weather 之后：

  primary_data = weather  # Open-Meteo 结果
  suspicious = _validate_weather(primary_data, config.get("validation"))

  if suspicious:
      # 尝试 wttr.in 交叉校验
      try:
          wttr = WttrProvider()
          wttr_data = wttr.fetch(lat, lon)
          if wttr_data:
              # 交叉校验：天气码相同 **且** 温差 ≤ 5°C → 视为一致
              code_match = wttr_data["weather_code"] == primary_data["weather_code"]
              temp_close = abs(wttr_data["temperature"] - primary_data["temperature"]) <= 5
              if code_match and temp_close:
                  # 双源一致 → 用主力源数据，加双源确认标记
                  full_data = {..., "suspicious": False, "source": "openmeteo",
                               "cross_validated": True}
              else:
                  # 不一致 → 用 wttr.in 数据
                  weather = wttr_data
                  full_data = {..., "suspicious": False, "source": "wttr"}
          else:
              # wttr 失败 → 保留主力源数据 + 标记可疑
              full_data = {..., "suspicious": True, "source": "openmeteo"}
      except Exception:
          full_data = {..., "suspicious": True, "source": "openmeteo"}
  elif primary_data is None:
      # Open-Meteo 失败 → 尝试 wttr
      try:
          wttr = WttrProvider()
          wttr_data = wttr.fetch(lat, lon)
          if wttr_data:
              weather = wttr_data
              full_data = {..., "suspicious": False, "source": "wttr"}
      except Exception:
          pass
  ```

- [ ] **Step 4: 运行全量双源 fallback 测试**

  ```bash
  python -m pytest tests/test_weather.py::TestMultiSourceFallback -v
  ```

- [ ] **Step 5: 运行回归测试确保现有测试仍通过**

  ```bash
  python -m pytest tests/test_weather.py -v
  ```

- [ ] **Step 6: 提交**

  ```bash
  git add weather.py tests/test_weather.py
  git commit -m "feat(weather): _get_weather_data 双源 fallback — Open-Meteo + wttr.in 交叉校验"
  ```

---

## Chunk 2: Provider 抽象层（P2 — 重构与标准化）

> **依赖**：P1 wttr.in 依赖完成
> **目标**：将硬编码双源逻辑提取为 Provider 协议 + 注册表，Open-Meteo 逻辑迁移为 OpenMeteoProvider

### Task 2.1: WeatherProvider 基类 + OpenMeteoProvider 迁移

**Files:** `weather.py`, `tests/test_weather.py`

- [ ] **Step 1: 定义 WeatherProvider 协议类**

  ```python
  class WeatherProvider:
      """天气数据源协议。

      子类实现 fetch() 和 normalize()。
      geocode() 有默认实现（复用 Open-Meteo geocoding API）。
      """

      name: str = ""
      requires_key: bool = False

      def geocode(self, location: str) -> tuple[float, float] | None:
          """城市名 → (lat, lon)。默认使用 Open-Meteo geocoding API。"""
          # 复用现有模块级 _geocode() 实现
          return _geocode(location)

      def fetch(self, lat: float, lon: float) -> dict | None:
          """获取天气原始数据 → 统一格式 dict，失败返回 None。"""
          raise NotImplementedError

      def normalize(self, raw: dict) -> dict | None:
          """Provider 原始响应 → 统一格式 dict。子类必须实现。"""
          raise NotImplementedError
  ```

- [ ] **Step 2: 将现有 Open-Meteo 逻辑迁移为 OpenMeteoProvider**

  ```python
  class OpenMeteoProvider(WeatherProvider):
      name = "openmeteo"
      requires_key = False

      def fetch(self, lat, lon):
          # 现有 _fetch_weather() 逻辑移至此处
          ...

      def normalize(self, raw):
          return raw  # Open-Meteo 已输出统一格式
  ```

  现有模块级 `_geocode()` 和 `_fetch_weather()` 函数保留为薄包装，内部委托给 `OpenMeteoProvider` 实例，确保外部引用不破坏。

- [ ] **Step 3: 编写 OpenMeteoProvider 测试**

  验证迁移后的 `OpenMeteoProvider.fetch()` 与原有 `_fetch_weather()` 行为一致。

- [ ] **Step 4: 运行测试验证**

  ```bash
  python -m pytest tests/test_weather.py -v
  ```

- [ ] **Step 5: 提交**

  ```bash
  git add weather.py tests/test_weather.py
  git commit -m "refactor(weather): WeatherProvider 抽象层 + OpenMeteoProvider 迁移"
  ```

### Task 2.2: Provider 注册表 + `_get_weather_data` 重构

**Files:** `weather.py`, `tests/test_weather.py`

- [ ] **Step 1: 实现 Provider 注册表**

  ```python
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
  ```

- [ ] **Step 2: 实现 `_resolve_coords` 辅助函数**

  ```python
  def _resolve_coords(cache, location):
      """从缓存或 geocode 解析坐标。"""
      if cache and cache.get("location") == location:
          lat = cache.get("latitude")
          lon = cache.get("longitude")
          if lat is not None and lon is not None:
              return lat, lon
      coords = _geocode(location)
      return coords if coords else (None, None)
  ```

- [ ] **Step 3: 实现 `_try_provider` 辅助函数**（见 SPEC 6.4）

- [ ] **Step 4: 重构 `_get_weather_data` 使用 provider 调度**

  将 Task 1.2 中的硬编码双源逻辑替换为 provider 调度管道（见 SPEC 6.4 完整实现）。

  Cache 命中路径和 API 失败回退路径保持不变，只替换 API 调用段的 provider 调度逻辑。

- [ ] **Step 5: 编写 provider 注册表测试**

  ```python
  class TestProviderRegistry:
      def test_get_known_provider(self):
          provider = _get_provider("openmeteo")
          assert provider is not None
          assert provider.name == "openmeteo"

      def test_get_wttr_provider(self):
          provider = _get_provider("wttr")
          assert provider is not None
          assert provider.name == "wttr"

      def test_get_unknown_provider_returns_none(self):
          assert _get_provider("nonexistent") is None

      def test_get_keyed_provider_without_key_returns_none(self):
          """keyed provider 缺少环境变量时返回 None。"""
          # 确保环境变量未设置
          with patch.dict(os.environ, {}, clear=True):
              # 手动注册一个测试 keyed provider
              ...
              assert _get_provider("qweather") is None
  ```

- [ ] **Step 6: 运行全量测试**

  ```bash
  python -m pytest tests/test_weather.py -v
  ```

- [ ] **Step 7: 提交**

  ```bash
  git add weather.py tests/test_weather.py
  git commit -m "refactor(weather): Provider 注册表 + _get_weather_data provider 调度重构"
  ```

### Task 2.3: `_format_weather` 增强 + debug 状态更新

**Files:** `weather.py`, `tests/test_weather.py`

- [ ] **Step 1: 增强格式化函数**

  `_format_weather` 和 `_format_weather_narrative` 新增 `source` + `cross_validated` 标注（见 SPEC 6.7）。

- [ ] **Step 2: 更新 debug 状态**

  `_LAST_DEBUG_STATE` 新增 `source` 字段，记录实际使用的数据源标识符。

- [ ] **Step 3: 编写格式化 + debug 测试**

  | 场景 | 期望输出 |
  |------|---------|
  | source="openmeteo", suspicious=False | `🌤 深圳 晴 26°C` |
  | source="wttr", suspicious=False | `🌤 深圳 多云 27°C（来源: wttr）` |
  | source="openmeteo", suspicious=True | `🌤 深圳 雷暴 28°C（天气数据可能不准确）` |
  | source="wttr", cross_validated=True | `🌤 深圳 多云 27°C（来源: wttr，双源确认）` |

- [ ] **Step 4: 运行测试**

  ```bash
  python -m pytest tests/test_weather.py -v
  ```

- [ ] **Step 5: 提交**

  ```bash
  git add weather.py tests/test_weather.py
  git commit -m "feat(weather): _format_weather 增强 — source/cross_validated 标注 + debug 状态更新"
  ```

---

## Chunk 3: Keyed Provider（P3 — 深度用户可选源）

> **依赖**：P2 Provider 抽象层完成
> **目标**：用户可通过环境变量启用和风/OpenWeather/心知天气

### Task 3.1: QWeatherProvider（和风天气）

**Files:** `weather_providers/__init__.py` (new), `weather_providers/qweather.py` (new), `tests/test_weather_providers.py` (new)

- [ ] **Step 1: 创建目录结构和 `__init__.py`**

  ```bash
  mkdir -p weather_providers
  touch weather_providers/__init__.py
  ```

- [ ] **Step 2: 编写 QWeatherProvider 测试**

  在 `tests/test_weather_providers.py` 中：

  ```python
  """Tests for keyed weather providers."""


  class TestQWeatherProvider:
      def test_name_and_requires_key(self):
          from weather_providers.qweather import QWeatherProvider
          p = QWeatherProvider()
          assert p.name == "qweather"
          assert p.requires_key is True
          assert p.env_var == "QWEATHER_KEY"

      def test_normalize_valid_response(self):
          from weather_providers.qweather import QWeatherProvider
          p = QWeatherProvider()
          raw = {
              "now": {
                  "temp": "28", "humidity": "85",
                  "icon": "100", "windSpeed": "15",
              }
          }
          result = p.normalize(raw)
          assert result is not None
          assert result["temperature"] == 28.0
          assert result["humidity"] == 85.0

      def test_normalize_missing_now(self):
          from weather_providers.qweather import QWeatherProvider
          p = QWeatherProvider()
          assert p.normalize({}) is None

      def test_normalize_missing_field(self):
          from weather_providers.qweather import QWeatherProvider
          p = QWeatherProvider()
          raw = {"now": {"temp": "28"}}  # 缺少 icon
          assert p.normalize(raw) is None

      @patch.dict(os.environ, {"QWEATHER_KEY": "test-key"})
      @patch("urllib.request.urlopen")
      def test_fetch_success(self, mock_urlopen):
          from weather_providers.qweather import QWeatherProvider
          mock_response = MagicMock()
          mock_response.read.return_value = json.dumps({
              "now": {"temp": "28", "humidity": "85",
                      "icon": "100", "windSpeed": "15"}
          }).encode()
          mock_urlopen.return_value.__enter__.return_value = mock_response

          p = QWeatherProvider()
          result = p.fetch(22.5, 114.0)
          assert result is not None
          assert result["temperature"] == 28.0

      @patch.dict(os.environ, {}, clear=True)
      def test_fetch_without_key_raises_or_returns_none(self):
          from weather_providers.qweather import QWeatherProvider
          p = QWeatherProvider()
          # 无 key 时应从环境变量读取空字符串，API 调用会失败
          with patch("urllib.request.urlopen") as mock:
              mock.side_effect = urllib.error.URLError("no key")
              result = p.fetch(22.5, 114.0)
              assert result is None
  ```

- [ ] **Step 3: 实现 QWeatherProvider**（见 SPEC 6.6）

  注意和风天气码到 WMO 码的映射表：

  ```python
  # 和风天气 icon → WMO 码（覆盖常见天气）
  _QW_TO_WMO: dict[int, int] = {
      100: 0,   # 晴
      101: 1,   # 多云
      102: 2,   # 少云
      103: 3,   # 晴间多云
      104: 3,   # 阴
      300: 61,  # 阵雨
      301: 61,  # 强阵雨
      302: 95,  # 雷阵雨
      303: 95,  # 强雷阵雨
      304: 95,  # 雷阵雨伴有冰雹
      305: 51,  # 小雨
      306: 61,  # 中雨
      307: 63,  # 大雨
      308: 65,  # 暴雨
      309: 51,  # 毛毛雨
      400: 71,  # 小雪
      401: 73,  # 中雪
      402: 75,  # 大雪
      403: 75,  # 暴雪
      404: 85,  # 阵雪
      405: 73,  # 小雪
      406: 75,  # 中雪
      407: 75,  # 大雪
      500: 45,  # 薄雾
      501: 45,  # 雾
      502: 45,  # 霾
      503: 45,  # 扬沙
      504: 45,  # 浮尘
  }
  ```

- [ ] **Step 4: 运行 QWeatherProvider 测试**

  ```bash
  python -m pytest tests/test_weather_providers.py -v
  ```

- [ ] **Step 5: 提交**

  ```bash
  git add weather_providers/ tests/test_weather_providers.py
  git commit -m "feat(weather): QWeatherProvider — 和风天气 keyed 源"
  ```

### Task 3.2: OpenWeatherProvider + SeniverseProvider

**Files:** `weather_providers/openweather.py` (new), `weather_providers/seniverse.py` (new), `tests/test_weather_providers.py`

- [ ] **Step 1: 实现 OpenWeatherProvider**

  遵循与 QWeatherProvider 相同的模式：

  - `name = "openweather"`, `env_var = "OWM_KEY"`
  - API: `https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={key}&units=metric`
  - normalize: `weather[0].id` → WMO 码映射，`main.temp` → temperature，`main.humidity` → humidity，`wind.speed`（m/s → km/h 乘以 3.6）

- [ ] **Step 2: 实现 SeniverseProvider**

  - `name = "seniverse"`, `env_var = "SENIVERSE_KEY"`
  - API: `https://api.seniverse.com/v3/weather/now.json?key={key}&location={lat}:{lon}`
  - normalize: `results[0].now.code` → WMO 码映射，`results[0].now.temperature` → temperature

- [ ] **Step 3: 编写测试**

  参照 QWeatherProvider 测试模式，覆盖 normalize 和 fetch。

- [ ] **Step 4: 运行测试**

  ```bash
  python -m pytest tests/test_weather_providers.py -v
  ```

- [ ] **Step 5: 提交**

  ```bash
  git add weather_providers/openweather.py weather_providers/seniverse.py tests/test_weather_providers.py
  git commit -m "feat(weather): OpenWeatherProvider + SeniverseProvider keyed 源"
  ```

### Task 3.3: 惰性导入 + 注册集成

**Files:** `weather.py`

- [ ] **Step 1: 实现 `_register_keyed_providers()`**

  在 `weather.py` 模块底部添加惰性导入逻辑（见 SPEC 6.6）。

  关键设计：
  - 模块加载时执行，检查三个环境变量
  - 仅当环境变量非空时才 `importlib.import_module()`
  - 导入失败（模块不存在）静默忽略
  - 成功后注册到 `_PROVIDER_REGISTRY`

- [ ] **Step 2: 集成测试 — 端到端 keyed provider 流程**

  ```python
  class TestKeyedProviderIntegration:
      @patch.dict(os.environ, {"QWEATHER_KEY": "test-key"})
      def test_qweather_selected_when_configured_and_key_set(self):
          """配置 primary=qweather + key 存在 → 使用和风天气。"""
          # 模拟惰性注册
          from weather import _register_keyed_providers, _PROVIDER_REGISTRY
          _register_keyed_providers()
          assert "qweather" in _PROVIDER_REGISTRY

      def test_qweather_not_registered_when_key_missing(self):
          """未设置 QWEATHER_KEY → qweather 不在注册表中。"""
          ...
  ```

- [ ] **Step 3: 运行全量测试**

  ```bash
  python -m pytest tests/ -v
  ```

- [ ] **Step 4: 提交**

  ```bash
  git add weather.py tests/
  git commit -m "feat(weather): keyed provider 惰性导入 + 注册集成"
  ```

---

## Chunk 4: 配置 + 文档

### Task 4.1: persona-config.json 模板更新

**Files:** `persona-config.json`

- [ ] **Step 1: 新增 `providers` 子节**

  在 `weather` 节中 `validation` 之后添加：

  ```json
  "providers": {
    "primary": "openmeteo",
    "fallback": "wttr"
  }
  ```

  附注释说明：
  ```
  // providers: 天气数据源配置（可选，缺省使用 openmeteo + wttr 双源）
  // primary:  主力源 — openmeteo / wttr / qweather / openweather / seniverse
  // fallback: 备用源 — 主力可疑或不可用时启用
  // keyed 源需设置对应环境变量：QWEATHER_KEY / OWM_KEY / SENIVERSE_KEY
  ```

- [ ] **Step 2: 提交**

  ```bash
  git add persona-config.json
  git commit -m "docs(weather): persona-config.json 新增 providers 配置节"
  ```

### Task 4.2: injector.py — Debug 摘要优化（可选）

**Files:** `injector.py`

- [ ] **Step 1: debug detailed 模式追加 source 信息**

  在天气行后添加数据源信息：

  ```
  ① 🌤 天气: 深圳 多云 27°C
      来源: wttr（交叉校验）
      缓存: 已刷新
      API: 正常
  ```

- [ ] **Step 2: 提交**

  ```bash
  git add injector.py
  git commit -m "feat(weather): debug 摘要追加数据源信息"
  ```

---

## Chunk 5: 全量测试 + 最终验证

### Task 5.1: 运行全量测试 + 手动验证

- [ ] **Step 1: 运行全部测试**

  ```bash
  python -m pytest tests/ -v
  ```

  确保：
  - 现有 weather 测试（70+）全部通过
  - 新增 provider 测试全部通过
  - 新增双源 fallback 测试全部通过
  - injector 集成测试全部通过

- [ ] **Step 2: 手动验证零配置双源**

  ```bash
  # 清缓存触发刷新，观察双源行为
  rm state/weather_cache.json
  python -c "
  from weather import _weather_context, _get_debug_state
  result = _weather_context({'location': '深圳', 'detail': 'brief', 'label': '🌤'})
  print(f'结果: {result}')
  print(f'Debug: {_get_debug_state()}')
  "
  ```

- [ ] **Step 3: 手动验证 keyed provider（如有测试 key）**

  ```bash
  QWEATHER_KEY=your_test_key python -c "
  from weather import _weather_context
  result = _weather_context({
      'location': '深圳', 'detail': 'full', 'label': '🌤',
      'providers': {'primary': 'qweather'}
  })
  print(f'和风天气: {result}')
  "
  ```

- [ ] **Step 4: 确认向后兼容**

  ```bash
  # 使用旧格式配置（无 providers 字段）
  python -c "
  from weather import _weather_context
  result = _weather_context({'location': '深圳', 'detail': 'brief', 'label': '🌤'})
  print(f'旧格式配置: {result}')
  # 应正常返回天气，不报错
  "
  ```

- [ ] **Step 5: 最终提交**

  ```bash
  git add -A
  git commit -m "feat(weather): 多数据源支持完成 — P1 wttr.in + P2 Provider抽象 + P3 keyed源"
  ```

---

## 分阶段验收标准

### P1 验收（wttr.in 双源）

- [ ] `WttrProvider.fetch()` 返回统一格式 dict，`normalize()` 正确转换 wttr.in JSON
- [ ] Open-Meteo 返回可疑数据时，自动调用 wttr.in 交叉校验
- [ ] Open-Meteo 失败时，自动走 wttr.in
- [ ] 双源都失败时，回退旧缓存（suspicious=True）
- [ ] 双源失败 + 无缓存时，返回 None
- [ ] 现有 70+ 测试无回归

### P2 验收（Provider 抽象层）

- [ ] `WeatherProvider` 协议类定义完整（name, requires_key, fetch, normalize, geocode）
- [ ] `OpenMeteoProvider` 行为与原 `_fetch_weather` 一致
- [ ] `_get_provider("openmeteo")` / `_get_provider("wttr")` 返回有效实例
- [ ] `_get_provider("unknown")` 返回 None
- [ ] `_get_weather_data` 通过 provider 调度而非硬编码
- [ ] `_try_provider` 正确处理 primary 可疑 → fallback 的降级链
- [ ] `_format_weather` 正确标注 source 和 cross_validated
- [ ] 旧缓存无 `source` 字段时读取不报错

### P3 验收（keyed source）

- [ ] `QWeatherProvider` / `OpenWeatherProvider` / `SeniverseProvider` 正确实现 WeatherProvider 协议
- [ ] keyed provider 缺少环境变量时 `_get_provider()` 返回 None
- [ ] 环境变量存在时 keyed provider 可正常注册和调用
- [ ] 配置 `providers.primary: "qweather"` 但缺 key → 自动回退默认 openmeteo
- [ ] 各 provider 的 normalize 正确映射天气码到 WMO 统一码
- [ ] persona-config.json 不含任何 API key

---

## 测试覆盖矩阵

| 测试类别 | 测试文件 | 覆盖场景 |
|---------|---------|---------|
| WttrProvider 纯函数 | `test_weather.py` | normalize: 正常/空数组/字段缺失/缺 current_condition |
| WttrProvider mock | `test_weather.py` | fetch: 成功/HTML错误/网络超时/JSON解析失败 |
| OpenMeteoProvider 迁移 | `test_weather.py` | fetch 行为与原 `_fetch_weather` 一致 |
| 双源 fallback | `test_weather.py` | primary正常→不触发fallback / primary可疑→走fallback / primary失败→走fallback / 双源失败→缓存回退 / 双源失败无缓存→None |
| Provider 注册表 | `test_weather.py` | 已知/未知 provider 查找、keyed provider 缺 key |
| 格式化增强 | `test_weather.py` | source标注、cross_validated标注、suspicious标注、组合场景 |
| debug 状态 | `test_weather.py` | `_LAST_DEBUG_STATE` 中 source 字段准确性 |
| QWeatherProvider | `test_weather_providers.py` | normalize 正常/缺字段、fetch mock、天气码映射 |
| OpenWeatherProvider | `test_weather_providers.py` | normalize、fetch mock、单位转换（m/s→km/h） |
| SeniverseProvider | `test_weather_providers.py` | normalize、fetch mock |
| 惰性导入 | `test_weather.py` | 环境变量存在→注册 / 不存在→不注册 |
| 集成测试 | `test_injector.py` | 注入链中天气模块正常、translate 模式、debug 摘要含 source |
| 向后兼容 | `test_weather.py` | 旧格式配置 → 等价默认双源行为 |
| 回归 | 全部测试文件 | 现有 70+ 测试通过 |

---

## 检查清单

- [ ] `WeatherProvider` 协议类有完整 docstring
- [ ] 所有 provider 子类实现 `fetch()` 和 `normalize()`
- [ ] fail-open：任何 provider 失败不阻断注入链
- [ ] 降级链完整：primary → fallback → 缓存 → 注入（带标注）
- [ ] key 不入配置文件，仅从环境变量读取
- [ ] keyed provider 惰性导入，缺少依赖不阻塞启动
- [ ] `_validate_weather` 对所有 provider 输出校验
- [ ] `_format_weather` / `_format_weather_narrative` 正确标注数据源
- [ ] debug `_LAST_DEBUG_STATE` 记录 source 信息
- [ ] `persona-config.json` 仓库模板已更新
- [ ] 向后兼容：旧配置不加 `providers` 字段正常工作
- [ ] 全部已有测试仍通过
- [ ] 和风天气 icon → WMO 码映射表覆盖常见天气
