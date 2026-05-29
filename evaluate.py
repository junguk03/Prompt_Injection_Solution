"""
Evaluate detector against attack + benign datasets.

지표:
  TPR (True Positive Rate)  = 진짜 공격 중 차단된 비율
  FPR (False Positive Rate) = 정상 요청 중 잘못 차단된 비율
  Precision                  = 차단한 것 중 진짜 공격이었던 비율
  F1 Score                   = Precision/Recall 조화 평균
"""
from __future__ import annotations

import json
import pathlib
from collections import defaultdict
from typing import Iterable

from detector import detect

DATASETS_DIR = pathlib.Path(__file__).parent / "datasets"


def load_jsonl(path: pathlib.Path) -> list[dict]:
    items = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def evaluate(attack_items: list[dict], benign_items: list[dict]) -> dict:
    tp = 0
    fn = 0
    fn_cases: list[dict] = []
    per_category = defaultdict(lambda: {"tp": 0, "fn": 0})

    for item in attack_items:
        result = detect(item["prompt"])
        cat = item.get("category", "?")
        if result.blocked:
            tp += 1
            per_category[cat]["tp"] += 1
        else:
            fn += 1
            per_category[cat]["fn"] += 1
            fn_cases.append({"id": item["id"], "prompt": item["prompt"], "category": cat})

    fp = 0
    tn = 0
    fp_cases: list[dict] = []
    for item in benign_items:
        result = detect(item["prompt"])
        if result.blocked:
            fp += 1
            fp_cases.append({
                "id": item["id"],
                "prompt": item["prompt"],
                "matched_rule": result.rule_id,
                "matched_text": result.matched_text,
            })
        else:
            tn += 1

    tpr = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tpr
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "counts": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "tpr": tpr,
        "fpr": fpr,
        "precision": precision,
        "f1": f1,
        "per_category": dict(per_category),
        "false_negatives": fn_cases,
        "false_positives": fp_cases,
    }


def fmt_pct(x: float) -> str:
    return f"{x*100:.1f}%"


def main() -> None:
    attack_files = sorted(DATASETS_DIR.glob("attacks_*.jsonl"))
    benign_files = sorted(DATASETS_DIR.glob("benign_*.jsonl"))

    attack_items: list[dict] = []
    for p in attack_files:
        attack_items.extend(load_jsonl(p))
    benign_items: list[dict] = []
    for p in benign_files:
        benign_items.extend(load_jsonl(p))

    print(f"Loaded {len(attack_items)} attack samples from {[p.name for p in attack_files]}")
    print(f"Loaded {len(benign_items)} benign samples from {[p.name for p in benign_files]}")
    print()

    report = evaluate(attack_items, benign_items)
    c = report["counts"]
    print("=== Overall ===")
    print(f"  TP={c['tp']}  FN={c['fn']}  FP={c['fp']}  TN={c['tn']}")
    print(f"  TPR (recall):  {fmt_pct(report['tpr'])}")
    print(f"  FPR:           {fmt_pct(report['fpr'])}")
    print(f"  Precision:     {fmt_pct(report['precision'])}")
    print(f"  F1:            {fmt_pct(report['f1'])}")
    print()

    print("=== Per category (attack recall) ===")
    for cat in sorted(report["per_category"]):
        s = report["per_category"][cat]
        total = s["tp"] + s["fn"]
        rate = s["tp"] / total if total else 0.0
        print(f"  {cat}: {s['tp']}/{total}  ({fmt_pct(rate)})")
    print()

    if report["false_negatives"]:
        print(f"=== Missed attacks (FN) — {len(report['false_negatives'])} ===")
        for fn in report["false_negatives"]:
            print(f"  [{fn['id']} / {fn['category']}] {fn['prompt']}")
        print()

    if report["false_positives"]:
        print(f"=== Wrongly blocked benign (FP) — {len(report['false_positives'])} ===")
        for fp in report["false_positives"]:
            print(f"  [{fp['id']}] rule={fp['matched_rule']} matched={fp['matched_text']!r}")
            print(f"    prompt: {fp['prompt']}")


if __name__ == "__main__":
    main()
