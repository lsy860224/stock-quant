"""Order Executor — CLOB 주문 제출 (보고서 §6.4 / §7.1).

안전 설계:
- 기본은 DRY_RUN(페이퍼) — 실제 자금 이동 없음, 로그만 남긴다.
- 라이브 주문은 (1) DRY_RUN=false 이고 (2) py-clob-client(`uv sync --extra live`)가
  설치돼 있고 (3) POLYGON_WALLET_PRIVATE_KEY 가 있을 때만 동작한다.
- 오류 시 cancel_all() 킬스위치 제공.

라이브 사전조건 (코드 범위 밖, 1회성 수동):
- 에이전트 전용 지갑(메인과 분리)에 USDC(Polygon) 보유.
- CLOB Exchange 에 대한 USDC allowance(approve)가 설정돼 있어야 주문이 체결된다.
  (Polymarket UI 또는 별도 web3 스크립트로 1회 설정. py-clob-client 는 approve 를 하지 않는다.)
- 지갑 유형에 따라 CLOB_SIGNATURE_TYPE(0=EOA, 1=email-proxy, 2=safe)과
  CLOB_FUNDER_ADDRESS 가 필요할 수 있다(.env 참조). 기본은 EOA.
"""

from __future__ import annotations

import json
import logging
import os
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any

from .config import settings
from .detector import Opportunity

log = logging.getLogger("stock_quant.executor")

_client: Any = None  # 캐시된 ClobClient (라이브 모드에서만 생성)


def place_order(opp: Opportunity, bet_size_usdc: float) -> dict:
    """주문 1건 실행(또는 dry-run 시 로깅).

    Returns: {"status": "dry_run"|"submitted"|"skipped", ...}.
    """
    summary = (
        f"{opp.side} {opp.question[:60]!r} "
        f"price={opp.market_price:.3f} fair={opp.fair_value:.3f} "
        f"edge={opp.edge:+.3f} budget=${bet_size_usdc:.2f}"
    )

    if settings.dry_run:
        log.info("[DRY-RUN] would place: %s", summary)
        return {"status": "dry_run", "summary": summary}

    return _place_live_order(opp, bet_size_usdc, summary)


# --------------------------------------------------------------------------- #
# 순수 헬퍼 (네트워크/키 불필요 — 단위 테스트 대상)
# --------------------------------------------------------------------------- #

def _token_id_for_side(market: dict[str, Any], side: str) -> str:
    """베팅 방향에 해당하는 CLOB token id. YES→clobTokenIds[0], NO→[1].

    YES 매수 = YES 토큰 매수, NO 매수 = NO 토큰 매수 → 주문 side 는 항상 BUY.
    """
    raw = market.get("clobTokenIds")
    ids = json.loads(raw) if isinstance(raw, str) else raw
    if not ids or len(ids) < 2:
        raise ValueError("market has no usable clobTokenIds")
    return str(ids[0] if side == "YES" else ids[1])


def _round_price_to_tick(price: float, tick: float) -> float:
    """가격을 유효 tick 그리드로 반올림 (create_order 의 price_valid 통과용)."""
    t = Decimal(str(tick))
    steps = (Decimal(str(price)) / t).to_integral_value(rounding=ROUND_HALF_UP)
    return float(steps * t)


def _shares_for_budget(bet_size_usdc: float, price: float) -> float:
    """예산(USDC) 안에서 살 수 있는 outcome 토큰 수. cost = price*size ≤ budget.

    예산 초과 방지를 위해 0.01 단위로 내림(ROUND_DOWN)한다.
    """
    if price <= 0:
        return 0.0
    shares = Decimal(str(bet_size_usdc)) / Decimal(str(price))
    return float(shares.quantize(Decimal("0.01"), rounding=ROUND_DOWN))


# --------------------------------------------------------------------------- #
# 라이브 경로 (py-clob-client + 지갑 키 필요)
# --------------------------------------------------------------------------- #

def _get_clob_client() -> Any:
    """L1(개인키) + L2(API creds) 인증이 설정된 ClobClient 를 캐시 반환."""
    global _client
    if _client is not None:
        return _client

    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.constants import POLYGON
    except ImportError as e:
        raise RuntimeError(
            "라이브 주문에는 py-clob-client 가 필요합니다. `uv sync --extra live` 후 재시도."
        ) from e

    pk = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
    if not pk:
        raise RuntimeError("POLYGON_WALLET_PRIVATE_KEY 미설정 — 라이브 주문 불가.")

    kwargs: dict[str, Any] = {"host": settings.clob_host, "key": pk, "chain_id": POLYGON}
    sig_type = os.getenv("CLOB_SIGNATURE_TYPE")
    funder = os.getenv("CLOB_FUNDER_ADDRESS")
    if sig_type:
        kwargs["signature_type"] = int(sig_type)
    if funder:
        kwargs["funder"] = funder

    client = ClobClient(**kwargs)
    client.set_api_creds(client.create_or_derive_api_creds())  # L2 creds 파생
    _client = client
    log.info("CLOB client ready (chain=POLYGON, sig_type=%s)", sig_type or "default/EOA")
    return _client


def _place_live_order(opp: Opportunity, bet_size_usdc: float, summary: str) -> dict:
    """라이브 CLOB 주문: 현재 ask 에 marketable limit BUY 제출.

    실제 자금이 이동한다. DRY_RUN=false 일 때만 호출됨(place_order 에서 게이트).
    """
    from py_clob_client.clob_types import OrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY

    client = _get_clob_client()
    token_id = _token_id_for_side(opp.market, opp.side)

    # 현재 매수 호가(ask). get_price 응답: {"price": "0.09"} (문자열) — 라이브 검증 형태.
    quote = client.get_price(token_id, BUY)
    try:
        ask = float(quote["price"]) if isinstance(quote, dict) else float(quote)
    except (KeyError, TypeError, ValueError):
        log.warning("invalid price quote %r — skip: %s", quote, summary)
        return {"status": "skipped", "reason": "no_quote", "summary": summary}
    if not (0 < ask < 1):
        return {"status": "skipped", "reason": "ask_out_of_range", "ask": ask, "summary": summary}

    tick = float(client.get_tick_size(token_id))
    price = _round_price_to_tick(ask, tick)
    size = _shares_for_budget(bet_size_usdc, price)

    min_size = float(opp.market.get("orderMinSize") or 0)
    if size <= 0 or size < min_size:
        return {"status": "skipped", "reason": "below_min_size", "size": size, "min": min_size}

    order = client.create_order(OrderArgs(token_id=token_id, price=price, size=size, side=BUY))
    resp = client.post_order(order, OrderType.GTC)
    log.info("[LIVE] submitted BUY token=%s price=%s size=%s :: %s", token_id[:12], price, size, summary)
    return {
        "status": "submitted",
        "side": opp.side,
        "token_id": token_id,
        "price": price,
        "size": size,
        "cost_estimate": round(price * size, 4),
        "response": resp,
    }


def cancel_all_orders() -> Any:
    """킬스위치(보고서 §7.1) — 모든 미체결 주문 취소. dry-run 에서는 no-op."""
    if settings.dry_run:
        log.info("[DRY-RUN] cancel_all skipped")
        return None
    return _get_clob_client().cancel_all()
