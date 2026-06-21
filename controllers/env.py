import yaml
import paramiko
import threading

import time
import shlex
import subprocess
from pathlib import Path
import json
from typing import Optional
import importlib
import uuid
import tempfile
from utils.logger import ProjectLogger
from utils.basic import reset_applications, transform_pyautogui_line
from launcher.docker.restart_docker import (
    docker_reset_container,
    docker_start_container,
    container_exists,
    docker_remove_container,
    docker_run_container,
    DOCKER_RUN_SCRIPT_PATH,
)

import shlex
import stat

logger = ProjectLogger()


class MacOSEnv:
    def __init__(self, config_file="config/default_config.yaml"):
        """
        Initialize the MacOSEnv class. Reads configurations from the provided YAML file.
        """
        self.config = self._load_config(config_file)
        self.mode = self.config.get("mode", "docker")
        self.platform = self.config.get("platform", "wsl")
        self.docker_name = self.config.get("docker_name", "evalkit_macos")
        self.host_ip = self.config.get("host_ip", "localhost")
        self.port = self.config.get("port", 50922)
        self.password = self.config.get("password", "1234")
        self.username = self.config.get("username", "pipiwu")
        self.action_space = self.config.get("action_space", "pyautogui")

        self.ssh_client = None
        self.eval_ssh_client = None
        self.sftp_client = None
        self.task = None
        self.use_eval_ssh = False

    def _load_config(self, config_file):
        """
        Load the YAML configuration file.
        """
        try:
            with open(config_file, "r") as file:
                return yaml.safe_load(file)
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            raise

    def connect_ssh(self):
        """
        Connects to the MacOS docker container via SSH.
        """
        transport = self.ssh_client.get_transport() if self.ssh_client else None
        if self.ssh_client is None or not transport or not transport.is_active():
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                self.ssh_client.connect(
                    self.host_ip,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                )
                logger.info(f"Connected to {self.host_ip} on port {self.port}")
            except Exception as e:
                logger.error(f"SSH connection failed: {e}")
                raise e
        else:
            # logger.info("Already connected to the container.")
            pass

    def connect_eval_ssh(self):
        """
        Connects to the MacOS docker container via a separate SSH session for
        evaluator reads. This session avoids PTY allocation.
        """
        transport = self.eval_ssh_client.get_transport() if self.eval_ssh_client else None
        if self.eval_ssh_client is None or not transport or not transport.is_active():
            self.eval_ssh_client = paramiko.SSHClient()
            self.eval_ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                self.eval_ssh_client.connect(
                    self.host_ip,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                )
                logger.info(f"Connected eval SSH to {self.host_ip} on port {self.port}")
            except Exception as e:
                logger.error(f"Eval SSH connection failed: {e}")
                raise e

    def _reset_env(self):
        self.close_connection()
        if self.mode == "docker":
            docker_remove_container(self.docker_name)
            retry_time = 0
            while container_exists(self.docker_name) and retry_time < 10:
                time.sleep(3)
                retry_time += 1
            if container_exists(self.docker_name):
                raise TimeoutError(f"Remove Container {self.docker_name} Timeout")
            docker_run_container(
                self.docker_name,
                platform=self.platform,
                docker_name=self.docker_name,
                port=self.port,
            )
            # if not container_exists(self.docker_name):
            #     logger.info(f"Launching container: {self.docker_name}")
            #     proc = subprocess.Popen(["bash", str(DOCKER_RUN_SCRIPT_PATH)])

            #     for _ in range(100):
            #         try:
            #             self.connect_ssh()
            #             logger.info("SSH connection established.")
            #             break
            #         except Exception:
            #             time.sleep(2)
            #     else:
            #         logger.error("Failed to SSH into the container after timeout.")
            # docker_reset_container(self.docker_name)
            # # docker_start_container(self.docker_name)
        else:
            raise ValueError(f"Unspported mode: {self.mode}")

    def _run_with_hard_timeout(self, func, timeout, fallback, use_eval=False):
        """Execute func() in a thread with a hard timeout.
        If it doesn't complete within timeout seconds, close the relevant
        ssh client and return fallback.
        """
        result = [None]
        exception = [None]
        def target():
            try:
                result[0] = func()
            except Exception as e:
                exception[0] = e
        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive() or exception[0]:
            if t.is_alive():
                logger.warning(f"[hard_timeout] {timeout}s exceeded")
            else:
                logger.warning(f"[hard_timeout] command failed: {exception[0]}")
            if use_eval:
                try:
                    self.eval_ssh_client.close()
                except Exception:
                    pass
                self.eval_ssh_client = None
            else:
                try:
                    self.ssh_client.close()
                except Exception:
                    pass
                self.ssh_client = None
                try:
                    self.sftp_client.close()
                except Exception:
                    pass
                self.sftp_client = None
            return fallback
        return result[0]

    def _run_command_inner(self, command: str, decode: bool = True):
        if not self.ssh_client:
            self.connect_ssh()
        stdin, stdout, stderr = self.ssh_client.exec_command(command, get_pty=True)
        if decode:
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = ""
            return out, err
        else:
            return stdout, stderr

    def run_command(self, command: str, decode: bool = True, timeout: int = 300):
        if self.use_eval_ssh:
            return self.run_eval_command(command, decode=decode)
        return self._run_with_hard_timeout(
            lambda: self._run_command_inner(command, decode),
            timeout,
            fallback=("", "") if decode else (None, None),
        )

    def run_command_no_pty(self, command: str, decode: bool = True):
        if self.use_eval_ssh:
            return self.run_eval_command(command, decode=decode)

        if not self.ssh_client:
            self.connect_ssh()

        stdin, stdout, stderr = self.ssh_client.exec_command(command, get_pty=False)

        if decode:
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            return out, err
        return stdout, stderr

    def _run_command_with_status_inner(self, command: str, decode: bool = True):
        if not self.ssh_client:
            self.connect_ssh()
        stdin, stdout, stderr = self.ssh_client.exec_command(command, get_pty=True)
        if decode:
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = ""
            status = stdout.channel.recv_exit_status()
            return out, err, status
        status = stdout.channel.recv_exit_status()
        return stdout, stderr, status

    def run_command_with_status(self, command: str, decode: bool = True, timeout: int = 300):
        """Run a command via SSH and return (stdout, stderr, exit_status).

        Args:
            timeout: Max seconds to wait for the command to finish.
                     Default 300s (5 min). If exceeded, returns empty
                     output with exit_status=-1 instead of hanging forever.
        """
        if self.use_eval_ssh:
            if not self.eval_ssh_client:
                self.connect_eval_ssh()

            stdin, stdout, stderr = self.eval_ssh_client.exec_command(
                command, get_pty=False, timeout=timeout
            )

            try:
                if decode:
                    stdout.channel.settimeout(timeout)
                    stderr.channel.settimeout(timeout)
                    out = stdout.read().decode("utf-8", errors="replace").strip()
                    err = stderr.read().decode("utf-8", errors="replace").strip()
                    status = stdout.channel.recv_exit_status()
                    return out, err, status

                status = stdout.channel.recv_exit_status()
                return stdout, stderr, status
            except Exception as e:
                logger.warning(f"[run_command_with_status] timeout/error after {timeout}s: {e}")
                return ("", str(e), -1) if decode else (None, None, -1)

        return self._run_with_hard_timeout(
            lambda: self._run_command_with_status_inner(command, decode),
            timeout,
            fallback=("", f"hard timeout after {timeout}s", -1) if decode else (None, None, -1),
        )

    def _run_eval_command_inner(self, command: str, decode: bool = True):
        if not self.eval_ssh_client:
            self.connect_eval_ssh()

        stdin, stdout, stderr = self.eval_ssh_client.exec_command(command, get_pty=False)

        if decode:
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            return out, err
        return stdout, stderr

    def run_eval_command(self, command: str, decode: bool = True, timeout: int = 300):
        return self._run_with_hard_timeout(
            lambda: self._run_eval_command_inner(command, decode),
            timeout,
            fallback=("", "") if decode else (None, None),
            use_eval=True,
        )

    def _get_obs(self):
        return {
            "screenshot": self.get_screenshot(),
            "accessibility_tree": None,
            "terminal": None,
            "instruction": None,
        }

    def step(self, action, pause=2):
        if self.task is None:
            logger.info("Task is None, load a task before taking actions.")
            return None, None, None, None
        self.task.step_no += 1
        self.task.action_history.append(action)

        reward = 0  # always 0, keep the same as OSworld do, maybe insert a PRM later
        done = False
        info = {}

        # handle the special actions
        if action in ["WAIT", "FAIL", "DONE"] or (
            type(action) == dict and action["action_type"] in ["WAIT", "FAIL", "DONE"]
        ):
            if action == "WAIT":
                time.sleep(pause)
            elif action == "FAIL":
                done = True
                info = {"fail": True}
            elif action == "DONE":
                done = True
                info = {"done": True}

        if self.action_space == "computer_13":
            # the set of all possible actions defined in the action representation
            self.execute_action(action)
        elif self.action_space == "pyautogui":
            if action in ["WAIT", "FAIL", "DONE"]:
                pass
            else:
                self.execute_python_command(action)

        time.sleep(pause)
        observation = self._get_obs()

        return observation, reward, done, info

    def execute_action(self, action):
        # TODO
        pass

    def execute_python_command(self, action: str):
        """
        Upload a temporary Python script to the remote macOS and execute it safely.
        """

        remote_tmp_path = f"/tmp/task_script_{uuid.uuid4().hex}.py"

        if self.task is None:
            lines = []
            lines.append("import pyautogui")
            lines.append("import time")
            lines.append("import pynput")
            lines.append("import keyboard")
            lines.append("pyautogui.FAILSAFE = False")
            for line in action.strip().splitlines():
                if line.strip():
                    lines.append(line)
            python_code = "\n".join(lines)

        else:
            lines = []
            for line in action.strip().splitlines():
                stripped = line.strip()
                # current_line = line
                if not stripped or stripped.startswith("#"):
                    continue
                # if "pyautogui.write" in stripped or "pyautogui.typewrite" in stripped:
                #     indent = line[:len(line) - len(line.lstrip())]
                #     line = f"{indent}pyautogui.keyUp('shift'); {line.lstrip()}"
                transformed_line = transform_pyautogui_line(line)
                lines.append(transformed_line)
            command_block = "\n".join(lines)
            python_code = self.task.pkgs_prefix.format(command=command_block)

        try:
            self.connect_sftp()
            with self.sftp_client.open(remote_tmp_path, "w") as remote_script:
                remote_script.write(python_code)

            logger.info(f"Uploaded script to: {remote_tmp_path}")

            # full_cmd = f"sudo python3 {remote_tmp_path}"
            full_cmd = f"sudo /usr/bin/python3 {remote_tmp_path}"
            stdout, stderr = self.run_command(full_cmd)
            logger.info(f"[exec code] {python_code}")
            logger.info(f"[exec output] {stdout}")
            logger.info(f"[exec error] {stderr}")

            self.run_command(f"rm -f {remote_tmp_path}")

        except Exception as e:
            logger.error(f"execute_python_command failed: {e}")

    def get_screenshot(
        self, remote_tmp_path: str = "/tmp/fullscreen_dock.png"
    ) -> bytes:
        """
        Capture a fullscreen screenshot on the remote macOS system and return it as raw image bytes.

        :param remote_tmp_path: Remote temporary path to store screenshot
        :return: Screenshot image content as bytes (e.g., PNG format); returns b'' on failure
        """
        capture_cmd = f"screencapture -C {remote_tmp_path}"

        try:
            self.connect_ssh()
            logger.info("Executing screencapture command in macOS...")
            stdout, stderr = self.run_command(capture_cmd, decode=False)

            out = stdout.read().decode().strip() if hasattr(stdout, "read") else ""
            # PTY merges stderr into stdout, so stderr is always empty
            err = ""
            logger.debug(f"[stdout] {out}")
            logger.debug(f"[stderr] {err}")

            self.connect_sftp()
            with self.sftp_client.open(remote_tmp_path, "rb") as remote_file:
                image_data = remote_file.read()

            logger.info("Screenshot successfully captured and returned.")
            return image_data

        except Exception as e:
            logger.error(f"get_screenshot failed: {e}")
            return b""

    def start_recording(
        self,
        remote_path="/tmp/screen_recording_test.mp4",
        resolution="1920x1080",
        fps=30,
    ):
        """
        Starts periodic screenshots on macOS.
        """
        remote_frames_dir = "/Users/pipiwu/Codes/openclaw_recording_frames"
        remote_pid_path = "/Users/pipiwu/Codes/openclaw_recording_pid"
        remote_log_path = "/Users/pipiwu/Codes/openclaw_recording.log"
        cleanup_cmd = (
            f'if [ -f "{remote_pid_path}" ]; then '
            f'kill "$(cat "{remote_pid_path}")" >/dev/null 2>&1 || true; '
            f'fi; '
            f'rm -rf "{remote_frames_dir}"; '
            f'rm -f "{remote_pid_path}" "{remote_log_path}" "{remote_path}"'
        )
        cleanup_shell_cmd = f"zsh -lc {shlex.quote(cleanup_cmd)}"
        cleanup_out, cleanup_err = self.run_command(cleanup_shell_cmd)
        logger.info(f"Screen recording cleanup stdout: {cleanup_out}")
        logger.info(f"Screen recording cleanup stderr: {cleanup_err}")
        loop_cmd = (
            f'i=0; '
            f'while true; do '
            f'ts=$(date "+%Y-%m-%d %H:%M:%S"); '
            f'outfile="{remote_frames_dir}/frame_${{i}}.png"; '
            f'screencapture -x "$outfile"; '
            f'capture_status=$?; '
            f'printf "[%s] frame=%s status=%s file=%s\\n" "$ts" "$i" "$capture_status" "$outfile"; '
            f'if [ "$capture_status" -ne 0 ]; then '
            f'printf "[%s] screencapture failed for frame=%s\\n" "$ts" "$i"; '
            f'fi; '
            f'i=$((i+1)); '
            f'sleep 2; '
            f'done'
        )
        python_cmd = (
            "import subprocess; "
            f"cmd = ['zsh', '-lc', {loop_cmd!r}]; "
            f"log_path = {remote_log_path!r}; "
            f"pid_path = {remote_pid_path!r}; "
            "log_file = open(log_path, 'ab', buffering=0); "
            "proc = subprocess.Popen("
            "cmd, stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT, "
            "start_new_session=True, close_fds=True"
            "); "
            "open(pid_path, 'w', encoding='utf-8').write(str(proc.pid)); "
            "log_file.flush()"
        )
        cmd = (
            f'mkdir -p "{remote_frames_dir}" && '
            f': > "{remote_log_path}" && '
            f'python3 -c {shlex.quote(python_cmd)}'
        )
        shell_cmd = f"zsh -lc {shlex.quote(cmd)}"
        out, err = self.run_command_no_pty(shell_cmd)
        logger.info(f"Screen recording start command: {shell_cmd}")
        logger.info(f"Screen recording start stdout: {out}")
        logger.info(f"Screen recording start stderr: {err}")
        pid_cmd = f'cat "{remote_pid_path}" 2>/dev/null || true'
        pid_out, pid_err = self.run_command(f"zsh -lc {shlex.quote(pid_cmd)}")
        logger.info(f"Screen recording pid file: {pid_out}")
        logger.info(f"Screen recording pid stderr: {pid_err}")
        ps_cmd = (
            f'if [ -f "{remote_pid_path}" ]; then '
            f'ps -p "$(cat "{remote_pid_path}")" -o pid,ppid,stat,command; '
            f'fi 2>&1 || true'
        )
        ps_out, ps_err = self.run_command(f"zsh -lc {shlex.quote(ps_cmd)}")
        logger.info(f"Screen recording process after start:\n{ps_out}")
        logger.info(f"Screen recording process after start stderr: {ps_err}")
        if not str(pid_out).strip():
            logger.warning(
                "Screen recording PID file was not created; recorder may not have started."
            )
        elif "PID" not in str(ps_out):
            logger.warning(
                "Screen recording process is not visible in ps output after start."
            )
        self.recording_path = remote_path
        self.recording_frames_dir = remote_frames_dir
        self.recording_pid_path = remote_pid_path
        self.recording_log_path = remote_log_path
        self._recording_start_time = time.time()
        logger.info(f"Screen recording started at {remote_frames_dir}.")

    def end_recording(self, local_save_path: str):
        """
        Stops screenshot recording and fetches the frames directory.
        """
        remote_pid_path = getattr(
            self, "recording_pid_path", "/Users/pipiwu/Codes/openclaw_recording_pid"
        )
        remote_frames_dir = getattr(
            self, "recording_frames_dir", "/Users/pipiwu/Codes/openclaw_recording_frames"
        )
        remote_log_path = getattr(
            self, "recording_log_path", "/Users/pipiwu/Codes/openclaw_recording.log"
        )
        # Find and kill ffmpeg process
        ps_cmd = (
            f'if [ -f "{remote_pid_path}" ]; then '
            f'ps -p "$(cat "{remote_pid_path}")" -o pid,ppid,stat,command; '
            f'fi 2>&1 || true'
        )
        ps_out, ps_err = self.run_command(f"zsh -ilc {shlex.quote(ps_cmd)}")
        logger.info(f"Screen recording process before stop:\n{ps_out}")
        logger.info(f"Screen recording process before stop stderr: {ps_err}")
        stop_cmd = f'if [ -f "{remote_pid_path}" ]; then kill "$(cat "{remote_pid_path}")"; fi'
        out, err = self.run_command(f"zsh -ilc {shlex.quote(stop_cmd)}")
        logger.info(f"Screen recording stop stdout: {out}")
        logger.info(f"Screen recording stop stderr: {err}")
        logger.info("Stopped screen recording.")

        # Wait briefly to ensure file write is finished
        time.sleep(10)

        # Fetch the frames directory
        ls_cmd = f'ls -lh "{remote_frames_dir}" 2>&1 || true'
        ls_out, ls_err = self.run_command(f"zsh -ilc {shlex.quote(ls_cmd)}")
        logger.info(f"Screen recording remote file check: {ls_out}")
        logger.info(f"Screen recording remote file check stderr: {ls_err}")
        log_cmd = f'tail -50 "{remote_log_path}" 2>&1 || true'
        log_out, log_err = self.run_command(f"zsh -ilc {shlex.quote(log_cmd)}")
        logger.info(f"recording log tail:\n{log_out}")
        logger.info(f"recording log tail stderr: {log_err}")
        local_path = Path(local_save_path)
        self.connect_sftp()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_frames_dir = local_path.parent / f"{local_path.stem}_frames"
        self.fetch_dir(remote_frames_dir, str(local_frames_dir))
        # Compress PNG frames to JPEG to save disk space (~10x smaller)
        self._compress_frames(local_frames_dir)
        logger.info(f"Recording frames saved to {local_frames_dir}")
        local_log_path = local_path.parent / "recording.log"
        self.fetch_file(remote_log_path, str(local_log_path))
        logger.info(f"Recording log saved to {local_log_path}")

    @staticmethod
    def _compress_frames(frames_dir: Path, quality: int = 70):
        """Convert PNG frames to JPEG to save disk space.

        Replaces each .png file in *frames_dir* with a .jpg at the given
        quality (default 70). Keeps original resolution for readability.
        A typical 2MB PNG screenshot becomes ~200KB JPEG (~10x smaller).
        """
        try:
            from PIL import Image
        except ImportError:
            logger.warning(
                "[_compress_frames] Pillow not installed, skipping compression"
            )
            return

        frames_dir = Path(frames_dir)
        if not frames_dir.exists():
            return

        for png_file in frames_dir.glob("*.png"):
            try:
                jpg_file = png_file.with_suffix(".jpg")
                with Image.open(png_file) as img:
                    img = img.convert("RGB")
                    img.save(jpg_file, "JPEG", quality=quality)
                png_file.unlink()
            except Exception as e:
                logger.warning(f"[_compress_frames] Failed to compress {png_file.name}: {e}")

    def connect_sftp(self):
        self.connect_ssh()
        if self.sftp_client is None:
            self.sftp_client = self.ssh_client.open_sftp()

    def fetch_file(self, remote_path: str, local_save_path: str) -> None:
        self.connect_sftp()
        local_path = Path(local_save_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.sftp_client.get(remote_path, str(local_path))

    def fetch_dir(self, remote_dir: str, local_dir: str) -> None:
        self.connect_sftp()
        local_path = Path(local_dir)
        local_path.mkdir(parents=True, exist_ok=True)

        for entry in self.sftp_client.listdir_attr(remote_dir):
            remote_entry = f"{remote_dir.rstrip('/')}/{entry.filename}"
            local_entry = local_path / entry.filename
            if stat.S_ISDIR(entry.st_mode):
                self.fetch_dir(remote_entry, str(local_entry))
            else:
                self.sftp_client.get(remote_entry, str(local_entry))

    def push_file(self, local_path: str, remote_path: str) -> None:
        self.connect_sftp()
        self.run_command(f"mkdir -p {shlex.quote(str(Path(remote_path).parent))}")
        self.sftp_client.put(local_path, remote_path)

    def close_connection(self):
        """
        Close all the connection.
        """
        if self.sftp_client:
            self.sftp_client.close()
            self.sftp_client = None
        if self.eval_ssh_client:
            self.eval_ssh_client.close()
            self.eval_ssh_client = None
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None

    def init_task_info(self, task_json_path: str):
        path = Path(task_json_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Task JSON file not found at: {path}")
        self.task: Optional[TaskController] = TaskController(path)

    def init_task(self, task_json_path: str):

        def disable_caps_lock():
            jxa_script = """
            ObjC.import("IOKit");

            (() => {
                var ioConnect = Ref();
                var state = Ref();

                $.IOServiceOpen(
                    $.IOServiceGetMatchingService(
                        $.kIOMasterPortDefault,
                        $.IOServiceMatching($.kIOHIDSystemClass)
                    ),
                    $.mach_task_self_,
                    $.kIOHIDParamConnectType,
                    ioConnect
                );

                $.IOHIDGetModifierLockState(ioConnect, $.kIOHIDCapsLockState, state);
                if (state[0]) {
                    $.IOHIDSetModifierLockState(ioConnect, $.kIOHIDCapsLockState, 0);
                }

                $.IOServiceClose(ioConnect);
            })();
            """.strip()

            stdout, _ = self.run_command(
                f"osascript -l JavaScript -e {shlex.quote(jxa_script)}"
            )
            logger.info("====Close Caps Lock====")
            logger.info(stdout)
            logger.info(_)

        disable_caps_lock()

        self.init_task_info(task_json_path)
        if self.task is None:
            raise ValueError("TaskController was not initialized.")

        if (not self.task.config) or len(self.task.config) == 0:
            return

        for step in self.task.config:
            step_type = step.get("type")
            parameters = step.get("parameters", {})

            if step_type == "cmd":
                commands = parameters.get("command", [])
                for cmd in commands:
                    stdout, _ = self.run_command(cmd)
                    # logger.info(stdout)
                    # logger.info(_)
            else:
                try:
                    basic_utils = importlib.import_module("utils.basic")
                    getter_utils = importlib.import_module("evaluators.getter")
                    func = None
                    source_module = None

                    if hasattr(basic_utils, step_type):
                        func = getattr(basic_utils, step_type)
                        source_module = "utils.basic"
                    elif hasattr(getter_utils, step_type):
                        func = getattr(getter_utils, step_type)
                        source_module = "evaluators.getter"

                    if func is not None:
                        logger.info(
                            f"Executing: {step_type} from {source_module} with {parameters}"
                        )
                        func(self, **parameters)
                    else:
                        logger.warning(
                            f"Function '{step_type}' not found in utils.basic or evaluators.getter"
                        )
                except Exception as e:
                    logger.error(f"Error executing step '{step_type}': {e}")

    def evaluate_task(self):
        """
        Evaluate the task and return either a ``bool`` (legacy) or an
        ``EvalResult`` (fine-grained), depending on what the task JSON
        declares.

        Dispatch rule:
        - If the task has a non-empty ``scoring_components`` field, run
          the fine-grained code path and return an ``EvalResult`` whose
          ``__bool__`` reports strict completion (``score == 1.0``).
        - Otherwise, run the original ``evaluator``-based code path
          unchanged and return a plain ``bool``.

        This dispatch keeps every task that has *not* opted into
        fine-grained evaluation (currently everything outside
        ``tasks/multi_app/``) bit-for-bit identical to the previous
        behaviour.

        Backward compatibility:
        - ``bool(env.evaluate_task())`` works for both return types.
        - The ``result.txt`` writer in ``batch_run.py`` detects the
          return type and serialises the legacy ``{completed, ...}``
          shape unless an ``EvalResult`` is produced.
        """
        if not self.task:
            logger.warning("No task loaded.")
            return False

        if getattr(self.task, "scoring_components", None):
            return self._evaluate_task_fine_grained()
        return self._evaluate_task_legacy()

    def _evaluate_task_legacy(self):
        """
        Original boolean evaluator. Runs every getter listed under
        ``self.task.evaluator``, applies the configured metric, and
        combines the results with ``and`` / ``or``.

        This is the unchanged pre-fine-grained code path. Tasks that
        have *not* declared ``scoring_components`` continue to flow
        through here verbatim.
        """
        if not self.task.evaluator:
            logger.warning("No evaluator found in task.")
            return False

        evaluator = self.task.evaluator
        func_list = evaluator.get("func", [])
        expected_list = evaluator.get("expected", [])
        param_list = evaluator.get("parameters", [{}] * len(func_list))
        conj = evaluator.get("conj", "and")

        if not (len(func_list) == len(expected_list) == len(param_list)):
            raise ValueError(
                "Evaluator 'func', 'parameters', and 'expected' lists must be the same length."
            )

        results = []
        prev_use_eval_ssh = self.use_eval_ssh
        self.use_eval_ssh = True
        try:
            # Reset the applications
            reset_applications(self, self.task.related_apps)

            for func_name, params, expected in zip(func_list, param_list, expected_list):
                # Load the getter function from evaluators.getter (already imported in __init__.py)
                try:
                    evaluators_getter = importlib.import_module("evaluators.getter")
                    getter_func = getattr(evaluators_getter, func_name)
                    # logger.info(getter_func)
                except AttributeError as e:
                    logger.error(
                        f"Getter function '{func_name}' not found in 'evaluators': {e}"
                    )
                    results.append(False)
                    continue

                # Execute the getter function
                try:
                    output = getter_func(self, **params)
                except Exception as e:
                    logger.error(f"Error calling getter '{func_name}': {e}")
                    results.append(False)
                    continue

                # Evaluate the result using the metric function
                try:
                    metric_type = expected.get("type")
                    metric_func_name = expected["rules"]["func"]
                    metric_params = expected["rules"]["parameters"]

                    metric_module = importlib.import_module(
                        f"evaluators.metrics.{metric_type}"
                    )
                    metric_func = getattr(metric_module, metric_func_name)

                    # Call the metric function with correct parameter format
                    if isinstance(metric_params, list):
                        match = metric_func(output, *metric_params)
                    elif isinstance(metric_params, dict):
                        match = metric_func(output, **metric_params)
                    else:
                        match = metric_func(output, metric_params)

                    results.append(match)
                    logger.info(
                        f"[Evaluation] {func_name} => {output} vs {metric_func_name}({metric_params}) => {match}"
                    )

                except Exception as e:
                    logger.error(f"Evaluation failed for '{func_name}': {e}")
                    results.append(False)
        finally:
            self.use_eval_ssh = prev_use_eval_ssh

        # Combine results based on conjunction type: 'and' or 'or'
        return all(results) if conj == "and" else any(results)

    def _evaluate_task_fine_grained(self):
        """
        Fine-grained evaluator. Runs each entry in
        ``self.task.scoring_components`` independently, applies its
        ``rule``, normalises the result to a ``[0, 1]`` score, and
        returns an :class:`EvalResult` whose total score is the
        weighted sum of component scores.

        See ``FINE_GRAINED_EVAL_DESIGN.md`` for the schema and the
        scoring formula. The error-handling philosophy is permissive:
        any exception inside a component (missing getter, getter raise,
        bad rule, type mismatch) zeroes that component but does not
        abort the task — so a single broken checkpoint never crashes
        the whole evaluation.
        """
        from evaluators.eval_result import EvalComponent, EvalResult

        components_spec = self.task.scoring_components or []

        # Soft validation: warn if weights don't sum to 1.0.
        total_weight = sum(float(c.get("weight", 0) or 0) for c in components_spec)
        if components_spec and abs(total_weight - 1.0) > 1e-6:
            logger.warning(
                f"[fine-grained] Task '{self.task.task_id}': scoring_components "
                f"weights sum to {total_weight:.4f}, expected 1.0"
            )

        eval_components: list[EvalComponent] = []
        prev_use_eval_ssh = self.use_eval_ssh
        self.use_eval_ssh = True
        try:
            # Reset the applications, mirroring the legacy path.
            reset_applications(self, self.task.related_apps)

            for spec in components_spec:
                comp = self._evaluate_one_component(spec)
                eval_components.append(comp)
        finally:
            self.use_eval_ssh = prev_use_eval_ssh

        result = EvalResult(
            task_id=self.task.task_id,
            components=eval_components,
        )
        logger.info(
            f"[fine-grained] {result.task_id}: score={result.score:.3f} "
            f"({result.n_checkpoints_passed}/{result.n_checkpoints} chkpts) "
            f"completed={result.completed}"
        )
        return result

    def _evaluate_one_component(self, spec: dict):
        """
        Run a single fine-grained scoring component:
        getter -> rule -> normalised score -> :class:`EvalComponent`.

        Permissive: any failure (missing getter, getter raise, bad
        metric, unknown type) is logged and reported as ``score=0`` for
        that component; the rest of the task continues to evaluate.
        """
        from evaluators.eval_result import EvalComponent

        name = spec.get("name", "<unnamed>")
        weight = float(spec.get("weight", 0) or 0)
        capability = spec.get("capability", "")
        func_name = spec.get("func", "")
        params = spec.get("parameters", {}) or {}
        rule = spec.get("rule", {}) or {}

        # ---- Step 1: call the getter ----
        try:
            getter_module = importlib.import_module("evaluators.getter")
            getter_func = getattr(getter_module, func_name)
        except (AttributeError, ImportError) as e:
            logger.error(
                f"[fine-grained] Component '{name}': getter '{func_name}' "
                f"not found: {e}"
            )
            return EvalComponent(
                name=name, weight=weight, capability=capability,
                score=0.0, func=func_name, parameters=params,
                raw_output=f"<getter not found: {e}>"[:200],
            )

        try:
            output = getter_func(self, **params)
        except Exception as e:
            logger.error(
                f"[fine-grained] Component '{name}': getter '{func_name}' "
                f"raised: {e}"
            )
            return EvalComponent(
                name=name, weight=weight, capability=capability,
                score=0.0, func=func_name, parameters=params,
                raw_output=f"<getter error: {e}>"[:200],
            )

        raw_output_str = str(output)[:200]

        # ---- Step 2: apply the rule ----
        score = 0.0
        try:
            metric_type = rule.get("type", "common")
            metric_func_name = rule.get("func", "is_true")
            metric_params = rule.get("parameters", [])

            metric_module = importlib.import_module(
                f"evaluators.metrics.{metric_type}"
            )
            metric_func = getattr(metric_module, metric_func_name)

            if isinstance(metric_params, list):
                metric_result = metric_func(output, *metric_params)
            elif isinstance(metric_params, dict):
                metric_result = metric_func(output, **metric_params)
            else:
                metric_result = metric_func(output, metric_params)

            # Normalise to [0, 1]:
            #  - bool                 -> 1.0 / 0.0
            #  - int / float in [0,1] -> as-is (clipped)
            #  - anything else        -> 0.0
            if isinstance(metric_result, bool):
                score = 1.0 if metric_result else 0.0
            elif isinstance(metric_result, (int, float)):
                score = max(0.0, min(1.0, float(metric_result)))
            else:
                logger.warning(
                    f"[fine-grained] Component '{name}': metric "
                    f"'{metric_func_name}' returned non-numeric "
                    f"{type(metric_result).__name__}, scoring as 0"
                )
                score = 0.0

            logger.info(
                f"[fine-grained] {name}: {func_name} => {raw_output_str[:60]} "
                f"| {metric_func_name}({metric_params}) => {metric_result} "
                f"(score={score:.3f}, weight={weight})"
            )
        except Exception as e:
            logger.error(
                f"[fine-grained] Component '{name}': rule failed: {e}"
            )
            score = 0.0

        return EvalComponent(
            name=name, weight=weight, capability=capability,
            score=score, func=func_name, parameters=params,
            raw_output=raw_output_str,
        )


class TaskController:
    def __init__(
        self,
        json_path: Path,
        pkgs_prefix: str = 'from AppKit import NSBundle; app_info = NSBundle.mainBundle().infoDictionary(); app_info["LSBackgroundOnly"] = "1"; import pyautogui; import time; import pynput; import keyboard; pyautogui.FAILSAFE = False; {command}',
    ):
        self.json_path = Path(json_path)
        self.task = self._load_task()

        self.task_id = self.task.get("id")
        self.system_img = self.task.get("system_img", "default")
        self.instruction = self.task.get("instruction", "")
        self.config = self.task.get("config", [])
        self.related_apps = self.task.get("related_apps", [])
        self.evaluator = self.task.get("evaluator", {})
        # Fine-grained evaluation spec — only present for tasks that
        # have opted in (currently only some tasks under tasks/multi_app/).
        # When non-empty, MacOSEnv.evaluate_task() will dispatch to the
        # fine-grained code path and return an EvalResult instead of bool.
        self.scoring_components = self.task.get("scoring_components", [])

        self.step_no = 0
        self.action_history = []
        self.pkgs_prefix = pkgs_prefix

    def _load_task(self):
        if not self.json_path.exists():
            logger.error(f"Task JSON file not found: {self.json_path}")
            raise FileNotFoundError(f"Missing task definition file: {self.json_path}")

        with open(self.json_path, "r", encoding="utf-8") as f:
            task_data = json.load(f)
            logger.info(f"Loaded task from {self.json_path}")
            return task_data

    def get_config_steps(self):
        return self.config

    def get_evaluator_spec(self):
        return self.evaluator

    def get_instruction(self):
        return self.instruction

    def get_related_apps(self):
        return self.related_apps
