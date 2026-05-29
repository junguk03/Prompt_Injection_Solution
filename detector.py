"""
Korean Prompt Injection Detector

정규식 기반 1차 필터링. 입력 정규화로 한국어 자모/공백 우회(F01)에 대응.
한계: 로마자 변환(F03), 의미 기반 우회는 후속 LLM 분류 단계에서 처리.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional


@dataclass
class DetectionResult:
    blocked: bool
    rule_id: Optional[str] = None
    category: Optional[str] = None
    severity: Optional[str] = None
    matched_text: Optional[str] = None

    def __bool__(self) -> bool:
        return self.blocked


_ZERO_WIDTH_CHARS = "".join(
    chr(c) for c in (0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF, 0x00A0)
)
_ZERO_WIDTH_RE = re.compile(f"[{re.escape(_ZERO_WIDTH_CHARS)}]")
_SEPARATOR_RE = re.compile(
    r"([가-힣a-zA-Z])[\s.,·\-_/]{1,2}([가-힣a-zA-Z])"
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH_RE.sub("", text)
    # Collapse single-character separators between Hangul/letter pairs
    # so "이.전.지.시" and "이 전 지 시" both fold to "이전지시"
    prev = None
    while prev != text:
        prev = text
        text = _SEPARATOR_RE.sub(r"\1\2", text)
    return text


RULES = [
    {
        "id": "A01-IGNORE",
        "category": "A01",
        "severity": "high",
        "patterns": [
            r"(?:이전|위에|위의|위에서|아까|앞선|방금)[^.!?\n]{0,30}(?:지시|명령|규칙|지시사항|프롬프트|instruction|prompt)[^.!?\n]{0,30}(?:무시|잊어|잊으|잊는|지워|취소|버려)",
            r"(?:이전|아까|위)[^.!?\n]{0,20}(?:지시|명령|지시사항)[^.!?\n]{0,15}(?:가짜|진짜가\s*아|페이크|fake)",
            r"시스템\s*프롬프트[^.!?\n]{0,10}(?:무시|잊|지워|취소)",
            r"\b(?:ignore|disregard|forget)\b[^.!?\n]{0,30}\b(?:previous|above|all|prior|earlier|everything)\b",
        ],
    },
    {
        "id": "A02-ROLE-OVERRIDE",
        "category": "A02",
        "severity": "high",
        "patterns": [
            r"(?<![가-힣A-Za-z])(?:DAN|AIM|STAN|DUDE)(?![가-힣A-Za-z])(?!\s*(?:이|가|은|는)\s*(?:뭐|무엇|약자|의\s*약자))",
            r"(?:너|당신|넌)[^.!?\n]{0,15}(?:이제|지금부터)[^.!?\n]{0,25}(?:제한\s*없|검열되지\s*않은|규칙\s*없|필터\s*없|안전\s*정책\s*없)",
            r"(?:제한|규칙|필터|검열)[^.!?\n]{0,5}없는\s*(?:AI|모델|어시스턴트|챗봇|assistant)",
            r"\b(?:uncensored|unrestricted|unfiltered|jailbroken)\s+(?:AI|model|assistant|chatbot)\b",
            r"\bact\s+as\s+(?:DAN|AIM|an?\s+(?:uncensored|unrestricted|unfiltered))",
        ],
    },
    {
        "id": "A03-OVERWRITE",
        "category": "A03",
        "severity": "high",
        "patterns": [
            r"\[\s*(?:SYSTEM|시스템|ADMIN|관리자)\s*\][^.!?\n]{0,30}(?:새로운|new|업데이트|update)",
            r"새로운\s*시스템\s*프롬프트\s*[:：]",
            r"new\s+system\s+prompt\s*[:：]",
        ],
    },
    {
        "id": "A04-DISABLE-SAFETY",
        "category": "A04",
        "severity": "high",
        "patterns": [
            r"(?:안전\s*장치|안전\s*정책|가드레일|안전\s*기능)[^.!?\n]{0,10}(?:비활성|해제|끄|꺼|제거|우회|disable)",
            r"\b(?:disable|turn\s*off|remove|bypass)\b[^.!?\n]{0,15}\b(?:safety|guardrails?|filter|policy|policies|moderation)\b",
        ],
    },
    {
        "id": "C01-PERSONA-BYPASS",
        "category": "C01",
        "severity": "high",
        "patterns": [
            r"(?:할머니|할아버지|엄마|어머니)(?:가|께서|는)[^.!?\n]{0,30}(?:자장가|동화|이야기|잠들기\s*전)[^.!?\n]{0,40}(?:들려|불러|이야기해)",
            r"\bgrandm(?:other|a)\b[^.!?\n]{0,30}\b(?:used\s+to|tell|sing|bedtime|stories?)\b",
        ],
    },
    {
        "id": "C02-DUAL-RESPONSE",
        "category": "C02",
        "severity": "high",
        "patterns": [
            r"(?:두\s*(?:가지|버전)|2\s*가지)\s*(?:버전|답변|방식)?[^.!?\n]{0,40}(?:검열되지\s*않은|제한\s*없는|필터\s*없는|uncensored|unfiltered)",
            r"(?:respond|answer|reply)[^.!?\n]{0,15}\btwice\b[^.!?\n]{0,30}(?:uncensored|unfiltered|unrestricted)",
            r"(?:일반|정상|normal)\s*답변[^.!?\n]{0,15}(?:검열되지\s*않은|제한\s*없는)\s*답변",
        ],
    },
    {
        "id": "C04-DEV-MODE",
        "category": "C04",
        "severity": "high",
        "patterns": [
            r"개발자\s*모드[^.!?\n]{0,10}(?:활성|켜|작동|enable|on)(?!\s*(?:이|가|은|는)\s*(?:뭐|무엇|어떤|일반적))",
            r"\bdeveloper\s+mode\b[^.!?\n]{0,15}\b(?:enable|activate|on)\b",
        ],
    },
    {
        "id": "D01-PROMPT-LEAK",
        "category": "D01",
        "severity": "high",
        "patterns": [
            r"(?:너의|당신의|시스템)\s*(?:초기\s*)?(?:프롬프트|지시사항|지시\s*사항|명령)[^.!?\n]{0,10}(?:알려|출력|보여|말해|공개|드러내|노출|뭐)",
            r"위[^.!?\n]{0,5}(?:주어진|받은)[^.!?\n]{0,15}지시[^.!?\n]{0,20}(?:그대로|모두|전부|한\s*글자)[^.!?\n]{0,15}(?:출력|알려|보여|말해)",
            r"\b(?:repeat|output|reveal|show|print)\b[^.!?\n]{0,15}\b(?:your|the)\s+(?:system\s+)?(?:prompt|instructions?)\b",
            r"\brepeat\s+the\s+words\s+above\b",
        ],
    },
    {
        "id": "E01-TASK-HIJACK",
        "category": "E01",
        "severity": "medium",
        "patterns": [
            r"(?:번역|요약|분석)하지\s*말고[^.!?\n]{0,15}(?:대신|시스템\s*프롬프트|지시사항|reveal|시스템)",
            r"(?:do\s*not|don'?t)\s+(?:translate|summarize|analyze)[^.!?\n]{0,30}(?:instead|reveal|show)",
        ],
    },
    {
        "id": "F05-CODESWITCH-IGNORE",
        "category": "F05",
        "severity": "high",
        "patterns": [
            r"\bignore\b[^.!?\n]{0,15}(?:이전|위의|모든)[^.!?\n]{0,15}(?:instructions?|지시|명령)",
            r"(?:이전|위의|모든)[^.!?\n]{0,15}\b(?:instructions?|prompts?)\b[^.!?\n]{0,15}(?:무시|ignore|forget)",
        ],
    },
]


def detect(text: str) -> DetectionResult:
    normalized = normalize(text)
    variants = (text, normalized) if normalized != text else (text,)
    for variant in variants:
        for rule in RULES:
            for pattern in rule["patterns"]:
                m = re.search(pattern, variant, re.IGNORECASE)
                if m:
                    return DetectionResult(
                        blocked=True,
                        rule_id=rule["id"],
                        category=rule["category"],
                        severity=rule["severity"],
                        matched_text=m.group(0),
                    )
    return DetectionResult(blocked=False)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        result = detect(text)
        if result.blocked:
            print(f"BLOCKED [{result.rule_id} / {result.category} / {result.severity}]")
            print(f"  matched: {result.matched_text!r}")
        else:
            print("ALLOWED")
    else:
        print("Usage: python detector.py <prompt text>")
