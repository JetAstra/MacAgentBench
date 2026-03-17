import json
import shlex
import datetime
from dateutil import tz
from zoneinfo import ZoneInfo

from controllers.env import MacOSEnv
from utils.logger import ProjectLogger


logger = ProjectLogger().get()


def _run_command(env: MacOSEnv, command: str) -> str:
    env.connect_ssh()
    stdout, _ = env.run_command(command)
    return stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()


def _run_remindctl(env: MacOSEnv, args: str) -> str:
    """
    Run remindctl and return stdout.
    Prefer remindctl for new_reminders evaluators.
    """
    return _run_command(env, f"remindctl {args}")


def _get_remote_timezone(env: MacOSEnv):
    """
    Best-effort fetch of the evaluated macOS timezone.
    """
    tz_name = _run_command(
        env,
        r"""python3 -c 'from zoneinfo import ZoneInfo; import os; print(os.environ.get("TZ", "") or ZoneInfo("localtime").key)'""",
    )
    if not tz_name:
        return None
    try:
        return ZoneInfo(tz_name.strip())
    except Exception:
        logger.error(f"Failed to load remote timezone: {tz_name}")
        return None


def _run_osascript(env: MacOSEnv, script: str) -> str:
    """
    AppleScript fallback helper for cases remindctl cannot cover.
    """
    safe_code = shlex.quote(script.strip())
    return _run_command(env, f"osascript -e {safe_code}")


def _read_remote_file(env: MacOSEnv, output_file: str) -> str | None:
    remote_py = f"""
from pathlib import Path
import os

path = os.path.expandvars(os.path.expanduser({output_file!r}))
file_path = Path(path)
if not file_path.exists():
    print("__MISSING__")
else:
    print(file_path.read_text(encoding="utf-8", errors="replace"))
"""
    safe_code = shlex.quote(remote_py.strip())
    content = _run_command(env, f"python3 -c {safe_code}")
    if content == "__MISSING__":
        logger.error(f"Output file not found: {output_file}")
        return None
    return content


def _parse_remindctl_json(output: str):
    try:
        return json.loads(output)
    except Exception as exc:
        logger.error(f"Failed to parse remindctl JSON output: {exc}")
        return None


def _parse_plain_titles(output: str) -> list[str]:
    """
    Parse titles from remindctl --plain output (TSV).
    Best-effort parser: returns the first non-empty field per line.
    """
    titles = []
    for line in output.splitlines():
        row = line.strip()
        if not row:
            continue
        fields = [part.strip() for part in row.split("\t")]
        first = next((f for f in fields if f), "")
        if first:
            titles.append(first)
    return titles


def _collect_candidate_titles(value) -> list[str]:
    """
    Recursively collect likely title/name strings from remindctl JSON payload.
    """
    collected = []
    if isinstance(value, dict):
        for key, val in value.items():
            if key in {"title", "name"} and isinstance(val, str):
                collected.append(val)
            collected.extend(_collect_candidate_titles(val))
    elif isinstance(value, list):
        for item in value:
            collected.extend(_collect_candidate_titles(item))
    return collected


def _collect_reminder_entries(value) -> list[dict]:
    """
    Recursively collect reminder-like entries with title and due fields
    from remindctl JSON payload.
    """
    entries = []
    if isinstance(value, dict):
        title = None
        if isinstance(value.get("title"), str):
            title = value.get("title")
        elif isinstance(value.get("name"), str):
            title = value.get("name")

        if title:
            due_value = None
            for key in (
                "due",
                "dueDate",
                "due_date",
                "dueAt",
                "due_at",
                "remindAt",
                "remind_at",
            ):
                if key in value and value[key] not in (None, ""):
                    due_value = value[key]
                    break
            list_name = None
            for key in ("listName", "list_name", "list"):
                if isinstance(value.get(key), str):
                    list_name = value.get(key)
                    break
            is_completed = None
            for key in ("isCompleted", "completed", "is_done", "done"):
                if isinstance(value.get(key), bool):
                    is_completed = value.get(key)
                    break
            entries.append(
                {
                    "title": title,
                    "due": due_value,
                    "list_name": list_name,
                    "is_completed": is_completed,
                }
            )

        for item in value.values():
            entries.extend(_collect_reminder_entries(item))
    elif isinstance(value, list):
        for item in value:
            entries.extend(_collect_reminder_entries(item))
    return entries


