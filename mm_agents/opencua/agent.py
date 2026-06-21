"""
OpenCUA Agent adapted for MacAgentBench evaluation.
Based on: https://github.com/xlang-ai/OSWorld/blob/main/mm_agents/opencua/opencua_agent.py

For 7B/32B: use_old_sys_prompt=True, cot_level=l2, coordinate_type=qwen25
"""

import re
import os
import ast
import time
import logging
import traceback
from typing import Dict, List, Tuple, Optional
from openai import OpenAI

from mm_agents.opencua.utils import (
    encode_image,
    smart_resize,
)
from mm_agents.opencua.prompts import (
    INSTRUTION_TEMPLATE,
    STEP_TEMPLATE,
    ACTION_HISTORY_TEMPLATE,
    THOUGHT_HISTORY_TEMPLATE,
    OBSERVATION_HISTORY_TEMPLATE,
    SYSTEM_PROMPT_V1_L1,
    SYSTEM_PROMPT_V1_L2,
    SYSTEM_PROMPT_V1_L3,
    build_sys_prompt,
)

logger = logging.getLogger("desktopenv.opencua_agent")


KEY_MAP = {
    "enter": "pynput.keyboard.Key.enter",
    "space": "pynput.keyboard.Key.space",
    "shift": "pynput.keyboard.Key.shift",
    "ctrl": "pynput.keyboard.Key.ctrl",
    "alt": "pynput.keyboard.Key.alt",
    "cmd": "pynput.keyboard.Key.cmd",
    "command": "pynput.keyboard.Key.cmd",
    "tab": "pynput.keyboard.Key.tab",
    "esc": "pynput.keyboard.Key.esc",
    "backspace": "pynput.keyboard.Key.backspace",
    "delete": "pynput.keyboard.Key.delete",
    "up": "pynput.keyboard.Key.up",
    "down": "pynput.keyboard.Key.down",
    "left": "pynput.keyboard.Key.left",
    "right": "pynput.keyboard.Key.right",
    "home": "pynput.keyboard.Key.home",
    "end": "pynput.keyboard.Key.end",
    "pageup": "pynput.keyboard.Key.page_up",
    "pagedown": "pynput.keyboard.Key.page_down",
    "f1": "pynput.keyboard.Key.f1",
    "f2": "pynput.keyboard.Key.f2",
    "f3": "pynput.keyboard.Key.f3",
    "f4": "pynput.keyboard.Key.f4",
    "f5": "pynput.keyboard.Key.f5",
    "f6": "pynput.keyboard.Key.f6",
    "f7": "pynput.keyboard.Key.f7",
    "f8": "pynput.keyboard.Key.f8",
    "f9": "pynput.keyboard.Key.f9",
    "f10": "pynput.keyboard.Key.f10",
    "f11": "pynput.keyboard.Key.f11",
    "f12": "pynput.keyboard.Key.f12",
}


def _map_key(key: str) -> str:
    k = key.strip().strip("'\"").lower()
    return KEY_MAP.get(k, repr(key.strip().strip("'\"")))


