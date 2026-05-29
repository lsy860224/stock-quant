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
    parser.add_argument("--once", action="store_true", help="루프 1회만 실행 후 종료")
    parser.add_argument("--limit", type=int, default=500, help="스캔할 마켓 수")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if not settings.dry_run:
        logging.getLogger("stock_quant").warning(
            "*** DRY_RUN=false — 라이브 주문 모드. 실자금이 이동할 수 있습니다. ***"
        )

    if args.once:
        run_once(scan_limit=args.limit)
    else:
        main_loop()


if __name__ == "__main__":
    main()
