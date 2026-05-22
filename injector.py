"""Persona context injector: config loading, time generation, rule assembly.

Core module of hermes-persona. Provides the inject_context() entry point
called by the Hermes runtime on every pre_llm_call hook.
"""

from __future__ import annotations

import json
import os
import re
import time
import traceback
from datetime import datetime
from pathlib import Path

import config as _config

from dynamic_rules import (
    _get_time_slot_desc,
    _get_turn_stage_hint,
    _select_dynamic_rules,
)
from expression_vector import _ExpressionVector, _is_background_message
from variance import _randomize_variance

# ---------------------------------------------------------------------------
# Pending debug block for transform_llm_output hook
# NOTE: module-level variable is not thread-safe; assumes single-session runtime
# ---------------------------------------------------------------------------
_PENDING_DEBUG_BLOCK: str | None = None

# ---------------------------------------------------------------------------
# Diagnostic trace (remove after debugging)
# ---------------------------------------------------------------------------

def _trace(source: str, msg: str) -> None:
    """Append a diagnostic line to /tmp/hermes_persona_trace.log."""
    if not os.environ.get("HERMES_PERSONA_TRACE"):
        return
    try:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with open("/tmp/hermes_persona_trace.log", "a") as f:
            f.write(f"{ts} [{source}] {msg}\n")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Module registry
# ---------------------------------------------------------------------------

_MODULE_REGISTRY: dict[str, dict] = {
    "time": {
        "description": "时间上下文注入",
        "default": True,
        "phase": 1,
        "legacy_key": "time",
        "legacy_path": ("time", "enabled"),
    },
    "static_rules": {
        "description": "静态规则注入（context.rules + rules_first_turn_only）",
        "default": True,
        "phase": 2,
        "legacy_key": None,
        "legacy_path": None,
    },
    "dynamic": {
        "description": "动态规则总开关（任一子通道开启时才进入）",
        "default": True,
        "phase": 3,
        "legacy_key": None,
        "legacy_path": None,
    },
    "variance": {
        "description": "随机表达变化注入",
        "default": True,
        "phase": 4,
        "legacy_key": None,
        "legacy_path": None,
    },
    "memory": {
        "description": "记忆召回注入",
        "default": False,
        "phase": 5,
        "legacy_key": "memory",
        "legacy_path": ("memory", "enabled"),
    },
    "kanban": {
        "description": "看板状态注入（仅首轮）",
        "default": False,
        "phase": 6,
        "legacy_key": "project",
        "legacy_path": ("project", "enabled"),
    },
    "debug": {
        "description": "Debug Mode — 在注入上下文末尾追加人类可读的注入摘要",
        "default": False,
        "phase": 7,
        "legacy_key": None,
        "legacy_path": None,
    },
    "translate": {
        "description": "注入规则转译 — 自然语言拼装替代逐模块堆叠",
        "default": False,
        "phase": 8,
        "legacy_key": None,
        "legacy_path": None,
    },
}

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def _load_config() -> dict:
    """Load persona-config.json and return the "hermes-persona" sub-tree.

    Returns {} on any failure (degraded minimal-viability mode).

    Lookup order:
        1. _CONFIG_ROOT / "persona-config.json"  (set by register())
        2. Path(__file__).resolve().parents[3] / "persona-config.json"  (fallback)
    """
    config_path = _config._resolve_config_path("persona-config.json")
    if config_path is None:
        # L3 fallback: repo 根目录（pytest 等场景）
        config_path = Path(__file__).resolve().parents[2] / "persona-config.json"

    try:
        if not config_path.is_file():
            return {}
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return data.get("hermes-persona", {})
    except (json.JSONDecodeError, OSError):
        # Any parse or I/O error → degrade gracefully
        return {}


# ---------------------------------------------------------------------------
# Module switch helpers
# ---------------------------------------------------------------------------


def _resolve_modules(config: dict) -> dict:
    """解析 modules 配置，优先新格式，回退旧格式合成。

    返回值始终为 dict（保证调用方无需判空）。
    """
    try:
        modules = config.get("modules")
        if isinstance(modules, dict):
            return modules

        synthesized: dict[str, bool] = {}
        for key, meta in _MODULE_REGISTRY.items():
            lp = meta.get("legacy_path")
            if lp:
                section = config.get(lp[0])
                if isinstance(section, dict):
                    synthesized[key] = section.get(lp[1], meta["default"])
                else:
                    synthesized[key] = meta["default"]
            else:
                synthesized[key] = meta["default"]
        return synthesized
    except (TypeError, KeyError, AttributeError):
        return {}


