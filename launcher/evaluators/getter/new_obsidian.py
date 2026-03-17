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
    output = _run_command(env, f"python3 -c {safe_code}")
    if output == "__MISSING__":
        logger.error(f"Output file not found: {output_file}")
        return None
    return output


def _read_remote_json(env: MacOSEnv, script: str):
    safe_code = shlex.quote(script.strip())
    output = _run_command(env, f"python3 -c {safe_code}")
    try:
        return json.loads(output)
    except Exception as exc:
        logger.error(f"Failed to parse JSON from remote helper: {exc}; output={output}")
        return None


def new_obsidian_check_file_contains_all_note_paths_in_folder(
    env: MacOSEnv, vault_path: str, folder_path: str, output_file: str
) -> bool:
    remote_py = f"""
from pathlib import Path
import os
import json

vault = Path(os.path.expandvars(os.path.expanduser({vault_path!r})))
folder = vault / {folder_path!r}
if not folder.exists() or not folder.is_dir():
    print(json.dumps({{"exists": False, "paths": []}}))
else:
    paths = sorted(
        str(path.relative_to(vault))
        for path in folder.rglob("*.md")
        if path.is_file()
    )
    print(json.dumps({{"exists": True, "paths": paths}}))
"""
    payload = _read_remote_json(env, remote_py)
    if not payload or not payload.get("exists"):
        logger.error(f"Folder not found in vault: {folder_path}")
        return False

    expected_paths = payload.get("paths", [])
    if not expected_paths:
        logger.error(f"No markdown notes found in folder: {folder_path}")
        return False

    file_output = _read_remote_file(env, output_file)
    if file_output is None:
        return False

    lines = {line.strip() for line in file_output.splitlines() if line.strip()}
    return all(path in lines for path in expected_paths)


def new_obsidian_check_file_contains_all_search_matches(
    env: MacOSEnv, vault_path: str, query: str, output_file: str
) -> bool:
    remote_py = f"""
from pathlib import Path
import os
import json

vault = Path(os.path.expandvars(os.path.expanduser({vault_path!r})))
query = {query!r}
matches = []
for path in sorted(vault.rglob("*.md")):
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    if query in content:
        matches.append(str(path.relative_to(vault)))
print(json.dumps(matches))
"""
    expected_paths = _read_remote_json(env, remote_py)
    if expected_paths is None:
        return False
    if not expected_paths:
        logger.error(f"No search matches found for query: {query}")
        return False

    file_output = _read_remote_file(env, output_file)
    if file_output is None:
        return False

    lines = {line.strip() for line in file_output.splitlines() if line.strip()}
    return all(path in lines for path in expected_paths)


def new_obsidian_check_file_equals_note_content(
    env: MacOSEnv, vault_path: str, note_path: str, output_file: str
) -> bool:
    remote_py = f"""
from pathlib import Path
import os

vault = Path(os.path.expandvars(os.path.expanduser({vault_path!r})))
path = vault / {note_path!r}
if not path.suffix:
    path = path.with_suffix(".md")
if not path.exists():
    print("__MISSING__")
else:
    print(path.read_text(encoding="utf-8", errors="replace"))
"""
    safe_code = shlex.quote(remote_py.strip())
    expected = _run_command(env, f"python3 -c {safe_code}")
    if expected == "__MISSING__":
        logger.error(f"Note not found in vault: {note_path}")
        return False

    actual = _read_remote_file(env, output_file)
    if actual is None:
        return False
    return actual.strip() == expected.strip()


def new_obsidian_check_note_exists_with_exact_content(
    env: MacOSEnv, vault_path: str, note_path: str, expected_content: str
) -> bool:
    remote_py = f"""
from pathlib import Path
import os

vault = Path(os.path.expandvars(os.path.expanduser({vault_path!r})))
path = vault / {note_path!r}
if not path.suffix:
    path = path.with_suffix(".md")
if not path.exists():
    print("__MISSING__")
else:
    print(path.read_text(encoding="utf-8", errors="replace"))
"""
    safe_code = shlex.quote(remote_py.strip())
    actual = _run_command(env, f"python3 -c {safe_code}")
    if actual == "__MISSING__":
        logger.error(f"Expected note missing: {note_path}")
        return False
    return actual.strip() == expected_content.strip()


def new_obsidian_check_note_contains_text(
    env: MacOSEnv, vault_path: str, note_path: str, expected_text: str
) -> bool:
    remote_py = f"""
from pathlib import Path
import os

vault = Path(os.path.expandvars(os.path.expanduser({vault_path!r})))
path = vault / {note_path!r}
if not path.suffix:
    path = path.with_suffix(".md")
if not path.exists():
    print("__MISSING__")
else:
    print(path.read_text(encoding="utf-8", errors="replace"))
"""
    safe_code = shlex.quote(remote_py.strip())
    actual = _run_command(env, f"python3 -c {safe_code}")
    if actual == "__MISSING__":
        logger.error(f"Expected note missing: {note_path}")
        return False
    return expected_text in actual


