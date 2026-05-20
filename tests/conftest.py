"""Shared test fixtures for hermes-persona tests."""

import json
import tempfile
from pathlib import Path

import pytest

import config
import injector


@pytest.fixture
def temp_config_root():
    """Create a temporary directory and point _CONFIG_ROOT at it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_root = config._CONFIG_ROOT
        config._CONFIG_ROOT = Path(tmpdir)
        yield Path(tmpdir)
        config._CONFIG_ROOT = old_root


@pytest.fixture
def write_config(temp_config_root):
    """Write persona-config.json into the temp config root."""

    def _write(config_dict: dict):
        config_path = temp_config_root / "persona-config.json"
        config_path.write_text(json.dumps(config_dict, ensure_ascii=False), encoding="utf-8")
        return config_path

    return _write


@pytest.fixture
def mock_load_config_empty():
    """Patch _load_config to always return {}."""
    import injector as mod

    old_load = mod._load_config
    mod._load_config = lambda: {}
    yield
    mod._load_config = old_load


@pytest.fixture
def inject_context_defaults():
    """Provide default arguments for inject_context()."""
    return dict(
        session_id="test-session",
        user_message="Hello",
        conversation_history=[],
        is_first_turn=True,
        model="claude",
        platform="test",
    )
