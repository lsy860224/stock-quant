"""환경설정 + 불변 가드레일 (CLAUDE.md §5 / 보고서 §7.1).

가드레일 기본값은 함부로 약화시키지 말 것. .env 로 override 가능하되,
override 도 안전 범위 안에서만 의미가 있다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _f(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _i(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    # --- 가드레일 (§7.1) ---
    edge_threshold: float = _f("EDGE_THRESHOLD", 0.08)      # 최소 괴리 8%
    max_fraction: float = _f("MAX_FRACTION", 0.06)          # Kelly 상한 6%
    max_daily_loss_pct: float = _f("MAX_DAILY_LOSS_PCT", 0.20)
    max_positions: int = _i("MAX_POSITIONS", 10)
    min_liquidity: float = _f("MIN_LIQUIDITY", 1000.0)
    loop_minutes: int = _i("LOOP_MINUTES", 10)

    # --- 엔드포인트 (§6.1) ---
    gamma_api: str = "https://gamma-api.polymarket.com"
    clob_host: str = "https://clob.polymarket.com"

    # --- LLM ---
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")

    @property
    def dry_run(self) -> bool:
        """라이브 주문은 DRY_RUN=false 일 때만. 그 외 모든 값/미설정은 안전 측(dry-run)."""
        return os.getenv("DRY_RUN", "true").strip().lower() != "false"

    def __post_init__(self) -> None:
        # 가드레일이 안전 범위를 벗어나면 즉시 중단 (조용한 약화 방지).
        if not (0 < self.max_fraction <= 0.06):
            raise ValueError(f"max_fraction must be in (0, 0.06]; got {self.max_fraction}")
        if self.edge_threshold < 0.08:
            raise ValueError(f"edge_threshold must be >= 0.08; got {self.edge_threshold}")


settings = Settings()
