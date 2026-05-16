"""hermes-persona plugin — dynamic persona context injection engine.

Hermes loads this __init__.py directly from the plugin root.
The hermes_persona/ sub-package holds the engine modules.
"""

from __future__ import annotations

from pathlib import Path

# When loaded by Hermes as a plugin package, use relative import.
# When running tests or standalone Python, fall back to absolute import.
try:
    from .hermes_persona import guard, injector
except ImportError:
    from hermes_persona import guard, injector  # type: ignore[no-redef]


def register(ctx) -> None:
    """Register the hermes-persona plugin with the Hermes runtime.

    - Stores ctx.profile_path for config loading (persona-config.json).
    - Registers pre_llm_call for persona context injection.
    - Registers pre_tool_call / post_tool_call for safety guard.
    """
    if hasattr(ctx, "profile_path") and ctx.profile_path:
        injector._CONFIG_ROOT = Path(ctx.profile_path)

    ctx.register_hook("pre_llm_call", injector.inject_context)
    ctx.register_hook("pre_tool_call", guard.check_tool_call)
    ctx.register_hook("post_tool_call", guard.audit_tool_call)


__all__ = ["register"]
