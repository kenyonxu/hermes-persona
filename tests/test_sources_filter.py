"""Tests for sources_blacklist filtering — non-conversational platforms skip
persona injection and only receive time context.
"""

from unittest.mock import patch

import injector


# ── helpers ─────────────────────────────────────────────────────────────────

_BLACKLIST_CONFIG = {
    "modules": {
        "time": True,
        "sources_blacklist": ["cron", "api_server", "webhook"],
    },
    "time": {"format": "cn_full"},
}


# ── filtered platforms ─────────────────────────────────────────────────────


def test_cron_platform_filtered(inject_context_defaults):
    """platform="cron" in blacklist → only time context, no rules/dynamic."""
    kwargs = {**inject_context_defaults, "platform": "cron"}
    with patch("injector._load_config", return_value=_BLACKLIST_CONFIG):
        result = injector.inject_context(**kwargs)
    assert result is not None
    assert "🕐 时间：" in result["context"]
    assert "周" in result["context"]
    # Must be a short time-only string, not the full assembled pipeline
    assert len(result["context"]) < 30


def test_api_server_platform_filtered(inject_context_defaults):
    """platform="api_server" in blacklist → only time context."""
    kwargs = {**inject_context_defaults, "platform": "api_server"}
    with patch("injector._load_config", return_value=_BLACKLIST_CONFIG):
        result = injector.inject_context(**kwargs)
    assert result is not None
    assert "🕐 时间：" in result["context"]
    assert "周" in result["context"]
    assert len(result["context"]) < 30


def test_webhook_platform_filtered(inject_context_defaults):
    """platform="webhook" in blacklist → only time context."""
    kwargs = {**inject_context_defaults, "platform": "webhook"}
    with patch("injector._load_config", return_value=_BLACKLIST_CONFIG):
        result = injector.inject_context(**kwargs)
    assert result is not None
    assert "🕐 时间：" in result["context"]
    assert "周" in result["context"]
    assert len(result["context"]) < 30


# ── non-filtered platforms ─────────────────────────────────────────────────


def test_discord_platform_not_filtered(inject_context_defaults):
    """platform="discord" not in blacklist → full pipeline runs normally."""
    kwargs = {**inject_context_defaults, "platform": "discord"}
    with patch("injector._load_config", return_value={
        "modules": {"time": True, "sources_blacklist": ["cron"]},
        "time": {"format": "cn_full"},
        "context": {"rules": ["测试规则"]},
    }):
        result = injector.inject_context(**kwargs)
    assert result is not None
    assert "🕐" in result["context"]
    assert "测试规则" in result["context"]


def test_unknown_platform_not_filtered(inject_context_defaults):
    """platform="new_platform" not in blacklist → fail-open, full pipeline."""
    kwargs = {**inject_context_defaults, "platform": "new_platform"}
    with patch("injector._load_config", return_value={
        "modules": {"time": True, "sources_blacklist": ["cron"]},
        "time": {"format": "cn_full"},
        "context": {"rules": ["测试规则"]},
    }):
        result = injector.inject_context(**kwargs)
    assert result is not None
    assert "🕐" in result["context"]
    assert "测试规则" in result["context"]


# ── edge cases ──────────────────────────────────────────────────────────────


def test_blacklisted_time_disabled_returns_none(inject_context_defaults):
    """platform="cron" in blacklist + modules.time=false → returns None."""
    kwargs = {**inject_context_defaults, "platform": "cron"}
    with patch("injector._load_config", return_value={
        "modules": {"time": False, "sources_blacklist": ["cron"]},
    }):
        result = injector.inject_context(**kwargs)
    assert result is None


def test_no_sources_blacklist_backward_compat(inject_context_defaults):
    """sources_blacklist not in modules → all platforms behave identically."""
    kwargs_cron = {**inject_context_defaults, "platform": "cron"}
    kwargs_discord = {**inject_context_defaults, "platform": "discord"}

    with patch("injector._load_config", return_value={
        "modules": {"time": True},
        "time": {"format": "cn_full"},
        "context": {"rules": ["测试规则"]},
    }):
        result_cron = injector.inject_context(**kwargs_cron)
        result_discord = injector.inject_context(**kwargs_discord)

    # Both go through the full pipeline — both contain time and rules
    assert result_cron is not None
    assert result_discord is not None
    assert "🕐" in result_cron["context"]
    assert "测试规则" in result_cron["context"]
    assert "🕐" in result_discord["context"]
    assert "测试规则" in result_discord["context"]
