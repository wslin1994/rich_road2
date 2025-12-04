# -*- coding: utf-8 -*-
import argparse, os, json
from datetime import datetime, timezone
from typing import Dict
import pandas as pd
from binance_data import fetch_klines
from strategy_trend_intraday import StrategyParams, build_features_ltf, build_features_htf, merge_mtf, compute_signals
from backtester import Backtester
from utils import load_csv, ensure_utc_index

def prepare_symbol(symbol: str, market: str, ltf: str, htf: str, start: str, end: str, data_dir: str, params: StrategyParams) -> pd.DataFrame:
    ltf_csv = os.path.join(data_dir, f"{symbol}_{ltf}_{market}.csv")
    htf_csv = os.path.join(data_dir, f"{symbol}_{htf}_{market}.csv")
    if not os.path.exists(ltf_csv):
        df_ltf = fetch_klines(symbol, ltf, start, end, market=market, save_path=ltf_csv)
    else:
        df_ltf = load_csv(ltf_csv)
    if not os.path.exists(htf_csv):
        df_htf = fetch_klines(symbol, htf, start, end, market=market, save_path=htf_csv)
    else:
        df_htf = load_csv(htf_csv)
    df_ltf = ensure_utc_index(df_ltf)
    df_htf = ensure_utc_index(df_htf)
    df_ltf = df_ltf.loc[(df_ltf.index>=pd.to_datetime(start, utc=True))&(df_ltf.index<=pd.to_datetime(end, utc=True))]
    df_htf = df_htf.loc[(df_htf.index>=pd.to_datetime(start, utc=True))&(df_htf.index<=pd.to_datetime(end, utc=True))]
    f_ltf = build_features_ltf(df_ltf, params)
    f_htf = build_features_htf(df_htf, params)
    feat = merge_mtf(f_ltf, f_htf)
    feat = compute_signals(feat, params)
    return feat

def main():
    p = argparse.ArgumentParser(description="Binance 日内趋势回测（多资产）")
    p.add_argument("--market", type=str, default="usdm", choices=["spot","usdm"])
    p.add_argument("--symbols", nargs="+", default=["ETHUSDT"])
    p.add_argument("--ltf", type=str, default="15m")
    p.add_argument("--htf", type=str, default="4h")
    p.add_argument("--start", type=str, required=True)
    p.add_argument("--end", type=str, required=True)
    p.add_argument("--data_dir", type=str, default="data")
    p.add_argument("--initial_equity", type=float, default=10000.0)

    # 策略参数（默认即为你当前最优）
    p.add_argument("--ema_fast", type=int, default=20)
    p.add_argument("--ema_slow", type=int, default=80)
    p.add_argument("--htf_ema", type=int, default=200)
    p.add_argument("--adx_period", type=int, default=14)
    p.add_argument("--adx_threshold", type=float, default=28)
    p.add_argument("--donchian", type=int, default=90)
    p.add_argument("--atr_period", type=int, default=14)
    p.add_argument("--atr_stop_mult", type=float, default=2.5)
    p.add_argument("--atr_trail_mult", type=float, default=3.2)
    p.add_argument("--long_only", action="store_true", default=True)
    p.add_argument("--allow_short", dest="long_only", action="store_false", help="允许开空，默认仅做多")
    p.add_argument("--time_stop_bars", type=int, default=36)
    p.add_argument("--cooldown_bars", type=int, default=6)
    p.add_argument("--flat_daily", action="store_true", default=True)
    p.add_argument("--flat_time_utc", type=str, default="23:55")
    p.add_argument("--avoid_hours", nargs="*", type=int, default=[0,1,2,3,4,5,6])

    # 成本与过滤增强
    p.add_argument("--fee_bps", type=float, default=4.5)
    p.add_argument("--slippage_bps", type=float, default=2.0)
    p.add_argument("--risk_per_trade", type=float, default=0.005)
    p.add_argument("--breakout_buffer_bps", type=float, default=5.0)
    p.add_argument("--min_atr_pct", type=float, default=0.10)
    p.add_argument("--require_adx_rising", action="store_true", default=True)
    p.add_argument("--no_require_adx_rising", dest="require_adx_rising", action="store_false", help="禁用 ADX 上升过滤以提高交易频率")

    p.add_argument("--download", action="store_true")

    args = p.parse_args()

    params = StrategyParams(
        ltf=args.ltf, htf=args.htf,
        ema_fast=args.ema_fast, ema_slow=args.ema_slow, htf_ema=args.htf_ema,
        adx_period=args.adx_period, adx_threshold=args.adx_threshold,
        donchian=args.donchian, atr_period=args.atr_period,
        atr_stop_mult=args.atr_stop_mult, atr_trail_mult=args.atr_trail_mult,
        allow_short=not args.long_only, time_stop_bars=args.time_stop_bars, cooldown_bars=args.cooldown_bars,
        flat_daily=args.flat_daily, flat_time_utc=args.flat_time_utc,
        avoid_hours_utc=args.avoid_hours, fee_bps=args.fee_bps, slippage_bps=args.slippage_bps,
        risk_per_trade=args.risk_per_trade,
        breakout_buffer_bps=args.breakout_buffer_bps, min_atr_pct=args.min_atr_pct, require_adx_rising=args.require_adx_rising
    )

    if args.download:
        for sym in args.symbols:
            fetch_klines(sym, args.ltf, args.start, args.end, market=args.market, save_path=os.path.join(args.data_dir,f"{sym}_{args.ltf}_{args.market}.csv"))
            fetch_klines(sym, args.htf, args.start, args.end, market=args.market, save_path=os.path.join(args.data_dir,f"{sym}_{args.htf}_{args.market}.csv"))

    data: Dict[str, pd.DataFrame] = {}
    for sym in args.symbols:
        feat = prepare_symbol(sym, args.market, args.ltf, args.htf, args.start, args.end, args.data_dir, params)
        data[sym] = feat

    bt = Backtester(data, params, initial_equity=args.initial_equity)
    equity_df, trades_df, summary = bt.run()

    out_dir = "outputs"
    os.makedirs(out_dir, exist_ok=True)
    tag = f"{','.join(args.symbols)}_{args.ltf}_{args.htf}_{args.market}".replace(",","-").lower()
    equity_df.to_csv(os.path.join(out_dir, f"equity_{tag}.csv"))
    trades_df.to_csv(os.path.join(out_dir, f"trades_{tag}.csv"), index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
