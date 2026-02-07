# Polymarket 自动交易机器人

一个用于在 Polymarket 预测市场构建自动化交易机器人的 Python 模块化框架。

## 功能特点

- **模块化架构** - 策略、执行、数据管理清晰分离
- **自动跟单 v2.0** - 全新优化，支持持久化存储、API 重试、智能跟单
- **风险管理** - 内置仓位限制、滑点控制、敞口管理
- **模拟运行** - 支持干跑模式（Dry Run），不真正下单即可测试策略
- **虚拟持仓** - 模拟交易闭环，记录盈亏和交易历史
- **日志记录** - 完善的日志系统，便于监控和调试

## 项目结构

```
polymarket_bot/
├── __init__.py          # 包初始化
├── config.py            # 配置管理
├── client.py            # Polymarket API 客户端
├── strategy.py          # 策略基类和示例策略
├── executor.py          # 订单执行和持仓管理
├── bot.py               # 主机器人协调器
└── utils.py             # 工具函数

根目录脚本:
├── run_bot.py           # 简洁的启动脚本（推荐）
├── example.py           # 交互式示例
└── test.py              # 测试脚本

数据文件:
├── virtual_positions.json     # 模拟持仓
├── trade_history.csv          # 交易历史
├── copy_trading_state.json    # 跟单策略状态（已处理交易 ID）
└── bot.log                    # 日志文件
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入配置
```

### 3. 运行机器人

```bash
# 显示帮助
python run_bot.py

# 简单策略（低买高卖），单次运行
python run_bot.py simple

# 自动跟单策略，单次运行
python run_bot.py copy

# 自动跟单策略，连续运行（推荐用于实盘）
python run_bot.py copy continuous

# 查看跟单策略状态
python run_bot.py copy status

# 动量策略
python run_bot.py momentum once
```

## 配置说明

在 `.env` 文件中配置：

```bash
# API 凭证（私钥用于生成 API 凭证）
POLYMARKET_PRIVATE_KEY=your_ethereum_private_key

# 交易参数
MAX_POSITION_SIZE=100.0      # 单个市场最大仓位（USDC）
MAX_SLIPPAGE=0.02            # 最大滑点 2%
DRY_RUN=true                 # 干跑模式，不真正下单（生产环境设为 false）

# 运行参数
POLL_INTERVAL=60             # 策略执行间隔（秒）
LOG_LEVEL=INFO               # 日志级别
```

## 策略说明

### CopyTradingStrategy（自动跟单策略 v2.0）推荐

自动追踪目标用户的交易并复制：

```bash
# 基本用法
python run_bot.py copy

# 自定义跟单金额
python run_bot.py copy --copy-amount 20

# 按比例跟单（50%）
python run_bot.py copy --copy-ratio 0.5

# 调整时间窗口（10分钟内）
python run_run.py copy --time-window 600

# 追踪不同用户
python run_bot.py copy --target-user 0x...

# 连续运行（用于生产）
python run_bot.py copy continuous
```

**参数说明：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `target_user` | Sonix 地址 | 要追踪的目标用户钱包地址 |
| `copy_amount` | 10.0 | 固定跟单金额（USDC） |
| `copy_ratio` | None | 跟单比例（如 0.5 表示 50%） |
| `time_window` | 300 | 时间窗口（秒），只跟此范围内的交易 |
| `max_copy_size` | 100.0 | 最大跟单金额 |

**跟单逻辑：**
- 目标用户 BUY → 检查是否有持仓 → 无则跟单买入
- 目标用户 SELL → 检查是否有持仓 → 有则卖出全部
- 持久化存储已处理交易，重启不重复跟单
- API 请求自动重试，提高稳定性

### SimpleStrategy（简单低买高卖策略）

```bash
python run_bot.py simple
```

- 价格低于 0.3 时买入
- 价格达到 0.5 或以上时卖出
- 支持快速闭环测试模式

### MomentumStrategy（动量策略）

```bash
python run_bot.py momentum
```

- 价格快速上涨时买入
- 达到盈利目标（15%）时止盈
- 下跌超过阈值（10%）时止损

### 自定义策略

继承 `BaseStrategy` 类实现 `generate_signals` 方法：

```python
from polymarket_bot.strategy import BaseStrategy, Signal

class MyStrategy(BaseStrategy):
    def __init__(self):
        super().__init__("my_strategy")

    def generate_signals(self, markets, positions, balance):
        signals = []
        # 在这里实现你的交易逻辑
        # markets: 可用市场列表
        # positions: 当前持仓
        # balance: 可用余额
        return signals
```

## 数据文件说明

| 文件 | 说明 |
|------|------|
| `virtual_positions.json` | 模拟持仓记录（仅干跑模式使用） |
| `trade_history.csv` | 完整交易历史，包含盈亏、持仓时间、滑点 |
| `copy_trading_state.json` | 跟单策略状态，持久化已处理交易 ID |
| `bot.log` | 日志文件 |

## 状态管理

### 查看跟单状态

```bash
python run_bot.py copy status
```

输出示例：
```
========================================
策略状态:
========================================
  target_user: 0x7a0d...0eff14
  copy_amount: 10.0
  copy_ratio: None
  time_window: 300
  processed_trades: 15
  cached_markets: 8
  state_file: copy_trading_state.json
========================================
```

### 重置跟单状态

如需重新同步所有历史交易，可以删除状态文件：

```bash
rm copy_trading_state.json
```

## 风险提示

⚠️ **重要提醒：**
- 自动交易有风险，请先用干跑模式测试
- 切勿分享你的私钥或 API 凭证
- 从小仓位开始，逐步增加
- 监控机器人运行日志
- 仅使用你能承受损失的资金
- 生产环境建议设置 `DRY_RUN=false`

## 技术栈

- Python 3.8+
- py_clob_client（Polymarket API）
- python-dotenv（环境变量）
- requests（HTTP 请求）
- python-dateutil（时间处理）

## 许可证

MIT License
