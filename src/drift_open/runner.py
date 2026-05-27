from __future__ import annotations

from typing import Any

from .data import full_span_payload
from .models import Case
from .prompts import (
    build_bare_prompt,
    build_claim_keeper_prompt,
    build_dependency_tracer_prompt,
    build_support_context_request_prompt,
    build_support_seeker_prompt,
)
from .sanitize import (
    restrict_support_records_to_packet,
    sanitize_claim_ledger,
    sanitize_context_requests,
    sanitize_dependency_trace,
    sanitize_prediction,
    sanitize_support_records,
    trace_to_prediction,
)
from .span_store import SpanStore
from .utils import ordered_span_ids, span_number


def safe_chat_json(client, prompt: str, *, fallback: dict[str, Any], max_tokens: int = 4096) -> dict[str, Any]:
    try:
        return client.chat_json(prompt, temperature=0.1, max_tokens=max_tokens)
    except Exception as err:  # Keep batch runs auditable instead of losing the whole run.
        result = dict(fallback)
        result["_fallback_error"] = str(err)
        return result


def claim_seed_span_ids(case: Case, claim_ledger: dict[str, Any]) -> list[str]:
    span_ids: list[str] = []
    for claim in claim_ledger.get("claims") or []:
        for key in ("introduced_at", "becomes_consequential_at"):
            if claim.get(key):
                span_ids.append(claim[key])
        span_ids.extend([sid for sid in claim.get("used_by") or [] if sid])
    if case.spans:
        span_ids.append(case.spans[-1].span_id)
    return ordered_span_ids(span_ids, case)


def auto_context_requests_from_ledger(claim_ledger: dict[str, Any]) -> list[dict[str, Any]]:
    requests = []
    for claim in claim_ledger.get("claims") or []:
        claim_id = str(claim.get("claim_id") or "")
        if not claim_id or claim.get("status") not in {"consequential", "finalized"}:
            continue
        span_ids = []
        for key in ("introduced_at", "becomes_consequential_at"):
            if claim.get(key):
                span_ids.append(claim[key])
        used_by = [sid for sid in claim.get("used_by") or [] if sid]
        if used_by:
            span_ids.append(used_by[-1])
        claim_text = str(claim.get("claim") or "").strip()
        requests.append(
            {
                "claim_id": claim_id,
                "span_ids": span_ids,
                "grep_queries": [claim_text[:160]] if claim_text else [],
                "rationale": "auto request from claim ledger endpoints and claim text",
            }
        )
    return requests


def claim_completion_ids(claim_ledger: dict[str, Any]) -> list[str]:
    span_ids = []
    for claim in claim_ledger.get("claims") or []:
        if claim.get("status") not in {"consequential", "finalized"}:
            continue
        if claim.get("becomes_consequential_at"):
            span_ids.append(claim["becomes_consequential_at"])
        used_by = claim.get("used_by") or []
        if used_by:
            span_ids.append(used_by[-1])
        elif claim.get("introduced_at"):
            span_ids.append(claim["introduced_at"])
    return span_ids


def add_late_support_endpoints(case: Case, prediction: dict[str, Any], claim_ledger: dict[str, Any]) -> dict[str, Any]:
    completion_ids = ordered_span_ids(claim_completion_ids(claim_ledger), case)
    current_ids = list(prediction.get("error_span_ids") or [])
    if current_ids:
        first_num = min(span_number(sid) for sid in current_ids)
        additions = [sid for sid in completion_ids if span_number(sid) > first_num]
    else:
        additions = list(completion_ids)
    merged = ordered_span_ids(current_ids + additions, case)
    return {**prediction, "error_span_ids": merged, "earliest_harmful_span_id": merged[0] if merged else None}


def run_bare(client, case: Case) -> dict[str, Any]:
    prompt = build_bare_prompt(case)
    raw = safe_chat_json(
        client,
        prompt,
        fallback={"traj_id": case.case_id, "error_span_ids": [], "earliest_harmful_span_id": None, "reasons": []},
    )
    prediction = sanitize_prediction(raw, case)
    return {
        "setting": "bare",
        "case_id": case.case_id,
        "prediction": prediction,
        "logs": {"bare": {"prompt": prompt, "raw_output": raw, "validated": prediction}, "full_span_count": len(full_span_payload(case))},
    }


