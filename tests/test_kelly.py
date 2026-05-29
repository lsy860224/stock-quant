"""kelly_fraction 정확성 테스트 (보고서 §6.3)."""

import math

from stock_quant.kelly import kelly_fraction


def test_edge_case_prices_return_zero():
    assert kelly_fraction(0.9, 0.0) == 0.0
    assert kelly_fraction(0.9, 1.0) == 0.0


def test_no_edge_when_p_equals_price():
    # p == market_price 면 켈리 = 0 (베팅 가치 없음).
    assert math.isclose(kelly_fraction(0.5, 0.5, max_fraction=1.0), 0.0, abs_tol=1e-9)


def test_negative_kelly_clamped_to_zero():
    # 추정 확률 < 시장가 → 음수 켈리 → 0 으로 클램프 (방향은 호출부가 처리).
    assert kelly_fraction(0.3, 0.6) == 0.0


def test_capped_at_max_fraction():
    # 강한 엣지라도 상한 6% 를 넘지 않는다 (§7.1).
    assert kelly_fraction(0.95, 0.5, max_fraction=0.06) == 0.06


def test_known_value():
    # p=0.6, price=0.5 → b=1, f=(0.6*1-0.4)/1=0.2, 상한 1.0 하에서 0.2.
    assert math.isclose(kelly_fraction(0.6, 0.5, max_fraction=1.0), 0.2, abs_tol=1e-9)
