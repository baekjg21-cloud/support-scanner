"""지지선 탐지 로직 (scanner.py / backtest.py 공용)

지지선 정의
  1) 피봇 저점: 좌우 PIVOT_WINDOW일 안에서 가장 낮은 저가. 저점이 확정되려면
     우측 PIVOT_WINDOW일이 지나야 하므로, 실전/백테스트 모두 그 지연을 반영한다.
  2) 클러스터: 피봇 저점들을 CLUSTER_PCT 이내로 묶어 '터치 횟수'를 센다.
     2번 이상 되돌아온 가격대만 지지선으로 인정한다.
  3) 이동평균(MA50, MA200)은 동적 지지선으로 함께 본다.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class Support:
    level: float       # 지지선 가격
    touches: int       # 터치 횟수 (MA는 0)
    kind: str          # 'pivot' | 'ma50' | 'ma200'
    last_touch_idx: int  # 마지막 터치 봉 index


def pivot_lows(low: np.ndarray, window: int) -> np.ndarray:
    """각 봉이 좌우 window일 내 최저가면 True. 우측 window일이 지나야 확정됨."""
    n = len(low)
    out = np.zeros(n, dtype=bool)
    for i in range(window, n - window):
        seg = low[i - window:i + window + 1]
        if low[i] == seg.min() and (seg == low[i]).sum() == 1:
            out[i] = True
    return out


def cluster_levels(levels: list[tuple[int, float]], cluster_pct: float) -> list[Support]:
    """(index, price) 리스트를 가격 근접도로 묶는다."""
    if not levels:
        return []
    levels = sorted(levels, key=lambda x: x[1])
    clusters: list[list[tuple[int, float]]] = [[levels[0]]]
    for idx, p in levels[1:]:
        ref = np.mean([x[1] for x in clusters[-1]])
        if abs(p - ref) / ref <= cluster_pct:
            clusters[-1].append((idx, p))
        else:
            clusters.append([(idx, p)])
    return [
        Support(level=float(np.mean([x[1] for x in c])),
                touches=len(c), kind="pivot",
                last_touch_idx=max(x[0] for x in c))
        for c in clusters
    ]


def find_supports(df: pd.DataFrame, upto: int, cfg: dict) -> list[Support]:
    """df.iloc[:upto+1] 까지만 보고 지지선을 찾는다 (미래 정보 차단)."""
    w = cfg["pivot_window"]
    lookback = cfg["lookback_days"]
    start = max(0, upto - lookback)
    low = df["Low"].values[start:upto + 1]
    piv = pivot_lows(low, w)
    # 우측 w일이 지나 '확정된' 피봇만 사용 → 마지막 w개 봉은 제외됨 (pivot_lows 구조상 자동)
    levels = [(start + i, float(low[i])) for i in np.where(piv)[0]]
    sups = [s for s in cluster_levels(levels, cfg["cluster_pct"])
            if s.touches >= cfg["min_touches"]]

    close = df["Close"].values
    for n, kind in ((50, "ma50"), (200, "ma200")):
        if upto + 1 >= n + 20 and cfg.get(f"use_{kind}", True):
            # 이동평균이 '지지'였는지 확인: 최근 20일 중 종가가 MA 위였던 날이
            # ma_above_ratio 이상일 때만 지지선으로 인정. 아래에 있다가 뚫고
            # 올라온 경우(저항 돌파)는 제외 — 뉴스 급등을 지지 반등으로 오인 방지.
            ma_series = pd.Series(close[:upto + 1]).rolling(n).mean().values
            recent_c = close[upto - 19:upto + 1]
            recent_ma = ma_series[upto - 19:upto + 1]
            above = float((recent_c > recent_ma).mean())
            if above < cfg.get("ma_above_ratio", 0.7):
                continue
            ma = float(ma_series[upto])
            sups.append(Support(level=ma, touches=0, kind=kind, last_touch_idx=upto))
    return sups


def check_signal(df: pd.DataFrame, upto: int, cfg: dict) -> dict | None:
    """upto 봉 종가 기준으로 '지지선 근접 매수 후보'인지 판단."""
    if upto < 60:
        return None
    close = float(df["Close"].values[upto])
    sups = find_supports(df, upto, cfg)
    tol = cfg["tolerance_pct"]
    # 현재가가 지지선 바로 위(~tol) 또는 살짝 아래(-tol/2)
    near = [s for s in sups
            if -tol / 2 <= (close - s.level) / s.level <= tol]
    if not near:
        return None
    best = max(near, key=lambda s: (s.touches, -abs(close - s.level)))

    # 추세 필터: MA200 위 (없으면 통과)
    if cfg.get("require_above_ma200", True) and upto + 1 >= 200:
        ma200 = df["Close"].values[upto - 199:upto + 1].mean()
        if close < ma200 * (1 - tol):
            return None

    # 거래량 필터: 당일 거래량 ≥ 20일 평균 × vol_mult (매수세 확인)
    vol = df["Volume"].values
    if upto >= 20:
        avg20 = vol[upto - 20:upto].mean()
        vol_ratio = float(vol[upto] / avg20) if avg20 > 0 else 0.0
    else:
        vol_ratio = 0.0
    if vol_ratio < cfg["vol_mult"]:
        return None

    # 반등 확인: 당일 종가가 저가보다 위 (아래꼬리). 망치형에 가까울수록 좋음
    low_d = float(df["Low"].values[upto])
    high_d = float(df["High"].values[upto])
    rng = high_d - low_d
    close_pos = (close - low_d) / rng if rng > 0 else 0.5  # 0=저가 마감, 1=고가 마감
    if close_pos < cfg.get("min_close_pos", 0.5):
        return None

    # 당일 급등 제한: 하루 +max_day_gain 이상 뛴 건 지지 반등이 아니라 뉴스 급등 → 제외
    prev_c = float(df["Close"].values[upto - 1])
    day_gain = close / prev_c - 1
    if day_gain > cfg.get("max_day_gain", 0.06):
        return None

    return {
        "day_gain_pct": day_gain * 100,
        "close": close,
        "support": best.level,
        "dist_pct": (close - best.level) / best.level * 100,
        "touches": best.touches,
        "kind": best.kind,
        "vol_ratio": vol_ratio,
        "close_pos": close_pos,
        "stop": best.level * (1 - cfg["stop_pct"]),
        "target": close * (1 + cfg["target_pct"]),
    }
