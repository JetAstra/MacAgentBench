import paramiko
from controllers.env import MacOSEnv
from utils.logger import ProjectLogger
from pathlib import Path
import json
import time
from bs4 import BeautifulSoup
import datetime


script_dir = Path(__file__).resolve().parent.parent
logger = ProjectLogger(log_dir=script_dir / "logs")

CONDA_PATH = r"/opt/anaconda3/condabin/conda"


def force_close_terminal(env: MacOSEnv):
    env.connect_ssh()
    cmds = ["osascript -e 'tell application \"Terminal\" to quit'"]
    for cmd in cmds:
        env.run_command(f"{cmd}")
    time.sleep(3)


def terminal_reset_window_status(env: MacOSEnv):
    force_close_terminal(env)
    env.connect_ssh()
    env.run_command(f"open -a 'Terminal'")
    time.sleep(2)


def terminal_check_package_in_conda_env(env, env_name: str, package_name: str) -> bool:
    """
    Check if a given package is installed in a specified conda environment.

    :param env: MacOSEnv instance for SSH connection
    :param env_name: Name of the conda environment
    :param package_name: Package to check
    :return: True if the package is installed in the environment, else False
    """
    env.connect_ssh()

    check_cmd = f'{CONDA_PATH} list -n {env_name} | grep "^{package_name}\\s"'
    stdout, _ = env.run_command(check_cmd)
    # logger.info(_)
    output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )
    return bool(output)


def terminal_check_files_in_directory(
    env, folder_path: str, required_files: list[str]
) -> bool:
    """
    Check if all files in `required_files` exist in the given folder (non-recursive).

    :param env: MacOSEnv instance for SSH connection
    :param folder_path: Absolute path to the target directory
    :param required_files: List of filenames to check (no subdirectory paths)
    :return: True if all files exist in the folder, else False
    """
    env.connect_ssh()

    folder_path = folder_path.replace("~", "$HOME")
    # Construct shell command: list files in folder and check for presence
    check_cmd = f'ls "{folder_path}"'
    stdout, _ = env.run_command(check_cmd)
    logger.info(_)
    output = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )
    existing_files = set(output.splitlines())

    return all(filename in existing_files for filename in required_files)


def terminal_check_command_in_history(env, target_command: str) -> bool:
    """
    Check if a specific command is present in the user's terminal history.

    :param env: MacOSEnv instance for SSH connection
    :param target_command: Command string to search in history
    :return: True if command exists in history, else False
    """
    env.connect_ssh()

    # Read full history from remote
    check_cmd = "cat ~/.zsh_history || cat ~/.bash_history"
    stdout, _ = env.run_command(check_cmd)
    logger.info(stdout)
    output = stdout.read().decode() if hasattr(stdout, "read") else stdout

    # Check if target command appears as exact substring
    return target_command in output


def terminal_check_output_matches_command(
    env, file_path: str, reference_command: str
) -> bool:
    """
    Run *reference_command* on the macOS host and compare its stdout
    with the content of *file_path* (written by the agent).

    Comparison extracts the "path" column from each line of ``du``-style
    output (tab-separated: ``<size>\\t<path>``), then checks whether the
    two path lists are identical. This makes the comparison robust to
    minor size changes between the agent's run and the evaluator's run.

    Falls back to exact string comparison if the output doesn't look
    like tab-separated ``du`` output.

    Args:
        env (MacOSEnv): macOS automation environment
        file_path (str): Path to the file the agent wrote (e.g. ~/Desktop/output.txt)
        reference_command (str): The command to run as ground truth

    Returns:
        bool: True if the agent's output matches the reference.
    """
    env.connect_ssh()

    def _read(cmd):
        stdout, _ = env.run_command(cmd)
        raw = stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
        return raw

    def _extract_paths(text):
        """Extract the path column from du-style tab-separated output."""
        paths = []
        for line in text.strip().splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                paths.append(parts[1].strip())
            else:
                paths.append(line.strip())
        return paths

    try:
        # Run the reference command
        ref_output = _read(reference_command)

        # Read agent's file
        safe_path = file_path.replace("~", "$HOME")
        agent_output = _read(f'cat "{safe_path}"')

        if not ref_output or not agent_output:
            logger.warning(
                f"[terminal_check_output_matches_command] "
                f"empty output: ref={len(ref_output)} chars, agent={len(agent_output)} chars"
            )
            return False

        # Compare path columns (robust to size changes)
        ref_paths = _extract_paths(ref_output)
        agent_paths = _extract_paths(agent_output)

        matched = ref_paths == agent_paths
        logger.info(
            f"[terminal_check_output_matches_command] "
            f"ref_paths={ref_paths}, agent_paths={agent_paths}, match={matched}"
        )
        return matched

    except Exception as e:
        logger.error(f"terminal_check_output_matches_command failed: {e}")
        return False


