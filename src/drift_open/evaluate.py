from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .io import load_json, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate DRIFT predictions against TELBench gold labels.")
    parser.add_argument("--gold", required=True, help="TELBench JSONL/JSON file with gold.error_span_ids.")
    parser.add_argument("--pred", required=True, help="DRIFT summary.json or prediction JSON/JSONL.")
    parser.add_argument("--output", help="Optional JSON output path.")
    return parser


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def loads(text: str) -> Any:
    import json

    return json.loads(text)


def case_id(row: dict[str, Any]) -> str:
    return str(row.get("case_id") or row.get("traj_id") or row.get("id") or "")


def gold_ids(row: dict[str, Any]) -> list[str]:
    gold = row.get("gold") or {}
    ids = gold.get("error_span_ids")
    if ids is None:
        ids = row.get("error_span_ids") or []
    return [str(x) for x in ids]


def pred_ids(row: dict[str, Any]) -> list[str]:
    pred = row.get("prediction") or row
    return [str(x) for x in pred.get("error_span_ids") or []]


def load_gold(path: str | Path) -> dict[str, list[str]]:
    path = Path(path)
    rows = load_jsonl(path) if path.suffix == ".jsonl" else normalize_rows(load_json(path))
    return {case_id(row): gold_ids(row) for row in rows if case_id(row)}


def load_predictions(path: str | Path) -> dict[str, list[str]]:
    path = Path(path)
    rows = normalize_rows(load_json(path)) if path.suffix != ".jsonl" else load_jsonl(path)
    return {case_id(row): pred_ids(row) for row in rows if case_id(row)}


def normalize_rows(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, dict) and isinstance(obj.get("items"), list):
        return obj["items"]
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        return [obj]
    raise ValueError("Unsupported JSON structure.")


def precision_recall_f1(gold: set[str], pred: set[str]) -> tuple[float, float, float]:
    tp = len(gold & pred)
    precision = tp / len(pred) if pred else (1.0 if not gold else 0.0)
    recall = tp / len(gold) if gold else (1.0 if not pred else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def first_error_accuracy(gold: list[str], pred: list[str]) -> float:
    if not gold:
        return 1.0 if not pred else 0.0
    return 1.0 if pred and pred[0] == gold[0] else 0.0


def evaluate(gold: dict[str, list[str]], pred: dict[str, list[str]]) -> dict[str, Any]:
    ids = sorted(gold)
    rows = []
    micro_tp = micro_pred = micro_gold = 0
    for cid in ids:
        g_list = list(dict.fromkeys(gold.get(cid, [])))
        p_list = list(dict.fromkeys(pred.get(cid, [])))
        g = set(g_list)
        p = set(p_list)
        precision, recall, f1 = precision_recall_f1(g, p)
        fea = first_error_accuracy(g_list, p_list)
        rows.append(
            {
                "case_id": cid,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "first_error_accuracy": fea,
                "gold_count": len(g),
                "pred_count": len(p),
            }
        )
        micro_tp += len(g & p)
        micro_pred += len(p)
        micro_gold += len(g)

    n = len(rows) or 1
    micro_p = micro_tp / micro_pred if micro_pred else 0.0
    micro_r = micro_tp / micro_gold if micro_gold else 0.0
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if micro_p + micro_r else 0.0
    return {
        "case_count": len(rows),
        "macro_precision": sum(r["precision"] for r in rows) / n,
        "macro_recall": sum(r["recall"] for r in rows) / n,
        "macro_f1": sum(r["f1"] for r in rows) / n,
        "first_error_accuracy": sum(r["first_error_accuracy"] for r in rows) / n,
        "micro_precision": micro_p,
        "micro_recall": micro_r,
        "micro_f1": micro_f1,
        "missing_predictions": sorted(set(gold) - set(pred)),
        "extra_predictions": sorted(set(pred) - set(gold)),
        "items": rows,
    }


def main() -> None:
    args = build_parser().parse_args()
    result = evaluate(load_gold(args.gold), load_predictions(args.pred))
    if args.output:
        write_json(args.output, result)
    print(
        "case_count={case_count} macro_p={macro_precision:.4f} macro_r={macro_recall:.4f} "
        "macro_f1={macro_f1:.4f} fea={first_error_accuracy:.4f}".format(**result)
    )


if __name__ == "__main__":
    main()