def normalize_pyautogui_code(code: str) -> str:
    """Convert pyautogui code to macOS-compatible mixed format (pyautogui + pynput).

    On macOS, pyautogui has bugs with doubleClick, rightClick, keyboard input etc.
    This converts to the same format used by InternVL agent.
    """
    lines = code.split("\n")
    fixed = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Step 1: Add pyautogui. prefix if missing
        for func in ['write', 'press', 'click', 'Click', 'hotkey', 'scroll', 'moveTo',
                      'doubleClick', 'rightClick', 'middleClick', 'tripleClick', 'dragTo',
                      'DragTo', 'keyDown', 'keyUp', 'type', 'wait', 'terminate', 'hscroll']:
            if line.startswith(f"{func}(") and not line.startswith("pyautogui."):
                line = f"pyautogui.{line}"
                break
        # Normalize case: pyautogui.Click -> pyautogui.click, pyautogui.DragTo -> pyautogui.dragTo
        if line.startswith("pyautogui.Click("):
            line = line.replace("pyautogui.Click(", "pyautogui.click(", 1)
        if line.startswith("pyautogui.DragTo("):
            line = line.replace("pyautogui.DragTo(", "pyautogui.dragTo(", 1)

        # Step 2: Fix hotkey list args: pyautogui.hotkey(['cmd', 'space']) -> pyautogui.hotkey('cmd', 'space')
        hotkey_list_match = re.match(r"pyautogui\.hotkey\(\[(.+?)\]\)", line)
        if hotkey_list_match:
            line = f"pyautogui.hotkey({hotkey_list_match.group(1)})"

        # Step 3: Fix message= keyword: pyautogui.write(message='text') -> pyautogui.write('text')
        write_msg_match = re.match(r"pyautogui\.write\(message=(.+)\)", line)
        if write_msg_match:
            line = f"pyautogui.write({write_msg_match.group(1)})"

        # Step 4: Fix computer.triple_click -> pyautogui.tripleClick
        tc_match = re.match(r"computer\.triple_click\((?:x=)?(\d+),\s*(?:y=)?(\d+)\)", line)
        if tc_match:
            line = f"pyautogui.tripleClick({tc_match.group(1)}, {tc_match.group(2)})"

        # Step 5: Convert to macOS-compatible format (match InternVL agent)

        # doubleClick -> pynput
        dc_match = re.match(r"pyautogui\.doubleClick\((\d+),\s*(\d+)\)", line)
        if dc_match:
            x, y = dc_match.group(1), dc_match.group(2)
            line = f"from pynput.mouse import Controller, Button;mouse=Controller(); mouse.position=({x},{y}); mouse.click(Button.left,2)"

        # rightClick -> pynput
        rc_match = re.match(r"pyautogui\.rightClick\((\d+),\s*(\d+)\)", line)
        if rc_match:
            x, y = rc_match.group(1), rc_match.group(2)
            line = f"from pynput.mouse import Controller, Button;mouse=Controller(); mouse.position=({x},{y}); mouse.click(Button.right,1)"

        # middleClick -> pynput
        mc_match = re.match(r"pyautogui\.middleClick\((\d+),\s*(\d+)\)", line)
        if mc_match:
            x, y = mc_match.group(1), mc_match.group(2)
            line = f"from pynput.mouse import Controller, Button;mouse=Controller(); mouse.position=({x},{y}); mouse.click(Button.middle,1)"

        # tripleClick -> pynput doubleClick (closest action, same as InternVL)
        trc_match = re.match(r"pyautogui\.tripleClick\((\d+),\s*(\d+)\)", line)
        if trc_match:
            x, y = trc_match.group(1), trc_match.group(2)
            line = f"from pynput.mouse import Controller, Button;mouse=Controller(); mouse.position=({x},{y}); mouse.click(Button.left,2)"

        # scroll -> pynput
        scroll_match = re.match(r"pyautogui\.scroll\((-?\d+)\)", line)
        if scroll_match:
            clicks = scroll_match.group(1)
            line = f"mouse = pynput.mouse.Controller(); mouse.scroll(0, {clicks})"

        # press -> pynput
        press_match = re.match(r"pyautogui\.press\(['\"](.+?)['\"]\)", line)
        if press_match:
            key = press_match.group(1)
            mapped = _map_key(key)
            line = f"from pynput.keyboard import Controller as KeyboardController;kb=KeyboardController(); kb.press({mapped}); kb.release({mapped})"

        # hotkey -> pynput
        hotkey_match = re.match(r"pyautogui\.hotkey\((.+)\)", line)
        if hotkey_match:
            args_str = hotkey_match.group(1)
            keys = [k.strip().strip("'\"") for k in args_str.split(",")]
            seq = []
            for k in keys:
                seq.append(f"kb.press({_map_key(k)})")
            for k in reversed(keys):
                seq.append(f"kb.release({_map_key(k)})")
            line = f"from pynput.keyboard import Controller as KeyboardController;kb=KeyboardController(); {'; '.join(seq)}"

        # write -> keyboard.write
        write_match = re.match(r"pyautogui\.write\((.+)\)", line)
        if write_match:
            text_arg = write_match.group(1)
            line = f"keyboard.write({text_arg})"

        # typewrite -> keyboard.write
        tw_match = re.match(r"pyautogui\.typewrite\((.+)\)", line)
        if tw_match:
            text_arg = tw_match.group(1)
            line = f"keyboard.write({text_arg})"

        # type(message='text') -> keyboard.write (pyautogui.type is not a real function)
        type_match = re.match(r"pyautogui\.type\((?:message=)?(.+)\)", line)
        if type_match:
            text_arg = type_match.group(1)
            line = f"keyboard.write({text_arg})"

        # hscroll -> pynput scroll (horizontal mapped to vertical)
        hscroll_match = re.match(r"pyautogui\.hscroll\((-?\d+)\)", line)
        if hscroll_match:
            clicks = hscroll_match.group(1)
            line = f"mouse = pynput.mouse.Controller(); mouse.scroll({clicks}, 0)"

        # keyDown -> pynput
        kd_match = re.match(r"pyautogui\.keyDown\(['\"](.+?)['\"]\)", line)
        if kd_match:
            mapped = _map_key(kd_match.group(1))
            line = f"from pynput.keyboard import Controller as KeyboardController;kb=KeyboardController(); kb.press({mapped})"

        # keyUp -> pynput
        ku_match = re.match(r"pyautogui\.keyUp\(['\"](.+?)['\"]\)", line)
        if ku_match:
            mapped = _map_key(ku_match.group(1))
            line = f"from pynput.keyboard import Controller as KeyboardController;kb=KeyboardController(); kb.release({mapped})"

        # pyautogui.wait(N) -> time.sleep(N)
        wait_match = re.match(r"pyautogui\.wait\((\d+)\)", line)
        if wait_match:
            line = f"time.sleep({wait_match.group(1)})"

        # pyautogui.terminate(...) -> DONE
        if line.startswith("pyautogui.terminate("):
            line = "DONE"

        fixed.append(line)
    return "\n".join(fixed)