def _is_enabled(modules: dict, key: str) -> bool:
    """判断指定模块是否启用。

    key 不在 modules 中时回退注册表 default。
    key 不在注册表中时返回 True（fail-open）。

    当值为 dict 时，检查其中的 ``enabled`` 子键；
    若无 ``enabled`` 子键则默认启用（向后兼容 dynamic 等纯子通道配置）。
    """
    if key in modules:
        val = modules[key]
        if isinstance(val, dict):
            return val.get("enabled", True)
        return bool(val)
    return _MODULE_REGISTRY.get(key, {}).get("default", True)


def _has_any_dynamic(modules: dict) -> bool:
    """判断 dynamic 模块的子通道中是否至少有一个开启。

    仅当父开关和至少一个子通道同时开启时返回 True。
    """
    if not _is_enabled(modules, "dynamic"):
        return False

    dyn = modules.get("dynamic", {})
    if isinstance(dyn, dict):
        return (
            dyn.get("time_slots", True)
            or dyn.get("turn_stage", True)
            or dyn.get("keyword", True)
        )
    return True


# ---------------------------------------------------------------------------
# Time context generation
# ---------------------------------------------------------------------------

_WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


def _time_context(fmt: str = "cn_full") -> str:
    """Generate a time-description string for the current moment.

    Supported formats:
        "cn_full"  → "🕐 2026年5月16日 周五 14:30"
        "iso"      → "🕐 2026-05-16T14:30:00"
        "compact"  → "🕐 05/16 14:30"
    Unknown format falls back to "cn_full".
    """
    now = datetime.now()
    if fmt == "iso":
        return f"🕐 {now.isoformat()}"
    elif fmt == "compact":
        return f"🕐 {now.strftime('%m/%d %H:%M')}"
    else:
        # "cn_full" or unknown → Chinese full format
        weekday = _WEEKDAY_CN[now.weekday()]
        return f"🕐 {now.year}年{now.month}月{now.day}日 周{weekday} {now.strftime('%H:%M')}"


# ---------------------------------------------------------------------------
# Static rule injection
# ---------------------------------------------------------------------------


def _inject_static_rules(ctx_cfg: dict, is_first_turn: bool) -> list[str]:
    """Extract static rules from context configuration.

    - context.rules: injected every turn.
    - context.rules_first_turn_only: injected only on the first turn.

    Returns list of rule strings.
    """
    rules: list[str] = []
    rules.extend(ctx_cfg.get("rules", []))
    if is_first_turn:
        rules.extend(ctx_cfg.get("rules_first_turn_only", []))
    return rules


