from __future__ import annotations

import os
import re

from .models import ModelConfig


def load_env_file(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    env: dict[str, str] = {}
    for raw in open(path, encoding="utf-8").read().splitlines():
        line = re.sub(r"^export\s+", "", raw.strip())
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        env[key.strip()] = value
    return env


def normalize_endpoint(base_or_endpoint: str, *, api_type: str = "chat") -> str:
    text = base_or_endpoint.strip().rstrip("/")
    if api_type == "responses":
        if text.endswith("/v1/responses"):
            return text
        if text.endswith("/v1"):
            return text + "/responses"
        return text + "/v1/responses"
    if text.endswith("/v1/messages") or text.endswith("/chat/completions"):
        return text
    if text.endswith("/v1"):
        return text + "/chat/completions"
    return text + "/v1/chat/completions"


def resolve_model_config(
    *,
    model: str,
    env_file: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_type: str = "chat",
    reasoning_effort: str = "low",
) -> ModelConfig:
    file_env = load_env_file(env_file)
    resolved_base = (
        base_url
        or file_env.get("OPENAI_API_BASE")
        or file_env.get("CUSTOM_BASE_URL")
        or file_env.get("API_URL")
        or file_env.get("base_url")
        or os.environ.get("OPENAI_API_BASE")
        or os.environ.get("CUSTOM_BASE_URL")
        or os.environ.get("API_URL")
        or ""
    ).strip()
    resolved_key = (
        api_key
        or file_env.get("OPENAI_API_KEY")
        or file_env.get("CUSTOM_API_KEY")
        or file_env.get("API_KEY")
        or file_env.get("api_key")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("CUSTOM_API_KEY")
        or os.environ.get("API_KEY")
        or ""
    ).strip()
    if not resolved_base:
        raise RuntimeError("Missing API base URL.")
    if not resolved_key:
        raise RuntimeError("Missing API key.")
    return ModelConfig(
        model=model,
        base_url=resolved_base,
        api_key=resolved_key,
        api_type=api_type,
        reasoning_effort=reasoning_effort,
    )
