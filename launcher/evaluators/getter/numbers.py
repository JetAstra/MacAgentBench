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

def convert_applescript_rgb(r16, g16, b16):
    """16-bit RGB → 8-bit RGB"""
    return (
        round(r16 / 65535 * 255),
        round(g16 / 65535 * 255),
        round(b16 / 65535 * 255),
    )

def is_rbg_reddish(rgb8, dominance=40, min_red=120):
    """
    判断 8-bit RGB 是否偏红
    - 红色主导
    - 可调整 dominance（与其他通道差值）和 min_red
    """
    r, g, b = rgb8
    return r >= min_red and (r - max(g, b)) >= dominance

def __get_current_working_table(env) -> tuple[str, str, str]:
    try:
        # AppleScript to get the current document, sheet, and table names
        apple_script = """
        tell application "Numbers"
            set doc_name to name of front document
            set sheet_name to name of front sheet of front document
            set table_name to name of front table of front sheet of front document

            return {doc_name, sheet_name, table_name}
        end tell
        """

        # Execute the AppleScript using osascript
        stdout, stderr = env.run_command(f"osascript -e {shlex.quote(apple_script)}")

        # Read and decode the output
        output = stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
        # Parse the output into doc_name, sheet_name, table_name
        doc_name, sheet_name, table_name = output.split(", ")

        # Return the tuple of names
        return doc_name.strip('"'), sheet_name.strip('"'), table_name.strip('"')

    except Exception as e:
        logger.error(f"[__get_current_working_table] Error occurred: {e}")
        return "", "", ""

def numbers_check_sheet_template(env, template_name: str) -> bool:
    env.connect_ssh()

    template_name = template_name.strip()

    apple_script = f"""
    tell application "Numbers"
        if (count of documents) = 0 then
            return "false__no_document"
        end if

        set docTemplate to name of document template of front document
        return docTemplate
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
            logger.error("[numbers_check_sheet_template] No document open.")
            return False

        return output == template_name

    except Exception as e:
        logger.error(f"[numbers_check_sheet_template] Failed: {e}")
        return False

def numbers_check_doc_name(env, doc_name: str) -> bool:
    env.connect_ssh()

    apple_script = f"""
    tell application "Numbers"
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
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )

        if output.startswith("false__"):
            logger.error("[numbers_check_doc_name] No document open.")
            return False

        return strip_all_suffixes(output) == strip_all_suffixes(doc_name)

    except Exception as e:
        logger.error(f"[numbers_check_doc_name] Failed: {e}")
        return False

def numbers_check_all_sheet_names(env, sheet_names: list[str]) -> bool:
    env.connect_ssh()

    apple_script = """
    tell application "Numbers"
        if (count of documents) = 0 then
            return "false__no_document"
        end if
        
        tell front document
            return name of every sheet
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
            logger.error("[numbers_check_all_sheet_names] No document open.")
            return False

        actual_sheets = [s.strip() for s in output.split(",")]

        missing = set(sheet_names) - set(actual_sheets)
        extra = set(actual_sheets) - set(sheet_names)

        if missing:
            logger.error(f"[numbers_check_all_sheet_names] Missing sheets: {missing}")
        if extra:
            logger.error(f"[numbers_check_all_sheet_names] Extra sheets: {extra}")

        return not missing and not extra

    except Exception as e:
        logger.error(f"[numbers_check_all_sheet_names] Failed: {e}")
        return False

def numbers_check_single_sheet_name(env, sheet_name: str) -> bool:
    env.connect_ssh()

    apple_script = f"""
    tell application "Numbers"
        if (count of documents) = 0 then
            return "false__no_document"
        end if
        
        tell front document
            if exists sheet "{sheet_name}" then
                return "true__sheet_exists"
            else
                return "false__missing_sheet"
            end if
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

        if output=="false__no_document":
            logger.error("[numbers_check_single_sheet_name] No document open.")
            return False

        return output.startswith("true__")

    except Exception as e:
        logger.error(f"[numbers_check_all_sheet_names] Failed: {e}")
        return False

