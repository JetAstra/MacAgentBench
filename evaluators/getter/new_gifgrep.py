import shlex
from urllib.parse import urlparse

from controllers.env import MacOSEnv
from utils.logger import ProjectLogger


logger = ProjectLogger().get()


def _run_command(env: MacOSEnv, command: str) -> str:
    env.connect_ssh()
    stdout, _ = env.run_command(command)
    return stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()


def _read_remote_file(env: MacOSEnv, path_expr: str) -> str | None:
    remote_py = f"""
from pathlib import Path
import os

path = os.path.expandvars(os.path.expanduser({path_expr!r}))
p = Path(path)
if not p.exists():
    print("__MISSING__")
else:
    print(p.read_text(encoding="utf-8", errors="replace"))
"""
    safe_code = shlex.quote(remote_py.strip())
    output = _run_command(env, f"python3 -c {safe_code}")
    if output == "__MISSING__":
        return None
    return output


def _remote_file_exists_nonempty(env: MacOSEnv, path_expr: str) -> bool:
    remote_py = f"""
from pathlib import Path
import os

path = os.path.expandvars(os.path.expanduser({path_expr!r}))
p = Path(path)
print("1" if p.exists() and p.is_file() and p.stat().st_size > 0 else "0")
"""
    safe_code = shlex.quote(remote_py.strip())
    output = _run_command(env, f"python3 -c {safe_code}")
    return output == "1"


def _remote_file_is_png(env: MacOSEnv, path_expr: str) -> bool:
    remote_py = f"""
from pathlib import Path
import os

path = os.path.expandvars(os.path.expanduser({path_expr!r}))
p = Path(path)
if not p.exists() or not p.is_file() or p.stat().st_size <= 8:
    print("0")
else:
    with p.open("rb") as f:
        header = f.read(8)
    print("1" if header == b"\\x89PNG\\r\\n\\x1a\\n" else "0")
"""
    safe_code = shlex.quote(remote_py.strip())
    output = _run_command(env, f"python3 -c {safe_code}")
    return output == "1"


def _remote_file_is_gif(env: MacOSEnv, path_expr: str) -> bool:
    remote_py = f"""
from pathlib import Path
import os

path = os.path.expandvars(os.path.expanduser({path_expr!r}))
p = Path(path)
if not p.exists() or not p.is_file() or p.stat().st_size <= 6:
    print("0")
else:
    with p.open("rb") as f:
        header = f.read(6)
    print("1" if header in (b"GIF87a", b"GIF89a") else "0")
"""
    safe_code = shlex.quote(remote_py.strip())
    output = _run_command(env, f"python3 -c {safe_code}")
    return output == "1"


