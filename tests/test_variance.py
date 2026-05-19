"""P2 tests for variance — two-layer randomization."""

import random

import pytest

from variance import _randomize_variance


class TestRandomizeVariance:
    def test_empty_config_returns_empty(self):
        """Empty variance config returns []."""
        assert _randomize_variance({}) == []

    def test_probability_zero_never_appears(self):
        """probability=0 means the category is never selected."""
        cfg = {
            "tone": {"probability": 0, "variants": ["variant_a"]},
        }
        # With probability 0, random.random() > 0 is always True → skip
        for _ in range(200):
            result = _randomize_variance(cfg)
            assert result == []

    def test_probability_one_always_appears(self):
        """probability=1.0 means the category is always selected."""
        cfg = {
            "tone": {"probability": 1.0, "variants": ["always_on"]},
        }
        for _ in range(200):
            result = _randomize_variance(cfg)
            assert result == ["always_on"]

    def test_single_variant_always_returns_it(self):
        """With probability=1.0 and a single variant, it's always returned."""
        cfg = {
            "greeting": {"probability": 1.0, "variants": ["你好"]},
        }
        result = _randomize_variance(cfg)
        assert result == ["你好"]

    def test_invalid_prob_string_degraded(self):
        """probability="high" (non-numeric) → degraded to 0.5."""
        cfg = {
            "tone": {"probability": "high", "variants": ["test"]},
        }
        # Force seed so degraded 0.5 is predictable for one call
        random.seed(42)
        result = _randomize_variance(cfg)
        # With seed(42), random.random() → 0.639... > 0.5 → skip
        assert result == []

    def test_out_of_range_prob_degraded(self):
        """probability=1.5 (out of [0,1]) → degraded to 0.5."""
        cfg = {
            "tone": {"probability": 1.5, "variants": ["test"]},
        }
        random.seed(0)  # random.random() → 0.844... > 0.5 → skip
        result = _randomize_variance(cfg)
        assert result == []

    def test_empty_variants_skipped(self):
        """variants=[] → skip this category entirely."""
        cfg = {
            "tone": {"probability": 1.0, "variants": []},
        }
        result = _randomize_variance(cfg)
        assert result == []

    def test_non_list_variants_skipped(self):
        """variants not a list → skip."""
        cfg = {
            "tone": {"probability": 1.0, "variants": "not_a_list"},
        }
        result = _randomize_variance(cfg)
        assert result == []

    def test_multiple_categories_independent(self):
        """Each category is independently decided."""
        cfg = {
            "mood": {"probability": 1.0, "variants": ["开心"]},
            "tone": {"probability": 0.0, "variants": ["严肃"]},
            "speed": {"probability": 1.0, "variants": ["语速快"]},
        }
        result = _randomize_variance(cfg)
        assert "开心" in result
        assert "严肃" not in result
        assert "语速快" in result
        assert len(result) == 2

    def test_variance_statistical_spread(self):
        """1000 calls with probability=0.5 → appearance rate 40%-60%."""
        cfg = {
            "mood": {"probability": 0.5, "variants": ["开心"]},
        }
        hits = 0
        for _ in range(1000):
            result = _randomize_variance(cfg)
            if result:
                hits += 1
        # With 1000 trials and true probability 0.5,
        # 99.99% CI is roughly 0.5 ± 0.05 → [450, 550]
        # We use a slightly wider range for robustness: 400-600
        assert 400 <= hits <= 600, f"Appearance rate {hits}/1000 outside expected range"

    def test_choice_selects_from_variants(self):
        """random.choice picks from the given variants."""
        cfg = {
            "greeting": {"probability": 1.0, "variants": ["A", "B", "C"]},
        }
        random.seed(123)
        result = _randomize_variance(cfg)
        assert result[0] in ("A", "B", "C")

    def test_result_is_always_str(self):
        """Each selected variant is converted to str."""
        cfg = {
            "val": {"probability": 1.0, "variants": [42, 3.14]},
        }
        result = _randomize_variance(cfg)
        assert len(result) == 1
        assert isinstance(result[0], str)
        assert result[0] in ("42", "3.14")

    def test_non_dict_category_skipped(self):
        """Non-dict category values are skipped."""
        cfg = {
            "bad_cat": "not_a_dict",
        }
        result = _randomize_variance(cfg)
        assert result == []