def terminal_check_archive_validity_count_name_mod(
    env, base_path="/Users/Shared", min_files: int = 5, permission: str = "100"
) -> bool:
    """
    Check whether a tar.gz archive with today's date exists in the given directory,
    contains at least min_files files, and has the expected permission.

    :param env: MacOSEnv instance
    :param base_path: Directory to search for archive
    :param min_files: Minimum number of files required in the archive
    :param permission: Expected permission suffix (e.g. "100", "700", "755")
    :return: True if valid archive found and all checks pass, else False
    """
    env.connect_ssh()

    # 1. Get container time
    date_cmd = 'date "+%Y%m%d"'
    stdout, _ = env.run_command(date_cmd)
    date_str = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )

    if not date_str or not date_str.isdigit():
        logger.error(f"Failed to parse container date: {date_str}")
        return False

    filename = f"archive_{date_str}.tar.gz"
    archive_path = f"{base_path}/{filename}"

    # 2. Check if archive exists
    check_cmd = f'test -f "{archive_path}" && echo "Exists" || echo "NotFound"'
    stdout, _ = env.run_command(check_cmd)
    if "NotFound" in (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    ):
        logger.info("Archive not found.")
        return False

    # 3. Check number of files in the archive
    count_cmd = f'sudo tar -tzf "{archive_path}" | wc -l'
    stdout, _ = env.run_command(count_cmd)
    try:
        count = int(
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        logger.info(count)
        if count < min_files:
            logger.info(count)
            logger.info(f"Archive does not contain enough files (need {min_files}).")
            return False
    except Exception as e:
        logger.error(f"Failed to count files in archive: {e}")
        return False

    # 4. Check permission
    perm_cmd = f'sudo stat -f "%p" "{archive_path}"'
    stdout, _ = env.run_command(perm_cmd)
    raw_perm = (
        stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
    )
    if not raw_perm.endswith(permission):
        logger.info(f"Incorrect permissions: {raw_perm} (expected ending with {permission})")
        return False

    return True


def terminal_check_echo_macos_script(
    env,
    base_path="/Users/Shared",
    file_pattern=".*echo_macos*",
    permission: str = "",
    expected_output: str = "macOS task complete",
) -> bool:
    """
    Check for a valid hidden shell script in the given directory.
    Conditions:
    - File name matches the given pattern
    - Only one such file exists
    - File has user execute permission (no group/other permissions)
    - Script outputs the expected message on execution

    :param env: MacOSEnv instance
    :param base_path: Directory to search in
    :param file_pattern: Glob pattern for matching files (e.g. ".*echo_macos*")
    :param permission: Expected permission (e.g. "100", "700"). If empty, accepts any user-execute-only permission.
    :param expected_output: Expected stdout when running the script
    """
    env.connect_ssh()

    try:
        # 1. List matching files
        cmd_list = f'sudo find {base_path} -maxdepth 1 -name "{file_pattern}" -type f'
        stdout, _ = env.run_command(cmd_list)
        logger.info(stdout)
        logger.info(_)

        matches = (
            stdout.read().decode().strip().splitlines()
            if hasattr(stdout, "read")
            else stdout.strip().splitlines()
        )
        logger.info(f"[Check] Matching files: {matches}")

        # 2. Ensure exactly one match
        if len(matches) != 1:
            logger.error(f"Expected 1 match, got {len(matches)}")
            return False

        filepath = matches[0]

        # 3. Check permission
        cmd_perm = f'stat -f "%A" "{filepath}"'
        stdout, _ = env.run_command(cmd_perm)
        perms = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        logger.info(f"[Check] Permissions: {perms}")
        if permission:
            if perms != permission:
                logger.error(f"Expected permission {permission}, got {perms}.")
                return False
        else:
            valid_perms = {"500", "700"}
            if perms not in valid_perms:
                logger.error(f"Error permissions: {perms}.")
                return False

        # 4. Execute and check output
        cmd_exec = f'bash "{filepath}"'
        stdout, _ = env.run_command(cmd_exec)
        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        logger.info(f"[Check] Script output: {output}")
        return output == expected_output

    except Exception as e:
        logger.error(f"Script validation failed: {e}")
        return False


if __name__ == "__main__":
    # Initialize the environment with default config
    macos_env = MacOSEnv()

    # Connect to Docker container
    macos_env.connect_ssh()

    value = terminal_check_echo_macos_script(macos_env)
    logger.info(value)

    import time

    time.sleep(3)
    macos_env.close_connection()