def parse_response_to_cot_and_action(input_string, screen_size, coordinate_type):
    """Parse response including Observation, Thought, Action and code block.
    Copied from official opencua_agent.py."""
    sections = {}
    try:
        obs_match = re.search(
            r'^##\s*Observation\s*:?[\n\r]+(.*?)(?=^##\s*Thought:|^##\s*Action:|^##|\Z)',
            input_string, re.DOTALL | re.MULTILINE)
        if obs_match:
            sections['observation'] = obs_match.group(1).strip()

        thought_match = re.search(
            r'^##\s*Thought\s*:?[\n\r]+(.*?)(?=^##\s*Action:|^##|\Z)',
            input_string, re.DOTALL | re.MULTILINE)
        if thought_match:
            sections['thought'] = thought_match.group(1).strip()

        action_match = re.search(
            r'^##\s*Action\s*:?[\n\r]+(.*?)(?=^##|\Z)',
            input_string, re.DOTALL | re.MULTILINE)
        if action_match:
            sections['action'] = action_match.group(1).strip()

        code_blocks = re.findall(
            r'```(?:code|python)?\s*(.*?)\s*```',
            input_string, re.DOTALL | re.IGNORECASE)
        if not code_blocks:
            # Fallback: try <action>...</action> tags
            action_blocks = re.findall(
                r'<action>(.*?)</action>',
                input_string, re.DOTALL | re.IGNORECASE)
            if action_blocks:
                code_blocks = action_blocks
            else:
                logger.error("No code blocks found in the input string")
                return f"<Error>: no code blocks found", ["FAIL"], sections
        code_block = code_blocks[-1].strip()
        sections['original_code'] = code_block

        if "computer.wait" in code_block.lower():
            sections["code"] = "WAIT"
            return sections.get('action', ''), ["WAIT"], sections

        elif "computer.terminate" in code_block.lower():
            lower_block = code_block.lower()
            if ("failure" in lower_block) or ("fail" in lower_block):
                sections['code'] = "FAIL"
                return code_block, ["FAIL"], sections
            elif "success" in lower_block:
                sections['code'] = "DONE"
                return code_block, ["DONE"], sections
            else:
                return f"<Error>: terminate without status", ["FAIL"], sections

        corrected_code = code_block
        sections['code'] = corrected_code
        sections['code'] = project_coordinate_to_absolute_scale(
            corrected_code,
            screen_width=screen_size[0],
            screen_height=screen_size[1],
            coordinate_type=coordinate_type,
        )
        sections['code'] = normalize_pyautogui_code(sections['code'])

        if not sections.get('code'):
            return f"<Error>: no code parsed", ["FAIL"], sections
        if not sections.get('action'):
            sections['action'] = "Performing action"

        return sections['action'], [sections['code']], sections

    except Exception as e:
        return f"<Error>: {e}", ['FAIL'], sections