# ---------------------------------------------------------------------------
# Debug mode helpers
# ---------------------------------------------------------------------------


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
        if isinstance(dyn, dict):
            sub_parts = []
            for key in ("time_slots", "turn_stage", "keyword"):
                status = "on" if dyn.get(key, True) else "off"
                sub_parts.append(f"{key}: {status}")
            sub_status = " / ".join(sub_parts)
        else:
            sub_status = "on" if dyn else "off"
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
            "dimensions": {
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
        static_rules = debug_context.get("static_rules", [])
        if static_rules:
            lines.append(f"  ② 📜 {len(static_rules)}条静态规则:")
            for r in static_rules:
                lines.append(f"     {r}")
        else:
            lines.append(f"  ② 📜 {_t('modules.static_rules', count=0)}")
    else:
        lines.append(f"  ② 📜 {_t('modules.static_rules.stopped')}")

    # ③ Dynamic
    if _is_enabled(modules, "dynamic"):
        dynamic_rules = debug_context.get("dynamic_rules", [])
        if dynamic_rules:
            lines.append(f"  ③ ⚡ {len(dynamic_rules)}条动态规则触发:")
            for r in dynamic_rules:
                lines.append(f"     {r}")
        else:
            lines.append("  ③ ⚡ 无规则触发")
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
    from locales import _t as _tl

    fs_enabled = bool(fs)  # non-empty means at least one signal configured
    if not fs_enabled:
        lines.append(f"  ④a 📏⏱️ {_tl('modules.fixed_signals.none')}")
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
            detail = _tl("signal.message_length.triggered", length=length, threshold=threshold)
        else:
            detail = _tl("signal.message_length.idle", length=length, threshold=threshold)
        lines.append(f"    📏 {detail}")

    # reply_gap
    rg = fs.get("reply_gap", {})
    if rg.get("enabled", False):
        total += 1
        if rg.get("triggered", False):
            triggered += 1
            gap = rg.get("gap_minutes", 0)
            threshold = rg.get("threshold_minutes", 30)
            detail = _tl("signal.reply_gap.triggered", gap=round(gap, 1), threshold=threshold)
        else:
            detail = _tl("signal.reply_gap.idle")
        lines.append(f"    🎵 {detail}")
        # Always show last_reply detail for reply_gap if available
        last_reply = rg.get("last_reply")
        if last_reply:
            gap_minutes = rg.get("gap_minutes", 0)
            threshold = rg.get("threshold_minutes", 30)
            detail_line = _tl(
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
            detail = _tl("signal.daily_turn.triggered", count=count)
        else:
            detail = _tl("signal.daily_turn.idle", count=count)
        lines.append(f"    📊 {detail}")
        date = dc.get("date", "")
        if date:
            detail_line = _tl("signal.daily_turn.detail", date=date, count=count)
            lines.append(f"       {detail_line}")

    # Header line
    if total > 0:
        header = _tl("modules.fixed_signals.triggered", triggered=triggered, total=total)
        # Insert header line before the indented sub-lines
        insert_pos = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].startswith("    ④a") or lines[i].startswith("  ④a"):
                insert_pos = i
                break
        # If we didn't find an existing ④a line, append
        if insert_pos == len(lines):
            lines.append(f"  ④a 📏⏱️ {header}")
        else:
            lines[insert_pos] = f"  ④a 📏⏱️ {header}"


def _fmt_detailed_expression_vector(lines: list[str], ev: dict) -> None:
    """Format expression vector section for detailed debug output."""
    from locales import _t as _tl

    if not ev.get("enabled", False):
        lines.append(f"  ④b 📊 {_tl('modules.expression_vector.disabled')}")
        return

    turn_count = ev.get("turn_count", 0)
    header = _tl("modules.expression_vector", turn_count=turn_count)
    lines.append(f"  ④b 📊 {header}")

    dimensions = ev.get("dimensions", {})
    for dim_name in sorted(dimensions.keys()):
        dim = dimensions[dim_name]
        old_val = round(dim.get("old", 0))
        new_val = round(dim.get("new", 0))
        delta_val = dim.get("delta", new_val - old_val)
        sign = "+" if delta_val >= 0 else ""
        hit_keywords = dim.get("hit_keywords", [])
        hit_count = dim.get("hit_count", 0)
        decay_dims = dim.get("decay_dims", [])

        if old_val != new_val:
            base = f"  {dim_name}: {old_val}→{new_val} ({sign}{int(delta_val)})"
        else:
            base = f"  {dim_name}: {new_val}"

        if hit_keywords and hit_count > 0:
            kw_str = ", ".join(hit_keywords)
            base += f"  ← {_tl('modules.expression_vector.hit', keywords=kw_str, count=hit_count)}"
        elif decay_dims:
            base += f"  ← {_tl('modules.expression_vector.decay', dims=', '.join(decay_dims), count=hit_count)}"
        else:
            base += f"  ← {_tl('modules.expression_vector.no_hit')}"

        lines.append(base)


def _fmt_detailed_variance(lines: list[str], var_context: dict, modules: dict) -> None:
    """Format variance section for detailed debug output."""
    from locales import _t as _tl

    if not _is_enabled(modules, "variance"):
        lines.append(f"  ④ 🎲 {_tl('modules.variance.stopped')}")
        return

    items = var_context.get("items", [])
    if not items:
        lines.append(f"  ④ 🎲 {_tl('modules.variance.none')}")
        return

    hits = sum(1 for item in items if item.get("rolled", False))
    total = len(items)
    header = _tl("modules.variance.hit", hit=hits, total=total)
    lines.append(f"  ④ 🎲 {header}")

    for item in items:
        name = item.get("name", "unknown")
        prob = item.get("probability", 0.0)
        if item.get("rolled", False):
            chosen = item.get("chosen", "")
            detail = _tl("variance.hit", name=name, prob=prob, chosen=chosen)
            lines.append(f"    ✓ {detail}")
        else:
            detail = _tl("variance.miss", name=name, prob=prob)
            lines.append(f"    ✗ {detail}")


def _count_static_rules_in_parts(parts: list[str]) -> int:
    """Count items in parts produced by _inject_static_rules."""
    try:
        # Static rules are plain strings (no emoji prefix from time/variance/etc.)
        count = 0
        for part in parts:
            if not isinstance(part, str):
                continue
            # Skip parts that are clearly from other modules
            if part.startswith("🕐") or part.startswith("📝") or part.startswith("📋"):
                continue
            if part.startswith("🕐 [") or part.startswith("💬 ["):
                continue
            # Each static rule is a separate element in parts
            count += 1
        return count
    except Exception:
        return 0


def _fmt_dynamic_sub_status(dyn_dict) -> str:
    """Format dynamic subchannel status string for compact/debug display."""
    try:
        if not isinstance(dyn_dict, dict):
            return "on" if dyn_dict else "off"
        parts = []
        for key in ("time_slots", "turn_stage", "keyword"):
            status = "on" if dyn_dict.get(key, True) else "off"
            parts.append(f"{key}: {status}")
        return " / ".join(parts)
    except Exception:
        return "on"



def _fmt_kanban_debug(parts: list[str]) -> str:
    """Extract kanban items from parts and show summary."""
    try:
        for part in parts:
            if isinstance(part, str) and part.startswith("📋"):
                # Extract the first 2 lines after header
                lines = part.split("\n")
                items = [l.lstrip("- ").strip() for l in lines[1:] if l.startswith("- ")]
                if items:
                    return " / ".join(items[:2])
                return "无条目"
        return "无数据"
    except Exception:
        return "无数据"


# ---------------------------------------------------------------------------
# Fixed signal helpers
# ---------------------------------------------------------------------------


def _message_length_hint(user_message: str, fixed_cfg: dict) -> str | None:
    """检查消息长度，短消息注入提示。

    Args:
        user_message: 用户当前消息文本。
        fixed_cfg: fixed_signals 配置节。

    Returns:
        "📏 消息较短" 或 None。
    """
    ml_cfg = fixed_cfg.get("message_length", {})
    if not ml_cfg.get("enabled", False):
        return None

    threshold = ml_cfg.get("threshold", 50)
    if not isinstance(threshold, (int, float)):
        threshold = 50

    if len(user_message) < threshold:
        return "📏 消息较短"
    return None


def _reply_gap_hint(fixed_cfg: dict) -> tuple[str | None, float]:
    """检查回复间隔，长时间未回复注入欢迎回来提示。

    Args:
        fixed_cfg: fixed_signals 配置节。

    Returns:
        (hint_text_or_None, now_timestamp)
    """
    rg_cfg = fixed_cfg.get("reply_gap", {})
    if not rg_cfg.get("enabled", False):
        return None, time.time()

    threshold_minutes = rg_cfg.get("threshold_minutes", 30)
    if not isinstance(threshold_minutes, (int, float)):
        threshold_minutes = 30

    now = time.time()
    rg_default = str(Path(__file__).resolve().parent / "state" / "reply_timing.json")
    raw_path = rg_cfg.get("storage_path", "") or rg_default
    storage_path = Path(raw_path).expanduser()

    hint = None
    try:
        if storage_path.is_file():
            data = json.loads(storage_path.read_text(encoding="utf-8"))
            last_reply_at = data.get("last_reply_at")
            if last_reply_at:
                gap_minutes = (now - float(last_reply_at)) / 60.0
                if gap_minutes > threshold_minutes:
                    hint = "🎵 欢迎回来"
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        pass

    return hint, now


def _save_reply_timing(fixed_cfg: dict, now_ts: float) -> None:
    """将 last_reply_at 写回磁盘。

    Args:
        fixed_cfg: fixed_signals 配置节。
        now_ts: 当前时间戳（由 _reply_gap_hint 返回）。
    """
    rg_cfg = fixed_cfg.get("reply_gap", {})
    if not rg_cfg.get("enabled", False):
        return

    rg_default = str(Path(__file__).resolve().parent / "state" / "reply_timing.json")
    raw_path = rg_cfg.get("storage_path", "") or rg_default
    storage_path = Path(raw_path).expanduser()

    try:
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"last_reply_at": now_ts}
        storage_path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def _daily_turn_count_hint(fixed_cfg: dict, profile_path: str = "") -> str | None:
    """检查当日累计轮数，注入轮数感知信号。

    每日轮数在跨会话间累积（同一自然日内的所有消息）。
    日期跨越时自动归零。信号用于告知角色当日互动深度。

    Args:
        fixed_cfg: fixed_signals 配置节。
        profile_path: profile path for {profile} placeholder substitution.

    Returns:
        \"📊 今日第N轮 — …\" 或 None。
    """
    dc_cfg = fixed_cfg.get("daily_turn_count", {})
    if not dc_cfg.get("enabled", False):
        return None

    today_key = datetime.now().strftime("%Y-%m-%d")
    dc_default = str(Path(__file__).resolve().parent / "state" / "daily_turn_count.json")
    raw_path = dc_cfg.get("storage_path", "") or dc_default
    if profile_path:
        raw_path = raw_path.replace("{profile}", str(profile_path))
    storage_path = Path(raw_path).expanduser()

    # 读取或初始化
    data: dict = {"date": today_key, "count": 0}

    # 旧默认路径 fallback（SPEC 4.3）：新路径不存在时尝试从旧默认路径读取
    load_path = storage_path
    if not load_path.is_file():
        _OLD_DEFAULT_TEMPLATE = "~/.hermes/profiles/{profile}/state/daily_turn_count.json"
        old_default = Path(_OLD_DEFAULT_TEMPLATE.replace("{profile}", profile_path or "")).expanduser()
        if old_default.is_file():
            load_path = old_default

    try:
        if load_path.is_file():
            saved = json.loads(load_path.read_text(encoding="utf-8"))
            if isinstance(saved, dict) and saved.get("date") == today_key:
                data = saved
            # 日期变化 → 自动归零
    except (json.JSONDecodeError, OSError):
        pass

    # 递增
    data["count"] = data.get("count", 0) + 1

    # 持久化
    try:
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass

    count = data["count"]
    thresholds = dc_cfg.get("thresholds", {"morning": 10, "familiar": 50})

    if count <= thresholds.get("morning", 10):
        return f"📊 今日第{count}轮"
    elif count <= thresholds.get("familiar", 50):
        return f"📊 今日第{count}轮"
    else:
        return f"📊 今日第{count}轮 — 深度陪伴日"