def numbers_check_all_table_names(
    env,
    sheet_name: str,
    table_names: list[str],
) -> bool:
    env.connect_ssh()

    apple_script = f"""
    tell application "Numbers"
        if (count of documents) = 0 then
            return "false__no_document"
        end if
        
        tell front document
            if not (exists sheet "{sheet_name}") then
                return "false__missing_sheet"
            end if
            
            tell sheet "{sheet_name}"
                return name of every table
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

        if output == "false__no_document":
            logger.error("[numbers_check_all_table_names] No document open.")
            return False

        if output == "false__missing_sheet":
            logger.error("[numbers_check_all_table_names] Sheet not found.")
            return False

        actual_tables = (
            [t.strip() for t in output.split(",")]
            if output
            else []
        )

        missing = set(table_names) - set(actual_tables)
        extra = set(actual_tables) - set(table_names)

        if missing:
            logger.error(f"[numbers_check_all_table_names] Missing tables: {missing}")
        if extra:
            logger.error(f"[numbers_check_all_table_names] Extra tables: {extra}")

        return not missing and not extra

    except Exception as e:
        logger.error(f"[numbers_check_all_table_names] Failed: {e}")
        return False

def numbers_check_single_table_name(env, sheet_name: str, table_name: str) -> bool:
    env.connect_ssh()
    apple_script = f"""
    tell application "Numbers"
        if (count of documents) = 0 then
            return "false__no_document"
        end if
        
        tell front document
            if not (exists sheet "{sheet_name}") then
                return "false__missing_sheet"
            end if
            
            tell sheet "{sheet_name}"
                if exists table "{table_name}" then
                    return "true__table_exists"
                else
                    return "false__missing_table"
                end if
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
        if output == "false__no_document":
            logger.error("[numbers_check_single_table_name] No document open.")
            return False

        if output == "false__missing_sheet":
            logger.error("[numbers_check_single_table_name] Sheet not found.")
            return False

        return output.startswith("true__")

    except Exception as e:
        logger.error(f"[numbers_check_single_table_name] Failed: {e}")
        return False

def numbers_check_cell_value(
    env,
    sheet_name: str,
    table_name: str,
    row: int,
    col: int,
    target: str,
) -> bool:
    env.connect_ssh()

    apple_script = f"""
    tell application "Numbers"
        if (count of documents) = 0 then
            return "false__no_document"
        end if
        
        tell front document
            if not (exists sheet "{sheet_name}") then
                return "false__missing_sheet"
            end if
            
            tell sheet "{sheet_name}"
                if not (exists table "{table_name}") then
                    return "false__missing_table"
                end if
                
                tell table "{table_name}"
                    try
                        set cellValue to value of cell {col} of row {row}
                        return cellValue
                    on error
                        return "false__invalid_index"
                    end try
                end tell
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
        try:
            float_value = float(output)
            return float_value == target
        except ValueError:
            return output == target

    except Exception as e:
        logger.error(f"[numbers_check_cell_value] Failed: {e}")
        return False

def numbers_get_cell_value(
    env,
    sheet_name: str,
    table_name: str,
    row: int,
    col: int,
):
    env.connect_ssh()

    apple_script = f"""
    tell application "Numbers"
        tell front document
            tell sheet "{sheet_name}"
                tell table "{table_name}"
                    set cellValue to value of cell {col} of row {row}
                    return cellValue
                end tell
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
        try:
            return float(output)
        except ValueError:
            return output

    except Exception as e:
        logger.error(f"[numbers_check_cell_value] Failed: {e}")
        return -1

