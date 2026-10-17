"""지지선 매수 규칙 백테스트

규칙
  진입: check_signal() 이 True인 날 → 다음 날 시가 매수
  청산: 목표가(+target_pct) 도달 / 손절가(지지선 - stop_pct) 이탈 / max_hold_days 경과 중 먼저 오는 것
        같은 날 둘 다 걸리면 손절로 처리 (보수적)
  종목당 동시 1포지션. 포지션 사이징 없음 → 거래별 수익률만 본다.

사용법
  python backtest.py                # tickers.txt, 기본 3년
  python backtest.py --period 5y AAPL NVDA
"""
import json, os, sys
import numpy as np
import pandas as pd
import yfinance as yf
from support import check_signal

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))


def run_one(ticker, df):
    trades = []
    i, n = 60, len(df)
    o, h, l, c = (df[k].values for k in ("Open", "High", "Low", "Close"))
    while i < n - 2:
        sig = check_signal(df, i, CFG)
        if not sig:
            i += 1
            continue
        entry_i = i + 1
        entry = o[entry_i]
        target = entry * (1 + CFG["target_pct"])
        stop = sig["support"] * (1 - CFG["stop_pct"])
        exit_i, exit_px, reason = None, None, None
        for j in range(entry_i, min(entry_i + CFG["max_hold_days"], n)):
            if l[j] <= stop:
                exit_i, exit_px, reason = j, stop, "stop"
                break
            if h[j] >= target:
                exit_i, exit_px, reason = j, target, "target"
                break
        if exit_i is None:
            exit_i = min(entry_i + CFG["max_hold_days"], n) - 1
            exit_px, reason = c[exit_i], "time"
        trades.append({
            "ticker": ticker,
            "signal_date": df.index[i].strftime("%Y-%m-%d"),
            "entry": entry, "exit": exit_px,
            "ret_pct": (exit_px / entry - 1) * 100,
            "days": exit_i - entry_i, "reason": reason,
            "kind": sig["kind"], "touches": sig["touches"],
        })
        i = exit_i + 1
    return trades


def summarize(tr: pd.DataFrame):
    if tr.empty:
        print("거래 없음")
        return
    win = tr[tr.ret_pct > 0]
    loss = tr[tr.ret_pct <= 0]
    wr = len(win) / len(tr)
    avg_w = win.ret_pct.mean() if len(win) else 0
    avg_l = loss.ret_pct.mean() if len(loss) else 0
    expectancy = wr * avg_w + (1 - wr) * avg_l
    print("=" * 50)
    print(f"거래 수        {len(tr)}")
    print(f"승률           {wr*100:.1f}%")
    print(f"평균 수익(승)  {avg_w:+.2f}%")
    print(f"평균 손실(패)  {avg_l:+.2f}%")
    print(f"기대값/거래    {expectancy:+.2f}%   ← 이게 양수여야 전략이 성립")
    print(f"손익비         {abs(avg_w/avg_l) if avg_l else float('inf'):.2f}")
    print(f"평균 보유일    {tr.days.mean():.1f}")
    print(f"청산 사유      {tr.reason.value_counts().to_dict()}")
    print("-" * 50)
    print("지지선 종류별 기대값:")
    print(tr.groupby("kind").ret_pct.agg(["count", "mean"]).round(2))
    print("=" * 50)


def main():
    args = sys.argv[1:]
    period = "3y"
    if "--period" in args:
        k = args.index("--period"); period = args[k + 1]; del args[k:k + 2]
    tickers = [a for a in args if not a.startswith("--")]
    if not tickers:
        tickers = [l.strip().upper() for l in open(os.path.join(HERE, CFG["tickers_file"]))
                   if l.strip() and not l.startswith("#")]
    raw = yf.download(tickers, period=period, group_by="ticker",
                      auto_adjust=True, progress=False)
    all_tr = []
    for t in tickers:
        df = (raw[t] if len(tickers) > 1 else raw).dropna()
        if len(df) < 120:
            continue
        all_tr += run_one(t, df)
    tr = pd.DataFrame(all_tr)
    tr.to_csv(os.path.join(HERE, "backtest_trades.csv"), index=False)
    summarize(tr)


if __name__ == "__main__":
    main()
