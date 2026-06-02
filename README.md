# stock-quant

> 🏁 **상태 (2026-06-02): 연구 종결 — edge 없음, 라이브 거래 보류.**
> 백테스트·forward·보정 4축 검증 모두 에이전트가 시장을 못 이김 (forward Brier 0.153 vs 시장 0.047).
> 패배 원인은 과신이 아니라 **판별력 부족**(LLM 확률 추정 자체가 시장보다 부정확) — 보정으로도 해결 안 됨.
> 결론·수치 상세는 [`CLAUDE.md`](./CLAUDE.md). 코드·방법론은 보존(다른 신호원으로 재도전 시 토대). **dry-run/연구 전용.**

Polymarket 자율 트레이딩 에이전트. LLM이 각 예측시장의 공정가치를 추정하고, 시장가와 8% 이상 괴리할 때 켈리 기준으로 베팅액을 산출해 자동 주문한다. 10분 루프로 반복한다.

> 설계 근거: Obsidian `03. Stock-Compass/Polymarket 자율 트레이딩 에이전트 — 종합 분석 보고서.md`.
> 상세 아키텍처·가드레일·경계는 [`CLAUDE.md`](./CLAUDE.md) 참조.

> ⚠️ 교육·정보 목적 한정. 원금 손실 위험. Polymarket은 국가별 접근 제한이 있으니 거주지 규제·세무를 먼저 확인할 것. 옆 프로젝트 `stock-compass`(자동매매 금지 보조 도구)와 혼동 금지.

## 셋업

```bash
uv sync --extra dev          # 페이퍼/dry-run 개발 (기본)
cp .env.example .env         # ANTHROPIC_API_KEY 등 채우기
```

## 실행

```bash
uv run stock-quant --once    # 루프 1회 (dry-run 검증)
uv run stock-quant           # 10분 루프 상시 실행
```

기본은 **dry-run(페이퍼)** — 실제 주문 없음. 라이브 주문은 `.env` 의 `DRY_RUN=false` +
`uv sync --extra live`(py-clob-client) + `POLYGON_WALLET_PRIVATE_KEY` 가 모두 갖춰졌을 때만
동작한다(`executor._place_live_order`). 셋 중 하나라도 없으면 명확히 거부.

**라이브 사전조건:** 에이전트 전용 지갑에 USDC(Polygon) 보유 + CLOB Exchange 에 USDC
approve 1회 설정. 지갑 유형에 따라 `CLOB_SIGNATURE_TYPE`/`CLOB_FUNDER_ADDRESS` 필요(.env 참조).
**첫 라이브는 반드시 소액($20~50) 검증.** 오류 시 `cancel_all()` 킬스위치 자동 발동.

## Brier 캘리브레이션 (보고서 §7.3)

```bash
# 1) 시장 베이스라인 — 지금 바로 (LLM 키 불필요). 에이전트가 넘어서야 할 기준.
uv run stock-quant calibrate --backtest --limit 1000

# 2) 에이전트 LLM 백테스트 — resolved 마켓 (ANTHROPIC_API_KEY 필요)
uv run stock-quant calibrate --agent --sample 130

# 3) forward 페이퍼 (컨텍스트 포함, 무편향) — 현재 마켓에 예측 기록 → 해결 후 채점
uv run stock-quant calibrate --snapshot --horizon-days 14   # 14일 내 종료 Yes/No 마켓 예측 기록
uv run stock-quant calibrate --resolve                       # 해결된 마켓 결과 반영
uv run stock-quant calibrate --report                        # 에이전트 LLM vs 시장가 Brier
# (dry-run 루프 `run --once` 도 거래 후보 예측을 자동 기록)
```

forward 는 컨텍스트 포함 예측의 **무편향**(lookahead 없음) 측정이지만, 마켓이 해결돼야
Brier 가 나온다(스냅샷 후 며칠~). 백테스트(컨텍스트 비활성)와 비교해 컨텍스트 효과를 본다.

> ⚠️ **측정 결과 (2026-05-29): 에이전트 Brier 0.235 > 시장가 0.164 — edge 없음.**
> 현재 LLM 은 시장을 이기지 못하므로 라이브 거래 금지. dry-run/연구 전용.

Brier score = `mean((예측−결과)²)`. 0.25 = 동전던지기 기준선, 낮을수록 좋음.
**에이전트 Brier < 시장가 Brier 여야 edge 가 실재**한다. 예측은 `data/calibration.db`(gitignore)에 누적.

## 개발

```bash
uv run pytest                # 테스트 (kelly 정확성 등)
uv run ruff check src tests  # 린트
uv run mypy src              # 타입 체크
```

## 구조

| 모듈 | 역할 |
|---|---|
| `scanner.py` | Gamma API 활성 마켓 수집 |
| `reasoner.py` | Claude 공정가치(YES 확률) 추정 |
| `context.py` | 카테고리별 컨텍스트 라우팅 |
| `detector.py` | 미스프라이싱 탐지 + Kelly 사이징 |
| `kelly.py` | Kelly Criterion (순수 함수) |
| `executor.py` | 주문 실행 (dry-run 기본 / 라이브 게이트) |
| `cost_manager.py` | 잔고 감시 + API 비용 추적 (잔고 0 → 종료) |
| `agent.py` | 10분 루프 오케스트레이션 |
