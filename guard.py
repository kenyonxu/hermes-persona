"""Safety guard and audit — P4 implementation.

Provides:
  - check_tool_call: pre_tool_call hook for tool safety checks
  - audit_tool_call: post_tool_call hook for audit logging

Configuration is read from persona-config.json → hermes-persona.guard.
"""

from __future__ import annotations

import fcntl
import json
import re
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Guard config loading
# ---------------------------------------------------------------------------


def _load_guard_config() -> dict:
    """Load guard configuration from persona-config.json.

    Returns the "hermes-persona" → "guard" sub-tree.
    Returns {} on any failure (permissive mode — allow all).

    Uses the same _CONFIG_ROOT / fallback path strategy as injector._load_config().
    """
    import config as _config

    config_path = _config._resolve_config_path("persona-config.json")
    if config_path is None:
        config_path = Path(__file__).resolve().parents[2] / "persona-config.json"

    try:
        if not config_path.is_file():
            return {}
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        guard_cfg = data.get("hermes-persona", {}).get("guard", {})
        if not isinstance(guard_cfg, dict) or not guard_cfg.get("enabled", False):
            return {}
        return guard_cfg
    except (json.JSONDecodeError, OSError):
        return {}


# ---------------------------------------------------------------------------
# Pre-tool-call: safety check
# ---------------------------------------------------------------------------


def check_tool_call(tool_name: str, args: dict, **kwargs) -> dict | None:
    """Check if a tool call should be blocked or requires confirmation.

    Called by Hermes runtime as a pre_tool_call hook.

    Args:
        tool_name: Name of the tool being called (e.g. "Bash", "Write").
        tool_args: The arguments passed to the tool.

    Returns:
        {"blocked": True, "reason": "..."}  — block the call
        {"require_confirmation": True, "reason": "..."}  — warn, don't block
        None  — allow the call
    """
    try:
        guard_cfg = _load_guard_config()
    except Exception:
        # If config loading fails, permit everything (fail-open)
        return None

    if not guard_cfg.get("enabled", False):
        return None

    rules = guard_cfg.get("rules", {})
    if not isinstance(rules, dict):
        return None

    def _check_patterns(rule, tool_name, args):
        """Check tool_name pattern and optional arg_patterns."""
        pattern = rule.get("pattern", "")
        if pattern and re.search(pattern, tool_name):
            return True
        arg_patterns = rule.get("arg_patterns", {})
        if arg_patterns and isinstance(arg_patterns, dict):
            arg_name = arg_patterns.get("arg")
            arg_pattern_str = arg_patterns.get("pattern")
            if arg_name and arg_pattern_str:
                arg_value = str(args.get(arg_name, ""))
                if re.search(arg_pattern_str, arg_value):
                    return True
        return False

    # 1. Blocked rules — checked first, blocks the tool call
    for rule in rules.get("blocked", []):
        if not isinstance(rule, dict):
            continue
        if _check_patterns(rule, tool_name, args):
            return {
                "blocked": True,
                "reason": rule.get("reason", "此操作已被安全护栏阻止"),
            }

    # 2. Require-confirmation rules — warn but don't block
    for rule in rules.get("require_confirmation", []):
        if not isinstance(rule, dict):
            continue
        if _check_patterns(rule, tool_name, args):
            return {
                "require_confirmation": True,
                "reason": rule.get("reason", "此操作需要确认"),
            }

    return None


# ---------------------------------------------------------------------------
# Post-tool-call: audit logging
# ---------------------------------------------------------------------------


def audit_tool_call(tool_name: str, args: dict, result, **kwargs) -> None:
    """Record a tool-call audit entry.

    Called by Hermes runtime as a post_tool_call hook.

    Log format:
        [ISO-timestamp] tool_name | args: <summary> | result: <summary>

    Args and result strings are truncated to 200 characters.

    Never raises — audit must not block the agent's normal flow.
    """
    try:
        guard_cfg = _load_guard_config()
    except Exception:
        return

    audit_cfg = guard_cfg.get("audit", {})
    if not isinstance(audit_cfg, dict):
        return

    if not audit_cfg.get("enabled", False):
        return

    log_path_str = audit_cfg.get("log_path", "")
    if not log_path_str:
        return

    try:
        log_path = Path(log_path_str).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().isoformat()

        # Arg summary (truncate to 200 chars)
        args_str = str(args)
        args_summary = args_str if len(args_str) <= 200 else args_str[:200]

        # Result summary (truncate to 200 chars)
        result_str = str(result)
        result_summary = result_str if len(result_str) <= 200 else result_str[:200]

        log_entry = (
            f"[{timestamp}] {tool_name}"
            f" | args: {args_summary}"
            f" | result: {result_summary}\n"
        )

        with open(log_path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(log_entry)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        # Audit must never block or crash the agent
        pass
