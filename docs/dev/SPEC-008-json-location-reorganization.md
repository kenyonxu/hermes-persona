# SPEC-008: JSON 文件位置整顿

**文档编号:** SPEC-008
**对应 US:** US-008
**版本:** 1.0
**日期:** 2026-05-21
**作者:** 知惠（Zhihui）
**审阅:** Kai.Xu
**状态:** 📋 待审阅
**分支:** `feature/001-module-switch`

---

## 目录

1. [问题陈述](#1-问题陈述)
2. [目标结构](#2-目标结构)
3. [路径迁移方案](#3-路径迁移方案)
4. [向后兼容策略](#4-向后兼容策略)
5. [测试要点](#5-测试要点)
6. [实施步骤](#6-实施步骤)
7. [审批检查清单](#7-审批检查清单)

---

## 1. 问题陈述

### 1.1 散落现状

hermes-persona 插件的 JSON 文件目前散落在 **4 个位置**，导致用户困惑、备份冗余、沙盒幽灵拷贝污染：

| # | 当前位置 | 文件 | 说明 |
|:---|:---|:---|:---|
| 1 | `~/.hermes/profiles/{profile}/` | `persona-config.json` | 用户活跃配置（profile 根目录） |
| 2 | `~/.hermes/profiles/{profile}/` | `persona-config (副本).json` | 旧备份，已废弃 |
| 3 | `~/.hermes/profiles/{profile}/state/` | `expression_vector.json` | 运行时状态 |
| 4 | `~/.hermes/profiles/{profile}/home/.hermes/profiles/{profile}/` | `persona-config.json` | 沙盒幽灵拷贝（重复嵌套） |
| 5 | `~/github/hermes-persona/` | `keywords/`、`locales/`、`examples/` | 源码仓库有，但部署目录 `plugins/hermes-persona/` 缺少部分 |

### 1.2 痛点

- **用户困惑**：配置文件到底在哪改？profile 根目录还是插件目录？
- **备份冗余**：`(副本).json` 无人维护，与主文件不同步。
- **沙盒污染**：沙盒内嵌套的 `home/.hermes/...` 路径是 rsync/cp 的历史残留，占用磁盘且误导排查。
- **部署不对齐**：源码仓库有 `keywords/`、`locales/`，但部署后 `plugins/hermes-persona/` 下缺少这些目录，导致关键词匹配引擎初始化失败。

---

## 2. 目标结构

所有用户可编辑的 JSON 配置和运行时状态文件统一到**插件目录** `hermes-persona/` 下：

```
~/.hermes/profiles/{profile}/plugins/hermes-persona/
├── persona-config.json          ← 用户唯一需要手改的配置文件
├── keywords/                    ← 维度关键词（用户可手改 or 热加载）
│   ├── work.json
│   ├── intimacy.json
│   ├── play.json
│   ├── care.json
│   ├── eros.json
│   ├── future.json
│   └── synonyms.json
├── locales/                     ← 多语言模板
│   ├── en.json
│   └── zh.json
├── state/                       ← 运行时自动生成（用户不用管）
│   ├── expression_vector.json
│   └── daily_turn_count.json
└── examples/
    └── persona-config.json      ← 模板（新用户复制用）
```

**源码仓库 `~/github/hermes-persona/` 保持同样结构**，部署时 `rsync` 直接对齐，无需额外转换。

---

## 3. 路径迁移方案

### 3.1 文件级变更矩阵

| 文件 | 当前路径逻辑 | 新路径逻辑 | 向后兼容 |
|:---|:---|:---|:---|
| `persona-config.json` | `_CONFIG_ROOT / "persona-config.json"` | `Path(__file__).resolve().parent / "persona-config.json"` | ✅ 新路径不存在 → fallback 旧路径 |
| `expression_vector.json` | `cfg["storage_path"]` 默认 `~/.hermes/expression_vector.json` | `Path(__file__).resolve().parent / "state" / "expression_vector.json"` | ✅ 新路径不存在 → fallback 旧路径 |
| `daily_turn_count.json` | `~/.hermes/profiles/{profile}/state/daily_turn_count.json` | `Path(__file__).resolve().parent / "state" / "daily_turn_count.json"` | ✅ 新路径不存在 → fallback 旧路径 |
| `keywords/` | `Path(__file__).resolve().parent / "keywords"`（已正确） | 不变 | — |
| `locales/` | `_init_locales(_plugin_dir, config_data)` | 不变 | — |

### 3.2 `injector.py` — `_load_config()` 路径变更

**当前逻辑（L106–130）：**

```python
def _load_config() -> dict:
    if _config._CONFIG_ROOT is not None:
        config_path = _config._CONFIG_ROOT / "persona-config.json"
    else:
        config_path = Path(__file__).resolve().parents[2] / "persona-config.json"
```

**新逻辑：**

```python
_PLUGIN_DIR = Path(__file__).resolve().parent

def _load_config() -> dict:
    # 1. 优先：插件目录下的 persona-config.json
    plugin_config = _PLUGIN_DIR / "persona-config.json"
    if plugin_config.is_file():
        config_path = plugin_config
    # 2. 向后兼容：profile 根目录（旧路径）
    elif _config._CONFIG_ROOT is not None:
        config_path = _config._CONFIG_ROOT / "persona-config.json"
    # 3. 最终 fallback：开发环境（repo 根目录）
    else:
        config_path = _PLUGIN_DIR.parents[1] / "persona-config.json"
```

**关键约束：**
- 插件目录优先（新用户默认位置）。
- profile 根目录 fallback（现有用户配置不丢失）。
- 若两个位置都存在，以**插件目录**为准（鼓励迁移）。

### 3.3 `guard.py` — `_load_guard_config()` 路径变更

**当前逻辑（L32–37）：**

```python
def _load_guard_config() -> dict:
    import config as _config
    if _config._CONFIG_ROOT is not None:
        config_path = _config._CONFIG_ROOT / "persona-config.json"
    else:
        config_path = Path(__file__).resolve().parents[2] / "persona-config.json"
```

**新逻辑：** 复用 `injector._load_config()` 或提取公共函数 `_resolve_config_path()`，避免重复维护两套路径解析逻辑。

**推荐方案：** 在 `config.py` 中新增 `_resolve_config_path()` 公共函数，`injector.py` 和 `guard.py` 统一调用。

### 3.4 `expression_vector.py` — `_ExpressionVector` 存储路径变更

**当前逻辑（L80–85）：**

```python
raw_path = cfg.get("storage_path", "~/.hermes/expression_vector.json")
if profile_path:
    raw_path = raw_path.replace("{profile}", str(profile_path))
self.storage_path: Path = Path(raw_path).expanduser()
```

**新逻辑：**

```python
_PLUGIN_DIR = Path(__file__).resolve().parent

default_path = str(_PLUGIN_DIR / "state" / "expression_vector.json")
raw_path = cfg.get("storage_path", default_path)

# 向后兼容：如果配置中显式写了旧路径，保留用户意图
if "{profile}" in raw_path and profile_path:
    raw_path = raw_path.replace("{profile}", str(profile_path))

self.storage_path: Path = Path(raw_path).expanduser()
```

**关键约束：**
- `storage_path` 配置项仍保留，允许高级用户自定义路径。
- 默认值改为插件目录下的 `state/expression_vector.json`。
- 若用户显式配置了旧路径（如 `~/.hermes/profiles/{profile}/state/expression_vector.json`），尊重其配置。

### 3.5 `injector.py` — `_daily_turn_count_hint()` 存储路径变更

**当前逻辑（L771–777）：**

```python
raw_path = dc_cfg.get(
    "storage_path",
    "~/.hermes/profiles/{profile}/state/daily_turn_count.json",
)
```

**新逻辑：**

```python
_PLUGIN_DIR = Path(__file__).resolve().parent

default_path = str(_PLUGIN_DIR / "state" / "daily_turn_count.json")
raw_path = dc_cfg.get("storage_path", default_path)
```

### 3.6 `injector.py` — debug 详细模式中的 daily_turn_count 读取路径

**当前逻辑（L1032）：**

```python
dc_path_raw = dc_cfg.get("storage_path", "~/.hermes/profiles/{profile}/state/daily_turn_count.json")
```

**新逻辑：** 与 `_daily_turn_count_hint()` 统一，使用新的默认路径。

---

## 4. 向后兼容策略

### 4.1 三层 fallback 机制

```
加载配置/状态文件时：
  1. 先查插件目录（新规范位置）
  2. 再查 profile 根目录 / state/（旧规范位置）
  3. 最后查开发环境 repo 根目录（pytest 场景）
```

### 4.2 自动迁移（可选，非阻塞）

在 `register()` 中增加一次性的自动迁移逻辑：

```python
def _migrate_json_locations(profile_path: Path) -> None:
    """将旧位置的 JSON 文件迁移到插件目录（若新位置不存在）。"""
    plugin_dir = Path(__file__).resolve().parent
    old_config = profile_path / "persona-config.json"
    new_config = plugin_dir / "persona-config.json"

    if old_config.is_file() and not new_config.is_file():
        import shutil
        shutil.copy2(old_config, new_config)
```

**约束：**
- 迁移是**复制**而非移动（保留旧文件作为备份）。
- 仅在首次检测到新路径缺失时执行一次。
- 任何异常（权限、磁盘满）静默降级，不阻塞插件启动。

### 4.3 状态文件跨路径读取

对于 `expression_vector.json` 和 `daily_turn_count.json`：
- 若新路径存在 → 读取新路径。
- 若新路径不存在但旧路径存在 → 读取旧路径，并在首次 `save()` 时写入新路径（自然迁移）。
- 若两者都不存在 → 初始化空状态。

---

## 5. 测试要点

### 5.1 必须保持的测试覆盖

当前测试总数：**333 passed**。以下测试类/文件必须继续通过：

| 测试文件 | 关键场景 | 影响 |
|:---|:---|:---|
| `test_injector.py::TestLoadConfig` | `_load_config()` 路径解析 | 需适配新 fallback 逻辑 |
| `test_expression_vector.py::TestDiskPersistence` | `save()` / `load()` 往返 | 需适配新默认路径 |
| `test_guard.py` | `_load_guard_config()` 路径解析 | 需复用新的公共路径函数 |
| `test_fixed_signals.py` | `daily_turn_count` 读写 | 需适配新默认路径 |
| `conftest.py::temp_config_root` | 测试 fixture 的临时目录 | 需确保临时 persona-config.json 写到正确位置 |

### 5.2 新增测试用例

| TC-ID | 场景 | 断言 |
|:---|:---|:---|
| LOC-01 | 插件目录存在 persona-config.json | `_load_config()` 从插件目录读取 |
| LOC-02 | 插件目录不存在，profile 根目录存在 | `_load_config()` fallback 到 profile 根目录 |
| LOC-03 | 两者都不存在 | `_load_config()` 返回 `{}`，不抛异常 |
| LOC-04 | `expression_vector` 新默认路径 save+load | 文件写入 `state/expression_vector.json` |
| LOC-05 | `daily_turn_count` 新默认路径 | 文件写入 `state/daily_turn_count.json` |
| LOC-06 | 旧路径有状态文件，新路径无 | 读取旧路径，save 后新路径生成 |
| LOC-07 | `keywords/` 目录在插件目录下 | `_KeywordMatcher` 正常初始化 |

### 5.3 conftest.py 调整

`temp_config_root` fixture 当前将 `persona-config.json` 写到临时目录根。需要调整：

```python
@pytest.fixture
def temp_config_root():
    """Create a temporary directory mimicking the plugin directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "plugins" / "hermes-persona"
        plugin_dir.mkdir(parents=True)
        # ... 将 config 写到 plugin_dir / "persona-config.json"
```

**或者**保留现有 fixture 行为（模拟旧路径），同时新增 fixture 测试新路径。

---

## 6. 实施步骤

### Phase 1: 提取公共路径函数（30 min）

1. 在 `config.py` 中新增 `_resolve_config_path()`：
   ```python
   def _resolve_config_path() -> Path:
       """Resolve persona-config.json path with new → old fallback."""
       plugin_dir = Path(__file__).resolve().parent
       plugin_config = plugin_dir / "persona-config.json"
       if plugin_config.is_file():
           return plugin_config
       if _CONFIG_ROOT is not None:
           return _CONFIG_ROOT / "persona-config.json"
       return plugin_dir.parents[1] / "persona-config.json"
   ```
2. `injector.py` 和 `guard.py` 统一调用 `_resolve_config_path()`。
3. 运行测试：`pytest tests/test_injector.py::TestLoadConfig -v`

### Phase 2: 调整 expression_vector 默认路径（20 min）

1. 修改 `expression_vector.py` L80–85，默认路径改为插件目录 `state/`。
2. 确保 `state/` 目录在 `save()` 时自动创建（已有 `mkdir(parents=True)`）。
3. 运行测试：`pytest tests/test_expression_vector.py::TestDiskPersistence -v`

### Phase 3: 调整 daily_turn_count 默认路径（20 min）

1. 修改 `injector.py` 中 `_daily_turn_count_hint()` 和 debug 详细模式的默认路径。
2. 运行测试：`pytest tests/test_fixed_signals.py -v`

### Phase 4: 清理废弃文件（10 min）

1. 删除 `persona-config (副本).json`（如果源码仓库中有）。
2. 在 `.gitignore` 中追加：
   ```
   # Runtime state — auto-generated, do not commit
   state/
   ```

### Phase 5: 全量测试（10 min）

```bash
python -m pytest tests/ -v
# 期望：333 passed, 0 failed
```

### Phase 6: 文档更新（10 min）

1. 更新 `README.md` 中配置文件位置说明。
2. 更新 `DESIGN.md` 中目录结构描述。
3. 更新 `CHANGELOG.md`。

---

## 7. 审批检查清单

- [ ] SPEC 文档已审阅并通过
- [ ] 所有路径变更点已列出（injector.py、guard.py、expression_vector.py）
- [ ] 向后兼容 fallback 逻辑已确认（三层：插件目录 → profile 根目录 → repo 根目录）
- [ ] conftest.py fixture 调整方案已确认
- [ ] 新增测试用例 LOC-01 ~ LOC-07 已编写并通过
- [ ] 全量测试 333 passed
- [ ] README / DESIGN / CHANGELOG 已更新
- [ ] 废弃文件（副本.json、沙盒幽灵拷贝）已清理或标记清理
- [ ] `.gitignore` 已追加 `state/`
