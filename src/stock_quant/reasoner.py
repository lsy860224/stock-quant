"""Claude Reasoner — 마켓 질문 → 공정가치(YES 확률) 추정 (보고서 §6.2).

프롬프트 골격(§6.6): ① 역사적 기저율 → ② 현재 증거 → ③ 시장가와의 차이 → "숫자만".
"""

from __future__ import annotations

import anthropic

from .config import settings

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 사용
    return _client


_PROMPT = """예측 시장 질문: {question}
관련 정보: {context}

다음 순서로 추론하되, 마지막 줄에는 YES 확률을 0~100 정수 하나로만 출력하세요.
1) 역사적 기저율(base rate)
2) 현재 이용 가능한 증거
3) 위를 종합한 확률

마지막 줄: 숫자만(0~100)."""


def estimate_fair_value(question: str, context: str = "") -> float:
    """YES 확률을 0~1 로 반환. 파싱 실패 시 0.5(중립) 반환."""
    msg = _get_client().messages.create(
        model=settings.claude_model,
        max_tokens=256,
        messages=[{"role": "user", "content": _PROMPT.format(question=question, context=context)}],
    )
    text = "".join(getattr(block, "text", "") for block in msg.content).strip()
    if not text:
        return 0.5
    last = text.splitlines()[-1].strip().rstrip("%")
    try:
        return max(0.0, min(float(last) / 100, 1.0))
    except ValueError:
        return 0.5