def project_coordinate_to_absolute_scale(pyautogui_code, screen_width, screen_height, coordinate_type="qwen25"):
    """Convert coordinates in pyautogui code to absolute screen coordinates.
    Copied from official opencua_agent.py."""

    def _coordinate_projection(x, y, sw, sh, ct):
        if ct == "relative":
            return int(round(x * sw)), int(round(y * sh))
        elif ct == "qwen25":
            height, width = smart_resize(
                height=sh, width=sw, factor=28, min_pixels=3136, max_pixels=12845056)
            if 0 <= x <= 1 and 0 <= y <= 1:
                return int(round(x * width)), int(round(y * height))
            return int(x / width * sw), int(y / height * sh)
        else:
            raise ValueError(f"Invalid coordinate type: {ct}")

    pattern = r'(pyautogui\.\w+\([^\)]*\))'
    matches = re.findall(pattern, pyautogui_code)
    new_code = pyautogui_code

    for full_call in matches:
        func_match = re.match(r'(pyautogui\.\w+)\((.*)\)', full_call, re.DOTALL)
        if not func_match:
            continue
        func_name = func_match.group(1)
        args_str = func_match.group(2)

        try:
            parsed = ast.parse(f"func({args_str})").body[0].value
            parsed_args = parsed.args
            parsed_keywords = parsed.keywords
        except SyntaxError:
            return pyautogui_code

        function_parameters = {
            'click': ['x', 'y', 'clicks', 'interval', 'button', 'duration', 'pause'],
            'rightClick': ['x', 'y', 'duration', 'tween', 'pause'],
            'middleClick': ['x', 'y', 'duration', 'tween', 'pause'],
            'doubleClick': ['x', 'y', 'interval', 'button', 'duration', 'pause'],
            'tripleClick': ['x', 'y', 'interval', 'button', 'duration', 'pause'],
            'moveTo': ['x', 'y', 'duration', 'tween', 'pause'],
            'dragTo': ['x', 'y', 'duration', 'button', 'mouseDownUp', 'pause'],
        }

        func_base = func_name.split('.')[-1]
        param_names = function_parameters.get(func_base, [])

        args = {}
        for idx, arg in enumerate(parsed_args):
            if idx < len(param_names):
                args[param_names[idx]] = ast.literal_eval(arg)
        for kw in parsed_keywords:
            try:
                args[kw.arg] = ast.literal_eval(kw.value)
            except:
                return pyautogui_code

        updated = False
        if 'x' in args and 'y' in args:
            try:
                x_abs, y_abs = _coordinate_projection(
                    float(args['x']), float(args['y']),
                    screen_width, screen_height, coordinate_type)
                args['x'] = x_abs
                args['y'] = y_abs
                updated = True
            except ValueError:
                pass

        if updated:
            reconstructed = []
            for pn in param_names:
                if pn in args:
                    v = args[pn]
                    reconstructed.append(f"'{v}'" if isinstance(v, str) else str(v))
                else:
                    break
            used = set(param_names[:len(reconstructed)])
            for kw in parsed_keywords:
                if kw.arg not in used:
                    v = args[kw.arg]
                    reconstructed.append(f"{kw.arg}='{v}'" if isinstance(v, str) else f"{kw.arg}={v}")
            new_code = new_code.replace(full_call, f"{func_name}({', '.join(reconstructed)})")

    return new_code


