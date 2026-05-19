"""Random expression variance — two-layer randomization.

Layer 1 — Appearance probability (probability): random.random() < prob
Layer 2 — Expression variation (variants): random.choice(variants)

Each dimension is independently decided per turn.
"""

import random


def _randomize_variance(variance_cfg: dict) -> list[str]:
    """Select random expression variants from each configured category.

    Args:
        variance_cfg: {"category_name": {"probability": 0.5, "variants": [...]}, ...}

    Returns:
        List of selected variant strings. May be empty if no category is selected.
    """
    if not variance_cfg:
        return []

    results: list[str] = []
    for category, cat_cfg in variance_cfg.items():
        if not isinstance(cat_cfg, dict):
            continue

        # --- Validate & normalise probability ---
        prob = cat_cfg.get("probability", 0.5)
        if not isinstance(prob, (int, float)):
            prob = 0.5
        elif not (0.0 <= prob <= 1.0):
            prob = 0.5

        # --- Layer 1: appearance probability ---
        if random.random() > prob:
            continue

        # --- Layer 2: expression variation ---
        variants = cat_cfg.get("variants")
        if not isinstance(variants, list) or not variants:
            continue

        chosen = random.choice(variants)
        results.append(str(chosen))

    return results
