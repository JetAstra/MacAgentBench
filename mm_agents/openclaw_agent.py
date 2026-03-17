import shlex
import time
import json
from utils.logger import ProjectLogger

logger = ProjectLogger()


class OpenClawAgent:
    def __init__(
        self,
        model="openclaw",
        url=None,
        agent_name="main",
        app_name="OpenClaw",
        local_config_path="/home/fuyikun/Documents/OS-Mac/openclaw.json",
        remote_config_dir="/Users/pipiwu/.openclaw",
        remote_sessions_dir="/Users/pipiwu/.openclaw/agents/main/sessions",
        app_wait_timeout=60,
        app_wait_interval=2,
        app_stable_delay=8,
        task_timeout_seconds=300,
    ):
        self.model = model
        self.url = url
        self.agent_name = agent_name
        self.app_name = app_name
        self.local_config_path = local_config_path
        self.remote_config_dir = remote_config_dir
        self.remote_sessions_dir = remote_sessions_dir
        self.app_wait_timeout = app_wait_timeout
        self.app_wait_interval = app_wait_interval
        self.app_stable_delay = app_stable_delay
        self.task_timeout_seconds = task_timeout_seconds

    def reset(self, _logger=None):
        return None

    def launch_app(self, env):
        command = f"open -a {shlex.quote(self.app_name)}"
        logger.info(f"[OpenClaw] Launching app with command: {command}")
        stdout, stderr, exit_status = env.run_command_with_status(command)
        logger.info(
            f"[OpenClaw] Launch result exit_status={exit_status}, stdout={stdout!r}, stderr={stderr!r}"
        )
        return {
            "command": command,
            "stdout": stdout,
            "stderr": stderr,
            "exit_status": exit_status,
        }

    def sync_config(self, env):
        config_name = self.local_config_path.split("/")[-1]
        remote_config_path = f"{self.remote_config_dir.rstrip('/')}/{config_name}"
        logger.info(
            f"[OpenClaw] Syncing config {self.local_config_path} -> {remote_config_path}"
        )
        env.push_file(self.local_config_path, remote_config_path)
        logger.info("[OpenClaw] Config sync completed")
        return {
            "local_config_path": self.local_config_path,
            "remote_config_path": remote_config_path,
        }

    def wait_until_app_ready(self, env):
        check_command = "zsh -ilc " + shlex.quote("Openclaw nodes status --json")
        logger.info(f"[OpenClaw] Waiting for app ready with command: {check_command}")

        total_waited = 0
        attempts = []
        attempt_idx = 1
        while total_waited < self.app_wait_timeout:
            logger.info(
                f"[OpenClaw] Ready check attempt {attempt_idx}, waited={total_waited}s"
            )
            stdout, stderr, exit_status = env.run_command_with_status(check_command)
            ready = False
            parsed = None
            if exit_status == 0 and stdout.strip():
                try:
                    parsed = json.loads(stdout)
                    nodes = parsed.get("nodes", [])
                    ready = any(
                        node.get("connected") is True and node.get("paired") is True
                        for node in nodes
                    )
                except json.JSONDecodeError:
                    parsed = None
            logger.info(
                f"[OpenClaw] Ready check attempt {attempt_idx} result: exit_status={exit_status}, ready={ready}, stderr={stderr!r}"
            )
            attempts.append(
                {
                    "waited": total_waited,
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_status": exit_status,
                    "ready": ready,
                    "parsed": parsed,
                }
            )
            if ready:
                logger.info(
                    f"[OpenClaw] App reported ready, sleeping {self.app_stable_delay}s for stabilization"
                )
                time.sleep(self.app_stable_delay)
                return {
                    "ready": True,
                    "check_command": check_command,
                    "attempts": attempts,
                }
            time.sleep(self.app_wait_interval)
            total_waited += self.app_wait_interval
            attempt_idx += 1

        logger.warning(
            f"[OpenClaw] App did not become ready within {self.app_wait_timeout}s"
        )
        return {
            "ready": False,
            "check_command": check_command,
            "attempts": attempts,
        }

    def prepare_env(self, env):
        logger.info("[OpenClaw] Preparing environment")
        config_result = self.sync_config(env)
        launch_result = self.launch_app(env)
        ready_result = self.wait_until_app_ready(env)
        logger.info(
            f"[OpenClaw] Environment prepared: ready={ready_result.get('ready', False)}"
        )
        return {
            "config": config_result,
            "launch": launch_result,
            "ready": ready_result,
        }

    def build_command(self, instruction: str) -> str:
        session_id_expr = f"clean-$(date +%s)"
        openclaw_cmd = (
            f"Openclaw agent "
            f"--agent {shlex.quote(self.agent_name)} "
            f"--session-id {session_id_expr} "
            f"--timeout {self.task_timeout_seconds} "
            f"--message {shlex.quote(instruction)}"
        )
        return f"zsh -ilc {shlex.quote(openclaw_cmd)}"

    def run_task(self, env, instruction: str):
        logger.info(f"[OpenClaw] Starting task run with instruction: {instruction}")
        prepare_result = self.prepare_env(env)
        command = self.build_command(instruction)
        logger.info(f"[OpenClaw] Executing agent command: {command}")
        stdout, stderr, exit_status = env.run_command_with_status(command)
        logger.info(
            f"[OpenClaw] Agent command finished: exit_status={exit_status}, stdout={stdout!r}, stderr={stderr!r}"
        )
        return {
            "prepare": prepare_result,
            "command": command,
            "stdout": stdout,
            "stderr": stderr,
            "exit_status": exit_status,
            "remote_sessions_dir": self.remote_sessions_dir,
        }
