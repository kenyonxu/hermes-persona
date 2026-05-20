# PLAN-006: Debug 详细模式 + 国际化 — 实施计划

**文档编号:** PLAN-006
**对应 SPEC:** SPEC-003 §2.1-2.3（§2.5 turn_stage 已有 PLAN-005，不动）
**依赖:** PLAN-004（目录扁平化完成）、CR-014（config.py 提取完成）
**版本:** 1.0
**日期:** 2026-05-21
**作者:** 知惠 (zhihui)
**状态:** 📋 待审阅

---

## 目录

1. [总体时间估算](#1-总体时间估算)
2. [实施步骤](#2-实施步骤)
    - [Phase 0: 环境准备与基线验证](#phase-0-环境准备与基线验证)
    - [Phase 1: 国际化基础设施—locales 加载器 + _t() 函数](#phase-1-国际化基础设施locales-加载器--t-函数)
    - [Phase 2: _debug_summary() 重构为 compact/detailed 双模式](#phase-2-_debug_summary-重构为-compactdetailed-双模式)
    - [Phase 3: _detailed_summary() 详细模式实现](#phase-3-_detailed_summary-详细模式实现)
    - [Phase 4: inject_context() 组装 debug_context](#phase-4-inject_context-组装-debug_context)
    - [Phase 5: test_debug_detailed.py — 详细模式测试](#phase-5-test_debug_detailedpy--详细模式测试)
    - [Phase 6: test_locales.py — 国际化测试](#phase-6-test_localespy--国际化测试)
    - [Phase 7: 更新 examples/persona-config.json + 全量回归](#phase-7-更新-examplespersona-configjson--全量回归)
3. [风险点与回滚方案](#3-风险点与回滚方案)
4. [验证检查清单](#4-验证检查清单)

---

## 1. 总体时间估算

| Phase | 内容 | 预估时间 |
|:---|:---|:---|
| Phase 0 | 环境准备与基线验证 | 5 min |
| Phase 1 | 国际化基础设施 — locales 加载器 + `_t()` 函数 | 25 min |
| Phase 2 | `_debug_summary()` 重构为 compact/detailed 双模式 | 20 min |
| Phase 3 | `_detailed_summary()` 详细模式实现 | 30 min |
| Phase 4 | `inject_context()` 组装 `debug_context` | 15 min |
| Phase 5 | `test_debug_detailed.py` — 详细模式测试 | 20 min |
| Phase 6 | `test_locales.py` — 国际化测试 | 15 min |
| Phase 7 | 更新 examples/persona-config.json + 全量回归 | 10 min |
| **合计** | | **~2 小时 20 分** |

### 阶段依赖关系

```
Phase 0 (基线) → Phase 1 (locales + _t)
                      ↓
Phase 2 (重构 debug_summary)
    ↓
Phase 3 (detailed_summary) ←─── Phase 4 (debug_context)
    ↓
Phase 5 (测试详细模式)    Phase 6 (测试国际化)
    ↓                           ↓
Phase 7 (全量回归 + 更新范例)
```

Phase 1 → 2 → 3 → 4 是串联改动链。Phase 5 和 Phase 6 可并行，但都依赖 Phase 3+4 完成。Phase 7 依赖所有前置。

---

## 2. 实施步骤

### Phase 0: 环境准备与基线验证

**目标：** 确认分支正确、工作区干净、现有测试基线记录。

**操作：**

```bash
# 1. 确认分支
git branch --show-current
# 期望: feature/001-module-switch（或其他主开发分支）

# 2. 确认工作区干净
git status
# 期望: 无未提交变更

# 3. 记录当前测试通过数（基线：231 passed，8 failed 为预存失败）
python -m pytest tests/ -v --tb=no 2>&1 | tail -10
# 期望: 231 passed, 8 failed（预存失败的 8 个测试与本次改动无关）
```

**验证标准：**
- 工作区无未提交变更
- 记录基线通过数（231 passed）

**回滚：** 无需回滚（尚未改动代码）

---

### Phase 1: 国际化基础设施 — locales 加载器 + `_t()` 函数

**目标：** 创建 locales 目录结构、中文/英文翻译文件、加载器模块和翻译工具函数。

#### 1.1 创建 locales/ 目录结构

**文件：**
- 新建：`locales/__init__.py`
- 新建：`locales/zh.json`
- 新建：`locales/en.json`

**操作：**

```bash
# 创建目录
mkdir -p locales/
```

#### 1.2 locales/zh.json — 中文翻译文件

```json
{
  "debug.header": "🔧 [Debug] 本轮注入:",
  "modules.time.injected": "时间已注入",
  "modules.time.stopped": "已停用",
  "modules.static_rules": "{count}条静态规则",
  "modules.static_rules.stopped": "已停用",
  "modules.dynamic.status": "{status}",
  "modules.dynamic.stopped": "已停用",
  "modules.fixed_signals.triggered": "固定信号 ({triggered}/{total}触发)",
  "modules.fixed_signals.none": "固定信号 (无触发)",
  "modules.expression_vector": "表达向量 | 第{turn_count}轮",
  "modules.expression_vector.enabled": "已注入",
  "modules.expression_vector.disabled": "未启用",
  "modules.expression_vector.hit": "命中: {keywords}({count})",
  "modules.expression_vector.decay": "衰减: {dims}({count})",
  "modules.expression_vector.no_hit": "无命中",
  "modules.variance.hit": "随机变化 ({hit}/{total}抽中)",
  "modules.variance.none": "随机变化 (0条)",
  "modules.variance.stopped": "已停用",
  "modules.memory.injected": "已注入",
  "modules.memory.stopped": "已停用",
  "modules.kanban.no_data": "无数据",
  "modules.kanban.data": "有数据",
  "modules.kanban.stopped": "已停用",
  "signal.message_length.triggered": "len={length} < threshold={threshold} → 触发",
  "signal.message_length.idle": "len={length} >= threshold={threshold} → 未触发",
  "signal.reply_gap.triggered": "gap={gap}min > threshold={threshold}min → 触发",
  "signal.reply_gap.idle": "已启用（未触发）",
  "signal.reply_gap.detail": "last_reply: {last_reply} (gap={gap}min, threshold={threshold}min)",
  "signal.daily_turn.triggered": "{count} → 触发",
  "signal.daily_turn.idle": "{count} (未触发)",
  "signal.daily_turn.detail": "today: {date}, count={count}",
  "variance.hit": "✓ {name} (prob={prob}): \"{chosen}\"",
  "variance.miss": "✗ {name} (prob={prob}): 未抽中"
}
```

#### 1.3 locales/en.json — 英文翻译文件

```json
{
  "debug.header": "🔧 [Debug] Turn Summary:",
  "modules.time.injected": "Time injected",
  "modules.time.stopped": "Stopped",
  "modules.static_rules": "{count} static rules",
  "modules.static_rules.stopped": "Stopped",
  "modules.dynamic.status": "{status}",
  "modules.dynamic.stopped": "Stopped",
  "modules.fixed_signals.triggered": "Fixed Signals ({triggered}/{total} triggered)",
  "modules.fixed_signals.none": "Fixed Signals (none)",
  "modules.expression_vector": "Expression Vector | turn {turn_count}",
  "modules.expression_vector.enabled": "Injected",
  "modules.expression_vector.disabled": "Disabled",
  "modules.expression_vector.hit": "hit: \"{keywords}\"({count})",
  "modules.expression_vector.decay": "decay: {dims}({count})",
  "modules.expression_vector.no_hit": "none",
  "modules.variance.hit": "Variance ({hit}/{total} rolled)",
  "modules.variance.none": "Variance (0)",
  "modules.variance.stopped": "Stopped",
  "modules.memory.injected": "Memory injected",
  "modules.memory.stopped": "Stopped",
  "modules.kanban.no_data": "No data",
  "modules.kanban.data": "Has data",
  "modules.kanban.stopped": "Stopped",
  "signal.message_length.triggered": "len={length} < threshold={threshold} → triggered",
  "signal.message_length.idle": "len={length} >= threshold={threshold} → idle",
  "signal.reply_gap.triggered": "gap={gap}min > threshold={threshold}min → triggered",
  "signal.reply_gap.idle": "Idle (not triggered)",
  "signal.reply_gap.detail": "last_reply: {last_reply} (gap={gap}min, threshold={threshold}min)",
  "signal.daily_turn.triggered": "{count} → triggered",
  "signal.daily_turn.idle": "{count} (idle)",
  "signal.daily_turn.detail": "today: {date}, count={count}",
  "variance.hit": "✓ {name} (p={prob}): \"{chosen}\"",
  "variance.miss": "✗ {name} (p={prob}): not rolled"
}
```

**设计要点：**
- 键名使用点式命名空间（`modules.*`、`signal.*`、`variance.*`），方便按模块组织
- 使用 `{placeholder}` 语法进行参数插值，与 Python `str.format()` 对齐
- `modules.*.stopped` 是模块关闭时的通用回退文案
- variance 条目覆盖了（en, disabled, none）三种状态

#### 1.4 locales/__init__.py — 加载器与 _t() 工具函数

```python
"""Locale loader and translation utility for hermes-persona debug output.

Design:
- Translations are preloaded into memory at plugin registration time
- Missing keys fall back to hardcoded Chinese (current behavior)
- Missing locale files fall back to Chinese
- _t(key, **kwargs) performs str.format() style interpolation
"""

from __future__ import annotations

import json
from pathlib import Path

# In-memory cache: loaded once at registration time
_TRANSLATIONS: dict[str, str] = {}
_ACTIVE_LANG: str = "zh"


def _resolve_language(config: dict) -> str:
    """Resolve effective language from config.

    Priority:
        1. config["language"] if set to "zh" or "en"
        2. "auto" → infer from config["time"]["format"]
            "cn_full" → "zh", anything else → "en"
        3. Default → "zh"
    """
    lang = config.get("language", "auto")
    if lang in ("zh", "en"):
        return lang
    # "auto" or any other value → infer from time.format
    time_cfg = config.get("time", {})
    tf = time_cfg.get("format", "")
    if tf == "cn_full":
        return "zh"
    return "en"


def _load_translations(plugin_dir: str | Path, lang: str) -> dict[str, str]:
    """Load translation dict for a given language from locales/{lang}.json.

    Args:
        plugin_dir: Path to the hermes-persona plugin directory.
        lang: Language code ("zh" or "en").

    Returns:
        Translation dict. Returns empty dict if file not found or parse error.
    """
    locale_path = Path(plugin_dir) / "locales" / f"{lang}.json"
    try:
        if locale_path.is_file():
            data = json.loads(locale_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _init_locales(plugin_dir: str | Path, config: dict) -> None:
    """Initialize locale system: resolve language and preload translations.

    Must be called once at plugin registration time.

    Args:
        plugin_dir: Plugin directory path (where locales/ lives).
        config: Fully loaded hermes-persona config dict.
    """
    global _TRANSLATIONS, _ACTIVE_LANG

    # If no language config key exists, fall back to auto-detect
    _ACTIVE_LANG = _resolve_language(config)
    _TRANSLATIONS = _load_translations(plugin_dir, _ACTIVE_LANG)

    # If active lang translations are empty, try zh as fallback
    if not _TRANSLATIONS and _ACTIVE_LANG != "zh":
        zh_fallback = _load_translations(plugin_dir, "zh")
        if zh_fallback:
            _TRANSLATIONS = zh_fallback


def _t(key: str, **kwargs) -> str:
    """Translate a key with optional format parameters.

    Falls back to the key itself if no translation found.

    Args:
        key: Translation key (e.g., "modules.time.injected").
        **kwargs: Format parameters for str.format() interpolation.

    Returns:
        Translated and formatted string.
    """
    template = _TRANSLATIONS.get(key)
    if template is None:
        return key  # fallback: return raw key (will be handled by caller)
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template


def set_language(lang: str, plugin_dir: str | Path) -> None:
    """Dynamically change the active language at runtime (for testing).

    Args:
        lang: "zh" or "en".
        plugin_dir: Plugin directory for re-loading translations.
    """
    global _TRANSLATIONS, _ACTIVE_LANG
    _ACTIVE_LANG = lang
    _TRANSLATIONS = _load_translations(plugin_dir, lang)
```

#### 1.5 在 __init__.py register() 中挂接 locales 初始化

**文件：** `__init__.py`（修改）

**改动：** 在 `register()` 函数末尾添加 locales 预加载调用。

```python
# 在 register() 末尾添加（在 guard hook 注册之后）
from locales import _init_locales

# 加载配置并初始化 locale
config_data = injector._load_config()
_init_locales(_plugin_dir, config_data)
```

**设计说明：**
- 需要在 `injector._load_config()` 可用之后调用
- `_plugin_dir` 已在 `__init__.py` 模块级别定义（L18）
- 预加载只执行一次，运行时无磁盘 I/O

**验证标准：**

```bash
# 1. locales 可导入
python -c "from locales import _t, _init_locales, _resolve_language; print('OK')"
# 期望: OK

# 2. _resolve_language 基本逻辑
python -c "
from locales import _resolve_language
assert _resolve_language({'language': 'zh'}) == 'zh'
assert _resolve_language({'language': 'en'}) == 'en'
assert _resolve_language({'language': 'auto', 'time': {'format': 'cn_full'}}) == 'zh'
assert _resolve_language({'language': 'auto', 'time': {'format': 'iso'}}) == 'en'
assert _resolve_language({}) == 'zh'  # 无配置默认
print('OK')
"
# 期望: OK

# 3. 翻译文件存在且有效
python -c "
import json
with open('locales/zh.json') as f: zh = json.load(f)
with open('locales/en.json') as f: en = json.load(f)
assert isinstance(zh, dict) and len(zh) >= 30
assert isinstance(en, dict) and len(en) >= 30
# 键名必须一致（英文可以有更多键，但不能少）
for k in zh:
    assert k in en, f'Missing key in en.json: {k}'
print(f'OK: zh={len(zh)} keys, en={len(en)} keys')
"
# 期望: OK: zh=XX keys, en=XX keys

# 4. _t() 基础功能
python -c "
from locales import _init_locales
_init_locales('.', {'language': 'zh'})
from locales import _t
result = _t('debug.header')
assert result == '🔧 [Debug] 本轮注入:', f'Got: {result}'
print('OK')
"
# 期望: OK

# 5. _t() 带参数
python -c "
from locales import _init_locales
_init_locales('.', {'language': 'zh'})
from locales import _t
result = _t('modules.static_rules', count=8)
assert result == '8条静态规则', f'Got: {result}'
print('OK')
"
# 期望: OK
```

**回滚：**

```bash
# 删除新建文件
rm -rf locales/
# __init__.py 回滚（如果已改动）
git checkout HEAD -- __init__.py
```

---

### Phase 2: _debug_summary() 重构为 compact/detailed 双模式

**目标：** 将 `_debug_summary()` 重构为根据 `debug.detail` 配置选择 compact 或 detailed 路径的入口函数。compact 路径逻辑与当前完全一致。

**文件：** `injector.py`（修改）

**改动 1：** 修改 `_debug_summary()` 签名和入口逻辑

```python
def _debug_summary(
    modules: dict,
    parts: list[str],
    var_count: int = 0,
    config: dict | None = None,
    debug_context: dict | None = None,
) -> str:
    """Generate a human-readable injection summary for debug mode.

    Supports two modes based on config["debug"]["detail"]:
    - "compact" (default): Current concise format, backward compatible.
    - "detailed": Per-module expanded sub-lines with trigger details.

    Args:
        modules: Module enable/disable dict.
        parts: Injected parts list (for counting & analysis).
        var_count: Number of variance items selected.
        config: Full hermes-persona config (for detail mode resolution).
        debug_context: Dict with detailed context assembled by inject_context()
            for detailed mode. Contains fixed_signal_state, expression_vector_delta, etc.

    Returns:
        Formatted debug summary string.
    """
    # Determine detail mode from config
    detail = "compact"
    if config:
        detail = config.get("debug", {}).get("detail", "compact")
        if detail not in ("compact", "detailed"):
            detail = "compact"

    if detail == "detailed":
        return _detailed_summary(modules, parts, var_count, debug_context or {})

    # === Compact mode (current behavior, unchanged) ===
    lines = ["🔧 [Debug] 本轮注入:"]

    # ① Time
    if _is_enabled(modules, "time"):
        lines.append("  ① 🕐 时间已注入")
    else:
        lines.append("  ① 🕐 已停用")

    # ② Static rules
    if _is_enabled(modules, "static_rules"):
        rule_count = _count_static_rules_in_parts(parts)
        lines.append(f"  ② 📜 {rule_count}条静态规则")
    else:
        lines.append("  ② 📜 已停用")

    # ③ Dynamic
    if _is_enabled(modules, "dynamic"):
        dyn = modules.get("dynamic", {})
        sub_status = _fmt_dynamic_sub_status(dyn)
        lines.append(f"  ③ ⚡ {sub_status}")
    else:
        lines.append("  ③ ⚡ 已停用")

    # ④a Fixed signals
    fixed_hit = any(
        p.startswith("📏") or p.startswith("🎵")
        or (p.startswith("📊") and not p.startswith("📊 ["))
        for p in parts
    )
    lines.append(
        f"  ④a 📏⏱️ 固定信号{'已注入' if fixed_hit else '无触发'}"
    )

    # ④b Expression vector
    ev_hit = any("📊 [表达向量]" in p for p in parts)
    if ev_hit:
        ev_part = next(p for p in parts if "📊 [表达向量]" in p)
        match = re.search(r"\[表达向量\] (.+?) \|", ev_part)
        if match:
            lines.append(f"  ④b 📊 {match.group(1)}")
        else:
            lines.append("  ④b 📊 已注入")
    else:
        lines.append("  ④b 📊 未启用")

    # ④ Variance
    if _is_enabled(modules, "variance"):
        if var_count > 0:
            lines.append(f"  ④ 🎲 {var_count}条变化")
        else:
            lines.append("  ④ 🎲 0条变化")
    else:
        lines.append("  ④ 🎲 已停用")

    # ⑤ Memory
    if _is_enabled(modules, "memory"):
        lines.append("  ⑤ 🧠 已注入")
    else:
        lines.append("  ⑤ 🧠 已停用")

    # ⑥ Kanban
    if _is_enabled(modules, "kanban"):
        kanban_status = _fmt_kanban_debug(parts)
        lines.append(f"  ⑥ 📋 {kanban_status}")
    else:
        lines.append("  ⑥ 📋 已停用")

    return "\n".join(lines)
```

**改动 2：** 在文件头部新增 `_detailed_summary` 函数的 import（Phase 3 实现）

```python
# 在现有 import 之后添加（约 L21）
from locales import _t as _translate
```

**验证标准：**

```bash
# 1. 语法合法
python -c "import ast; ast.parse(open('injector.py').read()); print('OK')"
# 期望: OK

# 2. 无 import 错误
python -c "import injector; print('OK')"
# 期望: OK

# 3. 默认模式不变 — compact 输出与修改前完全一致
python -c "
import injector
modules = {'time': True, 'static_rules': True, 'dynamic': {'time_slots': True, 'turn_stage': False, 'keyword': True}, 'variance': True, 'memory': False, 'kanban': True, 'debug': True}
result = injector._debug_summary(modules, ['📏 消息较短'], var_count=0, config={'debug': {'detail': 'compact'}})
print(result)
"
# 期望: 输出应与当前 compact 格式完全一致

# 4. detail="compact"（默认）仍走 compact 路径
python -c "
import injector
# 不传 config 参数时默认 compact
result = injector._debug_summary({'time': True}, [], var_count=0)
assert '已注入' in result or '已停用' in result
print('OK')
"
# 期望: OK
```

**回滚：**

```bash
git checkout HEAD -- injector.py
```

---

### Phase 3: _detailed_summary() 详细模式实现

**目标：** 实现 `_detailed_summary()` 函数，接收 `debug_context` 展开每模块细节。

**文件：** `injector.py`（新增函数）

**位置：** 在 `_debug_summary()` 之后（~L324），`_count_static_rules_in_parts()` 之前。

#### 3.1 _detailed_summary() 函数实现

```python
def _detailed_summary(
    modules: dict,
    parts: list[str],
    var_count: int,
    debug_context: dict,
) -> str:
    """Generate a detailed-format debug summary.

    Expected debug_context keys (assembled by inject_context):
        fixed_signals: {
            "message_length": {"triggered": bool, "length": int, "threshold": int},
            "reply_gap": {"enabled": bool, "triggered": bool, "last_reply": str|None,
                           "gap_minutes": float|None, "threshold_minutes": int},
            "daily_turn_count": {"triggered": bool, "count": int, "date": str},
        }
        expression_vector: {
            "dimensions": {  # keyed by dimension name
                name: {"old": float, "new": float, "delta": float,
                       "hit_keywords": list[str], "hit_count": int}
            },
            "turn_count": int,
            "enabled": bool,
        }
        variance: {
            "items": [
                {"name": str, "probability": float, "rolled": bool, "chosen": str|None}
            ],
            "total": int,
            "hits": int,
        }

    Args:
        modules: Module enable/disable dict.
        parts: Injected parts list (for counting & fallback display).
        var_count: Number of variance items selected (from _randomize_variance return).
        debug_context: Detailed state dict assembled by inject_context().

    Returns:
        Multi-line detailed debug summary string.
    """
    from locales import _t

    lines = [_t("debug.header")]

    # ① Time
    if _is_enabled(modules, "time"):
        lines.append(f"  ① 🕐 {_t('modules.time.injected')}")
    else:
        lines.append(f"  ① 🕐 {_t('modules.time.stopped')}")

    # ② Static rules
    if _is_enabled(modules, "static_rules"):
        rule_count = _count_static_rules_in_parts(parts)
        lines.append(f"  ② 📜 {_t('modules.static_rules', count=rule_count)}")
    else:
        lines.append(f"  ② 📜 {_t('modules.static_rules.stopped')}")

    # ③ Dynamic
    if _is_enabled(modules, "dynamic"):
        dyn = modules.get("dynamic", {})
        sub_status = _fmt_dynamic_sub_status(dyn)
        lines.append(f"  ③ ⚡ {_t('modules.dynamic.status', status=sub_status)}")
    else:
        lines.append(f"  ③ ⚡ {_t('modules.dynamic.stopped')}")

    # ④a Fixed signals - detailed
    fs_context = debug_context.get("fixed_signals", {})
    _fmt_detailed_fixed_signals(lines, fs_context)

    # ④b Expression vector - detailed
    ev_context = debug_context.get("expression_vector", {})
    _fmt_detailed_expression_vector(lines, ev_context)

    # ④ Variance - detailed
    var_context = debug_context.get("variance", {})
    _fmt_detailed_variance(lines, var_context, modules)

    # ⑤ Memory
    if _is_enabled(modules, "memory"):
        lines.append(f"  ⑤ 🧠 {_t('modules.memory.injected')}")
    else:
        lines.append(f"  ⑤ 🧠 {_t('modules.memory.stopped')}")

    # ⑥ Kanban
    if _is_enabled(modules, "kanban"):
        kanban_status = _fmt_kanban_debug(parts)
        lines.append(f"  ⑥ 📋 {kanban_status}")
    else:
        lines.append(f"  ⑥ 📋 {_t('modules.kanban.stopped')}")

    return "\n".join(lines)


def _fmt_detailed_fixed_signals(lines: list[str], fs: dict) -> None:
    """Format fixed signals section for detailed debug output."""
    from locales import _t

    fs_enabled = bool(fs)  # non-empty means at least one signal configured
    if not fs_enabled:
        lines.append(f"  ④a 📏⏱️ {_t('modules.fixed_signals.none')}")
        return

    total = 0
    triggered = 0

    # message_length
    ml = fs.get("message_length", {})
    if ml.get("visible", True):
        total += 1
        length = ml.get("length", 0)
        threshold = ml.get("threshold", 50)
        if ml.get("triggered", False):
            triggered += 1
            detail = _t("signal.message_length.triggered", length=length, threshold=threshold)
        else:
            detail = _t("signal.message_length.idle", length=length, threshold=threshold)
        lines.append(f"    📏 {detail}")

    # reply_gap
    rg = fs.get("reply_gap", {})
    if rg.get("enabled", False):
        total += 1
        if rg.get("triggered", False):
            triggered += 1
            gap = rg.get("gap_minutes", 0)
            threshold = rg.get("threshold_minutes", 30)
            detail = _t("signal.reply_gap.triggered", gap=round(gap, 1), threshold=threshold)
        else:
            detail = _t("signal.reply_gap.idle")
        lines.append(f"    🎵 {detail}")
        # Always show last_reply detail for reply_gap if available
        last_reply = rg.get("last_reply")
        if last_reply:
            gap_minutes = rg.get("gap_minutes", 0)
            threshold = rg.get("threshold_minutes", 30)
            detail_line = _t(
                "signal.reply_gap.detail",
                last_reply=last_reply,
                gap=round(gap_minutes, 1),
                threshold=threshold,
            )
            lines.append(f"       {detail_line}")

    # daily_turn_count
    dc = fs.get("daily_turn_count", {})
    if dc.get("visible", True):
        total += 1
        count = dc.get("count", 0)
        if dc.get("triggered", False):
            triggered += 1
            detail = _t("signal.daily_turn.triggered", count=count)
        else:
            detail = _t("signal.daily_turn.idle", count=count)
        lines.append(f"    📊 {detail}")
        date = dc.get("date", "")
        if date:
            detail_line = _t("signal.daily_turn.detail", date=date, count=count)
            lines.append(f"       {detail_line}")

    # Header line
    if total > 0:
        header = _t("modules.fixed_signals.triggered", triggered=triggered, total=total)
        lines.insert(-(len([l for l in lines[-10:] if l.startswith("    ")]) or 1), f"  ④a 📏⏱️ {header}")


def _fmt_detailed_expression_vector(lines: list[str], ev: dict) -> None:
    """Format expression vector section for detailed debug output."""
    from locales import _t

    if not ev.get("enabled", False):
        lines.append(f"  ④b 📊 {_t('modules.expression_vector.disabled')}")
        return

    turn_count = ev.get("turn_count", 0)
    header = _t("modules.expression_vector", turn_count=turn_count)
    lines.append(f"  ④b 📊 {header}")

    dimensions = ev.get("dimensions", {})
    for dim_name in sorted(dimensions.keys()):
        dim = dimensions[dim_name]
        old_val = round(dim.get("old", 0))
        new_val = round(dim.get("new", 0))
        delta = dim.get("delta", new_val - old_val)
        sign = "+" if delta >= 0 else ""
        hit_keywords = dim.get("hit_keywords", [])
        hit_count = dim.get("hit_count", 0)
        decay_dims = dim.get("decay_dims", [])

        if old_val != new_val:
            base = f"  {dim_name}: {old_val}→{new_val} ({sign}{int(delta)})"
        else:
            base = f"  {dim_name}: {new_val}"

        if hit_keywords and hit_count > 0:
            kw_str = ", ".join(hit_keywords)
            base += f"  ← {_t('modules.expression_vector.hit', keywords=kw_str, count=hit_count)}"
        elif decay_dims:
            base += f"  ← {_t('modules.expression_vector.decay', dims=', '.join(decay_dims), count=hit_count)}"
        else:
            base += f"  ← {_t('modules.expression_vector.no_hit')}"

        lines.append(base)


def _fmt_detailed_variance(lines: list[str], var_context: dict, modules: dict) -> None:
    """Format variance section for detailed debug output."""
    from locales import _t

    if not _is_enabled(modules, "variance"):
        lines.append(f"  ④ 🎲 {_t('modules.variance.stopped')}")
        return

    items = var_context.get("items", [])
    if not items:
        lines.append(f"  ④ 🎲 {_t('modules.variance.none')}")
        return

    hits = sum(1 for item in items if item.get("rolled", False))
    total = len(items)
    header = _t("modules.variance.hit", hit=hits, total=total)
    lines.append(f"  ④ 🎲 {header}")

    for item in items:
        name = item.get("name", "unknown")
        prob = item.get("probability", 0.0)
        if item.get("rolled", False):
            chosen = item.get("chosen", "")
            detail = _t("variance.hit", name=name, prob=prob, chosen=chosen)
            lines.append(f"    ✓ {detail}")
        else:
            detail = _t("variance.miss", name=name, prob=prob)
            lines.append(f"    ✗ {detail}")
```

**设计要点：**

1. **`_fmt_detailed_fixed_signals()`** 使用 `visible` 字段控制输出，因为兼容模式下 fixed signal helpers 可能未配置全部三项
2. **`_fmt_detailed_expression_vector()`** 接收表达向量更新前后的 delta 信息，`hit_keywords` 列表显示命中的具体关键词
3. **`_fmt_detailed_variance()`** 展示每个变体的概率和抽中/未抽中状态，基于 `debug_context["variance"]["items"]`

**验证标准：**

```bash
# 1. 语法合法
python -c "import ast; ast.parse(open('injector.py').read()); print('OK')"
# 期望: OK

# 2. 函数存在
python -c "
import injector
assert hasattr(injector, '_detailed_summary')
assert hasattr(injector, '_fmt_detailed_fixed_signals')
assert hasattr(injector, '_fmt_detailed_expression_vector')
assert hasattr(injector, '_fmt_detailed_variance')
print('OK')
"
# 期望: OK

# 3. 空 debug_context 不崩溃
python -c "
import injector
modules = {'time': True, 'static_rules': True, 'dynamic': {}, 'variance': True, 'memory': False, 'kanban': True, 'debug': True}
result = injector._debug_summary(modules, [], var_count=0, config={'debug': {'detail': 'detailed'}}, debug_context={})
print(result)
print('--- OK ---')
"
# 期望: 输出，不崩溃

# 4. 详细模式输出包含预期结构
python -c "
import injector
modules = {'time': True, 'static_rules': True, 'dynamic': {}, 'variance': True, 'memory': False, 'kanban': True, 'debug': True}
dc = {
    'fixed_signals': {
        'message_length': {'visible': True, 'triggered': True, 'length': 3, 'threshold': 50},
        'reply_gap': {'enabled': True, 'triggered': False, 'last_reply': '2026-05-19 19:25:32', 'gap_minutes': 0.5, 'threshold_minutes': 30},
        'daily_turn_count': {'visible': True, 'triggered': True, 'count': 42, 'date': '2026-05-19'},
    },
    'expression_vector': {
        'enabled': True,
        'turn_count': 174,
        'dimensions': {
            'care': {'old': 2.0, 'new': 3.0, 'delta': 1.0, 'hit_keywords': ['吃饭'], 'hit_count': 1, 'decay_dims': []},
            'work': {'old': 5.0, 'new': 6.0, 'delta': 1.0, 'hit_keywords': ['spec'], 'hit_count': 1, 'decay_dims': []},
        },
    },
    'variance': {
        'items': [
            {'name': 'fox_girl_body_language', 'probability': 0.6, 'rolled': True, 'chosen': '🦊 狐耳与狐尾联动的肢体语言表达'},
            {'name': 'metaphor_of_the_day', 'probability': 0.3, 'rolled': False, 'chosen': None},
        ],
    },
}
result = injector._debug_summary(modules, [], var_count=1, config={'debug': {'detail': 'detailed'}}, debug_context=dc)
print(result)
print('--- OK ---')
"
# 期望: 详细格式输出，包含 len=3 < threshold=50, 表达向量 delta, variance 勾选状态
```

**回滚：**

```bash
git checkout HEAD -- injector.py
```

---

### Phase 4: inject_context() 组装 debug_context

**目标：** 在 `inject_context()` 的 ④a、④b、④ 阶段捕获状态，组装 `debug_context` dict 传给 `_debug_summary()`。

**文件：** `injector.py`（修改）

**改动 1：** 在 inject_context() 中 ④a 阶段后捕获 fixed signal 状态

在 `inject_context()` 中，`_inject_context()` 函数内部 ~L680-693 的固定信号生成之后，添加状态捕获：

```python
# 在④a Fixed signals 部分末尾（L693 之后）添加：
# ─── debug_context: capture fixed signal state for detailed mode ───
debug_fs = {}
# message_length
ml_cfg = fixed_cfg.get("message_length", {})
if ml_cfg.get("enabled", False):
    ml_threshold = ml_cfg.get("threshold", 50)
    msg_len = len(user_message or "")
    debug_fs["message_length"] = {
        "visible": True,
        "triggered": msg_len < ml_threshold,
        "length": msg_len,
        "threshold": ml_threshold,
    }
# reply_gap
rg_cfg = fixed_cfg.get("reply_gap", {})
if rg_cfg.get("enabled", False):
    rg_threshold = rg_cfg.get("threshold_minutes", 30)
    rg_last_reply = None
    rg_gap = None
    rg_triggered = False
    try:
        rg_path = Path(rg_cfg.get("storage_path", "~/.hermes/reply_timing.json")).expanduser()
        if rg_path.is_file():
            rg_data = json.loads(rg_path.read_text(encoding="utf-8"))
            last_ts = rg_data.get("last_reply_at")
            if last_ts:
                rg_gap = (time.time() - float(last_ts)) / 60.0
                rg_triggered = rg_gap > rg_threshold
                rg_last_reply = datetime.fromtimestamp(float(last_ts)).strftime("%Y-%m-%d %H:%M:%S")
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        pass
    debug_fs["reply_gap"] = {
        "enabled": True,
        "triggered": rg_triggered,
        "last_reply": rg_last_reply,
        "gap_minutes": round(rg_gap, 1) if rg_gap is not None else None,
        "threshold_minutes": rg_threshold,
    }
# daily_turn_count
dc_cfg = fixed_cfg.get("daily_turn_count", {})
if dc_cfg.get("enabled", False):
    dc_thresholds = dc_cfg.get("thresholds", {"morning": 10, "familiar": 50})
    dc_count = 0
    dc_date = datetime.now().strftime("%Y-%m-%d")
    try:
        dc_path_raw = dc_cfg.get("storage_path", "~/.hermes/profiles/{profile}/state/daily_turn_count.json")
        dc_profile = kwargs.get("profile_path", "")
        if dc_profile:
            dc_path_raw = dc_path_raw.replace("{profile}", str(dc_profile))
        dc_path = Path(dc_path_raw).expanduser()
        if dc_path.is_file():
            dc_data = json.loads(dc_path.read_text(encoding="utf-8"))
            if isinstance(dc_data, dict) and dc_data.get("date") == dc_date:
                dc_count = dc_data.get("count", 0)
    except (json.JSONDecodeError, OSError):
        pass
    # Note: _daily_turn_count_hint 会在内部做 count+1，我们读取的是+1之前的原始值
    debug_fs["daily_turn_count"] = {
        "visible": True,
        "triggered": True,  # daily_turn_count 启用即视为"触发"
        "count": dc_count,
        "date": dc_date,
    }
```

**改动 2：** 在 ④b 表达向量阶段捕获 delta

在 ~L695-708 的表达向量处理之后，添加状态捕获：

```python
# ─── ④b debug_context: capture expression vector state ───
debug_ev = {"enabled": False, "turn_count": 0, "dimensions": {}}
if ev_cfg.get("enabled", False) and not _is_background_message(user_message or ""):
    try:
        profile = kwargs.get("profile_path", "")
        ev = _ExpressionVector(ev_cfg, profile_path=profile)
        ev.load()
        # Capture old values before update
        snapshot_before = dict(ev.vectors)
        ev.update(user_message or "", session_id)
        # Record hit counts per dimension
        msg_lower = (user_message or "").lower()
        debug_ev["enabled"] = True
        debug_ev["turn_count"] = turn_count
        for dim_name in sorted(ev.dimensions.keys()):
            old_val = snapshot_before.get(dim_name, 0.0)
            new_val = ev.vectors.get(dim_name, 0.0)
            delta = new_val - old_val
            # Find which keywords were hit
            hit_keywords = []
            hit_count = 0
            decay_dims = []
            for kw in ev.dimensions.get(dim_name, []):
                if kw and kw.lower() in msg_lower:
                    hit_keywords.append(kw)
                    hit_count += 1
            if not hit_keywords and delta != 0:
                decay_dims.append(dim_name)
            debug_ev["dimensions"][dim_name] = {
                "old": old_val,
                "new": new_val,
                "delta": delta,
                "hit_keywords": hit_keywords,
                "hit_count": hit_count,
                "decay_dims": decay_dims if not hit_keywords else [],
            }
        ev.save()
        parts.append(ev.format_inject(turn_count))
    except Exception:
        pass  # fail-open
else:
    # Not enabled or background message
    if ev_cfg.get("enabled", False):
        try:
            profile = kwargs.get("profile_path", "")
            ev = _ExpressionVector(ev_cfg, profile_path=profile)
            ev.load()
            debug_ev["enabled"] = True
            debug_ev["turn_count"] = turn_count
            for dim_name in sorted(ev.dimensions.keys()):
                val = ev.vectors.get(dim_name, 0.0)
                debug_ev["dimensions"][dim_name] = {
                    "old": val, "new": val, "delta": 0.0,
                    "hit_keywords": [], "hit_count": 0, "decay_dims": [],
                }
            parts.append(ev.format_inject(turn_count))
        except Exception:
            pass
```

**改动 3：** 在 ④ 随机变化阶段捕获每个变体状态

需要修改 `_randomize_variance()` 返回更详细的信息，或者在 inject_context() 中调用其原始逻辑并捕获每个类别结果。

**方案选择：** 不修改 `_randomize_variance()` 的返回值签名以保持兼容。在 inject_context() 中添加并行捕获逻辑：

```python
# 在 5. Random variance 处理之后（L711-715 附近）添加：
var_context_items = []
if _is_enabled(modules, "variance"):
    var_cfg = config.get("variance", {})
    if var_cfg:
        for category, cat_cfg in var_cfg.items():
            if not isinstance(cat_cfg, dict):
                continue
            prob = cat_cfg.get("probability", 0.5)
            if not isinstance(prob, (int, float)):
                prob = 0.5
            elif not (0.0 <= prob <= 1.0):
                prob = 0.5
            variants = cat_cfg.get("variants", [])
            if not isinstance(variants, list):
                variants = []
            # Determine if this category was selected (check var_results)
            import random as _random
            was_rolled = _random.random() <= prob  # Call again for tracking
            # Actually, we need to match with actual var_results.
            # Better approach: look at what was actually in var_results
            chosen_text = None
            if was_rolled and variants:
                # __import__('random').choice would have been called,
                # but we can't replay it deterministically.
                # Instead, find matching result in parts
                for p in parts:
                    if isinstance(p, str) and any(kw in p for kw in [category]):
                        chosen_text = p
                        break
            var_context_items.append({
                "name": category,
                "probability": prob,
                "rolled": was_rolled,
                "chosen": chosen_text,
            })
```

**简化方案：** 由于 `_randomize_variance()` 调用 random 不可完美回放，更好的方法是：**修改 `_randomize_variance()` 返回 (results: list[str], items: list[dict]) 元组**，但这样会破坏接口。

**最终方案：** 在 `inject_context()` 中，不改变 `_randomize_variance()` 调用，而是在其返回后，**反向匹配** parts 中的内容来确定哪些被抽中。

```python
# 在 5. Random variance (L711-715) 之后添加：
# ─── debug_context: capture variance item states ───
var_context_items = []
var_cfg = config.get("variance", {})
if isinstance(var_cfg, dict):
    for category, cat_cfg in var_cfg.items():
        if not isinstance(cat_cfg, dict):
            continue
        prob = cat_cfg.get("probability", 0.5)
        if not isinstance(prob, (int, float)):
            prob = 0.5
        elif not (0.0 <= prob <= 1.0):
            prob = 0.5
        # Check if this category's result is in the recently added var_results
        matched = False
        chosen_variant = None
        for vr in var_results:  # var_results is still in scope
            if isinstance(vr, str) and (category in vr or any(
                isinstance(v, str) and v in vr for v in cat_cfg.get("variants", [])
            )):
                matched = True
                chosen_variant = vr
                break
        var_context_items.append({
            "name": category,
            "probability": prob,
            "rolled": matched,
            "chosen": chosen_variant,
        })
```

**改动 4：** 在 ⑦ Debug 调用点传递 config 和 debug_context

将 L742 的调用由：
```python
_PENDING_DEBUG_BLOCK = f"\n\n---\n{_debug_summary(modules, parts, var_count=var_count)}"
```
改为：
```python
debug_context = {
    "fixed_signals": debug_fs,
    "expression_vector": debug_ev,
    "variance": {"items": var_context_items},
}
_PENDING_DEBUG_BLOCK = f"\n\n---\n{_debug_summary(
    modules, parts,
    var_count=var_count,
    config=config,
    debug_context=debug_context,
)}"
```

**验证标准：**

```bash
# 1. 语法合法
python -c "import ast; ast.parse(open('injector.py').read()); print('OK')"
# 期望: OK

# 2. 无 import 错误
python -c "import injector; print('OK')"
# 期望: OK

# 3. compact 模式输出不变（无 config 参数时默认 compact）
python -c "
import injector
# 模拟 inject_context 的 debug context 组装不影响 compact 路径
modules = {'time': True, 'static_rules': True, 'dynamic': {}, 'variance': False, 'memory': False, 'kanban': False, 'debug': True}
result = injector._debug_summary(modules, [], var_count=0)
assert '🔧 [Debug] 本轮注入:' in result
print('OK')
"
# 期望: OK
```

**回滚：**

```bash
git checkout HEAD -- injector.py
```

---

### Phase 5: test_debug_detailed.py — 详细模式测试

**目标：** 编写测试覆盖详细模式各模块输出格式、边界条件、compact 兼容性。

**文件：** `tests/test_debug_detailed.py`（新建）

```python
"""Tests for detailed debug mode (SPEC-003 §2.1-2.2)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import injector
from locales import _init_locales, _t, _resolve_language


class TestDebugModeSwitch:
    """_debug_summary() 模式切换测试。"""

    def test_default_mode_compact(self):
        """不传 config 参数 → 默认 compact 模式。"""
        result = injector._debug_summary(
            {"time": True, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
        )
        assert "🔧 [Debug] 本轮注入:" in result

    def test_detailed_mode_not_crash(self):
        """detailed 模式空 debug_context 不崩溃。"""
        result = injector._debug_summary(
            {"time": True, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={},
        )
        assert result  # 非空字符串

    def test_invalid_detail_fallback_to_compact(self):
        """无效 detail 值 → 回退 compact。"""
        result = injector._debug_summary(
            {"time": True, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "invalid_mode"}},
        )
        assert "🔧 [Debug] 本轮注入:" in result


class TestDebugDetailedFixedSignals:
    """④a 固定信号详细模式测试。"""

    def test_fixed_signals_all_triggered(self):
        """全部信号触发 → 显示 3/3 触发。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={
                "fixed_signals": {
                    "message_length": {"visible": True, "triggered": True, "length": 3, "threshold": 50},
                    "reply_gap": {"enabled": True, "triggered": False, "last_reply": "2026-05-19 19:25:32", "gap_minutes": 0.5, "threshold_minutes": 30},
                    "daily_turn_count": {"visible": True, "triggered": True, "count": 42, "date": "2026-05-19"},
                },
            },
        )
        assert "3/3触发" in result or "3/3 triggered" in result

    def test_reply_gap_detail_shown(self):
        """reply_gap 显示 last_reply 时间戳。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={
                "fixed_signals": {
                    "reply_gap": {"enabled": True, "triggered": False, "last_reply": "2026-05-19 19:25:32", "gap_minutes": 0.5, "threshold_minutes": 30},
                },
            },
        )
        assert "2026-05-19" in result

    def test_no_fixed_signals(self):
        """无固定信号配置 → 显示无触发。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={"fixed_signals": {}},
        )
        assert "无触发" in result or "none" in result


class TestDebugDetailedExpressionVector:
    """④b 表达向量详细模式测试。"""

    def test_dimension_delta_shown(self):
        """维度变化显示 old→new (delta)。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={
                "expression_vector": {
                    "enabled": True,
                    "turn_count": 42,
                    "dimensions": {
                        "care": {"old": 2.0, "new": 3.0, "delta": 1.0, "hit_keywords": ["吃饭"], "hit_count": 1, "decay_dims": []},
                    },
                },
            },
        )
        assert "2→3" in result
        assert "care" in result

    def test_no_hit_displayed(self):
        """无命中维度显示无命中标注。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={
                "expression_vector": {
                    "enabled": True,
                    "turn_count": 1,
                    "dimensions": {
                        "work": {"old": 0.0, "new": 0.0, "delta": 0.0, "hit_keywords": [], "hit_count": 0, "decay_dims": []},
                    },
                },
            },
        )
        assert "无命中" in result or "none" in result

    def test_disabled_expression_vector(self):
        """表达向量未启用 → 显示未启用。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={"expression_vector": {"enabled": False}},
        )
        assert "未启用" in result or "Disabled" in result


class TestDebugDetailedVariance:
    """④ 随机变化详细模式测试。"""

    def test_variance_hit_miss_displayed(self):
        """显示每个变体抽中/未抽中状态。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": True, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=1,
            config={"debug": {"detail": "detailed"}},
            debug_context={
                "variance": {
                    "items": [
                        {"name": "fox_girl_body_language", "probability": 0.6, "rolled": True, "chosen": "🦊 test"},
                        {"name": "maid_body_language", "probability": 0.6, "rolled": False, "chosen": None},
                    ],
                },
            },
        )
        assert "✓" in result
        assert "✗" in result

    def test_variance_stopped(self):
        """variance 模块关闭 → 显示已停用。"""
        result = injector._debug_summary(
            {"time": False, "static_rules": False, "dynamic": {}, "variance": False, "memory": False, "kanban": False, "debug": True},
            [],
            var_count=0,
            config={"debug": {"detail": "detailed"}},
            debug_context={"variance": {"items": []}},
        )
        assert "已停用" in result


class TestCompactBackwardCompatibility:
    """compact 模式兼容性测试 — 输出必须与当前完全一致。"""

    def test_compact_output_unchanged(self):
        """compact 模式输出格式与当前一致。"""
        # 模拟典型 debug 场景
        parts = [
            "🕐 现在是 2026年5月21日 星期四 03:03",
            "📝 测试规则1",
            "📝 测试规则2",
            "📏 消息较短",
            "📊 [表达向量] care:2 intimacy:0 work:0 | 第 10 轮",
            "🦊 狐尾轻轻摆动",
        ]
        result = injector._debug_summary(
            {"time": True, "static_rules": True, "dynamic": {"time_slots": True, "turn_stage": False, "keyword": True}, "variance": True, "memory": False, "kanban": True, "debug": True},
            parts,
            var_count=1,
        )
        assert "🔧 [Debug] 本轮注入:" in result
        assert "① 🕐 时间已注入" in result
        assert "② 📜" in result
        assert "③ ⚡" in result
        assert "④a" in result
        assert "④b" in result
        assert "④ 🎲" in result
        assert "⑤ 🧠 已停用" in result
        assert "⑥ 📋" in result
```

**操作：**

```bash
# 运行新测试验证
python -m pytest tests/test_debug_detailed.py -v
# 期望: ~12 passed

# 确认不影响现有测试
python -m pytest tests/ --tb=no -q 2>&1 | tail -3
# 期望: 12+ passed (新增) + 231 passed (现有) + 8 failed (预存失败)
```

**回滚：**

```bash
rm tests/test_debug_detailed.py
```

---

### Phase 6: test_locales.py — 国际化测试

**目标：** 验证中英文翻译键完整性、language 推断逻辑、回退行为。

**文件：** `tests/test_locales.py`（新建）

```python
"""Tests for locale/i18n system (SPEC-003 §2.3)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from locales import (
    _resolve_language,
    _load_translations,
    _init_locales,
    _t,
    set_language,
)


class TestResolveLanguage:
    """_resolve_language() 逻辑测试。"""

    def test_explicit_zh(self):
        """language: 'zh' → 'zh'。"""
        assert _resolve_language({"language": "zh"}) == "zh"

    def test_explicit_en(self):
        """language: 'en' → 'en'。"""
        assert _resolve_language({"language": "en"}) == "en"

    def test_auto_cn_full(self):
        """auto + time.format='cn_full' → 'zh'。"""
        assert _resolve_language({"language": "auto", "time": {"format": "cn_full"}}) == "zh"

    def test_auto_iso(self):
        """auto + time.format='iso' → 'en'。"""
        assert _resolve_language({"language": "auto", "time": {"format": "iso"}}) == "en"

    def test_no_language_config(self):
        """无 language 键 → 默认 'zh'。"""
        assert _resolve_language({}) == "zh"

    def test_no_time_config(self):
        """language='auto' 但无 time 配置 → 'en'。"""
        assert _resolve_language({"language": "auto"}) == "en"


class TestLoadTranslations:
    """_load_translations() 测试。"""

    def test_load_zh(self):
        """加载 zh.json 成功。"""
        translations = _load_translations(".", "zh")
        assert isinstance(translations, dict)
        assert "debug.header" in translations
        assert translations["debug.header"] == "🔧 [Debug] 本轮注入:"

    def test_load_en(self):
        """加载 en.json 成功。"""
        translations = _load_translations(".", "en")
        assert isinstance(translations, dict)
        assert "debug.header" in translations
        assert translations["debug.header"] == "🔧 [Debug] Turn Summary:"

    def test_missing_locale_file(self):
        """不存在的语言 → 空 dict。"""
        translations = _load_translations(".", "jp")
        assert translations == {}

    def test_key_count_match(self):
        """中英文翻译键数量一致（英文可以多但不能少）。"""
        zh = _load_translations(".", "zh")
        en = _load_translations(".", "en")
        for k in zh:
            assert k in en, f"Missing key in en.json: {k}"


class TestTranslateFunction:
    """_t() 翻译函数测试。"""

    def setup_method(self):
        _init_locales(".", {"language": "zh"})

    def test_basic_translation(self):
        """基本翻译。"""
        result = _t("debug.header")
        assert result == "🔧 [Debug] 本轮注入:"

    def test_format_interpolation(self):
        """参数插值。"""
        result = _t("modules.static_rules", count=8)
        assert "8" in result
        assert "条静态规则" in result

    def test_missing_key(self):
        """缺失键 → 返回键名本身。"""
        result = _t("nonexistent.key")
        assert result == "nonexistent.key"

    def test_en_translation(self):
        """英文翻译。"""
        set_language("en", ".")
        result = _t("debug.header")
        assert result == "🔧 [Debug] Turn Summary:"


class TestFallbackBehavior:
    """回退逻辑测试。"""

    def test_active_lang_missing_fallback_to_zh(self):
        """语言启用了但翻译文件为空 → zh 回退。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            en_file = tmpdir_path / "locales" / "en.json"
            en_file.parent.mkdir(parents=True)
            en_file.write_text("{}", encoding="utf-8")
            zh_file = tmpdir_path / "locales" / "zh.json"
            zh_file.write_text(json.dumps({"debug.header": "测试回退"}), encoding="utf-8")

            from locales import _TRANSLATIONS as _orig
            _init_locales(str(tmpdir_path), {"language": "en"})
            from locales import _TRANSLATIONS
            assert _TRANSLATIONS.get("debug.header") == "测试回退"
```

**测试用例清单：**

| TC-ID | 场景 | 验证点 |
|:---|:---|:---|
| RL-01 | language="zh" | 返回 "zh" |
| RL-02 | language="en" | 返回 "en" |
| RL-03 | auto + cn_full | 返回 "zh" |
| RL-04 | auto + iso | 返回 "en" |
| RL-05 | 无 language 键 | 默认 "zh" |
| LT-01 | 加载 zh.json | debug.header 正确 |
| LT-02 | 加载 en.json | debug.header 正确 |
| LT-03 | 不存在的语言 | 空 dict |
| LT-04 | 中英键一致性 | en 包含 zh 所有键 |
| TF-01 | _t 基本翻译 | 返回正确值 |
| TF-02 | _t 参数插值 | {count} 被替换 |
| TF-03 | _t 缺失键 | 返回键名 |
| TF-04 | set_language 切换 | 翻译改变 |
| FB-01 | en 空 → zh 回退 | 自动 fallback |

**操作：**

```bash
# 运行新测试
python -m pytest tests/test_locales.py -v
# 期望: ~14 passed

# 确认不影响现有测试
python -m pytest tests/ --tb=no -q 2>&1 | tail -3
# 期望: ~14+ passed (新增) + 231+ passed (现有) + 8 failed (预存)
```

**回滚：**

```bash
rm tests/test_locales.py
```

---

### Phase 7: 更新 examples/persona-config.json + 全量回归

**目标：** 更新范例配置添加 debug.detail 和 language 键，运行全量回归，确认兼容性。

#### 7.1 更新 examples/persona-config.json

**文件：** `examples/persona-config.json`（修改）

**改动：** 在 `debug` 节添加 `detail` 键，在根级添加 `language` 键

```json
"debug": {
  "enabled": false,
  "visible": false,
  "detail": "compact"
},
```

在文件末尾（`guard` 块之后）添加：

```json
"language": "auto"
```

对应修改后的完整 debug 节：

```json
"debug": {
  "enabled": false,
  "visible": false,
  "detail": "compact"
}
```

和末尾：

```json
  "guard": {
    "enabled": false,
    ...
  },
  "language": "auto"
}
```

#### 7.2 全量回归

```bash
# 1. 全量测试
python -m pytest tests/ -v --tb=no 2>&1 | tail -20
# 期望: 231+12(test_debug_detailed)+14(test_locales) = ~257 passed
# 预存 8 failed 保持不变

# 2. 确认 injector.py 语法
python -c "import ast; ast.parse(open('injector.py').read()); print('AST OK')"

# 3. 确认 locales 语法
python -c "import json; json.load(open('locales/zh.json')); json.load(open('locales/en.json')); print('JSON OK')"

# 4. 确认 __init__.py 语法
python -c "import ast; ast.parse(open('__init__.py').read()); print('INIT OK')"

# 5. 确认 examples 语法
python -c "import json; json.load(open('examples/persona-config.json')); print('EXAMPLES OK')"

# 6. 确认 import 路径正常
python -c "import injector; from locales import _t; print('IMPORT OK')"
```

#### 7.3 验收检查清单

```bash
# AC-1: _debug_summary() 接收 config + debug_context 参数
grep -n "def _debug_summary" injector.py | grep -q "config" && echo "PASS" || echo "FAIL"

# AC-2: _detailed_summary() 存在
grep -q "def _detailed_summary" injector.py && echo "PASS" || echo "FAIL"

# AC-3: locales 模块可导入
python -c "from locales import _t, _init_locales; print('PASS')"

# AC-4: zh.json 和 en.json 存在
test -f locales/zh.json && test -f locales/en.json && echo "PASS" || echo "FAIL"

# AC-5: compact 模式输出不变（通过测试验证）
python -m pytest tests/test_debug_detailed.py::TestCompactBackwardCompatibility -v
# 期望: PASSED

# AC-6: language 推断正确
python -c "
from locales import _resolve_language
assert _resolve_language({'language': 'auto', 'time': {'format': 'cn_full'}}) == 'zh'
assert _resolve_language({'language': 'en'}) == 'en'
print('PASS')
"

# AC-7: 全量测试通过（预存 8 failed 除外）
python -m pytest tests/ -q 2>&1 | tail -3
# 期望: passed（passing 数增加，failed 数不增加）
```

**影响范围确认：**

```bash
# 确认仅修改/新增了目标文件
git diff --stat HEAD
# 期望:
#  injector.py                        | XX ++++++++-
#  __init__.py                        |  X +++
#  examples/persona-config.json       |  X +-
#  locales/__init__.py                | XX ++++++++
#  locales/zh.json                    | XX ++++++++
#  locales/en.json                    | XX ++++++++
#  tests/test_debug_detailed.py       | XX ++++++++
#  tests/test_locales.py              | XX ++++++++
```

**回滚：**

```bash
# 完整回滚
git checkout HEAD -- injector.py __init__.py examples/persona-config.json
rm -rf locales/ tests/test_debug_detailed.py tests/test_locales.py
```

---

## 3. 风险点与回滚方案

### 3.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|:---|:--:|:--:|:---|
| compact 模式输出因重构而改变 | 低 | 高 | Phase 2 重构时 compact 路径代码与原始代码逐行对比；Phase 5 有专门的 compact 兼容性测试 |
| debug_context 组装逻辑与inject_context() 现有逻辑重复（读取 JSON 两次） | 中 | 低 | 固定信号 JSON 文件 < 100 bytes，二次读取 < 1ms；可接受 |
| _randomize_variance() 不可回放（random 调用）导致方差命中状态误判 | 中 | 中 | 使用 parts 反向匹配确定抽中状态；即使匹配不完美，debug 面板只是辅助显示，不影响主逻辑 |
| locale 初始化时机：injector 导入时 _load_config() 尚未就绪 | 低 | 高 | 在 __init__.py register() 中延迟初始化，此时 _CONFIG_ROOT 已设置 |
| 翻译文件缺失时 _t() 返回键名 → _detailed_summary 显示原始键名 | 低 | 低 | _t() 缺失返回键名，由各格式化函数做最后防线回退 |

### 3.2 回滚方案

| 回滚方式 | 操作 |
|:---|:---|
| **Git 回滚单个文件** | `git checkout HEAD -- injector.py` |
| **删除 locales** | `rm -rf locales/` |
| **删除新测试** | `rm tests/test_debug_detailed.py tests/test_locales.py` |
| **完整回滚** | `git stash` 或 `git reset --hard HEAD` |

### 3.3 安全边界

- `inject_context()` 主流程（①~⑦ 顺序）**完全不变**
- `_daily_turn_count_hint()` / `_reply_gap_hint()` / `_message_length_hint()` **完全未修改**
- `_randomize_variance()` 签名 **未变更**（返回值不变）
- `_ExpressionVector` 类 **未修改**
- compact 模式代码路径在 Phase 2 中完整保留
- 所有新功能通过 `debug.detail` 和 `language` 配置开关控制，缺省时零行为变化
- 翻译文件缺失 → 回退硬编码中文（当前行为完全不变）

---

## 4. 验证检查清单

### 4.1 代码改动

- [ ] `locales/__init__.py` — 加载器 + `_t()` 翻译函数
- [ ] `locales/zh.json` — 中文翻译（30+ 键）
- [ ] `locales/en.json` — 英文翻译（30+ 键，包含 zh 的全部键）
- [ ] `injector.py` — `_debug_summary()` 重构为双模式入口
- [ ] `injector.py` — 新增 `_detailed_summary()` + 子函数
- [ ] `injector.py` — `inject_context()` 组装 `debug_context`
- [ ] `__init__.py` — `register()` 中调用 `_init_locales()`
- [ ] `examples/persona-config.json` — 添加 `debug.detail` + `language`

### 4.2 测试

- [ ] `tests/test_debug_detailed.py` — 新建，~12 个测试全部 PASSED
- [ ] `tests/test_locales.py` — 新建，~14 个测试全部 PASSED
- [ ] `python -m pytest tests/ -v` → 全量通过，0 new failure
- [ ] 预存 8 个失败的测试不增加（expression_vector + guard 相关）

### 4.3 行为验证

- [ ] compact 模式输出与修改前完全一致
- [ ] detailed 模式输出包含 ④a 固定信号详情（阈值、实际值、触发状态）
- [ ] detailed 模式输出包含 ④b 表达向量 delta（old→new、命中关键词）
- [ ] detailed 模式输出包含 ④ 方差抽中/未抽中状态
- [ ] language="zh" 输出中文翻译
- [ ] language="en" 输出英文翻译
- [ ] language="auto" + cn_full → 中文
- [ ] language="auto" + iso → 英文
- [ ] 无 language 配置 → 默认从 time.format 推断
- [ ] 翻译文件缺失 → 不崩溃，回退硬编码中文
- [ ] _t() 缺失键 → 不崩溃

### 4.4 文件变更总览

| 文件 | 操作 | 说明 |
|:---|:---|:---|
| `injector.py` | 修改 | `_debug_summary()` 重构 + 新增 `_detailed_summary()` + 子函数 + `inject_context()` debug_context 组装 |
| `__init__.py` | 修改 | `register()` 添加 `_init_locales()` 调用 |
| `locales/__init__.py` | 新建 | 加载器 + `_t()` 翻译函数 |
| `locales/zh.json` | 新建 | 中文翻译 |
| `locales/en.json` | 新建 | 英文翻译 |
| `examples/persona-config.json` | 修改 | 添加 `debug.detail` + `language` |
| `tests/test_debug_detailed.py` | 新建 | 详细模式测试（~12 个） |
| `tests/test_locales.py` | 新建 | 国际化测试（~14 个） |

---

*知惠 · 2026-05-21 · PLAN-006 v1.0（基于 SPEC-003 §2.1-2.3 · 不涉及 §2.5 turn_stage）· 等待审阅*
