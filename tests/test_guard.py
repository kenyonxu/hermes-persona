"""Tests for guard — P4 safety guard and audit."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from guard import check_tool_call, audit_tool_call, _load_guard_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_guard_config(monkeypatch, config: dict):
    """Patch _load_guard_config to return a specific config."""
    monkeypatch.setattr(
        "guard._load_guard_config",
        lambda: config,
    )


# ---------------------------------------------------------------------------
# check_tool_call tests
# ---------------------------------------------------------------------------


def test_guard_disabled(monkeypatch):
    """When guard.enabled=false, all tools should be allowed."""
    _mock_guard_config(monkeypatch, {"enabled": False})
    assert check_tool_call("Bash(rm -rf /)", {"command": "rm -rf /"}) is None
    assert check_tool_call("Write", {"file_path": "/tmp/x"}) is None


def test_guard_enabled_missing(monkeypatch):
    """When 'enabled' key is missing, treat as disabled (permissive)."""
    _mock_guard_config(monkeypatch, {})
    assert check_tool_call("Bash(rm -rf /)", {}) is None


def test_block_tool(monkeypatch):
    """Tool name matching a blocked pattern returns blocked=True."""
    _mock_guard_config(
        monkeypatch,
        {
            "enabled": True,
            "rules": {
                "blocked": [
                    {"pattern": r"rm\s", "reason": "文件删除操作已阻止"},
                    {"pattern": r"DROP\s", "reason": "数据库删除操作已阻止"},
                ],
            },
        },
    )
    result = check_tool_call("Bash(rm -rf /)", {"command": "rm -rf /"})
    assert result is not None
    assert result["blocked"] is True
    assert "文件删除" in result["reason"]


def test_block_tool_second_rule(monkeypatch):
    """Tool matching the second blocked pattern should also be blocked."""
    _mock_guard_config(
        monkeypatch,
        {
            "enabled": True,
            "rules": {
                "blocked": [
                    {"pattern": r"rm\s", "reason": "文件删除操作已阻止"},
                    {"pattern": r"DROP\s", "reason": "数据库删除操作已阻止"},
                ],
            },
        },
    )
    result = check_tool_call("Bash(DROP TABLE users)", {"command": "DROP TABLE users"})
    assert result is not None
    assert result["blocked"] is True
    assert "数据库" in result["reason"]


def test_allow_tool(monkeypatch):
    """Tool name not matching any pattern returns None (allow)."""
    _mock_guard_config(
        monkeypatch,
        {
            "enabled": True,
            "rules": {
                "blocked": [{"pattern": r"rm\s", "reason": "阻止"}],
            },
        },
    )
    assert check_tool_call("Read", {"file_path": "/tmp/x"}) is None
    assert check_tool_call("Write", {"file_path": "/tmp/x"}) is None
    assert check_tool_call("Grep", {"pattern": "hello"}) is None


def test_require_confirmation(monkeypatch):
    """Tool matching confirm pattern returns require_confirmation=True (no block)."""
    _mock_guard_config(
        monkeypatch,
        {
            "enabled": True,
            "rules": {
                "require_confirmation": [
                    {"pattern": r"git\s+push", "reason": "代码推送需确认"},
                ],
            },
        },
    )
    result = check_tool_call("Bash(git push origin main)", {"command": "git push"})
    assert result is not None
    assert result.get("require_confirmation") is True
    assert result.get("blocked") is None  # explicitly not blocked
    assert "推送" in result["reason"]


def test_block_takes_priority(monkeypatch):
    """When a tool matches both blocked and confirm patterns, block wins."""
    _mock_guard_config(
        monkeypatch,
        {
            "enabled": True,
            "rules": {
                "blocked": [
                    {"pattern": r"rm\s", "reason": "删除被阻止"},
                ],
                "require_confirmation": [
                    {"pattern": r"rm\s", "reason": "删除需确认"},
                ],
            },
        },
    )
    result = check_tool_call("Bash(rm file.txt)", {"command": "rm file.txt"})
    assert result is not None
    assert result["blocked"] is True  # block takes priority
    assert result.get("require_confirmation") is None


def test_empty_guard_config(monkeypatch):
    """When guard node is empty/missing from config, everything is allowed."""
    _mock_guard_config(monkeypatch, {})
    assert check_tool_call("Bash(rm -rf /)", {}) is None
    assert check_tool_call("Write", {}) is None


def test_no_rules_key(monkeypatch):
    """When guard is enabled but has no rules key, allow all."""
    _mock_guard_config(monkeypatch, {"enabled": True})
    assert check_tool_call("Bash(rm -rf /)", {}) is None


def test_empty_blocked_list(monkeypatch):
    """When blocked list is empty, don't block anything."""
    _mock_guard_config(
        monkeypatch,
        {"enabled": True, "rules": {"blocked": []}},
    )
    assert check_tool_call("Bash(rm -rf /)", {}) is None


def test_malformed_rule_skipped(monkeypatch):
    """Rules that aren't dicts should be skipped gracefully."""
    _mock_guard_config(
        monkeypatch,
        {
            "enabled": True,
            "rules": {
                "blocked": [
                    "not_a_dict",  # malformed
                    {"pattern": r"rm\s", "reason": "删除被阻止"},
                ],
            },
        },
    )
    result = check_tool_call("Bash(rm file.txt)", {})
    assert result is not None
    assert result["blocked"] is True


