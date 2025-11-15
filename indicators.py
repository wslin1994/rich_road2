# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

def ema(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=period, adjust=False, min_periods=period).mean()

def rma(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(alpha=1/period, adjust=False).mean()

def atr(df: pd.DataFrame, period: int=14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    return rma(tr, period)

def donchian(df: pd.DataFrame, period: int=20):
    upper = df["high"].rolling(period, min_periods=period).max()
    lower = df["low"].rolling(period, min_periods=period).min()
    return upper, lower

def adx(df: pd.DataFrame, period: int=14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move
    tr1 = (high - low)
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_ = rma(tr, period)
    plus_di = 100 * rma(plus_dm, period) / atr_
    minus_di = 100 * rma(minus_dm, period) / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return rma(dx, period)
