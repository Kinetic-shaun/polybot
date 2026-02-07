#!/usr/bin/env python3
"""
Polymarket 数据来源调研

探索:
1. Up/Down 合约的价格来源
2. Gamma API 数据结构
3. 历史K线/价格数据获取
"""

import requests
from datetime import datetime
from collections import defaultdict

DATA_API = "https://data-api.polymarket.com/trades"
GAMMA_API = "https://gamma-api.polymarket.com/events"


def explore_trades_api():
    print("=" * 70)
    print("1. 交易数据 API (data-api.polymarket.com/trades)")
    print("=" * 70)

    params = {"user": "0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d", "limit": 5}
    response = requests.get(DATA_API, params=params, timeout=15)
    data = response.json()
    trades = data.get('data', []) if isinstance(data, dict) else data

    if trades:
        trade = trades[0]
        print(f"\n交易字段 ({len(trade)}个):")
        for key in sorted(trade.keys()):
            print(f"  {key}")

        print(f"\n【Up/Down 关键字段】")
        print(f"  side: {trade.get('side')} (BUY/SELL)")
        print(f"  outcome: {trade.get('outcome')} (YES/NO)")
        print(f"  price: {trade.get('price')}")
        print(f"  size: {trade.get('size')}")


def explore_gamma_api():
    print("\n" + "=" * 70)
    print("2. Gamma Events API")
    print("=" * 70)

    params = {"limit": 5, "active": "true"}
    response = requests.get(GAMMA_API, params=params, timeout=15)
    markets = response.json()

    print(f"\n响应: list, {len(markets)} 个市场")
    if markets:
        m = markets[0]
        print(f"\n字段: {list(m.keys())}")
        if 'tokens' in m and m['tokens']:
            t = m['tokens'][0]
            print(f"\nToken字段: {list(t.keys())}")
            print(f"  symbol: {t.get('symbol')}")
            print(f"  outcome: {t.get('outcome')}")
            print(f"  price: {t.get('price')}")


def analyze_up_down():
    print("\n" + "=" * 70)
    print("3. Up/Down 合约分析")
    print("=" * 70)

    params = {"user": "0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d", "limit": 100}
    response = requests.get(DATA_API, params=params, timeout=15)
    data = response.json()
    trades = data.get('data', []) if isinstance(data, dict) else data

    outcomes = defaultdict(int)
    sides = defaultdict(int)
    prices = []

    for t in trades:
        outcomes[t.get('outcome', 'N/A')] += 1
        sides[t.get('side', 'N/A')] += 1
        if t.get('price'):
            prices.append(float(t.get('price')))

    print(f"\nOutcome分布:")
    for k, v in sorted(outcomes.items()):
        print(f"  {k}: {v} ({v/len(trades)*100:.1f}%)")

    print(f"\nSide分布:")
    for k, v in sorted(sides.items()):
        print(f"  {k}: {v} ({v/len(trades)*100:.1f}%)")

    if prices:
        print(f"\n价格统计:")
        print(f"  范围: {min(prices):.4f} - {max(prices):.4f}")


def data_source_summary():
    print("\n" + "=" * 70)
    print("Polymarket 数据来源总结")
    print("=" * 70)

    summary = """
Up/Down 价格关系:
  • YES价格 + NO价格 ≈ 1.00
  • YES = 事件发生概率
  • NO = 1 - YES

API数据流:
  Gamma API (/events) ──▶ 市场+价格 ──▶ 本地存储

回测数据方案:
  1. 自己采集: python monitor_prices.py
  2. 社区数据: polymarket-data (GitHub)
  3. 付费API: CCData

数据字段:
  • timestamp  - 时间戳
  • market_id - 市场ID
  • outcome   - YES/NO
  • price     - 价格 (0-1)
"""
    print(summary)


def main():
    print("\n" + "#" * 70)
    print("#" + "    Polymarket 数据来源调研".center(68) + "#")
    print("#" * 70)

    explore_trades_api()
    explore_gamma_api()
    analyze_up_down()
    data_source_summary()

    print("\n" + "=" * 70)
    print("调研完成!")
    print("使用 monitor_prices.py 采集历史数据")
    print("=" * 70)


if __name__ == "__main__":
    main()