def numbers_check_cell_format(
    env,
    sheet_name: str,
    table_name: str,
    row: int,
    col: int,
    target_format: str,
) -> bool:

    env.connect_ssh()

    apple_script = f"""
    tell application "Numbers"
        if (count of documents) = 0 then
            return "false__no_document"
        end if
        
        tell front document
            if not (exists sheet "{sheet_name}") then
                return "false__missing_sheet"
            end if
            
            tell sheet "{sheet_name}"
                if not (exists table "{table_name}") then
                    return "false__missing_table"
                end if
                
                tell table "{table_name}"
                    try
                        set cellFormat to format of cell {col} of row {row}
                        if cellFormat is "{target_format}" then
                            return "true__correct_format"
                        else
                            return "false__not_correct_format"
                        end if
                    on error
                        return "false__invalid_index"
                    end try
                end tell
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
        print(output)
        return output.startswith("true__")

    except Exception as e:
        logger.error(f"[numbers_check_cell_format] Failed: {e}")
        return False

def numbers_check_cell_is_merged(
    env,
    sheet_name: str,
    table_name: str,
    row: int,
    col: int,
) -> bool:
    """
    Check whether a specific cell is a merged cell (i.e., has row span > 1 or column span > 1).

    Returns True if the cell is a merge master cell.
    Returns False otherwise.
    """

    env.connect_ssh()

    apple_script = f"""
    tell application "Numbers"
        if (count of documents) = 0 then
            return "false__no_document"
        end if

        tell front document
            if not (exists sheet "{sheet_name}") then
                return "false__no_sheet"
            end if

            tell sheet "{sheet_name}"
                if not (exists table "{table_name}") then
                    return "false__no_table"
                end if

                tell table "{table_name}"
                    set targetCell to cell {row} of column {col}
                    set rSpan to row span of targetCell
                    set cSpan to column span of targetCell

                    if rSpan > 1 or cSpan > 1 then
                        return "true__merged"
                    else
                        return "false__not_merged"
                    end if
                end tell
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

        if output == "false__no_document":
            logger.error("[numbers_check_cell_is_merged] No document open.")
            return False

        if output == "false__no_sheet":
            logger.error(f"[numbers_check_cell_is_merged] Sheet '{sheet_name}' not found.")
            return False

        if output == "false__no_table":
            logger.error(f"[numbers_check_cell_is_merged] Table '{table_name}' not found.")
            return False

        return output.startswith("true__")

    except Exception as e:
        logger.error(f"[numbers_check_cell_is_merged] Failed: {e}")
        return False

def numbers_check_range_merged(
    env,
    sheet_name: str,
    table_name: str,
    start_row: int,
    start_col: int,
    end_row: int,
    end_col: int,
) -> bool:
    """
    Check whether a rectangular range is merged correctly.

    Validation logic:
    Only verify the top-left cell of the range.
    The cell must have the expected row span and column span.
    """

    env.connect_ssh()

    apple_script = f"""
    tell application "Numbers"
        tell front document's sheet "{sheet_name}"'s table "{table_name}"
            set nameList to ""
            repeat with r from {start_row} to {end_row}
                repeat with c from {start_col} to {end_col}
                    -- 获取单元格的 name
                    set cName to name of cell c of row r
                    set nameList to nameList & cName & ","
                end repeat
            end repeat
            return nameList
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
        
        names = [n for n in output.split(",") if n]
        # 判断是否所有名字都一致 (即是否都指向同一个单元格)
        is_merged = (len(set(names)) == 1)
        return is_merged

    except Exception as e:
        logger.error(f"[numbers_check_range_merged] Failed: {e}")
        return False

def numbers_get_visible_rows(
    env,
    sheet_name: str,
    table_name: str,
) -> list[int]:
    """
    Return a list of visible row indices in the given sheet and table.

    A row is considered visible if its 'hidden' property is false.
    """

    env.connect_ssh()

    apple_script = f"""
    tell application "Numbers"
        if (count of documents) = 0 then
            return "false__no_document"
        end if

        tell front document
            if not (exists sheet "{sheet_name}") then
                return "false__no_sheet"
            end if

            tell sheet "{sheet_name}"
                if not (exists table "{table_name}") then
                    return "false__no_table"
                end if

                tell table "{table_name}"
                    set rowCount to count of rows
                    set visibleRows to ""

                    repeat with i from 1 to rowCount
                        if hidden of row i is false then
                            if visibleRows is "" then
                                set visibleRows to i as string
                            else
                                set visibleRows to visibleRows & "," & (i as string)
                            end if
                        end if
                    end repeat

                    return visibleRows
                end tell
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
        print(output)
        if output == "false__no_document":
            logger.error("[numbers_get_visible_rows] No document open.")
            return []

        if output == "false__no_sheet":
            logger.error(f"[numbers_get_visible_rows] Sheet '{sheet_name}' not found.")
            return []

        if output == "false__no_table":
            logger.error(f"[numbers_get_visible_rows] Table '{table_name}' not found.")
            return []

        if output == "":
            return []

        return [int(x) for x in output.split(",")]

    except Exception as e:
        logger.error(f"[numbers_get_visible_rows] Failed: {e}")
        return []

