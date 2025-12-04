# -*- coding: utf-8 -*-
import io
import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone
from typing import Optional, Sequence

SPOT_ENDPOINTS: Sequence[str] = (
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
)

USDM_ENDPOINTS: Sequence[str] = (
    "https://fapi.binance.com",
    "https://fapi.binance.me",
    "https://fapi.binancefuture.com",
)

def _to_millis(ts: str) -> int:
    try:
        dt = datetime.fromisoformat(ts.replace("Z","")).replace(tzinfo=timezone.utc)
    except ValueError:
        dt = datetime.strptime(ts, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp()*1000)

def _endpoints(market: str, base_url_spot: Optional[str]=None, base_url_usdm: Optional[str]=None) -> Sequence[str]:
    if market == "spot":
        return (base_url_spot,) if base_url_spot else SPOT_ENDPOINTS
    elif market == "usdm":
        return (base_url_usdm,) if base_url_usdm else USDM_ENDPOINTS
    else:
        raise ValueError("market must be 'spot' or 'usdm'")


def _next_month(dt: datetime) -> datetime:
    month = dt.month + 1
    year = dt.year
    if month == 13:
        month = 1
        year += 1
    return dt.replace(year=year, month=month, day=1)


def _vision_prefix(market: str) -> str:
    if market == "spot":
        return "https://data.binance.vision/data/spot"
    if market == "usdm":
        return "https://data.binance.vision/data/futures/um"
    raise ValueError("market must be 'spot' or 'usdm'")


def _fetch_from_vision(symbol: str, interval: str, start_ms: int, end_ms: int, market: str, sess: requests.Session) -> pd.DataFrame:
    prefix = _vision_prefix(market)
    start_dt = datetime.fromtimestamp(start_ms/1000, tz=timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_dt = datetime.fromtimestamp(end_ms/1000, tz=timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_cursor = start_dt
    frames = []
    cols = [
        "openTime","open","high","low","close","volume","closeTime","qav","numTrades","takerBaseVol","takerQuoteVol","ignore"
    ]
    while month_cursor <= end_dt:
        url = f"{prefix}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{month_cursor.year}-{month_cursor.month:02d}.zip"
        r = sess.get(url, timeout=30)
        if r.status_code == 404:
            month_cursor = _next_month(month_cursor)
            continue
        r.raise_for_status()
        df = pd.read_csv(io.BytesIO(r.content), compression="zip", header=None, names=cols)
        df[["openTime","closeTime"]] = df[["openTime","closeTime"]].apply(pd.to_numeric, errors="coerce").astype("Int64")
        df = df.dropna(subset=["openTime","closeTime"])
        df[["openTime","closeTime"]] = df[["openTime","closeTime"]].astype(int)
        df = df[(df["openTime"] >= start_ms) & (df["closeTime"] <= end_ms)]
        if df.empty:
            month_cursor = _next_month(month_cursor)
            continue
        df["timestamp"] = pd.to_datetime(df["openTime"], unit="ms", utc=True)
        for c in ["open","high","low","close","volume"]:
            df[c] = df[c].astype(float)
        frames.append(df[["timestamp","open","high","low","close","volume"]])
        month_cursor = _next_month(month_cursor)
    if not frames:
        return pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])
    out = pd.concat(frames, axis=0).drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return out

def fetch_klines(symbol: str, interval: str, start: str, end: str, market: str="spot",
                 base_url_spot: Optional[str]=None, base_url_usdm: Optional[str]=None,
                 save_path: Optional[str]=None, sleep_sec: float=0.25) -> pd.DataFrame:
    endpoints = _endpoints(market, base_url_spot, base_url_usdm)
    path = "/api/v3/klines" if market=="spot" else "/fapi/v1/klines"
    start_ms = _to_millis(start)
    end_ms   = _to_millis(end)
    limit = 1000
    frames = []
    cur = start_ms
    sess = requests.Session()
    try:
        while cur < end_ms:
            params = {"symbol": symbol.upper(), "interval": interval, "startTime": cur, "endTime": end_ms, "limit": limit}
            last_exc = None
            for base in endpoints:
                url = base + path
                try:
                    r = sess.get(url, params=params, timeout=20)
                    r.raise_for_status()
                    break
                except requests.RequestException as exc:
                    last_exc = exc
                    continue
            else:
                raise RuntimeError(
                    f"无法下载 {symbol} {interval} K线（{market}）：{last_exc}. 尝试的节点: {', '.join(endpoints)}. "
                    "请检查代理/网络设置，或预先将对应 CSV 放入 data 目录后运行回测时不要使用 --download。"
                ) from last_exc
            data = r.json()
            if not data:
                break
            df = pd.DataFrame(data, columns=[
                "openTime","open","high","low","close","volume","closeTime","qav","numTrades","takerBaseVol","takerQuoteVol","ignore"
            ])
            df["timestamp"] = pd.to_datetime(df["openTime"], unit="ms", utc=True)
            for c in ["open","high","low","close","volume"]:
                df[c] = df[c].astype(float)
            frames.append(df[["timestamp","open","high","low","close","volume"]])
            cur = int(data[-1][6]) + 1
            time.sleep(sleep_sec)
    except RuntimeError as api_exc:
        vision_df = _fetch_from_vision(symbol.upper(), interval, start_ms, end_ms, market, sess)
        if not vision_df.empty:
            if save_path:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                vision_df.to_csv(save_path, index=False)
            return vision_df
        raise api_exc
    if not frames:
        return pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])
    out = pd.concat(frames, axis=0).drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        out.to_csv(save_path, index=False)
    return out
