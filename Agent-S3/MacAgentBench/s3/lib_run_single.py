import datetime
import json
import logging
import os
import time
from typing import *
from wrapt_timeout_decorator import *
from controllers.env import MacOSEnv
from processed_step_action import save_processed_step_image


def _fix_screen_recording_permission(env: MacOSEnv, logger):
    """Extend Screen Recording permission expiry to 2099 to prevent popup.

    macOS Sequoia resets screen recording permissions monthly. The popup
    steals focus and breaks UI-state evaluations. This sets all expiry
    dates in ScreenCaptureApprovals.plist to 2099-01-01.
    """
    fix_script = (
        "python3 -c \""
        "import plistlib; from pathlib import Path; from datetime import datetime; "
        "p = Path.home() / 'Library/Group Containers/group.com.apple.replayd/ScreenCaptureApprovals.plist'; "
        "exec(open('/dev/null').read()) if not p.exists() else None; "
        "d = plistlib.loads(p.read_bytes()) if p.exists() else {}; "
        "f = datetime(2099, 1, 1); "
        "[d[k].__setitem__(field, f) for k in d if isinstance(d[k], dict) for field in d[k] if isinstance(d[k][field], datetime)]; "
        "p.write_bytes(plistlib.dumps(d)) if d else None; "
        "print('ScreenCapture permissions extended to 2099')"
        "\""
    )
    try:
        stdout, _ = env.run_command(fix_script)
        out = stdout.read().decode().strip() if hasattr(stdout, "read") else stdout.strip()
        logger.info(f"[fix_screen_recording] {out}")
    except Exception as e:
        logger.warning(f"[fix_screen_recording] Failed: {e}")

def wait_for_ssh(env: MacOSEnv, logger, max_wait: int = 900, interval: int = 5):
    total_waited = 0
    attempt = 1
    while total_waited < max_wait:
        try:
            logger.info(f"[SSH Attempt {attempt}] Trying to connect...")
            env.connect_ssh()
            transport = env.ssh_client.get_transport() if env.ssh_client else None
            if not transport or not transport.is_active():
                raise ConnectionError("SSH transport not active after connect()")
            logger.info("✅ SSH connected successfully.")
            time.sleep(15)
            return
        except Exception as e:
            logger.warning(f"[SSH Attempt {attempt}] Failed: {type(e).__name__}: {e}")
            time.sleep(interval)
            total_waited += interval
            attempt += 1
    raise TimeoutError(f"❌ SSH connection failed after waiting {max_wait} seconds.")

def run_single_example(
    agent, env, example, max_steps, max_solving_time, instruction, args, example_result_dir, scores
):
    runtime_logger = logging.getLogger(f"desktopenv.example.{example['id']}")
    agent.reset()
    env.macos_env._reset_env()
    wait_for_ssh(env=env.macos_env._env, logger=runtime_logger)
    _fix_screen_recording_permission(env=env.macos_env._env, logger=runtime_logger)
    env.macos_env.init_task(task_json_config=example)
    time.sleep(15)
    obs = env._get_obs()  # Get the initial observation

    with open(os.path.join(example_result_dir, f"step_0.png"), "wb") as _f:
        _f.write(obs["screenshot"])

    with open(
        os.path.join(example_result_dir, "instruction.txt"), "w", encoding="utf-8"
    ) as f:
        f.write(instruction)

    done = False
    step_idx = 0
    # env.controller.start_recording()
    t0 = time.time()
    while not done and step_idx < max_steps:
        dt = time.time() - t0
        if dt > max_solving_time:
            runtime_logger.info(f"Stop due to time limitation ({max_solving_time}s)")
            break
        response, actions = agent.predict(instruction, obs)
        for action in actions:
            action_timestamp = datetime.datetime.now().strftime("%Y%m%d@%H%M%S")
            runtime_logger.info("Step %d: %s", step_idx + 1, action)
            obs, reward, done, info = env.step(action, args.sleep_after_execution)

            runtime_logger.info("Reward: %.2f", reward)
            runtime_logger.info("Done: %s", done)
            # Save screenshot and trajectory information
            with open(
                os.path.join(
                    example_result_dir, f"step_{step_idx + 1}_{action_timestamp}.png"
                ),
                "wb",
            ) as _f:
                _f.write(obs["screenshot"])
            try:
                save_processed_step_image(
                    example_result_dir,
                    step_idx + 1,
                    action_timestamp,
                    obs["screenshot"],
                    action,
                )
            except Exception as e:
                runtime_logger.warning("processed_step annotation failed: %s", e)

            response.update(
                {
                    "step_num": step_idx + 1,
                    "action_timestamp": action_timestamp,
                    "action": action,
                    "reward": reward,
                    "done": done,
                    "info": info,
                    "screenshot_file": f"step_{step_idx + 1}_{action_timestamp}.png",
                }
            )
            with open(
                os.path.join(example_result_dir, "traj.jsonl"), "a", encoding="utf-8"
            ) as f:
                f.write(json.dumps(response, ensure_ascii=False))
                f.write("\n")
            if done:
                runtime_logger.info("The episode is done.")
                break
        step_idx += 1
    if step_idx >= max_steps:
        runtime_logger.info(f"Stop due to step limitation ({max_steps} steps)")
    runtime_logger.info(f"[total time cost] {time.time() - t0}s")
    runtime_logger.info(f"[total step cost] {step_idx}")
    result = env.evaluate()
    runtime_logger.info("Result: %.2f", result)
    scores.append(result)
    result_path = os.path.join(example_result_dir, "result.txt")
    # Fine-grained results (EvalResult) get serialized as full JSON with the
    # per-checkpoint components so downstream tools can aggregate by capability.
    # Legacy bool / unknown results fall back to the one-line summary.
    try:
        from evaluators.eval_result import EvalResult
    except Exception:
        EvalResult = None
    if EvalResult is not None and isinstance(result, EvalResult):
        payload = result.to_result_txt(steps_used=step_idx, max_steps=max_steps)
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    else:
        with open(result_path, "w", encoding="utf-8") as f:
            f.write(f"{result}\n")
    # env.controller.end_recording(os.path.join(example_result_dir, "recording.mp4"))