def numbers_get_cell_bg_color(env, sheet_name: str, table_name: str, row: int, col: int):
    """
    获取 Numbers 某个 cell 的 background color（16-bit RGB）
    返回: (r16, g16, b16) 或 None
    """
    env.connect_ssh()

    apple_script = f"""
    tell application "Numbers"
        if (count of documents) = 0 then
            return "ERROR__no_document"
        end if
        
        tell front document
            if not (exists sheet "{sheet_name}") then
                return "ERROR__missing_sheet"
            end if
            
            tell sheet "{sheet_name}"
                if not (exists table "{table_name}") then
                    return "ERROR__missing_table"
                end if
                
                tell table "{table_name}"
                    try
                        set bg to background color of cell {col} of row {row}
                        return (item 1 of bg as string) & "," & (item 2 of bg as string) & "," & (item 3 of bg as string)
                    on error
                        return "ERROR__invalid_index"
                    end try
                end tell
            end tell
        end tell
    end tell
    """

    try:
        stdout, stderr = env.run_command(f"osascript -e {shlex.quote(apple_script)}")
        output = stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()

        if output.startswith("ERROR__"):
            logger.warning(f"[numbers_get_cell_bg_color] {output}")
            return None

        r16, g16, b16 = map(int, output.split(","))
        return r16, g16, b16

    except Exception as e:
        logger.error(f"[numbers_get_cell_bg_color] Failed: {e}")
        return None

def numbers_check_cell_bg_is_reddish(env, sheet_name: str, table_name: str, row: int, col: int) -> bool:
    """
    检查 Numbers 某个 cell 是否偏红
    """
    color16 = numbers_get_cell_bg_color(env, sheet_name, table_name, row, col)
    if color16 is None:
        return False

    rgb8 = convert_applescript_rgb(*color16)
    return is_rbg_reddish(rgb8)

def numbers_test_create_and_save_table(env, template_name: str, doc_name: str, file_name: str, sheet_name: str, table_name: str):
    '''
    task 1: save a document with certain
    - template
    - save file name
    - doc, sheet, table names
    note:
    - only support one sheet and one table (for simplicity)
    '''
    if not common.check_file_exists(env=env, file_path=file_name):
        return False
    if not numbers_check_sheet_template(env=env, template_name=template_name):
        return False
    if not numbers_check_doc_name(env=env, doc_name=doc_name):
        return False
    if not numbers_check_single_sheet_name(env=env, sheet_name=sheet_name):
        return False
    if not numbers_check_single_table_name(env=env, sheet_name=sheet_name, table_name=table_name):
        return False
    return True

def numbers_test_cell_operation(env, cells: list[list[int]], values: list[int]):
    '''
    task 2: cell operation, write certain value to certain cells
    '''
    doc_name, sheet_name, table_name = __get_current_working_table(env)
    for cell, value in zip(cells, values):
        if not numbers_check_cell_value(env=env, sheet_name=sheet_name, table_name=table_name, row=cell[0], col=cell[1], target=value):
            return False
    return True

