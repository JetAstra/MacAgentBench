import os
import logging

import backoff
from anthropic import Anthropic
from openai import (
    AzureOpenAI,
    APIConnectionError,
    APIError,
    AzureOpenAI,
    OpenAI,
    RateLimitError,
)

logger = logging.getLogger(__name__)

def _anthropic_usage_to_openai_shape(message):
    """Map Anthropic Message.usage to OpenAI-style prompt/completion/total fields."""
    usage_obj = getattr(message, "usage", None)
    if usage_obj is None:
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }
    pt = getattr(usage_obj, "input_tokens", None)
    ct = getattr(usage_obj, "output_tokens", None)
    tt = pt + ct if pt is not None and ct is not None else None
    return {
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": tt,
    }


def _anthropic_assistant_text(message):
    """Concatenate assistant-visible text blocks (skip thinking blocks)."""
    parts = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts) if parts else None


# --- Request size guard (Anthropic has a hard 30 MB per-request limit) ---
# Trim oldest image blocks from the outgoing messages until the request fits.
# Leaves text content intact so the model still has step history, only the
# oldest screenshots (which it already acted on) are dropped.

_ANTHROPIC_REQUEST_LIMIT_BYTES = 28 * 1024 * 1024  # 2 MB headroom below 30 MB


def _estimate_anthropic_message_size(messages) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total += len(content)
            continue
        if not isinstance(content, list):
            continue
        for c in content:
            t = c.get("type", "")
            if t == "text":
                total += len(c.get("text", ""))
            elif t == "image":
                total += len(c.get("source", {}).get("data", ""))
            elif t == "image_url":
                total += len(c.get("image_url", {}).get("url", ""))
    return total


def _trim_anthropic_images_to_fit(messages, limit: int = _ANTHROPIC_REQUEST_LIMIT_BYTES):
    """Return (new_messages, n_images_dropped). Does not mutate the input list."""
    # Shallow-copy messages and their content lists so we can safely mutate.
    trimmed = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            trimmed.append({**m, "content": list(content)})
        else:
            trimmed.append(dict(m))

    dropped = 0
    # Walk from oldest to newest; drop image blocks from each message until the
    # total is under the limit. Stop as soon as we're within budget.
    for m in trimmed:
        if _estimate_anthropic_message_size(trimmed) <= limit:
            break
        content = m.get("content")
        if not isinstance(content, list):
            continue
        new_content = [c for c in content if c.get("type") not in ("image", "image_url")]
        if len(new_content) != len(content):
            dropped += len(content) - len(new_content)
            m["content"] = new_content
    return trimmed, dropped


class LMMEngine:
    pass


class LMMEngineOpenAI(LMMEngine):
    def __init__(
        self,
        base_url=None,
        api_key=None,
        model=None,
        rate_limit=-1,
        temperature=None,
        organization=None,
        **kwargs,
    ):
        assert model is not None, "model must be provided"
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.organization = organization
        self.request_interval = 0 if rate_limit == -1 else 60.0 / rate_limit
        self.llm_client = None
        self.temperature = temperature  # Can force temperature to be the same (in the case of o3 requiring temperature to be 1)
        # Optional per-request timeout (seconds). If OPENAI_HTTP_TIMEOUT is set, use it.
        try:
            # self.timeout = float(os.getenv("OPENAI_HTTP_TIMEOUT", "0")) or None
            self.timeout = 100
        except Exception:
            self.timeout = None

    @backoff.on_exception(
        backoff.expo, (APIConnectionError, APIError, RateLimitError), max_time=120
    )
    def generate(self, messages, temperature=0.0, max_new_tokens=None, **kwargs):
        api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        if api_key is None:
            raise ValueError(
                "An API Key needs to be provided in either the api_key parameter or as an environment variable named OPENAI_API_KEY"
            )
        organization = self.organization or os.getenv("OPENAI_ORG_ID")
        if not self.llm_client:
            if not self.base_url:
                self.llm_client = OpenAI(
                    api_key=api_key,
                    organization=organization,
                    timeout=self.timeout,
                )
            else:
                self.llm_client = OpenAI(
                    base_url=self.base_url,
                    api_key=api_key,
                    organization=organization,
                    timeout=self.timeout,
                )
        resp = self.llm_client.chat.completions.create(
            model=self.model,
            messages=messages,
            # max_completion_tokens=max_new_tokens if max_new_tokens else 4096,
            temperature=(
                temperature if self.temperature is None else self.temperature
            ),
            **kwargs,
        )
        return {
            "text": resp.choices[0].message.content,
            "usage": {
                "prompt_tokens": resp.usage.prompt_tokens if resp.usage else None,
                "completion_tokens": resp.usage.completion_tokens if resp.usage else None,
                "total_tokens": resp.usage.total_tokens if resp.usage else None,
            }
        }


