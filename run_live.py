# -*- coding: utf-8 -*-
import argparse, yaml, json
from notifier import Notifier
from strategy_trend_intraday import StrategyParams
from live_trader import LiveConfig, LiveTrader

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, default="config/live.yaml")
    args = ap.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    tg = cfg.get("telegram", {})
    notifier = Notifier(enabled=tg.get("enabled", True), bot_token=tg.get("bot_token",""), chat_id=str(tg.get("chat_id","")))

    params = StrategyParams(
        ltf=cfg.get("ltf","15m"), htf=cfg.get("htf","4h"),
        ema_fast=cfg.get("ema_fast",20), ema_slow=cfg.get("ema_slow",80), htf_ema=cfg.get("htf_ema",200),
        adx_period=cfg.get("adx_period",14), adx_threshold=cfg.get("adx_threshold",28),
        donchian=cfg.get("donchian",90), atr_period=cfg.get("atr_period",14),
        atr_stop_mult=cfg.get("atr_stop_mult",2.5), atr_trail_mult=cfg.get("atr_trail_mult",3.2),
        allow_short=cfg.get("allow_short", False),
        time_stop_bars=cfg.get("time_stop_bars",36), cooldown_bars=cfg.get("cooldown_bars",6),
        flat_daily=cfg.get("flat_daily", True), flat_time_utc=cfg.get("flat_time_utc","23:55"),
        avoid_hours_utc=cfg.get("avoid_hours_utc", [0,1,2,3,4,5,6]),
        fee_bps=cfg.get("fee_bps",4.5), slippage_bps=cfg.get("slippage_bps",2.0),
        risk_per_trade=cfg.get("risk_per_trade",0.005),
        breakout_buffer_bps=cfg.get("breakout_buffer_bps",5.0), min_atr_pct=cfg.get("min_atr_pct",0.10),
        require_adx_rising=cfg.get("require_adx_rising", True)
    )

    lc = cfg.get("trade", {})
    bn = cfg.get("binance", {})
    paths = cfg.get("paths", {})

    live_cfg = LiveConfig(
        market=cfg.get("market","usdm"),
        symbols=[str(s) for s in cfg.get("symbols",["ETHUSDT"])],
        ltf=cfg.get("ltf","15m"), htf=cfg.get("htf","4h"),
        params=params,
        live_enabled=lc.get("live_enabled", False),
        use_testnet=lc.get("use_testnet", False),
        paper_initial_equity=float(lc.get("paper_initial_equity",10000.0)),
        quote_ccy=str(lc.get("quote_ccy","USDT")),
        qty_min_notional=float(lc.get("qty_min_notional",5.0)),
        api_key=bn.get("api_key",""), api_secret=bn.get("api_secret",""),
        spot_base=bn.get("spot_base_url","https://api.binance.com"),
        usdm_base=bn.get("usdm_base_url","https://fapi.binance.com"),
        usdm_testnet_base=bn.get("usdm_testnet_base_url","https://testnet.binancefuture.com"),
        notifier=notifier,
        status_interval_min=int(tg.get("status_interval_min",60)),
        state_path=paths.get("state_file","state/state.json")
    )

    lt = LiveTrader(live_cfg)
    lt.run_forever()

if __name__ == "__main__":
    main()
