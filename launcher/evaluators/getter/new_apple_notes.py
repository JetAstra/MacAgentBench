import shlex

from controllers.env import MacOSEnv
from utils.logger import ProjectLogger


logger = ProjectLogger().get()


def _parse_titles_from_memo_output(memo_output: str) -> list[str]:
    titles = []
    for line in memo_output.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "All your notes:":
            continue
        if stripped.startswith("Fetching notes"):
            continue
        if stripped.startswith("No notes found"):
            continue
        if ". " not in stripped:
            continue

        prefix, rest = stripped.split(". ", 1)
        if not prefix.isdigit():
            continue

        if " - " in rest:
            _, title = rest.split(" - ", 1)
        else:
            title = rest

        title = title.strip()
        if title:
            titles.append(title)
    return titles


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
    stdout, _ = env.run_command(f"python3 -c {safe_code}")
    file_output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )

    if file_output == "__MISSING__":
        logger.error(f"Output file not found: {output_file}")
        return None
    return file_output


def new_apple_notes_check_file_contains_all_note_titles(
    env: MacOSEnv, output_file: str = "$HOME/Desktop/test.md"
) -> bool:
    """
    Use `memo notes` to read current note titles, then verify a target file contains
    every title at least once.

    :param env: MacOSEnv instance
    :param output_file: Output file path, supports $HOME expansion
    :return: True if the file exists and contains all current note titles
    """
    env.connect_ssh()

    stdout, _ = env.run_command("memo notes")
    memo_output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )

    titles = _parse_titles_from_memo_output(memo_output)
    if not titles:
        logger.error(f"No note titles parsed from memo output: {memo_output}")
        return False

    file_output = _read_remote_file(env, output_file)
    if file_output is None:
        return False

    return all(title in file_output for title in titles)


def new_apple_notes_check_file_contains_all_titles_in_folder(
    env: MacOSEnv, folder_name: str, output_file: str
) -> bool:
    """
    Use `memo notes -f <folder>` to read note titles in one folder, then verify a
    target file contains every title at least once.

    :param env: MacOSEnv instance
    :param folder_name: Notes folder name to inspect
    :param output_file: Output file path, supports $HOME expansion
    :return: True if the file exists and contains all note titles in the folder
    """
    env.connect_ssh()

    stdout, _ = env.run_command(f"memo notes -f {shlex.quote(folder_name)}")
    memo_output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )

    if "No notes found." in memo_output:
        logger.error(f"No notes found in folder: {folder_name}")
        return False

    titles = _parse_titles_from_memo_output(memo_output)
    if not titles:
        logger.error(
            f"No note titles parsed for folder {folder_name}: {memo_output}"
        )
        return False

    file_output = _read_remote_file(env, output_file)
    if file_output is None:
        return False

    return all(title in file_output for title in titles)


def new_apple_notes_check_file_contains_all_search_result_titles(
    env: MacOSEnv, query: str, output_file: str
) -> bool:
    """
    Use `memo notes -s <query>` to read note titles in search results, then verify
    a target file contains every matching title at least once.

    :param env: MacOSEnv instance
    :param query: Search query passed to memo
    :param output_file: Output file path, supports $HOME expansion
    :return: True if the file exists and contains all matching note titles
    """
    env.connect_ssh()

    stdout, _ = env.run_command(f"memo notes -s {shlex.quote(query)}")
    memo_output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )

    if "No notes found." in memo_output:
        logger.error(f"No notes found for search query: {query}")
        return False

    titles = _parse_titles_from_memo_output(memo_output)
    if not titles:
        logger.error(
            f"No note titles parsed for search query {query}: {memo_output}"
        )
        return False

    file_output = _read_remote_file(env, output_file)
    if file_output is None:
        return False

    return all(title in file_output for title in titles)


def new_apple_notes_check_note_exists_with_content(
    env: MacOSEnv, note_title: str, note_content: str
) -> bool:
    """
    Verify that at least one note with the requested title exists and that its
    displayed content via `memo` contains the expected content.

    :param env: MacOSEnv instance
    :param note_title: Exact note title to match
    :param note_content: Expected plaintext snippet
    :return: True if a matching note exists and contains the expected content
    """
    env.connect_ssh()

    stdout, _ = env.run_command("memo notes")
    memo_output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )

    if "No notes found." in memo_output:
        logger.error("No notes found while checking note content.")
        return False

    matching_indexes = []
    for line in memo_output.splitlines():
        stripped = line.strip()
        if ". " not in stripped:
            continue
        prefix, rest = stripped.split(". ", 1)
        if not prefix.isdigit():
            continue

        if " - " in rest:
            _, parsed_title = rest.split(" - ", 1)
        else:
            parsed_title = rest

        if parsed_title.strip() == note_title:
            matching_indexes.append(int(prefix))

    if not matching_indexes:
        return False

    for note_index in matching_indexes:
        stdout, _ = env.run_command(f"memo notes -v {note_index}")
        note_view = (
            stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
        )
        if note_content in note_view:
            return True

    return False


def new_apple_notes_check_note_exists_in_folder(
    env: MacOSEnv, note_title: str, folder_name: str
) -> bool:
    """
    Verify that a note with the requested title appears in the specified folder
    when listed via `memo`.

    :param env: MacOSEnv instance
    :param note_title: Exact note title to match
    :param folder_name: Folder name expected to contain the note
    :return: True if the note is listed in that folder
    """
    env.connect_ssh()

    stdout, _ = env.run_command(f"memo notes -f {shlex.quote(folder_name)}")
    memo_output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )

    if "No notes found." in memo_output or "does not exists" in memo_output:
        logger.error(f"Folder not available or empty while checking {folder_name}: {memo_output}")
        return False

    titles = _parse_titles_from_memo_output(memo_output)
    return note_title in titles


def new_apple_notes_check_note_absent(
    env: MacOSEnv, note_title: str
) -> bool:
    """
    Verify that no note with the requested title appears in the global `memo notes`
    listing.

    :param env: MacOSEnv instance
    :param note_title: Exact note title to check
    :return: True if the title is absent from the notes list
    """
    env.connect_ssh()

    stdout, _ = env.run_command("memo notes")
    memo_output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )

    if "No notes found." in memo_output:
        return True

    titles = _parse_titles_from_memo_output(memo_output)
    return note_title not in titles


def new_apple_notes_check_export_contains_note_title(
    env: MacOSEnv, export_dir: str, note_title: str
) -> bool:
    """
    Verify that the export directory exists and contains at least one HTML file
    whose content includes the requested note title.

    :param env: MacOSEnv instance
    :param export_dir: Export directory path, supports $HOME expansion
    :param note_title: Note title expected to appear in exported HTML
    :return: True if a matching exported HTML file is found
    """
    env.connect_ssh()

    remote_py = f"""
from pathlib import Path
import os

path = Path(os.path.expandvars(os.path.expanduser({export_dir!r})))
if not path.exists() or not path.is_dir():
    print("__MISSING__")
else:
    matched = False
    for html_file in path.rglob("*.html"):
        try:
            content = html_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if {note_title!r} in content:
            matched = True
            break
    print("__MATCH__" if matched else "__NO_MATCH__")
"""
    safe_code = shlex.quote(remote_py.strip())
    stdout, _ = env.run_command(f"python3 -c {safe_code}")
    output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )

    if output == "__MATCH__":
        return True
    if output == "__MISSING__":
        logger.error(f"Export directory missing: {export_dir}")
        return False
    if output == "__NO_MATCH__":
        logger.error(f"No exported HTML contained title: {note_title}")
        return False

    logger.error(f"Unexpected export check output: {output}")
    return False