def test_rule_without_pattern_skipped(monkeypatch):
    """Rule with empty pattern should be skipped."""
    _mock_guard_config(
        monkeypatch,
        {
            "enabled": True,
            "rules": {
                "blocked": [
                    {"reason": "无pattern的规则"},  # no pattern key
                    {"pattern": r"DROP\s", "reason": "数据库删除已阻止"},
                ],
            },
        },
    )
    # "rm" should NOT match the empty pattern rule
    result = check_tool_call("Bash(rm file.txt)", {})
    assert result is None  # rm doesn't match DROP


def test_rule_without_reason_uses_default(monkeypatch):
    """Rule without explicit reason should get a default reason."""
    _mock_guard_config(
        monkeypatch,
        {
            "enabled": True,
            "rules": {
                "blocked": [
                    {"pattern": r"rm\s"},  # no reason key
                ],
            },
        },
    )
    result = check_tool_call("Bash(rm file.txt)", {})
    assert result is not None
    assert result["blocked"] is True
    assert len(result["reason"]) > 0  # default reason provided


# ---------------------------------------------------------------------------
# audit_tool_call tests
# ---------------------------------------------------------------------------


def test_audit_writes_log(monkeypatch):
    """When audit is enabled, a log entry should be written."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.log"
        _mock_guard_config(
            monkeypatch,
            {
                "audit": {
                    "enabled": True,
                    "log_path": str(log_path),
                },
            },
        )
        audit_tool_call("Read", {"file_path": "/tmp/test.txt"}, "file content here")
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        # Verify format: [timestamp] tool_name | args: ... | result: ...
        assert "Read" in content
        assert "args:" in content
        assert "result:" in content
        assert "/tmp/test.txt" in content
        assert "file content here" in content


def test_audit_disabled(monkeypatch):
    """When audit is disabled, no log should be written."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.log"
        _mock_guard_config(
            monkeypatch,
            {
                "audit": {
                    "enabled": False,
                    "log_path": str(log_path),
                },
            },
        )
        audit_tool_call("Read", {"file_path": "/tmp/test.txt"}, "content")
        assert not log_path.exists()


def test_audit_creates_parent_dir(monkeypatch):
    """Audit should create parent directories if they don't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "sub" / "nested" / "audit.log"
        _mock_guard_config(
            monkeypatch,
            {
                "audit": {
                    "enabled": True,
                    "log_path": str(log_path),
                },
            },
        )
        audit_tool_call("Write", {"file_path": "/x"}, "ok")
        assert log_path.exists()


def test_audit_truncates_long_args(monkeypatch):
    """Args longer than 200 chars should be truncated."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.log"
        _mock_guard_config(
            monkeypatch,
            {
                "audit": {
                    "enabled": True,
                    "log_path": str(log_path),
                },
            },
        )
        long_arg = "x" * 300
        audit_tool_call("Test", {"data": long_arg}, "result")
        content = log_path.read_text(encoding="utf-8")
        # The full 300-x string should NOT appear (was truncated)
        assert long_arg not in content
        # But some of it should appear
        assert "x" * 100 in content


def test_audit_truncates_long_results(monkeypatch):
    """Results longer than 200 chars should be truncated."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.log"
        _mock_guard_config(
            monkeypatch,
            {
                "audit": {
                    "enabled": True,
                    "log_path": str(log_path),
                },
            },
        )
        long_result = "y" * 300
        audit_tool_call("Test", {"arg": "val"}, long_result)
        content = log_path.read_text(encoding="utf-8")
        # The full 300-y string should NOT appear (was truncated)
        assert "y" * 300 not in content
        # But some of it should appear
        assert "y" * 100 in content


def test_audit_appends_multiple_entries(monkeypatch):
    """Multiple calls should append, not overwrite."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.log"
        _mock_guard_config(
            monkeypatch,
            {
                "audit": {
                    "enabled": True,
                    "log_path": str(log_path),
                },
            },
        )
        audit_tool_call("Read", {"file_path": "/a"}, "content a")
        audit_tool_call("Write", {"file_path": "/b"}, "content b")
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert "Read" in lines[0]
        assert "Write" in lines[1]


def test_audit_empty_log_path(monkeypatch):
    """When log_path is empty, audit should be a no-op."""
    _mock_guard_config(
        monkeypatch,
        {
            "audit": {
                "enabled": True,
                "log_path": "",
            },
        },
    )
    # Should not raise
    audit_tool_call("Read", {}, "result")


def test_audit_no_exception_on_error(monkeypatch):
    """Audit must never raise, even on write errors."""
    _mock_guard_config(
        monkeypatch,
        {
            "audit": {
                "enabled": True,
                "log_path": "/nonexistent/root/only/path/audit.log",
            },
        },
    )
    # Should not raise even if parent dir cannot be created
    audit_tool_call("Read", {}, "result")


def test_audit_missing_enabled_defaults_false(monkeypatch):
    """When audit config has no 'enabled' key, default to disabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.log"
        _mock_guard_config(
            monkeypatch,
            {
                "audit": {
                    "log_path": str(log_path),
                },
            },
        )
        audit_tool_call("Read", {}, "result")
        assert not log_path.exists()


# ---------------------------------------------------------------------------
# _load_guard_config tests
# ---------------------------------------------------------------------------


def test_load_guard_config_empty_when_disabled(monkeypatch):
    """When guard node doesn't exist, return {}."""
    import guard as _guard
    monkeypatch.setattr(_guard, "_load_guard_config", lambda: {})
    assert _guard._load_guard_config() == {}
    assert _guard.check_tool_call("Bash(rm -rf /)", {}) is None
