#!/usr/bin/env python3
"""
Polymarket 回测引擎

功能:
1. 使用采集的历史数据进行策略回测
2. 分析交易人模式
3. 生成回测报告

使用:
  python backtest.py --trader 0x6031b6...  # 分析交易人模式
  python backtest.py --days 7              # 回测所有数据
"""

import sqlite3
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
import statistics


class BacktestEngine:
    """回测引擎"""

    def __init__(self, db_path="polymarket_prices.db"):
        self.db_path = db_path
        self.data = {}

    def load_data(self, market_id=None, days=7):
        """加载历史数据"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        min_ts = int((datetime.now() - timedelta(days=days)).timestamp())

        if market_id:
            c.execute('''
                SELECT p.timestamp, p.market_id, m.name, p.outcome, p.price, p.volume
                FROM prices p
                JOIN markets m ON p.market_id = m.market_id
                WHERE p.market_id = ? AND p.timestamp > ?
                ORDER BY p.timestamp, p.market_id, p.outcome
            ''', (market_id, min_ts))
        else:
            c.execute('''
                SELECT p.timestamp, p.market_id, m.name, p.outcome, p.price, p.volume
                FROM prices p
                JOIN markets m ON p.market_id = m.market_id
                WHERE p.timestamp > ?
                ORDER BY p.timestamp, p.market_id, p.outcome
            ''', (min_ts,))

        rows = c.fetchall()
        conn.close()

        # 按市场分组
        self.data = defaultdict(list)
        for ts, mid, name, outcome, price, vol in rows:
            self.data[mid].append({
                'timestamp': ts,
                'name': name,
                'outcome': outcome,
                'price': price,
                'volume': vol
            })

        print(f"加载 {len(self.data)} 个市场, {sum(len(v) for v in self.data.values())} 条记录")
        return self.data

    def analyze_up_down_markets(self):
        """分析Up/Down市场"""
        print("\n" + "="*70)
        print("  Up/Down 市场分析")
        print("="*70)

        up_down_markets = []
        for mid, prices in self.data.items():
            name = prices[0]['name'].lower()
            # 更宽松的匹配条件
            if any(kw in name for kw in ['up or down', 'up/down', 'up or lower', 'higher']):
                up_down_markets.append({
                    'id': mid,
                    'name': prices[0]['name'][:50],
                    'samples': len(prices),
                    'avg_price': sum(p['price'] for p in prices) / len(prices)
                })

        # 也显示所有市场供查看
        print(f"\n所有市场 (前10):")
        for mid, prices in list(self.data.items())[:10]:
            name = prices[0]['name'][:45]
            avg = sum(p['price'] for p in prices) / len(prices)
            print(f"  {name}")
            print(f"    ID: {mid[:20]}... | 样本: {len(prices)} | 均价: {avg:.2%}")

        return up_down_markets

    def analyze_trader_patterns(self, trader_address):
        """分析交易人模式"""
        print("\n" + "="*70)
        print("  交易人模式分析")
        print("="*70)

        import requests
        DATA_API = "https://data-api.polymarket.com/trades"
        params = {"user": trader_address, "limit": 500}
        response = requests.get(DATA_API, params=params, timeout=15)
        data = response.json()
        trades = data.get('data', []) if isinstance(data, dict) else data

        if not trades:
            print("未找到交易数据")
            return

        prices = [float(t.get('price', 0)) for t in trades if t.get('price')]
        sizes = [float(t.get('size', 0)) for t in trades]

        # Outcome分布
        outcomes = defaultdict(int)
        for t in trades:
            outcomes[t.get('outcome', 'N/A')] += 1

        # 时间分析
        hours = []
        for t in trades:
            ts = t.get('timestamp')
            if ts:
                dt = datetime.fromtimestamp(int(ts))
                hours.append(dt.hour)

        hour_counts = defaultdict(int)
        for h in hours:
            hour_counts[h] += 1

        print(f"\n交易人 {trader_address[:20]}...")
        print(f"\n【价格分布】")
        print(f"  范围: {min(prices):.2%} - {max(prices):.2%}")
        print(f"  平均: {sum(prices)/len(prices):.2%}")
        print(f"  中位数: {sorted(prices)[len(prices)//2]:.2%}")

        print(f"\n【Outcome偏好】")
        for k, v in sorted(outcomes.items()):
            print(f"  {k}: {v} ({v/len(trades)*100:.0f}%)")

        print(f"\n【时间模式 (UTC)】")
        for h, c in sorted(hour_counts.items(), key=lambda x: -x[1])[:3]:
            print(f"  {h:02d}:00 - {c} 笔")

        # 价格区间统计
        buckets = {'<20%':0, '20-40%':0, '40-60%':0, '60-80%':0, '80-100%':0}
        for p in prices:
            if p < 0.2:
                buckets['<20%'] += 1
            elif p < 0.4:
                buckets['20-40%'] += 1
            elif p < 0.6:
                buckets['40-60%'] += 1
            elif p < 0.8:
                buckets['60-80%'] += 1
            else:
                buckets['80-100%'] += 1

        print(f"\n【价格区间】")
        for r, c in buckets.items():
            pct = c / len(prices) * 100
            bar = '█' * int(pct / 5)
            print(f"  {r:>10}: {c:3d} ({pct:5.1f}%) {bar}")

        # 生成建议
        avg_price = sum(prices) / len(prices)
        top_hours = sorted(hour_counts.items(), key=lambda x: -x[1])[:2]

        print(f"\n【建议规则】")
        print(f"  价格区间: {max(0, avg_price-0.15):.0%} - {min(1, avg_price+0.15):.0%}")
        print(f"  平均仓位: ${sum(sizes)/len(sizes):.0f}")
        print(f"  活跃时段: UTC {top_hours[0][0]:02d}:00")
        print(f"  建议止盈: 10%")
        print(f"  建议止损: 15%")

        return {
            'avg_price': avg_price,
            'price_range': [max(0, avg_price-0.15), min(1, avg_price+0.15)],
            'avg_size': sum(sizes)/len(sizes),
            'top_hours': [h for h, c in top_hours]
        }

    def simulate_strategy(self, rules):
        """模拟策略"""
        print("\n" + "="*70)
        print("  策略模拟")
        print("="*70)

        trades = []
        pnl_total = 0
        wins = losses = 0

        # 遍历所有市场
        for mid, prices in self.data.items():
            # 模拟入场信号
            for i, p in enumerate(prices):
                if rules['min_entry'] <= p['price'] <= rules['max_entry']:
                    entry_price = p['price']

                    # 模拟持有 (下一个数据点作为出场)
                    if i + 1 < len(prices):
                        exit_price = prices[i+1]['price']
                        pnl_pct = (exit_price - entry_price) / entry_price

                        if pnl_pct > 0:
                            wins += 1
                        else:
                            losses += 1

                        pnl = rules['position_size'] * pnl_pct
                        pnl_total += pnl

                        trades.append({
                            'market': p['name'][:30],
                            'entry': entry_price,
                            'exit': exit_price,
                            'pnl': pnl,
                            'pnl_pct': pnl_pct * 100
                        })

        print(f"\n【模拟结果】")
        print(f"  信号数: {len(trades)}")
        print(f"  盈利: {wins}, 亏损: {losses}")
        print(f"  胜率: {wins/max(len(trades),1)*100:.1f}%")
        print(f"  总盈亏: ${pnl_total:.2f}")

        # 显示部分交易
        if trades:
            print(f"\n【示例交易】")
            for t in trades[:3]:
                sign = '+' if t['pnl'] > 0 else ''
                print(f"  {t['market']}")
                print(f"    入场: {t['entry']:.2%} -> 出场: {t['exit']:.2%} ({sign}{t['pnl_pct']:.1f}%)")

        return trades


def main():
    parser = argparse.ArgumentParser(description="Polymarket回测引擎")
    parser.add_argument("--db", default="polymarket_prices.db", help="数据库路径")
    parser.add_argument("--days", type=int, default=7, help="回测天数")
    parser.add_argument("--trader", "-t", help="交易人地址")
    parser.add_argument("--min-entry", type=float, default=0.40, help="最小入场价")
    parser.add_argument("--max-entry", type=float, default=0.60, help="最大入场价")
    parser.add_argument("--position", type=float, default=20, help="仓位大小")

    args = parser.parse_args()

    engine = BacktestEngine(args.db)
    engine.load_data(days=args.days)

    # 分析Up/Down市场
    engine.analyze_up_down_markets()

    # 分析交易人
    if args.trader:
        rules = engine.analyze_trader_patterns(args.trader)

    # 策略模拟
    if args.trader:
        print("\n使用分析结果模拟策略...")
        rules = {
            'min_entry': args.min_entry,
            'max_entry': args.max_entry,
            'position_size': args.position,
        }
        engine.simulate_strategy(rules)

    print("\n" + "="*70)


if __name__ == "__main__":
    main()
