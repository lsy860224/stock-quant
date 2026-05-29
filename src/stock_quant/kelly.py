"""Kelly Criterion 포지션 사이징 (보고서 §6.3).

순수 함수 — 외부 의존성 없음. 테스트로 정확성 보장(tests/test_kelly.py).
"""

from __future__ import annotations


def kelly_fraction(p: float, market_price: float, max_fraction: float = 0.06) -> float:
    """최적 베팅 비율을 뱅크롤 대비 분수로 반환.

    Args:
        p: AI 추정 YES 확률 (0~1).
        market_price: 현재 YES 가격 (0~1).
        max_fraction: 상한 (기본 6%, §7.1 가드레일).

    Returns:
        0 ~ max_fraction 사이로 클램프된 베팅 비율.
        엣지가 음수면 0 (이 함수는 매수 사이즈만, 방향은 호출부가 결정).
    """
    if market_price <= 0 or market_price >= 1:
        return 0.0
    b = (1 - market_price) / market_price          # 승리 시 배당률
    kelly = (p * b - (1 - p)) / b                  # f = (p*b - (1-p)) / b
    return max(0.0, min(kelly, max_fraction))
