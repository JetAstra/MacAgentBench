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
from . import common

script_dir = Path(__file__).resolve().parent.parent

logger = ProjectLogger(log_dir=script_dir / "logs")


def strip_all_suffixes(name: str) -> str:
    normalized = Path(name).name
    while True:
        stem = Path(normalized).stem
        if stem == normalized:
            return normalized
        normalized = stem

def is_rbg_reddish(rgb8, dominance=40, min_red=120):
    """
    判断 8-bit RGB 是否偏红
    - 红色主导
    - 可调整 dominance（与其他通道差值）和 min_red
    """
    r, g, b = rgb8
    return r >= min_red and (r - max(g, b)) >= dominance

def is_rbg_greenish(rgb8, dominance=40, min_green=120):
    """
    判断 8-bit RGB 是否偏绿
    - 绿色主导
    - 可调整 dominance（与其他通道差值）和 min_red
    """
    r, g, b = rgb8
    return g >= min_green and (g - max(r, b)) >= dominance

def pages_get_character_color(env, idx: int) -> tuple:
    env.connect_ssh()

    apple_script = f"""
    tell application "Pages"
        tell front document
            set charColor to color of character {idx} of body text
            return charColor
        end tell
    end tell
    """

    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )

        if output.startswith("false__"):
            logger.error(f"[pages_check_character_color] {output}")
            return False

        rgb = tuple(int(x.strip()) for x in output.split(","))
        return rgb

    except Exception as e:
        logger.error(f"[pages_check_character_color] Failed: {e}")
        return tuple(0,0,0)

def pages_get_text_alignment(env, p_idx):
    env.connect_ssh()

    apple_script = f"""
    tell application "Pages"
        tell front document
            set theAlignment to alignment of paragraph {p_idx} of selection
            return theAlignment
        end tell
    end tell
    """

    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        logger.error(f"[pages_get_text_alignment]: {output}")
        return output

    except Exception as e:
        logger.error(f"[pages_get_text_alignment] Failed: {e}")
        return ""

def pages_get_text_font(env, idx):
    env.connect_ssh()

    apple_script = f"""
    tell application "Pages"
        tell front document
            set charColor to font of character {idx} of body text
            return charColor
        end tell
    end tell
    """

    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        if output.startswith("false__"):
            logger.error(f"[pages_get_text_font] {output}")
            return False

        return output

    except Exception as e:
        logger.error(f"[pages_get_text_font] Failed: {e}")
        return ""

def pages_get_body_text(env, page_idx):
    env.connect_ssh()

    apple_script = f"""
    tell application "Pages"
        tell front document
            tell page {page_idx}
                return body text
            end tell
        end tell
    end tell
    """

    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        if output.startswith("false__"):
            logger.error(f"[pages_get_body_text] {output}")
            return False

        return output

    except Exception as e:
        logger.error(f"[pages_get_body_text] Failed: {e}")
        return ""

def pages_get_table_cell_value(env, row, col):
    env.connect_ssh()
    
    apple_script = f"""tell application "Pages"
        tell front document
            set cellValue to value of cell {col} of row {row} of first table
            return cellValue
        end tell
    end tell
    """
    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        if output.startswith("false__"):
            logger.error(f"[pages_get_table_cell_value] {output}")
            return False

        return output

    except Exception as e:
        logger.error(f"[pages_get_table_cell_value] Failed: {e}")
        return ""

def pages_get_first_shape_property(env, property):
    if property not in ['opacity', 'parent', 'class', 'reflection showing', 'background fill type', 'position', 'object text', 'width', 'rotation', 'reflection value', 'height', 'locked']:
        return ''
    
    env.connect_ssh()
    
    apple_script = f"""tell application "Pages"
        tell front document
            tell front shape
                return {property}
            end tell
        end tell
    end tell
    """
    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )

        return output

    except Exception as e:
        logger.error(f"[pages_get_first_shape_property] Failed: {e}")
        return ""
    
def pages_check_character_color(env, idx: int, expected_color: tuple) -> bool:
    env.connect_ssh()

    apple_script = f"""
    tell application "Pages"
        tell front document
            set charColor to color of character {idx} of body text
            return charColor
        end tell
    end tell
    """

    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )

        if output.startswith("false__"):
            logger.error(f"[pages_check_character_color] {output}")
            return False

        rgb = tuple(int(x.strip()) for x in output.split(","))

        return rgb == expected_color

    except Exception as e:
        logger.error(f"[pages_check_character_color] Failed: {e}")
        return False

def pages_check_body_text(env, expected_text: str, exact_match: bool = True, p_idx: int = 1) -> bool:
    env.connect_ssh()

    apple_script = f"""
    tell application "Pages"
        tell front document
            tell page {p_idx}
                return body text
            end tell
        end tell
    end tell
    """

    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode("utf-8").strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        
        if exact_match:
            return output == expected_text.strip()
        else:
            return expected_text.strip() in output

    except Exception as e:
        logger.error(f"[pages_check_body_text] Failed: {e}")
        return False

