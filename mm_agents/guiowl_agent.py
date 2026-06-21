"""
GUI-Owl-1.5 agent for MacAgentBench evaluation.
Strictly follows the official implementation from:
  https://github.com/X-PLUG/MobileAgent/blob/main/Mobile-Agent-v3.5/computer_use/
"""

import ast
import base64
import json
import logging
import os
import re
import time
from io import BytesIO
from typing import Dict, List, Tuple

from openai import OpenAI
from PIL import Image

logger = logging.getLogger("desktopenv.guiowl_agent")

# Official smart_resize: factor=16
def smart_resize(height, width, factor=16, min_pixels=3136, max_pixels=10035200):
    """Qwen-VL style resize with factor alignment."""
    import math
    if max(height, width) / min(height, width) > 200:
        raise ValueError(f"Aspect ratio too large: {max(height, width) / min(height, width)}")
    h_bar = max(factor, round(height / factor) * factor)
    w_bar = max(factor, round(width / factor) * factor)
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = math.floor(height / beta / factor) * factor
        w_bar = math.floor(width / beta / factor) * factor
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = math.ceil(height * beta / factor) * factor
        w_bar = math.ceil(width * beta / factor) * factor
    return h_bar, w_bar


def pil_to_base64(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def process_image(image_bytes):
    """Process image using official GUI-Owl parameters: factor=16, PNG format."""
    image = Image.open(BytesIO(image_bytes))
    width, height = image.size
    resized_height, resized_width = smart_resize(
        height, width, factor=16, min_pixels=3136, max_pixels=10035200,
    )
    image = image.resize((resized_width, resized_height))
    return pil_to_base64(image), resized_width, resized_height


# Official SYSTEM_PROMPT from utils.py
SYSTEM_PROMPT = (
    '# Tools\n\n'
    'You may call one or more functions to assist with the user query.\n\n'
    'You are provided with function signatures within <tools></tools> XML tags:\n'
    '<tools>\n'
    '{"type": "function", "function": {"name": "computer_use", '
    '"description": "Use a mouse and keyboard to interact with a computer, '
    'and take screenshots.\\n'
    '* This is an interface to a desktop GUI. You do not have access to a '
    'terminal or applications menu. You must click on desktop icons to start '
    'applications.\\n'
    '* Some applications may take time to start or process actions, so you '
    'may need to wait and take successive screenshots to see the results of '
    'your actions. E.g. if you click on Firefox and a window doesn\'t open, '
    'try wait and taking another screenshot.\\n'
    '* The screen\'s resolution is 1000x1000.\\n'
    '* Make sure to click any buttons, links, icons, etc with the cursor tip '
    'in the center of the element. Don\'t click boxes on their edges unless '
    'asked.", '
    '"parameters": {"properties": {"action": {"description": '
    '"The action to perform. The available actions are:\\n'
    '* `key`: Performs key down presses on the arguments passed in order, '
    'then performs key releases in reverse order.\\n'
    '* `type`: Type a string of text on the keyboard.\\n'
    '* `mouse_move`: Move the cursor to a specified (x, y) pixel coordinate '
    'on the screen.\\n'
    '* `left_click`: Click the left mouse button at a specified (x, y) pixel '
    'coordinate on the screen.\\n'
    '* `left_click_drag`: Click and drag the cursor to a specified (x, y) '
    'pixel coordinate on the screen.\\n'
    '* `right_click`: Click the right mouse button at a specified (x, y) '
    'pixel coordinate on the screen.\\n'
    '* `middle_click`: Click the middle mouse button at a specified (x, y) '
    'pixel coordinate on the screen.\\n'
    '* `double_click`: Double-click the left mouse button at a specified '
    '(x, y) pixel coordinate on the screen.\\n'
    '* `triple_click`: Triple-click the left mouse button at a specified '
    '(x, y) pixel coordinate on the screen.\\n'
    '* `scroll`: Performs a scroll of the mouse scroll wheel.\\n'
    '* `hscroll`: Performs a horizontal scroll.\\n'
    '* `wait`: Wait specified seconds for the change to happen.\\n'
    '* `terminate`: Terminate the current task and report its completion '
    'status.\\n'
    '* `answer`: Answer a question.\\n'
    '* `interact`: Resolve the blocking window by interacting with the user.", '
    '"enum": ["key", "type", "mouse_move", "left_click", "left_click_drag", '
    '"right_click", "middle_click", "double_click", "triple_click", "scroll", '
    '"hscroll", "wait", "terminate", "answer", "interact"], "type": "string"}, '
    '"keys": {"description": "Required only by `action=key`.", '
    '"type": "array"}, '
    '"text": {"description": "Required only by `action=type`, `action=answer` '
    'and `action=interact`.", "type": "string"}, '
    '"coordinate": {"description": "(x, y): The x (pixels from the left edge) '
    'and y (pixels from the top edge) coordinates to move the mouse to. '
    'Required only by `action=mouse_move` and `action=left_click_drag`.", '
    '"type": "array"}, '
    '"pixels": {"description": "The amount of scrolling to perform. Positive '
    'values scroll up, negative values scroll down. Required only by '
    '`action=scroll` and `action=hscroll`.", "type": "number"}, '
    '"time": {"description": "The seconds to wait. Required only by '
    '`action=wait`.", "type": "number"}, '
    '"status": {"description": "The status of the task. Required only by '
    '`action=terminate`.", "type": "string", "enum": ["success", "failure"]}}, '
    '"required": ["action"], "type": "object"}}}\n'
    '</tools>\n\n'
    'For each function call, return a json object with function name and '
    'arguments within <tool_call></tool_call> XML tags:\n'
    '<tool_call>\n'
    '{"name": <function-name>, "arguments": <args-json-object>}\n'
    '</tool_call>\n\n'
    '# Response format\n\n'
    'Response format for every step:\n'
    '1) Action: a short imperative describing what to do in the UI.\n'
    '2) A single <tool_call>...</tool_call> block containing only the JSON: '
    '{"name": <function-name>, "arguments": <args-json-object>}.\n\n'
    'Rules:\n'
    '- Output exactly in the order: Action, <tool_call>.\n'
    '- Be brief: one for Action.\n'
    '- Do not output anything else outside those two parts.\n'
    '- If finishing, use action=terminate in the tool call.'
)


class GUIOwlAgent:
    def __init__(
            self,
            platform: str = "macos",
            model: str = "GUI-Owl-1.5-32B-Think",
            base_url: str = "",
            api_key: str = "empty",
            max_tokens: int = 4096,
            top_p: float = 0.9,
            temperature: float = 0.0,
            action_space: str = "pyautogui",
            observation_type: str = "screenshot",
            history_n: int = 4,  # Official default
    ):
        self.platform = platform
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.temperature = temperature
        self.action_space = action_space
        self.observation_type = observation_type
        self.history_n = history_n

        self.thoughts = []
        self.actions = []
        self.observations = []
        self.responses = []
        self.screenshots = []  # base64 strings

        self.step_input_tokens = 0
        self.step_output_tokens = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def predict(self, instruction: str, obs: Dict) -> List:
        screenshot_bytes = obs["screenshot"]

        image = Image.open(BytesIO(screenshot_bytes))
        original_width, original_height = image.size

        img_b64, resized_width, resized_height = process_image(screenshot_bytes)
        self.screenshots.append(img_b64)

        current_step = len(self.actions)
        history_start_idx = max(0, current_step - self.history_n)

        # Summarize early actions (official style)
        previous_actions = []
        for i in range(history_start_idx):
            if i < len(self.responses):
                text = self.responses[i]
                if "Action:" in text and "<tool_call>" in text:
                    text = text.split("Action:")[1].split("<tool_call>")[0].strip()
                previous_actions.append(f"Step {i + 1}: {text}")
        previous_actions_str = "\n".join(previous_actions) if previous_actions else "None"

        instruction_prompt = (
            "Please generate the next move according to the UI screenshot, "
            "instruction and previous actions.\n\n"
            f"Instruction: {instruction}\n\n"
            f"Previous actions:\n{previous_actions_str}"
        )

        # Build messages (official format)
        messages = [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
        ]

        history_len = min(self.history_n, len(self.responses))
        if history_len > 0:
            history_responses = self.responses[-history_len:]
            history_screenshots = self.screenshots[-history_len - 1:-1]

            for idx in range(history_len):
                if idx < len(history_screenshots):
                    img_url = f"data:image/png;base64,{history_screenshots[idx]}"
                    if idx == 0:
                        messages.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": instruction_prompt},
                                {"type": "image_url", "image_url": {"url": img_url}},
                            ],
                        })
                    else:
                        messages.append({
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": img_url}},
                            ],
                        })
                messages.append({
                    "role": "assistant",
                    "content": [{"type": "text", "text": history_responses[idx]}],
                })

            curr_img_url = f"data:image/png;base64,{img_b64}"
            messages.append({
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": curr_img_url}},
                ],
            })
        else:
            curr_img_url = f"data:image/png;base64,{img_b64}"
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction_prompt},
                    {"type": "image_url", "image_url": {"url": curr_img_url}},
                ],
            })

        # Call LLM (official: no extra params)
        response = self.call_llm(messages)

        # Parse response
        low_level_instruction, pyautogui_code, action_str = self.parse_response(
            response, original_width, original_height, resized_width, resized_height,
        )

        self.responses.append(response)
        self.actions.append(low_level_instruction)
        return response, pyautogui_code

    def parse_response(self, response, original_width, original_height,
                       resized_width, resized_height):
        low_level_instruction = ""
        pyautogui_code = []
        action_str = []

        def rescale(x, y):
            """Official: coordinate / 1000 * resized, then resized -> original."""
            rx = int(x / 1000 * resized_width)
            ry = int(y / 1000 * resized_height)
            ox = int(rx / resized_width * original_width)
            oy = int(ry / resized_height * original_height)
            return ox, oy

        # Official: extract_tool_calls using regex + ast.literal_eval
        pattern = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL | re.IGNORECASE)
        blocks = pattern.findall(response)

        for blk in blocks:
            blk = blk.strip()
            try:
                tool_call = ast.literal_eval(blk)
            except (ValueError, SyntaxError):
                try:
                    tool_call = json.loads(blk)
                except:
                    continue

            if tool_call.get("name") != "computer_use":
                continue
            args = tool_call.get("arguments", {})
            action = args.get("action", "")

            # Official action mapping from run_gui_owl_1_5_for_pc.py
            if action in ("click", "left_click"):
                if "coordinate" in args:
                    x, y = args["coordinate"]
                    ox, oy = rescale(x, y)
                    pyautogui_code.append(f"pyautogui.click({ox}, {oy})")
                    action_str.append(f"left_click({x}, {y})")

            elif action in ("right_click", "right click"):
                if "coordinate" in args:
                    x, y = args["coordinate"]
                    ox, oy = rescale(x, y)
                    pyautogui_code.append(f"pyautogui.rightClick({ox}, {oy})")
                    action_str.append(f"right_click({x}, {y})")

            elif action == "middle_click":
                if "coordinate" in args:
                    x, y = args["coordinate"]
                    ox, oy = rescale(x, y)
                    pyautogui_code.append(f"pyautogui.middleClick({ox}, {oy})")
                    action_str.append(f"middle_click({x}, {y})")

            elif action in ("double_click", "computer_double_click"):
                if "coordinate" in args:
                    x, y = args["coordinate"]
                    ox, oy = rescale(x, y)
                    pyautogui_code.append(f"pyautogui.doubleClick({ox}, {oy})")
                    action_str.append(f"double_click({x}, {y})")

            elif action == "triple_click":
                if "coordinate" in args:
                    x, y = args["coordinate"]
                    ox, oy = rescale(x, y)
                    pyautogui_code.append(f"pyautogui.doubleClick({ox}, {oy})")
                    action_str.append(f"triple_click({x}, {y})")

            elif action == "mouse_move":
                if "coordinate" in args:
                    x, y = args["coordinate"]
                    ox, oy = rescale(x, y)
                    pyautogui_code.append(f"pyautogui.moveTo({ox}, {oy})")
                    action_str.append(f"mouse_move({x}, {y})")

            elif action == "left_click_drag":
                if "coordinate" in args:
                    x, y = args["coordinate"]
                    ox, oy = rescale(x, y)
                    pyautogui_code.append(f"pyautogui.dragTo({ox}, {oy}, button='left', duration=1.0)")
                    action_str.append(f"drag({x}, {y})")

            elif action == "type":
                text = args.get("text", "")
                # Split \n into separate typewrite + enter
                lines = text.split("\n")
                for i, line in enumerate(lines):
                    if line:
                        pyautogui_code.append(f"pyautogui.typewrite({repr(line)})")
                    if i < len(lines) - 1:
                        pyautogui_code.append("pyautogui.press('enter')")
                action_str.append(f"type('{text}')")

            elif action in ("key", "hotkey"):
                keys = args.get("keys", [])
                if isinstance(keys, list) and keys:
                    cleaned = [str(k).lower().replace("command", "cmd").replace("control", "ctrl") for k in keys]
                    if len(cleaned) == 1:
                        pyautogui_code.append(f"pyautogui.press('{cleaned[0]}')")
                    else:
                        pyautogui_code.append(f"pyautogui.hotkey({', '.join(repr(k) for k in cleaned)})")
                    action_str.append(f"key({cleaned})")

            elif action == "scroll":
                pixels = args.get("pixels", 0)
                if not pixels:
                    direction = args.get("direction", "down")
                    amount = args.get("amount", 3)
                    pixels = -amount if direction == "down" else amount
                if "coordinate" in args:
                    x, y = args["coordinate"]
                    ox, oy = rescale(x, y)
                    pyautogui_code.append(f"pyautogui.moveTo({ox}, {oy})")
                pyautogui_code.append(f"pyautogui.scroll({pixels})")
                action_str.append(f"scroll({pixels})")

            elif action == "wait":
                wait_time = args.get("time", 2)
                pyautogui_code.append(f"WAIT")
                action_str.append(f"wait({wait_time})")

            elif action in ("terminate", "stop", "done"):
                pyautogui_code.append("DONE")
                action_str.append("terminate()")

            elif action == "answer":
                pyautogui_code.append("DONE")
                action_str.append(f"answer({args.get('text', '')})")

        # Extract Action: line for low_level_instruction
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("Action:"):
                low_level_instruction = line.split("Action:")[1].strip()
                break

        if not low_level_instruction and pyautogui_code:
            low_level_instruction = "Performing action"

        return low_level_instruction, pyautogui_code, action_str

    def call_llm(self, messages):
        client = OpenAI(base_url=self.base_url, api_key=self.api_key)

        for _ in range(5):
            try:
                # Official: no extra params (no max_tokens, temperature, top_p)
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                )
                usage = response.usage
                if usage:
                    self.step_input_tokens = usage.prompt_tokens or 0
                    self.step_output_tokens = usage.completion_tokens or 0
                    self.total_input_tokens += self.step_input_tokens
                    self.total_output_tokens += self.step_output_tokens
                return response.choices[0].message.content or ""
            except Exception as e:
                logger.error(f"Error calling GUI-Owl: {e}")
                time.sleep(5)
        return ""

    def reset(self, _logger=None):
        global logger
        if _logger is not None:
            logger = _logger
        self.thoughts = []
        self.actions = []
        self.observations = []
        self.responses = []
        self.screenshots = []
        self.step_input_tokens = 0
        self.step_output_tokens = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
