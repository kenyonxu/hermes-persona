"""hermes-persona: Dynamic persona context injection engine for Hermes Agent.

Usage:
    from . import register  # Hermes plugin root
    register(ctx)  # ctx is a Hermes PluginContext
"""

from __future__ import annotations

import sys
from pathlib import Path

# Hermes loads plugins as packages — relative imports are correct.
# pytest / standalone Python need absolute imports as fallback.
# Additionally, register short aliases in sys.modules so that
# sub-modules (injector.py, guard.py) can use bare ``import config``
# regardless of which code path loaded them.
_plugin_dir = str(Path(__file__).resolve().parent)

try:
    from . import config
    # Register config alias immediately — injector.py/guard.py use bare
    # ``import config`` at module level, which resolves via sys.modules
    # (not __path__), so the alias must exist before those modules load.
    sys.modules.setdefault("config", config)
    from . import locales
    from . import guard
    from . import injector
    sys.modules.setdefault("locales", locales)
    sys.modules.setdefault("guard", guard)
    sys.modules.setdefault("injector", injector)
except ImportError:
    # Flat layout fallback: ensure plugin dir is on sys.path so bare
    # ``import config`` resolves.
    if _plugin_dir not in sys.path:
        sys.path.insert(0, _plugin_dir)
    import config
    import locales
    import guard
    import injector


def register(ctx) -> None:
    """Register the hermes-persona plugin with the Hermes runtime.

    - Stores the profile directory path (ctx.profile_path) for config loading.
    - Registers the pre_llm_call hook for persona context injection.
    - Registers transform_llm_output hook for reliable debug injection.
    - Registers pre_tool_call / post_tool_call hooks for safety guard (P4).

    Args:
        ctx: Hermes PluginContext with profile_path, register_hook, etc.
    """
    # Store profile path for config loading
    if hasattr(ctx, "profile_path") and ctx.profile_path:
        config._CONFIG_ROOT = Path(ctx.profile_path)
    # else: _CONFIG_ROOT stays None → _load_config() uses fallback path

    # P1: persona context injection
    ctx.register_hook("pre_llm_call", injector.inject_context)

    # Debug: reliable post-injection via transform_llm_output
    ctx.register_hook("transform_llm_output", injector.transform_llm_output)

    # Load config and initialize locale system (after _CONFIG_ROOT is set)
    try:
        config_data = injector._load_config()
        locales._init_locales(_plugin_dir, config_data)
    except Exception:
        pass  # locale failure is non-fatal; plugin still works

    # P4: safety guard
    ctx.register_hook("pre_tool_call", guard.check_tool_call)
    ctx.register_hook("post_tool_call", guard.audit_tool_call)
