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
    p_cal.add_argument("--agent", action="store_true", help="에이전트 LLM Brier 백테스트 (ANTHROPIC_API_KEY 필요)")
    p_cal.add_argument("--snapshot", action="store_true", help="현재 마켓에 컨텍스트 포함 예측 기록 (forward)")
    p_cal.add_argument("--resolve", action="store_true", help="기록된 예측의 결과를 Gamma 에서 채움")
    p_cal.add_argument("--report", action="store_true", help="forward 페이퍼 Brier 리포트")
    p_cal.add_argument("--export-seed", action="store_true", help="예측을 커밋용 JSONL 시드로 내보냄")
    p_cal.add_argument("--limit", type=int, default=200, help="시장 베이스라인 표본 수")
    p_cal.add_argument("--sample", type=int, default=120, help="백테스트/스냅샷 LLM 호출 수")
    p_cal.add_argument("--since", default="2026-01-31", help="이 날짜 이후 종료분만 (lookahead 방지)")
    p_cal.add_argument("--horizon-days", type=int, default=14, help="스냅샷: 며칠 내 종료 마켓만")

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
    if args.agent:
        print(calibration.backtest_agent_llm(sample=args.sample, since=args.since))
    if args.snapshot:
        print(calibration.snapshot_predictions(sample=args.sample, horizon_days=args.horizon_days))
    if args.export_seed:
        n = calibration.export_seed()
        print(f"exported {n} predictions → data/predictions_seed.jsonl")
    if args.resolve:
        n = calibration.resolve_predictions()
        print(f"resolved {n} markets.")
    if args.report or not (args.backtest or args.agent or args.snapshot or args.resolve or args.export_seed):
        print(calibration.report())


if __name__ == "__main__":
    main()
