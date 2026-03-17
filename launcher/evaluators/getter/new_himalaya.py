import shlex
import json

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


def _extract_kv_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = " ".join(key.strip().lower().split())
        value = " ".join(value.strip().lower().split())
        if key:
            pairs.append((key, value))
    return pairs


def new_himalaya_check_single_kv_equals(
    env: MacOSEnv, output_file: str, expected_command: str
) -> bool:
    """
    Semi-strict key:value check:
    - expected output must contain at least one key:value line
    - user output can be multi-line
    - pass if user has one key:value pair matching expected key and value
      (case/space-insensitive)
    """
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False

    expected_text = _run_command(env, expected_command)
    if not expected_text:
        return False

    expected_pairs = _extract_kv_pairs(expected_text)
    if not expected_pairs:
        return False
    target = expected_pairs[0]

    user_pairs = _extract_kv_pairs(output_text)
    if not user_pairs:
        return False

    return target in user_pairs


def _nonempty_unique_lines(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in text.splitlines():
        v = line.strip()
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def new_himalaya_check_file_contains_live_lines(
    env: MacOSEnv, output_file: str, expected_command: str, min_overlap: int = 1
) -> bool:
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False

    try:
        required = int(min_overlap)
    except Exception:
        return False
    if required < 1:
        return False

    user_lines = _nonempty_unique_lines(output_text)
    live_text = _run_command(env, expected_command)
    live_lines = _nonempty_unique_lines(live_text)

    if not live_lines:
        return len(user_lines) == 0
    if len(user_lines) < required:
        return False
    return len(set(user_lines) & set(live_lines)) >= required


def new_himalaya_check_file_equals_live_output(
    env: MacOSEnv, output_file: str, expected_command: str
) -> bool:
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False
    expected_text = _run_command(env, expected_command)
    # Normalize line endings but preserve all content otherwise.
    out_norm = output_text.replace("\r\n", "\n").strip()
    exp_norm = expected_text.replace("\r\n", "\n").strip()
    return out_norm == exp_norm


def new_himalaya_check_json_equals_live(
    env: MacOSEnv, output_file: str, expected_command: str
) -> bool:
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False
    expected_text = _run_command(env, expected_command)
    if not expected_text:
        return False
    try:
        output_json = json.loads(output_text)
        expected_json = json.loads(expected_text)
    except Exception:
        return False
    # Normalize emails list order when present.
    def _normalize(value):
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if k == "emails" and isinstance(v, list):
                    norm_items = []
                    for item in v:
                        if isinstance(item, dict):
                            norm_item = {
                                kk: (
                                    " ".join(str(vv).strip().split())
                                    if isinstance(vv, str)
                                    else vv
                                )
                                for kk, vv in item.items()
                            }
                            norm_items.append(norm_item)
                        else:
                            norm_items.append(item)
                    norm_items.sort(
                        key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False)
                    )
                    out[k] = norm_items
                else:
                    out[k] = _normalize(v)
            return out
        if isinstance(value, list):
            return [_normalize(v) for v in value]
        return value

    return _normalize(output_json) == _normalize(expected_json)


def new_himalaya_check_keyword_moved(
    env: MacOSEnv, source_folder: str, target_folder: str, keyword: str
) -> bool:
    """
    Validate move effect:
    - source has no subject matching keyword
    - target has at least one subject matching keyword
    """
    src_cmd = (
        f"himalaya envelope list --folder {shlex.quote(source_folder)} -o json"
    )
    dst_cmd = (
        f"himalaya envelope list --folder {shlex.quote(target_folder)} -o json"
    )
    src_text = _run_command(env, src_cmd)
    dst_text = _run_command(env, dst_cmd)
    try:
        src_rows = json.loads(src_text) if src_text else []
        dst_rows = json.loads(dst_text) if dst_text else []
    except Exception:
        return False

    kw = keyword.lower()
    src_has = any(kw in (row.get("subject") or "").lower() for row in src_rows)
    dst_has = any(kw in (row.get("subject") or "").lower() for row in dst_rows)
    return (not src_has) and dst_has


def _load_json_file(env: MacOSEnv, path_expr: str):
    text = _read_remote_file(env, path_expr)
    if text is None:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _count_keyword_in_folder(env: MacOSEnv, folder: str, keyword: str) -> int:
    cmd = (
        "all=$(for p in {1..50}; do "
        f"out=$(himalaya envelope list --folder {shlex.quote(folder)} --page \"$p\" "
        "--page-size 100 -o json 2>/dev/null || true); "
        "[ -z \"$out\" ] && break; [ \"$out\" = \"[]\" ] && break; echo \"$out\"; "
        "done); "
        "if [ -z \"$all\" ]; then echo 0; "
        "else printf '%s\\n' \"$all\" | jq -s "
        f"'{json.dumps(keyword.lower())} as $kw | add | map(select(((.subject // \"\") | ascii_downcase) | contains($kw))) | length'; "
        "fi"
    )
    out = _run_command(env, cmd)
    try:
        return int(out.strip())
    except Exception:
        return 0


def new_himalaya_check_keyword_moved_with_baseline(
    env: MacOSEnv,
    source_folder: str,
    target_folder: str,
    keyword: str,
    baseline_file: str,
) -> bool:
    """
    Validate move behavior against baseline snapshot:
    - source keyword count decreases and ends at 0
    - target keyword count increases
    """
    baseline = _load_json_file(env, baseline_file)
    if not isinstance(baseline, dict):
        return False
    try:
        src_before = int(baseline.get("source_count", 0))
        dst_before = int(baseline.get("target_count", 0))
    except Exception:
        return False

    src_after = _count_keyword_in_folder(env, source_folder, keyword)
    dst_after = _count_keyword_in_folder(env, target_folder, keyword)

    moved_from_source = src_after < src_before
    moved_to_target = dst_after > dst_before
    source_cleared = src_after == 0
    return moved_from_source and moved_to_target and source_cleared


def new_himalaya_check_keyword_moved_after(
    env: MacOSEnv, source_folder: str, target_folder: str, keyword: str
) -> bool:
    """
    Post-action validation without baseline (compatible with evaluation flow):
    - source has no keyword-matching subject
    - target has at least one keyword-matching subject
    """
    src_after = _count_keyword_in_folder(env, source_folder, keyword)
    dst_after = _count_keyword_in_folder(env, target_folder, keyword)
    return src_after == 0 and dst_after > 0
