from __future__ import annotations

from drift_open.data import sanitize_case
from drift_open.prompts import build_bare_prompt, build_dependency_tracer_prompt
from drift_open.sanitize import sanitize_dependency_trace


def test_bare_prompt_matches_release_contract():
    case = sanitize_case(
        {
            "case_id": "t1",
            "question": "Q?",
            "spans": [{"span_id": "s001", "span_text": "search"}, {"span_id": "s002", "span_text": "final wrong answer"}],
        }
    )
    prompt = build_bare_prompt(case)
    assert "This is a bare single-call evaluation" in prompt
    assert "No Claim Keeper" not in prompt


def test_dependency_prompt_uses_open_names():
    case = sanitize_case(
        {
            "case_id": "t1",
            "question": "Q?",
            "spans": [{"span_id": "s001", "span_text": "commit"}, {"span_id": "s002", "span_text": "final"}],
        }
    )
    prompt = build_dependency_tracer_prompt(case, {"claims": []}, [], {"available_span_ids": ["s001", "s002"], "raw_chunks": []})
    assert "first_error_span" in prompt
    assert "linked_error_span_ids" in prompt

    trace = sanitize_dependency_trace(
        {"first_error_span": "s001", "linked_error_span_ids": ["s002"], "error_span_ids": []},
        case,
    )
    assert trace["first_error_span"] == "s001"
    assert trace["linked_error_span_ids"] == ["s002"]
    assert trace["error_span_ids"] == ["s001", "s002"]
