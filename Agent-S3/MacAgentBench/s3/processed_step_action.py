"""Annotate step screenshots from executed pyautogui action code; save under processed_step/."""

from __future__ import annotations

import ast
import os
import re
from io import BytesIO
from typing import List, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont


def _find_matching_paren(s: str, open_idx: int) -> int:
    """Index of closing paren matching '(' at open_idx."""
    depth = 0
    i = open_idx
    while i < len(s):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _first_call_inner(action: str, prefix: str) -> Optional[str]:
    """Return inner string of first ``prefix...`` call (balanced parens). ``prefix`` must end with ``(``."""
    start = action.find(prefix)
    if start < 0:
        return None
    open_paren = start + len(prefix) - 1
    if open_paren >= len(action) or action[open_paren] != "(":
        open_paren = action.find("(", start)
    if open_paren < 0:
        return None
    close_paren = _find_matching_paren(action, open_paren)
    if close_paren < 0:
        return None
    return action[open_paren + 1 : close_paren]


def _first_arg_from_call_inner(inner: str) -> str:
    """First top-level comma-separated argument (rough, good for write/hotkey)."""
    if not inner:
        return ""
    depth = 0
    for i, c in enumerate(inner):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            return inner[:i].strip()
    return inner.strip()


def _parse_write_preview(action: str) -> Optional[str]:
    inner = _first_call_inner(action, "pyautogui.write(")
    if inner is None:
        return None
    arg0 = _first_arg_from_call_inner(inner)
    if not arg0:
        return None
    try:
        v = ast.literal_eval(arg0)
        if isinstance(v, str):
            t = v.replace("\n", "\\n")
            return t if len(t) <= 200 else t[:197] + "..."
        return str(v)[:200]
    except (ValueError, SyntaxError):
        return arg0[:200]


def _parse_hotkey_preview(action: str) -> Optional[str]:
    inner = _first_call_inner(action, "pyautogui.hotkey(")
    if inner is None:
        return None
    return inner.strip()[:300]


def _parse_pyperclip_preview(action: str) -> Optional[str]:
    inner = _first_call_inner(action, "pyperclip.copy(")
    if inner is None:
        return None
    arg0 = _first_arg_from_call_inner(inner)
    if not arg0:
        return None
    try:
        v = ast.literal_eval(arg0)
        if isinstance(v, str):
            t = v.replace("\n", "\\n")
            return t if len(t) <= 200 else t[:197] + "..."
        return str(v)[:200]
    except (ValueError, SyntaxError):
        return arg0[:200]


def _parse_all_clicks(action: str) -> List[Tuple[int, int, str]]:
    """(x, y, button) for each ``pyautogui.click(...)``."""
    out: List[Tuple[int, int, str]] = []
    pat = re.compile(
        r"pyautogui\.click\s*\(\s*(\d+)\s*,\s*(\d+)([^)]*)\)", re.DOTALL
    )
    for m in pat.finditer(action):
        x, y, rest = int(m.group(1)), int(m.group(2)), m.group(3)
        btn_m = re.search(r"button\s*=\s*['\"](\w+)['\"]", rest)
        button = btn_m.group(1) if btn_m else "left"
        out.append((x, y, button))
    return out


def _get_font(size: int = 20) -> Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]:
    candidates = []
    if os.name == "nt":
        candidates = [
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "msyh.ttc"),
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "arial.ttf"),
        ]
    else:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    for p in candidates:
        if p and os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_label(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: Tuple[int, int, int, int] = (255, 0, 0, 255),
    outline: Tuple[int, int, int, int] = (255, 255, 255, 255),
) -> None:
    x, y = xy
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def _wrap_text(text: str, max_chars: int = 60) -> List[str]:
    lines: List[str] = []
    for raw in text.split("\n"):
        while len(raw) > max_chars:
            lines.append(raw[:max_chars])
            raw = raw[max_chars:]
        if raw:
            lines.append(raw)
    return lines[:12]


def annotate_screenshot_for_action(screenshot_bytes: bytes, action: str) -> bytes:
    """
    Draw click markers / type or hotkey captions / or full action text on a copy of the screenshot.
    Returns PNG bytes.
    """
    img = Image.open(BytesIO(screenshot_bytes)).convert("RGBA")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    font = _get_font(18)
    font_small = _get_font(16)

    clicks = _parse_all_clicks(action)
    write_preview = _parse_write_preview(action)
    clip_preview = _parse_pyperclip_preview(action)
    hotkey_preview = _parse_hotkey_preview(action)

    radius = max(10, min(w, h) // 100)

    for x, y, button in clicks:
        x = max(0, min(w - 1, x))
        y = max(0, min(h - 1, y))
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            outline=(255, 0, 0, 255),
            width=max(2, radius // 5),
        )
        draw.line(
            (x - radius * 2, y, x + radius * 2, y),
            fill=(255, 0, 0, 255),
            width=max(2, radius // 6),
        )
        draw.line(
            (x, y - radius * 2, x, y + radius * 2),
            fill=(255, 0, 0, 255),
            width=max(2, radius // 6),
        )
        label = f"{button}"
        _draw_label(draw, (x + radius + 4, y - radius - 4), label, font_small)

    footer_lines: List[str] = []

    if write_preview is not None:
        footer_lines.append(f"type: {write_preview}")
    elif clip_preview is not None:
        footer_lines.append(f"type: {clip_preview}")
    if hotkey_preview is not None:
        footer_lines.append(f"hotkey: {hotkey_preview}")

    if not clicks and not footer_lines:
        snippet = action.strip().replace("\n", " ")
        if len(snippet) > 500:
            snippet = snippet[:497] + "..."
        footer_lines.append(f"action: {snippet}")

    if footer_lines:
        margin = 8
        line_h = 22
        pad = 10
        text_block = "\n".join(_wrap_text("\n".join(footer_lines), max_chars=80))
        wrapped = text_block.split("\n")
        box_h = min(h // 2, len(wrapped) * line_h + pad * 2)
        overlay = Image.new("RGBA", (w, box_h), (0, 0, 0, 180))
        img.paste(overlay, (0, h - box_h), overlay)
        ty = h - box_h + pad
        for line in wrapped:
            draw.text((margin, ty), line, font=font, fill=(255, 255, 255, 255))
            ty += line_h

    out = BytesIO()
    img.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def save_processed_step_image(
    example_result_dir: str,
    step_num: int,
    action_timestamp: str,
    screenshot_bytes: bytes,
    action: str,
) -> str:
    """Write annotated PNG under ``example_result_dir/processed_step/``. Returns path."""
    proc_dir = os.path.join(example_result_dir, "processed_step")
    os.makedirs(proc_dir, exist_ok=True)
    out_path = os.path.join(
        proc_dir, f"step_{step_num}_{action_timestamp}.png"
    )
    data = annotate_screenshot_for_action(screenshot_bytes, action)
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path
