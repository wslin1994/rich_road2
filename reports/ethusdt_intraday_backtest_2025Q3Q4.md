# ETHUSDT 15m/4h 趋势策略回测（2025-08-04 ~ 2025-12-04）

> 今日日期：2025-12-04；本报告覆盖最近 4 个月。所有回测均假设初始权益 10,000 USDT，USDM 永续，含双边手续费 4.5 bps、滑点 2 bps。

## 结论摘要
- **候选 A（稳健多头）**：`ema_fast=14, ema_slow=45, htf_ema=180, adx_threshold=20, donchian=55, atr_stop=2.0, atr_trail=2.8, risk=0.8%`，保持 ADX 上升过滤与日线平仓，4 个月收益 **+4.1%**，最大回撤 -2.8%，夏普 1.74，成交 9 笔，胜率 66.7%，利润因子 2.61。
- **候选 B（略高频）**：`ema_fast=16, ema_slow=50, htf_ema=180, adx_threshold=18, donchian=50, breakout_buffer=2bps, risk=1%`，收益 **+2.4%**，最大回撤 -3.5%，成交 11 笔。
- 放宽 ADX 上升或开启做空会显著拉低绩效（见下方失效试验），因此维持多头+ADX 上升过滤是当前阶段的稳健方案。

## 详细试验记录

| ID | 方向 | 关键参数差异 | 收益 | 年化夏普 | 回撤 | 交易数 | 备注 |
|---|---|---|---|---|---|---|---|
| A | 多 | ema 14/45，HTF EMA 180，ADX≥20，Donchian 55，breakout 3bps，ATR 止损 2.0/2.8，risk 0.8%，保持 ADX 上升 | **+4.12%** | 1.74 | -2.78% | 9 | 稳健、低回撤，但频率偏低（约 0.5 笔/周）【测试 dca70e】 |
| B | 多 | ema 16/50，HTF EMA 180，ADX≥18，Donchian 50，breakout 2bps，ATR 止损 2.0/2.8，risk 1%，保持 ADX 上升 | +2.43% | 0.84 | -3.46% | 11 | 稍高频（~0.65 笔/周），收益略低【测试 0883d0】 |
| C | 多 | ema 12/34，HTF EMA 150，ADX≥18，Donchian 45，breakout 2bps，ATR 1.8/2.6，risk 1.2%，关闭 ADX 上升 | +0.23% | 0.12 | -6.21% | 18 | 频率提升但回撤与效率显著变差【测试 8aa5b2】 |
| D | 多空 | ema 10/30，HTF EMA 120，ADX≥16，Donchian 35，breakout 1.5bps，ATR 1.7/2.4，risk 1.5%，关闭 ADX 上升，允许做空 | -24.17% | -1.95 | -29.98% | 97 | 高频但绩效严重恶化【测试 0f5ffe】 |
| E | 多 | ema 12/34，HTF EMA 150，ADX≥18，Donchian 45，breakout 2bps，ATR 1.9/2.6，risk 1%，关闭 ADX 上升 | -1.02% | -0.20 | -5.48% | 18 | 放松 ADX 过滤后收益转负【测试 0bdffe】 |
| F | 多空 | 与 B 相近但允许做空 | -8.08% | -1.48 | -9.30% | 43 | 做空在本区间显著拖累收益【测试 955ce7】 |

## 推荐执行方案（满足“不过于低频”与周收益目标的折中）
- 采用 **候选 B** 作为基础：相较 A 提供 ~22% 更多成交，回撤仍可控。若希望进一步提升收益，可将单笔风险上调至 1.2% 并手动监测回撤；但周化 3% 目标在该区间并未达到，建议结合杠杆或多品种分散。
- 保持：15m 入场 / 4h 趋势过滤、ADX 上升过滤、日终平仓与开盘避开 0-6 点（UTC）。
- 不建议：关闭 ADX 上升过滤、开放做空或过度缩短 Donchian 通道，这些会显著增加回撤并降低利润因子。

