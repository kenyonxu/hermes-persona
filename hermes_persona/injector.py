"""Persona context injector: config loading, time generation, rule assembly.

Core module of hermes-persona. Provides the inject_context() entry point
called by the Hermes runtime on every pre_llm_call hook.
"""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime
from pathlib import Path

from .dynamic_rules import _select_dynamic_rules
from .expression_vector import _ExpressionVector
from .variance import _randomize_variance

# ---------------------------------------------------------------------------
# Module-level variable set by __init__.py:register()
# ---------------------------------------------------------------------------
_CONFIG_ROOT: Path | None = None

# ---------------------------------------------------------------------------
# Pending debug block for transform_llm_output hook
# ---------------------------------------------------------------------------
_PENDING_DEBUG_BLOCK: str | None = None

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
    if _CONFIG_ROOT is not None:
        config_path = _CONFIG_ROOT / "persona-config.json"
    else:
        config_path = Path(__file__).resolve().parents[3] / "persona-config.json"

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
    except Exception:
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


def _debug_summary(modules: dict, parts: list[str], var_count: int = 0) -> str:
    """Generate a human-readable injection summary for debug mode.

    When modules.debug.visible is True, the summary is wrapped in an
    instruction telling the LLM to echo it verbatim in the response.
    When visible is False (or debug is a plain bool), the summary is an
    internal memo only — injected into context but not surfaced to the user.
    """
    debug_cfg = modules.get("debug", {})
    visible = isinstance(debug_cfg, dict) and debug_cfg.get("visible", False)

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
        import re
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

    summary = "\n".join(lines)

    if visible:
        return (
            f"🔧 [Hermes-Persona Debug Mode — Visible]\n"
            f"你必须在回复的最末尾原样输出以下内容（含每行的前导空格），"
            f"不要做任何改写、省略或格式化：\n"
            f"```\n{summary}\n```\n"
            f"此段为系统注入，不是用户的输入。"
        )
    else:
        return summary


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
    """Format dynamic subchannel status string."""
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


def _fmt_variance_status(parts: list[str]) -> str:
    """Extract variance status from parts content."""
    try:
        # Variance items are the plain strings added by _randomize_variance
        # that are not from time, static rules, dynamic, memory, or kanban
        variance_items = []
        for part in parts:
            if not isinstance(part, str):
                continue
            if part.startswith("🕐") or part.startswith("📝") or part.startswith("📋"):
                continue
            if part.startswith("🕐 [") or part.startswith("💬 ["):
                continue
            # This is a static rule or variance — we can't easily distinguish
            # So we report based on whether parts exist beyond known prefixes
        if variance_items:
            return " / ".join(variance_items)
        return "无注入"
    except Exception:
        return "无数据"


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
    raw_path = rg_cfg.get("storage_path", "~/.hermes/reply_timing.json")
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

    raw_path = rg_cfg.get("storage_path", "~/.hermes/reply_timing.json")
    storage_path = Path(raw_path).expanduser()

    try:
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"last_reply_at": now_ts}
        storage_path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def _daily_turn_count_hint(fixed_cfg: dict) -> str | None:
    """检查当日累计轮数，注入轮数感知信号。

    每日轮数在跨会话间累积（同一自然日内的所有消息）。
    日期跨越时自动归零。信号用于告知角色当日互动深度。

    Args:
        fixed_cfg: fixed_signals 配置节。

    Returns:
        \"📊 今日第N轮 — …\" 或 None。
    """
    dc_cfg = fixed_cfg.get("daily_turn_count", {})
    if not dc_cfg.get("enabled", False):
        return None

    today_key = datetime.now().strftime("%Y-%m-%d")
    raw_path = dc_cfg.get(
        "storage_path",
        "~/.hermes/profiles/{profile}/state/daily_turn_count.json",
    )
    storage_path = Path(raw_path).expanduser()

    # 读取或初始化
    data: dict = {"date": today_key, "count": 0}
    try:
        if storage_path.is_file():
            saved = json.loads(storage_path.read_text(encoding="utf-8"))
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

        # 1. Time context
        if _is_enabled(modules, "time"):
            time_cfg = config.get("time", {})
            fmt = time_cfg.get("format", "cn_full")
            parts.append(_time_context(fmt))

        # 2. Static rules
        if _is_enabled(modules, "static_rules"):
            ctx_cfg = config.get("context", {})
            parts.extend(_inject_static_rules(ctx_cfg, is_first_turn))

        # 3. Dynamic rules (subchannel-controllable)
        turn_count = len(conversation_history or []) // 2  # ← 提前，④b 复用
        if _has_any_dynamic(modules):
            dynamic_cfg = config.get("dynamic", {})
            parts.extend(
                _select_dynamic_rules(
                    dynamic_cfg,
                    user_message,
                    is_first_turn,
                    turn_count,
                    modules=modules.get("dynamic", {}),
                )
            )

        # ─── ④a Fixed signals ────────────────────────────
        fixed_cfg = config.get("fixed_signals", {})
        hint = _message_length_hint(user_message or "", fixed_cfg)
        if hint:
            parts.append(hint)

        gap_hint, now_ts = _reply_gap_hint(fixed_cfg)
        if gap_hint:
            parts.append(gap_hint)
        _save_reply_timing(fixed_cfg, now_ts)

        turn_hint = _daily_turn_count_hint(fixed_cfg)
        if turn_hint:
            parts.append(turn_hint)
        # ──────────────────────────────────────────────────

        # ─── ④b Expression vector (FuzzyUtility) ─────────
        ev_cfg = config.get("expression_vector", {})
        if ev_cfg.get("enabled", False):
            try:
                profile = kwargs.get("profile_path", "")
                ev = _ExpressionVector(ev_cfg, profile_path=profile)
                ev.load()
                ev.update(user_message or "", session_id)
                ev.save()
                parts.append(ev.format_inject(turn_count))
            except Exception:
                pass  # fail-open：表达向量失败不阻断后续注入
        # ──────────────────────────────────────────────────

        # 5. Random variance
        var_count = 0
        if _is_enabled(modules, "variance"):
            var_results = _randomize_variance(config.get("variance", {}))
            parts.extend(var_results)
            var_count = len(var_results)

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

        # Record non-debug content count before debug injection
        non_debug_count = len(parts)

        # 7. Debug summary
        global _PENDING_DEBUG_BLOCK
        _PENDING_DEBUG_BLOCK = None
        if _is_enabled(modules, "debug"):
            summary = _debug_summary(modules, parts, var_count=var_count)
            debug_cfg = modules.get("debug", {})
            visible = isinstance(debug_cfg, dict) and debug_cfg.get("visible", False)
            if visible:
                # 可靠路径：存到模块变量，由 transform_llm_output 拼接到 LLM 回复末尾
                _PENDING_DEBUG_BLOCK = f"\n\n---\n{summary}"
            else:
                # 内部路径：注入到系统提示供 LLM 参考（不要求 echo）
                parts.append(summary)

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

    仅在 pre_llm_call 阶段 debug.visible=true 时生效。
    不修改 response_text 本身，只在末尾追加等待中的 debug 摘要块。
    追加完成后清空 _PENDING_DEBUG_BLOCK。

    Returns:
        追加后的完整文本，或 None（无 debug 块时不修改）。
    """
    try:
        global _PENDING_DEBUG_BLOCK
        if _PENDING_DEBUG_BLOCK:
            result = response_text + _PENDING_DEBUG_BLOCK
            _PENDING_DEBUG_BLOCK = None
            return result
        return None  # 不修改
    except Exception:
        return None
