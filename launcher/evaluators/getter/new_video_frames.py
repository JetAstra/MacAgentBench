import shlex

from controllers.env import MacOSEnv
from utils.logger import ProjectLogger


logger = ProjectLogger().get()


def _run_command(env: MacOSEnv, command: str) -> str:
    env.connect_ssh()
    stdout, _ = env.run_command(command)
    return stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()


def _run_command_with_stderr(env: MacOSEnv, command: str) -> tuple[str, str]:
    env.connect_ssh()
    stdout, stderr = env.run_command(command)
    out = stdout.read().decode().strip() if hasattr(stdout, "read") else str(stdout).strip()
    err = stderr.read().decode().strip() if hasattr(stderr, "read") else str(stderr).strip()
    return out, err


def new_video_frames_check_first_frame_matches_expected(
    env: MacOSEnv, output_file: str, input_video: str
) -> bool:
    return _check_frame_like_expected(
        env,
        output_file=output_file,
        input_video=input_video,
        timestamp=None,
        width=None,
        height=None,
    )


def new_video_frames_check_timestamp_frame_matches_expected(
    env: MacOSEnv, output_file: str, input_video: str, timestamp: str
) -> bool:
    return _check_frame_like_expected(
        env,
        output_file=output_file,
        input_video=input_video,
        timestamp=timestamp,
        width=None,
        height=None,
    )


def new_video_frames_check_scaled_frame_matches_expected(
    env: MacOSEnv,
    output_file: str,
    input_video: str,
    timestamp: str,
    width: int,
    height: int,
) -> bool:
    return _check_frame_like_expected(
        env,
        output_file=output_file,
        input_video=input_video,
        timestamp=timestamp,
        width=width,
        height=height,
        preserve_size_for_compare=True,
    )


def _check_frame_like_expected(
    env: MacOSEnv,
    output_file: str,
    input_video: str,
    timestamp: str | None,
    width: int | None,
    height: int | None,
    preserve_size_for_compare: bool = False,
) -> bool:
    remote_py = f"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

output_file = os.path.expandvars(os.path.expanduser({output_file!r}))
input_video = os.path.expandvars(os.path.expanduser({input_video!r}))
timestamp = {timestamp!r}
width = {width!r}
height = {height!r}
preserve_size_for_compare = {preserve_size_for_compare!r}

output_path = Path(output_file)
input_path = Path(input_video)

if not output_path.exists() or not output_path.is_file() or output_path.stat().st_size <= 0:
    print("FAIL_OUTPUT_MISSING")
    raise SystemExit(0)
if not input_path.exists() or not input_path.is_file() or input_path.stat().st_size <= 0:
    print("FAIL_INPUT_MISSING")
    raise SystemExit(0)

suffix = output_path.suffix if output_path.suffix else ".png"
with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
    expected_path = Path(tf.name)

cmd_parts = ["ffmpeg", "-y"]
if timestamp:
    cmd_parts.extend(["-ss", timestamp])
cmd_parts.extend(["-i", str(input_path)])
if width is not None and height is not None:
    cmd_parts.extend(["-vf", f"scale={{int(width)}}:{{int(height)}}"])
cmd_parts.extend(["-frames:v", "1", str(expected_path)])

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
    a = ImageOps.exif_transpose(img_a).convert("L")
    b = ImageOps.exif_transpose(img_b).convert("L")
    if preserve_size_for_compare:
        if a.size != b.size:
            return 0.0
    else:
        a = a.resize((256, 256), Image.Resampling.BILINEAR)
        b = b.resize((256, 256), Image.Resampling.BILINEAR)
    pa = list(a.getdata())
    pb = list(b.getdata())
    mae = sum(abs(x - y) for x, y in zip(pa, pb)) / len(pa)
    return 1.0 - (mae / 255.0)

with Image.open(expected_path) as exp_img, Image.open(output_path) as out_img:
    sim = _mae_similarity(exp_img, out_img)
with Image.open(expected_path) as exp_img2, Image.open(output_path) as out_img2:
    dh = abs(_dhash(exp_img2) - _dhash(out_img2))

passed = (sim >= 0.995) and (dh <= 6)
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
    if len(lines) >= 3:
        logger.info(f"[new_video_frames] {lines[-3]}")
        logger.info(f"[new_video_frames] {lines[-2]}")
        return lines[-1] == "1"
    if len(lines) == 1 and lines[0].startswith("FAIL_"):
        logger.warning(f"[new_video_frames] {lines[0]}")
        if err:
            logger.warning(f"[new_video_frames] stderr: {err}")
        return False
    if output:
        logger.warning(f"[new_video_frames] unexpected stdout: {output}")
    if err:
        logger.warning(f"[new_video_frames] stderr: {err}")
    return False
