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
try:
    from . import config
    from . import guard
    from . import injector
    # Register short aliases — Hermes puts modules under
    # hermes_plugins.hermes_persona.<name>, so bare ``import config``
    # in sub-modules would fail without these aliases.
    sys.modules.setdefault("config", config)
    sys.modules.setdefault("guard", guard)
    sys.modules.setdefault("injector", injector)
except ImportError:
    import config
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

    # P4: safety guard
    ctx.register_hook("pre_tool_call", guard.check_tool_call)
    ctx.register_hook("post_tool_call", guard.audit_tool_call)
