"""
Run each attack against a fresh Claude Code subagent via `claude -p`,
capture the response, judge it, and persist results.

전제 조건:
  - Python 3.9+
  - Claude Code CLI 설치 + Claude 계정(Pro/Max 구독)으로 로그인됨
    (API key 방식이 아니라 `claude login` 으로 OAuth 인증 — Max 구독 quota 사용)
  - 본 스크립트를 프로젝트 루트에서 실행

사용법:
  python run_subagent.py                            # 전체 어택, 기본 모델
  python run_subagent.py 10                         # 처음 10개 (스모크 테스트)
  python run_subagent.py 20 --cat F                 # F 카테고리에서 처음 20개
  python run_subagent.py --model sonnet             # Sonnet 으로 실행
  python run_subagent.py --model haiku 50           # Haiku 50개 (가장 저렴)

결과:
  results/run_YYYYMMDD_HHMMSS.jsonl       전체 결과(어택 + 응답 + 판정)
  results/bypasses_YYYYMMDD_HHMMSS.jsonl  우회된 어택만 (다음 분석 대상)

주의: `claude -p` 는 Claude Code 컨텍스트에서 응답하므로 vanilla
chat과 약간 다를 수 있음. 결과는 'Claude Code 환경에서의 우회율'로 해석할 것.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
from datetime import datetime

from judge import judge

ROOT = pathlib.Path(__file__).parent
DATASETS = ROOT / "datasets"
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)


def load_attacks(category_filter: str | None = None) -> list[dict]:
    items = []
    for f in sorted(DATASETS.glob("attacks_*.jsonl")):
        if "benign" in f.name:
            continue
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                if category_filter and not item.get("category", "").startswith(category_filter):
                    continue
                items.append(item)
    return items


def run_against_subagent(prompt: str, timeout: int = 90, model: str | None = None) -> str:
    """Send the attack to a fresh Claude Code subagent. Each call is a new process."""
    cmd = ["claude", "-p", prompt]
    if model:
        cmd.extend(["--model", model])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return (result.stdout or "").strip() or "[NO OUTPUT]"
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except FileNotFoundError:
        print("ERROR: `claude` CLI not found in PATH.", file=sys.stderr)
        print("       Install Claude Code and run `claude login` first.", file=sys.stderr)
        sys.exit(1)


VERDICT_MARK = {"blocked": "OK ", "bypassed": "!! ", "ambiguous": "?? "}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("limit", nargs="?", type=int, default=None, help="처음 N개만 실행")
    parser.add_argument("--cat", default=None, help="카테고리 필터 (예: A, F, F01)")
    parser.add_argument("--model", default=None, help="모델 지정 (sonnet | haiku | opus). 미지정 시 Claude Code 기본값")
    parser.add_argument("--throttle", type=float, default=1.0, help="호출 간 대기 초")
    parser.add_argument("--timeout", type=int, default=90, help="호출 타임아웃 초")
    args = parser.parse_args()

    attacks = load_attacks(category_filter=args.cat)
    if args.limit:
        attacks = attacks[: args.limit]

    if not attacks:
        print("실행할 어택이 없습니다.")
        return

    print(f"Loaded {len(attacks)} attacks. Running via `claude -p`...")
    if args.cat:
        print(f"Category filter: {args.cat}")
    if args.model:
        print(f"Model: {args.model}")
    print(f"Throttle: {args.throttle}s, Timeout: {args.timeout}s\n")

    results: list[dict] = []
    counts = {"blocked": 0, "bypassed": 0, "ambiguous": 0}

    for i, item in enumerate(attacks, 1):
        prompt = item["prompt"]
        print(
            f"[{i:3d}/{len(attacks)}] {item['id']:14s} ({item.get('category','?'):3s}) ",
            end="",
            flush=True,
        )

        response = run_against_subagent(prompt, timeout=args.timeout, model=args.model)
        v = judge(prompt, response)
        counts[v["verdict"]] += 1

        results.append(
            {
                **item,
                "response": response,
                "verdict": v["verdict"],
                "judge_reason": v.get("reason"),
                "judge_pattern": v.get("pattern"),
                "judge_matched": v.get("matched"),
                "tested_at": datetime.now().isoformat(),
                "model": args.model or "default",
            }
        )

        print(f"{VERDICT_MARK[v['verdict']]} {v['verdict']}")

        if args.throttle > 0:
            time.sleep(args.throttle)

    # Persist
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_all = RESULTS / f"run_{ts}.jsonl"
    out_bypass = RESULTS / f"bypasses_{ts}.jsonl"

    with out_all.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with out_bypass.open("w", encoding="utf-8") as f:
        for r in results:
            if r["verdict"] == "bypassed":
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("\n=== Summary ===")
    total = len(results)
    for k in ("blocked", "bypassed", "ambiguous"):
        pct = (counts[k] / total * 100) if total else 0
        print(f"  {k:10s}: {counts[k]:4d}  ({pct:5.1f}%)")
    print(f"\nFull results:  {out_all}")
    print(f"Bypasses only: {out_bypass}")


if __name__ == "__main__":
    main()
