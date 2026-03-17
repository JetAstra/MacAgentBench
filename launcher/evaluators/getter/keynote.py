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

def parse_fixed_string(s, keys):
    result = {}
    for i in range(len(keys)):
        current_key = keys[i] + ":"
        next_key = keys[i+1] + ":" if i + 1 < len(keys) else None
        
        start = s.find(current_key) + len(current_key)
        
        if next_key:
            end = s.find(next_key)
            val = s[start:end].strip().rstrip(',')
        else:
            val = s[start:].strip()
            
        result[keys[i]] = val
    return result

def keynote_get_document_template(env):
    env.connect_ssh()

    apple_script = f"""
    tell application "Keynote"
        tell front document
            return document theme
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
        return output.split(" ")[-1] # Application/20_BasicBlack/Standard

    except Exception as e:
        logger.error(f"[keynote_get_document_template] Failed: {e}")
        return ""

def keynote_get_document_name(env):
    env.connect_ssh()

    apple_script = f"""
    tell application "Keynote"
        tell front document
            return name
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
        logger.error(f"[keynote_get_document_name] Failed: {e}")
        return ""

def keynote_get_text_box_cnt(env, s_idx):
    env.connect_ssh()

    apple_script = f"""
    tell application "Keynote"
        tell front document
            tell slide {s_idx}
                set itemCount to count every text item
                return itemCount
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
        
        text_box_cnt = int(output)

        return text_box_cnt

    except Exception as e:
        logger.error(f"[keynote_get_text_box_cnt] Failed: {e}")
        return -1

def keynote_get_text_boxes(env, s_idx):
    env.connect_ssh()

    keys = ["opacity", "parent", "class", "reflection showing", "background fill type", 
            "position", "object text", "width", "rotation", "reflection value", "height", "locked"]

    apple_script = f"""
    tell application "Keynote"
        tell front document
            tell slide {s_idx}
                set itemCount to count every text item
                return itemCount
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
        
        text_box_cnt = int(output)
        boxes = []
        
        for i in range(text_box_cnt):
            apple_script = f"""
            tell application "Keynote"
                tell front document
                    tell slide {s_idx}
                        tell text item {i+1}
                            return properties
                        end tell
                    end tell
                end tell
            end tell
            """
            stdout, stderr = env.run_command(
                f"osascript -e {shlex.quote(apple_script)}"
            )

            output = (
                stdout.read().decode().strip()
                if hasattr(stdout, "read")
                else stdout.strip()
            )
            boxes.append(parse_fixed_string(output, keys))

        return boxes

    except Exception as e:
        logger.error(f"[keynote_get_text_boxes] Failed: {e}")
        return []
    
def keynote_get_tables(env, s_idx):
    env.connect_ssh()

    apple_script = f"""
    tell application "Keynote"
        tell front document
            tell slide {s_idx}
                set itemCount to count every table
                return itemCount
            end tell
        end tell
    end tell
    """
    
    keys_table = [
        "column count", "width", "height", "row count"
    ]
    
    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        
        text_box_cnt = int(output)
        boxes = []
        
        for i in range(text_box_cnt):
            temp_dict = {}
            
            for key in keys_table:
                apple_script = f"""
                tell application "Keynote"
                    tell front document
                        tell slide {s_idx}
                            tell table {i+1}
                                return {key}
                            end tell
                        end tell
                    end tell
                end tell
                """
                stdout, stderr = env.run_command(
                    f"osascript -e {shlex.quote(apple_script)}"
                )

                output = (
                    stdout.read().decode().strip()
                    if hasattr(stdout, "read")
                    else stdout.strip()
                )
                temp_dict[key] = output
            
            boxes.append(temp_dict)

        return boxes

    except Exception as e:
        logger.error(f"[keynoet_get_tables] Failed: {e}")
        return []
    
def keynote_get_image_cnt(env, s_idx):
    env.connect_ssh()

    apple_script = f"""
    tell application "Keynote"
        tell front document
            tell slide {s_idx}
                set itemCount to count every image
                return itemCount
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
        
        image_cnt = int(output)

        return image_cnt

    except Exception as e:
        logger.error(f"[keynote_get_image_cnt] Failed: {e}")
        return 0
    
def keynote_get_image_property(env, s_idx, property, image_idx=1):
    env.connect_ssh()

    apple_script = f"""
    tell application "Keynote"
        tell front document
            tell slide {s_idx}
                tell image {image_idx}
                    return {property}
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
        
        return output

    except Exception as e:
        logger.error(f"[keynote_get_image_property] Failed: {e}")
        return ""

def keynote_get_table_val(env, s_idx, t_idx, row, col):
    env.connect_ssh()
    
    apple_script = f"""
    tell application "Keynote"
        tell front document
            tell slide {s_idx}
                tell table {t_idx}
                    tell row {row}
                        tell cell {col}
                            return value
                        end tell
                    end tell
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
        
        return output

    except Exception as e:
        logger.error(f"[keynote_get_image_property] Failed: {e}")
        return ""

def keynote_get_text_item_text_properties(env, s_idx, t_idx):
    env.connect_ssh()
    
    apple_script = f"""
    tell application "Keynote"
        tell front document
            tell slide {s_idx}
                tell text item {t_idx}
                    tell object text
                        return properties
                    end tell
                end tell
            end tell
        end tell
    end tell
    """
    keys = ['font', 'color', 'class', 'size']
    
    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        
        return parse_fixed_string(s=output, keys=keys)

    except Exception as e:
        logger.error(f"[keynote_get_text_item_text_properties] Failed: {e}")
        return []

def keynote_get_shape_properties(env, s_idx, sh_idx):
    env.connect_ssh()
    
    apple_script = f"""
    tell application "Keynote"
        tell front document
            tell slide {s_idx}
                tell shape {sh_idx}
                    return properties
                end tell
            end tell
        end tell
    end tell
    """
    keys = ['opacity', 'parent', 'class', 'reflection showing', 'background fill type', 
            'position', 'object text', 'width', 'rotation', 'reflection value', 'height', 'locked']
    
    try:
        stdout, stderr = env.run_command(
            f"osascript -e {shlex.quote(apple_script)}"
        )

        output = (
            stdout.read().decode().strip()
            if hasattr(stdout, "read")
            else stdout.strip()
        )
        
        return parse_fixed_string(s=output, keys=keys)

    except Exception as e:
        logger.error(f"[keynote_get_shape_properties] Failed: {e}")
        return []

def keynote_get_slide_skip(env, s_idx):
    env.connect_ssh()
    
    apple_script = f"""
    tell application "Keynote"
        tell front document
            tell slide {s_idx}
                return skipped
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
        
        return output == 'true'

    except Exception as e:
        logger.error(f"[keynote_get_slide_skip] Failed: {e}")
        return False
    
