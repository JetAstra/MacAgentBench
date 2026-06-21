"""Per-subtask runtime.log: one file per example dir, all desktopenv.* logs (agent, LLM, example)."""

from __future__ import annotations

import logging
import os
from typing import Optional

# Unified field order: time, level, logger name, location, process, message
DATE_FMT = "%Y-%m-%d %H:%M:%S"
PLAIN_FMT = (
    "[%(asctime)s] [%(levelname)s] [%(name)s] %(module)s:%(lineno)d %(processName)s | %(message)s"
)
ANSI_FMT = (
    "\x1b[1;33m[%(asctime)s]\x1b[0m "
    "\x1b[31m%(levelname)s\x1b[0m "
    "\x1b[32m[%(name)s]\x1b[0m "
    "%(module)s:%(lineno)d-%(processName)s | %(message)s"
)

_task_runtime_handler: Optional[logging.Handler] = None


def plain_formatter() -> logging.Formatter:
    return logging.Formatter(fmt=PLAIN_FMT, datefmt=DATE_FMT)


def ansi_formatter() -> logging.Formatter:
    return logging.Formatter(fmt=ANSI_FMT, datefmt=DATE_FMT)


def attach_task_runtime_log(example_result_dir: str) -> None:
    """Route all ``desktopenv.*`` log records to ``example_result_dir/runtime.log``.

    Removes any previously attached task file handler in this process (next task in same worker).
    """
    global _task_runtime_handler
    detach_task_runtime_log()
    os.makedirs(example_result_dir, exist_ok=True)
    path = os.path.join(example_result_dir, "runtime.log")
    h = logging.FileHandler(path, encoding="utf-8")
    h.setLevel(logging.DEBUG)
    h.setFormatter(plain_formatter())
    base = logging.getLogger("desktopenv")
    base.setLevel(logging.DEBUG)
    base.addHandler(h)
    _task_runtime_handler = h


def detach_task_runtime_log() -> None:
    """Remove the current task's file handler; close the file."""
    global _task_runtime_handler
    if _task_runtime_handler is None:
        return
    base = logging.getLogger("desktopenv")
    try:
        base.removeHandler(_task_runtime_handler)
    finally:
        try:
            _task_runtime_handler.close()
        except Exception:
            pass
        _task_runtime_handler = None
