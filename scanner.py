"""매일 장 마감 후 실행: 지지선 근접 매수 후보를 찾아 텔레그램으로 보낸다.

사용법
  python scanner.py                 # tickers.txt 전체 스캔
  python scanner.py AAPL NVDA       # 지정 종목만
  python scanner.py --dry           # 텔레그램 전송 없이 콘솔 출력만

환경변수 (텔레그램)
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import json, os, sys
from datetime import datetime
import pandas as pd
import yfinance as yf
import requests
from support import check_signal

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))


def load_tickers(args):
    tk = [a for a in args if not a.startswith("--")]
    if tk:
        return tk
    path = os.path.join(HERE, CFG["tickers_file"])
    return [l.strip().upper() for l in open(path)
            if l.strip() and not l.startswith("#")]


def fetch(tickers):
    """yfinance 일괄 다운로드 → {ticker: DataFrame}"""
    raw = yf.download(tickers, period=CFG["history_period"], group_by="ticker",
                      auto_adjust=True, progress=False, threads=True)
    out = {}
    for t in tickers:
        try:
            df = raw[t] if len(tickers) > 1 else raw
            df = df.dropna()
            if len(df) >= 60:
                out[t] = df
        except KeyError:
            pass
    return out


def scan(data):
    rows = []
    for t, df in data.items():
        sig = check_signal(df, len(df) - 1, CFG)
        if sig:
            sig["ticker"] = t
            sig["date"] = df.index[-1].strftime("%Y-%m-%d")
            rows.append(sig)
    # 터치 많고, 지지선에 가까운 순
    rows.sort(key=lambda r: (-r["touches"], abs(r["dist_pct"])))
    return rows


def format_msg(rows):
    today = datetime.now().strftime("%Y-%m-%d")
    if not rows:
        return f"📭 {today} 지지선 근접 종목 없음"
    lines = [f"📍 {today} 지지선 매수 후보 {len(rows)}개", ""]
    for r in rows:
        lines.append(
            f"*{r['ticker']}*  ${r['close']:.2f}\n"
            f"  지지 ${r['support']:.2f} ({r['kind']}, 터치 {r['touches']}회, 거리 {r['dist_pct']:+.1f}%)\n"
            f"  거래량 {r['vol_ratio']:.1f}x · 손절 ${r['stop']:.2f} · 목표 ${r['target']:.2f}"
        )
    lines.append("")
    lines.append("_알림일 뿐 매수 지시가 아님. 차트·뉴스 직접 확인 후 판단._")
    return "\n".join(lines)


def send_telegram(text):
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[telegram] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 없음 → 전송 생략")
        return
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
                      timeout=15)
    print("[telegram]", r.status_code, r.text[:120])


def main():
    args = sys.argv[1:]
    tickers = load_tickers(args)
    print(f"스캔 대상 {len(tickers)}개 ...")
    data = fetch(tickers)
    rows = scan(data)
    msg = format_msg(rows)
    print(msg)
    if rows:
        out = os.path.join(HERE, "signals.csv")
        pd.DataFrame(rows).to_csv(out, mode="a", index=False,
                                  header=not os.path.exists(out))
    write_json(rows, len(tickers))
    if "--dry" not in args:
        send_telegram(msg)


def write_json(rows, n_scanned):
    """docs/signals.json — 웹앱이 읽는 파일. 최근 30일 이력 유지."""
    path = os.path.join(HERE, "docs", "signals.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    hist = []
    if os.path.exists(path):
        try:
            hist = json.load(open(path)).get("history", [])
        except Exception:
            hist = []
    today = datetime.now().strftime("%Y-%m-%d")
    entry = {"date": today, "scanned": n_scanned,
             "signals": [{k: (round(v, 3) if isinstance(v, float) else v)
                          for k, v in r.items()} for r in rows]}
    hist = [h for h in hist if h["date"] != today] + [entry]
    hist = sorted(hist, key=lambda h: h["date"])[-30:]
    json.dump({"updated": datetime.now().isoformat(timespec="minutes"),
               "config": {k: CFG[k] for k in ("tolerance_pct", "stop_pct", "target_pct", "min_touches")},
               "history": hist}, open(path, "w"), ensure_ascii=False, indent=1)
    print(f"[json] {path} 갱신 ({len(hist)}일 이력)")


if __name__ == "__main__":
    main()
