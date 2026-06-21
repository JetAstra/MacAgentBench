import paramiko
from controllers.env import MacOSEnv
from utils.logger import ProjectLogger
from pathlib import Path
import json
import time
from bs4 import BeautifulSoup
import shlex
import textwrap
import plistlib

script_dir = Path(__file__).resolve().parent.parent

logger = ProjectLogger(log_dir=script_dir / "logs")


def finder_check_file_exists(env, file_path: str) -> bool:
    """
    Check if a file exists at the given path on macOS via SSH.

    :param env: MacOSEnv instance
    :param file_path: Absolute file path to check
    :return: True if file exists, False otherwise
    """
    env.connect_ssh()
    cmd = f'test -f "{file_path}" && echo "Exists" || echo "Not found"'
    stdout, stderr = env.run_command(cmd)
    output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )
    return output == "Exists"


def finder_check_file_has_tag_xattr(env, file_path: str) -> bool:
    """
    Check whether a file has the ``_kMDItemUserTags`` extended attribute,
    regardless of whether its content is a valid Finder tag.

    Returns True if the agent attempted ANY tag operation on the file
    (``xattr -w``, ``osxmetadata``, AppleScript NSURL, etc.), even if
    the tag format was wrong and ``finder_check_file_tag`` returns False.

    Use this as a "did the agent at least TRY to tag this file?"
    checkpoint, giving partial credit for the attempt.

    Args:
        env (MacOSEnv): macOS automation environment
        file_path (str): Path to the file to check

    Returns:
        bool: True if the ``_kMDItemUserTags`` xattr exists on the file.
    """
    env.connect_ssh()

    file_path = file_path.replace("~", "$HOME")
    cmd = f'xattr -p com.apple.metadata:_kMDItemUserTags "{file_path}" >/dev/null 2>&1 && echo YES || echo NO'
    stdout, _ = env.run_command(cmd)
    output = (
        stdout.read().decode().strip()
        if hasattr(stdout, "read")
        else stdout.strip()
    )
    result = output == "YES"
    logger.info(
        f"[finder_check_file_has_tag_xattr] {file_path}: {result}"
    )
    return result


def finder_check_file_exists_normalized(env, file_path: str) -> bool:
    """
    Accent-insensitive file existence check.

    Lists files in the parent directory of *file_path*, strips Unicode
    accents from both the expected filename and each actual filename,
    then checks for a match. This handles the common case where the
    agent creates ``Schröder.txt`` (correct spelling) but the task
    expected ``Schroder.txt`` (ASCII transliteration), or vice versa.

    Falls back to exact path check if the parent directory doesn't exist.

    Args:
        env (MacOSEnv): macOS automation environment
        file_path (str): Expected file path (may or may not have accents)

    Returns:
        bool: True if a matching file (accent-insensitive) exists.
    """
    from evaluators.metrics.common import strip_accents

    env.connect_ssh()

    file_path = file_path.replace("~", "$HOME")
    # Get parent dir and expected filename
    parent_cmd = f'dirname "{file_path}"'
    stdout, _ = env.run_command(parent_cmd)
    parent = (stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip())

    basename_cmd = f'basename "{file_path}"'
    stdout, _ = env.run_command(basename_cmd)
    expected_name = (stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip())

    # List files in parent directory
    ls_cmd = f'ls -1 "{parent}" 2>/dev/null'
    stdout, _ = env.run_command(ls_cmd)
    raw = (stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip())

    if not raw:
        logger.warning(f"[finder_check_file_exists_normalized] parent dir empty or not found: {parent}")
        return False

    actual_files = raw.splitlines()
    expected_norm = strip_accents(expected_name)

    for actual in actual_files:
        if strip_accents(actual.strip()) == expected_norm:
            logger.info(
                f"[finder_check_file_exists_normalized] matched: "
                f"expected={expected_name!r} actual={actual.strip()!r} (normalized={expected_norm!r})"
            )
            return True

    logger.info(
        f"[finder_check_file_exists_normalized] no match for {expected_name!r} "
        f"(normalized={expected_norm!r}) in {actual_files}"
    )
    return False


