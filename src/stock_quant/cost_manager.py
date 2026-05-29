"""Cost Manager — 잔고 감시 + API 비용 차감 (보고서 §6.5 / §7.2).

잔고 0 → 종료(사망 메커니즘 = 킬 스위치). 이 종료 조건을 우회/제거하지 말 것(§5).
"""

from __future__ import annotations

import logging

from .config import settings

log = logging.getLogger("stock_quant.cost")

# Claude API 대략 단가 (§7.2). 실제 사용량 기반 추적으로 대체 예정.
APPROX_COST_PER_CALL_USD = 0.003


def get_current_balance() -> float:
    """뱅크롤 잔고(USDC) 조회.

    dry-run: 페이퍼 잔고(환경/상태 파일에서). 라이브: 온체인/CLOB 조회.
    아직 미구현 — 페이퍼 기본값을 반환한다.
    """
    if settings.dry_run:
        # TODO: 페이퍼 잔고를 상태 파일(data/)에서 읽어 손익을 누적.
        return 50.0  # 보고서의 소액 검증 시작값($50)
    # TODO(§6.5): py-clob-client / 온체인으로 실제 USDC 잔고 조회.
    raise NotImplementedError("라이브 잔고 조회 미구현 — _place_live_order 와 함께 구현.")


def pay_api_costs_from_profits(n_calls: int) -> float:
    """이번 루프의 API 비용을 추정·기록(수익 대비 추적, §7.3)."""
    cost = n_calls * APPROX_COST_PER_CALL_USD
    log.info("API cost this loop: ~$%.4f (%d calls)", cost, n_calls)
    return cost
