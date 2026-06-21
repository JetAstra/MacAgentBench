import json
import re
from pathlib import Path
from collections import defaultdict

results_base = Path("/home/fuyikun/Documents/MacAgentBench/results")

# Category mapping from plot_sunburst.py
CATEGORIES = {
    "Productivity": ["notes", "new_apple_notes", "reminders", "new_reminders", "calendar", "pages", "numbers", "keynote", "new_obsidian"],
    "System": ["finder", "terminal", "mac_system_settings", "clock"],
    "Internet": ["safari", "new_github", "new_himalaya", "new_blogwatcher", "new_weather"],
    "Development": ["vscode", "new_tmux", "new_clawhub"],
    "Multimedia": ["new_songsee", "new_gifgrep", "new_whisper", "new_sherpa_onnx_tts", "new_video_frames", "new_peekaboo"],
    "Multi-App": ["multi_app"],
}

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
    ("Baseline", "UI-TARS-1.5-7B", results_base / "UI-TARS-1.5-7B/uitars15-7b-baseline-v2"),
    ("Baseline", "ScaleCUA-32B", results_base / "ScaleCUA-32B/scalecua-32b-baseline"),
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

def parse_result(rf):
    text = rf.read_text().strip()
    if text in ("True", "False"):
        return text == "True"
    if text.startswith("EvalResult("):
        m = re.search(r'completed=(True|False)', text)
        return m.group(1) == "True" if m else False
    try:
        d = json.loads(text)
        return bool(d.get("completed", False))
    except:
        return False

def calc_category_pass1(result_dir, domains):
    total = passed = 0
    for domain in domains:
        domain_dir = result_dir / domain
        if not domain_dir.exists():
            continue
        for rf in domain_dir.glob("*/result.txt"):
            total += 1
            if parse_result(rf):
                passed += 1
    return (passed / total * 100) if total else 0

prev_fw = None
for fw, model_name, model_path in MODELS:
    if fw != prev_fw:
        if prev_fw is not None:
            print()
        print(f"=== {fw} ===")
        prev_fw = fw
    
    cats = {}
    for cat_name, domains in CATEGORIES.items():
        cats[cat_name] = calc_category_pass1(model_path, domains)
    
    print(f"& {model_name:24s} & {cats['Productivity']:5.1f} & {cats['System']:5.1f} & "
          f"{cats['Internet']:5.1f} & {cats['Development']:5.1f} & "
          f"{cats['Multimedia']:5.1f} & {cats['Multi-App']:5.1f} \\\\")
