#!/usr/bin/env python3
"""
Polymarket 策略优化器

专门针对交易人模式进行策略优化

使用:
  python optimizer.py --trader 0x6031b6...
"""

import requests
import sqlite3
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
from itertools import product
import statistics


class TraderStrategyOptimizer:
    """交易人策略优化器"""

    def __init__(self, db_path="polymarket_prices.db"):
        self.db_path = db_path
        self.trader_data = None

    def load_trader_data(self, trader_address, limit=500):
        """加载交易人历史数据"""
        DATA_API = "https://data-api.polymarket.com/trades"
        params = {"user": trader_address, "limit": limit}

        response = requests.get(DATA_API, params=params, timeout=15)
        data = response.json()
        trades = data.get('data', []) if isinstance(data, dict) else data

        if not trades:
            print("未找到交易数据")
            return None

        # 分析交易人模式
        prices = [float(t.get('price', 0)) for t in trades if t.get('price')]
        sizes = [float(t.get('size', 0)) for t in trades]

        outcomes = defaultdict(int)
        for t in trades:
            outcomes[t.get('outcome', 'N/A')] += 1

        # 时间分析
        hours = []
        for t in trades:
            ts = t.get('timestamp')
            if ts:
                hours.append(datetime.fromtimestamp(int(ts)).hour)

        hour_counts = defaultdict(int)
        for h in hours:
            hour_counts[h] += 1

        self.trader_data = {
            'prices': prices,
            'sizes': sizes,
            'outcomes': dict(outcomes),
            'hour_counts': dict(hour_counts),
            'avg_price': sum(prices) / len(prices),
            'avg_size': sum(sizes) / len(sizes),
            'price_range': (min(prices), max(prices)),
        }

        return self.trader_data

    def load_market_data(self, days=7):
        """加载市场数据"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        min_ts = int((datetime.now() - timedelta(days=days)).timestamp())

        c.execute('''
            SELECT p.timestamp, p.market_id, m.name, p.outcome, p.price, p.volume
            FROM prices p
            JOIN markets m ON p.market_id = m.market_id
            WHERE p.timestamp > ?
            ORDER BY p.timestamp, p.market_id
        ''', (min_ts,))

        rows = c.fetchall()
        conn.close()

        self.market_data = defaultdict(list)
        for ts, mid, name, outcome, price, vol in rows:
            self.market_data[mid].append({
                'timestamp': ts,
                'name': name,
                'outcome': outcome,
                'price': price,
                'volume': vol
            })

        self.market_data = {k: v for k, v in self.market_data.items() if len(v) >= 3}
        print(f"加载 {len(self.market_data)} 个市场")
        return self.market_data

    def analyze_trader_style(self):
        """分析交易人风格"""
        if not self.trader_data:
            return

        data = self.trader_data

        print("\n" + "="*70)
        print("  交易人风格分析")
        print("="*70)

        print(f"\n【价格偏好】")
        print(f"  平均入场价: {data['avg_price']:.2%}")
        print(f"  价格范围: {data['price_range'][0]:.2%} - {data['price_range'][1]:.2%}")

        # 价格区间分布
        buckets = {'<20%':0, '20-40%':0, '40-60%':0, '60-80%':0, '80-100%':0}
        for p in data['prices']:
            if p < 0.2: buckets['<20%'] += 1
            elif p < 0.4: buckets['20-40%'] += 1
            elif p < 0.6: buckets['40-60%'] += 1
            elif p < 0.8: buckets['60-80%'] += 1
            else: buckets['80-100%'] += 1

        print(f"\n【价格分布】")
        for r, c in buckets.items():
            pct = c / len(data['prices']) * 100
            bar = '█' * int(pct / 5)
            print(f"  {r:>10}: {c:3d} ({pct:5.1f}%) {bar}")

        print(f"\n【Outcome偏好】")
        for k, v in sorted(data['outcomes'].items()):
            print(f"  {k}: {v} ({v/len(data['prices'])*100:.0f}%)")

        print(f"\n【活跃时段 (UTC)】")
        for h, c in sorted(data['hour_counts'].items(), key=lambda x: -x[1])[:3]:
            print(f"  {h:02d}:00 - {c} 笔")

        print(f"\n【仓位统计】")
        print(f"  平均: ${data['avg_size']:.1f}")
        print(f"  范围: ${min(data['sizes']):.0f} - ${max(data['sizes']):.0f}")

    def suggest_parameters(self):
        """基于交易人风格建议参数"""
        if not self.trader_data:
            return

        data = self.trader_data
        avg_price = data['avg_price']

        # 基于价格分布建议
        price_std = statistics.stdev(data['prices']) if len(data['prices']) > 1 else 0.2

        print("\n" + "="*70)
        print("  建议参数")
        print("="*70)

        print(f"\n【入场参数】")
        min_entry = max(0, avg_price - price_std)
        max_entry = min(1, avg_price + price_std)
        print(f"  价格区间: {min_entry:.0%} - {max_entry:.0%}")
        print(f"  (基于均值±1标准差)")

        print(f"\n【仓位参数】")
        print(f"  建议仓位: ${data['avg_size']:.0f}")
        print(f"  范围: ${data['avg_size']*0.5:.0f} - ${data['avg_size']*1.5:.0f}")

        print(f"\n【时间参数】")
        top_hour = sorted(data['hour_counts'].items(), key=lambda x: -x[1])[0][0]
        print(f"  活跃时段: UTC {top_hour:02d}:00")

        return {
            'min_entry': min_entry,
            'max_entry': max_entry,
            'position_size': data['avg_size'],
            'stop_loss': 0.15,
            'profit_target': 0.10,
        }

    def backtest_with_trader_rules(self, rules):
        """使用交易人规则进行回测"""
        if not hasattr(self, 'market_data'):
            self.load_market_data()

        trades = []
        pnl_list = []

        for mid, prices in self.market_data.items():
            if len(prices) < 2:
                continue

            for i in range(len(prices) - 1):
                entry = prices[i]

                # 使用交易人风格的价格区间
                if not (rules['min_entry'] <= entry['price'] <= rules['max_entry']):
                    continue

                # 模拟持有
                exit_price = prices[i+1]['price']
                pnl_pct = (exit_price - entry['price']) / entry['price']
                pnl = rules['position_size'] * pnl_pct

                trades.append({
                    'market': entry['name'][:35],
                    'entry': entry['price'],
                    'exit': exit_price,
                    'pnl_pct': pnl_pct * 100,
                    'pnl': pnl
                })
                pnl_list.append(pnl)

        return self._calc_stats(trades, pnl_list)

    def _calc_stats(self, trades, pnl_list):
        """计算统计"""
        if not trades:
            return None

        wins = [p for p in pnl_list if p > 0]
        losses = [p for p in pnl_list if p <= 0]

        cumulative = []
        total = 0
        for pnl in pnl_list:
            total += pnl
            cumulative.append(total)

        max_dd = 0
        peak = 0
        for val in cumulative:
            if val > peak:
                peak = val
            dd = (peak - val) / max(peak, 1) * 100
            if dd > max_dd:
                max_dd = dd

        return {
            'total_trades': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(trades) * 100,
            'total_pnl': sum(pnl_list),
            'avg_pnl': sum(pnl_list) / len(pnl_list),
            'max_drawdown': max_dd,
            'profit_factor': abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 0,
        }

    def run_grid_search(self):
        """网格搜索"""
        if not self.trader_data:
            return

        data = self.trader_data
        avg_price = data['avg_price']
        price_std = statistics.stdev(data['prices']) if len(data['prices']) > 1 else 0.15

        print("\n" + "="*70)
        print("  网格搜索")
        print("="*70)

        # 基于交易人风格生成参数范围
        base_min = max(0, avg_price - price_std)
        base_max = min(1, avg_price + price_std)

        param_grid = {
            'min_entry': [base_min - 0.05, base_min, base_min + 0.05],
            'max_entry': [base_max - 0.05, base_max, base_max + 0.05],
            'position_size': [data['avg_size'] * 0.5, data['avg_size'], data['avg_size'] * 1.5],
        }

        results = []
        total = 1
        for v in param_grid.values():
            total *= len(v)

        print(f"测试 {total} 种参数组合...\n")

        for params in product(*param_grid.values()):
            rules = {
                'min_entry': max(0, params[0]),
                'max_entry': min(1, params[1]),
                'position_size': max(1, params[2]),
            }

            stats = self.backtest_with_trader_rules(rules)
            if stats and stats['total_trades'] > 10:
                results.append({
                    'params': rules,
                    'win_rate': stats['win_rate'],
                    'total_pnl': stats['total_pnl'],
                    'trades': stats['total_trades']
                })

        results.sort(key=lambda x: (-x['total_pnl'], -x['win_rate']))

        print("Top 5 结果:")
        print("-"*70)
        for r in results[:5]:
            p = r['params']
            print(f"  区间: {p['min_entry']:.0%}-{p['max_entry']:.0%} | "
                  f"仓位: ${p['position_size']:.0f} | "
                  f"胜率: {r['win_rate']:.1f}% | "
                  f"盈亏: ${r['total_pnl']:.2f}")

        return results


def main():
    parser = argparse.ArgumentParser(description="策略优化器")
    parser.add_argument("--trader", "-t", required=True, help="交易人地址")
    parser.add_argument("--db", default="polymarket_prices.db", help="数据库路径")
    parser.add_argument("--days", type=int, default=7, help="市场数据天数")

    args = parser.parse_args()

    optimizer = TraderStrategyOptimizer(args.db)

    # 加载交易人数据
    if not optimizer.load_trader_data(args.trader):
        return

    # 加载市场数据
    optimizer.load_market_data(days=args.days)

    # 分析
    optimizer.analyze_trader_style()
    optimizer.suggest_parameters()
    optimizer.run_grid_search()

    print("\n" + "="*70)


if __name__ == "__main__":
    main()
