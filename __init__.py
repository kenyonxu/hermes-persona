"""hermes-persona plugin entry point.

This file lets Hermes discover the register() function from the plugin root.
The actual implementation lives in the hermes_persona/ package.
"""

from hermes_persona import register

__all__ = ["register"]
