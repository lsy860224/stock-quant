"""카테고리별 컨텍스트 라우팅 (보고서 §6.6).

마켓 카테고리에 따라 외부 데이터 소스를 선택해 LLM 추정 정확도를 높인다.
아래 fetcher 들은 스텁 — 실데이터 소스(§5.2)는 필요해질 때 채운다.
"""

from __future__ import annotations

from typing import Any


def get_context(market: dict[str, Any]) -> str:
    """마켓 카테고리로 분기해 관련 컨텍스트 문자열을 반환."""
    cat = str(market.get("category", "")).lower()
    if "weather" in cat:
        return _get_noaa_forecast(market)
    if "sports" in cat:
        return _get_injury_report(market)
    if "crypto" in cat:
        return _get_onchain_metrics(market)
    return _search_news(market.get("question", ""))


# --- 데이터 fetcher 스텁 (§5.2) ---
# 실구현 전까지 빈 컨텍스트를 반환 → LLM 은 기저율(base rate) 기반으로만 추정.

def _get_noaa_forecast(market: dict[str, Any]) -> str:
    return ""  # TODO: NOAA api.weather.gov (무료)


def _get_injury_report(market: dict[str, Any]) -> str:
    return ""  # TODO: ESPN / SportsRadar / Rotowire


def _get_onchain_metrics(market: dict[str, Any]) -> str:
    return ""  # TODO: Dune / Nansen / Glassnode


def _search_news(question: str) -> str:
    return ""  # TODO: 뉴스 검색 API (fallback)
