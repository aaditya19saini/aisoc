"""Plug-and-play LLM layer.

Every AI call goes through here. The model for each task ("classifier", "writer")
is chosen in Settings as provider + model name + API key, and routed through
LiteLLM, so Claude, OpenAI, Gemini, Groq, OpenRouter or a local Ollama model
can be swapped without code changes.
"""

import json
import re
from dataclasses import dataclass
from typing import TypeVar

import litellm
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.store import get_setting

litellm.drop_params = True  # ignore params a provider doesn't support

TASKS = ("classifier", "writer")

PROVIDERS = {
    "anthropic": {"label": "Anthropic (Claude)", "needs_key": True},
    "openai": {"label": "OpenAI", "needs_key": True},
    "gemini": {"label": "Google Gemini", "needs_key": True},
    "groq": {"label": "Groq", "needs_key": True},
    "openrouter": {"label": "OpenRouter", "needs_key": True},
    "ollama": {"label": "Ollama (local)", "needs_key": False},
}

DEFAULTS = {
    "classifier": {"provider": "anthropic", "model": "claude-haiku-5-5"},
    "writer": {"provider": "anthropic", "model": "claude-sonnet-5-5"},
}

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str
    api_key: str | None = None  # None -> LiteLLM falls back to env vars (ANTHROPIC_API_KEY, ...)
    api_base: str | None = None

    @property
    def litellm_model(self) -> str:
        return f"{self.provider}/{self.model}"


def get_model_config(db: Session, task: str) -> ModelConfig:
    if task not in TASKS:
        raise ValueError(f"unknown task {task!r}")
    default = DEFAULTS[task]
    return ModelConfig(
        provider=get_setting(db, f"llm.{task}.provider", default["provider"]),
        model=get_setting(db, f"llm.{task}.model", default["model"]),
        api_key=get_setting(db, f"llm.{task}.api_key") or None,
        api_base=get_setting(db, f"llm.{task}.api_base") or None,
    )


def get_text(cfg: ModelConfig, system: str, prompt: str, max_tokens: int = 1500) -> str:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    return _complete(cfg, messages, max_tokens)


def get_json(cfg: ModelConfig, system: str, prompt: str, schema: type[T], max_tokens: int = 1500) -> T:
    """Ask for JSON matching `schema`; retry once with the validation error if it doesn't parse."""
    system = (
        f"{system}\n\nRespond with ONLY a JSON object matching this JSON schema, no prose, no code fences:\n"
        f"{json.dumps(schema.model_json_schema())}"
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    raw = _complete(cfg, messages, max_tokens)
    try:
        return schema.model_validate(extract_json(raw))
    except (ValueError, ValidationError) as e:
        messages += [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": f"That was not valid: {e}. Reply with only the corrected JSON object."},
        ]
        raw = _complete(cfg, messages, max_tokens)
        try:
            return schema.model_validate(extract_json(raw))
        except (ValueError, ValidationError) as e2:
            raise LLMError(f"model returned invalid JSON: {e2}") from e2


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (tolerates code fences / surrounding text)."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object found in model reply")
    return json.loads(text[start : end + 1])


def _complete(cfg: ModelConfig, messages: list[dict], max_tokens: int) -> str:
    try:
        resp = litellm.completion(
            model=cfg.litellm_model,
            messages=messages,
            api_key=cfg.api_key,
            api_base=cfg.api_base,
            max_tokens=max_tokens,
            timeout=90,
        )
    except Exception as e:  # LiteLLM raises provider-specific exception types
        raise LLMError(f"{cfg.litellm_model}: {e}") from e
    content = resp.choices[0].message.content
    if not content:
        raise LLMError(f"{cfg.litellm_model}: empty response")
    return content
