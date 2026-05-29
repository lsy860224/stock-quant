# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **상태: GREENFIELD (코드 없음).** 이 문서는 기존 코드 문서화가 아니라 **신규 프로젝트 헌장 + 아키텍처 블루프린트**다.
> 근거 문서: Obsidian `03. Stock-Compass/Polymarket 자율 트레이딩 에이전트 — 종합 분석 보고서.md` (이하 "보고서"). 섹션 참조(§n)는 모두 그 보고서를 가리킨다.
> 코드가 생기면 이 문서의 "계획" 표현을 실제 동작·명령으로 교체할 것.

## 0. 이 프로젝트가 무엇이고, 무엇이 아닌가

**stock-quant** = 예측시장(Polymarket)에서 **LLM이 공정가치를 추정 → 시장가와 괴리 시 켈리 기준으로 베팅액 산출 → 자동 주문**하는 **자율 트레이딩 에이전트**. 10분 루프로 반복하며 수익에서 자기 API 비용을 차감하고 잔고 0이 되면 종료한다(§1, §2).

### 옆 프로젝트 `~/dev/stock-compass`와 절대 혼동 금지

| | stock-quant (이 repo) | stock-compass (별도 repo) |
|---|---|---|
| 정체성 | 자율 매매 에이전트 (주문 실행 O) | 개인 매매 의사결정 **보조** 도구 |
| 매매 | **자동 주문(CLOB/mint) 실행** | **BUY/SELL 금지, 사용자가 결정, 자동매매 없음** |
| 도메인 | 예측시장 YES/NO 베팅 | KR·US 주식 다요인 점수화 (예측기 아님) |
| 데이터 | USDC/온체인, Polymarket Gamma/CLOB | yfinance·pykrx·DART, 로컬 SQLite |

보고서 §8 결론: **Polymarket 자율매매 아키텍처를 stock-compass에 통째 채택 = 불가** (stock-compass의 "예측기 아님·BUY/SELL 금지·자동매매 없음" 원칙과 정면 충돌). 두 프로젝트는 **이름·디렉터리·원칙이 의도적으로 분리**되어 있다. stock-quant 작업 중 stock-compass 코드를 끌어오거나, 반대로 이 자율매매 로직을 stock-compass에 이식하지 말 것.

## 1. 검증 노트 (먼저 읽기)

- 원사례 `$50→$2,980 (48시간)`은 **단일 트윗 일화 · 표본 1 · 생존자 편향 · 재현 불가**. "기대 수익"이 아니라 "이런 아키텍처가 존재한다"는 사례로만 취급(§meta, §검증).
- LLM 모델: 보고서 코드의 `claude-opus-4-6`/`gpt-4o-mini`는 예시. **현재 환경 기본은 최신 Claude Opus(4.8) 또는 비용 최적화 시 Haiku**. 모델 ID 하드코딩 시 최신값으로.
- **Polymarket은 미국 등에서 접근 제한**. 한국 거주자 이용·세무·외환은 별도 확인 필요(§11). 법적: 교육·정보 목적 한정, 원금 손실 위험. 점수·코드의 외부 제공/판매 시 유사투자자문업 위반 가능 — **본인 사용 한정**.

## 2. 기술 스택 — 기본 경로 = Python (경로 A)

보고서는 Python(§4.1)·TypeScript/Sapience(§4.2) 두 경로를 제시한다. **이 repo의 기본은 경로 A(Python)** — 가장 빠른 시작, 공식 SDK.

- 런타임: Python 3.9+
- 공식 프레임워크: `github.com/Polymarket/agents` (clone 후 의존성 설치)
- 거래 SDK: `py-clob-client` (`github.com/Polymarket/py-clob-client`)
- AI SDK: `anthropic` (Claude, 권장) · 선택적으로 `openai`
- HTTP: `requests`
- 스케줄러: `schedule` 라이브러리 + `systemd`(Linux) / `launchd`(macOS)
- 인프라: VPS 24/7 (Hetzner CX11 $4.5~6/월 등)

> 경로 B(TS/Sapience, 온체인 직접 mint)는 보고서 §4.2·§6.7에 명세. 온체인 직접 거래가 요구사항이 될 때만 채택. 그 전까지 경로 A로 진행.

## 3. 부트스트랩 명령 (코드 생성 시 계획)

아직 코드가 없다. 신규 셋업 시 보고서 §4.1·§5.3 기준:

```bash
# 1) 공식 프레임워크 클론 + 가상환경
git clone https://github.com/Polymarket/agents
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install py-clob-client anthropic requests schedule

# 2) .env 작성 (§5.3, 절대 커밋 금지)
#   POLYGON_WALLET_PRIVATE_KEY="0x..."   # 에이전트 전용 지갑 개인키
#   ANTHROPIC_API_KEY="sk-ant-..."        # Claude (권장)
#   OPENAI_API_KEY="sk-..."               # 선택

# 3) 로컬 실행 (10분 루프)
python main.py

# 4) 상시 실행 (Linux systemd 유닛은 §6.5 참조, macOS는 launchd)
```

