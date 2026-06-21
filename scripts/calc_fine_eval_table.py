"""Calculate fine-grained evaluation results on multi-application tasks."""

import json
import re
from pathlib import Path
from collections import defaultdict

results_base = Path("/home/fuyikun/Documents/MacAgentBench/results")

MODELS = [
    # Baseline
    ("Baseline", "Claude Opus 4.6", results_base / "claude-opus-4-6/claude-opus-4-6-baseline"),
    ("Baseline", "GPT-5.4", results_base / "gpt-5.4/gpt-5.4-baseline"),
    ("Baseline", "Gemini 3.1 Pro", results_base / "gemini-3.1-pro-preview/gemini-3.1-pro-preview-baseline"),
    ("Baseline", "Qwen3VL-235B-A22B", results_base / "Qwen3-VL-235B-A22B-Thinking/qwen3-vl-235b-thinking-baseline-v8"),
    ("Baseline", "Qwen3VL-32B", results_base / "Qwen3-VL-32B-Thinking/qwen3-vl-32b-thinking-baseline"),
    ("Baseline", "Qwen3VL-8B", results_base / "Qwen3-VL-8B-Thinking/qwen3-vl-8b-thinking-baseline"),
    ("Baseline", "OpenCUA-32B", results_base / "OpenCUA-32B/opencua-32b-baseline"),
    ("Baseline", "OpenCUA-7B", results_base / "OpenCUA-7B/opencua-7b-baseline"),
    ("Baseline", "GUI-Owl-1.5-32B", results_base / "GUI-Owl-1.5-32B-Think/guiowl-32b-think-baseline"),
    ("Baseline", "GUI-Owl-1.5-8B", results_base / "GUI-Owl-1.5-8B-Think/guiowl-8b-think-baseline"),
    ("Baseline", "UI-TARS-72B-DPO", results_base / "UI-TARS-72B-DPO/uitars72b-dpo-baseline"),
    ("Baseline", "ScaleCUA-32B", results_base / "ScaleCUA-32B/scalecua-32b-baseline"),
    ("Baseline", "UI-TARS-1.5-7B", results_base / "UI-TARS-1.5-7B/uitars15-7b-baseline-v2"),
    ("Baseline", "ScaleCUA-7B", results_base / "ScaleCUA-7B/scalecua-7b-baseline"),
    ("Baseline", "InternVL-14B", results_base / "InternVL3_5-14B/internvl35-14b-baseline-v2"),
    ("Baseline", "InternVL-8B", results_base / "InternVL3_5-8B/internvl35-8b-baseline-v2"),
    # AgentS3
    ("AgentS3", "Claude Opus 4.6", results_base / "agents3/claude-opus-4-6"),
    ("AgentS3", "GPT-5.4", results_base / "agents3/gpt-5.4"),
    ("AgentS3", "Gemini 3.1 Pro", results_base / "agents3/gemini-3.1-pro-preview"),
    ("AgentS3", "Qwen3VL-235B-A22B", results_base / "agents3/Qwen3-VL-235B-A22B-Thinking"),
    ("AgentS3", "Qwen3VL-32B", results_base / "agents3/Qwen3-VL-32B-Thinking"),
    ("AgentS3", "Qwen3VL-8B", results_base / "agents3/Qwen3-VL-8B-Thinking"),
    ("AgentS3", "InternVL-14B", results_base / "agents3/InternVL3_5-14B"),
    ("AgentS3", "InternVL-8B", results_base / "agents3/InternVL3_5-8B"),
    # OpenClaw
    ("OpenClaw", "Claude Opus 4.6", results_base / "openclaw/claude-opus-4-6-thinking"),
    ("OpenClaw", "GPT-5.4", results_base / "openclaw/gpt-5.4"),
    ("OpenClaw", "Gemini 3.1 Pro", results_base / "openclaw/gemini-3.1-pro-preview"),
    ("OpenClaw", "Qwen3VL-235B-A22B", results_base / "openclaw/qwen3-vl-235b-thinking"),
    ("OpenClaw", "Qwen3VL-32B", results_base / "openclaw/qwen3-vl-32b-thinking"),
    ("OpenClaw", "Qwen3VL-8B", results_base / "openclaw/qwen3-vl-8b-thinking"),
    ("OpenClaw", "InternVL-14B", results_base / "openclaw/internvl35-14b"),
    ("OpenClaw", "InternVL-8B", results_base / "openclaw/internvl35-8b"),
]

CAPS = ["research", "app_state", "content_match", "file_ops", "system_config"]


def parse_result(rf):
    text = rf.read_text().strip()
    if text.startswith("EvalResult("):
        m_score = re.search(r'score=([\d.]+)', text)
        m_comp = re.search(r'completed=(True|False)', text)
        score = float(m_score.group(1)) if m_score else 0.0
        completed = m_comp.group(1) == "True" if m_comp else False
        return {"score": score, "completed": completed, "components": []}
    try:
        return json.loads(text)
    except:
        return None


if __name__ == "__main__":
    prev_framework = None
    for framework, model_name, model_path in MODELS:
        if framework != prev_framework:
            if prev_framework is not None:
                print()
            print(f"=== {framework} ===")
            prev_framework = framework

        multi_app_dir = model_path / "multi_app"
        total_tasks = passed_tasks = 0
        total_score = 0.0
        cap_counts = defaultdict(lambda: {"passed": 0, "total": 0})

        for rf in sorted(multi_app_dir.glob("*/result.txt")):
            d = parse_result(rf)
            if d is None:
                continue

            total_tasks += 1
            if d.get("completed", False):
                passed_tasks += 1
            total_score += d.get("score", 0.0)

            for comp in d.get("components", []):
                cap = comp.get("capability", "")
                s = comp.get("score", 0.0)
                if cap in CAPS:
                    cap_counts[cap]["total"] += 1
                    if s > 0:
                        cap_counts[cap]["passed"] += 1

        pass_rate = passed_tasks / total_tasks * 100 if total_tasks else 0
        avg_score = total_score / total_tasks * 100 if total_tasks else 0
        cap_pcts = {}
        for c in CAPS:
            cap_pcts[c] = (cap_counts[c]["passed"] / cap_counts[c]["total"] * 100
                           if cap_counts[c]["total"] > 0 else 0.0)

        print(f"& {model_name:24s} & {pass_rate:5.1f} & {avg_score:5.1f} & "
              f"{cap_pcts['research']:5.1f} & {cap_pcts['app_state']:5.1f} & "
              f"{cap_pcts['content_match']:5.1f} & {cap_pcts['file_ops']:5.1f} & "
              f"{cap_pcts['system_config']:5.1f} \\\\")
