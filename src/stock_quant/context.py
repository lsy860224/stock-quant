"""카테고리별 컨텍스트 라우팅 + 실데이터 fetcher (보고서 §5.2 / §6.6).

마켓 카테고리에 따라 외부 데이터 소스를 호출해 LLM 추정 정확도를 높인다.
설계 원칙:
- 모든 fetcher 는 **best-effort** — 실패/미해결 시 빈 문자열을 반환하고 절대 예외를 루프로 던지지 않는다.
  (컨텍스트가 비면 reasoner 는 기저율 기반으로만 추정.)
- 키 없이 동작하는 무료 API 우선(NOAA·CoinGecko·ESPN·Nominatim). 뉴스만 NEWS_API_KEY 게이트.
- 엔드포인트 스키마는 라이브 검증(2026-05-29)으로 확인된 형태를 따른다.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

from .config import settings

log = logging.getLogger("stock_quant.context")

_MAX_CONTEXT_CHARS = 600  # LLM 프롬프트에 넣을 컨텍스트 상한


def get_context(market: dict[str, Any]) -> str:
    """마켓 카테고리로 분기해 관련 컨텍스트 문자열을 반환 (실패 시 "")."""
    cat = str(market.get("category", "")).lower()
    question = str(market.get("question", ""))
    try:
        if "weather" in cat:
            return _get_noaa_forecast(question)
        if "sports" in cat:
            return _get_injury_report(question)
        if "crypto" in cat:
            return _get_onchain_metrics(question)
        return _search_news(question)
    except Exception as e:  # noqa: BLE001 — fetcher 는 절대 루프를 죽이지 않는다
        log.debug("context fetch failed for %r: %s", question[:50], e)
        return ""


# --------------------------------------------------------------------------- #
# HTTP / 추출 헬퍼
# --------------------------------------------------------------------------- #

def _ua() -> dict[str, str]:
    return {"User-Agent": settings.http_user_agent}


def _get_json(url: str, params: dict[str, Any] | None = None) -> Any | None:
    try:
        resp = requests.get(url, params=params, headers=_ua(), timeout=settings.http_timeout)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as e:
        log.debug("GET %s failed: %s", url, e)
        return None


def _capitalized_phrases(text: str) -> list[str]:
    """질문에서 고유명사 후보(대문자로 시작하는 연속 단어 묶음)를 길이 순으로 추출.

    예: "Will New York City exceed 90F by June 1?" → ["New York City", "June"]
    문장 첫 단어는 항상 대문자라 노이즈가 될 수 있어, 2글자 이상 + 흔한 의문사 제외.
    """
    stop = {"Will", "Does", "Did", "Is", "Are", "Has", "Have", "Can", "Should", "What", "Who", "When"}
    phrases = re.findall(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b", text)
    cleaned = []
    for p in phrases:
        words = [w for w in p.split() if w not in stop]
        if words:
            cleaned.append(" ".join(words))
    # 길이(단어 수) 긴 것 우선 — 고유명사일 확률이 높다.
    return sorted(dict.fromkeys(cleaned), key=lambda s: -len(s.split()))


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text[:_MAX_CONTEXT_CHARS]


# --------------------------------------------------------------------------- #
# 날씨 — NOAA (미국 한정, 무료, UA 필요). 위치는 Nominatim 으로 지오코딩.
# --------------------------------------------------------------------------- #

# 실제 행정구역(도시/마을)만 인정. amenity(식당)·highway(도로) 등 동명 POI 오매칭 방지.
_PLACE_ADDRESSTYPES = {"city", "town", "village", "hamlet", "municipality"}


def _get_noaa_forecast(question: str) -> str:
    for place in _capitalized_phrases(question):
        geo = _get_json(
            "https://nominatim.openstreetmap.org/search",
            {"q": place, "format": "json", "limit": 1, "countrycodes": "us", "addressdetails": 1},
        )
        if not geo:
            continue
        hit = geo[0]
        # 행정구역(class=place/boundary + addresstype=city/town/...)이 아니면 동명 POI → 스킵.
        if hit.get("class") not in {"place", "boundary"} or hit.get("addresstype") not in _PLACE_ADDRESSTYPES:
            continue
        lat, lon = hit["lat"], hit["lon"]
        points = _get_json(f"https://api.weather.gov/points/{lat},{lon}")
        if not points:
            continue
        forecast_url = points.get("properties", {}).get("forecast")
        if not forecast_url:
            continue
        fc = _get_json(forecast_url)
        periods = (fc or {}).get("properties", {}).get("periods", [])[:3]
        if not periods:
            continue
        lines = [f"{p['name']}: {p['temperature']}{p['temperatureUnit']}, {p['shortForecast']}" for p in periods]
        return _clip(f"NOAA 날씨 예보 ({place}): " + " | ".join(lines))
    return ""


# --------------------------------------------------------------------------- #
# 스포츠 — ESPN 검색 (무료). 부상/뉴스 헤드라인.
# --------------------------------------------------------------------------- #

def _get_injury_report(question: str) -> str:
    query = next(iter(_capitalized_phrases(question)), question)
    data = _get_json("https://site.web.api.espn.com/apis/search/v2", {"query": query, "limit": 5})
    if not data:
        return ""
    headlines: list[str] = []
    for group in data.get("results", []):
        if group.get("type") != "article":
            continue
        for item in group.get("contents", []):
            title = item.get("displayName") or item.get("title") or ""
            desc = item.get("description") or ""
            if title:
                headlines.append(f"{title}. {desc}".strip())
    if not headlines:
        return ""
    return _clip(f"ESPN 관련 뉴스 ({query}): " + " / ".join(headlines[:3]))


# --------------------------------------------------------------------------- #
# 크립토 — CoinGecko (무료). 시세/24h 변동/시총 순위.
#   * 진짜 온체인 메트릭(Dune/Nansen/Glassnode)은 키 필요 — 추후 확장 지점.
# --------------------------------------------------------------------------- #

def _get_onchain_metrics(question: str) -> str:
    for term in _capitalized_phrases(question):
        search = _get_json("https://api.coingecko.com/api/v3/search", {"query": term})
        coins = (search or {}).get("coins", [])
        if not coins:
            continue
        coin_id = coins[0]["id"]
        markets = _get_json(
            "https://api.coingecko.com/api/v3/coins/markets",
            {"vs_currency": "usd", "ids": coin_id},
        )
        if not markets:
            continue
        d = markets[0]
        chg = d.get("price_change_percentage_24h")
        chg_s = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else "n/a"
        return _clip(
            f"CoinGecko {d.get('symbol', '').upper()} 시세: "
            f"${d.get('current_price')} (24h {chg_s}), 시총 순위 #{d.get('market_cap_rank')}"
        )
    return ""


# --------------------------------------------------------------------------- #
# 범용 fallback — 뉴스 (NEWS_API_KEY 있을 때만, newsapi.org).
# --------------------------------------------------------------------------- #

def _search_news(question: str) -> str:
    if not settings.news_api_key:
        return ""  # 키 없으면 비활성 — reasoner 는 기저율로만 추정
    data = _get_json_with_key(
        "https://newsapi.org/v2/everything",
        {"q": question, "language": "en", "sortBy": "publishedAt", "pageSize": 5},
    )
    articles = (data or {}).get("articles", [])
    if not articles:
        return ""
    items = [f"{a.get('title', '')}. {a.get('description') or ''}".strip() for a in articles[:3]]
    return _clip("최근 뉴스: " + " / ".join(i for i in items if i))


def _get_json_with_key(url: str, params: dict[str, Any]) -> Any | None:
    try:
        headers = {**_ua(), "X-Api-Key": settings.news_api_key}
        resp = requests.get(url, params=params, headers=headers, timeout=settings.http_timeout)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as e:
        log.debug("news GET failed: %s", e)
        return None
