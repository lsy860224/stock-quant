"""Brier score / 캘리브레이션 순수 함수 테스트 (네트워크 없음)."""

import math

from stock_quant.calibration import brier_score, calibration_table, market_baseline_pairs


def test_brier_perfect():
    assert brier_score([(1.0, 1.0), (0.0, 0.0)]) == 0.0


def test_brier_coinflip_baseline():
    # 항상 0.5 예측, 결과 반반 → Brier = 0.25 (기준선).
    assert brier_score([(0.5, 1.0), (0.5, 0.0)]) == 0.25


def test_brier_worst():
    assert brier_score([(1.0, 0.0), (0.0, 1.0)]) == 1.0


def test_brier_empty_is_nan():
    assert math.isnan(brier_score([]))


def test_calibration_table_groups_and_measures_gap():
    # 0.9 예측 2건 중 1건만 발생 → 그 구간 observed=0.5, gap=0.4.
    pairs = [(0.9, 1.0), (0.9, 0.0), (0.1, 0.0)]
    table = {(round(b.lo, 1)): b for b in calibration_table(pairs)}
    hi = table[0.9]
    assert hi.count == 2
    assert hi.mean_pred == 0.9
    assert hi.observed_freq == 0.5
    assert math.isclose(hi.gap, 0.4)


def test_market_baseline_pairs_reconstructs_and_filters():
    markets = [
        # 정상: 24h 전 가격 = 0.001 - (-0.40) = 0.401, 결과 outcome[0]=0
        {"outcomes": '["A","B"]', "outcomePrices": '["0","1"]',
         "umaResolutionStatus": "resolved", "lastTradePrice": 0.001, "oneDayPriceChange": -0.40},
        # 미해결 → 제외
        {"outcomes": '["A","B"]', "outcomePrices": '["0.4","0.6"]',
         "umaResolutionStatus": "proposed", "lastTradePrice": 0.4, "oneDayPriceChange": 0.0},
        # 비이진 → 제외
        {"outcomes": '["A","B","C"]', "outcomePrices": '["1","0","0"]',
         "umaResolutionStatus": "resolved", "lastTradePrice": 1.0, "oneDayPriceChange": 0.0},
    ]
    pairs = market_baseline_pairs(markets)
    assert len(pairs) == 1
    pred, actual = pairs[0]
    assert actual == 0.0
    assert math.isclose(pred, 0.401, abs_tol=1e-9)
