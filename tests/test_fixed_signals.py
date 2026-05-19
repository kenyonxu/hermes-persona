"""Tests for fixed signal functions — message length and reply gap hints.

Per SPEC-002 §10.6: TC-IDs FS-01~09.
"""

import json
import time
from pathlib import Path

import pytest

import injector


# ── TestMessageLengthHint: FS-01 ~ FS-03 ──────────────────────────────────


class TestMessageLengthHint:
    """FS-01 ~ FS-03: _message_length_hint() 测试。"""

    def test_FS01_short_message_returns_hint(self):
        """FS-01: 消息长度 < threshold → 返回 '📏 消息较短'。"""
        result = injector._message_length_hint(
            "好",
            {"message_length": {"enabled": True, "threshold": 50}},
        )
        assert result == "📏 消息较短"

    def test_FS02_message_at_threshold_returns_none(self):
        """FS-02: 消息长度 ≥ threshold → 返回 None。"""
        msg = "x" * 50
        result = injector._message_length_hint(
            msg,
            {"message_length": {"enabled": True, "threshold": 50}},
        )
        assert result is None

    def test_FS03_disabled_returns_none(self):
        """FS-03: enabled=false → 返回 None。"""
        result = injector._message_length_hint(
            "好",
            {"message_length": {"enabled": False}},
        )
        assert result is None


# ── TestReplyGapHint: FS-04 ~ FS-09 ───────────────────────────────────────


class TestReplyGapHint:
    """FS-04 ~ FS-09: _reply_gap_hint() + _save_reply_timing() 测试。"""

    def test_FS04_gap_above_threshold(self, tmp_path):
        """FS-04: 间隔 > threshold → 返回 '🎵 欢迎回来'。"""
        storage = tmp_path / "timing.json"
        storage.write_text(
            json.dumps({"last_reply_at": time.time() - 3600}),  # 60 分钟前
            encoding="utf-8",
        )
        result, _ = injector._reply_gap_hint({
            "reply_gap": {
                "enabled": True,
                "threshold_minutes": 30,
                "storage_path": str(storage),
            },
        })
        assert result == "🎵 欢迎回来"

    def test_FS05_gap_below_threshold(self, tmp_path):
        """FS-05: 间隔 ≤ threshold → 返回 None。"""
        storage = tmp_path / "timing.json"
        storage.write_text(
            json.dumps({"last_reply_at": time.time() - 600}),  # 10 分钟前
            encoding="utf-8",
        )
        result, _ = injector._reply_gap_hint({
            "reply_gap": {
                "enabled": True,
                "threshold_minutes": 30,
                "storage_path": str(storage),
            },
        })
        assert result is None

    def test_FS06_no_timing_file(self, tmp_path):
        """FS-06: 文件不存在 → 返回 None（首次对话不欢迎回来）。"""
        storage = tmp_path / "nonexistent.json"
        result, _ = injector._reply_gap_hint({
            "reply_gap": {
                "enabled": True,
                "threshold_minutes": 30,
                "storage_path": str(storage),
            },
        })
        assert result is None

    def test_FS07_disabled_returns_none(self):
        """FS-07: enabled=false → 返回 None。"""
        result, _ = injector._reply_gap_hint({
            "reply_gap": {"enabled": False},
        })
        assert result is None

    def test_FS08_corrupt_file_returns_none(self, tmp_path):
        """FS-08: 文件损坏 → 返回 None，不抛异常。"""
        storage = tmp_path / "timing.json"
        storage.write_text("not json at all", encoding="utf-8")
        result, _ = injector._reply_gap_hint({
            "reply_gap": {
                "enabled": True,
                "threshold_minutes": 30,
                "storage_path": str(storage),
            },
        })
        assert result is None

    def test_FS09_save_reply_timing_writes_file(self, tmp_path):
        """FS-09: _save_reply_timing() 写回 last_reply_at。"""
        storage = tmp_path / "timing.json"
        now_ts = time.time()
        injector._save_reply_timing(
            {"reply_gap": {"enabled": True, "storage_path": str(storage)}},
            now_ts,
        )
        assert storage.is_file()
        data = json.loads(storage.read_text(encoding="utf-8"))
        assert abs(data["last_reply_at"] - now_ts) < 1.0
