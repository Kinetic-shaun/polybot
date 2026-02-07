# Polymarket 模仿策略研究总结

## 1. 数据来源

### 可用的 API
| API | 端点 | 用途 |
|-----|------|------|
| Gamma API | `gamma-api.polymarket.com/events` | 市场列表、价格 |
| Data API | `data-api.polymarket.com/trades` | 交易历史 |
| Tickers | `gamma-api.polymarket.com/tickers` | 行情数据 |

### Up/Down 合约结构
```
市场 (Market)
├── outcome: "Yes" (UP) / "No" (DOWN)
├── outcomePrices: [price_yes, price_no]
└── 价格关系: YES + NO ≈ 1.00

交易 (Trade)
├── side: "BUY" / "SELL"
├── outcome: "Yes" / "No"
├── price: 0-1 (概率)
└── size: 仓位金额
```

## 2. 交易人分析 (0x6031b6...f96d)

### 行为模式
| 维度 | 特征 |
|------|------|
| 交易风格 | 高频剥头皮 (200笔/17分钟) |
| 价格偏好 | 40-60% 区间 (约40%交易) |
| 仓位规模 | $10-30 |
| 交易间隔 | 平均5秒/笔 |
| 市场专注 | BTC/ETH Up or Down (100%) |
| 活跃时段 | UTC 21:00-23:00 |

### 价格分布
```
<20%:   32% ██████  (抄底偏好)
20-40%: 15% ██
40-60%: 10% █
60-80%: 13% ██
80-100%:30% ██████ (追高偏好)
```

## 3. 模仿策略规则

### 入场条件
- 价格进入 40-60% 区间时入场
- 标的为 Bitcoin/Ethereum Up or Down
- 仓位控制在 $10-$30
- UTC 21-23点 操作

### 出场条件
- 止盈: 10% 或 5分钟内
- 止损: 15% 立即平仓

### 风控
- 单日最大亏损: $100
- 总暴露不超过: $500
- 不加仓、不补仓

## 4. 工具脚本

### monitor_prices.py
```bash
# 启动监控
python monitor_prices.py --interval 30 --duration 60

# 查看状态
python monitor_prices.py --status
```

### backtest.py
```bash
# 分析交易人模式
python backtest.py --trader 0x6031b6... --days 7

# 策略模拟
python backtest.py --min-entry 0.40 --max-entry 0.60 --position 20
```

### mimic_strategy.py
```bash
# 分析模式
python mimic_strategy.py --mode analyze

# 模拟交易
python mimic_strategy.py --mode paper

# 生成配置
python mimic_strategy.py --mode config
```

## 5. 建议执行方式

### 方式一：直接跟单
```bash
python run_bot.py copy \
  --target-user 0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d \
  --copy-amount 10 \
  --max-copy-size 50 \
  --time-window 180
```

### 方式二：监控信号（推荐进阶）
1. 部署 `monitor_prices.py` 持续采集数据
2. 使用 `backtest.py` 验证策略
3. 根据信号手动执行

## 6. 注意事项

1. **数据延迟**: Gamma API 有约30秒延迟
2. **滑点影响**: 高频交易需注意
3. **手续费**: Polymarket 收取约1%手续费
4. **结算时间**: 某些市场结算较慢

## 7. 下一步

- [ ] 收集更多历史数据进行回测
- [ ] 测试不同价格区间策略
- [ ] 添加止盈止损自动化
- [ ] 集成到主 bot
