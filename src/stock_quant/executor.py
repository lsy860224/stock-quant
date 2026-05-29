"""Order Executor — CLOB 주문 제출 (보고서 §6.4 / §7.1).

안전 설계:
- 기본은 DRY_RUN(페이퍼) — 실제 자금 이동 없음, 로그만 남긴다.
- 라이브 주문은 (1) DRY_RUN=false 이고 (2) py-clob-client(`uv sync --extra live`)가
  설치돼 있고 (3) 지갑 키가 있을 때만. 셋 중 하나라도 없으면 명시적으로 거부한다.
- 라이브 경로는 아직 미구현 — 실주문을 켜기 전 사용자 확인 + 소액 검증 필수(§7.1).
"""

from __future__ import annotations

import logging

from .config import settings
from .detector import Opportunity

log = logging.getLogger("stock_quant.executor")


def place_order(opp: Opportunity, bet_size_usdc: float) -> dict:
    """주문 1건 실행(또는 dry-run 시 로깅).

    Returns: {"status": "dry_run"|"submitted", ...} 형태의 결과.
    """
    summary = (
        f"{opp.side} {opp.question[:60]!r} "
        f"price={opp.market_price:.3f} fair={opp.fair_value:.3f} "
        f"edge={opp.edge:+.3f} size=${bet_size_usdc:.2f}"
    )

    if settings.dry_run:
        log.info("[DRY-RUN] would place: %s", summary)
        return {"status": "dry_run", "summary": summary}

    return _place_live_order(opp, bet_size_usdc, summary)


def _place_live_order(opp: Opportunity, bet_size_usdc: float, summary: str) -> dict:
    """라이브 CLOB 주문 — py-clob-client 필요. 아직 미구현(안전 가드)."""
    try:
        import py_clob_client  # type: ignore[import-not-found] # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "라이브 주문에는 py-clob-client 가 필요합니다. `uv sync --extra live` 후 재시도. "
            "(현재 DRY_RUN=false 인데 SDK 미설치 — 안전을 위해 중단)"
        ) from e

    # TODO(보고서 §6.4, §7.1): py-clob-client 로 CLOB 주문 제출.
    #   - 전용 지갑 서명 / conditionId / tokenId / side / size
    #   - GTD 만료, 배치(postOrders), 오류 시 cancelAll() 킬스위치
    raise NotImplementedError(
        "라이브 주문 경로는 의도적으로 미구현입니다. 실주문을 켜기 전 "
        "사용자 확인 + 소액($20~50) 검증을 거쳐 이 함수를 구현하세요. "
        f"(요청: {summary})"
    )
