"""Shared configuration root — set by __init__.py:register()."""

from __future__ import annotations

from pathlib import Path

_CONFIG_ROOT: Path | None = None
