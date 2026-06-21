"""Dynamic task-level parallel dispatch for baseline evaluation.

Usage:
    python parallel_dispatch.py \\
        --model gemini-3.1-pro-preview \\
        --model_type gpt \\
        --model_sub_dir gemini-3.1-pro-preview-baseline \\
        --num_workers 7 \\
        --config_dir config

Each worker gets its own VM (via config file) and pulls tasks one-by-one
from a shared queue. Fast workers automatically pick up more tasks.
"""

import argparse
import datetime
import multiprocessing
import os
import queue
import sys
import threading
import time
from pathlib import Path

# All domains
ALL_DOMAINS = [
    "multi_app", "new_reminders", "keynote", "new_songsee",
    "new_apple_notes", "new_himalaya", "new_obsidian", "new_peekaboo",
    "pages", "new_blogwatcher", "new_tmux", "new_github", "numbers",
    "new_weather", "new_whisper", "new_gifgrep", "terminal", "notes",
    "new_video_frames", "safari", "reminders", "finder", "clock",
    "calendar", "vscode", "new_clawhub", "new_sherpa_onnx_tts",
    "mac_system_settings",
]

WORK_DIR = Path(__file__).resolve().parent
TASK_ROOT = WORK_DIR / "tasks"
RESULT_ROOT = WORK_DIR / "results"


def collect_tasks(result_root):
    """Collect all pending tasks (no result.txt yet)."""
    from batch_run import get_all_tasks
    task_paths = get_all_tasks(ALL_DOMAINS, task_root=str(TASK_ROOT))
    task_root_resolved = TASK_ROOT.resolve()

    pending = []
    skipped = 0
    for tp in task_paths:
        tp = Path(tp).resolve()
        task_name = tp.relative_to(task_root_resolved).with_suffix("")
        result_file = result_root / task_name / "result.txt"
        if result_file.exists():
            skipped += 1
        else:
            pending.append(str(tp))  # str for multiprocessing serialization

    print(f"Total tasks: {len(task_paths)}, skipped: {skipped}, pending: {len(pending)}")
    return pending


TASK_HARD_TIMEOUT = 2400  # 40 minutes, above do_single_task's 30min internal timeout


def _run_task_inner(config_file, model, model_type, url, task_path, result_root,
                    openclaw_config_path=None):
    """Run a single task. Called in a sub-thread for timeout control."""
    from batch_run import create_agent, do_single_task
    from controllers.env import MacOSEnv

    agent = create_agent(model, model_type, url, openclaw_config_path)
    env = None
    try:
        env = MacOSEnv(config_file=str(config_file))
        do_single_task(
            env,
            agent,
            Path(task_path),
            Path(result_root),
            disable_recording=False,
        )
    finally:
        if env:
            env.close_connection()


