from __future__ import annotations

from typing import Any

from .models import Case


def span_number(span_id: str) -> int:
    digits = "".join(ch for ch in str(span_id) if ch.isdigit())
    return int(digits) if digits else 10**9


def ordered_span_ids(ids: list[str], case: Case) -> list[str]:
    wanted = {str(span_id) for span_id in ids if span_id}
    result = []
    for span in case.spans:
        if span.span_id in wanted and span.span_id not in result:
            result.append(span.span_id)
    return result


def safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

