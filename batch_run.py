import argparse
import datetime
import json
import os
import time
from pathlib import Path

from controllers.env import MacOSEnv
from utils.logger import ProjectLogger
from mm_agents.agent import PromptAgent
from mm_agents.aguvis_agent import AguvisAgent
from mm_agents.uitars_agent import UITARSAgent
from mm_agents.internvl_agent import InternvlAgent
from mm_agents.simple_qwenvl_agent import SimpleQwenvlAgent
from mm_agents.openclaw_agent import OpenClawAgent
from mm_agents.qwen3vl_agent import Qwen3VLAgent
from mm_agents.qwen3vl_agent_235B import Qwen3VLAgent as Qwen3VLAgent235B
from mm_agents.guiowl_agent import GUIOwlAgent
from mm_agents.opencua.agent import OpenCUAAgent
from mm_agents.anthropic import AnthropicAgent

script_dir = Path(__file__).resolve().parent
logger = ProjectLogger(log_dir=script_dir / "logs")

MODEL_TYPE_LIST = {
    "gpt": lambda model, url: PromptAgent(model=model),
    "claude": lambda model, url: PromptAgent(model=model),
    "uitars": lambda model, url: UITARSAgent(model=model, url=url),
    "aguvis": lambda model, url: AguvisAgent(
        planner_model=None, executor_model=model, url=url
    ),
    "opencua": lambda model, url: InternvlAgent(model=model, url=url),
    "qwen25vl": lambda model, url: InternvlAgent(model=model, url=url),
    "qwen25vl-no-local-history": lambda model, url: SimpleQwenvlAgent(
        model=model, url=url
    ),
    "openclaw": lambda model, url: OpenClawAgent(model=model, url=url),
    "qwen3vl": lambda model, url: Qwen3VLAgent(
        model=model, base_url=url, api_key=os.environ.get("QWEN3VL_API_KEY", "empty"),
        platform="macos",
    ),
    "qwen3vl-235b": lambda model, url: Qwen3VLAgent235B(
        model=model, base_url=url, api_key=os.environ.get("QWEN3VL_API_KEY", "empty"),
        platform="macos",
    ),
    "guiowl": lambda model, url: GUIOwlAgent(
        model=model, base_url=url, api_key="empty",
    ),
    "xlang_cua": lambda model, url: OpenCUAAgent(
        model=model, base_url=url, api_key="empty",
    ),
    "anthropic_cu": lambda model, url: AnthropicAgent(
        model=model, base_url=url or os.environ.get("ANTHROPIC_BASE_URL", ""),
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        platform="macOS",
    ),
}


def build_openclaw_agent(model, url, openclaw_config_path=None):
    kwargs = {"model": model, "url": url}
    if openclaw_config_path:
        kwargs["local_config_path"] = openclaw_config_path
    return OpenClawAgent(**kwargs)


def get_all_tasks(domains, task_root="tasks", task_slices=None):
    """Get task paths, optionally slicing specific domains.

    task_slices: dict of {domain: (start, end)} for per-domain slicing.
    """
    task_root = Path(task_root)
    if "all" in domains or "single_app" in domains:
        domains = [
            "calendar",
            "clock",
            "finder",
            "mac_system_settings",
            "notes",
            "reminders",
            "safari",
            "terminal",
            "vscode",
        ]

    task_slices = task_slices or {}
    task_paths = []
    for domain in domains:
        domain_path = task_root / domain
        if domain_path.exists():
            domain_tasks = sorted(domain_path.glob("*.json"))
            if domain in task_slices:
                start, end = task_slices[domain]
                domain_tasks = domain_tasks[start:end]
            task_paths.extend(domain_tasks)
    return task_paths


def wait_for_ssh(env: MacOSEnv, max_wait: int = 900, interval: int = 5):
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


def _fix_screen_recording_permission(env: MacOSEnv):
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


