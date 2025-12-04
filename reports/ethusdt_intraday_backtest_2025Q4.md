# ETHUSDT 15m/4h 趋势回测（2025-08-04 ~ 2025-12-04）

本轮回测使用最新代码与数据，目标是在不显著降低频次的前提下保持稳健收益。核心设定为 15m 入场 + 4h 趋势过滤，仅做多，带 ADX 上升过滤与较低突破缓冲。

## 最佳方案（基线）
- **参数**：ema_fast=18, ema_slow=50, htf_ema=200, adx_threshold=20, donchian=60, atr_stop_mult=2.1, atr_trail_mult=2.8, breakout_buffer_bps=3, min_atr_pct=0.07, require_adx_rising=true, allow_short=false, risk_per_trade=1%，cooldown_bars=4, time_stop_bars=60。
- **结果**（2025-08-04~2025-12-04）：总收益 +5.30%，年化 17.18%，Sharpe 1.86，最大回撤 -3.39%，交易 8 笔，胜率 75%，PF 3.49。
- **频次权衡**：4 个月 8 笔交易（≈0.46 笔/周），虽然频次不高，但在当前区间能保持低回撤和正收益，适合稳健纸上测试；若需更高频率可降低 donchian 或放开 allow_short，但当前区间绩效会下降。

### 复现命令
```bash
python run_backtest.py --market usdm --symbols ETHUSDT --ltf 15m --htf 4h \
  --start 2025-08-04 --end 2025-12-04 \
  --ema_fast 18 --ema_slow 50 --htf_ema 200 --adx_threshold 20 --donchian 60 \
  --atr_period 14 --atr_stop_mult 2.1 --atr_trail_mult 2.8 \
  --fee_bps 4.5 --slippage_bps 2 --risk_per_trade 0.01 \
  --cooldown_bars 4 --time_stop_bars 60 \
  --breakout_buffer_bps 3 --min_atr_pct 0.07 --require_adx_rising --download
```

## 真实运行（纸上模拟）步骤
1. 编辑 `config/live.yaml`：保持 `live_enabled=false`，`paper_initial_equity=100`（与你的本金一致），策略参数已预填为上方基线。
2. 配置 Telegram：填入 `telegram.bot_token` 和 `telegram.chat_id`，保留 `status_interval_min=60` 以便每小时推送净值/持仓/收益率。
3. 启动纸上服务：
```bash
python run_live.py --config config/live.yaml
```
4. 检查通知：Bot 每小时会报告当前市值净值（含未实现盈亏）、持仓与收益率；开/平仓、错误也会实时推送。
5. 若要提升频次：可尝试减小 `donchian` 或开启 `allow_short`，但请先回测验证，因为在近期区间会牺牲稳健性。

## 其他观察
- 较高的突破缓冲和 ATR 门槛能显著降低回撤，但会牺牲频次；当前组合在回撤/频次之间取平衡。
- 若未来波动放大，可上调 `min_atr_pct` 或 `adx_threshold` 以避免过度交易；若行情震荡，可关闭 ADX 上升过滤提升成交。
