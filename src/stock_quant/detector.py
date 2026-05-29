"""Mispricing Detector — 공정가치 vs 시장가 괴리 탐지 (보고서 §6.4)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .config import settings
from .context import get_context
from .kelly import kelly_fraction
from .reasoner import estimate_fair_value


@dataclass
class Opportunity:
    market: dict[str, Any]
    question: str
    market_price: float    # 현재 YES 가격 (0~1)
    fair_value: float      # AI 추정 YES 확률 (0~1)
    edge: float            # fair_value - market_price
    side: str              # "YES" | "NO"
    fraction: float        # 뱅크롤 대비 베팅 비율 (Kelly, ≤ max_fraction)


def _is_yes_no(market: dict[str, Any]) -> bool:
    """이진 Yes/No 마켓만 거래. (Up/Down 등 비이진 마켓은 스킵.)"""
    raw = market.get("outcomes")
    try:
        outcomes = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(outcomes, list) and [str(o).lower() for o in outcomes] == ["yes", "no"]


def _yes_price(market: dict[str, Any]) -> float | None:
    """YES 가격(0~1). Gamma 실제 스키마: bestBid/bestAsk 중간값, 없으면 lastTradePrice.

    (보고서 §6.1 의 `outcomePrices` 는 현재 Gamma API 에 존재하지 않는다 — 검증으로 확인.)
    """
    bid, ask = market.get("bestBid"), market.get("bestAsk")
    try:
        if bid is not None and ask is not None:
            mid = (float(bid) + float(ask)) / 2
            if 0 < mid < 1:
                return mid
        last_raw = market.get("lastTradePrice")
        if last_raw is None:
            return None
        last = float(last_raw)
        return last if 0 < last < 1 else None
    except (ValueError, TypeError):
        return None


def find_opportunities(markets: list[dict[str, Any]]) -> list[Opportunity]:
    """가드레일을 통과한 거래 후보만 반환.

    필터: Yes/No 이진 마켓, 유동성 ≥ MIN_LIQUIDITY, |edge| ≥ EDGE_THRESHOLD, Kelly 분수 > 0.
    """
    out: list[Opportunity] = []
    for market in markets:
        if not _is_yes_no(market):
            continue
        if float(market.get("liquidityNum", 0) or 0) < settings.min_liquidity:
            continue
        price = _yes_price(market)
        if price is None or not (0 < price < 1):
            continue

        question = market.get("question", "")
        fair = estimate_fair_value(question, get_context(market))
        edge = fair - price
        if abs(edge) < settings.edge_threshold:
            continue

        # edge>0 → YES 저평가 매수, edge<0 → NO 매수. Kelly 는 승확률 기준.
        side = "YES" if edge > 0 else "NO"
        win_prob = fair if side == "YES" else 1 - fair
        ref_price = price if side == "YES" else 1 - price
        fraction = kelly_fraction(win_prob, ref_price, settings.max_fraction)
        if fraction <= 0:
            continue

        out.append(Opportunity(market, question, price, fair, edge, side, fraction))
    return out