def worker_process(worker_id, config_file, task_queue, model, model_type, url,
                   result_root, log_dir, log_prefix, openclaw_config_path=None):
    """Worker process: pull tasks from queue and execute them.

    Each worker is a separate process with its own log file.
    """
    # Redirect stdout/stderr to per-worker log file
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(log_dir) / f"{log_prefix}_{ts}_worker_{worker_id}.log"
    fh = open(log_file, "w")
    sys.stdout = fh
    sys.stderr = fh

    # Reset all existing loggers so their StreamHandlers point to the new stdout
    import logging
    for name in list(logging.Logger.manager.loggerDict) + ['root']:
        lg = logging.getLogger(name if name != 'root' else None)
        for handler in lg.handlers[:]:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                lg.removeHandler(handler)
                new_handler = logging.StreamHandler(fh)
                new_handler.setLevel(handler.level)
                new_handler.setFormatter(handler.formatter)
                lg.addHandler(new_handler)

    from utils.logger import ProjectLogger
    logger = ProjectLogger(name=f"worker_{worker_id}")

    logger.info(f"[Worker {worker_id}] Started. Log: {log_file}")

    while True:
        try:
            task_path_str = task_queue.get_nowait()
        except queue.Empty:
            logger.info(f"[Worker {worker_id}] No more tasks. Done!")
            break

        task_name = Path(task_path_str).relative_to(TASK_ROOT.resolve()).with_suffix("")
        remaining = task_queue.qsize()
        logger.info(f"[Worker {worker_id}] Starting: {task_name} ({remaining} remaining)")

        # Run task in a sub-thread with hard timeout
        error_holder = []

        def _run_with_error():
            try:
                _run_task_inner(config_file, model, model_type, url,
                                task_path_str, result_root, openclaw_config_path)
            except Exception as e:
                error_holder.append(e)

        task_thread = threading.Thread(target=_run_with_error, daemon=True)
        task_thread.start()
        task_thread.join(timeout=TASK_HARD_TIMEOUT)

        if task_thread.is_alive():
            logger.error(f"[Worker {worker_id}] TIMEOUT after {TASK_HARD_TIMEOUT}s: {task_name}, skipping")
            time.sleep(10)
        elif error_holder:
            logger.error(f"[Worker {worker_id}] Failed: {task_name}: {error_holder[0]}")
        else:
            logger.info(f"[Worker {worker_id}] Finished: {task_name}")

    fh.close()


def main():
    parser = argparse.ArgumentParser(description="Dynamic task-level parallel dispatch.")
    parser.add_argument("--model", required=True, help="Model name (e.g. gemini-3.1-pro-preview)")
    parser.add_argument("--model_type", required=True,
                        help="Agent type (e.g. gpt, claude, qwen3vl, openclaw)")
    parser.add_argument("--model_sub_dir", required=True, help="Result subdirectory name")
    parser.add_argument("--url", default="", help="Model API URL")
    parser.add_argument("--num_workers", type=int, default=7)
    parser.add_argument("--config_prefix", default="qwen3vl_worker",
                        help="Config file prefix (default: qwen3vl_worker)")
    parser.add_argument("--config_dir", default="config", help="Config directory")
    parser.add_argument("--result_root", default=None, help="Result root (default: results/)")
    parser.add_argument("--log_prefix", default="dispatch", help="Log file prefix")
    parser.add_argument("--openclaw_config_path", default=None,
                        help="Path to OpenClaw config JSON (for openclaw model_type)")
    args = parser.parse_args()

    model = args.model
    model_type = args.model_type
    url = args.url
    model_sub_dir = args.model_sub_dir
    config_dir = WORK_DIR / args.config_dir
    log_dir = WORK_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _result_root = Path(args.result_root) if args.result_root else RESULT_ROOT

    # Determine result root: results/{model}/{model_sub_dir}/
    result_root = _result_root / model / model_sub_dir
    result_root.mkdir(parents=True, exist_ok=True)

    # Collect pending tasks
    pending = collect_tasks(result_root)
    if not pending:
        print("No pending tasks. All done!")
        return

    # Build shared task queue (multiprocessing-safe)
    task_queue = multiprocessing.Queue()
    for tp in pending:
        task_queue.put(tp)

    # Config files for workers
    config_files = [str(config_dir / f"{args.config_prefix}_{i}.yaml")
                    for i in range(1, args.num_workers + 1)]

    print(f"=== {model} ({model_sub_dir}): {len(pending)} tasks, {args.num_workers} workers ===")

    # Launch worker processes
    processes = []
    for i, config_file in enumerate(config_files):
        p = multiprocessing.Process(
            target=worker_process,
            args=(i + 1, config_file, task_queue, model, model_type, url,
                  str(result_root), str(log_dir), args.log_prefix,
                  args.openclaw_config_path),
        )
        p.start()
        processes.append(p)

    # Wait for all workers to finish
    for p in processes:
        p.join()

    print(f"=== All workers finished! ===")


if __name__ == "__main__":
    main()
