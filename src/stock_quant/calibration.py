"""Brier Score 캘리브레이션 (보고서 §7.3 / §8.3).

Brier score = mean((예측확률 − 실제결과)^2). 0에 가까울수록 정확·잘 보정됨.
0.25 = 무작정 0.5 찍는 수준의 기준선. 0.25 미만이어야 정보가치가 있다.

두 가지 모드:
- backtest_market_baseline(): resolved 마켓으로 **시장 가격 자체**의 Brier 를 지금 계산.
  (LLM 키 불필요. 에이전트 LLM 이 넘어서야 할 기준선.)
- forward 페이퍼: record_prediction() 으로 dry-run 예측을 누적 → resolve_predictions()
  로 결과를 채우고 → report() 로 **에이전트(LLM)** Brier 측정.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .config import settings

_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "calibration.db"
# 커밋 가능한 텍스트 시드 (원격 채점용). DB 는 gitignore 라 원격엔 없으므로,
# 빈 DB 일 때 이 JSONL 에서 예측을 복원한다 (결과/타임스탬프는 제외 → 원격이 새로 resolve).
_SEED_PATH = _DB_PATH.parent / "predictions_seed.jsonl"


# --------------------------------------------------------------------------- #
# 순수 통계 (네트워크 없음 — 단위 테스트 대상)
# --------------------------------------------------------------------------- #

def brier_score(pairs: list[tuple[float, float]]) -> float:
    """pairs = [(예측확률 0~1, 실제결과 0|1), ...] → Brier score."""
    if not pairs:
        return float("nan")
    return sum((p - o) ** 2 for p, o in pairs) / len(pairs)


@dataclass
class CalibrationBin:
    lo: float
    hi: float
    count: int
    mean_pred: float       # 이 구간 평균 예측확률
    observed_freq: float    # 이 구간 실제 발생 빈도
    gap: float              # |mean_pred − observed_freq| (작을수록 잘 보정)


def calibration_table(pairs: list[tuple[float, float]], bins: int = 10) -> list[CalibrationBin]:
    """예측확률을 구간으로 나눠 '예측 vs 실제 빈도' 보정 곡선을 만든다."""
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(bins)]
    for p, o in pairs:
        idx = min(int(p * bins), bins - 1)
        buckets[idx].append((p, o))
    table: list[CalibrationBin] = []
    for i, b in enumerate(buckets):
        if not b:
            continue
        mean_pred = sum(p for p, _ in b) / len(b)
        observed = sum(o for _, o in b) / len(b)
        table.append(
            CalibrationBin(i / bins, (i + 1) / bins, len(b), mean_pred, observed, abs(mean_pred - observed))
        )
    return table


def format_report(label: str, pairs: list[tuple[float, float]]) -> str:
    if not pairs:
        return f"[{label}] 표본 없음."
    bs = brier_score(pairs)
    lines = [
        f"[{label}] n={len(pairs)}  Brier={bs:.4f}  (기준선 0.25; 낮을수록 좋음)",
        "  pred범위    n   평균예측  실제빈도   gap",
    ]
    for b in calibration_table(pairs):
        lines.append(
            f"  {b.lo:.1f}-{b.hi:.1f}  {b.count:>4}   {b.mean_pred:.3f}    {b.observed_freq:.3f}   {b.gap:.3f}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 시장 베이스라인 백테스트 (resolved 마켓, 키 불필요)
# --------------------------------------------------------------------------- #

def _ua() -> dict[str, str]:
    return {"User-Agent": settings.http_user_agent}


def _parse_json_list(raw: Any) -> list[Any] | None:
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
        return v if isinstance(v, list) else None
    except (json.JSONDecodeError, TypeError):
        return None


def fetch_resolved_markets(limit: int = 200) -> list[dict[str, Any]]:
    """resolved 마켓 수집. Gamma 는 페이지당 100개 상한이라 offset 으로 페이지네이션."""
    out: list[dict[str, Any]] = []
    page = 100
    offset = 0
    while len(out) < limit:
        params: dict[str, Any] = {
            "closed": True, "limit": min(page, limit - len(out)),
            "offset": offset, "order": "volume24hr", "ascending": False,
        }
        resp = requests.get(f"{settings.gamma_api}/markets", params=params, headers=_ua(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        batch = data if isinstance(data, list) else data.get("data", [])
        if not batch:
            break
        out.extend(batch)
        offset += len(batch)
        if len(batch) < page:
            break
    return out


def market_baseline_pairs(markets: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """resolved 이진 마켓에서 (시장가_해결~24h전, 실제결과) 쌍을 만든다.

    - 실제결과: outcomePrices[0] (이진 마켓에서 0 또는 1 로 해결).
    - 예측(시장가): lastTradePrice − oneDayPriceChange 로 ~24h 전 가격을 복원 후 [0,1] 클램프.
      (별도 히스토리 호출 없이 Gamma 필드만으로 베이스라인 산출.)
    """
    pairs: list[tuple[float, float]] = []
    for m in markets:
        outcomes = _parse_json_list(m.get("outcomes"))
        prices = _parse_json_list(m.get("outcomePrices"))
        if not outcomes or len(outcomes) != 2 or not prices or len(prices) != 2:
            continue
        if str(m.get("umaResolutionStatus")) != "resolved":
            continue
        try:
            actual = float(prices[0])
        except (ValueError, TypeError):
            continue
        if actual not in (0.0, 1.0):  # 깔끔히 해결된 것만
            continue
        last = m.get("lastTradePrice")
        chg = m.get("oneDayPriceChange")
        if last is None or chg is None:
            continue
        try:
            pred = float(last) - float(chg)  # ~24h 전 가격 복원
        except (ValueError, TypeError):
            continue
        pred = max(0.0, min(1.0, pred))
        pairs.append((pred, actual))
    return pairs


def backtest_market_baseline(limit: int = 200) -> str:
    markets = fetch_resolved_markets(limit)
    pairs = market_baseline_pairs(markets)
    return format_report(f"시장 베이스라인 (resolved {len(markets)}건 중 {len(pairs)}건)", pairs)


def resolved_yesno_records(markets: list[dict[str, Any]], since: str) -> list[dict[str, Any]]:
    """resolved 이진 Yes/No 마켓만 추출 (에이전트가 실제 거래하는 유형과 동일).

    since(YYYY-MM-DD) 이후 종료분만 → 모델 cutoff 이후라 lookahead 최소화.
    각 레코드: question / actual(0|1, outcome[0]=YES) / market_pred(~24h전 시장가).
    """
    recs: list[dict[str, Any]] = []
    for m in markets:
        outcomes = _parse_json_list(m.get("outcomes"))
        prices = _parse_json_list(m.get("outcomePrices"))
        if not outcomes or [str(o).lower() for o in outcomes] != ["yes", "no"]:
            continue
        if not prices or len(prices) != 2 or str(m.get("umaResolutionStatus")) != "resolved":
            continue
        if (m.get("endDate") or "") <= since:
            continue
        try:
            actual = float(prices[0])
        except (ValueError, TypeError):
            continue
        if actual not in (0.0, 1.0):
            continue
        market_pred = None
        last, chg = m.get("lastTradePrice"), m.get("oneDayPriceChange")
        if last is not None and chg is not None:
            try:
                market_pred = max(0.0, min(1.0, float(last) - float(chg)))
            except (ValueError, TypeError):
                market_pred = None
        recs.append({"question": m["question"], "actual": actual, "market_pred": market_pred})
    return recs


def backtest_agent_llm(
    sample: int = 120, fetch_limit: int = 1000, since: str = "2026-01-31", workers: int = 8
) -> str:
    """에이전트 LLM 의 Brier 를 resolved 마켓으로 측정 (ANTHROPIC_API_KEY 필요).

    lookahead 방지: (1) cutoff 이후 종료분만, (2) 라이브 컨텍스트 fetcher 비활성(context="")
    — 해결 후 데이터가 누설되지 않도록 질문+모델 지식만으로 예측.
    """
    import logging
    from concurrent.futures import ThreadPoolExecutor

    from .reasoner import estimate_fair_value

    log = logging.getLogger("stock_quant.calibration")
    markets = fetch_resolved_markets(fetch_limit)
    recs = resolved_yesno_records(markets, since)[:sample]
    if not recs:
        return f"백테스트 대상 없음 (resolved Yes/No, endDate>{since})."
    log.info("agent backtest: %d markets, LLM=%s, workers=%d", len(recs), settings.claude_model, workers)

    def _predict(rec: dict[str, Any]) -> float:
        try:
            return estimate_fair_value(rec["question"], context="")  # 컨텍스트 비활성
        except Exception as e:  # noqa: BLE001 — 개별 실패가 전체를 죽이지 않음
            log.warning("predict failed (%s): %s", rec["question"][:40], e)
            return 0.5

    with ThreadPoolExecutor(max_workers=workers) as ex:
        preds = list(ex.map(_predict, recs))

    agent_pairs = [(p, r["actual"]) for p, r in zip(preds, recs)]
    market_pairs = [(r["market_pred"], r["actual"]) for r in recs if r["market_pred"] is not None]
    return (
        format_report(f"에이전트 LLM (컨텍스트 비활성, endDate>{since})", agent_pairs)
        + "\n"
        + format_report(f"같은 마켓 시장가 ~24h전 (n={len(market_pairs)})", market_pairs)
        + "\n\n주의: resolved 마켓 backtest. cutoff 이후 종료분만 사용해 lookahead 최소화했으나, "
        "AI/메타 등 일부 질문은 모델이 결과를 알 수 있어 낙관 편향 가능. "
        "**에이전트 Brier < 시장가 Brier** 여야 edge 가 실재한다는 신호."
    )


# --------------------------------------------------------------------------- #
# Forward 페이퍼 캘리브레이션 (SQLite 누적 → 해결 시 채점)
# --------------------------------------------------------------------------- #

def snapshot_predictions(
    sample: int = 60, scan_limit: int = 500, horizon_days: int = 14, workers: int = 6
) -> str:
    """현재 열린 Yes/No 마켓에 **컨텍스트 포함** 예측을 기록 (forward 페이퍼).

    백테스트와 달리 edge 필터 없이 샘플 전체를 기록(무편향 캘리브레이션).
    horizon_days 내 종료 마켓 우선 → 며칠 내 --resolve/--report 로 채점 가능.
    마켓이 아직 안 열렸으니 Brier 는 지금 안 나오고, 해결 후 산출된다.
    """
    import logging
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timedelta, timezone

    from .context import get_context
    from .detector import _is_yes_no, _yes_price
    from .reasoner import estimate_fair_value
    from .scanner import scan_markets

    log = logging.getLogger("stock_quant.calibration")
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=horizon_days)

    def _ends_soon(m: dict[str, Any]) -> bool:
        raw = m.get("endDate")
        if not raw:
            return False
        try:
            end = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return False
        return now < end <= cutoff

    markets = scan_markets(scan_limit)
    cands: list[tuple[dict[str, Any], float]] = []
    for m in markets:
        if not _is_yes_no(m) or not _ends_soon(m):
            continue
        if float(m.get("liquidityNum", 0) or 0) < settings.min_liquidity:
            continue
        price = _yes_price(m)
        if price is None:
            continue
        cands.append((m, price))
        if len(cands) >= sample:
            break

    if not cands:
        return f"snapshot 대상 없음 (Yes/No, {horizon_days}일 내 종료, liquidity≥{settings.min_liquidity})."
    log.info("snapshot: %d markets, context-included, LLM=%s", len(cands), settings.claude_model)

    def _predict(item: tuple[dict[str, Any], float]) -> tuple[dict[str, Any], float, float]:
        m, price = item
        fair = estimate_fair_value(m["question"], get_context(m))  # 컨텍스트 포함
        return m, price, fair

    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(_predict, cands))

    for m, price, fair in results:
        side = "YES" if fair >= price else "NO"
        record_prediction(str(m.get("conditionId", "")), m["question"], side, fair, price)

    edges = [abs(fair - price) for _, price, fair in results]
    big = sum(1 for e in edges if e >= settings.edge_threshold)
    return (
        f"snapshot: {len(results)}건 컨텍스트 포함 예측 기록 → data/calibration.db "
        f"(|edge|≥{settings.edge_threshold:.0%}: {big}건). "
        f"{horizon_days}일 내 종료 예정 — 이후 `calibrate --resolve` → `--report` 로 Brier 산출."
    )


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS predictions (
            condition_id TEXT, question TEXT, side TEXT,
            predicted REAL, market_price REAL,
            outcome REAL, recorded_at REAL, resolved_at REAL,
            PRIMARY KEY (condition_id, recorded_at)
        )"""
    )
    # 빈 DB + 시드 존재 시 복원 (원격 stateless 채점). 로컬은 이미 데이터가 있어 건너뜀.
    if _SEED_PATH.exists() and conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 0:
        _load_seed(conn)
    return conn