# ---------------------------------------------------------------------------
# Stub functions (P2 / P3)
# ---------------------------------------------------------------------------


def _recall_memories(user_message: str, mem_cfg: dict) -> str | None:
    """Recall relevant memories from an external memory API.

    Args:
        user_message: The user's current message (used as query).
        mem_cfg: Memory configuration dict with keys:
            - enabled (bool): must be True.
            - api_url (str): POST endpoint URL.
            - max_results (int): max memories to fetch (default 3).

    Returns:
        Formatted memory string or None on any failure (graceful degradation).
    """
    if not mem_cfg.get("enabled") or not mem_cfg.get("api_url"):
        return None

    try:
        import httpx
    except ImportError:
        return None

    try:
        api_url = mem_cfg["api_url"]
        max_results = mem_cfg.get("max_results", 3)
        resp = httpx.post(
            api_url,
            json={"query": user_message, "limit": max_results},
            timeout=3,
        )
        if resp.status_code != 200:
            return None

        results = resp.json().get("results")
        if not results:
            return None

        # Truncate each result to 120 chars and add bullet prefix
        items = [f"- {str(r)[:120]}" for r in results]
        return "📝 相关记忆:\n" + "\n".join(items)
    except Exception:
        return None


def _read_kanban(kanban_path: str, label: str) -> str | None:
    """Read project kanban status from the filesystem.

    Scans *kanban_path* for ``*.md`` files, reads each file and extracts the
    first line containing ``"优先级:"``. Results are formatted as:

        "- {filename}: {priority_line}"

    At most 5 items are returned.  Every I/O or parsing error is caught and
    results in graceful degradation (returns ``None``).

    Args:
        kanban_path: Filesystem path to the kanban directory.
        label: Section header text.  When empty, defaults to ``"📋 项目状态:"``.

    Returns:
        Formatted kanban section string or ``None`` when there is nothing to
        inject.
    """
    if not kanban_path:
        return None

    try:
        kb = Path(kanban_path)
        if not kb.is_dir():
            return None

        md_files = sorted(kb.glob("*.md"))
        if not md_files:
            return None

        items: list[str] = []
        for md_file in md_files:
            if len(items) >= 5:
                break
            try:
                # Empty file → split yields [""] → "" → skip
                first_line = md_file.read_text(encoding="utf-8").split("\n")[0].strip()
                if "优先级:" in first_line:
                    items.append(f"- {md_file.stem}: {first_line}")
            except OSError:
                continue

        if not items:
            return None

        header = label or "📋 项目状态:"
        return header + "\n" + "\n".join(items)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Narrative assembly (translate mode)
