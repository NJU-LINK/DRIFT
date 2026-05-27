from __future__ import annotations

from typing import Any

from .models import Case
from .utils import ordered_span_ids


def sanitize_prediction(data: dict[str, Any], case: Case) -> dict[str, Any]:
    error_ids = ordered_span_ids(list(data.get("error_span_ids") or []), case)
    earliest = data.get("earliest_harmful_span_id")
    if earliest not in error_ids:
        first_error = data.get("first_error_span")
        earliest = first_error if first_error in error_ids else (error_ids[0] if error_ids else None)
    valid = set(error_ids)
    reasons = [
        {"span_id": row.get("span_id"), "reason": str(row.get("reason") or "")}
        for row in data.get("reasons") or []
        if row.get("span_id") in valid
    ]
    return {
        "traj_id": case.case_id,
        "error_span_ids": error_ids,
        "earliest_harmful_span_id": earliest,
        "reasons": reasons,
    }


def sanitize_claim_ledger(data: dict[str, Any], case: Case, *, max_claims: int = 8) -> dict[str, Any]:
    allowed_types = {"entity", "constraint", "evidence", "retrieval", "compute", "process"}
    allowed_status = {"exploratory", "tentative", "consequential", "finalized"}
    claims = []
    for idx, row in enumerate(data.get("claims") or [], start=1):
        introduced = ordered_span_ids([str(row.get("introduced_at") or "")], case)
        consequential = ordered_span_ids([str(row.get("becomes_consequential_at") or "")], case)
        used_by = ordered_span_ids(list(row.get("used_by") or []), case)
        claim_type = str(row.get("claim_type") or "")
        status = str(row.get("status") or "")
        claim = str(row.get("claim") or "").strip()
        if not claim:
            continue
        claims.append(
            {
                "claim_id": str(row.get("claim_id") or f"c{idx}"),
                "claim": claim,
                "introduced_at": introduced[0] if introduced else "",
                "becomes_consequential_at": consequential[0] if consequential else (introduced[0] if introduced else ""),
                "used_by": used_by,
                "claim_type": claim_type if claim_type in allowed_types else "evidence",
                "status": status if status in allowed_status else "tentative",
            }
        )
    return {
        "traj_id": case.case_id,
        "task_goal": str(data.get("task_goal") or ""),
        "hard_constraints": [str(x) for x in (data.get("hard_constraints") or []) if str(x).strip()],
        "claims": claims[:max_claims],
        "notes": str(data.get("notes") or ""),
    }


def sanitize_context_requests(data: dict[str, Any], case: Case, claim_ledger: dict[str, Any]) -> list[dict[str, Any]]:
    claim_ids = {str(row.get("claim_id")) for row in claim_ledger.get("claims") or []}
    rows = []
    for row in data.get("context_requests") or []:
        claim_id = str(row.get("claim_id") or "")
        if claim_id not in claim_ids:
            continue
        queries = []
        for query in row.get("grep_queries") or []:
            text = str(query).strip()
            if text:
                queries.append(text[:160])
        rows.append(
            {
                "claim_id": claim_id,
                "span_ids": ordered_span_ids(list(row.get("span_ids") or []), case)[:8],
                "grep_queries": queries[:4],
                "rationale": str(row.get("rationale") or ""),
            }
        )
    return rows[:8]


def sanitize_support_records(data: dict[str, Any], case: Case, claim_ledger: dict[str, Any]) -> list[dict[str, Any]]:
    claim_ids = {str(row.get("claim_id")) for row in claim_ledger.get("claims") or []}
    allowed_status = {"direct", "weak", "missing", "conflicting"}
    allowed_auditors = {"entity", "constraint", "evidence", "retrieval", "compute", "process"}
    allowed_roles = {"direct_support", "partial_support", "missing_link", "conflict", "commitment", "linked_use", "downstream_use", "related"}
    rows = []
    for row in data.get("support_records") or []:
        claim_id = str(row.get("claim_id") or "")
        if claim_id not in claim_ids:
            continue
        handles = []
        for handle in row.get("evidence_handles") or []:
            span_ids = ordered_span_ids([str(handle.get("span_id") or "")], case)
            if not span_ids:
                continue
            role = str(handle.get("role") or "related")
            handles.append(
                {
                    "span_id": span_ids[0],
                    "chunk_id": str(handle.get("chunk_id") or "")[:40],
                    "role": role if role in allowed_roles else "related",
                    "text": str(handle.get("text") or "")[:360],
                }
            )
        status = str(row.get("support_status") or "")
        rows.append(
            {
                "claim_id": claim_id,
                "support_spans": ordered_span_ids(list(row.get("support_spans") or []), case),
                "support_status": status if status in allowed_status else "weak",
                "missing_support": str(row.get("missing_support") or ""),
                "needs_auditors": [str(x) for x in row.get("needs_auditors") or [] if str(x) in allowed_auditors],
                "evidence_handles": handles[:4],
            }
        )
    return rows[:8]


def restrict_support_records_to_packet(records: list[dict[str, Any]], evidence_packet: dict[str, Any]) -> list[dict[str, Any]]:
    available = set(evidence_packet.get("available_span_ids") or [])
    return [
        {
            **record,
            "support_spans": [sid for sid in record.get("support_spans") or [] if sid in available],
            "evidence_handles": [handle for handle in record.get("evidence_handles") or [] if handle.get("span_id") in available],
        }
        for record in records
    ]


def sanitize_dependency_trace(data: dict[str, Any], case: Case) -> dict[str, Any]:
    first = ordered_span_ids([str(data.get("first_error_span") or "")], case)
    linked = ordered_span_ids(list(data.get("linked_error_span_ids") or []), case)
    errors = ordered_span_ids(list(data.get("error_span_ids") or []), case)
    if first and first[0] not in errors:
        errors = ordered_span_ids([first[0]] + errors, case)
    for sid in linked:
        if sid not in errors:
            errors.append(sid)
    errors = ordered_span_ids(errors, case)
    return {
        "traj_id": case.case_id,
        "first_error_span": first[0] if first else (errors[0] if errors else None),
        "linked_error_span_ids": linked,
        "non_errors": ordered_span_ids(list(data.get("non_errors") or data.get("not_errors") or []), case),
        "reason": str(data.get("reason") or ""),
        "error_span_ids": errors,
        "earliest_harmful_span_id": first[0] if first else (errors[0] if errors else None),
    }


def trace_to_prediction(trace: dict[str, Any], case: Case) -> dict[str, Any]:
    error_ids = ordered_span_ids(list(trace.get("error_span_ids") or []), case)
    earliest = trace.get("earliest_harmful_span_id") if trace.get("earliest_harmful_span_id") in error_ids else (error_ids[0] if error_ids else None)
    return {
        "traj_id": case.case_id,
        "error_span_ids": error_ids,
        "earliest_harmful_span_id": earliest,
        "reasons": [{"span_id": sid, "reason": str(trace.get("reason") or "")} for sid in error_ids],
    }
