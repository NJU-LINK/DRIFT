from __future__ import annotations

import json
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .env import normalize_endpoint
from .models import ModelConfig

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None


SYSTEM_PROMPT = (
    "You are a careful trajectory-reading assistant.\n"
    "Output only one valid JSON object.\n"
    "No markdown.\n"
    "No extra text."
)


@dataclass
class OpenAICompatibleClient:
    endpoint: str
    model: str
    api_key: str
    api_type: str = "chat"
    reasoning_effort: str = "low"
    timeout_s: int = 300
    usage_records: list[dict[str, Any]] | None = None

    def chat(self, prompt: str, *, temperature: float = 0.1, max_tokens: int = 4096) -> str:
        if self.api_type == "responses":
            return self._responses_call(prompt, max_tokens=max_tokens)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(self.endpoint, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        context = ssl.create_default_context(cafile=certifi.where()) if certifi else None
        with urlopen(req, timeout=self.timeout_s, context=context) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(f"api_error: {data['error']}")
        choices = data.get("choices") or []
        if not choices:
            raise ValueError(f"missing choices: {raw[:400]}")
        msg = choices[0].get("message") or {}
        content = msg.get("content") or msg.get("reasoning_content") or choices[0].get("text") or ""
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"empty content: {raw[:400]}")
        self._record_usage(data.get("usage") or {})
        return content.strip()

    def _responses_call(self, prompt: str, *, max_tokens: int) -> str:
        payload = {
            "model": self.model,
            "instructions": SYSTEM_PROMPT,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
            "stream": True,
            "max_output_tokens": int(max_tokens),
            "reasoning": {"effort": self.reasoning_effort},
            "text": {"format": {"type": "json_object"}},
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(self.endpoint, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        context = ssl.create_default_context(cafile=certifi.where()) if certifi else None
        chunks: list[str] = []
        done_text = ""
        usage: dict[str, Any] = {}
        with urlopen(req, timeout=self.timeout_s, context=context) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                event = line[5:].strip()
                if not event or event == "[DONE]":
                    continue
                try:
                    obj = json.loads(event)
                except json.JSONDecodeError:
                    continue
                typ = obj.get("type")
                if typ == "response.output_text.delta":
                    chunks.append(obj.get("delta") or "")
                elif typ == "response.output_text.done" and obj.get("text"):
                    done_text = str(obj["text"])
                elif typ == "response.completed":
                    response = obj.get("response") or {}
                    usage = response.get("usage") or {}
                    if not done_text:
                        text_parts = []
                        for item in response.get("output") or []:
                            for content in item.get("content") or []:
                                if content.get("type") in {"output_text", "text"} and content.get("text"):
                                    text_parts.append(str(content["text"]))
                        done_text = "".join(text_parts)
                elif typ == "response.failed":
                    raise RuntimeError(str(obj))
        self._record_usage(usage)
        text = (done_text or "".join(chunks)).strip()
        if not text:
            raise RuntimeError("empty response text")
        return text

    def _record_usage(self, usage: dict[str, Any]) -> None:
        if self.usage_records is None:
            self.usage_records = []
        self.usage_records.append(dict(usage or {}))

    def chat_json(
        self,
        prompt: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        retries: int = 5,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        retry_prompt = prompt
        for attempt in range(retries + 1):
            try:
                return parse_json_object(self.chat(retry_prompt, temperature=temperature, max_tokens=max_tokens))
            except (HTTPError, URLError, TimeoutError, socket.timeout, OSError, ValueError, json.JSONDecodeError) as err:
                last_error = err
                if attempt < retries:
                    time.sleep(min(2**attempt, 16))
                    retry_prompt = "Return only valid JSON. Fix syntax only.\n\n" + prompt
                    continue
        raise RuntimeError(f"LLM call failed after retries: {last_error}")


def build_client(config: ModelConfig) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        endpoint=normalize_endpoint(config.base_url, api_type=config.api_type),
        model=config.model,
        api_key=config.api_key,
        api_type=config.api_type,
        reasoning_effort=config.reasoning_effort,
        timeout_s=config.timeout_s,
        usage_records=[],
    )


def parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("```")).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Expected a top-level JSON object.")
    return data