def _is_http_url(text: str) -> bool:
    try:
        parsed = urlparse(text.strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _unique_http_urls_from_text(content: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for line in content.splitlines():
        candidate = line.strip()
        if not candidate or not _is_http_url(candidate) or candidate in seen:
            continue
        seen.add(candidate)
        urls.append(candidate)
    return urls


def _run_gifgrep_urls(env: MacOSEnv, query: str, source: str) -> list[str]:
    safe_query = shlex.quote(query)
    safe_source = shlex.quote(source)
    output = _run_command(
        env,
        f"gifgrep {safe_query} --source {safe_source} --format url",
    )
    return _unique_http_urls_from_text(output)


def new_gifgrep_check_url_file_has_min_lines(
    env: MacOSEnv,
    output_file: str,
    min_lines: int,
    query: str,
    source: str,
    min_overlap: int,
) -> bool:
    """
    Check output URL file format and overlap with live gifgrep results.
    """
    content = _read_remote_file(env, output_file)
    if content is None:
        return False

    try:
        min_count = int(min_lines)
        overlap_required = int(min_overlap)
    except Exception:
        return False

    if min_count < 1 or overlap_required < 1:
        return False

    user_urls = _unique_http_urls_from_text(content)
    if len(user_urls) < min_count:
        return False

    expected_urls = _run_gifgrep_urls(env, query=query, source=source)
    if not expected_urls:
        return False

    overlap = len(set(user_urls) & set(expected_urls))
    return overlap >= overlap_required


def new_gifgrep_check_file_exists_nonempty(env: MacOSEnv, output_file: str) -> bool:
    """
    Check that a downloaded file exists and is non-empty.
    """
    return _remote_file_exists_nonempty(env, output_file)


def new_gifgrep_check_download_matches_first_result(
    env: MacOSEnv, output_file: str, query: str, source: str
) -> bool:
    """
    Check that output_file is a GIF and matches the hash of the first current search URL.
    """
    if not _remote_file_exists_nonempty(env, output_file):
        return False
    if not _remote_file_is_gif(env, output_file):
        return False

    remote_py = f"""
from pathlib import Path
import hashlib
import os
import shlex
import subprocess
import urllib.request

path = os.path.expandvars(os.path.expanduser({output_file!r}))
query = {query!r}
source = {source!r}
output_path = Path(path)

if not output_path.exists() or not output_path.is_file() or output_path.stat().st_size <= 0:
    print("0")
    raise SystemExit(0)

cmd = (
    f"gifgrep {{shlex.quote(query)}} --source {{shlex.quote(source)}} --format url | head -n 1"
)
first_url = subprocess.check_output(
    ["/bin/zsh", "-lc", cmd],
    text=True,
    stderr=subprocess.DEVNULL,
).strip()
if not first_url.startswith("http://") and not first_url.startswith("https://"):
    print("0")
    raise SystemExit(0)

req = urllib.request.Request(first_url, headers={{"User-Agent": "Mozilla/5.0"}})
with urllib.request.urlopen(req, timeout=30) as response:
    expected_bytes = response.read()

if not expected_bytes:
    print("0")
    raise SystemExit(0)

actual_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
expected_sha256 = hashlib.sha256(expected_bytes).hexdigest()
print(first_url)
print(expected_sha256)
print(actual_sha256)
print("1" if actual_sha256 == expected_sha256 else "0")
"""
    safe_code = shlex.quote(remote_py.strip())
    output = _run_command(env, f"python3 -c {safe_code}")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) >= 4:
        first_url = lines[-4]
        expected_sha256 = lines[-3]
        actual_sha256 = lines[-2]
        verdict = lines[-1]
        logger.info(f"[new_gifgrep] first_url={first_url}")
        logger.info(f"[new_gifgrep] expected_sha256={expected_sha256}")
        logger.info(f"[new_gifgrep] actual_sha256={actual_sha256}")
        return verdict == "1"
    return False


def new_gifgrep_check_still_matches_expected_hash(
    env: MacOSEnv, output_file: str, input_gif_path: str, at_time: str
) -> bool:
    """
    Check that still output is perceptually similar to expected image
    generated with the same args.
    """
    if not _remote_file_exists_nonempty(env, output_file):
        return False
    if not _remote_file_is_png(env, output_file):
        return False

    remote_py = f"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

output_file = os.path.expandvars(os.path.expanduser({output_file!r}))
input_gif_path = os.path.expandvars(os.path.expanduser({input_gif_path!r}))
at_time = {at_time!r}

output_path = Path(output_file)
input_path = Path(input_gif_path)

if not output_path.exists() or not output_path.is_file() or output_path.stat().st_size <= 0:
    print("0")
    raise SystemExit(0)
if not input_path.exists() or not input_path.is_file() or input_path.stat().st_size <= 0:
    print("0")
    raise SystemExit(0)

with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
    expected_path = Path(tf.name)

cmd = (
    f"gifgrep still {{shlex.quote(str(input_path))}} --at {{shlex.quote(at_time)}} "
    f"-o {{shlex.quote(str(expected_path))}}"
)
proc = subprocess.run(
    ["/bin/zsh", "-lc", cmd],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
if proc.returncode != 0 or not expected_path.exists() or expected_path.stat().st_size <= 0:
    print("0")
    try:
        expected_path.unlink(missing_ok=True)
    except Exception:
        pass
    raise SystemExit(0)

try:
    from PIL import Image, ImageOps
except Exception:
    print("0")
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

with Image.open(expected_path) as exp_img, Image.open(output_path) as out_img:
    sim = _mae_similarity(exp_img, out_img)
with Image.open(expected_path) as exp_img2, Image.open(output_path) as out_img2:
    dh = abs(_dhash(exp_img2) - _dhash(out_img2))

passed = (sim >= 0.98) and (dh <= 12)
print(f"sim={{sim:.6f}}")
print(f"dhash_distance={{dh}}")
print("1" if passed else "0")

try:
    expected_path.unlink(missing_ok=True)
except Exception:
    pass
"""
    safe_code = shlex.quote(remote_py.strip())
    output = _run_command(env, f"python3 -c {safe_code}")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) >= 3:
        sim_line = lines[-3]
        dh_line = lines[-2]
        verdict = lines[-1]
        logger.info(f"[new_gifgrep][still] {sim_line}")
        logger.info(f"[new_gifgrep][still] {dh_line}")
        return verdict == "1"
    return False


def new_gifgrep_check_sheet_matches_expected_hash(
    env: MacOSEnv, output_file: str, input_gif_path: str, frames: int, cols: int
) -> bool:
    """
    Check that sheet output is perceptually similar to expected image
    generated with the same args.
    """
    if not _remote_file_exists_nonempty(env, output_file):
        return False
    if not _remote_file_is_png(env, output_file):
        return False

    remote_py = f"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

output_file = os.path.expandvars(os.path.expanduser({output_file!r}))
input_gif_path = os.path.expandvars(os.path.expanduser({input_gif_path!r}))
frames = int({frames!r})
cols = int({cols!r})

output_path = Path(output_file)
input_path = Path(input_gif_path)

if not output_path.exists() or not output_path.is_file() or output_path.stat().st_size <= 0:
    print("0")
    raise SystemExit(0)
if not input_path.exists() or not input_path.is_file() or input_path.stat().st_size <= 0:
    print("0")
    raise SystemExit(0)
if frames <= 0 or cols <= 0:
    print("0")
    raise SystemExit(0)

with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
    expected_path = Path(tf.name)

cmd = (
    f"gifgrep sheet {{shlex.quote(str(input_path))}} "
    f"--frames {{frames}} --cols {{cols}} -o {{shlex.quote(str(expected_path))}}"
)
proc = subprocess.run(
    ["/bin/zsh", "-lc", cmd],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
if proc.returncode != 0 or not expected_path.exists() or expected_path.stat().st_size <= 0:
    print("0")
    try:
        expected_path.unlink(missing_ok=True)
    except Exception:
        pass
    raise SystemExit(0)

try:
    from PIL import Image, ImageOps
except Exception:
    print("0")
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

with Image.open(expected_path) as exp_img, Image.open(output_path) as out_img:
    sim = _mae_similarity(exp_img, out_img)
with Image.open(expected_path) as exp_img2, Image.open(output_path) as out_img2:
    dh = abs(_dhash(exp_img2) - _dhash(out_img2))

passed = (sim >= 0.98) and (dh <= 12)
print(f"sim={{sim:.6f}}")
print(f"dhash_distance={{dh}}")
print("1" if passed else "0")

try:
    expected_path.unlink(missing_ok=True)
except Exception:
    pass
"""
    safe_code = shlex.quote(remote_py.strip())
    output = _run_command(env, f"python3 -c {safe_code}")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) >= 3:
        sim_line = lines[-3]
        dh_line = lines[-2]
        verdict = lines[-1]
        logger.info(f"[new_gifgrep][sheet] {sim_line}")
        logger.info(f"[new_gifgrep][sheet] {dh_line}")
        return verdict == "1"
    return False


def new_gifgrep_check_png_exists_nonempty(env: MacOSEnv, output_file: str) -> bool:
    """
    Check that output file exists, is non-empty, and has PNG signature.
    """
    return _remote_file_is_png(env, output_file)


def new_gifgrep_check_sheet_exists_nonempty(env: MacOSEnv, output_file: str) -> bool:
    """
    Check that sheet output exists, is non-empty, and has PNG signature.
    """
    return _remote_file_is_png(env, output_file)
