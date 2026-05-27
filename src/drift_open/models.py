from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Span:
    span_id: str
    span_text: str
    raw_start_step: int | None = None
    raw_end_step: int | None = None


@dataclass(frozen=True)
class Case:
    case_id: str
    question: str
    spans: list[Span]
    source_path: str = ""


@dataclass(frozen=True)
class ModelConfig:
    model: str
    base_url: str
    api_key: str
    api_type: str = "chat"
    reasoning_effort: str = "low"
    timeout_s: int = 300


JsonDict = dict[str, Any]