def finder_check_folder_exists(env, folder_path: str) -> bool:
    """
    Check if a directory exists at the given path on macOS via SSH.

    :param env: MacOSEnv instance
    :param folder_path: Absolute path to the folder to check
    :return: True if folder exists, False otherwise
    """
    env.connect_ssh()
    cmd = f'test -d "{folder_path}" && echo "Exists" || echo "Not found"'
    stdout, stderr = env.run_command(cmd)
    output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )
    return output == "Exists"


def finder_read_file_contents(env, file_path: str) -> str:
    """
    Read the contents of a file at the given path via SSH.

    :param env: MacOSEnv instance
    :param file_path: Absolute file path to read
    :return: File contents as string (empty string if not found or error)
    """
    env.connect_ssh()
    file_path = file_path.replace("~", "$HOME")
    cmd = f'cat "{file_path}"'

    stdout, stderr = env.run_command(cmd)
    logger.info(stdout)
    logger.info(stderr)

    if stderr and hasattr(stderr, "read") and stderr.read():
        logger.error(f"[finder_read_file_contents] Error reading file: {file_path}")
        return ""

    output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )
    return output


def finder_check_file_tag(env, file_path: str, target_tag: str = "Blue") -> bool:
    """
    Check if the given file has a specific Finder tag using osxmetadata inside macOS Docker.
    If the file does not exist, return False.

    :param env: MacOSEnv instance
    :param file_path: Absolute path to the file inside macOS
    :param target_tag: Tag color to check for (e.g., 'Blue')
    :return: True if tag is present, False otherwise
    """
    env.connect_ssh()

    # Python script to run remotely
    remote_py = f"""
import os
from pathlib import Path
try:
    from osxmetadata import OSXMetaData
    path = Path(r\"\"\"{file_path}\"\"\").expanduser().resolve()
    if not path.exists():
        print("__NOT_FOUND__")
    else:
        md = OSXMetaData(str(path))
        tags = md.tags or []
        print("__TAGS__:" + ",".join(str(tag) for tag in tags))
except Exception as e:
    print("__ERROR__:" + str(e))
"""

    try:
        # Save script to remote temporary file
        remote_tmp_path = "/tmp/check_tag_script.py"
        env.connect_sftp()
        with env.sftp_client.file(remote_tmp_path, "w") as f:
            f.write(remote_py)

        # Run the script
        stdout, stderr = env.run_command(f"/usr/bin/python3 {remote_tmp_path}")
        # logger.info(stdout)
        # logger.info(stderr)
        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        
        print(output)

        if "__NOT_FOUND__" in output:
            return False
        if "__TAGS__:" in output:
            tags = output.split("__TAGS__:")[-1].split(",")
            return any(target_tag.lower() in tag.lower() for tag in tags)
        if "__ERROR__:" in output:
            logger.error(f"Tag check error: {output}")
            return False

        logger.error(f"Unexpected tag output: {output}")
        return False

    except Exception as e:
        logger.error(f"Failed to check file tag: {e}")
        return False