def run_drift(client, case: Case) -> dict[str, Any]:
    claim_prompt = build_claim_keeper_prompt(case)
    claim_raw = safe_chat_json(
        client,
        claim_prompt,
        fallback={"traj_id": case.case_id, "task_goal": "", "hard_constraints": [], "claims": [], "notes": ""},
    )
    claim_ledger = sanitize_claim_ledger(claim_raw, case)

    context_requests = sanitize_context_requests(
        {"context_requests": auto_context_requests_from_ledger(claim_ledger)},
        case,
        claim_ledger,
    )
    span_store = SpanStore(case)
    evidence_packet = span_store.chunked_evidence_packet(
        seed_span_ids=claim_seed_span_ids(case, claim_ledger),
        requests=context_requests,
    )

    support_prompt = build_support_seeker_prompt(case, claim_ledger, evidence_packet)
    support_raw = safe_chat_json(
        client,
        support_prompt,
        fallback={"traj_id": case.case_id, "support_records": [], "notes": ""},
    )
    support_records = restrict_support_records_to_packet(
        sanitize_support_records(support_raw, case, claim_ledger),
        evidence_packet,
    )

    trace_prompt = build_dependency_tracer_prompt(case, claim_ledger, support_records, evidence_packet)
    trace_raw = safe_chat_json(
        client,
        trace_prompt,
        fallback={
            "traj_id": case.case_id,
            "first_error_span": None,
            "linked_error_span_ids": [],
            "non_errors": [],
            "reason": "",
            "error_span_ids": [],
            "earliest_harmful_span_id": None,
        },
    )
    trace = sanitize_dependency_trace(trace_raw, case)
    allowed = set(evidence_packet.get("available_span_ids") or [])
    trace = {
        **trace,
        "first_error_span": trace.get("first_error_span") if trace.get("first_error_span") in allowed else None,
        "linked_error_span_ids": [sid for sid in trace.get("linked_error_span_ids") or [] if sid in allowed],
        "non_errors": [sid for sid in trace.get("non_errors") or [] if sid in allowed],
        "error_span_ids": [sid for sid in trace.get("error_span_ids") or [] if sid in allowed],
    }
    prediction = trace_to_prediction(trace, case)
    prediction = add_late_support_endpoints(case, prediction, claim_ledger)
    prediction = {
        **prediction,
        "error_span_ids": ordered_span_ids([sid for sid in prediction.get("error_span_ids") or [] if sid in allowed], case),
    }
    prediction = {
        **prediction,
        "earliest_harmful_span_id": prediction["error_span_ids"][0] if prediction.get("error_span_ids") else None,
        "reasons": [row for row in prediction.get("reasons") or [] if row.get("span_id") in set(prediction.get("error_span_ids") or [])],
    }

    return {
        "setting": "drift",
        "case_id": case.case_id,
        "prediction": prediction,
        "logs": {
            "audit_room": {
                "agents": ["claim_keeper", "support_seeker", "dependency_tracer"],
                "context_access": "claim_graph_chunk_grep",
            },
            "claim_keeper": {"prompt": claim_prompt, "raw_output": claim_raw, "validated": claim_ledger},
            "context_request": {"prompt": None, "raw_output": None, "validated": context_requests},
            "span_store": {
                "seed_span_ids": evidence_packet.get("seed_span_ids") or [],
                "available_span_ids": evidence_packet.get("available_span_ids") or [],
                "grep_results": evidence_packet.get("grep_results") or [],
            },
            "support_seeker": {"prompt": support_prompt, "raw_output": support_raw, "validated": support_records},
            "dependency_tracer": {"prompt": trace_prompt, "raw_output": trace_raw, "validated": trace},
            "full_span_count": len(full_span_payload(case)),
            "evidence_span_count": len(evidence_packet.get("available_span_ids") or []),
        },
    }


def run_setting(client, case: Case, setting: str) -> dict[str, Any]:
    if setting == "bare":
        return run_bare(client, case)
    if setting == "drift":
        return run_drift(client, case)
    raise ValueError(f"Unknown setting: {setting}")

