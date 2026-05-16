#!/usr/bin/env python3
"""Performance benchmark for hermes-persona inject_context().

Measures single inject_context() call latency (excluding external API calls)
and verifies it meets the < 5ms requirement.

Usage:
    python scripts/benchmark.py              # run from repo root
    python scripts/benchmark.py --runs 5000  # custom iteration count
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

# Ensure repo root is on the path for imports
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from hermes_persona import injector  # noqa: E402

# ---------------------------------------------------------------------------
# Benchmark configurations
# ---------------------------------------------------------------------------

MINIMAL_CONFIG: dict = {"hermes-persona": {}}

FULL_CONFIG: dict = {
    "hermes-persona": {
        "time": {"enabled": True, "format": "cn_full"},
        "context": {
            "rules": [
                "你是一个友好的AI助手",
                "请用简洁清晰的语言回答",
                "保持专业但温暖的语气",
            ],
            "rules_first_turn_only": [
                "这是本次会话的第一条消息，请向用户打招呼",
            ],
            "dynamic": {
                "time_slots": {
                    "00:00-06:00": ["深夜模式：简洁柔和"],
                    "06:00-12:00": ["早晨模式：充满活力"],
                    "12:00-18:00": ["下午模式：保持高效"],
                    "18:00-24:00": ["傍晚模式：适当放松"],
                },
                "turn_stage": {
                    "first_turn": ["首轮：建立关系"],
                    "after_10": ["第10轮：深化对话"],
                    "after_50": ["第50轮：深度总结"],
                },
                "keywords": {
                    "报错|bug|error": ["检测到问题——优先排查"],
                    "哈哈|开心|笑": ["用户情绪积极——保持轻松"],
                    "谢谢|感谢": ["友好回应感谢"],
                },
            },
        },
        "variance": {
            "tone": {
                "probability": 0.6,
                "variants": ["变体A", "变体B", "变体C", "变体D"],
            },
            "style": {
                "probability": 0.4,
                "variants": ["风格1", "风格2", "风格3"],
            },
        },
        "memory": {"enabled": False, "api_url": "", "max_results": 3},
        "project": {"enabled": False, "kanban_path": "", "label": ""},
        "guard": {"enabled": False, "rules": {"blocked": [], "require_confirmation": []}, "audit": {"enabled": False, "log_path": ""}},
    }
}


def run_benchmark(
    config: dict,
    runs: int = 1000,
    label: str = "benchmark",
    is_first_turn: bool = False,
) -> dict:
    """Run inject_context() many times and collect timing statistics.

    Args:
        config: The full persona-config.json dict (including top-level key).
        runs: Number of iterations.
        label: Human-readable label for this benchmark.
        is_first_turn: Whether to simulate first-turn invocation.

    Returns:
        Dict with min/avg/median/max/p99 timings in milliseconds.
    """
    # Create a temporary config file so _load_config() can find it
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "persona-config.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

        # Point injector at our temp config
        old_root = injector._CONFIG_ROOT
        injector._CONFIG_ROOT = Path(tmpdir)

        try:
            # Warmup: two calls to stabilise Python bytecode cache
            for _ in range(3):
                injector.inject_context(
                    session_id="bench-session",
                    user_message="你好，请帮我分析一下这个报错",
                    conversation_history=[{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好！有什么可以帮你的？"}] * 25,
                    is_first_turn=is_first_turn,
                    model="benchmark-model",
                    platform="linux",
                )

            # Timed runs
            timings: list[float] = []
            for _ in range(runs):
                # Use turn_count=25 to trigger after_10 turn_stage rule
                conv_hist = [{"role": "user", "content": "msg"}, {"role": "assistant", "content": "reply"}] * 25
                t0 = time.perf_counter()
                injector.inject_context(
                    session_id="bench-session",
                    user_message="你好，请帮我分析一下这个报错信息",
                    conversation_history=conv_hist,
                    is_first_turn=is_first_turn,
                    model="benchmark-model",
                    platform="linux",
                )
                elapsed = time.perf_counter() - t0
                timings.append(elapsed * 1000)  # convert to ms
        finally:
            injector._CONFIG_ROOT = old_root

    timings.sort()
    return {
        "label": label,
        "runs": runs,
        "min_ms": round(timings[0], 3),
        "avg_ms": round(statistics.mean(timings), 3),
        "median_ms": round(statistics.median(timings), 3),
        "p95_ms": round(timings[int(runs * 0.95)], 3),
        "p99_ms": round(timings[int(runs * 0.99)], 3),
        "max_ms": round(timings[-1], 3),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="hermes-persona performance benchmark")
    parser.add_argument("--runs", type=int, default=1000, help="Iterations per scenario")
    args = parser.parse_args()
    runs = args.runs

    print(f"{'=' * 60}")
    print(f"hermes-persona inject_context() 性能基准")
    print(f"{'=' * 60}")
    print(f"每场景迭代: {runs} 次")
    print()

    results: list[dict] = []

    # Scenario 1: minimal config
    print("▶ 场景 1: 最小配置 (空 {}) ...", end=" ", flush=True)
    r = run_benchmark(MINIMAL_CONFIG, runs=runs, label="最小配置 (空 {})")
    results.append(r)
    print(f"avg={r['avg_ms']}ms, p99={r['p99_ms']}ms")

    # Scenario 2: full config, non-first-turn
    print("▶ 场景 2: 完整配置 (非首轮) ...", end=" ", flush=True)
    r = run_benchmark(FULL_CONFIG, runs=runs, label="完整配置 (非首轮)")
    results.append(r)
    print(f"avg={r['avg_ms']}ms, p99={r['p99_ms']}ms")

    # Scenario 3: full config, first turn
    print("▶ 场景 3: 完整配置 (首轮) ...", end=" ", flush=True)
    r = run_benchmark(FULL_CONFIG, runs=runs, label="完整配置 (首轮)", is_first_turn=True)
    results.append(r)
    print(f"avg={r['avg_ms']}ms, p99={r['p99_ms']}ms")

    # -------------------------------------------------------------------
    # Report
    # -------------------------------------------------------------------
    print()
    print(f"{'─' * 60}")
    print(f"{'场景':<30} {'平均':>8} {'中位':>8} {'P99':>8}")
    print(f"{'─' * 60}")
    for r in results:
        print(
            f"{r['label']:<30}"
            f" {r['avg_ms']:>7.3f}ms"
            f" {r['median_ms']:>7.3f}ms"
            f" {r['p99_ms']:>7.3f}ms"
        )

    # Verdict
    print()
    threshold_ms = 5.0
    all_pass = all(r["p99_ms"] < threshold_ms for r in results)
    worst = max(r["p99_ms"] for r in results)

    if all_pass:
        print(f"✅ 全部场景 P99 延迟 ({worst:.3f}ms) < {threshold_ms}ms — 达标")
    else:
        failing = [r for r in results if r["p99_ms"] >= threshold_ms]
        print(f"❌ {len(failing)} 个场景未达标 (阈值 {threshold_ms}ms):")
        for r in failing:
            print(f"   - {r['label']}: P99={r['p99_ms']}ms")

    print()
    print(f"{'=' * 60}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
