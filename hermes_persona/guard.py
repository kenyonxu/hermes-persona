"""Safety guard and audit — P4 stubs.

P4 will implement:
  - check_tool_call: pre_tool_call hook for tool safety checks
  - audit_tool_call: post_tool_call hook for audit logging
"""


def check_tool_call(tool_name: str, tool_args: dict, **kwargs):
    """P4 implementation. Currently returns None (allow all)."""
    return None


def audit_tool_call(tool_name: str, tool_args: dict, result, **kwargs):
    """P4 implementation. Currently a no-op."""
    pass