def keynote_get_slide_cnt(env):
    env.connect_ssh()
    
    apple_script = f"""
    tell application "Keynote"
        tell front document
            set slideCount to count every slide
            return slideCount
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
        
        return int(output)

    except Exception as e:
        logger.error(f"[keynote_get_slide_cnt] Failed: {e}")
        return 0

def keynote_test_doc_creation(env, template_name, doc_name):
    template_id = ""
    if template_name == "Basic Black":
        template_id = "Application/20_BasicBlack/Standard"
    if template_name == "Basic White":
        template_id = "Application/21_BasicWhite/Standard"
    if keynote_get_document_template(env=env) != template_id:
        return False
    actual_doc_name = strip_all_suffixes(keynote_get_document_name(env=env))
    expected_doc_name = strip_all_suffixes(doc_name)
    if actual_doc_name != expected_doc_name:
        return False
    return True

def keynote_test_item_delection(env, del_cnt):
    if keynote_get_slide_cnt(env=env) != 2:
        return False
    if keynote_get_text_box_cnt(env=env, s_idx=2) != 5 - del_cnt:
        print(keynote_get_text_box_cnt(env=env, s_idx=2))
        return False
    return True

def keynote_test_image_insertion(env, width, height, rotation, posx, posy):
    if width != None:
        if keynote_get_image_property(env=env, s_idx=1, property="width") != f"{width}":
            return False
    if height != None:
        if keynote_get_image_property(env=env, s_idx=1, property="height") != f"{height}":
            return False
    if rotation != None:
        if keynote_get_image_property(env=env, s_idx=1, property="rotation") != f"{rotation}":
            return False
    if posx != None:
        if keynote_get_image_property(env=env, s_idx=1, property="position").split(", ")[0] != f"{posx}":
            return False
    if posy != None:
        if keynote_get_image_property(env=env, s_idx=1, property="position").split(", ")[1] != f"{posy}":
            return False
    return True

def keynote_test_table_insertion(env, rows, cols, row, col, content):
    table = keynote_get_tables(env=env, s_idx=1)[0]
    print(table)
    if table['column count'] != f"{cols}":
        return False
    if table['row count'] != f"{rows}":
        return False
    if keynote_get_table_val(env=env, s_idx=1, t_idx=1, row=row, col=col) != content:
        print(keynote_get_table_val(env=env, s_idx=1, t_idx=1, row=row, col=col))
        return False
    return True

def keynote_test_text_box_insertion(env, color, content, font_size, font):
    text_style = keynote_get_text_item_text_properties(env=env, s_idx=1, t_idx=1)
    # TODO: check box idx
    text = keynote_get_text_boxes(env=env, s_idx=1)[0]
    rgb = tuple(int(x.strip()) for x in text_style['color'].split(","))
    if color.lower() == 'red':
        if not is_rbg_reddish(rgb8=rgb):
            return False
    if text['object text'] != content:
        return False
    if float(text_style['size']) != font_size:
        return False
    if text_style['font'] != f"{font}":
        return False
    return True

def keynote_test_shape_insertion(env, width, height, posx, posy):
    shape = keynote_get_shape_properties(env=env, s_idx=1, sh_idx=2)
    if width != None:
        if shape["width"] != f"{width}":
            return False
    if height != None:
        if shape["height"] != f"{height}":
            return False
    if posx != None:
        if shape["position"].split(", ")[0] != f"{posx}":
            return False
    if posy != None:
        if shape["position"].split(", ")[1] != f"{posy}":
            return False
    return True

def keynote_test_slide_insertion(env, insert_cnt, skip_idx):
    if keynote_get_slide_cnt(env=env) != insert_cnt+1:
        return False
    if not keynote_get_slide_skip(env=env, s_idx=skip_idx):
        return False
    return True

def keynote_test_shape_insertion_multi(env, width, height, pos1, pos2, pos3):
    shape1 = keynote_get_shape_properties(env=env, s_idx=1, sh_idx=2)
    shape2 = keynote_get_shape_properties(env=env, s_idx=1, sh_idx=3)
    shape3 = keynote_get_shape_properties(env=env, s_idx=1, sh_idx=4)
    
    if shape1["width"] != f"{width}":
        return False
    if shape2["width"] != f"{width}":
        return False
    if shape3["width"] != f"{width}":
        return False
    
    if shape1["height"] != f"{height}":
        return False
    if shape2["height"] != f"{height}":
        return False
    if shape3["height"] != f"{height}":
        return False
    
    if shape1["position"] != pos1:
        return False
    if shape2["position"] != pos2:
        return False
    if shape3["position"] != pos3:
        return False
    return True
