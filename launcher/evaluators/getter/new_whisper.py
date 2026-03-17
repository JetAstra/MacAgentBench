import shlex
import re

from controllers.env import MacOSEnv


def _run_command(env: MacOSEnv, command: str) -> str:
    env.connect_ssh()
    stdout, _ = env.run_command(command)
    return stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()


def _read_remote_file(env: MacOSEnv, path_expr: str) -> str | None:
    remote_py = f"""
from pathlib import Path
import os

path = os.path.expandvars(os.path.expanduser({path_expr!r}))
p = Path(path)
if not p.exists():
    print("__MISSING__")
else:
    print(p.read_text(encoding="utf-8", errors="replace"))
"""
    safe_code = shlex.quote(remote_py.strip())
    output = _run_command(env, f"python3 -c {safe_code}")
    if output == "__MISSING__":
        return None
    return output


def _extract_srt_text(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.isdigit():
            continue
        if "-->" in line:
            continue
        lines.append(line)
    return "\n".join(lines)


def _normalize_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            insert_cost = curr[j - 1] + 1
            delete_cost = prev[j] + 1
            replace_cost = prev[j - 1] + (ca != cb)
            curr.append(min(insert_cost, delete_cost, replace_cost))
        prev = curr
    return prev[-1]


def _similarity_ratio(a: str, b: str) -> float:
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 1.0
    dist = _levenshtein_distance(a, b)
    return 1.0 - (dist / max_len)


def new_whisper_check_file_matches_live_output(
    env: MacOSEnv,
    output_file: str,
    expected_command: str,
    file_format: str,
    min_similarity: float,
) -> bool:
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False

    expected_text = _run_command(env, expected_command)
    if not expected_text:
        return False

    out_norm = output_text.replace("\r\n", "\n").strip()
    exp_norm = expected_text.replace("\r\n", "\n").strip()

    fmt = (file_format or "").strip().lower()
    if fmt == "srt":
        out_norm = _extract_srt_text(out_norm)
        exp_norm = _extract_srt_text(exp_norm)

    out_norm = _normalize_text(out_norm)
    exp_norm = _normalize_text(exp_norm)

    try:
        threshold = float(min_similarity)
    except Exception:
        return False

    return _similarity_ratio(out_norm, exp_norm) >= threshold
