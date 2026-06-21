from __future__ import annotations

import json
import os
import shlex
import tempfile
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class _CmdResult:
    stdout: str
    stderr: str
    status: int


class MacAgentBenchCompatEnv:
    """Adapt standalone `MacAgentBench.controllers.env.MacOSEnv` to OS-Symphony `DesktopEnv`.

    Standalone MacAgentBench: `MacAgentBench/controllers/env.py`
    OS-Symphony expects: `init_task(task_json_config=dict)`, dict returns from
    code execution helpers, and `_close_env` for cleanup.

    When `connect_only=True` (default), `_close_env` only closes SSH and does not
    remove the Docker container — for an already-running VM you opened yourself.
    """

    def __init__(self, macos_env, connect_only: bool = True):
        self._env = macos_env
        self.connect_only = connect_only

    # ---------- lifecycle / env API ----------
    def _reset_env(self):
        return self._env._reset_env()

    def init_task(self, task_json_config: Optional[Dict[str, Any]] = None, **kwargs):
        """Accept a task config dict, materialize to a temp JSON, and delegate."""
        if task_json_config is None:
            raise ValueError("task_json_config is required")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(task_json_config, f, ensure_ascii=False, indent=2)
            task_path = f.name

        try:
            return self._env.init_task(task_path)
        finally:
            try:
                os.remove(task_path)
            except Exception:
                pass

    def step(self, action, pause=3):
        return self._env.step(action, pause)

    def get_screenshot(self) -> bytes:
        return self._env.get_screenshot()

    def evaluate_task(self):
        return self._env.evaluate_task()

    def _close_env(self):
        try:
            self._env.close_connection()
        except Exception:
            pass
        if self.connect_only:
            return
        try:
            docker_name = getattr(self._env, "docker_name", None)
            if docker_name:
                from controllers.env import docker_remove_container

                docker_remove_container(docker_name)
        except Exception:
            pass

    # ---------- command execution for CodeAgent ----------
    def _run_cmd_with_status(self, cmd: str, timeout: int=30) -> _CmdResult:
        out, err, status = self._env.run_command_with_status(cmd, decode=True, timeout=timeout)
        return _CmdResult(stdout=out or "", stderr=err or "", status=int(status))

    def execute_bash_command(
        self, script: str, timeout: int = 30, working_dir: Optional[str] = None
    ) -> Dict:
        script = script or ""
        if working_dir:
            prefix = f"cd {shlex.quote(working_dir)} && "
        else:
            prefix = ""
        cmd = f"zsh -lc {shlex.quote(prefix + script)}"
        res = self._run_cmd_with_status(cmd, timeout)
        merged = (
            res.stdout + ("\n" if (res.stdout and res.stderr) else "") + res.stderr
        ).strip()
        return {
            "status": "ok" if res.status == 0 else "error",
            "returncode": res.status,
            "output": merged,
            "error": "",
        }

    def execute_python_command(self, script: str) -> Dict:
        script = script or ""
        remote_tmp_path = f"/tmp/agent_s_code_{uuid.uuid4().hex}.py"

        self._env.connect_sftp()
        with self._env.sftp_client.open(remote_tmp_path, "w") as remote_script:
            remote_script.write(script)

        try:
            res = self._run_cmd_with_status(
                f"sudo python3 {shlex.quote(remote_tmp_path)}"
            )
        finally:
            try:
                self._env.run_command(f"rm -f {shlex.quote(remote_tmp_path)}")
            except Exception:
                pass

        return {
            "status": "ok" if res.status == 0 else "error",
            "return_code": res.status,
            "output": (res.stdout or "").strip(),
            "error": (res.stderr or "").strip(),
        }
