# 交易历史记录系统使用指南

## 新增功能总览

### 1. 随机滑点模拟
在 DRY_RUN 模式下，每笔虚拟交易都会添加 0% - 1% 的随机滑点：
- **BUY 订单**: 成交价 = 市场价 × (1 + 滑点%)
- **SELL 订单**: 成交价 = 市场价 × (1 - 滑点%)

这样可以更真实地模拟实际交易环境，因为市价订单通常无法精确按照市场中间价成交。

### 2. 交易历史自动记录
每次执行 SELL 订单时，系统会自动记录完整的交易信息到 `trade_history.csv`，包括：

| 字段 | 说明 |
|------|------|
| timestamp | 交易时间（ISO格式）|
| token_id | Token ID（完整长度）|
| side | 交易方向（SELL）|
| entry_price | 买入价格（带6位小数）|
| exit_price | 卖出价格（带6位小数）|
| size | 持仓数量 |
| holding_time_seconds | 持仓时间（秒）|
| pnl | 盈亏金额（$）|
| pnl_pct | 盈亏百分比 |
| slippage | 卖出时的滑点 |

## CSV 文件示例

```csv
timestamp,token_id,side,entry_price,exit_price,size,holding_time_seconds,pnl,pnl_pct,slippage
2026-01-13T22:51:29.045232,111128191581505463501777127559667396812474366956707382672202929745167742497287,SELL,0.500818,0.496308,10.000000,74.43,-0.045099,-0.009005,0.007384
```

## 使用方式

### 方法 1：使用现有策略
任何策略在 DRY_RUN 模式下运行时，都会自动启用滑点模拟和交易历史记录功能。

```bash
# 确保配置文件中设置了 DRY_RUN=true
python run_bot.py
```

### 方法 2：使用演示脚本
我们提供了一个完整的演示脚本 `demo_trade_history.py`：

```bash
# 第一步：执行 BUY 订单
python demo_trade_history.py

# 第二步：执行 SELL 订单并记录交易历史
FORCE_SELL=true python demo_trade_history.py
```

## 数据分析

### 在 Excel 中分析
1. 使用 Excel 打开 `trade_history.csv`
2. 可以计算以下统计指标：
   - **胜率**: `=COUNTIF(pnl列,">0")/COUNT(pnl列)`
   - **平均盈亏**: `=AVERAGE(pnl列)`
   - **平均持仓时间**: `=AVERAGE(holding_time_seconds列)/3600` (小时)
   - **最大盈利**: `=MAX(pnl列)`
   - **最大亏损**: `=MIN(pnl列)`
   - **平均滑点**: `=AVERAGE(slippage列)`

### 在 Python 中分析

```python
import pandas as pd

# 读取交易历史
df = pd.read_csv('trade_history.csv')

# 基础统计
print("交易统计:")
print(f"总交易次数: {len(df)}")
print(f"胜率: {(df['pnl'] > 0).sum() / len(df):.2%}")
print(f"平均盈亏: ${df['pnl'].mean():.4f}")
print(f"平均盈亏比: {df['pnl_pct'].mean():.2%}")
print(f"平均持仓时间: {df['holding_time_seconds'].mean() / 3600:.2f} 小时")
print(f"平均滑点: {df['slippage'].mean():.2%}")

# 盈亏分布
print("\n盈亏分布:")
print(df['pnl'].describe())

# 最佳/最差交易
print(f"\n最佳交易: ${df['pnl'].max():.4f} ({df['pnl_pct'].max():.2%})")
print(f"最差交易: ${df['pnl'].min():.4f} ({df['pnl_pct'].min():.2%})")
```

## 实现细节

### 代码位置
- **滑点模拟**: `polymarket_bot/executor.py` → `OrderExecutor._execute_signal()`
- **历史记录**: `polymarket_bot/executor.py` → `VirtualPositionManager._record_trade_history()`

### 关键逻辑

#### 1. 滑点计算（executor.py:343-350）
```python
# 添加随机滑点 (0% - 1%)
slippage = random.uniform(0.0, 0.01)

# 应用滑点：买入时价格上涨，卖出时价格下跌
if signal.side == "BUY":
    execution_price_with_slippage = execution_price * (1 + slippage)
else:  # SELL
    execution_price_with_slippage = execution_price * (1 - slippage)
```

#### 2. 交易历史记录（executor.py:125-178）
```python
def remove_position(self, token_id: str, size: float = None,
                   exit_price: float = None, slippage: float = 0.0):
    # 计算持仓时间
    holding_time_seconds = (exit_time - entry_time).total_seconds()

    # 计算盈亏
    pnl = (exit_price - entry_price) * trade_size
    pnl_pct = (exit_price - entry_price) / entry_price

    # 记录到 CSV
    self._record_trade_history(
        token_id=token_id,
        entry_price=entry_price,
        exit_price=exit_price,
        size=trade_size,
        holding_time_seconds=holding_time_seconds,
        pnl=pnl,
        pnl_pct=pnl_pct,
        slippage=slippage
    )
```

## 注意事项

1. **文件位置**: `trade_history.csv` 和 `virtual_positions.json` 都存储在项目根目录
2. **自动创建**: 首次运行时会自动创建 CSV 文件并写入表头
3. **追加模式**: 后续交易会追加到文件末尾，不会覆盖历史记录
4. **仅限 DRY_RUN**: 交易历史记录功能仅在 DRY_RUN 模式下工作
5. **精度**: 所有价格和金额都保留 6 位小数，确保精确记录

## 性能影响

- ✅ **最小化开销**: 只在 SELL 时写入一次 CSV（不是每次迭代）
- ✅ **无内存累积**: 直接写入磁盘，不占用内存
- ✅ **快速 I/O**: 使用 Python 内置 csv 模块，性能优秀
- ✅ **并发安全**: 每次操作独立打开/关闭文件

## 未来扩展建议

1. **可视化仪表板**: 使用 Plotly/Dash 创建实时交易监控面板
2. **策略对比**: 支持多策略并行测试，对比不同策略的表现
3. **回测报告**: 自动生成包含图表的 HTML 回测报告
4. **风险指标**: 添加 Sharpe Ratio、Max Drawdown 等风险指标
5. **导出格式**: 支持导出为 JSON、Parquet 等其他格式

## 示例输出

运行完整测试后的输出示例：

```
[DRY RUN] Would execute: BUY 10.0 of 111128... @ $0.5008 (market: $0.5000, slippage: 0.16%)
[VIRTUAL POSITION] Added: BUY 10.0 of 111128... @ $0.5008

[DRY RUN] Would execute: SELL 10.0 of 111128... @ $0.4963 (market: $0.5000, slippage: 0.74%)
[TRADE HISTORY] Recorded: 11112819158150546350... P&L: $-0.0451 (-0.90%)
[VIRTUAL POSITION] Removed: 111128... (sold 10.0 shares, P&L: $-0.05)
```

## 问题排查

### CSV 文件为空
- 确认已经执行过 SELL 订单（BUY 不会记录）
- 检查日志是否有 `[TRADE HISTORY] Recorded` 消息

### 数据不准确
- 确认滑点计算正确：BUY 增加价格，SELL 减少价格
- 检查持仓时间：entry_time 是否正确记录

### 无法在 Excel 打开
- 确认文件编码为 UTF-8
- 如果 Token ID 过长，Excel 可能显示为科学计数法（这是正常的）
