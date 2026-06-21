import shlex
import re

from controllers.env import MacOSEnv
from utils.logger import ProjectLogger


logger = ProjectLogger().get()


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
        '{full_name: .full_name, description: (.description // ""), license_name: (.license.name // "NO LICENSE"), license_spdx: (.license.spdx_id // ""), homepage_url: (.homepage // ""), main_language: (.language // "")}'
    )
    cmd = f"gh api {endpoint} --jq {jq_expr}"
    expected_json = _run_command(env, cmd)
    if not expected_json:
        return False

    try:
        import json

        expected = json.loads(expected_json)
    except Exception:
        return False

    required_values = [
        expected.get("full_name", "").strip(),
        expected.get("description", "").strip(),
        expected.get("homepage_url", "").strip(),
        expected.get("main_language", "").strip(),
    ]
    non_empty_values = [v for v in required_values if v]
    if not non_empty_values:
        return False

    license_candidates = [
        expected.get("license_name", "").strip(),
        expected.get("license_spdx", "").strip(),
    ]
    license_candidates = [v for v in license_candidates if v]
    if not license_candidates:
        license_candidates = ["NO LICENSE"]

    return all(v in output_text for v in non_empty_values) and any(
        license in output_text for license in license_candidates
    )


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
        logger.error(
            f"[new_github_top_issue] output file missing or unreadable: {output_file}"
        )
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
        logger.info(
            f"[new_github_top_issue] no live open issue found for repo={repo}; "
            f"nonempty_output_lines={len(_nonempty_unique_lines(output_text))}"
        )
        return len(_nonempty_unique_lines(output_text)) == 0

    expected_values = [_normalize_live_line(v) for v in expected_tsv.split("\t")]
    if len(expected_values) != 5:
        logger.error(
            f"[new_github_top_issue] unexpected expected_tsv shape for repo={repo}: "
            f"{expected_tsv!r}"
        )
        return False

    non_empty_values = [v for v in expected_values if v]
    if not non_empty_values:
        logger.error(
            f"[new_github_top_issue] all expected values empty for repo={repo}: "
            f"{expected_tsv!r}"
        )
        return False

    normalized_output = _normalize_live_line(output_text)
    missing_values = [v for v in non_empty_values if v not in normalized_output]

    logger.info(
        f"[new_github_top_issue] repo={repo} output_file={output_file} "
        f"expected_values={expected_values!r}"
    )
    logger.info(
        f"[new_github_top_issue] normalized_output={normalized_output!r}"
    )

    if missing_values:
        logger.warning(
            f"[new_github_top_issue] missing_values={missing_values!r} "
            f"for repo={repo}"
        )
        return False

    logger.info(f"[new_github_top_issue] all expected values matched for repo={repo}")
    return True