def finder_check_no_unexpected_tags(
    env, directory: str, allowed_files: list[str], target_tag: str = "Red"
) -> bool:
    """
    Check that NO file in *directory*, OTHER than those in *allowed_files*,
    has the given Finder tag.

    This is a pure "integrity / negative" check: it does NOT verify that
    allowed_files actually have the tag (that's done by separate
    ``finder_check_file_tag`` components). It only checks that the agent
    didn't accidentally tag files that shouldn't be tagged.

    Args:
        env (MacOSEnv): macOS automation environment
        directory (str): Path to the directory to scan
        allowed_files (list[str]): Filenames that ARE allowed to have the tag
        target_tag (str): The tag to check for (default "Red")

    Returns:
        bool: True if no unexpected file has the tag. False if any
              non-allowed file was tagged.
    """
    env.connect_ssh()

    tag_str = target_tag.lower()
    allowed_set_str = repr(set(allowed_files))
    directory_str = str(directory)

    remote_py = textwrap.dedent(
        f"""
    from pathlib import Path
    from osxmetadata import OSXMetaData

    target_tag = "{tag_str}"
    allowed = {allowed_set_str}
    dir_path = Path("{directory_str}").expanduser().resolve()

    if not dir_path.is_dir():
        print("__NOT_FOUND__")
    else:
        issues = []
        for file in dir_path.iterdir():
            if not file.is_file():
                continue
            if file.name in allowed:
                continue
            try:
                md = OSXMetaData(str(file))
                tags = [str(t.name).lower() for t in (md.tags or [])]
                if target_tag in tags:
                    issues.append(file.name)
            except Exception:
                pass

        if not issues:
            print("__ALL_OK__")
        else:
            print("__UNEXPECTED__:" + ",".join(issues))
    """
    )

    safe_code = shlex.quote(remote_py)
    try:
        stdout, _ = env.run_command(f"/usr/bin/python3 -c {safe_code}")
        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        logger.info(
            f"[finder_check_no_unexpected_tags] {directory_str}: {output}"
        )
        if "__ALL_OK__" in output:
            return True
        if "__NOT_FOUND__" in output:
            logger.warning(f"[finder_check_no_unexpected_tags] dir not found: {directory_str}")
            return False
        return False
    except Exception as e:
        logger.error(f"finder_check_no_unexpected_tags failed: {e}")
        return False


def finder_check_tagged_files_strict(
    env, directory: str, expected_tagged_files: list[str], target_tag: str = "Red"
) -> bool:
    env.connect_ssh()

    # Prepare embedded values
    tag_str = target_tag.lower()
    files_list_str = repr(expected_tagged_files)
    directory_str = str(directory)

    # Inline script with resolved Python values
    remote_py = textwrap.dedent(
        f"""
    import os
    from pathlib import Path
    from osxmetadata import OSXMetaData

    target_tag = "{tag_str}"
    expected_files = {files_list_str}
    expected_set = set(expected_files)

    dir_path = Path("{directory_str}").expanduser().resolve()
    if not dir_path.is_dir():
        print("__NOT_FOUND__")
    else:
        actual_files = set(f.name for f in dir_path.iterdir() if f.is_file())
        for expected in expected_set:
            if expected not in actual_files:
                print(f"__MISSING_FILE__::{{expected}}")
                exit(0)

        issues = []
        for file in dir_path.iterdir():
            if not file.is_file():
                continue
            try:
                md = OSXMetaData(str(file))
                tags = [str(t.name).lower() for t in (md.tags or [])]
                has_tag = target_tag in tags
                name = file.name

                if name in expected_set:
                    if not has_tag:
                        issues.append(f"MISSING_TAG::{{name}}")
                else:
                    if has_tag:
                        issues.append(f"UNEXPECTED_TAG::{{name}}")
            except Exception as e:
                issues.append(f"ERROR::{{file.name}}::{{str(e)}}")

        if not issues:
            print("__ALL_OK__")
        else:
            print("__ISSUES__:" + "||".join(issues))
    """
    )

    # Safely quote and run
    safe_code = shlex.quote(remote_py)
    stdout, _ = env.run_command(f"/usr/bin/python3 -c {safe_code}")
    output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )

    if output == "__ALL_OK__":
        return True
    elif output.startswith("__MISSING_FILE__::"):
        logger.error(f"Missing expected file: {output}")
        return False
    elif output.startswith("__ISSUES__:"):
        logger.warning(f"Tag mismatch issues: {output}")
        return False
    elif output == "__NOT_FOUND__":
        logger.error(f"Directory '{directory}' not found.")
        return False
    else:
        logger.error(f"Unexpected output: {output}")
        return False