class LMMEngineAnthropic(LMMEngine):
    def __init__(
        self,
        base_url=None,
        api_key=None,
        model=None,
        thinking=False,
        temperature=None,
        **kwargs,
    ):
        assert model is not None, "model must be provided"
        self.model = model
        self.thinking = thinking
        self.base_url = base_url
        self.api_key = api_key
        self.llm_client = None
        self.temperature = temperature

    def _ensure_anthropic_client(self, api_key):
        """Anthropic SDK supports base_url for proxies / relay gateways (see ANTHROPIC_BASE_URL)."""
        if self.llm_client is None:
            client_kw = {"api_key": api_key, "timeout": 120, "max_retries": 0}
            base = self.base_url or os.getenv("ANTHROPIC_BASE_URL")
            if base:
                client_kw["base_url"] = base.rstrip("/")
            self.llm_client = Anthropic(**client_kw)

    @backoff.on_exception(
        backoff.expo, (APIConnectionError, APIError, RateLimitError), max_time=120
    )
    def generate(self, messages, temperature=0.0, max_new_tokens=None, **kwargs):
        api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if api_key is None:
            raise ValueError(
                "An API Key needs to be provided in either the api_key parameter or as an environment variable named ANTHROPIC_API_KEY"
            )
        # self.llm_client = Anthropic(api_key=api_key)
        self._ensure_anthropic_client(api_key)
        # Use the instance temperature if not specified in the call
        temp = self.temperature if temperature is None else temperature
        # Pre-flight size guard: Anthropic rejects requests >30 MB with a 400.
        # Strip oldest screenshots until the payload fits, so we never send
        # a request that is known-too-big.
        raw_size = _estimate_anthropic_message_size(messages)
        if raw_size > _ANTHROPIC_REQUEST_LIMIT_BYTES:
            messages, dropped = _trim_anthropic_images_to_fit(messages)
            logger.warning(
                "Pre-flight trimmed %d oldest image(s) to fit Anthropic request "
                "(raw=%d bytes, limit=%d bytes, trimmed=%d bytes)",
                dropped,
                raw_size,
                _ANTHROPIC_REQUEST_LIMIT_BYTES,
                _estimate_anthropic_message_size(messages),
            )
        if self.thinking:
            full_response = self.llm_client.messages.create(
                system=messages[0]["content"][0]["text"],
                model=self.model,
                messages=messages[1:],
                max_tokens=8192,
                thinking={"type": "enabled", "budget_tokens": 4096},
                **kwargs,
            )
            return {
                "text": _anthropic_assistant_text(full_response),
                "usage": _anthropic_usage_to_openai_shape(full_response),
            }
        resp = self.llm_client.messages.create(
            system=messages[0]["content"][0]["text"],
            model=self.model,
            messages=messages[1:],
            max_tokens=max_new_tokens if max_new_tokens else 4096,
            temperature=temp,
            **kwargs,
        )
        return {
            "text": _anthropic_assistant_text(resp),
            "usage": _anthropic_usage_to_openai_shape(resp),
        }

    @backoff.on_exception(
        backoff.expo, (APIConnectionError, APIError, RateLimitError), max_time=120
    )
    # Compatible with Claude-3.7 Sonnet thinking mode
    def generate_with_thinking(
        self, messages, temperature=0.0, max_new_tokens=None, **kwargs
    ):
        """Generate the next message based on previous messages, and keeps the thinking tokens"""
        api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if api_key is None:
            raise ValueError(
                "An API Key needs to be provided in either the api_key parameter or as an environment variable named ANTHROPIC_API_KEY"
            )
        # self.llm_client = Anthropic(api_key=api_key)
        self._ensure_anthropic_client(api_key)
        full_response = self.llm_client.messages.create(
            system=messages[0]["content"][0]["text"],
            model=self.model,
            messages=messages[1:],
            max_tokens=8192,
            thinking={"type": "enabled", "budget_tokens": 4096},
            **kwargs,
        )

        thoughts = full_response.content[0].thinking
        answer = full_response.content[1].text
        text = (
            f"<thoughts>\n{thoughts}\n</thoughts>\n\n<answer>\n{answer}\n</answer>\n"
        )
        return {
            "text": text,
            "usage": _anthropic_usage_to_openai_shape(full_response),
        }