# ---------------------------------------------------------------------------


def _assemble_narrative(
    weekday: str,
    current_time: str,
    time_slot_desc: str,
    today_turn: int,
    turn_stage_hint: str | None,
    top3: list[tuple[str, float, str]],
    variance_items: list[str],
    fixed_rules: list[str],
) -> str:
    """将分散的模块注入数据拼装为一段流畅的自然语言指令。

    各数据源独立，缺失项优雅跳过（不抛异常、不输出该段落）。
    """
    lines: list[str] = []

    # ── ① 时间感知 + 时段规则 ──
    if time_slot_desc:
        lines.append(f"现在时间是：{weekday}，{current_time}。{time_slot_desc}")
    else:
        lines.append(f"现在时间是：{weekday}，{current_time}。")

    # ── ② 轮数追踪 + 轮数阶段 ──
    if today_turn > 0:
        turn_line = f"这是今天的第{today_turn}轮对话。"
        if turn_stage_hint:
            turn_line += f" {turn_stage_hint}。"
        lines.append(turn_line)

    # ── ③ 表达向量 top 3 转译 ──
    if top3:
        top_labels = [f"{label}（{trend}）" for label, _, trend in top3]
        lines.append(f"主人目前的状态是{'，'.join(top_labels)}。")

    # ── ④ 随机变化（抽中的）─ 直接放行，条目本身即为完整句 ──
    if variance_items:
        for item in variance_items:
            clean = _clean_variance_item(item)
            lines.append(clean)

    # ── ⑤ 固定规则（自然收尾） ──
    if fixed_rules:
        rules_text = "；".join(fixed_rules)
        lines.append(rules_text + "。")

    return "\n\n".join(lines)


