"""Shared configuration root — set by __init__.py:register()."""

from __future__ import annotations

from pathlib import Path

_CONFIG_ROOT: Path | None = None


def _resolve_config_path(filename: str = "persona-config.json") -> Path | None:
    """三层 fallback 解析配置文件路径。

    1. 插件目录（新规范）→ Path(__file__).parent / filename
    2. _CONFIG_ROOT（旧规范，profile 根目录）
    3. 返回 None（调用方自行处理）
    """
    # L1: 插件目录（__file__ 是 config.py 所在目录 = 插件根）
    plugin_path = Path(__file__).resolve().parent / filename
    if plugin_path.is_file():
        return plugin_path

    # L2: _CONFIG_ROOT（旧规范，向后兼容）
    if _CONFIG_ROOT is not None:
        legacy_path = _CONFIG_ROOT / filename
        if legacy_path.is_file():
            return legacy_path

    return None
