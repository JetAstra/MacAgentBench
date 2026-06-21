import re
import time
from io import BytesIO
from PIL import Image

from typing import Tuple, Dict

from gui_agents.s3.memory.procedural_memory import PROCEDURAL_MEMORY

import logging

import requests

logger = logging.getLogger("desktopenv.agent")


def create_pyautogui_code(agent, code: str, obs: Dict) -> str:
    """
    Attempts to evaluate the code into a pyautogui code snippet with grounded actions using the observation screenshot.

    Args:
        agent (ACI): The grounding agent to use for evaluation.
        code (str): The code string to evaluate.
        obs (Dict): The current observation containing the screenshot.

    Returns:
        exec_code (str): The pyautogui code to execute the grounded action.

    Raises:
        Exception: If there is an error in evaluating the code.
    """
    agent.assign_screenshot(obs)  # Necessary for grounding
    exec_code = eval(code)
    return exec_code


def call_llm_safe(
    agent, temperature: float = 0.0, use_thinking: bool = False, **kwargs
) -> str:
    """Call agent.get_response with simple retry, with extra logging for debugging."""
    max_retries = 3
    attempt = 0
    response = ""
    if not temperature:
        temperature = 0.0
    # Best-effort introspection for easier debugging in logs
    engine = getattr(agent, "engine", None)
    model_name = getattr(engine, "model", "<unknown-model>")
    base_url = getattr(engine, "base_url", getattr(engine, "endpoint", "<unknown-url>"))

    messages = kwargs.get("messages")
    if messages is not None:
        # Very verbose debug log of request content. Do NOT enable in production.
        try:
            def _shorten(text: str, n: int = 200) -> str:
                return text if len(text) <= n else text[:n] + "...[truncated]"

            for idx, msg in enumerate(messages):
                role = msg.get("role")
                parts = msg.get("content", [])
                texts = []
                images = []
                for c in parts:
                    if c.get("type") == "text":
                        texts.append(_shorten(c.get("text", "")))
                    elif c.get("type") == "image_url":
                        url = c.get("image_url", {}).get("url", "")
                        images.append(
                            f"url_prefix={_shorten(url[:128], 128)}, len={len(url)}"
                        )
                logger.info(
                    "LLM request message[%d] role=%s text=%s images=%s temperature=%s" ,
                    idx,
                    role,
                    texts,
                    images,
                    temperature
                )
        except Exception as e:
            logger.warning("Failed to log LLM request messages: %s", e)

    # Hard wall-clock budget for the whole retry loop. Individual attempts have
    # been observed to hang up to ~1800s on APIConnectionError when the request
    # body exceeds upstream limits; without this cap call_llm_safe can block a
    # step for hours.
    budget_seconds = 300
    budget_deadline = time.time() + budget_seconds
    while attempt < max_retries:
        if time.time() > budget_deadline:
            logger.error(
                "call_llm_safe wall-clock budget (%ds) exceeded for model=%s, base_url=%s, giving up",
                budget_seconds,
                model_name,
                base_url,
            )
            break
        try:
            t0 = time.time()
            resp = agent.get_response(
                temperature=temperature, use_thinking=use_thinking, **kwargs
            )
            if isinstance(resp, str):
                response = resp
            else:
                response = resp["text"]
            # response = resp["text"]
            usage = resp.get("usage", {})

            input_tokens = usage.get("prompt_tokens")
            output_tokens = usage.get("completion_tokens")
            
            dt = time.time() - t0
            assert response is not None, "Response from agent should not be None"
            print("Response success!")
            logger.info(
                "LLM call success on attempt %d (model=%s, base_url=%s, %.2fs), input=%s output=%s total=%s",
                attempt + 1,
                model_name,
                base_url,
                dt,
                input_tokens,
                output_tokens,
                usage.get("total_tokens"),
            )
            break
        except Exception as e:
            attempt += 1
            dt = time.time() - t0 if "t0" in locals() else 0.0
            print(f"Attempt {attempt} failed: {e}")
            logger.warning(
                "LLM call failed on attempt %d (model=%s, base_url=%s, %.2fs): %s",
                attempt,
                model_name,
                base_url,
                dt,
                repr(e),
            )
            # Request body too large is deterministic: every retry ships the
            # same oversized context, so bail instead of burning more calls.
            if "30.000MB" in str(e):
                logger.error(
                    "Request body exceeds API size limit, skipping remaining retries: %s",
                    e,
                )
                break
            if attempt == max_retries:
                print("Max retries reached. Handling failure.")
                logger.error(
                    "Max retries (%d) reached for model=%s, base_url=%s",
                    max_retries,
                    model_name,
                    base_url,
                )
        time.sleep(1.0)
    return response if response is not None else ""