class LMMEngineGemini(LMMEngine):
    def __init__(
        self,
        base_url=None,
        api_key=None,
        model=None,
        rate_limit=-1,
        temperature=None,
        **kwargs,
    ):
        assert model is not None, "model must be provided"
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.request_interval = 0 if rate_limit == -1 else 60.0 / rate_limit
        self.llm_client = None
        self.temperature = temperature

    @backoff.on_exception(
        backoff.expo, (APIConnectionError, APIError, RateLimitError), max_time=120
    )
    def generate(self, messages, temperature=0.0, max_new_tokens=None, **kwargs):
        api_key = self.api_key or os.getenv("GEMINI_API_KEY")
        if api_key is None:
            raise ValueError(
                "An API Key needs to be provided in either the api_key parameter or as an environment variable named GEMINI_API_KEY"
            )
        base_url = self.base_url or os.getenv("GEMINI_ENDPOINT_URL")
        if base_url is None:
            raise ValueError(
                "An endpoint URL needs to be provided in either the endpoint_url parameter or as an environment variable named GEMINI_ENDPOINT_URL"
            )
        if not self.llm_client:
            self.llm_client = OpenAI(base_url=base_url, api_key=api_key)
        # Use the temperature passed to generate, otherwise use the instance's temperature, otherwise default to 0.0
        temp = self.temperature if temperature is None else temperature
        return (
            self.llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_new_tokens if max_new_tokens else 4096,
                temperature=temp,
                **kwargs,
            )
            .choices[0]
            .message.content
        )


class LMMEngineOpenRouter(LMMEngine):
    def __init__(
        self,
        base_url=None,
        api_key=None,
        model=None,
        rate_limit=-1,
        temperature=None,
        **kwargs,
    ):
        assert model is not None, "model must be provided"
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.request_interval = 0 if rate_limit == -1 else 60.0 / rate_limit
        self.llm_client = None
        self.temperature = temperature

    @backoff.on_exception(
        backoff.expo, (APIConnectionError, APIError, RateLimitError), max_time=120
    )
    def generate(self, messages, temperature=0.0, max_new_tokens=None, **kwargs):
        api_key = self.api_key or os.getenv("OPENROUTER_API_KEY")
        if api_key is None:
            raise ValueError(
                "An API Key needs to be provided in either the api_key parameter or as an environment variable named OPENROUTER_API_KEY"
            )
        base_url = self.base_url or os.getenv("OPEN_ROUTER_ENDPOINT_URL")
        if base_url is None:
            raise ValueError(
                "An endpoint URL needs to be provided in either the endpoint_url parameter or as an environment variable named OPEN_ROUTER_ENDPOINT_URL"
            )
        if not self.llm_client:
            self.llm_client = OpenAI(base_url=base_url, api_key=api_key)
        # Use self.temperature if set, otherwise use the temperature argument
        temp = self.temperature if self.temperature is not None else temperature
        return (
            self.llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_new_tokens if max_new_tokens else 4096,
                temperature=temp,
                **kwargs,
            )
            .choices[0]
            .message.content
        )


class LMMEngineAzureOpenAI(LMMEngine):
    def __init__(
        self,
        base_url=None,
        api_key=None,
        azure_endpoint=None,
        model=None,
        api_version=None,
        rate_limit=-1,
        temperature=None,
        **kwargs,
    ):
        assert model is not None, "model must be provided"
        self.model = model
        self.api_version = api_version
        self.api_key = api_key
        self.azure_endpoint = azure_endpoint
        self.request_interval = 0 if rate_limit == -1 else 60.0 / rate_limit
        self.llm_client = None
        self.cost = 0.0
        self.temperature = temperature

    @backoff.on_exception(
        backoff.expo, (APIConnectionError, APIError, RateLimitError), max_time=120
    )
    def generate(self, messages, temperature=0.0, max_new_tokens=None, **kwargs):
        api_key = self.api_key or os.getenv("AZURE_OPENAI_API_KEY")
        if api_key is None:
            raise ValueError(
                "An API Key needs to be provided in either the api_key parameter or as an environment variable named AZURE_OPENAI_API_KEY"
            )
        api_version = self.api_version or os.getenv("OPENAI_API_VERSION")
        if api_version is None:
            raise ValueError(
                "api_version must be provided either as a parameter or as an environment variable named OPENAI_API_VERSION"
            )
        azure_endpoint = self.azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        if azure_endpoint is None:
            raise ValueError(
                "An Azure API endpoint needs to be provided in either the azure_endpoint parameter or as an environment variable named AZURE_OPENAI_ENDPOINT"
            )
        if not self.llm_client:
            self.llm_client = AzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_key=api_key,
                api_version=api_version,
            )
        # Use self.temperature if set, otherwise use the temperature argument
        temp = self.temperature if self.temperature is not None else temperature
        completion = self.llm_client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_new_tokens if max_new_tokens else 4096,
            temperature=temp,
            **kwargs,
        )
        total_tokens = completion.usage.total_tokens
        self.cost += 0.02 * ((total_tokens + 500) / 1000)
        return completion.choices[0].message.content


