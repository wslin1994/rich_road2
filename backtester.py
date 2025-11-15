# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import math
from strategy_trend_intraday import StrategyParams, infer_minutes

@dataclass
class Trade:
    symbol: str
    side: str          # 'long' / 'short'
    qty: float
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    pnl: float
    gross_pnl: float
    fees: float
    bars_held: int
    reason: str

@dataclass
class Position:
    side: str
    qty: float
    entry_price: float
    stop: float
    entry_time: pd.Timestamp
    bars_held: int = 0
    init_stop_dist: float = 0.0  # 1R 距离（用于保本）

def _slip_price(price: float, bps: float, side: str, is_entry: bool) -> float:
    shift = price * (bps * 1e-4)
    if is_entry:
        return price + shift if side == "long" else price - shift
    else:
        return price - shift if side == "long" else price + shift

def _fees(notional: float, fee_bps: float) -> float:
    return abs(notional) * (fee_bps * 1e-4)

def _round_qty(qty: float) -> float:
    return float(np.floor(qty * 1e6) / 1e6)

class Backtester:
    def __init__(self, data: Dict[str, pd.DataFrame], params: StrategyParams, initial_equity: float=10000.0):
        self.data = data
        self.params = params
        self.initial_equity = initial_equity
        self.trades: List[Trade] = []
        self.equity_curve = None
        self.summary = {}

    def run(self) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
        all_times = sorted(set().union(*[set(df.index) for df in self.data.values()]))
        if not all_times:
            raise ValueError("No bars after filtering. Check date range/market/data files.")
        equity = self.initial_equity
        positions: Dict[str, Position] = {}
        cooldown: Dict[str, int] = {sym:0 for sym in self.data.keys()}
        eq_records = []
        minutes = infer_minutes(self.params.ltf)

        dfs = self.data

        for t in all_times:
            # 更新持仓（trail/stop/时间止损 + 1R 保本）
            for sym, df in dfs.items():
                if t not in df.index:  # 此时间点该 symbol 无bar
                    continue
                row = df.loc[t]
                if sym in positions:
                    pos = positions[sym]
                    pos.bars_held += 1
                    atr = float(row["atr"])
                    # 更新拖尾
                    if pos.side == "long":
                        pos.stop = max(pos.stop, row["close"] - self.params.atr_trail_mult * atr)
                        # 1R 保本
                        if (row["close"] - pos.entry_price) >= pos.init_stop_dist:
                            pos.stop = max(pos.stop, pos.entry_price)
                        # 触发
                        if row["low"] <= pos.stop:
                            exit_px = _slip_price(pos.stop, self.params.slippage_bps, pos.side, is_entry=False)
                            fee = _fees(pos.qty*pos.entry_price, self.params.fee_bps) + _fees(pos.qty*exit_px, self.params.fee_bps)
                            pnl = pos.qty * (exit_px - pos.entry_price) - fee
                            gross = pos.qty * (exit_px - pos.entry_price)
                            self.trades.append(Trade(sym, pos.side, pos.qty, pos.entry_time, pos.entry_price, t, exit_px, pnl, gross, fee, pos.bars_held, "Stop/Trail"))
                            equity += pnl
                            del positions[sym]
                            cooldown[sym] = self.params.cooldown_bars
                    else:
                        pos.stop = min(pos.stop, row["close"] + self.params.atr_trail_mult * atr)
                        if (pos.entry_price - row["close"]) >= pos.init_stop_dist:
                            pos.stop = min(pos.stop, pos.entry_price)
                        if row["high"] >= pos.stop:
                            exit_px = _slip_price(pos.stop, self.params.slippage_bps, pos.side, is_entry=False)
                            fee = _fees(pos.qty*pos.entry_price, self.params.fee_bps) + _fees(pos.qty*exit_px, self.params.fee_bps)
                            pnl = pos.qty * (pos.entry_price - exit_px) - fee
                            gross = pos.qty * (pos.entry_price - exit_px)
                            self.trades.append(Trade(sym, pos.side, pos.qty, pos.entry_time, pos.entry_price, t, exit_px, pnl, gross, fee, pos.bars_held, "Stop/Trail"))
                            equity += pnl
                            del positions[sym]
                            cooldown[sym] = self.params.cooldown_bars

            # 名义敞口
            total_notional = 0.0
            for sym, pos in positions.items():
                if t in dfs[sym].index:
                    total_notional += pos.qty * float(dfs[sym].loc[t]["close"])

            # 入场/反手
            for sym, df in dfs.items():
                if t not in df.index: continue
                row = df.loc[t]

                if cooldown[sym] > 0:
                    cooldown[sym] -= 1

                # 时间止损
                if sym in positions and self.params.time_stop_bars > 0:
                    pos = positions[sym]
                    if pos.bars_held >= self.params.time_stop_bars:
                        exit_px = _slip_price(float(row["open"]), self.params.slippage_bps, pos.side, is_entry=False)
                        fee = _fees(pos.qty*pos.entry_price, self.params.fee_bps) + _fees(pos.qty*exit_px, self.params.fee_bps)
                        if pos.side == "long":
                            pnl = pos.qty * (exit_px - pos.entry_price) - fee
                            gross = pos.qty * (exit_px - pos.entry_price)
                        else:
                            pnl = pos.qty * (pos.entry_price - exit_px) - fee
                            gross = pos.qty * (pos.entry_price - exit_px)
                        self.trades.append(Trade(sym, pos.side, pos.qty, pos.entry_time, pos.entry_price, t, exit_px, pnl, gross, fee, pos.bars_held, "TimeStop"))
                        equity += pnl
                        del positions[sym]
                        cooldown[sym] = self.params.cooldown_bars
                        continue

                if sym not in positions and cooldown[sym] == 0:
                    sig = int(row.get("signal_exec", 0))
                    if sig == 0:
                        continue
                    # long_only 限制
                    if (not self.params.allow_short) and sig < 0:
                        continue

                    atr_val = float(row["atr"])
                    if np.isnan(atr_val) or atr_val <= 0:
                        continue
                    entry_px_raw = float(row["open"])
                    side = "long" if sig > 0 else "short"
                    entry_px = _slip_price(entry_px_raw, self.params.slippage_bps, side, is_entry=True)

                    stop_dist = self.params.atr_stop_mult * atr_val
                    if stop_dist <= 0:
                        continue
                    risk_amt = equity * self.params.risk_per_trade
                    qty = risk_amt / stop_dist
                    qty = _round_qty(qty)
                    if qty <= 0:
                        continue

                    # 账户杠杆/敞口约束
                    new_notional = total_notional + qty * entry_px
                    max_notional = self.params.max_leverage * equity
                    if new_notional > max_notional:
                        allow = max(0.0, max_notional - total_notional)
                        qty = _round_qty(allow / entry_px)
                        if qty <= 0:
                            continue

                    # 扣除入场手续费
                    fee_entry = _fees(qty * entry_px, self.params.fee_bps)
                    equity_after_fee = equity - fee_entry
                    if equity_after_fee <= 0:
                        continue
                    equity = equity_after_fee

                    # 初始止损
                    if side == "long":
                        stop = entry_px - stop_dist
                    else:
                        stop = entry_px + stop_dist

                    positions[sym] = Position(side=side, qty=qty, entry_price=entry_px, stop=stop, entry_time=t, init_stop_dist=stop_dist)
                    total_notional += qty * entry_px

            # 记净值
            mark_equity = equity
            for sym, pos in positions.items():
                if t in dfs[sym].index:
                    px = float(dfs[sym].loc[t]["close"])
                    if pos.side == "long":
                        mark_equity += pos.qty * (px - pos.entry_price)
                    else:
                        mark_equity += pos.qty * (pos.entry_price - px)
            eq_records.append((t, mark_equity))

        # 强平
        t = all_times[-1]
        for sym, pos in list(positions.items()):
            px = float(dfs[sym].loc[t]["close"]) if t in dfs[sym].index else pos.entry_price
            exit_px = _slip_price(px, self.params.slippage_bps, pos.side, is_entry=False)
            fee = _fees(pos.qty*pos.entry_price, self.params.fee_bps) + _fees(pos.qty*exit_px, self.params.fee_bps)
            if pos.side == "long":
                pnl = pos.qty * (exit_px - pos.entry_price) - fee
                gross = pos.qty * (exit_px - pos.entry_price)
            else:
                pnl = pos.qty * (pos.entry_price - exit_px) - fee
                gross = pos.qty * (pos.entry_price - exit_px)
            self.trades.append(Trade(sym, pos.side, pos.qty, pos.entry_time, pos.entry_price, t, exit_px, pnl, gross, fee, pos.bars_held, "ForceClose"))
            del positions[sym]

        equity_df = pd.DataFrame(eq_records, columns=["timestamp","equity"]).set_index("timestamp")
        trades_df = pd.DataFrame([t.__dict__ for t in self.trades])

        # 汇总
        ret = equity_df["equity"].pct_change().fillna(0.0)
        bars_per_year = int((365*24*60)//minutes)
        ann_vol = ret.std() * math.sqrt(bars_per_year) if ret.std() > 0 else 0.0
        ann_ret = (equity_df["equity"].iloc[-1] / max(1e-12, equity_df["equity"].iloc[0])) ** (bars_per_year / max(1, len(ret))) - 1.0 if len(ret)>0 else 0.0
        sharpe = (ret.mean() / ret.std() * math.sqrt(bars_per_year)) if ret.std() > 0 else 0.0
        roll_max = equity_df["equity"].cummax()
        dd = equity_df["equity"] / roll_max - 1.0
        max_dd = dd.min()

        win_rate = float((trades_df["pnl"] > 0).mean()) if len(trades_df)>0 else 0.0
        pf = float(trades_df.loc[trades_df["pnl"]>0,"pnl"].sum() / abs(trades_df.loc[trades_df["pnl"]<0,"pnl"].sum())) if (trades_df["pnl"]<0).any() else float("inf") if len(trades_df)>0 else 0.0
        self.summary = {
            "initial_equity": self.initial_equity,
            "final_equity": float(equity_df["equity"].iloc[-1]) if len(equity_df)>0 else self.initial_equity,
            "total_return": float(equity_df["equity"].iloc[-1]/equity_df["equity"].iloc[0]-1.0) if len(equity_df)>0 else 0.0,
            "annual_return": float(ann_ret),
            "annual_vol": float(ann_vol),
            "sharpe": float(sharpe),
            "max_drawdown": float(max_dd),
            "num_trades": int(len(trades_df)),
            "win_rate": float(win_rate),
            "profit_factor": float(pf),
        }
        return equity_df, trades_df, self.summary
