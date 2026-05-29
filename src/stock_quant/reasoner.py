"""Claude Reasoner — 마켓 질문 → 공정가치(YES 확률) 추정 (보고서 §6.2).

프롬프트 골격(§6.6): ① 역사적 기저율 → ② 현재 증거 → ③ 시장가와의 차이 → "숫자만".
"""

from __future__ import annotations

import re

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

다음을 간단히(각 1~2문장) 추론하세요.
1) 역사적 기저율(base rate)
2) 현재 이용 가능한 증거
3) 종합 판단

그리고 맨 마지막 줄에 반드시 다음 형식으로만 답하세요(YES가 일어날 확률 %):
ANSWER: <0부터 100 사이 정수>"""

_ANSWER_RE = re.compile(r"ANSWER:\s*(\d{1,3})", re.IGNORECASE)


def _parse_probability(text: str) -> float:
    """LLM 응답에서 YES 확률(0~1)을 추출. 실패 시 0.5(중립)."""
    if not text:
        return 0.5
    m = _ANSWER_RE.search(text)
    if m:
        return max(0.0, min(int(m.group(1)) / 100, 1.0))
    # 폴백: 0~100 범위 정수 중 마지막 것 (연도 등 4자리는 \b\d{1,3}\b 로 제외)
    nums = [int(n) for n in re.findall(r"\b(\d{1,3})\b", text) if int(n) <= 100]
    return nums[-1] / 100 if nums else 0.5


def estimate_fair_value(question: str, context: str = "") -> float:
    """YES 확률을 0~1 로 반환. 파싱 실패 시 0.5(중립) 반환.

    CoT 추론이 토큰 상한에 잘리지 않도록 충분한 max_tokens + ANSWER 마커로 안정 파싱.
    """
    msg = _get_client().messages.create(
        model=settings.claude_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": _PROMPT.format(question=question, context=context)}],
    )
    text = "".join(getattr(block, "text", "") for block in msg.content).strip()
    return _parse_probability(text)
