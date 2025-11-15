# -*- coding: utf-8 -*-
import time
import requests
import pandas as pd
from datetime import datetime, timezone
from typing import Optional

SPOT_ENDPOINT = "https://api.binance.com"
USDM_ENDPOINT = "https://fapi.binance.com"

def _to_millis(ts: str) -> int:
    try:
        dt = datetime.fromisoformat(ts.replace("Z","")).replace(tzinfo=timezone.utc)
    except ValueError:
        dt = datetime.strptime(ts, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp()*1000)

def _endpoint(market: str, base_url_spot: Optional[str]=None, base_url_usdm: Optional[str]=None) -> str:
    if market == "spot":
        return base_url_spot or SPOT_ENDPOINT
    elif market == "usdm":
        return base_url_usdm or USDM_ENDPOINT
    else:
        raise ValueError("market must be 'spot' or 'usdm'")

def fetch_klines(symbol: str, interval: str, start: str, end: str, market: str="spot",
                 base_url_spot: Optional[str]=None, base_url_usdm: Optional[str]=None,
                 save_path: Optional[str]=None, sleep_sec: float=0.25) -> pd.DataFrame:
    base = _endpoint(market, base_url_spot, base_url_usdm)
    path = "/api/v3/klines" if market=="spot" else "/fapi/v1/klines"
    url = base + path
    start_ms = _to_millis(start)
    end_ms   = _to_millis(end)
    limit = 1000
    frames = []
    cur = start_ms
    sess = requests.Session()
    while cur < end_ms:
        params = {"symbol": symbol.upper(), "interval": interval, "startTime": cur, "endTime": end_ms, "limit": limit}
        r = sess.get(url, params=params, timeout=20)
        r.raise_for_status()
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
    if not frames:
        return pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])
    out = pd.concat(frames, axis=0).drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    if save_path:
        out.to_csv(save_path, index=False)
    return out
