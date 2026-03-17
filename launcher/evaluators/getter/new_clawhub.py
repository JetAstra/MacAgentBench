import os
import shlex

from controllers.env import MacOSEnv


def _read_remote_file(env: MacOSEnv, path_expr: str) -> str | None:
    env.connect_ssh()
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
    stdout, _ = env.run_command(f"python3 -c {safe_code}")
    text = stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    if text == "__MISSING__":
        return None
    return text


def _remote_path_exists(env: MacOSEnv, path_expr: str) -> bool:
    env.connect_ssh()
    remote_py = f"""
from pathlib import Path
import os

path = os.path.expandvars(os.path.expanduser({path_expr!r}))
print("1" if Path(path).exists() else "0")
"""
    safe_code = shlex.quote(remote_py.strip())
    stdout, _ = env.run_command(f"python3 -c {safe_code}")
    text = stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    return text == "1"


def new_clawhub_check_skill_installed(
    env: MacOSEnv, install_dir: str, skill_slug: str
) -> bool:
    """
    Check whether a skill is installed under <install_dir>/<skill_slug>
    and SKILL.md declares matching name.
    """
    skill_dir_expr = os.path.join(install_dir, skill_slug)
    skill_md_expr = os.path.join(skill_dir_expr, "SKILL.md")

    if not _remote_path_exists(env, skill_dir_expr):
        return False

    skill_md = _read_remote_file(env, skill_md_expr)
    if skill_md is None:
        return False

    return f"name: {skill_slug}" in skill_md


def new_clawhub_check_list_output_contains_skill(
    env: MacOSEnv, output_file: str, skill_slug: str
) -> bool:
    """
    Check whether saved `clawhub list` output exists and mentions the skill slug.
    """
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False
    return skill_slug in output_text


def new_clawhub_check_list_output_contains_all_skills(
    env: MacOSEnv, output_file: str, skill_slugs: str
) -> bool:
    """
    Check whether saved `clawhub list` output contains all expected skill slugs.
    `skill_slugs` is a comma-separated string.
    """
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False

    expected = [s.strip() for s in skill_slugs.split(",") if s.strip()]
    if not expected:
        return False

    return all(slug in output_text for slug in expected)