> **키 보안(§5.3 danger):** 개인키를 코드/Git에 절대 노출 금지. 항상 `.env` + `.gitignore`. **에이전트 전용 지갑을 메인 지갑과 분리**(리스크 격리). repo 초기화 시 `.gitignore`에 `.env*` 최우선 추가.

## 4. 아키텍처 — 10분 루프 & 컴포넌트

핵심 사이클(§2) — 단방향 파이프라인, 매 10분 반복:

```
스캔 → 공정가치 추정 → 미스프라이싱 탐지 → 포지션 사이징 → 주문 실행 → 비용 차감/잔고 감시
(Gamma API) (Claude)     (|edge|≥0.08)      (Kelly ≤6%)    (CLOB)      (잔고 0 → 종료)
```

| 컴포넌트 | 역할 | 구현 수단 |
|---|---|---|
| Market Scanner | 활성 마켓 500~1,000개 주기 수집 | Polymarket Gamma API `/markets` |
| Claude Reasoner | 질문 → 공정가치(YES 확률 0~1) | Anthropic (또는 OpenRouter) |
| Mispricing Detector | `edge = fair_value − market_price`, `|edge| ≥ 0.08`만 통과 | 자체 로직 |
| Kelly Calculator | 베팅 비율 `f = (p·b − (1−p))/b`, 상한 6% | 자체 로직 |
| Order Executor | CLOB 주문 제출·체결 (edge>0 → YES, <0 → NO) | py-clob-client |
| Cost Manager | 수익에서 API 비용 차감, 잔고 감시, **잔고 0 → 종료** | 자체 로직 |
| Data Fetchers | 카테고리별 외부 데이터 (구현됨, best-effort) | NOAA(날씨)·ESPN(스포츠)·CoinGecko(크립토)·NewsAPI(fallback) |

**설계 의도(§2 note):** "살아남으려면 수익을 내야 한다"는 생존 압력 = 사망 메커니즘 = 사실상 킬 스위치. 강화학습 유사 자기선택.

**컨텍스트 라우팅(§6.6, `context.py` 구현됨):** `market.category`로 분기 — weather→NOAA(미국 한정, Nominatim 지오코딩 + 행정구역 검증으로 동명 POI 오매칭 차단), sports→ESPN 검색, crypto→CoinGecko 시세(진짜 온체인 Dune/Nansen 은 키 필요 — 미구현 확장 지점), else→NewsAPI(`NEWS_API_KEY` 있을 때만). 키 없는 NOAA/ESPN/CoinGecko 는 즉시 동작. 모든 fetcher 는 **best-effort** — 실패/미해결 시 빈 문자열 반환, 절대 루프로 예외를 던지지 않는다(reasoner 가 기저율로 폴백). 추정 프롬프트 골격 = ① 역사적 기저율(base rate) → ② 현재 증거 → ③ 시장가와의 차이 → "숫자만(0~100)".

**핵심 엔드포인트:** Gamma `https://gamma-api.polymarket.com` · CLOB `https://clob.polymarket.com`. 코드 스니펫은 보고서 §6.1~6.6에 그대로 있음 — 구현 시 출발점으로 사용.

> ⚠️ **Gamma 스키마 검증 결과 (2026-05-29, 라이브 API 확인):** 보고서 §6.1/§6.4 의 `market['outcomePrices']` 필드는 **현재 Gamma API 에 존재하지 않는다.** 실제 스키마:
> - YES 가격: `bestBid`/`bestAsk` 중간값 (둘 다 0~1), fallback `lastTradePrice`. → `detector._yes_price`
> - 유동성: `liquidityNum` (숫자). `liquidity` 는 문자열.
> - 이진 마켓 판별: `outcomes`(JSON 문자열) == `["Yes","No"]`. Up/Down 등 비이진 마켓 다수 존재 → 스킵. → `detector._is_yes_no`
> - 주문 토큰: `clobTokenIds`(JSON 문자열, [YES, NO]) + `conditionId`. 라이브 주문 구현 시 사용.
> 보고서 코드를 복붙하지 말고 위 실제 필드명을 쓸 것.

