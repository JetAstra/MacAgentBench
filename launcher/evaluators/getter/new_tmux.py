import json
import shlex

from controllers.env import MacOSEnv
from utils.logger import ProjectLogger


logger = ProjectLogger().get()


def _run_command(env: MacOSEnv, command: str) -> str:
    env.connect_ssh()
    stdout, _ = env.run_command(command)
    return stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()


def _read_remote_file(env: MacOSEnv, output_file: str) -> str | None:
    remote_py = f"""
from pathlib import Path
import os

path = os.path.expandvars(os.path.expanduser({output_file!r}))
file_path = Path(path)
if not file_path.exists():
    print("__MISSING__")
else:
    print(file_path.read_text(encoding="utf-8", errors="replace"))
"""
    safe_code = shlex.quote(remote_py.strip())
    content = _run_command(env, f"python3 -c {safe_code}")
    if content == "__MISSING__":
        logger.error(f"Output file not found: {output_file}")
        return None
    return content


def _read_remote_json(env: MacOSEnv, output_file: str):
    content = _read_remote_file(env, output_file)
    if content is None:
        return None
    try:
        return json.loads(content)
    except Exception as exc:
        logger.error(f"Failed to parse JSON from {output_file}: {exc}")
        return None


def new_tmux_check_file_contains_text(
    env: MacOSEnv, output_file: str, expected_text: str
) -> bool:
    content = _read_remote_file(env, output_file)
    if content is None:
        return False
    return expected_text in content


def new_tmux_check_json_key_value(
    env: MacOSEnv, output_file: str, key: str, expected_value
) -> bool:
    payload = _read_remote_json(env, output_file)
    if not isinstance(payload, dict):
        return False
    return payload.get(key) == expected_value


def new_tmux_check_json_key_contains_text(
    env: MacOSEnv, output_file: str, key: str, expected_text: str
) -> bool:
    payload = _read_remote_json(env, output_file)
    if not isinstance(payload, dict):
        return False
    value = payload.get(key)
    return isinstance(value, str) and expected_text in value


def new_tmux_check_json_list_exact(
    env: MacOSEnv, output_file: str, key: str, expected_list: list[str]
) -> bool:
    payload = _read_remote_json(env, output_file)
    if not isinstance(payload, dict):
        return False
    actual = payload.get(key)
    return isinstance(actual, list) and actual == expected_list


def new_tmux_check_pane_contains_text(
    env: MacOSEnv, target: str, expected_text: str
) -> bool:
    out = _run_command(env, f"tmux capture-pane -t {shlex.quote(target)} -p")
    return expected_text in out