class LMMEnginevLLM(LMMEngine):
    def __init__(
        self,
        base_url=None,
        api_key=None,
        model=None,
        rate_limit=-1,
        temperature=None,
        **kwargs,
    ):
        assert model is not None, "model must be provided"
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.request_interval = 0 if rate_limit == -1 else 60.0 / rate_limit
        self.llm_client = None
        self.temperature = temperature
        # Align with OpenAI engine: optional per-request timeout
        try:
            self.timeout = 100
        except Exception:
            self.timeout = None

    @backoff.on_exception(
        backoff.expo, (APIConnectionError, APIError, RateLimitError), max_time=120
    )
    def generate(
        self,
        messages,
        temperature=0.0,
        top_p=0.8,
        repetition_penalty=1.05,
        max_new_tokens=512,
        **kwargs,
    ):
        api_key = self.api_key or os.getenv("vLLM_API_KEY")
        if api_key is None:
            raise ValueError(
                "A vLLM API key needs to be provided in either the api_key parameter or as an environment variable named vLLM_API_KEY"
            )
        base_url = self.base_url or os.getenv("vLLM_ENDPOINT_URL")
        if base_url is None:
            raise ValueError(
                "An endpoint URL needs to be provided in either the endpoint_url parameter or as an environment variable named vLLM_ENDPOINT_URL"
            )
        if not self.llm_client:
            self.llm_client = OpenAI(
                base_url=base_url,
                api_key=api_key,
                timeout=self.timeout,
            )
        # Use self.temperature if set, otherwise use the temperature argument
        temp = self.temperature if self.temperature is not None else temperature
        resp = self.llm_client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_new_tokens if max_new_tokens else 4096,
            temperature=temp,
            top_p=top_p,
            extra_body={"repetition_penalty": repetition_penalty},
            **kwargs,
        )
        return {
            "text": resp.choices[0].message.content,
            "usage": {
                "prompt_tokens": resp.usage.prompt_tokens if resp.usage else None,
                "completion_tokens": resp.usage.completion_tokens if resp.usage else None,
                "total_tokens": resp.usage.total_tokens if resp.usage else None,
            },
        }


class LMMEngineHuggingFace(LMMEngine):
    def __init__(self, base_url=None, api_key=None, rate_limit=-1, **kwargs):
        self.base_url = base_url
        self.api_key = api_key
        self.request_interval = 0 if rate_limit == -1 else 60.0 / rate_limit
        self.llm_client = None

    @backoff.on_exception(
        backoff.expo, (APIConnectionError, APIError, RateLimitError), max_time=120
    )
    def generate(self, messages, temperature=0.0, max_new_tokens=None, **kwargs):
        api_key = self.api_key or os.getenv("HF_TOKEN")
        if api_key is None:
            raise ValueError(
                "A HuggingFace token needs to be provided in either the api_key parameter or as an environment variable named HF_TOKEN"
            )
        base_url = self.base_url or os.getenv("HF_ENDPOINT_URL")
        if base_url is None:
            raise ValueError(
                "HuggingFace endpoint must be provided as base_url parameter or as an environment variable named HF_ENDPOINT_URL."
            )
        if not self.llm_client:
            self.llm_client = OpenAI(base_url=base_url, api_key=api_key)
        return (
            self.llm_client.chat.completions.create(
                model="tgi",
                messages=messages,
                max_tokens=max_new_tokens if max_new_tokens else 4096,
                temperature=temperature,
                **kwargs,
            )
            .choices[0]
            .message.content
        )


class LMMEngineParasail(LMMEngine):
    def __init__(
        self, base_url=None, api_key=None, model=None, rate_limit=-1, **kwargs
    ):
        assert model is not None, "Parasail model id must be provided"
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.request_interval = 0 if rate_limit == -1 else 60.0 / rate_limit
        self.llm_client = None

    @backoff.on_exception(
        backoff.expo, (APIConnectionError, APIError, RateLimitError), max_time=120
    )
    def generate(self, messages, temperature=0.0, max_new_tokens=None, **kwargs):
        api_key = self.api_key or os.getenv("PARASAIL_API_KEY")
        if api_key is None:
            raise ValueError(
                "A Parasail API key needs to be provided in either the api_key parameter or as an environment variable named PARASAIL_API_KEY"
            )
        base_url = self.base_url
        if base_url is None:
            raise ValueError(
                "Parasail endpoint must be provided as base_url parameter or as an environment variable named PARASAIL_ENDPOINT_URL"
            )
        if not self.llm_client:
            self.llm_client = OpenAI(
                base_url=base_url if base_url else "https://api.parasail.io/v1",
                api_key=api_key,
            )
        return (
            self.llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_new_tokens if max_new_tokens else 4096,
                temperature=temperature,
                **kwargs,
            )
            .choices[0]
            .message.content
        )
