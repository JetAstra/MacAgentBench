import shlex
import re

from controllers.env import MacOSEnv


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


def _nonempty_unique_lines(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in text.splitlines():
        v = line.strip()
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def new_weather_check_file_contains_live_lines(
    env: MacOSEnv, output_file: str, expected_command: str, min_overlap: int
) -> bool:
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False

    try:
        required = int(min_overlap)
    except Exception:
        return False
    if required < 1:
        return False

    user_lines = _nonempty_unique_lines(output_text)
    live_text = _run_command(env, expected_command)
    live_lines = _nonempty_unique_lines(live_text)

    if not live_lines:
        return len(user_lines) == 0

    if len(user_lines) < required:
        return False

    overlap = len(set(user_lines) & set(live_lines))
    return overlap >= required


def new_weather_check_contains_live_current_values(
    env: MacOSEnv, output_file: str, expected_command: str
) -> bool:
    """
    Semantic check for current-weather tasks with fixed metric units:
    C (temperature), km/h (wind), % (humidity), mm (precipitation).
    """
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False

    live_text = _run_command(env, expected_command).strip()
    if not live_text:
        return len(_nonempty_unique_lines(output_text)) == 0

    def _to_float(s: str) -> float | None:
        try:
            return float(s)
        except Exception:
            return None

    def _parse_live(line: str) -> dict[str, float | str] | None:
        temp_m = re.search(r"temperature:([+-]?\d+(?:\.\d+)?)\s*°?\s*C", line)
        wind_m = re.search(r"wind:.*?([0-9]+(?:\.\d+)?)\s*(km/h|kph)", line)
        hum_m = re.search(r"humidity:([0-9]+(?:\.\d+)?)%", line)
        prec_m = re.search(r"precipitation:([0-9]+(?:\.\d+)?)\s*mm", line)
        if not (temp_m and wind_m and hum_m and prec_m):
            return None
        temp_v = _to_float(temp_m.group(1))
        wind_v = _to_float(wind_m.group(1))
        hum_v = _to_float(hum_m.group(1))
        prec_v = _to_float(prec_m.group(1))
        if None in (temp_v, wind_v, hum_v, prec_v):
            return None
        return {
            "temp_c": temp_v,
            "wind_kmh": wind_v,
            "humidity": hum_v,
            "prec_mm": prec_v,
        }

    def _parse_user(text: str) -> dict[str, float | str] | None:
        t = text
        temp_m = re.search(r"temp(?:erature)?[^0-9+-]*([+-]?\d+(?:\.\d+)?)\s*°?\s*C", t, re.I)
        if not temp_m:
            temp_m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*°\s*C", t, re.I)
        wind_m = re.search(r"wind[^0-9]*([0-9]+(?:\.\d+)?)\s*(km/h|kph)", t, re.I)
        hum_m = re.search(r"humidity[^0-9]*([0-9]+(?:\.\d+)?)\s*%", t, re.I)
        if not hum_m:
            hum_m = re.search(r"\b([0-9]{1,3}(?:\.\d+)?)\s*%[^\\n]*humid", t, re.I)
        prec_m = re.search(r"(?:precip(?:itation)?|rain)[^0-9]*([0-9]+(?:\.\d+)?)\s*mm\b", t, re.I)
        if not (temp_m and wind_m and hum_m and prec_m):
            return None
        temp_v = _to_float(temp_m.group(1))
        wind_v = _to_float(wind_m.group(1))
        hum_v = _to_float(hum_m.group(1))
        prec_v = _to_float(prec_m.group(1))
        if None in (temp_v, wind_v, hum_v, prec_v):
            return None
        return {
            "temp_c": temp_v,
            "wind_kmh": wind_v,
            "humidity": hum_v,
            "prec_mm": prec_v,
        }

    live = _parse_live(live_text.splitlines()[0])
    user = _parse_user(output_text)
    if not live or not user:
        return False

    if abs(user["temp_c"] - live["temp_c"]) > 2.0:
        return False
    if abs(user["wind_kmh"] - live["wind_kmh"]) > 5.0:
        return False
    if abs(user["humidity"] - live["humidity"]) > 10.0:
        return False
    if abs(user["prec_mm"] - live["prec_mm"]) > 0.5:
        return False
    return True


def new_weather_check_yes_no_matches_live(
    env: MacOSEnv, output_file: str, expected_command: str, output_key: str
) -> bool:
    """
    Compare yes/no result semantically (tolerant to spaces/case/extra text).
    """
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False

    expected_text = _run_command(env, expected_command).strip()
    if not expected_text:
        return len(_nonempty_unique_lines(output_text)) == 0

    def _extract_bool(text: str, key: str) -> str | None:
        key_re = re.escape(key)
        m = re.search(rf"{key_re}\s*:\s*(yes|no)\b", text, flags=re.I)
        if m:
            return m.group(1).lower()
        # Fallback: accept a standalone yes/no if user didn't keep the key.
        vals = re.findall(r"\b(yes|no)\b", text, flags=re.I)
        vals = [v.lower() for v in vals]
        if not vals:
            return None
        uniq = sorted(set(vals))
        if len(uniq) == 1:
            return uniq[0]
        return None

    expected_bool = _extract_bool(expected_text, output_key)
    user_bool = _extract_bool(output_text, output_key)
    if expected_bool is None or user_bool is None:
        return False
    return expected_bool == user_bool


def new_weather_check_rain_dates_exact(
    env: MacOSEnv, output_file: str, expected_command: str
) -> bool:
    """
    Strict set match for rain-date tasks.
    User output must exactly match expected dates (order-insensitive),
    or exactly `none` when no rainy day exists.
    """
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False

    expected_text = _run_command(env, expected_command).strip()

    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    def _parse_lines(text: str) -> tuple[set[str] | None, bool]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return set(), False
        lowered = [l.lower() for l in lines]
        has_none = "none" in lowered
        if has_none:
            # `none` cannot be mixed with other content.
            if len(lines) != 1 or lowered[0] != "none":
                return None, True
            return set(), True
        dates: set[str] = set()
        for line in lines:
            if not date_re.match(line):
                return None, False
            dates.add(line)
        return dates, False

    expected_dates, expected_is_none = _parse_lines(expected_text)
    user_dates, user_is_none = _parse_lines(output_text)
    if expected_dates is None or user_dates is None:
        return False

    if expected_is_none:
        return user_is_none and len(user_dates) == 0
    if user_is_none:
        return False
    return user_dates == expected_dates


def new_weather_check_temp_range_with_tolerance(
    env: MacOSEnv, output_file: str, expected_command: str, tolerance_c: float
) -> bool:
    """
    Semantic comparison for today's max/min temperatures with tolerance.
    """
    output_text = _read_remote_file(env, output_file)
    if output_text is None:
        return False

    expected_text = _run_command(env, expected_command).strip()
    if not expected_text:
        return False

    try:
        tol = float(tolerance_c)
    except Exception:
        return False
    if tol < 0:
        return False

    def _extract_pair(text: str) -> tuple[float, float] | None:
        max_m = re.search(r"max[^0-9-]*(-?\d+(?:\.\d+)?)\s*°?\s*C", text, flags=re.I)
        min_m = re.search(r"min[^0-9-]*(-?\d+(?:\.\d+)?)\s*°?\s*C", text, flags=re.I)
        if not (max_m and min_m):
            return None
        try:
            return float(max_m.group(1)), float(min_m.group(1))
        except Exception:
            return None

    expected_pair = _extract_pair(expected_text)
    user_pair = _extract_pair(output_text)
    if not expected_pair or not user_pair:
        return False

    exp_max, exp_min = expected_pair
    usr_max, usr_min = user_pair
    if abs(usr_max - exp_max) > tol:
        return False
    if abs(usr_min - exp_min) > tol:
        return False
    return True
