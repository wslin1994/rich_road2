# -*- coding: utf-8 -*-
import time, uuid, math, traceback
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
import pandas as pd
from datetime import datetime, timezone, timedelta

from binance_data import fetch_klines
from strategy_trend_intraday import StrategyParams, build_features_ltf, build_features_htf, merge_mtf, compute_signals
from notifier import Notifier
from state_store import StateStore
from binance_client import BinanceClient

@dataclass
class LiveConfig:
    # 运行
    market: str
    symbols: List[str]
    ltf: str
    htf: str
    params: StrategyParams
    # 交易 & API
    live_enabled: bool
    use_testnet: bool
    paper_initial_equity: float
    quote_ccy: str
    qty_min_notional: float
    # Binance
    api_key: str
    api_secret: str
    spot_base: str
    usdm_base: str
    usdm_testnet_base: Optional[str]
    # 通知
    notifier: Notifier
    status_interval_min: int
    # 文件
    state_path: str

def _bp_to_frac(bp: float) -> float:
    return bp / 10000.0

def _round_step(qty: float, step: float) -> float:
    if step <= 0: return float(qty)
    return math.floor(qty / step) * step

def _now_utc():
    return datetime.now(timezone.utc)

class LiveTrader:
    def __init__(self, cfg: LiveConfig):
        self.cfg = cfg
        self.state = StateStore(cfg.state_path)
        if not self.state.get("service_id"):
            self.state.set("service_id", str(uuid.uuid4()))
        self.notifier = cfg.notifier
        # Binance client
        self.client = BinanceClient(
            market=cfg.market, api_key=cfg.api_key, api_secret=cfg.api_secret,
            base_url_spot=cfg.spot_base, base_url_usdm=cfg.usdm_base,
            base_url_usdm_testnet=cfg.usdm_testnet_base, use_testnet=cfg.use_testnet
        )
        # 记录上次状态上报时间
        self.last_status_ts = 0

    # --- 账户/步长 ---
    def _get_filters(self, symbol: str) -> Dict[str, float]:
        info = self.client.exchange_info(symbol, futures=(self.cfg.market=="usdm"))
        sym = info["symbols"][0]
        f_map = {f["filterType"]: f for f in sym["filters"]}
        step = float(f_map.get("LOT_SIZE", {}).get("stepSize", 0.001))
        tick = float(f_map.get("PRICE_FILTER", {}).get("tickSize", 0.01))
        return {"step": step, "tick": tick}

    def _get_available_equity(self) -> float:
        if not self.cfg.live_enabled:
            eq = self.state.get("equity", None)
            if eq is None:
                eq = self.cfg.paper_initial_equity
                self.state.set("equity", eq)
            return float(eq)
        # futures balance
        try:
            bals = self.client.futures_balance()
            for b in bals:
                if b.get("asset") == self.cfg.quote_ccy:
                    return float(b.get("balance") or b.get("withdrawAvailable") or 0.0)
        except Exception as e:
            self.notifier.error_throttle("余额查询失败", {"err": str(e)})
        # 回退：用上次记录
        eq = self.state.get("equity", self.cfg.paper_initial_equity)
        return float(eq)

    def _update_equity_paper(self, delta: float):
        eq = self.state.get("equity", self.cfg.paper_initial_equity)
        eq = float(eq) + float(delta)
        self.state.set("equity", eq)

    # --- 下单 ---
    def _place_order(self, symbol: str, side: str, qty: float, price_hint: Optional[float]=None, reduce_only: bool=False) -> Dict[str, Any]:
        if self.cfg.live_enabled:
            try:
                cid = f"LT-{int(time.time())}-{uuid.uuid4().hex[:6]}"
                data = self.client.futures_order_market(symbol, side, qty, reduce_only=reduce_only, client_id=cid)
                return {"ok": True, "detail": data}
            except Exception as e:
                self.notifier.error_throttle("实盘下单失败", {"symbol": symbol, "side": side, "qty": qty, "err": str(e)})
                return {"ok": False, "detail": {"error": str(e)}}
        else:
            # 纸上：记录成交价（带滑点）并更新权益
            px = float(price_hint or 0.0)
            return {"ok": True, "detail": {"symbol": symbol, "side": side, "qty": qty, "price": px, "paper": True, "ts": int(time.time()*1000)}}

    # --- 主循环 ---
    def run_forever(self):
        self.notifier.info("服务启动", {"service_id": self.state.get("service_id"), "live_enabled": self.cfg.live_enabled})
        while True:
            try:
                self._tick_once()
            except Exception as e:
                self.notifier.error_throttle("主循环异常", {"err": str(e), "trace": traceback.format_exc()[:500]})
                time.sleep(10)

    def _tick_once(self):
        now = _now_utc()

        for symbol in self.cfg.symbols:
            # 准备数据：最近一段（确保足够计算 HTF 指标）
            end = now + timedelta(minutes=1)
            start = now - timedelta(days=15)
            df_ltf = fetch_klines(symbol, self.cfg.ltf, start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"),
                                  market=self.cfg.market)
            df_htf = fetch_klines(symbol, self.cfg.htf, start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"),
                                  market=self.cfg.market)

            if len(df_ltf) < 200 or len(df_htf) < 60:
                self.notifier.warn("数据不足跳过", {"symbol": symbol, "ltf": len(df_ltf), "htf": len(df_htf)})
                time.sleep(20)
                continue

            df_ltf = df_ltf.set_index("timestamp")
            df_htf = df_htf.set_index("timestamp")

            feat_ltf = build_features_ltf(df_ltf, self.cfg.params)
            feat_htf = build_features_htf(df_htf, self.cfg.params)
            feat = merge_mtf(feat_ltf, feat_htf)
            feat = compute_signals(feat, self.cfg.params)

            # 只在“上一根 LTF close 完成”后执行：取最后一根的 signal（本根开盘执行）
            last_bar_time = feat.index[-1]
            prev_bar_time = feat.index[-2]
            prev_sig = int(feat["signal"].iloc[-1])      # 刚收盘bar信号
            exec_sig = int(feat["signal_exec"].iloc[-1]) # 下一根执行的信号（名义）

            # 避免重复：如果上次处理的 bar_ts 与本次相同，则跳过
            last_done_ts = self.state.get("last_bar_ts", None)
            if last_done_ts == str(last_bar_time):
                # 定时状态上报
                self._maybe_send_status(symbol, feat)
                continue

            # 执行
            self._process_symbol(symbol, feat)

            # 记 last_bar_ts
            self.state.set("last_bar_ts", str(last_bar_time))

            # 定时状态上报
            self._maybe_send_status(symbol, feat)

        # 对齐到下一个 30s
        time.sleep(30)

    def _maybe_send_status(self, symbol: str, feat: pd.DataFrame):
        if not self.cfg.notifier.enabled:
            return
        interval = int(self.cfg.status_interval_min) * 60
        now = int(time.time())
        if now - self.last_status_ts >= interval:
            self.last_status_ts = now
            # 简单权益与持仓展示
            eq = self._get_available_equity()
            pos = self.state.get("positions", {}).get(symbol, None)
            self.cfg.notifier.info("状态报告", {
                "symbol": symbol,
                "equity": round(eq, 4),
                "pos": json.dumps(pos, ensure_ascii=False) if pos else "flat",
                "live_enabled": self.cfg.live_enabled
            })

    def _process_symbol(self, symbol: str, feat: pd.DataFrame):
        row_prev = feat.iloc[-2]  # 已收盘bar（产生信号）
        row_now  = feat.iloc[-1]  # 刚开的bar（执行）
        sig = int(row_prev["signal"])      # 以上一根的信号进行判断
        atr = float(row_prev["atr"])
        open_px = float(row_now["open"])

        # 当前状态
        positions = self.state.get("positions", {})
        pos = positions.get(symbol, None)

        # 日终平仓
        if self.cfg.params.flat_daily:
            try:
                fh, fm = map(int, self.cfg.params.flat_time_utc.split(":"))
                now = datetime.now(timezone.utc)
                if now.hour == fh and now.minute >= fm and pos:
                    # 平仓
                    self._close_position(symbol, pos, row_now)
                    positions = self.state.get("positions", {})
                    pos = positions.get(symbol, None)
            except Exception:
                pass

        # 冷却或空信号
        cooldown = int(self.state.get("cooldown_bars", 0))
        if cooldown > 0:
            self.state.set("cooldown_bars", cooldown-1)
            return

        # 若无持仓，且有入场信号
        if not pos and sig != 0:
            if (not self.cfg.params.allow_short) and sig < 0:
                return
            # 计算仓位
            stop_dist = self.cfg.params.atr_stop_mult * atr
            eq = self._get_available_equity()
            risk_cash = eq * self.cfg.params.risk_per_trade
            qty = risk_cash / stop_dist if stop_dist>0 else 0.0
            # 步长 & 名义保护
            filters = self._get_filters(symbol)
            qty = max(0.0, _round_step(qty, filters["step"]))
            if qty * open_px < self.cfg.qty_min_notional:
                self.cfg.notifier.warn("名义过小，取消开仓", {"symbol": symbol, "qty": qty, "open_px": open_px})
                return

            # 成交价（加滑点）
            frac = _bp_to_frac(self.cfg.params.slippage_bps)
            entry_px = open_px * (1 + frac) if sig>0 else open_px * (1 - frac)
            # 下单
            side = "BUY" if sig>0 else "SELL"
            res = self._place_order(symbol, side, qty, price_hint=entry_px, reduce_only=False)
            if res.get("ok"):
                # 建仓成功，记录状态
                stop = entry_px - stop_dist if sig>0 else entry_px + stop_dist
                positions[symbol] = {
                    "side": "long" if sig>0 else "short",
                    "qty": qty,
                    "entry_price": entry_px,
                    "stop": stop,
                    "bars_held": 0,
                    "init_stop_dist": stop_dist
                }
                self.state.set("positions", positions)
                # 纸上扣手续费
                if not self.cfg.live_enabled:
                    fee = qty * entry_px * (self.cfg.params.fee_bps * 1e-4)
                    self._update_equity_paper(-fee)
                self.cfg.notifier.info("开仓",
                    {"symbol": symbol, "side": positions[symbol]["side"], "qty": qty, "px": round(entry_px,4), "stop": round(stop,4)})
            else:
                self.cfg.notifier.error_throttle("开仓失败", {"symbol": symbol, "err": res.get("detail")})

        # 若有持仓：更新拖尾 & 1R 保本 & 触发止损
        positions = self.state.get("positions", {})
        pos = positions.get(symbol, None)
        if pos:
            pos["bars_held"] += 1
            # 拖尾
            if pos["side"] == "long":
                new_stop = max(pos["stop"], row_prev["close"] - self.cfg.params.atr_trail_mult * atr)
                pos["stop"] = new_stop
                # 1R 保本
                if (row_prev["close"] - pos["entry_price"]) >= pos["init_stop_dist"]:
                    pos["stop"] = max(pos["stop"], pos["entry_price"])
                # 触发
                if row_now["low"] <= pos["stop"]:
                    self._close_position(symbol, pos, row_now, reason="Stop/Trail")
                    return
            else:
                new_stop = min(pos["stop"], row_prev["close"] + self.cfg.params.atr_trail_mult * atr)
                pos["stop"] = new_stop
                if (pos["entry_price"] - row_prev["close"]) >= pos["init_stop_dist"]:
                    pos["stop"] = min(pos["stop"], pos["entry_price"])
                if row_now["high"] >= pos["stop"]:
                    self._close_position(symbol, pos, row_now, reason="Stop/Trail")
                    return
            # 时间止损
            if self.cfg.params.time_stop_bars > 0 and pos["bars_held"] >= self.cfg.params.time_stop_bars:
                self._close_position(symbol, pos, row_now, reason="TimeStop")
                return
            self.state.set("positions", positions)

    def _close_position(self, symbol: str, pos: Dict[str, Any], row_now: Any, reason: str="Close"):
        side_out = "SELL" if pos["side"] == "long" else "BUY"
        qty = float(pos["qty"])
        # 成交价（加滑点朝不利方向）
        frac = _bp_to_frac(self.cfg.params.slippage_bps)
        px = float(row_now["open"])
        exit_px = px * (1 - frac) if pos["side"]=="long" else px * (1 + frac)

        res = self._place_order(symbol, side_out, qty, price_hint=exit_px, reduce_only=True)
        if res.get("ok"):
            # 手续费（双边）
            fee = qty * pos["entry_price"] * (self.cfg.params.fee_bps * 1e-4) + qty * exit_px * (self.cfg.params.fee_bps * 1e-4)
            if pos["side"] == "long":
                pnl = qty * (exit_px - pos["entry_price"]) - fee
            else:
                pnl = qty * (pos["entry_price"] - exit_px) - fee
            if not self.cfg.live_enabled:
                self._update_equity_paper(pnl)
            positions = self.state.get("positions", {})
            positions.pop(symbol, None)
            self.state.set("positions", positions)
            self.cfg.notifier.info("平仓", {"symbol": symbol, "reason": reason, "px": round(exit_px,4), "pnl": round(pnl,4)})
            # 冷却
            self.state.set("cooldown_bars", self.cfg.params.cooldown_bars)
        else:
            self.cfg.notifier.error_throttle("平仓失败", {"symbol": symbol, "err": res.get("detail")})
