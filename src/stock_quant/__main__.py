"""CLI 진입점: `stock-quant` 또는 `python -m stock_quant`.

  stock-quant            # 10분 루프 상시 실행
  stock-quant --once     # 루프 1회만 (검증용)
"""

from __future__ import annotations

import argparse
import logging

from .agent import main_loop, run_once
from .config import settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="stock-quant")
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="에이전트 실행 (기본)")
    p_run.add_argument("--once", action="store_true", help="루프 1회만 실행 후 종료")
    p_run.add_argument("--limit", type=int, default=500, help="스캔할 마켓 수")

    p_cal = sub.add_parser("calibrate", help="Brier score 캘리브레이션")
    p_cal.add_argument("--backtest", action="store_true", help="resolved 마켓 시장 베이스라인 (키 불필요)")
    p_cal.add_argument("--resolve", action="store_true", help="기록된 예측의 결과를 Gamma 에서 채움")
    p_cal.add_argument("--report", action="store_true", help="forward 페이퍼 Brier 리포트")
    p_cal.add_argument("--limit", type=int, default=200, help="백테스트 표본 수")

    # 하위호환: 인자 없거나 --once/--limit 만 주면 run 으로 취급
    args, _ = parser.parse_known_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if args.cmd == "calibrate":
        _run_calibrate(args)
        return

    if not settings.dry_run:
        logging.getLogger("stock_quant").warning(
            "*** DRY_RUN=false — 라이브 주문 모드. 실자금이 이동할 수 있습니다. ***"
        )
    once = getattr(args, "once", False)
    limit = getattr(args, "limit", 500)
    if once:
        run_once(scan_limit=limit)
    else:
        main_loop()


def _run_calibrate(args: argparse.Namespace) -> None:
    from . import calibration

    if args.backtest:
        print(calibration.backtest_market_baseline(limit=args.limit))
    if args.resolve:
        n = calibration.resolve_predictions()
        print(f"resolved {n} markets.")
    if args.report or not (args.backtest or args.resolve):
        print(calibration.report())


if __name__ == "__main__":
    main()
