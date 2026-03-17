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


def _normalize_live_line(line: str) -> str:
    normalized = re.sub(r"\s+", " ", line.strip())
    normalized = re.sub(r",\s+", ",", normalized)
    return normalized


def new_github_check_repo_info_matches(
    env: MacOSEnv, output_file: str, repo: str
) -> bool:
    """
    Validate saved text output by checking that all expected field values
    are present in the file content.
    """
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False

    endpoint = shlex.quote(f"repos/{repo}")
    jq_expr = shlex.quote(
        '[.full_name, (.description // ""), (.license.name // "NO LICENSE"), (.homepage // ""), (.language // "")] | @tsv'
    )
    cmd = f"gh api {endpoint} --jq {jq_expr}"
    expected_tsv = _run_command(env, cmd)
    if not expected_tsv:
        return False

    expected_values = [v.strip() for v in expected_tsv.split("\t")]
    if len(expected_values) != 5:
        return False

    # Only enforce non-empty expected values.
    non_empty_values = [v for v in expected_values if v]
    if not non_empty_values:
        return False

    return all(v in output_text for v in non_empty_values)


def new_github_check_file_contains_live_lines(
    env: MacOSEnv, output_file: str, expected_command: str, min_overlap: int
) -> bool:
    """
    Check that the saved output file overlaps with current live command output.
    """
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False

    try:
        required = int(min_overlap)
    except Exception:
        return False
    if required < 1:
        return False

    user_lines = [_normalize_live_line(line) for line in _nonempty_unique_lines(output_text)]

    live_text = _run_command(env, expected_command)
    live_lines = [_normalize_live_line(line) for line in _nonempty_unique_lines(live_text)]
    # If current live query has no results, accept empty user output.
    if not live_lines:
        return len(user_lines) == 0

    if len(user_lines) < required:
        return False

    overlap = len(set(user_lines) & set(live_lines))
    return overlap >= required


def new_github_check_top_issue_values_present(
    env: MacOSEnv, output_file: str, repo: str
) -> bool:
    """
    Check that output text contains key values of the top open issue
    returned by `gh issue list --limit 1`.
    """
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False

    endpoint = shlex.quote(repo)
    jq_expr = shlex.quote(
        '.[0] | [.number, .title, .state, .author.login, (([.labels[].name] | if length == 0 then "none" else join(",") end))] | @tsv'
    )
    cmd = (
        f"gh issue list --repo {endpoint} --state open --limit 1 "
        f"--json number,title,state,author,labels --jq {jq_expr}"
    )
    expected_tsv = _run_command(env, cmd)
    if not expected_tsv:
        # No open issues now: expect empty output file.
        return len(_nonempty_unique_lines(output_text)) == 0

    expected_values = [v.strip() for v in expected_tsv.split("\t")]
    if len(expected_values) != 5:
        return False

    non_empty_values = [v for v in expected_values if v]
    if not non_empty_values:
        return False

    return all(v in output_text for v in non_empty_values)