def _load_seed(conn: sqlite3.Connection) -> None:
    import logging

    rows = 0
    with open(_SEED_PATH, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            conn.execute(
                "INSERT OR IGNORE INTO predictions VALUES (?,?,?,?,?,?,?,?)",
                (d["condition_id"], d["question"], d["side"], d["predicted"],
                 d["market_price"], None, float(i), None),
            )
            rows += 1
    conn.commit()
    logging.getLogger("stock_quant.calibration").info("seeded %d predictions from %s", rows, _SEED_PATH.name)


def export_seed() -> int:
    """현재 예측을 커밋용 JSONL 시드로 내보낸다 (결과·타임스탬프 제외, 비밀 없음)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT condition_id, question, side, predicted, market_price FROM predictions"
        ).fetchall()
    _SEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_SEED_PATH, "w", encoding="utf-8") as f:
        for cid, q, side, pred, mp in rows:
            f.write(json.dumps(
                {"condition_id": cid, "question": q, "side": side, "predicted": pred, "market_price": mp},
                ensure_ascii=False,
            ) + "\n")
    return len(rows)


def record_prediction(
    condition_id: str, question: str, side: str, predicted: float, market_price: float
) -> None:
    """dry-run 루프에서 예측 1건을 기록 (forward 페이퍼)."""
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO predictions VALUES (?,?,?,?,?,?,?,?)",
            (condition_id, question, side, predicted, market_price, None, time.time(), None),
        )


def resolve_predictions() -> int:
    """미해결 예측의 마켓을 Gamma 에서 조회해 결과(outcome)를 채운다. 채운 건수 반환."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT condition_id FROM predictions WHERE outcome IS NULL"
        ).fetchall()
        resolved = 0
        for (cid,) in rows:
            outcome = _fetch_outcome(cid)
            if outcome is None:
                continue
            conn.execute(
                "UPDATE predictions SET outcome=?, resolved_at=? WHERE condition_id=? AND outcome IS NULL",
                (outcome, time.time(), cid),
            )
            resolved += 1
        return resolved


