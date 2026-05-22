"""Shared test fixtures for hermes-persona tests."""

import json
import tempfile
from pathlib import Path

import pytest

import config
import injector


@pytest.fixture
def temp_config_root():
    """Create a temporary directory and point _CONFIG_ROOT at it.

    Also temporarily moves aside the repo root's persona-config.json
    so that _resolve_config_path L1 (Path(__file__).parent / filename)
    doesn't shadow the test config written to _CONFIG_ROOT.
    """
    repo_config = Path(__file__).resolve().parent.parent / "persona-config.json"
    repo_config_backup = repo_config.with_suffix(".json.bak")

    with tempfile.TemporaryDirectory() as tmpdir:
        old_root = config._CONFIG_ROOT
        config._CONFIG_ROOT = Path(tmpdir)

        # 创建插件子目录结构（新文件布局）
        plugin_dir = Path(tmpdir) / "plugins" / "hermes-persona"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "keywords").mkdir(exist_ok=True)
        (plugin_dir / "state").mkdir(exist_ok=True)

        # 临时移走 repo 根的 persona-config.json（避免 L1 遮蔽测试配置）
        if repo_config.is_file():
            repo_config.rename(repo_config_backup)
            restore = True
        else:
            restore = False

        try:
            yield Path(tmpdir)
        finally:
            config._CONFIG_ROOT = old_root
            if restore:
                repo_config_backup.rename(repo_config)


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