> **라이브 주문 (`executor._place_live_order`, py-clob-client 0.34, 구현됨):** DRY_RUN=false + `--extra live` + 지갑키 3중 게이트. 라이브 API 검증 결과:
> - 주문 side 는 **항상 BUY** — 방향은 token id 로 결정. YES→`clobTokenIds[0]`, NO→`[1]`.
> - `client.get_price(token_id, BUY)` → **`{"price": "0.09"}` (dict, 문자열)** — float 아님. `["price"]` 파싱 필수.
> - `client.get_tick_size(token_id)` → 문자열(`"0.01"` 등). 가격은 tick 그리드로 반올림해야 `create_order` 의 `price_valid` 통과.
> - `create_order(OrderArgs)` 는 tick_size·neg_risk·fee 를 내부에서 자동 resolve (options 불필요). L1 인증 필요.
> - size = outcome 토큰 수, cost = price×size. 예산 초과 방지로 0.01 내림. `orderMinSize` 미만이면 스킵.
> - chain_id = `POLYGON`(137). 사전조건: USDC 보유 + CLOB Exchange approve(1회, 코드 범위 밖). 킬스위치 `cancel_all()`.

## 5. 리스크 관리 (불변 가드레일 — §7.1)

매매 로직을 건드릴 때 **반드시 유지**할 안전장치:

- 최대 단일 포지션: 뱅크롤 **6%** (Kelly 상한). 임의 상향 금지.
- 최소 edge: **8% 이상**만 거래.
- **잔고 0 → 자동 종료** (사망 = 킬 스위치). 이 종료 조건을 우회/제거하지 말 것.
- 전용 지갑 (메인과 분리).
- 추가 권장 한도: `MAX_DAILY_LOSS = bankroll*0.20`, `MAX_POSITIONS = 10`, `MIN_LIQUIDITY = 1000`.
- CLOB 모범사례: 오래된 호가 취소, GTD 만료, 배치 주문(`postOrders`), WebSocket 구독, **오류 시 `cancelAll()` 킬스위치**.
- **소액($20~50) 검증 후 증액.** 첫 라이브 실행은 항상 소액.

**비용 구조(§7.2):** Claude API ~$0.003/call (절감 시 Haiku 다운시프트) · VPS $4.5~6/월 · Polymarket 수수료 Maker/Taker **0%** · 브릿지 가스 <$0.01.

**모니터링(§7.3):** 수익/손실 실시간 로깅, API 비용 추적(수익 대비 %), 카테고리별 성과, **Brier Score로 예측 캘리브레이션 측정**(`calibration.py`).

> **Brier 캘리브레이션 (`calibration.py`, 구현됨):** `stock-quant calibrate`. 두 모드:
> - `--backtest`: resolved 마켓의 **시장가 베이스라인** Brier (키 불필요, offset 페이지네이션). 2026-05-29 측정 = **0.2198** (n=489) — 시장 ~24h 전 가격은 0.25 동전던지기를 근소하게만 상회. 에이전트 LLM 이 넘어서야 할 기준.
> - forward 페이퍼: dry-run 루프가 `record_prediction` 으로 예측을 `data/calibration.db`(SQLite, gitignore)에 누적 → `--resolve`(CLOB `/markets/{conditionId}` 의 `tokens[].winner` 로 결과 판정) → `--report`(에이전트 vs 시장가 Brier 비교).
> - **에이전트 Brier < 시장가 Brier** 여야 edge 가 실재. resolved 마켓엔 active 엔 없는 `outcomePrices`(`["0","1"]`)·`umaResolutionStatus="resolved"` 가 존재.
> - `--agent`: 에이전트 LLM 백테스트 (cutoff 이후 종료분 + 컨텍스트 비활성으로 lookahead 최소화).

> ⚠️ **측정된 결과 (2026-05-29): 현재 에이전트는 edge 가 없다.** `--agent` 백테스트(n=130) = **Brier 0.2350** vs 같은 마켓 시장가 **0.1637**. LLM 이 시장보다 나쁘고 극단에서 과신(예: ~4% 예측이 실제 20% 발생). **라이브 자금 거래 금지** — edge 를 입증(에이전트 Brier < 시장가)하기 전까지 dry-run/연구 전용. 개선 방향: 컨텍스트 활성 효과 측정, 확률 보정(calibration) 레이어, 카테고리 선별.

## 6. 작업 원칙

- **보고서가 단일 진실 소스(SSOT).** 스택·API·코드·리스크 결정은 먼저 보고서 §해당절을 확인하고 근거를 댄다. 원본 PDF 2종은 `~/dev/stock-compass/apnedix/`.
- 매매 가드레일(§5)은 "동작하게만" 하려고 약화시키지 않는다 — 글로벌 룰 "No Laziness / root cause" 적용.
- 라이브 자금 주문은 **되돌릴 수 없는 외부 행위**다. 실주문 경로를 활성화/실행하기 전 반드시 사용자 확인. 기본은 dry-run/페이퍼 모드로 검증.
- 변경은 task가 요구하는 곳만(Minimal Impact). stock-compass를 절대 건드리지 않는다.