def new_obsidian_check_note_contains_all_texts(
    env: MacOSEnv, vault_path: str, note_path: str, expected_texts: list[str]
) -> bool:
    remote_py = f"""
from pathlib import Path
import os

vault = Path(os.path.expandvars(os.path.expanduser({vault_path!r})))
path = vault / {note_path!r}
if not path.suffix:
    path = path.with_suffix(".md")
if not path.exists():
    print("__MISSING__")
else:
    print(path.read_text(encoding="utf-8", errors="replace"))
"""
    safe_code = shlex.quote(remote_py.strip())
    actual = _run_command(env, f"python3 -c {safe_code}")
    if actual == "__MISSING__":
        logger.error(f"Expected note missing: {note_path}")
        return False
    return all(text in actual for text in expected_texts)


def new_obsidian_check_note_moved(
    env: MacOSEnv,
    vault_path: str,
    source_note_path: str,
    target_note_path: str,
    expected_text: str = "",
) -> bool:
    remote_py = f"""
from pathlib import Path
import os
import json

vault = Path(os.path.expandvars(os.path.expanduser({vault_path!r})))
source = vault / {source_note_path!r}
target = vault / {target_note_path!r}
if not source.suffix:
    source = source.with_suffix(".md")
if not target.suffix:
    target = target.with_suffix(".md")

payload = {{
    "source_exists": source.exists(),
    "target_exists": target.exists(),
    "target_content": "",
}}
if target.exists():
    payload["target_content"] = target.read_text(encoding="utf-8", errors="replace")
print(json.dumps(payload))
"""
    payload = _read_remote_json(env, remote_py)
    if payload is None:
        return False

    if payload.get("source_exists"):
        logger.error(f"Source note still exists: {source_note_path}")
        return False
    if not payload.get("target_exists"):
        logger.error(f"Target note missing: {target_note_path}")
        return False
    if expected_text and expected_text not in payload.get("target_content", ""):
        logger.error(f"Moved note content missing expected text: {expected_text}")
        return False
    return True


def new_obsidian_check_links_updated_after_move(
    env: MacOSEnv,
    vault_path: str,
    referrer_note_path: str,
    old_link_text: str,
    new_link_text: str,
) -> bool:
    remote_py = f"""
from pathlib import Path
import os

vault = Path(os.path.expandvars(os.path.expanduser({vault_path!r})))
path = vault / {referrer_note_path!r}
if not path.suffix:
    path = path.with_suffix(".md")
if not path.exists():
    print("__MISSING__")
else:
    print(path.read_text(encoding="utf-8", errors="replace"))
"""
    safe_code = shlex.quote(remote_py.strip())
    actual = _run_command(env, f"python3 -c {safe_code}")
    if actual == "__MISSING__":
        logger.error(f"Referrer note missing: {referrer_note_path}")
        return False
    if old_link_text in actual:
        logger.error(f"Old link text still present in {referrer_note_path}: {old_link_text}")
        return False
    return new_link_text in actual


def new_obsidian_check_note_absent(
    env: MacOSEnv, vault_path: str, note_path: str
) -> bool:
    remote_py = f"""
from pathlib import Path
import os

vault = Path(os.path.expandvars(os.path.expanduser({vault_path!r})))
path = vault / {note_path!r}
if not path.suffix:
    path = path.with_suffix(".md")
print("__EXISTS__" if path.exists() else "__ABSENT__")
"""
    safe_code = shlex.quote(remote_py.strip())
    output = _run_command(env, f"python3 -c {safe_code}")
    return output == "__ABSENT__"


def new_obsidian_check_frontmatter_value(
    env: MacOSEnv, vault_path: str, note_path: str, key: str, expected_value: str
) -> bool:
    remote_py = f"""
from pathlib import Path
import os
import json

vault = Path(os.path.expandvars(os.path.expanduser({vault_path!r})))
path = vault / {note_path!r}
if not path.suffix:
    path = path.with_suffix(".md")
if not path.exists():
    print(json.dumps({{"exists": False, "value": None}}))
else:
    text = path.read_text(encoding="utf-8", errors="replace")
    value = None
    if text.startswith("---\\n"):
        parts = text.split("---\\n", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                if k.strip() == {key!r}:
                    value = v.strip().strip('"').strip("'")
                    break
    print(json.dumps({{"exists": True, "value": value}}))
"""
    payload = _read_remote_json(env, remote_py)
    if not payload or not payload.get("exists"):
        logger.error(f"Note missing while checking frontmatter: {note_path}")
        return False
    return str(payload.get("value")) == str(expected_value)
