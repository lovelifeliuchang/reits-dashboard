#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T期货策略信号计算 — 供 reits_monitor 每日调用
用法：python3 t_signal.py [YYYYMMDD]
输出：reits_reports/t_signal_YYYYMMDD.json
"""

import sys
import json
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, '/Applications/Wind API.app/Contents/python')
from WindPy import w as wind
wind.start(waitTime=15)
warnings.filterwarnings("ignore")

OUTPUT_DIR   = Path(__file__).parent / "reits_reports"
LONG_TH      = 1.0
PERSIST_DAYS = 20
ATR_MULT     = 1.5


def fetch_data(end_date: str, lookback_days: int = 300):
    end   = end_date
    start = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    r = wind.wsd("T.CFE", "open,high,low,close,volume,oi", start, end, "PriceAdj=F")
    price = pd.DataFrame(dict(zip([f.lower() for f in r.Fields], r.Data)),
                         index=pd.to_datetime(r.Times)).reset_index()
    price.columns = ["date"] + [f.lower() for f in r.Fields]
    price.rename(columns={"oi": "open_interest"}, inplace=True)

    y10 = pd.Series(wind.edb("S0059749", start, end).Data[0],
                    index=pd.to_datetime(wind.edb("S0059749", start, end).Times), name="y10")
    y2  = pd.Series(wind.edb("S0059745", start, end).Data[0],
                    index=pd.to_datetime(wind.edb("S0059745", start, end).Times), name="y2")
    yield_df = pd.DataFrame({"y10": y10, "y2": y2}).reset_index()
    yield_df.columns = ["date", "y10", "y2"]

    df = price.merge(yield_df, on="date", how="left")
    df[["y10", "y2"]] = df[["y10", "y2"]].ffill()
    return df.reset_index(drop=True)


def calc_indicators(df):
    c, h, lo = df["close"], df["high"], df["low"]
    tr = pd.concat([h - lo, (h - c.shift()).abs(), (lo - c.shift()).abs()], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14).mean()
    up_move = h.diff(); dn_move = -lo.diff()
    pdm = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
    ndm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)
    atr14 = df["atr14"]
    pdi = 100 * pd.Series(pdm, index=c.index).rolling(14).mean() / (atr14 + 1e-9)
    ndi = 100 * pd.Series(ndm, index=c.index).rolling(14).mean() / (atr14 + 1e-9)
    df["adx14"] = (100 * (pdi - ndi).abs() / (pdi + ndi + 1e-9)).rolling(14).mean()
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df["macd_hist"] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()
    df["bb_mid"]    = c.rolling(20).mean()
    bb_std          = c.rolling(20).std()
    df["bb_upper"]  = df["bb_mid"] + 2 * bb_std
    df["bb_lower"]  = df["bb_mid"] - 2 * bb_std
    delta = c.diff()
    df["rsi14"] = 100 - 100 / (1 + delta.clip(lower=0).rolling(14).mean() /
                                ((-delta.clip(upper=0)).rolling(14).mean() + 1e-9))
    df["y2_ma20"]   = df["y2"].rolling(20).mean()
    df["y2_dev"]    = df["y2"] - df["y2_ma20"]
    df["y10_ma40"]  = df["y10"].rolling(40, min_periods=20).mean()
    df["bull_gate"] = (df["y10"] < df["y10_ma40"]).astype(int)
    return df


def generate_signal(df):
    n         = len(df)
    hist      = df["macd_hist"].values
    rsi       = df["rsi14"].values
    bb_upper  = df["bb_upper"].values
    bb_lower  = df["bb_lower"].values
    close     = df["close"].values
    y2_dev    = df["y2_dev"].values
    y10v      = df["y10"].values
    y10_ma20  = pd.Series(y10v).rolling(20, min_periods=10).mean().values
    adx       = df["adx14"].values
    oi        = df["open_interest"].values

    macd_evt  = np.zeros(n); boll_evt = np.zeros(n)
    rsi_evt   = np.zeros(n); macro_evt = np.zeros(n)

    for i in range(2, n):
        if not (np.isnan(y10v[i]) or np.isnan(y10_ma20[i])):
            if y10v[i-1] >= y10_ma20[i-1] and y10v[i] < y10_ma20[i]:
                macd_evt[i] = 1
            elif y10v[i-1] < y10_ma20[i-1] and y10v[i] >= y10_ma20[i]:
                macd_evt[i] = -1
        if not (np.isnan(hist[i]) or np.isnan(hist[i-1])):
            if hist[i-1] > 0 and hist[i] <= 0:
                macd_evt[i] = max(macd_evt[i], 0.5)
            elif hist[i-1] < 0 and hist[i] >= 0:
                macd_evt[i] = min(macd_evt[i], -0.5)
        if not np.isnan(bb_lower[i]):
            if close[i] < bb_lower[i]:  boll_evt[i] = 1
            elif close[i] > bb_upper[i]: boll_evt[i] = -1
        if not np.isnan(rsi[i]):
            if rsi[i] < 30:    rsi_evt[i] = 1.0
            elif rsi[i] < 35:  rsi_evt[i] = 0.7
            elif rsi[i] > 78:  rsi_evt[i] = -1.0
            elif rsi[i] > 70:  rsi_evt[i] = -0.7
        if not (np.isnan(y2_dev[i]) or np.isnan(y2_dev[i-1])):
            if y2_dev[i-1] >= 0 and y2_dev[i] < 0:   macro_evt[i] = 1
            elif y2_dev[i-1] < 0 and y2_dev[i] >= 0: macro_evt[i] = -1

    def persist(events, days):
        sig = np.zeros(len(events)); current = 0; countdown = 0
        for i in range(len(events)):
            if events[i] != 0: current = float(events[i]); countdown = days
            if countdown > 0: sig[i] = current; countdown -= 1
        return sig

    macd_s  = persist(macd_evt, PERSIST_DAYS)
    boll_s  = persist(boll_evt, PERSIST_DAYS)
    rsi_s   = persist(rsi_evt,  PERSIST_DAYS)
    macro_s = persist(macro_evt, PERSIST_DAYS * 2)
    oi_mom5 = -(pd.Series(oi).pct_change(5)).values
    oi_evt  = np.where(np.abs(oi_mom5) > 0.05, np.sign(oi_mom5) * 0.5, 0.0)
    oi_s    = persist(oi_evt, 5)

    long_score = np.zeros(n)
    for i in range(n):
        adx_i   = adx[i] if not np.isnan(adx[i]) else 20.0
        w_trend = 1.4 if adx_i > 30 else (1.1 if adx_i > 20 else 1.0)
        w_rev   = 0.7 if adx_i > 30 else (1.0 if adx_i > 20 else 1.3)
        long_score[i] = (max(macd_s[i], 0) * w_trend + max(boll_s[i], 0) * w_rev +
                         max(rsi_s[i], 0) * w_rev + max(macro_s[i], 0) * 1.0 +
                         max(oi_s[i], 0) * 0.4)

    gate    = df["bull_gate"].values
    raw_sig = np.zeros(n)
    for i in range(n):
        if long_score[i] >= LONG_TH and gate[i] == 1: raw_sig[i] = 1

    signal = np.zeros(n)
    for i in range(1, n):
        if raw_sig[i] == 1 and raw_sig[i-1] == 1: signal[i] = 1
        else: signal[i] = 0

    return signal, long_score, macd_s, boll_s, rsi_s, macro_s, oi_s


def compute(date_str: str) -> dict:
    """计算给定日期（YYYY-MM-DD）的信号，返回结构化 dict"""
    df = fetch_data(date_str, lookback_days=300)
    df = calc_indicators(df)
    signal, long_score, macd_s, boll_s, rsi_s, macro_s, oi_s = generate_signal(df)

    last  = df.iloc[-1]
    sig   = int(signal[-1])
    ls    = float(long_score[-1])
    adx_i = float(last["adx14"]) if not np.isnan(float(last["adx14"])) else 20.0
    w_trend = 1.4 if adx_i > 30 else (1.1 if adx_i > 20 else 1.0)
    w_rev   = 0.7 if adx_i > 30 else (1.0 if adx_i > 20 else 1.3)
    atr_i   = max(float(last["atr14"]) if not np.isnan(float(last["atr14"])) else 0.15, 0.08)

    if sig == 1:
        stop_level = round(float(last["close"]) - ATR_MULT * atr_i, 3)
        signal_label = "▲ 做多"
    else:
        stop_level = None
        signal_label = "⬜ 空仓观望"

    # 信号触发日
    trigger_date = last["date"]
    for j in range(len(signal) - 2, -1, -1):
        if signal[j] != sig:
            trigger_date = df["date"].iloc[j + 1]
            break
    hold_days = int((last["date"] - trigger_date).days)

    result = {
        "date":          last["date"].strftime("%Y-%m-%d"),
        "signal":        sig,
        "signal_label":  signal_label,
        "long_score":    round(ls, 3),
        "threshold":     LONG_TH,
        "close":         round(float(last["close"]), 3),
        "y10":           round(float(last["y10"]), 4),
        "y10_ma40":      round(float(last["y10_ma40"]), 4),
        "bull_gate":     int(last["bull_gate"]),
        "adx14":         round(adx_i, 1),
        "atr14":         round(atr_i, 4),
        "stop_level":    stop_level,
        "trigger_date":  trigger_date.strftime("%Y-%m-%d"),
        "hold_days":     hold_days,
        "factors": {
            "macd":  {"score": round(float(max(macd_s[-1],  0)), 3), "weight": w_trend,
                      "contribution": round(float(max(macd_s[-1], 0)) * w_trend, 3)},
            "boll":  {"score": round(float(max(boll_s[-1],  0)), 3), "weight": w_rev,
                      "contribution": round(float(max(boll_s[-1], 0)) * w_rev, 3)},
            "rsi":   {"score": round(float(max(rsi_s[-1],   0)), 3), "weight": w_rev,
                      "contribution": round(float(max(rsi_s[-1],  0)) * w_rev, 3)},
            "macro": {"score": round(float(max(macro_s[-1], 0)), 3), "weight": 1.0,
                      "contribution": round(float(max(macro_s[-1], 0)), 3)},
            "oi":    {"score": round(float(max(oi_s[-1],    0)), 3), "weight": 0.4,
                      "contribution": round(float(max(oi_s[-1], 0)) * 0.4, 3)},
        },
    }
    return result


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg:
        date_str = f"{arg[:4]}-{arg[4:6]}-{arg[6:]}"
    else:
        date_str = datetime.today().strftime("%Y-%m-%d")

    date_key = date_str.replace("-", "")
    out_path = OUTPUT_DIR / f"t_signal_{date_key}.json"

    if out_path.exists():
        print(f"T信号已存在: {out_path}，跳过")
        return

    print(f"计算 T期货信号 [{date_str}]...")
    result = compute(date_str)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ T信号已保存: {out_path}")
    sig_emoji = result["signal_label"]
    print(f"  信号：{sig_emoji}  评分：{result['long_score']}/{result['threshold']}  "
          f"T收盘：{result['close']}  10Y：{result['y10']}%")


if __name__ == "__main__":
    main()
