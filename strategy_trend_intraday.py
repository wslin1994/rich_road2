# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Optional, List
import pandas as pd
import numpy as np
from indicators import ema, atr, donchian, adx

@dataclass
class StrategyParams:
    ltf: str = "15m"
    htf: str = "4h"
    ema_fast: int = 20
    ema_slow: int = 80
    htf_ema: int = 200
    adx_period: int = 14
    adx_threshold: float = 28.0
    donchian: int = 90
    atr_period: int = 14
    atr_stop_mult: float = 2.5
    atr_trail_mult: float = 3.2
    allow_short: bool = False  # long_only 默认
    time_stop_bars: int = 36
    cooldown_bars: int = 6
    flat_daily: bool = True
    flat_time_utc: str = "23:55"
    avoid_hours_utc: Optional[List[int]] = None
    fee_bps: float = 4.5
    slippage_bps: float = 2.0
    risk_per_trade: float = 0.005
    max_leverage: float = 3.0
    max_positions: int = 2
    # 增强过滤
    breakout_buffer_bps: float = 5.0  # 突破缓冲（bps）
    min_atr_pct: float = 0.10         # ATR/close *100 ≥ 此百分比
    require_adx_rising: bool = True

def infer_minutes(interval: str) -> int:
    m = {"1m":1,"3m":3,"5m":5,"15m":15,"30m":30,"1h":60,"2h":120,"4h":240,"6h":360,"8h":480,"12h":720,"1d":1440}
    if interval not in m:
        raise ValueError(f"Unsupported interval: {interval}")
    return m[interval]

def build_features_ltf(df_ltf: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    f = df_ltf.copy()
    f["ema_fast"] = ema(f["close"], params.ema_fast)
    f["ema_slow"] = ema(f["close"], params.ema_slow)
    f["atr"] = atr(f, params.atr_period)
    up, low = donchian(f, params.donchian)
    f["don_up"] = up
    f["don_low"] = low
    f["don_up_prev"] = f["don_up"].shift(1)
    f["don_low_prev"] = f["don_low"].shift(1)
    return f

def build_features_htf(df_htf: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    h = df_htf.copy()
    h["ema_trend"] = ema(h["close"], params.htf_ema)
    h["adx"] = adx(h, params.adx_period)
    # 在 4h 粒度判定“ADX 是否上升”，稍后合并到 15m 使用
    h["adx_rising_htf"] = h["adx"] > h["adx"].shift(1)
    h["trend_up"] = (h["close"] > h["ema_trend"]) & (h["adx"] >= params.adx_threshold)
    h["trend_dn"] = (h["close"] < h["ema_trend"]) & (h["adx"] >= params.adx_threshold)
    return h

def merge_mtf(ltf: pd.DataFrame, htf: pd.DataFrame) -> pd.DataFrame:
    ltfc = ltf.sort_index().reset_index().rename(columns={"index":"timestamp"})
    htfc = htf.sort_index().reset_index().rename(columns={"index":"timestamp"})
    out = pd.merge_asof(ltfc.sort_values("timestamp"),
                        htfc.sort_values("timestamp"),
                        on="timestamp", direction="backward", suffixes=("","_HTF"))
    out = out.set_index("timestamp")
    return out

def compute_signals(df: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    x = df.copy()
    x["hour"] = x.index.tz_convert("UTC").hour if x.index.tz is not None else x.index.hour
    avoid = set(params.avoid_hours_utc or [])
    x["avoid"] = x["hour"].isin(avoid)

    # 基础条件
    long_cond = (x.get("trend_up", False)) & (x["ema_fast"] > x["ema_slow"]) & (~x["avoid"])
    short_cond = (x.get("trend_dn", False)) & (x["ema_fast"] < x["ema_slow"]) & (~x["avoid"])

    # 最低波动门槛（ATR%）
    x["atr_pct"] = (x["atr"] / x["close"]) * 100.0
    vol_ok = x["atr_pct"] >= params.min_atr_pct

    # 突破缓冲（bps）
    buf = params.breakout_buffer_bps * 1e-4  # bps → 比例
    long_cond = long_cond & vol_ok & (x["close"] > x["don_up_prev"] * (1.0 + buf))
    short_cond = short_cond & vol_ok & (x["close"] < x["don_low_prev"] * (1.0 - buf))

    # ADX 上升过滤（新：使用 HTF 的 adx_rising_htf；合并后在当前 4h 窗口内整段有效）
    if params.require_adx_rising:
        col = "adx_rising_htf"
        if col in x.columns:
            x[col] = x[col].ffill()  # 防止局部缺失
            long_cond  = long_cond  & x[col]
            short_cond = short_cond & x[col]

    sig = pd.Series(0, index=x.index, dtype=int)
    sig[long_cond.fillna(False)] = 1
    if params.allow_short:
        sig[short_cond.fillna(False)] = -1

    x["signal"] = sig
    x["signal_exec"] = x["signal"].shift(1).fillna(0).astype(int)  # 次根开盘执行
    return x