def pages_check_character_font(env, idx: int, expected_font: str) -> bool:
    env.connect_ssh()

    apple_script = f"""
    tell application "Pages"
        if (count of documents) = 0 then
            return "false__no_document"
        end if

        tell front document
            if (length of body text) < {idx} then
                return "false__out_of_range"
            end if

            try
                set charFont to font of character {idx} of body text
                return charFont
            on error
                return "false__cannot_get_font"
            end try
        end tell
    end tell
    """

    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode("utf-8").strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )

        if output.startswith("false__"):
            logger.error(f"[pages_check_character_font] {output}")
            return False

        return output == expected_font.strip()

    except Exception as e:
        logger.error(f"[pages_check_character_font] Failed: {e}")
        return False

def pages_check_doc_name(env, expected_name: str, exact_match: bool = True) -> bool:
    env.connect_ssh()
    expected_name = expected_name.strip()

    apple_script = """
    tell application "Pages"
        if (count of documents) = 0 then
            return "false__no_document"
        end if

        return name of front document
    end tell
    """

    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode("utf-8").strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )

        if output.startswith("false__"):
            logger.error("[pages_check_doc_name] No document open.")
            return False

        if exact_match:
            return strip_all_suffixes(output) == strip_all_suffixes(expected_name)
        else:
            return expected_name in output

    except Exception as e:
        logger.error(f"[pages_check_doc_name] Failed: {e}")
        return False

def pages_get_template(env):
    env.connect_ssh()

    apple_script = f"""
    tell application "Pages"
        tell front document
            return document template
        end tell
    end tell
    """

    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )

        return output

    except Exception as e:
        logger.error(f"[pages_get_template] Failed: {e}")
        return ""

def pages_test_create_and_enter_content(env, template_name, doc_name, content) -> bool:
    if not pages_check_doc_name(env=env, expected_name=doc_name, exact_match=True):
        return False
    if not pages_check_body_text(env=env, expected_text=content, exact_match=True):
        return False
    if template_name == "Blank Black":
        if pages_get_template(env=env) != "template id Application/20_Blank_Black/Traditional":
            print(pages_get_template(env=env))
            return False
    return True

def pages_test_change_font_color(env, color: str) -> bool:
    font_color = pages_get_character_color(env, 1)
    if color.lower() == "red":
        if not is_rbg_reddish(rgb8=font_color):
            return False
    if color.lower() == "green":
        if not is_rbg_greenish(rgb8=font_color):
            return False
    return True

def pages_test_change_text_alignment(env, p_idx, target_alignment):
    alignment = pages_get_text_alignment(env=env, p_idx=p_idx)
    if not alignment.lower() == target_alignment.lower():
        return False
    return True

def pages_test_change_text_font(env, idx, target_font):
    alignment = pages_get_text_font(env=env, idx=idx)
    if not alignment.lower() == target_font.lower():
        return False
    return True

def pages_test_insert_table(env, row, col, target_val):
    val = pages_get_table_cell_value(env=env, row=row, col=col)
    if not val == target_val:
        return False
    return True

def pages_test_find_and_replace(env, content, target, replace):
    print(pages_get_body_text(env=env, page_idx=1))
    print(content.replace(target, replace))
    return pages_get_body_text(env=env, page_idx=1) == content.replace(target, replace)  

def pages_test_shape_pos_and_size(env, pos, width, height):
    width *= 72
    height *= 72
    if pos != pages_get_first_shape_property(env=env, property='position'):
        return False
    if f"{width}" != pages_get_first_shape_property(env=env, property='width'):
        return False
    if f"{height}" != pages_get_first_shape_property(env=env, property='height'):
        return False
    return True

def pages_init_content(env, content):
    env.connect_ssh()
    
    apple_script = f"""tell application "Pages"
        tell front document
            set body text to {content}
            return cellValue
        end tell
    end tell
    """
    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )

    except Exception as e:
        logger.error(f"[pages_init_content] Failed: {e}")

def pages_create_new_doc(env):
    env.connect_ssh()
    
    apple_script = f"""tell application "Pages"
        make new document
    end tell
    """
    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )

    except Exception as e:
        logger.error(f"[pages_create_new_doc] Failed: {e}")

if __name__ == "__main__":
    # Initialize the environment with default config
    macos_env = MacOSEnv()

    # Connect to Docker container
    macos_env.connect_ssh()

    value = calendar_debug(macos_env, "test_note")
    logger.info(value)

    import time

    time.sleep(3)
    macos_env.close_connection()