def numbers_test_cell_format(env, cell: list[int], target_format: str):
    '''
    task 2: cell operation, write certain value to certain cells
    '''
    doc_name, sheet_name, table_name = __get_current_working_table(env)
    if not numbers_check_cell_format(env=env, sheet_name=sheet_name, table_name=table_name, row=cell[0][0], col=cell[0][1], target_format=target_format):
        return False
    return True

def numbers_test_value_replacement(env, rows, cols, target_value, replace_value):
    doc_name, sheet_name, table_name = __get_current_working_table(env)
    for row in range(1, rows+1):
        for col in range(1, cols+1):
            if row * col == target_value:
                if not numbers_check_cell_value(env=env, sheet_name=sheet_name, table_name=table_name, row=row, col=col, target=replace_value):
                    return False
            else:
                if not numbers_check_cell_value(env=env, sheet_name=sheet_name, table_name=table_name, row=row, col=col, target=row * col):
                    print(row)
                    print(col)
                    return False
    return True

def numbers_test_cell_merge(env, rows, cols, merged_cell):
    doc_name, sheet_name, table_name = __get_current_working_table(env)
    if not numbers_check_range_merged(env=env, sheet_name=sheet_name, table_name=table_name, start_row=merged_cell[0], start_col=merged_cell[1], end_row=merged_cell[2], end_col=merged_cell[3]):
        return False
    return True

def numbers_test_filter(env, rows, cols, col_selected, is_larger, is_smaller, min, max, is_equal):
    doc_name, sheet_name, table_name = __get_current_working_table(env)
    visible_rows = numbers_get_visible_rows(env=env, sheet_name=sheet_name, table_name=table_name)
    all_rows = set(range(2, rows + 1))
    hidden_rows = sorted(all_rows - set(visible_rows))
    print(all_rows)
    print(hidden_rows)
    print(visible_rows)
    for row in visible_rows:
        val = numbers_get_cell_value(env=env, sheet_name=sheet_name, table_name=table_name, row=row, col=col_selected)
        if is_larger:
            if (is_equal and val < min) or (not is_equal and val <= min):
                return False
        if is_smaller:
            if (is_equal and val > max) or (not is_equal and val >= max):
                return False
            
    for row in hidden_rows:
        val = numbers_get_cell_value(env=env, sheet_name=sheet_name, table_name=table_name, row=row, col=col_selected)
        if is_larger:
            if (is_equal and val >= min) or (not is_equal and val > min):
                return False
        if is_smaller:
            if (is_equal and val <= max) or (not is_equal and val < max):
                return False
    return True

def numbers_test_change_bgcolor(env, rows, cols, is_larger, is_smaller, min, max, is_equal):
    doc_name, sheet_name, table_name = __get_current_working_table(env)
    for row in range(1, rows+1):
        for col in range(1, cols+1):
            val = numbers_get_cell_value(env=env, sheet_name=sheet_name, table_name=table_name, row=row, col=col)
            if numbers_check_cell_bg_is_reddish(env=env, sheet_name=sheet_name, table_name=table_name, row=row, col=col):
                if is_larger:
                    if (is_equal and val < min) or (not is_equal and val <= min):
                        return False
                if is_smaller:
                    if (is_equal and val > max) or (not is_equal and val >= max):
                        return False
            else:
                tag = False
                if is_larger:
                    if (is_equal and val < min) or (not is_equal and val <= min):
                        tag = True
                if is_smaller:
                    if (is_equal and val > max) or (not is_equal and val >= max):
                        tag = True
                if not tag:
                    return False
    return True

def numbers_init_table(env, rows, cols):
    env.connect_ssh()
    apple_script = f"""
    tell application "Numbers"
        activate
        set newDoc to make new document
        tell active sheet of newDoc
            delete every table
            set newTable to make new table with properties {{row count:{rows}, column count:{cols}}}
            tell newTable
                repeat with r from 1 to 5
                    repeat with c from 1 to 5
                        set value of cell c of row r to (r * c)
                    end repeat
                end repeat
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
    except Exception as e:
        logger.error(f"[numbers_init_table] Failed: {e}")

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