def _parse_datetime_maybe(value):
    if value in (None, ""):
        return None
    try:
        if isinstance(value, dict):
            # Best effort for structured datetime payloads.
            for key in ("date", "datetime", "value", "iso", "raw"):
                if key in value:
                    parsed = _parse_datetime_maybe(value[key])
                    if parsed is not None:
                        return parsed
            return None
        if isinstance(value, (int, float)):
            return datetime.datetime.fromtimestamp(value)
        text = str(value).strip()
        if text.isdigit():
            return datetime.datetime.fromtimestamp(int(text))
        from dateutil import parser as dateparser

        return dateparser.parse(text)
    except Exception:
        return None


def _to_local_minute_tuple(dt: datetime.datetime, local_tz=None):
    local_tz = local_tz or tz.tzlocal()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz)
    else:
        dt = dt.astimezone(local_tz)
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute)


def new_reminders_check_reminder_exists(env: MacOSEnv, title: str) -> bool:
    """
    Check whether a reminder with exact title exists.
    Prefer remindctl JSON output; fallback to --plain parsing.
    """
    json_output = _run_remindctl(env, "all --json")
    payload = _parse_remindctl_json(json_output)
    if payload is not None:
        titles = _collect_candidate_titles(payload)
        if title in titles:
            return True

    plain_output = _run_remindctl(env, "all --plain")
    titles_plain = _parse_plain_titles(plain_output)
    return title in titles_plain


def new_reminders_check_reminder_due_datetime(
    env: MacOSEnv, title: str, due_datetime: str
) -> bool:
    """
    Check whether a reminder exists with exact title and due datetime.
    Uses remindctl JSON output.
    """
    expected = _parse_datetime_maybe(due_datetime)
    if expected is None:
        logger.error(f"Invalid expected due_datetime: {due_datetime}")
        return False
    compare_tz = _get_remote_timezone(env) or tz.tzlocal()
    logger.info(
        f"[new_reminders_due_datetime] expected_raw={due_datetime} "
        f"expected_parsed={expected!r} expected_tuple={_to_local_minute_tuple(expected, compare_tz)}"
    )

    json_output = _run_remindctl(env, "all --json")
    payload = _parse_remindctl_json(json_output)
    if payload is None:
        logger.error("[new_reminders_due_datetime] remindctl JSON payload is None.")
        return False

    entries = _collect_reminder_entries(payload)
    logger.info(
        f"[new_reminders_due_datetime] collected_entries={len(entries)}"
    )
    matched = [entry for entry in entries if entry.get("title") == title]
    logger.info(
        f"[new_reminders_due_datetime] title={title!r} matched_entries={len(matched)} "
        f"matched_due_values={[entry.get('due') for entry in matched]!r}"
    )
    if not matched:
        return False

    expected_tuple = _to_local_minute_tuple(expected, compare_tz)
    for idx, entry in enumerate(matched, start=1):
        actual = _parse_datetime_maybe(entry.get("due"))
        if actual is None:
            logger.info(
                f"[new_reminders_due_datetime] match#{idx} due_raw={entry.get('due')!r} parsed=None"
            )
            continue
        actual_tuple = _to_local_minute_tuple(actual, compare_tz)
        logger.info(
            f"[new_reminders_due_datetime] match#{idx} due_raw={entry.get('due')!r} "
            f"actual_parsed={actual!r} actual_tuple={actual_tuple} expected_tuple={expected_tuple}"
        )
        if actual_tuple == expected_tuple:
            logger.info("[new_reminders_due_datetime] datetime comparison matched.")
            return True

    logger.info("[new_reminders_due_datetime] no matched datetime found.")
    return False


