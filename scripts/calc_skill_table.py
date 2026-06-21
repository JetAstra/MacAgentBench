"""Calculate skill vs no-skill Pass@1 table across frameworks."""

import json
import re
from pathlib import Path

SKILL_DOMAINS = [
    "new_apple_notes", "notes", "new_reminders", "reminders",
    "new_blogwatcher", "new_clawhub", "new_gifgrep", "new_github",
    "new_himalaya", "new_obsidian", "new_peekaboo", "new_sherpa_onnx_tts",
    "new_songsee", "new_tmux", "new_video_frames", "new_weather", "new_whisper",
]

NO_SKILL_DOMAINS = [
    "keynote", "pages", "numbers", "terminal", "safari", "finder",
    "clock", "calendar", "vscode", "mac_system_settings",
]

results_base = Path("/home/fuyikun/Documents/MacAgentBench/results")

MODELS = [
    # (display_name, baseline_path, agents3_path, openclaw_path)
    ("Claude Opus 4.6",
     results_base / "claude-opus-4-6/claude-opus-4-6-baseline",
     results_base / "agents3/claude-opus-4-6",
     results_base / "openclaw/claude-opus-4-6-thinking"),
    ("GPT-5.4",
     results_base / "gpt-5.4/gpt-5.4-baseline",
     results_base / "agents3/gpt-5.4",
     results_base / "openclaw/gpt-5.4"),
    ("Gemini 3.1 Pro",
     results_base / "gemini-3.1-pro-preview/gemini-3.1-pro-preview-baseline",
     results_base / "agents3/gemini-3.1-pro-preview",
     results_base / "openclaw/gemini-3.1-pro-preview"),
    ("Qwen3VL-235B-A22B",
     results_base / "Qwen3-VL-235B-A22B-Thinking/qwen3-vl-235b-thinking-baseline-v8",
     results_base / "agents3/Qwen3-VL-235B-A22B-Thinking",
     results_base / "openclaw/qwen3-vl-235b-thinking"),
    ("Qwen3VL-32B",
     results_base / "Qwen3-VL-32B-Thinking/qwen3-vl-32b-thinking-baseline",
     results_base / "agents3/Qwen3-VL-32B-Thinking",
     results_base / "openclaw/qwen3-vl-32b-thinking"),
    ("Qwen3VL-8B",
     results_base / "Qwen3-VL-8B-Thinking/qwen3-vl-8b-thinking-baseline",
     results_base / "agents3/Qwen3-VL-8B-Thinking",
     results_base / "openclaw/qwen3-vl-8b-thinking"),
    ("InternVL-14B",
     results_base / "InternVL3_5-14B/internvl35-14b-baseline-v2",
     results_base / "agents3/InternVL3_5-14B",
     results_base / "openclaw/internvl35-14b"),
    ("InternVL-8B",
     results_base / "InternVL3_5-8B/internvl35-8b-baseline-v2",
     results_base / "agents3/InternVL3_5-8B",
     results_base / "openclaw/internvl35-8b"),
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


def calc_pass1(result_dir, domains):
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


if __name__ == "__main__":
    for subset_name, domains in [("w/ Skill", SKILL_DOMAINS), ("w/o Skill", NO_SKILL_DOMAINS)]:
        print(f"=== {subset_name} ===")
        for name, bl_path, s3_path, oc_path in MODELS:
            oc = calc_pass1(oc_path, domains)
            s3 = calc_pass1(s3_path, domains)
            bl = calc_pass1(bl_path, domains)
            d_s3 = s3 - oc
            d_bl = bl - oc
            print(f"& {name:24s} & {oc:5.1f} & ${s3:5.1f}_{{\\,{d_s3:+.1f}}}$ & ${bl:5.1f}_{{\\,{d_bl:+.1f}}}$ \\\\")
        print()
