"""Agent orchestration — 10분 루프 (보고서 §2 / §6.5).

스캔 → 추정 → 탐지 → 사이징 → 실행 → 비용/잔고 감시.
"""

from __future__ import annotations

import logging

from .config import settings
from .cost_manager import get_current_balance, pay_api_costs_from_profits
from .detector import find_opportunities
from .executor import cancel_all_orders, place_order
from .scanner import scan_markets

log = logging.getLogger("stock_quant.agent")


def run_once(scan_limit: int = 500) -> dict:
    """루프 1회 실행. 잔고 0이면 종료 신호를 반환."""
    bankroll = get_current_balance()
    if bankroll <= 0:
        log.warning("Balance $0 — Agent dies. Game over.")  # 사망 = 킬 스위치(§5)
        return {"alive": False, "bankroll": 0.0, "orders": []}

    markets = scan_markets(limit=scan_limit)
    opps = find_opportunities(markets)

    # 포지션 수 상한(§7.1): edge 절댓값 큰 순으로 잘라낸다.
    opps.sort(key=lambda o: abs(o.edge), reverse=True)
    opps = opps[: settings.max_positions]

    orders = []
    try:
        for opp in opps:
            bet_size = bankroll * opp.fraction
            orders.append(place_order(opp, bet_size))
    except Exception:  # noqa: BLE001 — 주문 중 오류 시 미체결 전량 취소(§7.1 킬스위치)
        log.exception("order placement failed — triggering cancel_all kill switch")
        cancel_all_orders()
        raise

    pay_api_costs_from_profits(n_calls=len(markets))
    log.info(
        "loop done: scanned=%d opportunities=%d orders=%d bankroll=$%.2f dry_run=%s",
        len(markets), len(opps), len(orders), bankroll, settings.dry_run,
    )
    return {"alive": True, "bankroll": bankroll, "orders": orders}


def main_loop() -> None:
    """schedule 기반 10분 루프 (§6.5)."""
    import schedule

    log.info("stock-quant starting (dry_run=%s, every %dm)", settings.dry_run, settings.loop_minutes)
    run_once()  # 즉시 1회
    schedule.every(settings.loop_minutes).minutes.do(run_once)
    while True:
        schedule.run_pending()
        _sleep(1)


def _sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
