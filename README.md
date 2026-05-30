# KPI-Rules

한국어 환경 LLM에 대한 프롬프트 인젝션을 분류·탐지·평가하는 오픈 리서치.

## 왜

- 프롬프트 인젝션은 OWASP LLM Top 10에 있지만 **세부 패턴 분류는 합의되지 않음**
- 영어권 벤치마크(TensorTrust, PromptBench, HarmBench)는 다수, **한국어 특화 회피 기법은 백지**
- 본 프로젝트가 채우는 빈틈 → 자모 분리 · 존댓말 변형 · 한-영 혼용 · 한국 문화 컨텍스트

## 구조

```
├── taxonomy.md            공격 카테고리 분류 (A~F, 한국어 특화 F축 포함)
├── datasets/
│   ├── attacks_ko.jsonl    한국어 공격 — A·C·D·F (각 50건)
│   ├── attacks_ko_b.jsonl  한국어 공격 — B 간접 주입 (50건)
│   ├── attacks_ko_e.jsonl  한국어 공격 — E 목표 변경 (50건)
│   ├── attacks_en.jsonl    비교용 영어 공격
│   └── benign_ko.jsonl     정상 요청 (FPR 측정용)
├── detector.py            정규식 + 자모 정규화 탐지기
└── evaluate.py            TPR / FPR / F1 평가
```

## 실행

```bash
python evaluate.py
```

## 지표

| 지표 | 의미 |
|---|---|
| **TPR** | 진짜 공격을 막은 비율 |
| **FPR** | 정상 요청을 잘못 차단한 비율 |
| **F1**  | 정밀도/재현율의 조화 평균 |

## 상태

한국어 공격 300건(6개 카테고리 × 50건) 수공 작성 완료. 다음 단계: 자동 변형 생성기 + 실제 LLM 우회 측정.

## 참고

OWASP LLM Top 10 · TensorTrust · PromptBench · HarmBench