def _fetch_outcome(condition_id: str) -> float | None:
    """conditionId 로 CLOB 마켓을 조회해 outcome[0] 결과(1.0|0.0)를 반환, 미해결이면 None.

    CLOB `/markets/{conditionId}` 의 tokens[].winner 로 판정 (라이브 검증한 방식).
    """
    resp = requests.get(f"{settings.clob_host}/markets/{condition_id}", headers=_ua(), timeout=30)
    if not resp.ok:
        return None
    d = resp.json()
    tokens = d.get("tokens") or []
    if not d.get("closed") or len(tokens) != 2:
        return None
    if tokens[0].get("winner") is True:
        return 1.0
    if tokens[1].get("winner") is True:
        return 0.0
    return None  # closed 지만 승자 미확정 → 다음 resolve 때 재시도


def report() -> str:
    """기록된 forward 예측의 에이전트(LLM) Brier 리포트."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT predicted, market_price, outcome FROM predictions WHERE outcome IS NOT NULL"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    if not rows:
        return f"forward 예측 {total}건 기록됨, 해결된 건 0. 마켓이 해결되면 `calibrate --resolve` 후 재실행."
    agent_pairs = [(p, o) for p, _, o in rows]
    market_pairs = [(mp, o) for _, mp, o in rows]
    return (
        format_report("에이전트 LLM", agent_pairs)
        + "\n"
        + format_report("같은 마켓 시장가", market_pairs)
        + f"\n\n(전체 기록 {total}건 중 {len(rows)}건 해결됨. 에이전트 Brier < 시장가 Brier 여야 edge 가 실재.)"
    )
