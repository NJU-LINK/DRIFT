from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .io import load_json
from .models import Case, Span

FORBIDDEN_INPUT_KEYS = {
    "gold",
    "judge_result",
    "span_type",
    "short_label",
    "goal_signature",
    "annotations",
    "manual_error_span_ids",
}

BASE64_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\(data:image/[^)]*\)")


def clean_text(text: str) -> str:
    return BASE64_IMAGE_PATTERN.sub("[image omitted]", text)


def span_from_row(row: dict[str, Any]) -> Span:
    span_id = str(row.get("span_id") or row.get("id") or "")
    span_text = row.get("span_text")
    if span_text is None:
        span_text = row.get("raw")
    return Span(
        span_id=span_id,
        span_text=clean_text(str(span_text or "")),
        raw_start_step=row.get("raw_start_step"),
        raw_end_step=row.get("raw_end_step"),
    )


def sanitize_case(row: dict[str, Any], *, source_path: str = "") -> Case:
    source = row.get("traj") or row
    case_id = str(row.get("case_id") or row.get("id") or source.get("case_id") or source.get("id") or Path(source_path).stem)
    question = str(source.get("question") or source.get("q") or row.get("question") or "")
    span_rows = source.get("spans") or source.get("span") or []
    spans = [span_from_row(span) for span in span_rows]
    spans = [span for span in spans if span.span_id and span.span_text]
    return Case(case_id=case_id, question=question, spans=spans, source_path=source_path)


def load_cases(path: str | Path) -> list[Case]:
    path = Path(path)
    if path.suffix == ".jsonl":
        cases = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cases.append(sanitize_case(loads_json(line), source_path=str(path)))
        return cases
    obj = load_json(path)
    if isinstance(obj, dict) and "items" in obj:
        return [sanitize_case(item, source_path=str(path)) for item in obj["items"]]
    if isinstance(obj, list):
        return [sanitize_case(item, source_path=str(path)) for item in obj]
    if isinstance(obj, dict):
        return [sanitize_case(obj, source_path=str(path))]
    raise ValueError(f"Unsupported input format: {path}")


def loads_json(text: str) -> Any:
    import json

    return json.loads(text)


def full_span_payload(case: Case) -> list[dict[str, Any]]:
    return [
        {
            "span_id": span.span_id,
            "raw_start_step": span.raw_start_step,
            "raw_end_step": span.raw_end_step,
            "span_text": span.span_text,
        }
        for span in case.spans
    ]


def compact_case_payload(case: Case) -> dict[str, Any]:
    return {"question": case.question, "traj_id": case.case_id, "spans": full_span_payload(case)}