def new_reminders_check_list_exists(env: MacOSEnv, list_name: str) -> bool:
    """
    Check whether a reminder list with exact name exists.
    Prefer remindctl JSON output; fallback to plain output.
    """
    json_output = _run_remindctl(env, "list --json")
    payload = _parse_remindctl_json(json_output)
    if payload is not None:
        candidates = []
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title")
                    if isinstance(name, str):
                        candidates.append(name)
                elif isinstance(item, str):
                    candidates.append(item)
        elif isinstance(payload, dict):
            for key in ("lists", "data", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("title")
                            if isinstance(name, str):
                                candidates.append(name)
                        elif isinstance(item, str):
                            candidates.append(item)
            if isinstance(payload.get("name"), str):
                candidates.append(payload["name"])
        if list_name in candidates:
            return True

    plain_output = _run_remindctl(env, "list")
    for line in plain_output.splitlines():
        if line.strip() == list_name:
            return True
    return False


def new_reminders_check_reminder_exists_in_list(
    env: MacOSEnv, title: str, list_name: str
) -> bool:
    """
    Check whether a reminder exists with exact title in an exact list.
    Uses remindctl JSON output.
    """
    json_output = _run_remindctl(env, "all --json")
    payload = _parse_remindctl_json(json_output)
    if payload is None:
        return False

    entries = _collect_reminder_entries(payload)
    for entry in entries:
        if entry.get("title") == title and entry.get("list_name") == list_name:
            return True
    return False


def new_reminders_check_reminder_due_date_in_list(
    env: MacOSEnv, title: str, list_name: str, due_date: str
) -> bool:
    """
    Check whether a reminder exists in a list with exact due date (date-only).
    Uses remindctl JSON output.
    """
    expected = _parse_datetime_maybe(due_date)
    if expected is None:
        logger.error(f"Invalid expected due_date: {due_date}")
        return False

    expected_local = _to_local_minute_tuple(expected)[:3]
    json_output = _run_remindctl(env, "all --json")
    payload = _parse_remindctl_json(json_output)
    if payload is None:
        return False

    entries = _collect_reminder_entries(payload)
    matched = [
        entry
        for entry in entries
        if entry.get("title") == title and entry.get("list_name") == list_name
    ]
    if not matched:
        return False

    for entry in matched:
        actual = _parse_datetime_maybe(entry.get("due"))
        if actual is None:
            continue
        actual_local = _to_local_minute_tuple(actual)[:3]
        if actual_local == expected_local:
            return True
    return False


def new_reminders_check_file_contains_today_titles(
    env: MacOSEnv, output_file: str
) -> bool:
    """
    Check whether output file contains all reminder titles from `remindctl today`.
    """
    json_output = _run_remindctl(env, "today --json")
    payload = _parse_remindctl_json(json_output)
    if payload is None:
        return False

    titles = _collect_candidate_titles(payload)
    file_content = _read_remote_file(env, output_file)
    if file_content is None:
        return False

    return all(title in file_content for title in titles)


def new_reminders_check_file_contains_overdue_titles(
    env: MacOSEnv, output_file: str
) -> bool:
    """
    Check whether output file contains all reminder titles from `remindctl overdue`.
    """
    json_output = _run_remindctl(env, "overdue --json")
    payload = _parse_remindctl_json(json_output)
    if payload is None:
        return False

    titles = _collect_candidate_titles(payload)
    file_content = _read_remote_file(env, output_file)
    if file_content is None:
        return False

    return all(title in file_content for title in titles)


def new_reminders_check_file_contains_all_titles_in_list(
    env: MacOSEnv, list_name: str, output_file: str
) -> bool:
    """
    Check whether output file contains all reminder titles in a specific list.
    """
    json_output = _run_remindctl(env, f"list {shlex.quote(list_name)} --json")
    payload = _parse_remindctl_json(json_output)
    if payload is None:
        return False

    titles = _collect_candidate_titles(payload)
    file_content = _read_remote_file(env, output_file)
    if file_content is None:
        return False

    return all(title in file_content for title in titles)


def new_reminders_check_reminder_completed(env: MacOSEnv, title: str) -> bool:
    """
    Check whether a reminder with exact title is marked completed.
    Uses remindctl JSON output.
    """
    json_output = _run_remindctl(env, "all --json")
    payload = _parse_remindctl_json(json_output)
    if payload is None:
        return False

    entries = _collect_reminder_entries(payload)
    matched = [entry for entry in entries if entry.get("title") == title]
    if not matched:
        return False

    return any(entry.get("is_completed") is True for entry in matched)


def new_reminders_check_reminder_absent(env: MacOSEnv, title: str) -> bool:
    """
    Check whether a reminder with exact title does not exist.
    Uses remindctl JSON output.
    """
    json_output = _run_remindctl(env, "all --json")
    payload = _parse_remindctl_json(json_output)
    if payload is None:
        return False

    entries = _collect_reminder_entries(payload)
    return all(entry.get("title") != title for entry in entries)


def new_reminders_check_list_absent(env: MacOSEnv, list_name: str) -> bool:
    """
    Check whether a reminder list with exact name does not exist.
    Prefer remindctl JSON output; fallback to plain output.
    """
    return not new_reminders_check_list_exists(env, list_name)
