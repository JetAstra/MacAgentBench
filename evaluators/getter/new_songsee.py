import shlex

from controllers.env import MacOSEnv
from utils.logger import ProjectLogger


logger = ProjectLogger().get()


def _run_command_with_stderr(env: MacOSEnv, command: str) -> tuple[str, str]:
    env.connect_ssh()
    stdout, stderr = env.run_command(command)
    out = stdout.read().decode().strip() if hasattr(stdout, "read") else str(stdout).strip()
    err = stderr.read().decode().strip() if hasattr(stderr, "read") else str(stderr).strip()
    return out, err


def new_songsee_check_render_matches_expected(
    env: MacOSEnv,
    output_file: str,
    input_audio: str,
    image_format: str | None = None,
    viz_list: str | None = None,
    start_seconds: str | None = None,
    duration_seconds: str | None = None,
    style: str | None = None,
    width: int | None = None,
    height: int | None = None,
    window: int | None = None,
    hop: int | None = None,
    min_freq: int | None = None,
    max_freq: int | None = None,
) -> bool:
    remote_py = f"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

output_file = os.path.expandvars(os.path.expanduser({output_file!r}))
input_audio = os.path.expandvars(os.path.expanduser({input_audio!r}))
image_format = {image_format!r}
viz_list = {viz_list!r}
start_seconds = {start_seconds!r}
duration_seconds = {duration_seconds!r}
style = {style!r}
width = {width!r}
height = {height!r}
window = {window!r}
hop = {hop!r}
min_freq = {min_freq!r}
max_freq = {max_freq!r}

output_path = Path(output_file)
input_path = Path(input_audio)

if not output_path.exists() or not output_path.is_file() or output_path.stat().st_size <= 0:
    print("FAIL_OUTPUT_MISSING")
    raise SystemExit(0)
if not input_path.exists() or not input_path.is_file() or input_path.stat().st_size <= 0:
    print("FAIL_INPUT_MISSING")
    raise SystemExit(0)

suffix = output_path.suffix if output_path.suffix else ".png"
with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
    expected_path = Path(tf.name)

cmd_parts = ["songsee", str(input_path)]
if viz_list:
    cmd_parts.extend(["--viz", str(viz_list)])
if start_seconds is not None:
    cmd_parts.extend(["--start", str(start_seconds)])
if duration_seconds is not None:
    cmd_parts.extend(["--duration", str(duration_seconds)])
if style:
    cmd_parts.extend(["--style", str(style)])
if width is not None:
    cmd_parts.extend(["--width", str(width)])
if height is not None:
    cmd_parts.extend(["--height", str(height)])
if window is not None:
    cmd_parts.extend(["--window", str(window)])
if hop is not None:
    cmd_parts.extend(["--hop", str(hop)])
if min_freq is not None:
    cmd_parts.extend(["--min-freq", str(min_freq)])
if max_freq is not None:
    cmd_parts.extend(["--max-freq", str(max_freq)])
if image_format:
    cmd_parts.extend(["--format", str(image_format)])
cmd_parts.extend(["-o", str(expected_path)])

proc = subprocess.run(
    cmd_parts,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
if proc.returncode != 0 or not expected_path.exists() or expected_path.stat().st_size <= 0:
    print("FAIL_EXPECTED_BUILD")
    try:
        expected_path.unlink(missing_ok=True)
    except Exception:
        pass
    raise SystemExit(0)

try:
    from PIL import Image, ImageOps
except Exception:
    print("FAIL_PIL_IMPORT")
    try:
        expected_path.unlink(missing_ok=True)
    except Exception:
        pass
    raise SystemExit(0)

def _dhash(img, size=8):
    img = ImageOps.exif_transpose(img).convert("L").resize((size + 1, size), Image.Resampling.BILINEAR)
    px = list(img.getdata())
    dist = 0
    row_w = size + 1
    for y in range(size):
        row = y * row_w
        for x in range(size):
            if px[row + x] > px[row + x + 1]:
                dist += 1
    return dist

def _mae_similarity(img_a, img_b):
    a = ImageOps.exif_transpose(img_a).convert("L").resize((256, 256), Image.Resampling.BILINEAR)
    b = ImageOps.exif_transpose(img_b).convert("L").resize((256, 256), Image.Resampling.BILINEAR)
    pa = list(a.getdata())
    pb = list(b.getdata())
    mae = sum(abs(x - y) for x, y in zip(pa, pb)) / len(pa)
    return 1.0 - (mae / 255.0)

with Image.open(expected_path) as exp_img_raw:
    expected_format_detected = (exp_img_raw.format or "").lower()
    exp_img = ImageOps.exif_transpose(exp_img_raw)
    expected_size = exp_img.size
    expected_mode = exp_img.mode

with Image.open(output_path) as out_img_raw:
    actual_format = (out_img_raw.format or "").lower()
    out_img = ImageOps.exif_transpose(out_img_raw)
    actual_size = out_img.size
    actual_mode = out_img.mode

expected_format = (image_format or output_path.suffix.lstrip(".") or "").lower()
if expected_format == "jpg":
    expected_format = "jpeg"

if expected_format and actual_format != expected_format:
    print("FAIL_FORMAT_MISMATCH")
    print(f"expected_format={{expected_format}}")
    print(f"actual_format={{actual_format}}")
    try:
        expected_path.unlink(missing_ok=True)
    except Exception:
        pass
    raise SystemExit(0)

if width is not None and height is not None and actual_size != (int(width), int(height)):
    print("FAIL_SIZE_MISMATCH")
    print(f"expected_size={{int(width)}}x{{int(height)}}")
    print(f"actual_size={{actual_size[0]}}x{{actual_size[1]}}")
    try:
        expected_path.unlink(missing_ok=True)
    except Exception:
        pass
    raise SystemExit(0)

if actual_size != expected_size:
    print("FAIL_EXPECTED_SIZE_MISMATCH")
    print(f"expected_render_size={{expected_size[0]}}x{{expected_size[1]}}")
    print(f"actual_size={{actual_size[0]}}x{{actual_size[1]}}")
    try:
        expected_path.unlink(missing_ok=True)
    except Exception:
        pass
    raise SystemExit(0)

with Image.open(expected_path) as exp_img, Image.open(output_path) as out_img:
    sim = _mae_similarity(exp_img, out_img)
with Image.open(expected_path) as exp_img2, Image.open(output_path) as out_img2:
    dh = abs(_dhash(exp_img2) - _dhash(out_img2))

passed = (sim >= 0.995) and (dh <= 6)
print(f"expected_mode={{expected_mode}}")
print(f"actual_mode={{actual_mode}}")
print(f"sim={{sim:.6f}}")
print(f"dhash_distance={{dh}}")
print("1" if passed else "0")

try:
    expected_path.unlink(missing_ok=True)
except Exception:
    pass
"""
    safe_code = shlex.quote(remote_py.strip())
    output, err = _run_command_with_stderr(env, f"python3 -c {safe_code}")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) >= 5:
        logger.info(f"[new_songsee] {lines[-5]}")
        logger.info(f"[new_songsee] {lines[-4]}")
        logger.info(f"[new_songsee] {lines[-3]}")
        logger.info(f"[new_songsee] {lines[-2]}")
        return lines[-1] == "1"
    if lines and lines[0].startswith("FAIL_"):
        for line in lines:
            logger.warning(f"[new_songsee] {line}")
        if err:
            logger.warning(f"[new_songsee] stderr: {err}")
        return False
    if output:
        logger.warning(f"[new_songsee] unexpected stdout: {output}")
    if err:
        logger.warning(f"[new_songsee] stderr: {err}")
    return False