def finder_check_smart_folder_filters_pdf_in_seven_days(env, name: str) -> bool:
    """
    Check whether a Smart Folder has the correct filters

    :param env: MacOSEnv instance
    :param name: Name of the Smart Folder (without .savedSearch)
    :return: True if filters are satisfied
    """
    env.connect_ssh()

    remote_py = textwrap.dedent(
        """
    from pathlib import Path
    import plistlib

    smart_ok = False

    try:
        smart_path = Path.home() / "Library" / "Saved Searches" / "{name}.savedSearch"
        if smart_path.exists():
            with smart_path.open("rb") as f:
                data = plistlib.load(f)

            slices = data.get("SearchCriteria", []).get("FXCriteriaSlices", [])
            has_pdf = False
            has_last7 = False
            has_other = False
            for s in slices:
                display = s.get("displayValues", [])
                # print(display)
                if display == ["Kind", "is", "PDF"]:
                    has_pdf = True
                elif display == ["Last modified date", "is", "within last", "7", "days"]:
                    has_last7 = True
                else:
                    has_other = True
                    break

            if has_pdf and has_last7 and (not has_other):
                smart_ok = True
    except Exception as e:
        print("__ERROR_SMART__:" + str(e))
        

    if smart_ok:
        print("__MATCH__")
    elif not smart_ok:
        print("__SMART_FAIL__")
    """
    ).format(name=name)

    safe_code = shlex.quote(remote_py.strip())
    stdout, _ = env.run_command(f"python3 -c {safe_code}")
    logger.info(stdout)
    logger.info(_)
    output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )

    if output == "__MATCH__":
        return True
    elif "__SMART_FAIL__" in output:
        logger.warning(f"Smart Folder '{name}' filter conditions not satisfied.")
    elif output.startswith("__ERROR_"):
        logger.error(output)
    else:
        logger.error(f"Unexpected output: {output}")
    return False


# ====================================================================== #
# Fine-grained checkpoint helper (added 2026-04-12).
# ====================================================================== #


def finder_check_any_file_with_ext_in_dir(env, dir_path: str, ext: str = ".txt") -> bool:
    """
    Check whether *any* file with the given extension exists in the directory.

    Args:
        env (MacOSEnv): macOS automation environment
        dir_path (str): Absolute directory path to search
        ext (str): File extension including dot (e.g. ".jpg", ".txt")

    Returns:
        bool: True if at least one matching file exists.
    """
    env.connect_ssh()
    cmd = f'ls "{dir_path}"/*{ext} 2>/dev/null | head -1'
    stdout, _ = env.run_command(cmd)
    output = (
        stdout.read().decode().strip()
        if hasattr(stdout, "read")
        else stdout.strip()
    )
    found = len(output) > 0
    logger.info(f"[finder_check_any_file_with_ext_in_dir] {dir_path}/*{ext}: {found} ({output[:80]})")
    return found


def finder_check_any_txt_in_dir(env, dir_path: str) -> bool:
    """
    Check whether *any* .txt file exists in the given directory.

    Used as a coarse checkpoint for tasks where the agent should create
    a .txt file with a specific name — this catches the case where the
    agent created a file but got the name wrong.

    Args:
        env (MacOSEnv): macOS automation environment
        dir_path (str): Absolute directory path to search

    Returns:
        bool: True if at least one .txt file exists in the directory.
    """
    env.connect_ssh()
    cmd = f'ls "{dir_path}"/*.txt 2>/dev/null | head -1'
    stdout, _ = env.run_command(cmd)
    output = (
        stdout.read().decode().strip()
        if hasattr(stdout, "read")
        else stdout.strip()
    )
    found = len(output) > 0
    logger.info(f"[finder_check_any_txt_in_dir] {dir_path}: {found} ({output[:80]})")
    return found


if __name__ == "__main__":
    # Initialize the environment with default config
    macos_env = MacOSEnv()

    # Connect to Docker container
    macos_env.connect_ssh()

    value = finder_check_smart_folder_filters_pdf_in_seven_days(macos_env, "test1")
    logger.info(value)

    import time

    time.sleep(3)
    macos_env.close_connection()