def _clean_variance_item(item: str) -> str:
    """去除 emoji 前缀，保留其余内容原样输出。"""
    cleaned = item
    for prefix in ("🦊 ", "💬 ", "📊 ", "🌿 ", "💎 ", "🌙 "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    return cleaned.strip()





# ---------------------------------------------------------------------------
# Main entry point: inject_context()
# ---------------------------------------------------------------------------


def inject_context(
    session_id: str,
    user_message: str,
    conversation_history: list[dict],
    is_first_turn: bool,
    model: str,
    platform: str,
    **kwargs,
) -> dict | None:
    """Assemble and return the full persona context for this turn.

    Called by the Hermes runtime on every pre_llm_call hook.

    Injection order (immutable, per spec D2):
        1. Time context
        2. Static rules (context.rules + rules_first_turn_only)
        3. Dynamic rules (time slots + turn stages + keyword)
        4. Random variance       (stub in P1)
        5. Memory recall         (stub in P1)
        6. Kanban status         (stub in P1, first-turn only)

    Returns {"context": "<assembled string>"} or None when there is nothing
    to inject.
    """
    try:
        config = _load_config()
        modules = _resolve_modules(config)
        parts: list[str] = []

        # ── translate 模式：提前提取时间变量 ──
        _now = datetime.now()
        _weekday_cn = f"周{_WEEKDAY_CN[_now.weekday()]}"
        _current_time = _now.strftime("%H:%M")

        # ── 判断 translate 模式 ──
        _translate_mode = _is_enabled(modules, "translate")

        # ── 黑名单过滤：非对话来源只注入时间，跳过后续所有模块 ──
        _sources_blacklist = modules.get("sources_blacklist", [])
        if platform in _sources_blacklist:
            if _is_enabled(modules, "time"):
                return {"context": f"🕐 时间：{_weekday_cn}，{_current_time}"}
            return None

        # translate 模式下的数据容器
        _time_slot_desc = ""
        _turn_stage_hint = None
        _today_turn = 0
        _top3: list[tuple[str, float, str]] = []
        _variance_items: list[str] = []
        _filtered_rules: list[str] = []

        # 1. Time context
        if _is_enabled(modules, "time"):
            time_cfg = config.get("time", {})
            if _translate_mode:
                # translate 模式：时间已在前面从 _now 提取，跳过格式化注入
                pass
            else:
                fmt = time_cfg.get("format", "cn_full")
                parts.append(_time_context(fmt))

        # 2. Static rules
        static_rules: list[str] = []
        if _is_enabled(modules, "static_rules"):
            ctx_cfg = config.get("context", {})
            static_rules = _inject_static_rules(ctx_cfg, is_first_turn)
            if _translate_mode:
                _filtered_rules = list(static_rules)
            else:
                parts.extend(static_rules)

        # 3. Dynamic rules (subchannel-controllable)
        turn_count = len(conversation_history or []) // 2  # ← 提前，④b 复用
        dynamic_rules: list[str] = []
        if _has_any_dynamic(modules):
            dynamic_cfg = config.get("dynamic", {})
            if _translate_mode:
                dyn_mod = modules.get("dynamic", {})
                if dyn_mod is None or not isinstance(dyn_mod, dict):
                    dyn_mod = {}
                if dyn_mod.get("time_slots", True):
                    _time_slot_desc = _get_time_slot_desc(
                        dynamic_cfg.get("time_slots", {})
                    )
                # turn_stage 改用每日累积轮数，在 _today_turn 提取后计算
            else:
                dynamic_rules = _select_dynamic_rules(
                    dynamic_cfg,
                    user_message,
                    is_first_turn,
                    turn_count,
                    modules=modules.get("dynamic", {}),
                )
                parts.extend(dynamic_rules)

        # ─── ④a Fixed signals ────────────────────────────
        fixed_cfg = config.get("fixed_signals", {})

        if _translate_mode:
            # translate 模式：提取 today_turn 原始值，保持副作用
            turn_hint = _daily_turn_count_hint(
                fixed_cfg, profile_path=kwargs.get("profile_path", "")
            )
            if turn_hint:
                _m = re.search(r"今日第(\d+)轮", turn_hint)
                if _m:
                    _today_turn = int(_m.group(1))
            # 用每日累积轮数计算轮数阶段（不是会话内轮数）
            if modules.get("dynamic", {}).get("turn_stage", True):
                _turn_stage_hint = _get_turn_stage_hint(
                    config.get("dynamic", {}).get("turn_stage", {}),
                    is_first_turn,
                    _today_turn,
                )
            # translate 模式下也需要保存 reply_timing
            gap_hint, now_ts = _reply_gap_hint(fixed_cfg)
            _save_reply_timing(fixed_cfg, now_ts)
        else:
            hint = _message_length_hint(user_message or "", fixed_cfg)
            if hint:
                parts.append(hint)

            gap_hint, now_ts = _reply_gap_hint(fixed_cfg)
            if gap_hint:
                parts.append(gap_hint)
            _save_reply_timing(fixed_cfg, now_ts)

            turn_hint = _daily_turn_count_hint(fixed_cfg, profile_path=kwargs.get("profile_path", ""))
            if turn_hint:
                parts.append(turn_hint)
        # ──────────────────────────────────────────────────

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
                rg_dbg_default = str(Path(__file__).resolve().parent / "state" / "reply_timing.json")
                rg_path = Path(rg_cfg.get("storage_path", "") or rg_dbg_default).expanduser()
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
            dc_count = 0
            dc_date = datetime.now().strftime("%Y-%m-%d")
            try:
                dc_default_dbg = str(Path(__file__).resolve().parent / "state" / "daily_turn_count.json")
                dc_path_raw = dc_cfg.get("storage_path", "") or dc_default_dbg
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
            debug_fs["daily_turn_count"] = {
                "visible": True,
                "triggered": True,
                "count": dc_count,
                "date": dc_date,
            }
        # ──────────────────────────────────────────────────

        # ─── ④b Expression vector (FuzzyUtility) with delta capture ──
        ev_cfg = config.get("expression_vector", {})
        debug_ev = {"enabled": False, "turn_count": 0, "dimensions": {}}
        if ev_cfg.get("enabled", False):
            try:
                profile = kwargs.get("profile_path", "")
                ev = _ExpressionVector(ev_cfg, profile_path=profile)
                ev.load()
                # Capture snapshot BEFORE any modification
                snapshot_before = dict(ev.vectors)
                if not _is_background_message(user_message or ""):
                    ev.update(user_message or "", session_id)
                # Record delta information from snapshot_before → current
                msg_lower = (user_message or "").lower()
                debug_ev["enabled"] = True
                debug_ev["turn_count"] = turn_count
                for dim_name in sorted(ev.dimensions.keys()):
                    old_val = snapshot_before.get(dim_name, 0.0)
                    new_val = ev.vectors.get(dim_name, 0.0)
                    delta = new_val - old_val
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
                if _translate_mode:
                    _top3 = ev.top3(n=3, trend=True)
                else:
                    parts.append(ev.format_inject(turn_count))
            except Exception:
                pass  # fail-open：表达向量失败不阻断后续注入
        # ──────────────────────────────────────────────────

        # 5. Random variance
        var_count = 0
        var_results = []
        if _is_enabled(modules, "variance"):
            var_results = _randomize_variance(config.get("variance", {}))
            if _translate_mode:
                _variance_items = list(var_results)
            else:
                parts.extend(var_results)
                var_count = len(var_results)

        # ─── debug_context: capture variance item states ───
        var_context_items = []
        if _is_enabled(modules, "variance"):
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
                    for vr in var_results:
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
        # ──────────────────────────────────────────────────

        # 5. Memory recall
        if _is_enabled(modules, "memory"):
            mem_cfg = config.get("memory", {})
            memories = _recall_memories(user_message, mem_cfg)
            if memories is not None:
                parts.append(memories)

        # 6. Kanban status (first-turn only)
        if is_first_turn and _is_enabled(modules, "kanban"):
            project_cfg = config.get("project", {})
            kanban = _read_kanban(
                project_cfg.get("kanban_path", ""),
                project_cfg.get("label", ""),
            )
            if kanban is not None:
                parts.append(kanban)

        # ── translate 拼装 ──
        if _translate_mode:
            narrative = _assemble_narrative(
                weekday=_weekday_cn,
                current_time=_current_time,
                time_slot_desc=_time_slot_desc,
                today_turn=_today_turn,
                turn_stage_hint=_turn_stage_hint,
                top3=_top3,
                variance_items=_variance_items,
                fixed_rules=_filtered_rules,
            )
            parts.insert(0, narrative)

        # Record non-debug content count before debug injection
        non_debug_count = len(parts)

        # 7. Debug summary → stored to _PENDING_DEBUG_BLOCK, appended by transform_llm_output
        global _PENDING_DEBUG_BLOCK
        _PENDING_DEBUG_BLOCK = None
        debug_val = modules.get("debug", "<missing>")
        if _is_enabled(modules, "debug"):
            debug_context = {
                "fixed_signals": debug_fs,
                "expression_vector": debug_ev,
                "variance": {"items": var_context_items},
                "static_rules": static_rules,
                "dynamic_rules": dynamic_rules,
            }
            _PENDING_DEBUG_BLOCK = f"\n\n---\n{_debug_summary(
                modules, parts,
                var_count=var_count,
                config=config,
                debug_context=debug_context,
            )}"
            if _translate_mode:
                _PENDING_DEBUG_BLOCK += f"\n\n🔮 [转译结果]:\n{narrative}"
            _trace("inject_context", f"SET debug={debug_val!r} pending={len(_PENDING_DEBUG_BLOCK)} chars")
        else:
            _trace("inject_context", f"SKIP debug={debug_val!r} enabled={_is_enabled(modules, 'debug')} config_root={'set' if _config._CONFIG_ROOT else 'None'}")

        if non_debug_count == 0:
            return None
        return {"context": "\n\n".join(parts)}
    except Exception:
        # Never let persona injection block the agent's normal flow
        traceback.print_exc()
        return None


def transform_llm_output(
    response_text: str,
    session_id: str = "",
    model: str = "",
    platform: str = "",
    **kwargs,
) -> str | None:
    """transform_llm_output hook：将 debug 块拼接到 LLM 回复末尾。

    当 pre_llm_call 阶段 debug 启用时，_PENDING_DEBUG_BLOCK 被设置，
    此 hook 将其追加到 LLM 回复末尾后清空。

    Returns:
        追加后的完整文本，或 None（无 debug 块时不修改）。
    """
    global _PENDING_DEBUG_BLOCK
    try:
        if _PENDING_DEBUG_BLOCK:
            result = response_text + _PENDING_DEBUG_BLOCK
            _trace("transform_llm_output", f"FOUND pending={len(_PENDING_DEBUG_BLOCK)} chars → appended")
            _PENDING_DEBUG_BLOCK = None
            return result
        _trace("transform_llm_output", "MISS pending is None")
        return None
    except Exception:
        return None
