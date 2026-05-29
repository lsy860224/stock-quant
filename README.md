# stock-quant

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
`uv sync --extra live`(py-clob-client) + 지갑 키가 모두 갖춰졌을 때만 동작하며, 실행 경로는
의도적으로 미구현이다. 켜기 전 소액($20~50) 검증 필수.

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