def call_llm_formatted(generator, format_checkers, **kwargs):
    """
    Calls the generator agent's LLM and ensures correct formatting.

    Args:
        generator (ACI): The generator agent to call.
        obs (Dict): The current observation containing the screenshot.
        format_checkers (Callable): Functions that take the response and return a tuple of (success, feedback).
        **kwargs: Additional keyword arguments for the LLM call.

    Returns:
        response (str): The formatted response from the generator agent.
    """
    max_retries = 3  # Set the maximum number of retries
    attempt = 0
    response = ""
    if kwargs.get("messages") is None:
        messages = (
            generator.messages.copy()
        )  # Copy messages to avoid modifying the original
    else:
        messages = kwargs["messages"]
        del kwargs["messages"]  # Remove messages from kwargs to avoid passing it twice
    while attempt < max_retries:
        response = call_llm_safe(generator, messages=messages, **kwargs)

        # If the inner call gave up (context too large, budget exhausted,
        # max retries reached), it returns "". Running another outer iteration
        # just drives another full inner retry cycle against the same payload.
        if not response:
            logger.error(
                "call_llm_formatted giving up on attempt %d: inner returned empty response",
                attempt,
            )
            break

        # Prepare feedback messages for incorrect formatting
        feedback_msgs = []
        for format_checker in format_checkers:
            success, feedback = format_checker(response)
            if not success:
                feedback_msgs.append(feedback)
        if not feedback_msgs:
            # logger.info(f"Response formatted correctly on attempt {attempt} for {generator.engine.model}")
            break
        logger.error(
            f"Response formatting error on attempt {attempt} for {generator.engine.model}. Response: {response} {', '.join(feedback_msgs)}"
        )
        messages.append(
            {
                "role": "assistant",
                "content": [{"type": "text", "text": response}],
            }
        )
        logger.info(f"Bad response: {response}")
        delimiter = "\n- "
        formatting_feedback = f"- {delimiter.join(feedback_msgs)}"
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": PROCEDURAL_MEMORY.FORMATTING_FEEDBACK_PROMPT.replace(
                            "FORMATTING_FEEDBACK", formatting_feedback
                        ),
                    }
                ],
            }
        )
        logger.info("Feedback:\n%s", formatting_feedback)

        attempt += 1
        if attempt == max_retries:
            logger.error(
                "Max retries reached when formatting response. Handling failure."
            )
        time.sleep(1.0)
    return response


def split_thinking_response(full_response: str) -> Tuple[str, str]:
    try:
        # Extract thoughts section
        thoughts = full_response.split("<thoughts>")[-1].split("</thoughts>")[0].strip()

        # Extract answer section
        answer = full_response.split("<answer>")[-1].split("</answer>")[0].strip()

        return answer, thoughts
    except Exception as e:
        return full_response, ""


def parse_code_from_string(input_string):
    """Parses a string to extract each line of code enclosed in triple backticks (```)

    Args:
        input_string (str): The input string containing code snippets.

    Returns:
        str: The last code snippet found in the input string, or an empty string if no code is found.
    """
    input_string = input_string.strip()

    # This regular expression will match both ```code``` and ```python code```
    # and capture the `code` part. It uses a non-greedy match for the content inside.
    pattern = r"```(?:\w+\s+)?(.*?)```"

    # Find all non-overlapping matches in the string
    matches = re.findall(pattern, input_string, re.DOTALL)
    if len(matches) == 0:
        # return []
        return ""
    relevant_code = matches[
        -1
    ]  # We only care about the last match given it is the grounded action
    return relevant_code


def extract_agent_functions(code):
    """Extracts all agent function calls from the given code.

    Args:
        code (str): The code string to search for agent function calls.

    Returns:
        list: A list of all agent function calls found in the code.
    """
    pattern = r"(agent\.\w+\(\s*.*\))"  # Matches
    return re.findall(pattern, code)


def compress_image(image_bytes: bytes = None, image: Image = None) -> bytes:
    """Compresses an image represented as bytes.

    Compression involves resizing image into half its original size and saving to webp format.

    Args:
        image_bytes (bytes): The image data to compress.

    Returns:
        bytes: The compressed image data.
    """
    if not image:
        image = Image.open(BytesIO(image_bytes))
    output = BytesIO()
    image.save(output, format="WEBP")
    compressed_image_bytes = output.getvalue()
    return compressed_image_bytes
