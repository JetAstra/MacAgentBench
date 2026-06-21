from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


class PythonController:
    """Controller interface expected by Agent-S CodeAgent."""

    def __init__(self, macos_env):
        self.macos_env = macos_env

    def run_python_script(self, script: str) -> dict:
        return self.macos_env.execute_python_command(script)

    def run_bash_script(
        self, script: str, timeout: int = 30, working_dir: Optional[str] = None
    ) -> dict:
        return self.macos_env.execute_bash_command(
            script, timeout=timeout, working_dir=working_dir
        )


class DesktopEnv:
    """Minimal MacOS Arena env wrapper (no OS-Symphony dependency).

    This is intentionally small: Agent-S evaluation code only needs:
    - `reset(task_config=dict)`
    - `_get_obs() -> {'screenshot': bytes}`
    - `step(action, pause)`
    - `evaluate()`
    - `close()`
    - `.controller` with `run_python_script` / `run_bash_script`

    If `connect_only=True`, `reset()` does NOT call `_reset_env()` (no docker teardown).
    """

    def __init__(self, macos_env, connect_only: bool = True):
        self.macos_env = macos_env
        self.controller = PythonController(self.macos_env)
        self.connect_only = connect_only

    def _get_obs(self) -> Dict[str, Any]:
        return {"screenshot": self.macos_env.get_screenshot()}

    def reset(self, task_config: Optional[Dict[str, Any]] = None):
        if not self.connect_only:
            self.macos_env._reset_env()
        self.macos_env.init_task(task_json_config=task_config)
        return

    def step(self, action, pause=3):
        return self.macos_env.step(action, pause)

    def evaluate(self):
        return self.macos_env.evaluate_task()

    def close(self):
        self.macos_env._close_env()
        return