class OpenCUAAgent:
    def __init__(
            self,
            model: str = "OpenCUA-32B",
            base_url: str = "",
            api_key: str = "empty",
            platform: str = "macos",
            max_tokens: int = 4096,
            top_p: float = 0.9,
            temperature: float = 0.0,
            cot_level: str = "l2",
            coordinate_type: str = "qwen25",
            history_type: str = "action_history",
            max_image_history_length: int = 3,
            screen_size: Tuple[int, int] = (1920, 1080),
            use_old_sys_prompt: bool = True,
            password: str = "1234",
    ):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.platform = platform
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.temperature = temperature
        self.coordinate_type = coordinate_type
        self.screen_size = screen_size
        self.max_image_history_length = max_image_history_length

        # History template
        if history_type == "action_history":
            self.HISTORY_TEMPLATE = ACTION_HISTORY_TEMPLATE
        elif history_type == "thought_history":
            self.HISTORY_TEMPLATE = THOUGHT_HISTORY_TEMPLATE
        elif history_type == "observation_history":
            self.HISTORY_TEMPLATE = OBSERVATION_HISTORY_TEMPLATE
        else:
            raise ValueError(f"Invalid history type: {history_type}")

        # System prompt
        if use_old_sys_prompt:
            if cot_level == "l1":
                self.system_prompt = SYSTEM_PROMPT_V1_L1
            elif cot_level == "l2":
                self.system_prompt = SYSTEM_PROMPT_V1_L2
            elif cot_level == "l3":
                self.system_prompt = SYSTEM_PROMPT_V1_L3
            else:
                raise ValueError(f"Invalid cot_level: {cot_level}")
        else:
            self.system_prompt = build_sys_prompt(
                level=cot_level,
                password=password,
                use_random=False,
            )

        self.actions = []
        self.observations = []
        self.cots = []

        self.step_input_tokens = 0
        self.step_output_tokens = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def predict(self, instruction: str, obs: Dict) -> Tuple[str, List[str]]:
        messages = [{"role": "system", "content": self.system_prompt}]
        instruction_prompt = INSTRUTION_TEMPLATE.format(instruction=instruction)

        # Build history
        history_step_texts = []
        for i in range(len(self.actions)):
            if i > len(self.actions) - self.max_image_history_length:
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encode_image(self.observations[i]['screenshot'])}"}
                    }]
                })
                history_content = STEP_TEMPLATE.format(step_num=i + 1) + self.HISTORY_TEMPLATE.format(
                    observation=self.cots[i].get('observation'),
                    thought=self.cots[i].get('thought'),
                    action=self.cots[i].get('action'))
                messages.append({"role": "assistant", "content": history_content})
            else:
                history_content = STEP_TEMPLATE.format(step_num=i + 1) + self.HISTORY_TEMPLATE.format(
                    observation=self.cots[i].get('observation'),
                    thought=self.cots[i].get('thought'),
                    action=self.cots[i].get('action'))
                history_step_texts.append(history_content)
                if i == len(self.actions) - self.max_image_history_length:
                    messages.append({"role": "assistant", "content": "\n".join(history_step_texts)})

        # Current observation
        messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image(obs['screenshot'])}"}},
                {"type": "text", "text": instruction_prompt},
            ]
        })

        # Call LLM with retry
        response_text = ""
        pyautogui_actions = ["FAIL"]
        other_cot = {}

        for retry in range(5):
            try:
                response_text = self.call_llm(messages)
                if not response_text:
                    raise ValueError("Empty response")

                print(f"[DEBUG] Raw response (first 300): {response_text[:300]}")

                low_level_instruction, pyautogui_actions, other_cot = parse_response_to_cot_and_action(
                    response_text, self.screen_size, self.coordinate_type)

                print(f"[DEBUG] Parsed action: {low_level_instruction[:100] if low_level_instruction else 'None'}")
                print(f"[DEBUG] Parsed code: {pyautogui_actions}")
                print(f"[DEBUG] Sections keys: {list(other_cot.keys())}")

                if "<Error>" in str(low_level_instruction):
                    raise ValueError(low_level_instruction)
                break
            except Exception as e:
                logger.error(f"Retry {retry + 1}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                if retry == 4:
                    return str(e), ["FAIL"]

        self.observations.append(obs)
        self.actions.append(other_cot.get('action', ''))
        self.cots.append(other_cot)

        return response_text, pyautogui_actions

    def call_llm(self, messages):
        client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        for _ in range(5):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    top_p=self.top_p,
                    temperature=self.temperature,
                )
                usage = response.usage
                if usage:
                    self.step_input_tokens = usage.prompt_tokens or 0
                    self.step_output_tokens = usage.completion_tokens or 0
                    self.total_input_tokens += self.step_input_tokens
                    self.total_output_tokens += self.step_output_tokens
                return response.choices[0].message.content or ""
            except Exception as e:
                logger.error(f"LLM call error: {e}")
                time.sleep(5)
        return ""

    def reset(self, _logger=None):
        global logger
        if _logger is not None:
            logger = _logger
        self.observations = []
        self.cots = []
        self.actions = []
        self.step_input_tokens = 0
        self.step_output_tokens = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
