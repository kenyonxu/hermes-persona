"""Locale loader and translation utility for hermes-persona debug output.

Design:
- Translations are preloaded into memory at plugin registration time
- Missing keys fall back to hardcoded Chinese (current behavior)
- Missing locale files fall back to Chinese
- _t(key, **kwargs) performs str.format() style interpolation
"""

from __future__ import annotations

import json
from pathlib import Path

# In-memory cache: loaded once at registration time
_TRANSLATIONS: dict[str, str] = {}
_ACTIVE_LANG: str = "zh"


def _resolve_language(config: dict) -> str:
    """Resolve effective language from config.

    Priority:
        1. config["language"] if set to "zh" or "en"
        2. "auto" → infer from config["time"]["format"]
            "cn_full" → "zh", anything else → "en"
        3. Default → "zh"
    """
    lang = config.get("language", "auto")
    if lang in ("zh", "en"):
        return lang
    # "auto" or any other value → infer from time.format
    time_cfg = config.get("time", {})
    tf = time_cfg.get("format", "")
    if tf == "cn_full":
        return "zh"
    # No time config or unknown format → default to zh
    if not tf:
        return "zh"
    return "en"


def _load_translations(plugin_dir: str | Path, lang: str) -> dict[str, str]:
    """Load translation dict for a given language from locales/{lang}.json.

    Args:
        plugin_dir: Path to the hermes-persona plugin directory.
        lang: Language code ("zh" or "en").

    Returns:
        Translation dict. Returns empty dict if file not found or parse error.
    """
    locale_path = Path(plugin_dir) / "locales" / f"{lang}.json"
    try:
        if locale_path.is_file():
            data = json.loads(locale_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _init_locales(plugin_dir: str | Path, config: dict) -> None:
    """Initialize locale system: resolve language and preload translations.

    Must be called once at plugin registration time.

    Args:
        plugin_dir: Plugin directory path (where locales/ lives).
        config: Fully loaded hermes-persona config dict.
    """
    global _TRANSLATIONS, _ACTIVE_LANG

    # If no language config key exists, fall back to auto-detect
    _ACTIVE_LANG = _resolve_language(config)
    _TRANSLATIONS = _load_translations(plugin_dir, _ACTIVE_LANG)

    # If active lang translations are empty, try zh as fallback
    if not _TRANSLATIONS and _ACTIVE_LANG != "zh":
        zh_fallback = _load_translations(plugin_dir, "zh")
        if zh_fallback:
            _TRANSLATIONS = zh_fallback


def _t(key: str, **kwargs) -> str:
    """Translate a key with optional format parameters.

    Falls back to the key itself if no translation found.

    Args:
        key: Translation key (e.g., "modules.time.injected").
        **kwargs: Format parameters for str.format() interpolation.

    Returns:
        Translated and formatted string.
    """
    template = _TRANSLATIONS.get(key)
    if template is None:
        return key  # fallback: return raw key (will be handled by caller)
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template


def set_language(lang: str, plugin_dir: str | Path) -> None:
    """Dynamically change the active language at runtime (for testing).

    Args:
        lang: "zh" or "en".
        plugin_dir: Plugin directory for re-loading translations.
    """
    global _TRANSLATIONS, _ACTIVE_LANG
    _ACTIVE_LANG = lang
    _TRANSLATIONS = _load_translations(plugin_dir, lang)
