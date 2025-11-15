# -*- coding: utf-8 -*-
import json, os
import pandas as pd

def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    ts_col = "timestamp" if "timestamp" in df.columns else "open_time" if "open_time" in df.columns else None
    if ts_col is None:
        raise ValueError("CSV 缺少时间列 timestamp / open_time")
    df["timestamp"] = pd.to_datetime(df[ts_col], utc=True)
    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)
    df = df[["timestamp","open","high","low","close","volume"]].drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df = df.set_index("timestamp")
    return df

def ensure_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.index.tz is None:
        df = df.tz_localize("UTC")
    else:
        df = df.tz_convert("UTC")
    return df

def save_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def load_json(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
