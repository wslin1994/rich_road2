
# 加密货币日内趋势系统（ETH 优先、Binance、含实盘/纸上、Telegram 通知）

> **重要声明**：本项目仅用于教育与研究，不构成投资建议。加密资产风险极高，历史回测不代表未来表现。务必先在 **纸上交易或 Testnet** 验证，再谨慎决定是否实盘。

## 功能清单
- **趋势策略（日内）**：15m 入场 / 4h 趋势过滤，EMA 交叉 + ADX 过滤 + Donchian 突破；
  - **增强过滤**：ADX 上升、最小突破缓冲（bps）、最低波动门槛（ATR%）；
  - **风控**：ATR 初始止损 + ATR 追踪止损 + **到达 1R 自动保本**。
- **回测**：多品种组合回测（含手续费/滑点/仓位 sizing/冷却/时间止损/日终平仓）。
- **实时服务**：
  - **纸上（默认）/ 实盘（可开关）**：掉线重试，重启恢复状态；
  - **Binance USDM REST**（HMAC）：市价下单、查询步长/精度、余额/持仓同步；
  - **Telegram 通知**：成交/平仓/异常/心跳/定时状态报告（可配置）。
- **配置文件**：所有参数（含 APIKey、Telegram）集中在 `config/live.yaml`。

## 快速开始
```bash
pip install -r requirements.txt
```

### 回测示例（ETH 单品种，2025-08-01 → 2025-11-02，15m/4h）
```bash
python run_backtest.py \
  --market usdm --symbols ETHUSDT \
  --ltf 15m --htf 4h \
  --start 2025-08-01 --end 2025-11-02 \
  --ema_fast 20 --ema_slow 80 --htf_ema 200 \
  --adx_threshold 28 --donchian 90 \
  --atr_period 14 --atr_stop_mult 2.5 --atr_trail_mult 3.2 \
  --fee_bps 4.5 --slippage_bps 2 \
  --risk_per_trade 0.005 --cooldown_bars 6 --time_stop_bars 36 \
  --flat_daily --avoid_hours 0 1 2 3 4 5 6 --long_only
```

### 启动实时服务（默认纸上，不实盘）
1. 编辑 `config/live.yaml`，把你的 **Binance API Key/Secret** 和 **Telegram** 配好（默认已写好你提供的机器人配置）。
2. 运行：
```bash
python run_live.py --config config/live.yaml
```
- 首次启动会发送一条“上线心跳”。
- 默认 **live_enabled=false**：只做**纸上模拟**，每次下单/平仓、异常、定时状态都会发 Telegram；若配置了 `status_interval_min=60`，Bot 会每小时推送当前净值（含未实现盈亏）、收益率与持仓。
- 若要实盘，把 `trade.live_enabled` 改为 `true`（强烈建议先用 testnet 验证）。
- 纸上模式默认本金 **100 USDT**（可在 `trade.paper_initial_equity` 修改）。

## 默认策略参数（基于 2025-08-04~2025-12-04 的回测基线）
- 市场/品种：**USDM / ETHUSDT**（可改为多品种）
- 周期：LTF=**15m**，HTF=**4h**
- 过滤：EMA(18/50) + **HTF EMA 200** + **ADX ≥ 20** + **Donchian=60**
- 费用/滑点：fee=**4.5 bps**，slippage=**2 bps**
- 风控：ATR(14)、Stop=**2.1×ATR**、Trail=**2.8×ATR**、冷却=**4 bar**、时间止损=**60 bar**、日终平仓、**long_only**
- 增强：**最小突破缓冲 3bp**、**最低波动 0.07%**、**ADX 上升过滤**

## 目录结构
```
crypto_trend_system_live/
├── binance_data.py               # 历史K线下载（REST）
├── indicators.py                 # EMA/ATR/ADX/Donchian
├── strategy_trend_intraday.py    # 日内策略（含增强过滤）
├── backtester.py                 # 回测引擎（含1R保本）
├── live_trader.py                # 实时主循环（纸上/实盘）
├── binance_client.py             # Binance USDM/Spot REST 客户端（HMAC）
├── notifier.py                   # Telegram 通知
├── state_store.py                # 状态持久化（重启恢复）
├── utils.py                      # CSV & 时间工具
├── run_backtest.py               # 回测 CLI
├── run_live.py                   # 实时 CLI
├── config/
│   └── live.yaml                 # 你的配置（默认写入你提供的 Telegram 配置）
├── state/                        # 持久化状态（json）
├── logs/                         # 服务日志（建议用PM2/系统服务托管）
└── requirements.txt
```

## 安全注意
- **千万不要**把 `config/live.yaml` 提交到任何远程仓库（包含密钥与机器人令牌）。
- 实盘开启前，请先在 **纸上** 或 **Testnet** 连续跑满至少 2–4 周，确认风控、成交与通知正常。
