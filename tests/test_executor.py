"""executor 의 순수 헬퍼 + dry-run 게이트 테스트 (네트워크/키 없음)."""

import pytest

from stock_quant.detector import Opportunity
from stock_quant.executor import (
    _round_price_to_tick,
    _shares_for_budget,
    _token_id_for_side,
    place_order,
)

MARKET = {"clobTokenIds": '["YES_TOKEN_ID", "NO_TOKEN_ID"]', "orderMinSize": 5}


def test_token_id_selects_yes_or_no():
    assert _token_id_for_side(MARKET, "YES") == "YES_TOKEN_ID"
    assert _token_id_for_side(MARKET, "NO") == "NO_TOKEN_ID"


def test_token_id_raises_without_ids():
    with pytest.raises(ValueError):
        _token_id_for_side({"clobTokenIds": "[]"}, "YES")


def test_round_price_to_tick():
    assert _round_price_to_tick(0.094, 0.01) == 0.09
    assert _round_price_to_tick(0.096, 0.01) == 0.10
    assert _round_price_to_tick(0.5237, 0.001) == 0.524


def test_shares_never_exceed_budget():
    # budget=$3 at price 0.09 → 33.33 shares, 내림 → 33.33; cost ≤ 3.
    shares = _shares_for_budget(3.0, 0.09)
    assert shares * 0.09 <= 3.0 + 1e-9
    assert shares == pytest.approx(33.33, abs=0.01)


def test_shares_zero_on_bad_price():
    assert _shares_for_budget(3.0, 0.0) == 0.0


def test_place_order_dry_run_does_not_touch_network(monkeypatch):
    # DRY_RUN 기본(true)에서는 라이브 경로를 절대 타지 않는다.
    monkeypatch.delenv("DRY_RUN", raising=False)
    opp = Opportunity(MARKET, "Q?", 0.10, 0.30, 0.20, "YES", 0.06)
    result = place_order(opp, 3.0)
    assert result["status"] == "dry_run"