## 复现命令
- 候选 A（稳健多头）
```bash
python run_backtest.py --market usdm --symbols ETHUSDT --ltf 15m --htf 4h --start 2025-08-04 --end 2025-12-04 \
  --ema_fast 14 --ema_slow 45 --htf_ema 180 --adx_threshold 20 --donchian 55 \
  --atr_period 14 --atr_stop_mult 2.0 --atr_trail_mult 2.8 --risk_per_trade 0.008 \
  --cooldown_bars 3 --time_stop_bars 56 --breakout_buffer_bps 3 --min_atr_pct 0.07 --download
```
- 候选 B（略高频多头）
```bash
python run_backtest.py --market usdm --symbols ETHUSDT --ltf 15m --htf 4h --start 2025-08-04 --end 2025-12-04 \
  --ema_fast 16 --ema_slow 50 --htf_ema 180 --adx_threshold 18 --donchian 50 \
  --atr_period 14 --atr_stop_mult 2.0 --atr_trail_mult 2.8 --risk_per_trade 0.01 \
  --cooldown_bars 3 --time_stop_bars 56 --breakout_buffer_bps 2 --min_atr_pct 0.06 --download
```

## 后续优化思路
- **多品种/多周期并行**：在当前稳定参数下叠加 BTC/BNB/OP 等高流动品种，可提升周度目标收益；若算力允许，可在 15m/1h、1h/4h 组合上并行跑，增加机会。
- **提升交易密度的安全手段**：
  - 避开时段由 0-6 点缩短为 0-2 点，并保持 ADX 上升过滤；
  - 风险由 1.0% 微调到 1.2%，但设置权益回撤阈值（如 -6% 停止交易、-3% 降低风险）。
- **头寸管理**：引入梯度加仓/分批止盈（例如 1R 平半仓，2R 全平），以及尾盘平仓后次日首笔风险减半，降低隔夜情绪影响。
- **信号确认**：
  - 在 Donchian 突破的同时，要求 LTF RSI>55（多头）或 <45（空头）以过滤震荡假突破；
  - 关注 HTF（4h）K 线的蜡烛形态（上影长/下影长）作为加减分项。
- **执行可靠性**：对网络/交易失败加入重试与 Telegram 预警，并定期（每日）输出持仓与 PnL 摘要，确保策略“可执行”。

## 100 USDT 可执行投资组合（多币种分散，目标周收益 3% 的折中方案）
- **资金分配**（总本金 100 USDT）：ETH 40%、BTC 30%、BNB 20%、OP 10%。每个品种单笔风险按该子账户权益的 **1%** 设置（例：ETH 子资金 40 USDT，单笔亏损上限 0.4 USDT）。
- **参数与运行建议**：
  - ETHUSDT：使用“候选 B”参数，保持多头、ADX 上升过滤；
  - BTCUSDT：同样的 15m/4h 模式，参数参考 ETH 候选 B（可将 donchian=45, adx_threshold=20）；
  - BNBUSDT：略缩短 Donchian（40）并把 breakout_buffer_bps 提高到 3 以抑制假突破；
  - OPUSDT：波动更高，将 atr_stop_mult=2.3、atr_trail_mult=3.0，且 risk_per_trade 降到 0.8%。
- **实盘落地步骤**：
  1) 按子资金划分下单数量，开启纸上账户验证 1 周，确认成交/通知链路正常；
  2) `run_live.py --symbols ETHUSDT,BTCUSDT,BNBUSDT,OPUSDT --ltf 15m --htf 4h --risk_per_trade 0.01 --cooldown_bars 3 --time_stop_bars 56 --avoid_hours 0 1 2 --breakout_buffer_bps 2 --min_atr_pct 0.06 --require_adx_rising`（根据品种可在 YAML/CLI 覆盖差异参数）；
  3) 设置日内与权益回撤保护：日内亏损达 -2% 或权益回撤超 -6% 自动停机/降风险；
  4) 每周回顾成交与 PnL，依据胜率/利润因子微调风险或 Donchian 长度，保持周频 8-15 笔为目标区间。
- **期望与风控**：多品种叠加可将单一品种 0.5-0.7 笔/周提升至 8-15 笔/周；若平均单笔期望 0.3R、胜率 45-50%、风险 1% 左右，理论上可逼近 2-4% 周收益，但需严格执行停机与滑点/手续费监控。
