# 지지선 매수 스캐너 (미국 주식 · 텔레그램 알림)

케빈 쉬 방식 — "급등주 추격 대신 지지선 근처에서 매수, 약 +20%에 매도" — 를
매일 자동으로 걸러 알려주는 도구. **자동 매매는 하지 않는다.**

## 구성
| 파일 | 역할 |
|---|---|
| `support.py` | 지지선 탐지 + 매수 조건 판정 (공용 로직) |
| `scanner.py` | 매일 실행 → 후보 종목 텔레그램 전송 + `signals.csv` 누적 |
| `backtest.py` | 같은 규칙을 과거 데이터로 검증 → 승률·기대값 출력 |
| `config.json` | 모든 파라미터 |
| `tickers.txt` | 스캔 대상 종목 (자유 편집) |

## 매수 조건 (전부 만족해야 알림)
1. **지지선 근접**: 종가가 지지선 위 2% 이내 (또는 아래 1% 이내)
   - 지지선 = 최근 180일 피봇 저점 중 **2회 이상 터치된 가격대** + MA50 + MA200
2. **추세**: 종가가 MA200 위 (하락추세 종목 제외)
3. **매수세 확인**: 당일 거래량 ≥ 20일 평균 × 1.2
4. **반등 확인**: 당일 봉이 저가보다 위쪽(캔들 상단 50% 이상)에서 마감 — 떨어지는 칼날 제외

알림에는 지지선 가격, 터치 횟수, 손절가(지지선 −4%), 목표가(+20%)가 같이 나온다.

## 설치
```bash
pip install yfinance pandas numpy requests
```

## 텔레그램 연결 (5분)
1. 텔레그램에서 `@BotFather` → `/newbot` → 토큰 복사
2. 만든 봇에게 아무 메시지 전송
3. 브라우저에서 `https://api.telegram.org/bot<토큰>/getUpdates` → `"chat":{"id":숫자}` 복사
4. 환경변수 설정
```bash
export TELEGRAM_BOT_TOKEN=123456:ABC...
export TELEGRAM_CHAT_ID=987654321
```

## 실행
```bash
python scanner.py --dry          # 텔레그램 없이 콘솔 확인
python scanner.py                # 실제 전송
python scanner.py AAPL NVDA      # 특정 종목만
```

## 매일 자동 실행 (미국장 마감 후 = 한국시간 06:10, 서머타임엔 05:10)
```bash
crontab -e
10 6 * * 2-6 cd /path/to/support_scanner && /usr/bin/python3 scanner.py >> scan.log 2>&1
```
PC가 꺼져 있으면 안 돌아가므로 맥 상시 켜두기, 또는 GitHub Actions 무료 cron 추천.

## 폰에서 앱처럼 보기 (GitHub Actions + Pages, 무료, PC 불필요)
1. GitHub에 새 저장소 만들고 이 폴더 전체를 push (`.github/` 포함)
2. 저장소 **Settings → Pages → Source: Deploy from a branch → `main` / `/docs`** 저장
3. (선택) **Settings → Secrets → Actions**에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 등록 → 텔레그램 푸시도 같이 옴
4. **Actions 탭 → daily-support-scan → Run workflow** 한 번 수동 실행 → `docs/signals.json` 생성됨
5. 폰 Safari에서 `https://<아이디>.github.io/<저장소명>/` 열고 **공유 → 홈 화면에 추가**

이후엔 매일 한국시간 06:10(서머타임 중엔 05:10)에 자동 실행되고, 앱을 열면 최근 30일 이력이 보인다.
- 날짜 칩을 누르면 그날 후보로 전환
- 카드의 바는 `손절 ─ 지지선 | 현재가 ─ 목표` 위치
- iOS 홈 화면 앱은 푸시 알림이 까다로워서, "울리는 알림"은 텔레그램 봇이 담당하고 이 페이지는 "열어서 보는 대시보드"로 쓰는 게 깔끔하다

## 백테스트 — 알림 켜기 전에 반드시
```bash
python backtest.py                    # tickers.txt, 최근 3년
python backtest.py --period 5y        # 5년
python backtest.py RKT APT PLTR       # 특정 종목
```
출력 중 **`기대값/거래`가 양수**여야 전략이 성립한다. 음수면 `config.json`을 바꿔가며
(터치 횟수 ↑, tolerance ↓, 거래량 배수 ↑ 등) 다시 돌려볼 것.
거래 내역은 `backtest_trades.csv`에 저장된다.

## 파라미터 (config.json)
| 키 | 기본 | 의미 |
|---|---|---|
| `pivot_window` | 5 | 좌우 5일 내 최저가면 피봇 저점 |
| `lookback_days` | 180 | 지지선 탐색 기간 |
| `cluster_pct` | 0.015 | 1.5% 이내 저점은 같은 지지선으로 묶음 |
| `min_touches` | 2 | 최소 터치 횟수 |
| `tolerance_pct` | 0.02 | 지지선과 현재가 허용 거리 |
| `vol_mult` | 1.2 | 거래량 / 20일 평균 최소 배수 |
| `min_close_pos` | 0.5 | 캔들 내 종가 위치 (0=저가 마감, 1=고가 마감) |
| `require_above_ma200` | true | MA200 위 종목만 |
| `stop_pct` | 0.04 | 손절 = 지지선 × (1−0.04) |
| `target_pct` | 0.20 | 목표 = 진입가 × 1.20 |
| `max_hold_days` | 40 | 최대 보유일 (백테스트) |

## 솔직한 한계
- 지지선은 **사후적으로 그리기 쉽고 사전엔 자주 깨진다.** 합성(랜덤) 데이터로
  돌리면 기대값이 음수로 나오는 게 정상 — 실제 종목에서도 그러면 쓰지 말 것.
- 케빈 쉬 수익의 핵심은 지지선 로직이 아니라 **2020~21년 유동성 장세 + 전액 몰빵 반복**.
  같은 방식으로 날아간 계좌는 기록을 안 남긴다.
- 이 툴은 "매일 수백 개 차트를 볼 시간을 아껴주는 필터"다. 매수 판단은 직접.
