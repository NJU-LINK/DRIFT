from __future__ import annotations

import json
from typing import Any

from .data import compact_case_payload
from .models import Case

AUDITOR_TYPES = ["entity", "constraint", "evidence", "retrieval", "compute", "process"]


def build_bare_prompt(case: Case) -> str:
    schema = {
        "traj_id": case.case_id,
        "error_span_ids": ["s004", "s007"],
        "earliest_harmful_span_id": "s004",
        "reasons": [{"span_id": "s004", "reason": "short string"}],
    }
    payload = compact_case_payload(case)
    return (
        "You are evaluating one deep-research trajectory for span-level error localization.\n"
        "This is a bare single-call evaluation: read the full question and all ordered spans once, then predict final error spans directly.\n\n"
        "Mark a span only if the span itself contains a committed harmful mistake, an unsupported committed conclusion, "
        "a harmful premature finalization, or a harmful continuation.\n"
        "Do not mark harmless exploration, ordinary evidence gaps, isolated tool failures without commitment, retries, "
        "search queries, tentative candidate pivots, or generic uncertainty.\n"
        "Prefer a sparse set of committed harmful spans. If the actual harmful commitment appears only in the final report, output only that final span.\n"
        "If an early span already commits to the wrong answer path or harmful no-answer decision, mark that earliest committed span and any later spans that explicitly rely on or finalize it.\n"
        "If there is no committed harmful error, return an empty error_span_ids list.\n\n"
        "Return JSON only. Do not include markdown or explanations outside JSON.\n"
        f"Schema: {json.dumps(schema, ensure_ascii=False)}\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_claim_keeper_prompt(case: Case) -> str:
    schema = {
        "traj_id": case.case_id,
        "task_goal": "short string",
        "hard_constraints": ["short string"],
        "claims": [
            {
                "claim_id": "c1",
                "claim": "short factual or procedural claim",
                "introduced_at": "s003",
                "becomes_consequential_at": "s011",
                "used_by": ["s011", "s015"],
                "claim_type": "entity",
                "status": "tentative",
            }
        ],
        "notes": "short string",
    }
    payload = compact_case_payload(case) | {
        "allowed_claim_types": AUDITOR_TYPES,
        "allowed_status_values": ["exploratory", "tentative", "consequential", "finalized"],
    }
    return (
        "DRIFT Audit Room - A: Claim Keeper.\n"
        "Read the question and ordered trajectory as an audit ledger, not as a final judge.\n"
        "Track consequential claims the agent comes to believe: entities, constraints, dates/ranges, evidence interpretations, retrieval coverage, computations, and process/tool assumptions.\n"
        "For each claim, record when it first appears, when it first becomes consequential for later work, and which later spans use it.\n"
        "Keep only decision-critical claims: claims that choose the answer path, narrow to one candidate, verify a hard constraint, justify the final response, or explain why no answer can be produced.\n"
        "Use status=finalized only for claims that are submitted, finalized, used in the final answer/no-answer, or explicitly treated as solved. Use status=consequential for claims that drive later work but are not yet final. Use tentative/exploratory for probes and candidates.\n"
        "Treat an early span as a claim when it already states a final answer, a chosen candidate, or an inability-to-answer decision; even s001 can be the first harmful commitment candidate.\n"
        "A search query, subtask request, tool call, or candidate name inside a query is not a commitment. Record it only if the span also says it has identified/found/verified the candidate or uses it as the answer path.\n"
        "If earlier spans only search and the final report is the first span that asserts the answer, set both introduced_at and becomes_consequential_at to the final report span.\n"
        "For no-answer cases, track the claim that the agent cannot answer only when it says final answer / cannot determine / unable / apology and stops or avoids the requested computation.\n"
        "Do not create claims for ordinary searches, abandoned candidates, broad plans, tool noise, or process observations unless a later answer/abort decision explicitly relies on them.\n"
        "If a span only searches, probes, lists a candidate, or asks another subtask without endorsing it as the answer path, mark it exploratory or omit it.\n"
        "Keep the ledger compact: prefer 3-5 claims, and never include more than the few claims that could change the final error decision.\n"
        "Do not decide final error spans.\n\n"
        "Return JSON only.\n"
        f"Schema: {json.dumps(schema, ensure_ascii=False)}\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_support_context_request_prompt(case: Case, claim_ledger: dict[str, Any]) -> str:
    schema = {
        "traj_id": case.case_id,
        "context_requests": [
            {
                "claim_id": "c1",
                "span_ids": ["s003", "s011"],
                "grep_queries": ["candidate name exact phrase", "hard constraint phrase"],
                "rationale": "short string",
            }
        ],
        "notes": "short string",
    }
    span_catalog = [
        {
            "span_id": span.span_id,
            "raw_start_step": span.raw_start_step,
            "raw_end_step": span.raw_end_step,
        }
        for span in case.spans
    ]
    payload = {
        "question": case.question,
        "traj_id": case.case_id,
        "claim_ledger": claim_ledger,
        "span_catalog": span_catalog,
    }
    return (
        "DRIFT Audit Room - B0: On-demand context request.\n"
        "You are not judging errors and not assigning support yet. Your only task is to request raw spans needed to audit support for A's consequential claims.\n"
        "Use two access modes:\n"
        "1. span_ids: request exact spans already exposed by the claim ledger or obviously needed from the ordered span catalog.\n"
        "2. grep_queries: request exact names, titles, dates, constraints, source labels, or computation terms that should be searched in the raw span store.\n\n"
        "Prefer high-recall evidence access. For each finalized or consequential claim, request the introduced/consequential/used_by spans plus 1-3 focused grep queries when names or constraints are available.\n"
        "Do not request every span and do not use fixed windows. Do not make final error decisions.\n"
        "The runner will return only original raw span text matching these requests; no summaries or labels will be added.\n\n"
        "Return JSON only.\n"
        f"Schema: {json.dumps(schema, ensure_ascii=False)}\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_support_seeker_prompt(case: Case, claim_ledger: dict[str, Any], evidence_packet: dict[str, Any]) -> str:
    schema = {
        "traj_id": case.case_id,
        "support_records": [
            {
                "claim_id": "c1",
                "support_spans": ["s003", "s008"],
                "support_status": "weak",
                "missing_support": "short string",
                "needs_auditors": ["entity", "evidence"],
                "evidence_handles": [
                    {
                        "span_id": "s003",
                        "chunk_id": "s003:c001",
                        "role": "partial_support",
                        "text": "short original-text handle",
                    }
                ],
            }
        ],
        "notes": "short string",
    }
    payload = {
        "question": case.question,
        "traj_id": case.case_id,
        "claim_ledger": claim_ledger,
        "evidence_packet": evidence_packet,
        "allowed_support_status": ["direct", "weak", "missing", "conflicting"],
        "allowed_auditors": AUDITOR_TYPES,
        "allowed_handle_roles": ["direct_support", "partial_support", "missing_link", "conflict", "commitment", "linked_use", "related"],
    }
    return (
        "DRIFT Audit Room - B: Tuned On-demand Support Seeker.\n"
        "Your role is high-recall claim-support mining, not final judgment.\n"
        "Audit A's consequential/finalized claims using only the raw_chunks in evidence_packet. The packet is original trajectory text fetched from the same span store; it contains no generated preview, no span labels, no outcome fields, and no answer key.\n\n"
        "For each decision-critical claim, expose support risk rather than clearing it too early.\n"
        "Use direct only when the fetched spans explicitly verify the decisive identity, hard constraint, source link, exact count/computation, retrieval coverage, or no-answer justification required by the question.\n"
        "Use weak when evidence is related but one decisive bridge is only implied, assumed, based on partial snippets, or not checked against the exact question.\n"
        "Use missing when a finalized answer/no-answer/computation claim has no fetched support for a required decisive link. Use conflicting when fetched evidence contradicts the claim or a hard constraint.\n"
        "Prefer weak over direct when unsure. This B step may over-route because C will later decide which risky claims become harmful errors.\n"
        "Do not rewrite concrete answer claims into safer process claims. Do not drop a finalized claim merely because some related searches exist.\n"
        "Route weak/missing/conflicting claims when the gap could change the final answer, justify stopping, or explain a linked error chain.\n"
        "Support_spans must be span ids present in evidence_packet.available_span_ids. If evidence_packet contains raw_chunks, cite the parent span_id, not chunk_id.\n\n"
        "Also write compact evidence_handles for C using exactly these keys: span_id, chunk_id, role, text. Role must be one of allowed_handle_roles. Text should be a short original-text handle under 40 words. Handles are not summaries of the whole span; they are evidence pointers for dependency tracing.\n\n"
        "Return JSON only.\n"
        f"Schema: {json.dumps(schema, ensure_ascii=False)}\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_dependency_tracer_prompt(
    case: Case,
    claim_ledger: dict[str, Any],
    support_records: list[dict[str, Any]],
    evidence_packet: dict[str, Any],
) -> str:
    schema = {
        "traj_id": case.case_id,
        "first_error_span": "s003",
        "linked_error_span_ids": ["s011", "s015"],
        "non_errors": ["s004", "s005"],
        "reason": "short string",
        "error_span_ids": ["s003", "s011", "s015"],
        "earliest_harmful_span_id": "s003",
    }
    payload = {
        "question": case.question,
        "traj_id": case.case_id,
        "claim_ledger": claim_ledger,
        "support_records": support_records,
        "evidence_packet": evidence_packet,
    }
    return (
        "DRIFT Audit Room - C: Tuned On-demand Dependency Tracer.\n"
        "A has produced a claim ledger and B has produced support-risk records from an on-demand raw_chunks packet. C now localizes final error spans by tracing which risky claims become harmful commitments.\n\n"
        "Treat weak/missing/conflicting support as candidate signals when the claim is consequential or finalized. Do not clear a finalized claim just because the packet has related but non-decisive searches.\n"
        "First-error selection rule: choose the earliest fetched span that states the risky claim as settled, selects it as the answer path, completes a computation from it, or uses it to stop the task. Do not choose the earliest mere mention in a query or snippet.\n"
        "Linked-error rule: include later fetched spans that explicitly repeat, compute from, verify as final, give up because of, or finalize the same risky claim.\n"
        "Favor recall over excessive sparsity: if a first harmful commitment and final commitment both carry the same unsupported claim, include both. If the unsupported answer path is repeatedly asserted as settled, include the committed chain.\n"
        "Do not mark pure searches, tool calls, support snippets, retries, broad plans, or abandoned candidates unless the span itself commits to the claim.\n"
        "Return empty only when support records and fetched spans show no consequential/finalized harmful commitment, or when the weakness is merely incomplete logging for an otherwise verified answer.\n"
        "Do not output spans outside evidence_packet.available_span_ids. If evidence_packet contains raw_chunks, output the parent span_id, not chunk_id.\n\n"
        "Return JSON only.\n"
        f"Schema: {json.dumps(schema, ensure_ascii=False)}\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
