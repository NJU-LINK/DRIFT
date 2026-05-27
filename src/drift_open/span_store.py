from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import Case
from .utils import ordered_span_ids

WORD_RE = re.compile(r"[\w'-]+", re.UNICODE)


def query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for term in WORD_RE.findall(query.lower()):
        if len(term) >= 3 and term not in terms:
            terms.append(term)
    return terms


@dataclass(frozen=True)
class SpanStore:
    case: Case
    max_matches_per_query: int = 4
    max_total_chunks: int = 18
    chunk_chars: int = 1800
    chunk_overlap: int = 160

    def fetch(self, span_ids: list[str]) -> list[dict[str, Any]]:
        wanted = ordered_span_ids(span_ids, self.case)
        return [
            {
                "span_id": span.span_id,
                "raw_start_step": span.raw_start_step,
                "raw_end_step": span.raw_end_step,
                "span_text": span.span_text,
            }
            for span in self.case.spans
            if span.span_id in wanted
        ]

    def span_chunks(self, span_id: str) -> list[dict[str, Any]]:
        span = next((span for span in self.case.spans if span.span_id == span_id), None)
        if span is None:
            return []
        text = span.span_text
        if len(text) <= self.chunk_chars:
            return [{"span_id": span_id, "chunk_id": f"{span_id}:c001", "char_start": 0, "char_end": len(text), "text": text}]
        chunks = []
        start = 0
        index = 1
        while start < len(text):
            end = min(len(text), start + self.chunk_chars)
            chunks.append({"span_id": span_id, "chunk_id": f"{span_id}:c{index:03d}", "char_start": start, "char_end": end, "text": text[start:end]})
            if end == len(text):
                break
            start = max(0, end - self.chunk_overlap)
            index += 1
        return chunks

    def score_chunk(self, chunk: dict[str, Any], query: str) -> int:
        terms = query_terms(query)
        if not terms:
            return 0
        text = str(chunk.get("text") or "").lower()
        score = sum(text.count(term) for term in terms)
        if query.strip().lower() in text:
            score += 3
        return score

    def best_chunks_for_span(self, span_id: str, query: str, *, max_chunks: int = 2) -> list[dict[str, Any]]:
        chunks = self.span_chunks(span_id)
        if not chunks:
            return []
        scored = [(-self.score_chunk(chunk, query), chunk["char_start"], chunk) for chunk in chunks]
        scored.sort()
        if scored and scored[0][0] < 0:
            return [row[2] for row in scored[:max_chunks]]
        return [chunks[-1]]

    def grep_chunks(self, query: str) -> list[dict[str, Any]]:
        if not query_terms(query):
            return []
        scored = []
        for span in self.case.spans:
            for chunk in self.span_chunks(span.span_id):
                score = self.score_chunk(chunk, query)
                if score > 0:
                    scored.append((-score, int(span.raw_start_step or 0), chunk["chunk_id"], chunk))
        scored.sort()
        return [row[3] for row in scored[: self.max_matches_per_query]]

    def chunked_evidence_packet(self, *, seed_span_ids: list[str], requests: list[dict[str, Any]]) -> dict[str, Any]:
        query_by_span: dict[str, list[str]] = {}
        for request in requests:
            request_query = " ".join(str(query) for query in request.get("grep_queries") or [])
            for span_id in request.get("span_ids") or []:
                query_by_span.setdefault(str(span_id), []).append(request_query)

        chunks: list[dict[str, Any]] = []
        seen_chunks: set[str] = set()

        def add(chunk: dict[str, Any]) -> None:
            chunk_id = str(chunk.get("chunk_id") or "")
            if chunk_id and chunk_id not in seen_chunks:
                chunks.append(chunk)
                seen_chunks.add(chunk_id)

        for span_id in ordered_span_ids(seed_span_ids, self.case):
            query = " ".join(query_by_span.get(span_id) or [])
            for chunk in self.best_chunks_for_span(span_id, query):
                add(chunk)

        grep_results = []
        for request in requests:
            for span_id in ordered_span_ids([str(sid) for sid in request.get("span_ids") or []], self.case):
                query = " ".join(str(query) for query in request.get("grep_queries") or [])
                for chunk in self.best_chunks_for_span(span_id, query):
                    add(chunk)
            for query in request.get("grep_queries") or []:
                query_text = str(query).strip()
                if not query_text:
                    continue
                matches = self.grep_chunks(query_text)
                for chunk in matches:
                    add(chunk)
                grep_results.append(
                    {
                        "claim_id": str(request.get("claim_id") or ""),
                        "query": query_text,
                        "matched_chunk_ids": [chunk["chunk_id"] for chunk in matches],
                        "matched_span_ids": ordered_span_ids([chunk["span_id"] for chunk in matches], self.case),
                    }
                )

        chunks = chunks[: self.max_total_chunks]
        available_span_ids = ordered_span_ids([chunk["span_id"] for chunk in chunks], self.case)
        available_chunk_ids = {chunk["chunk_id"] for chunk in chunks}
        return {
            "access_mode": "claim_graph_chunk_grep",
            "seed_span_ids": ordered_span_ids(seed_span_ids, self.case),
            "requested_span_ids": ordered_span_ids([str(sid) for req in requests for sid in (req.get("span_ids") or [])], self.case),
            "grep_results": [
                {
                    **row,
                    "matched_chunk_ids": [cid for cid in row["matched_chunk_ids"] if cid in available_chunk_ids],
                    "matched_span_ids": [sid for sid in row["matched_span_ids"] if sid in set(available_span_ids)],
                }
                for row in grep_results
            ],
            "available_span_ids": available_span_ids,
            "raw_chunks": chunks,
        }