def do_single_task(
    env: MacOSEnv,
    agent,
    task_path: Path,
    result_path: Path,
    max_steps: int = 50,
    disable_recording: bool = False,
    task_timeout: int = 1800,
):
    task_name = task_path.stem
    domain_path = result_path / task_path.parent.name / task_name
    domain_path.mkdir(parents=True, exist_ok=True)

    env._reset_env()
    wait_for_ssh(env)
    _fix_screen_recording_permission(env)
    env.init_task(task_path)

    agent.reset()
    logger.warning(f"disable_recording: {disable_recording}")
    if not disable_recording:
        time.sleep(10)
        env.start_recording()

    if isinstance(agent, OpenClawAgent):
        logger.info(
            f"[OPENCLAW] Starting task {task_path} with result dir {domain_path}"
        )
        run_result = agent.run_task(env, env.task.instruction)
        step_idx = 1

        remote_sessions_dir = run_result.get("remote_sessions_dir")
        if remote_sessions_dir:
            local_sessions_dir = domain_path / Path(remote_sessions_dir).name
            try:
                logger.info(
                    f"[OPENCLAW] Fetching sessions {remote_sessions_dir} -> {local_sessions_dir}"
                )
                env.fetch_dir(remote_sessions_dir, str(local_sessions_dir))
                logger.info("[OPENCLAW] Session fetch completed")
            except Exception as e:
                logger.warning(
                    f"[OPENCLAW] Failed to fetch remote sessions {remote_sessions_dir}: {e}"
                )
    else:
        response_log_path = domain_path / "response.txt"
        traj_path = domain_path / "traj.jsonl"
        with open(response_log_path, "w", encoding="utf-8") as resp_file, open(
            traj_path, "w"
        ) as traj_file:
            obs = None
            for _retry in range(5):
                obs = env._get_obs()
                if obs.get("screenshot"):
                    break
                logger.warning(f"[screenshot] retry {_retry + 1}/5, waiting 5s...")
                time.sleep(5)
            if not obs or not obs.get("screenshot"):
                logger.error("[screenshot] Failed after 5 retries, skipping task")
                result = {"completed": False, "steps_used": 0, "max_steps": max_steps}
                with open(domain_path / "result.txt", "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2)
                if not disable_recording:
                    env.end_recording(str(domain_path / "recording.mp4"))
                return
            done = False
            step_idx = 0
            task_start_time = time.time()
            while not done and step_idx < max_steps:
                if time.time() - task_start_time > task_timeout:
                    logger.warning(f"[timeout] Task exceeded {task_timeout}s, stopping")
                    break
                response, actions = agent.predict(env.task.instruction, obs)
                resp_file.write(f"Step {step_idx + 1}:\n{response}\n\n")

                step_actions, step_rewards, step_infos = [], [], []

                for action in actions:
                    obs, reward, done, info = env.step(action)
                    step_actions.append(action)
                    step_rewards.append(reward)
                    step_infos.append(info)
                    if done:
                        break

                action_timestamp = datetime.datetime.now().strftime("%Y%m%d@%H%M%S")
                screenshot_file = (
                    domain_path / f"step_{step_idx + 1}_{action_timestamp}.jpg"
                )
                from PIL import Image as PILImage
                from io import BytesIO as _BytesIO
                try:
                    _img = PILImage.open(_BytesIO(obs["screenshot"]))
                    if _img.mode == "RGBA":
                        _img = _img.convert("RGB")
                    _img.save(str(screenshot_file), "JPEG", quality=70)
                except Exception as _e:
                    logger.error(f"[screenshot] Failed at step {step_idx + 1}, ending task: {_e}")
                    done = True

                traj_entry = {
                    "step_num": step_idx + 1,
                    "action_timestamp": action_timestamp,
                    "actions": step_actions,
                    "rewards": step_rewards,
                    "done": done,
                    "infos": step_infos,
                    "screenshot_file": screenshot_file.name,
                }
                if hasattr(agent, "step_input_tokens"):
                    traj_entry["input_tokens"] = agent.step_input_tokens
                    traj_entry["output_tokens"] = agent.step_output_tokens
                if hasattr(agent, "step_total_tokens"):
                    traj_entry["total_tokens"] = agent.step_total_tokens
                if hasattr(agent, "step_cache_read"):
                    traj_entry["cache_read"] = agent.step_cache_read
                    traj_entry["cache_write"] = agent.step_cache_write
                traj_file.write(json.dumps(traj_entry) + "\n")

                step_idx += 1

    result = env.evaluate_task()
    result_path_file = domain_path / "result.txt"
    # Tasks that opted into fine-grained evaluation return an EvalResult;
    # legacy tasks still return a plain bool. Serialize accordingly so
    # non-fine-grained tasks keep producing the exact same result.txt as before.
    from evaluators.eval_result import EvalResult
    if isinstance(result, EvalResult):
        payload = result.to_result_txt(steps_used=step_idx, max_steps=max_steps)
    else:
        payload = {
            "completed": bool(result),
            "steps_used": step_idx,
            "max_steps": max_steps,
        }
    with open(result_path_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    if not disable_recording:
        env.end_recording(str(domain_path / "recording.mp4"))


def create_agent(model, model_type, url, openclaw_config_path=None):
    """Create an agent instance based on model_type."""
    if model_type is None:
        if "openclaw" in model.lower():
            return build_openclaw_agent(model, url, openclaw_config_path)
        elif "aguvis" in model.lower():
            return AguvisAgent(planner_model=None, executor_model=model, url=url)
        elif "claude" in model.lower() or "gpt" in model.lower():
            return PromptAgent(model=model, url=url)
        elif "ui_tars" in model.lower() or "uitars" in model.lower():
            return UITARSAgent(model=model, url=url)
        elif "gui_v" in model.lower() or "opencua" in model.lower():
            return InternvlAgent(model=model, url=url)
        elif "simple" in model.lower():
            return SimpleQwenvlAgent(model=model, url=url)
        else:
            raise ValueError(f"Unknown model type for: {model}")

    matched_key = None
    for key in MODEL_TYPE_LIST:
        if key in model_type:
            matched_key = key
            break
    if matched_key is None:
        raise ValueError(f"Unknown or unsupported model_type: {model_type}")

    if matched_key == "openclaw":
        return build_openclaw_agent(model, url, openclaw_config_path)
    else:
        return MODEL_TYPE_LIST[matched_key](model, url)


def main(
    domains,
    models,
    model_type_list,
    url_list,
    planner_executor_model,
    exec_model_url_list,
    model_sub_dir,
    repeat_task,
    config_file,
    _result_root,
    disable_recording,
    openclaw_config_path,
):
    task_slices = {}
    if args.task_slice:
        for s in args.task_slice:
            parts = s.split(":")
            task_slices[parts[0]] = (int(parts[1]), int(parts[2]))
    task_paths = get_all_tasks(domains, task_root=args.task_root, task_slices=task_slices)
    task_root_path = Path(args.task_root).resolve()
    if models == ["none"]:
        models = []

    model_type_list = model_type_list or [None] * len(models)
    assert len(model_type_list) == len(
        models
    ), "model_type_list must match models in length."

    url_list = url_list or [None] * len(models)
    assert len(url_list) == len(models), "url_list must match models in length."

    for model, model_type, url in zip(models, model_type_list, url_list):
        print(f"=== Running model: {model} ===")
        if model_type is None:
            if "claude" in model.lower() or "gpt" in model.lower():
                AgentClass = PromptAgent
                get_model_name = lambda a: a.model
            elif "ui_tars" in model.lower() or "uitars" in model.lower():
                AgentClass = UITARSAgent
                get_model_name = lambda a: a.model
            elif "aguvis" in model.lower():
                AgentClass = lambda: AguvisAgent(
                    planner_model=None, executor_model=model
                )
                get_model_name = lambda a: a.executor_model
            elif "gui_v" in model.lower() or "opencua" in model.lower():
                AgentClass = InternvlAgent
                get_model_name = lambda a: a.model
            elif "openclaw" in model.lower():
                AgentClass = lambda model, url: build_openclaw_agent(
                    model, url, openclaw_config_path
                )
                get_model_name = lambda a: a.model
            elif "simple" in model.lower():
                AgentClass = SimpleQwenvlAgent
                get_model_name = lambda a: a.model
            else:
                raise ValueError(f"Unknown model type for: {model}")

            agent_for_name = (
                AgentClass(url=url)
                if "aguvis" in model.lower()
                else AgentClass(model, url)
                if "openclaw" in model.lower()
                else AgentClass(model=model, url=url)
            )
            model_name = get_model_name(agent_for_name)
        else:
            model_key = model_type

            matched_key = None
            for key in MODEL_TYPE_LIST:
                if key in model_key:
                    matched_key = key
                    break

            if matched_key is None:
                raise ValueError(
                    f"Unknown or unsupported model/model_type: {model_key}"
                )

            AgentClass = MODEL_TYPE_LIST[matched_key]
            if matched_key == "aguvis":
                agent_for_name = AgentClass(model, url=url)
                get_model_name = lambda a: a.executor_model
            elif matched_key == "openclaw":
                agent_for_name = build_openclaw_agent(
                    model, url, openclaw_config_path
                )
                get_model_name = lambda a: a.model
            elif matched_key == "anthropic_cu":
                agent_for_name = AgentClass(model, url=url)
                get_model_name = lambda a: a.model_name
            else:
                agent_for_name = AgentClass(model, url=url)
                get_model_name = lambda a: a.model

            model_name = get_model_name(agent_for_name)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        subfolder = model_sub_dir if model_sub_dir else timestamp
        result_root = Path(_result_root) / model_name / subfolder
        result_root.mkdir(parents=True, exist_ok=True)

        with open(result_root / "meta.txt", "w", encoding="utf-8") as meta_file:
            meta_file.write(f"model: {model_name}\n")
            meta_file.write(f"domains: {','.join(domains)}\n")

        for task_path in task_paths:
            task_name = Path(task_path).resolve().relative_to(task_root_path).with_suffix("")
            result_file = result_root / task_name / "result.txt"
            if not repeat_task and result_file.exists():
                logger.info(f"[SKIP] {task_name} already has result.txt")
                continue
            if model_type is None:
                agent = (
                    AgentClass(url=url)
                    if "aguvis" in model.lower()
                    else AgentClass(model, url)
                    if "openclaw" in model.lower()
                    else AgentClass(model=model, url=url)
                )
            else:
                if matched_key == "openclaw":
                    agent = build_openclaw_agent(model, url, openclaw_config_path)
                else:
                    agent = MODEL_TYPE_LIST[matched_key](model, url)
            macos_env = MacOSEnv(config_file=config_file)
            do_single_task(
                macos_env,
                agent,
                task_path,
                result_root,
                disable_recording=disable_recording,
            )
            macos_env.close_connection()

    valid_pairs = []
    for pair in planner_executor_model:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            valid_pairs.append(tuple(pair))
        else:
            logger.warning(f"[SKIP] Invalid planner-executor pair: {pair}")

    planner_executor_model = valid_pairs
    if len(planner_executor_model):
        for idx, (planner_model, executor_model) in enumerate(planner_executor_model):
            exec_url = exec_model_url_list[idx] if exec_model_url_list else None

            print(
                f"=== Running planner-executor pair: {planner_model} + {executor_model} ==="
            )
            model_name = f"{planner_model}-{executor_model}"
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            subfolder = model_sub_dir if model_sub_dir else timestamp
            result_root = Path(_result_root) / model_name / subfolder
            result_root.mkdir(parents=True, exist_ok=True)

            with open(result_root / "meta.txt", "w", encoding="utf-8") as meta_file:
                meta_file.write(f"planner: {planner_model}\n")
                meta_file.write(f"executor: {executor_model}\n")
                meta_file.write(f"domains: {','.join(domains)}\n")

            for task_path in task_paths:
                task_name = (
                    Path(task_path).resolve().relative_to(task_root_path).with_suffix("")
                )
                result_file = result_root / task_name / "result.txt"
                if not repeat_task and result_file.exists():
                    logger.info(f"[SKIP] {task_name} already has result.txt")
                    continue

                agent = AguvisAgent(
                    planner_model=planner_model,
                    executor_model=executor_model,
                    url=exec_url,
                )
                macos_env = MacOSEnv(config_file=config_file)
                do_single_task(
                    macos_env,
                    agent,
                    task_path,
                    result_root,
                    disable_recording=disable_recording,
                )
                macos_env.close_connection()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch run GUI agent tasks on macOS.")
    parser.add_argument(
        "--domains",
        nargs="+",
        default=["all"],
        help="List of task domains to run (default: all)",
    )
    parser.add_argument(
        "--task_root",
        type=str,
        default="tasks",
        help="Root directory containing task domain folders (default: tasks)",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        default=["ui_tars_15_7b"],
        help="List of agent models to run",
    )
    parser.add_argument(
        "--url_list",
        nargs="*",
        default=None,
        help="List of native agent model API URLs for each model (for gpt and claude, use None)",
    )
    parser.add_argument(
        "--model_type_list",
        nargs="*",
        default=None,
        help="Explicit model type list to use for agent models (e.g., gpt, aguvis, uitars, etc.), must match models in order",
    )
    parser.add_argument(
        "--planner_executor_model",
        nargs="*",
        action="append",
        default=[],
        metavar=("PLANNER", "EXECUTOR"),
        help="Planner-executor model pairs, e.g., --planner_executor_model gpt-4o uitars",
    )
    parser.add_argument(
        "--exec_model_url_list",
        nargs="*",
        default=None,
        help="List of executor model API URLs for each planner-grounder model",
    )
    parser.add_argument(
        "--model_sub_dir",
        type=str,
        default=None,
        help="Optional subdirectory name for results",
    )
    parser.add_argument(
        "--repeat_task",
        action="store_true",
        help="Repeat every task even if result.txt exists",
    )
    parser.add_argument(
        "--config_file",
        type=str,
        default="config/default_config.yaml",
        help="Path to YAML config file for MacOSEnv",
    )
    parser.add_argument(
        "--result_root",
        type=str,
        default="/nvme/wuzhenyu/results",
        help="Path to save results",
    )
    parser.add_argument(
        "--disable_recording",
        action="store_true",
        help="Disable screen recording for debugging.",
    )
    parser.add_argument(
        "--openclaw_config_path",
        type=str,
        default=None,
        help="Optional local OpenClaw config path to sync as ~/.openclaw/openclaw.json.",
    )
    parser.add_argument(
        "--task_slice",
        type=str,
        action="append",
        default=None,
        help="Per-domain task slicing: DOMAIN:START:END (e.g. multi_app:0:47). Can be repeated.",
    )

    args = parser.parse_args()

    main(
        domains=args.domains,
        models=args.models,
        model_type_list=args.model_type_list,
        url_list=args.url_list,
        planner_executor_model=args.planner_executor_model,
        exec_model_url_list=args.exec_model_url_list,
        model_sub_dir=args.model_sub_dir,
        repeat_task=args.repeat_task,
        config_file=args.config_file,
        _result_root=args.result_root,
        disable_recording=args.disable_recording,
        openclaw_config_path=args.openclaw_config_path,
    )
