"""Calculate evaluation metrics for all models.

Usage:
    python calc_metrics.py results/openclaw/claude-opus-4-6-thinking
    python calc_metrics.py results/openclaw/gpt-5.4
    python calc_metrics.py results/Qwen3-VL-8B-Thinking/qwen3-vl-8b-thinking-baseline
    python calc_metrics.py --all  # scan all result directories
"""

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from datetime import datetime

PRICING_FILE = Path(__file__).with_name("model_pricing.json")


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def _load_pricing():
    if not PRICING_FILE.exists():
        return {}
    try:
        return json.load(open(PRICING_FILE))
    except Exception:
        return {}


def _parse_iso(ts_str):
    if not ts_str or not isinstance(ts_str, str):
        return None
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except Exception:
        return None


def extract_session_metrics(task_dir: Path):
    """Extract metrics from OpenClaw session JSONL files."""
    session_dir = task_dir / "sessions"
    if not session_dir.exists():
        return None

    metrics = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read": 0,
        "cache_write": 0,
        "rounds": 0,
        "runtime_seconds": 0.0,
    }

    for jsonl in sorted(session_dir.glob("*.jsonl")):
        first_ts = last_ts = None
        try:
            with open(jsonl) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue

                    ts = _parse_iso(d.get("timestamp"))
                    if ts:
                        if first_ts is None or ts < first_ts:
                            first_ts = ts
                        if last_ts is None or ts > last_ts:
                            last_ts = ts

                    msg = d.get("message", {})
                    if msg.get("role") == "assistant":
                        metrics["rounds"] += 1

                    usage = msg.get("usage", {})
                    metrics["input_tokens"] += int(usage.get("input", 0) or 0)
                    metrics["output_tokens"] += int(usage.get("output", 0) or 0)
                    metrics["cache_read"] += int(usage.get("cacheRead", 0) or 0)
                    metrics["cache_write"] += int(usage.get("cacheWrite", 0) or 0)
        except Exception:
            continue

        if first_ts and last_ts:
            metrics["runtime_seconds"] += max(0, (last_ts - first_ts).total_seconds())

    return metrics


def extract_traj_metrics(task_dir: Path):
    """Extract metrics from traj.jsonl (baseline agents)."""
    traj_file = task_dir / "traj.jsonl"
    if not traj_file.exists():
        return None

    metrics = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read": 0,
        "cache_write": 0,
        "rounds": 0,
        "runtime_seconds": 0.0,
    }

    try:
        with open(traj_file) as f:
            for line in f:
                d = json.loads(line.strip())
                metrics["rounds"] += 1
                metrics["input_tokens"] += int(d.get("input_tokens", 0) or 0)
                metrics["output_tokens"] += int(d.get("output_tokens", 0) or 0)
                metrics["cache_read"] += int(d.get("cache_read", 0) or 0)
                metrics["cache_write"] += int(d.get("cache_write", 0) or 0)
    except Exception:
        pass

    return metrics


def analyze(result_root: str):
    result_root = Path(result_root).resolve()
    pricing = _load_pricing()
    result_files = sorted(result_root.glob("**/result.txt"))

    if not result_files:
        print(f"No results found in {result_root}")
        return

    # Detect model name
    model_name = result_root.name
    model_pricing = pricing.get(model_name, {})
    input_price = _safe_float(model_pricing.get("input_per_million", 0))
    output_price = _safe_float(model_pricing.get("output_per_million", 0))

    # Accumulators
    total = 0
    passed = 0
    groups = defaultdict(list)
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_write = 0
    total_rounds = 0
    total_runtime = 0.0

    for rf in result_files:
        try:
            d = json.load(open(rf))
        except Exception:
            continue

        completed = bool(d.get("completed", False))
        total += 1
        if completed:
            passed += 1

        task_name = rf.parent.name
        domain = rf.parent.parent.name
        group_id = f"{domain}/{task_name.rsplit('_', 1)[0]}"
        groups[group_id].append(completed)

        # Extract token metrics
        task_dir = rf.parent
        metrics = extract_session_metrics(task_dir)
        if metrics is None:
            metrics = extract_traj_metrics(task_dir)
        if metrics:
            total_input += metrics["input_tokens"]
            total_output += metrics["output_tokens"]
            total_cache_read += metrics["cache_read"]
            total_cache_write += metrics["cache_write"]
            total_rounds += metrics["rounds"]
            total_runtime += metrics["runtime_seconds"]

    # Calculate metrics
    n_groups = len(groups)
    any_pass = sum(1 for g in groups.values() if any(g))
    all_pass = sum(1 for g in groups.values() if all(g))

    pass1 = passed / total * 100 if total else 0
    passk = any_pass / n_groups * 100 if n_groups else 0
    pass_k = all_pass / n_groups * 100 if n_groups else 0
    rounds_avg = total_rounds / total if total else 0

    # OpenClaw sessions: input/cacheRead/cacheWrite always separate, so always add
    # Baseline traj.jsonl via OpenAI API: prompt_tokens already includes cached, don't add
    # Baseline traj.jsonl via Anthropic API: input_tokens excludes cache, need to add
    # Heuristic: "baseline" in name → traj.jsonl; non-claude baseline → don't add cache
    is_baseline = "baseline" in model_name
    is_anthropic = "claude" in model_name
    if is_baseline and not is_anthropic:
        effective_input = total_input
    else:
        effective_input = total_input + total_cache_read + total_cache_write

    cost_total = (effective_input * input_price + total_output * output_price) / 1_000_000
    cost_avg = cost_total / total if total else 0

    input_avg = effective_input / total if total else 0
    output_avg = total_output / total if total else 0

    print(f"=== {result_root.name} ({total}/676) ===")
    print(f"  Pass@1:       {pass1:.1f}%")
    print(f"  Pass@k:       {passk:.1f}%")
    print(f"  Pass^k:       {pass_k:.1f}%")
    print(f"  Rounds avg:   {rounds_avg:.1f}")
    print(f"  Input avg:    {input_avg:,.0f} tokens")
    print(f"  Output avg:   {output_avg:,.0f} tokens")
    print(f"  Cost avg:     ${cost_avg:.2f}/task")
    print(f"  Cost total:   ${cost_total:.2f}")
    print(f"  Runtime avg:  {total_runtime/total:.1f}s" if total else "")
    print()


def find_all_results():
    """Find all result directories."""
    results_dir = Path("results")
    dirs = []
    # OpenClaw results: results/openclaw/*/
    for d in sorted((results_dir / "openclaw").glob("*")):
        if d.is_dir() and (d / "multi_app").exists():
            dirs.append(str(d))
    # Baseline results: results/*/*/
    for model_dir in sorted(results_dir.glob("*")):
        if model_dir.name == "openclaw":
            continue
        for sub in sorted(model_dir.glob("*")):
            if sub.is_dir() and any(sub.glob("**/result.txt")):
                dirs.append(str(sub))
    return dirs


def main():
    parser = argparse.ArgumentParser(description="Calculate evaluation metrics.")
    parser.add_argument("result_root", nargs="?", help="Path to result directory")
    parser.add_argument("--all", action="store_true", help="Scan all result directories")
    args = parser.parse_args()

    if args.all:
        for d in find_all_results():
            analyze(d)
    elif args.result_root:
        analyze(args.result_root)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
