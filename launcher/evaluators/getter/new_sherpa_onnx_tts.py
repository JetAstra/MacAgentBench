import json
import shlex

from controllers.env import MacOSEnv
from utils.logger import ProjectLogger


logger = ProjectLogger().get()


def _run_command(env: MacOSEnv, command: str) -> str:
    env.connect_ssh()
    stdout, _ = env.run_command(command)
    return stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()


def new_sherpa_onnx_tts_check_wav_properties(
    env: MacOSEnv,
    output_file: str,
    min_duration_seconds: float,
    max_duration_seconds: float,
    min_size_bytes: int,
) -> bool:
    remote_py = f"""
from pathlib import Path
import json
import os
import wave

path = os.path.expandvars(os.path.expanduser({output_file!r}))
file_path = Path(path)
if not file_path.exists():
    print(json.dumps({{"exists": False}}))
else:
    payload = {{"exists": True, "size": file_path.stat().st_size}}
    try:
        with wave.open(str(file_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            sampwidth = wav_file.getsampwidth()
            duration = (frames / rate) if rate else 0.0
            payload.update({{
                "valid_wav": True,
                "frames": frames,
                "rate": rate,
                "channels": channels,
                "sampwidth": sampwidth,
                "duration": duration,
            }})
    except Exception as exc:
        payload.update({{"valid_wav": False, "error": str(exc)}})
    print(json.dumps(payload))
"""
    safe_code = shlex.quote(remote_py.strip())
    output = _run_command(env, f"python3 -c {safe_code}")
    try:
        payload = json.loads(output)
    except Exception as exc:
        logger.error(f"Failed to parse WAV metadata for {output_file}: {exc}")
        return False

    if not payload.get("exists"):
        logger.error(f"WAV output file not found: {output_file}")
        return False
    if payload.get("size", 0) < int(min_size_bytes):
        logger.error(
            f"WAV output too small: {payload.get('size')} < {min_size_bytes} ({output_file})"
        )
        return False
    if not payload.get("valid_wav"):
        logger.error(f"Invalid WAV output for {output_file}: {payload!r}")
        return False

    duration = float(payload.get("duration", 0.0))
    if duration < float(min_duration_seconds) or duration > float(max_duration_seconds):
        logger.error(
            f"WAV duration out of range for {output_file}: {duration} "
            f"not in [{min_duration_seconds}, {max_duration_seconds}]"
        )
        return False

    if int(payload.get("channels", 0)) <= 0 or int(payload.get("rate", 0)) <= 0:
        logger.error(f"Invalid WAV metadata for {output_file}: {payload!r}")
        return False

    return True
