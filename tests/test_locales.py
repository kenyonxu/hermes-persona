"""Tests for locale/i18n system (SPEC-003 §2.3)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from locales import (
    _resolve_language,
    _load_translations,
    _init_locales,
    _t,
    set_language,
)

# Save original state for restoration
_ORIG_LANG = None
_ORIG_TRANS = None


def setup_module():
    """Save original locale state."""
    global _ORIG_LANG, _ORIG_TRANS
    from locales import _ACTIVE_LANG, _TRANSLATIONS
    _ORIG_LANG = _ACTIVE_LANG
    _ORIG_TRANS = dict(_TRANSLATIONS)


def teardown_module():
    """Restore original locale state."""
    from locales import _ACTIVE_LANG, _TRANSLATIONS
    global _ORIG_LANG, _ORIG_TRANS
    # Use module-level assignment
    import locales as m
    m._ACTIVE_LANG = _ORIG_LANG
    m._TRANSLATIONS = dict(_ORIG_TRANS) if _ORIG_TRANS else {}


class TestResolveLanguage:
    """_resolve_language() 逻辑测试。"""

    def test_explicit_zh(self):
        """language: 'zh' → 'zh'。"""
        assert _resolve_language({"language": "zh"}) == "zh"

    def test_explicit_en(self):
        """language: 'en' → 'en'。"""
        assert _resolve_language({"language": "en"}) == "en"

    def test_auto_cn_full(self):
        """auto + time.format='cn_full' → 'zh'。"""
        assert _resolve_language({"language": "auto", "time": {"format": "cn_full"}}) == "zh"

    def test_auto_iso(self):
        """auto + time.format='iso' → 'en'。"""
        assert _resolve_language({"language": "auto", "time": {"format": "iso"}}) == "en"

    def test_no_language_config(self):
        """无 language 键 → 默认 'zh'。"""
        assert _resolve_language({}) == "zh"

    def test_no_time_config(self):
        """language='auto' 但无 time 配置 → 'zh'（默认）。"""
        assert _resolve_language({"language": "auto"}) == "zh"


class TestLoadTranslations:
    """_load_translations() 测试。"""

    def test_load_zh(self):
        """加载 zh.json 成功。"""
        translations = _load_translations(".", "zh")
        assert isinstance(translations, dict)
        assert "debug.header" in translations
        assert translations["debug.header"] == "🔧 [Debug] 本轮注入:"

    def test_load_en(self):
        """加载 en.json 成功。"""
        translations = _load_translations(".", "en")
        assert isinstance(translations, dict)
        assert "debug.header" in translations
        assert translations["debug.header"] == "🔧 [Debug] Turn Summary:"

    def test_missing_locale_file(self):
        """不存在的语言 → 空 dict。"""
        translations = _load_translations(".", "jp")
        assert translations == {}

    def test_key_count_match(self):
        """中英文翻译键数量一致（英文可以多但不能少）。"""
        zh = _load_translations(".", "zh")
        en = _load_translations(".", "en")
        for k in zh:
            assert k in en, f"Missing key in en.json: {k}"


class TestTranslateFunction:
    """_t() 翻译函数测试。"""

    def setup_method(self):
        _init_locales(".", {"language": "zh"})

    def test_basic_translation(self):
        """基本翻译。"""
        result = _t("debug.header")
        assert result == "🔧 [Debug] 本轮注入:"

    def test_format_interpolation(self):
        """参数插值。"""
        result = _t("modules.static_rules", count=8)
        assert "8" in result
        assert "条静态规则" in result

    def test_missing_key(self):
        """缺失键 → 返回键名本身。"""
        result = _t("nonexistent.key")
        assert result == "nonexistent.key"

    def test_en_translation(self):
        """英文翻译。"""
        set_language("en", ".")
        result = _t("debug.header")
        assert result == "🔧 [Debug] Turn Summary:"
        # Restore zh for other tests
        set_language("zh", ".")


class TestFallbackBehavior:
    """回退逻辑测试。"""

    def test_active_lang_missing_fallback_to_zh(self):
        """语言启用了但翻译文件为空 → zh 回退。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            locales_dir = tmpdir_path / "locales"
            locales_dir.mkdir(parents=True)
            en_file = locales_dir / "en.json"
            en_file.write_text("{}", encoding="utf-8")
            zh_file = locales_dir / "zh.json"
            zh_file.write_text(json.dumps({"debug.header": "测试回退"}), encoding="utf-8")

            _init_locales(str(tmpdir_path), {"language": "en"})
            from locales import _TRANSLATIONS
            assert _TRANSLATIONS.get("debug.header") == "测试回退"

        # Restore
        _init_locales(".", {"language": "zh"})
