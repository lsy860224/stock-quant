"""Market Scanner — Polymarket Gamma API 로 활성 마켓 수집 (보고서 §6.1)."""

from __future__ import annotations

from typing import Any

import requests

from .config import settings


def scan_markets(limit: int = 500) -> list[dict[str, Any]]:
    """활성 마켓을 거래량 순으로 수집.

    Returns: Gamma `/markets` 응답 리스트. 각 항목은 question/outcomePrices/
    conditionId/category/liquidity 등을 포함한다.
    """
    params: dict[str, Any] = {
        "active": True,
        "closed": False,
        "limit": limit,
        "order": "volume24hr",
        "ascending": False,
    }
    resp = requests.get(f"{settings.gamma_api}/markets", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else data.get("data", [])
