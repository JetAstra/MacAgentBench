import json
from typing import List
from controllers.env import MacOSEnv
from utils.logger import ProjectLogger
import time
import datetime
import pytz
import shlex

logger = ProjectLogger().get()

def check_file_exists(env, file_path: str) -> bool:
    """
    Check if a file exists at the specified path using AppleScript over SSH.

    :param env: The environment object (used for running commands)
    :param file_path: The file path in POSIX format
    :return: True if the file exists, False otherwise
    """
    try:
        # AppleScript to check if the file exists
        apple_script = f"""
        tell application "System Events"
            set fileExists to exists POSIX file "{file_path}"
        end tell
        return fileExists
        """
        
        # Execute the AppleScript using osascript
        stdout, stderr = env.run_command(f"osascript -e {shlex.quote(apple_script)}")

        # Read and decode the output
        output = stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()

        # If the output is "true", the file exists
        if output == "true":
            return True
        else:
            logger.error(f"[numbers_check_file_exists] File '{file_path}' does not exist.")
            return False

    except Exception as e:
        logger.error(f"[numbers_check_file_exists] Error occurred: {e}")
        return False