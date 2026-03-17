import json
import shlex
import time

from controllers.env import MacOSEnv
from utils.logger import ProjectLogger


logger = ProjectLogger().get()


def _run_command(env: MacOSEnv, command: str) -> str:
    env.connect_ssh()
    stdout, _ = env.run_command(command)
    return stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()


def _run_osascript(env: MacOSEnv, script: str) -> str:
    return _run_command(env, f"osascript -e {shlex.quote(script)}")


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
    output = _run_command(env, f"python3 -c {shlex.quote(remote_py.strip())}")
    if output == "__MISSING__":
        return None
    return output


def _read_remote_json(env: MacOSEnv, script: str):
    output = _run_command(env, f"python3 -c {shlex.quote(script.strip())}")
    try:
        return json.loads(output)
    except Exception as exc:
        logger.error(f"Failed to parse remote JSON: {exc}; output={output}")
        return None


def new_peekaboo_check_app_running(env: MacOSEnv, app_name: str) -> bool:
    script = f'''
tell application "System Events"
    return (name of processes) contains "{app_name}"
end tell
'''
    return _run_osascript(env, script).strip().lower() == "true"


def new_peekaboo_check_frontmost_app(env: MacOSEnv, app_name: str) -> bool:
    script = '''
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
    return frontApp
end tell
'''
    actual = _run_osascript(env, script).strip()
    if not actual:
        logger.error("Failed to resolve frontmost app")
        return False
    return actual == app_name


def new_peekaboo_check_textedit_document_equals(
    env: MacOSEnv, expected_content: str
) -> bool:
    script = '''
tell application "TextEdit"
    if (count of documents) is 0 then
        return "__MISSING__"
    end if
    return text of document 1
end tell
'''
    actual = _run_osascript(env, script)
    if actual == "__MISSING__":
        logger.error("TextEdit document 1 not found")
        return False
    return actual.strip() == expected_content.strip()


def new_peekaboo_check_textedit_document_count_at_least(
    env: MacOSEnv, min_count: int
) -> bool:
    script = '''
tell application "TextEdit"
    return count of documents
end tell
'''
    output = _run_osascript(env, script)
    try:
        return int(output.strip()) >= int(min_count)
    except Exception as exc:
        logger.error(f"Failed to parse TextEdit document count: {exc}; output={output}")
        return False


def new_peekaboo_check_window_count_at_least(
    env: MacOSEnv, app_name: str, min_count: int
) -> bool:
    script = f'''
tell application "{app_name}"
    return count of windows
end tell
'''
    output = _run_osascript(env, script)
    try:
        return int(output.strip()) >= int(min_count)
    except Exception as exc:
        logger.error(
            f"Failed to parse window count for {app_name}: {exc}; output={output}"
        )
        return False


def new_peekaboo_check_clipboard_text_equals(
    env: MacOSEnv, expected_text: str
) -> bool:
    actual = _run_command(env, "pbpaste")
    return actual.strip() == expected_text.strip()


def new_peekaboo_check_clipboard_empty(env: MacOSEnv) -> bool:
    actual = _run_command(env, "pbpaste")
    return actual == ""


def new_peekaboo_check_file_equals(
    env: MacOSEnv, output_file: str, expected_content: str
) -> bool:
    actual = _read_remote_file(env, output_file)
    if actual is None:
        logger.error(f"Output file missing: {output_file}")
        return False
    return actual.strip() == expected_content.strip()


def new_peekaboo_check_window_bounds(
    env: MacOSEnv,
    app_name: str,
    expected_x: int,
    expected_y: int,
    expected_width: int,
    expected_height: int,
    tolerance: int = 20,
) -> bool:
    script = f'''
tell application "{app_name}"
    if (count of windows) is 0 then
        return "__MISSING__"
    end if
    set b to bounds of front window
    return (item 1 of b as string) & "," & (item 2 of b as string) & "," & (item 3 of b as string) & "," & (item 4 of b as string)
end tell
'''
    output = _run_osascript(env, script)
    if output == "__MISSING__":
        logger.error(f"No front window for app: {app_name}")
        return False

    try:
        x1, y1, x2, y2 = [int(part.strip()) for part in output.split(",")]
    except Exception as exc:
        logger.error(f"Failed to parse window bounds for {app_name}: {exc}; output={output}")
        return False

    actual_width = x2 - x1
    actual_height = y2 - y1

    return (
        abs(x1 - int(expected_x)) <= int(tolerance)
        and abs(y1 - int(expected_y)) <= int(tolerance)
        and abs(actual_width - int(expected_width)) <= int(tolerance)
        and abs(actual_height - int(expected_height)) <= int(tolerance)
    )


def new_peekaboo_check_image_exists_nonempty(
    env: MacOSEnv, output_file: str, min_size_bytes: int = 1024
) -> bool:
    remote_py = f"""
from pathlib import Path
import json
import os

path = os.path.expandvars(os.path.expanduser({output_file!r}))
p = Path(path)
if not p.exists():
    print(json.dumps({{"exists": False}}))
else:
    print(json.dumps({{"exists": True, "size": p.stat().st_size, "suffix": p.suffix.lower()}}))
"""
    payload = _read_remote_json(env, remote_py)
    if not payload or not payload.get("exists"):
        logger.error(f"Image output missing: {output_file}")
        return False
    if payload.get("suffix") != ".png":
        logger.error(f"Unexpected image suffix for {output_file}: {payload.get('suffix')}")
        return False
    return int(payload.get("size", 0)) >= int(min_size_bytes)


def new_peekaboo_check_safari_front_url(env: MacOSEnv, expected_url: str) -> bool:
    script = '''
tell application "Safari"
    if (count of windows) is 0 then
        return "__MISSING__"
    end if
    return URL of front document
end tell
'''
    expected = expected_url.strip()
    last_actual = ""
    for _ in range(8):
        actual = _run_osascript(env, script)
        if actual == "__MISSING__":
            logger.error("Safari has no front document")
            time.sleep(1)
            continue
        last_actual = actual.strip()
        if last_actual == expected:
            return True
        time.sleep(1)

    logger.error(f"Safari front URL mismatch: expected={expected!r}, actual={last_actual!r}")
    return False
