from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .client import build_client
from .data import load_cases
from .env import resolve_model_config
from .io import ensure_dir, write_json
from .runner import run_setting


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run DRIFT or the bare full-context baseline.")
    parser.add_argument("--setting", choices=["bare", "drift"], required=True)
    parser.add_argument("--input", required=True, help="JSON/JSONL file containing cases with question and ordered spans.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-type", choices=["chat", "responses"], default="chat")
    parser.add_argument("--reasoning-effort", default="low", help="Responses API reasoning effort, e.g. low/medium/high.")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--env-file")
    parser.add_argument("--outdir", default="runs")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    cases = load_cases(args.input)
    if args.limit is not None:
        cases = cases[: args.limit]

    config = resolve_model_config(
        model=args.model,
        env_file=args.env_file,
        base_url=args.base_url,
        api_key=args.api_key,
        api_type=args.api_type,
        reasoning_effort=args.reasoning_effort,
    )
    outdir = ensure_dir(Path(args.outdir) / args.setting / args.model)

    def run_one(case):
        client = build_client(config)
        case_dir = ensure_dir(outdir / case.case_id)
        run = run_setting(client, case, args.setting)
        usage = aggregate_usage(client.usage_records or [])
        run["usage"] = usage
        write_json(case_dir / "run.json", run)
        return {
            "case_id": case.case_id,
            "setting": args.setting,
            "prediction": run["prediction"],
            "usage": usage,
        }

    items = []
    if args.workers <= 1:
        for case in cases:
            items.append(run_one(case))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_one, case): case.case_id for case in cases}
            for future in as_completed(futures):
                items.append(future.result())

    items.sort(key=lambda row: row["case_id"])
    write_json(
        outdir / "summary.json",
        {
            "setting": args.setting,
            "model": args.model,
            "case_count": len(items),
            "items": items,
            "usage": aggregate_usage([item.get("usage") or {} for item in items]),
        },
    )


def token_value(usage: dict, *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def aggregate_usage(records: list[dict]) -> dict:
    input_tokens = output_tokens = total_tokens = 0
    for usage in records:
        input_tokens += token_value(usage, "input_tokens", "prompt_tokens")
        output_tokens += token_value(usage, "output_tokens", "completion_tokens")
        total_tokens += token_value(usage, "total_tokens")
    if not total_tokens:
        total_tokens = input_tokens + output_tokens
    return {
        "call_count": len(records),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
