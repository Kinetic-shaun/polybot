#!/usr/bin/env python3
"""
Polymarket 高级回测系统

功能:
1. 多策略参数回测
2. 策略优化 (网格搜索)
3. 详细统计分析
4. 可视化报告

使用:
  python advanced_backtest.py --days 7 --trades 100
  python advanced_backtest.py --optimize
  python advanced_backtest.py --report
"""

import sqlite3
import json
import argparse
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
from itertools import product
import statistics


class AdvancedBacktest:
    """高级回测引擎"""

    def __init__(self, db_path="polymarket_prices.db"):
        self.db_path = db_path
        self.data = {}
        self.trades = []

    def load_data(self, days=7, min_samples=5):
        """加载历史数据"""
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

        # 按市场分组，保留时间序列
        self.data = defaultdict(list)
        for ts, mid, name, outcome, price, vol in rows:
            self.data[mid].append({
                'timestamp': ts,
                'name': name,
                'outcome': outcome,
                'price': price,
                'volume': vol
            })

        # 过滤样本数
        self.data = {k: v for k, v in self.data.items() if len(v) >= min_samples}

        print(f"加载 {len(self.data)} 个市场, 总记录 {sum(len(v) for v in self.data.values())}")
        return self.data

    def run_backtest(self, rules):
        """
        运行回测

        rules = {
            'min_entry': 0.40,
            'max_entry': 0.60,
            'position_size': 20,
            'stop_loss': 0.15,
            'profit_target': 0.10,
            'min_hold_bars': 1,
            'max_hold_bars': 10,
            'filter_volume': True,
            'min_volume': 1000,
        }
        """
        trades = []
        pnl_list = []

        for mid, prices in self.data.items():
            if len(prices) < 2:
                continue

            # 过滤低成交量
            if rules.get('filter_volume', False):
                avg_vol = sum(p['volume'] for p in prices) / len(prices)
                if avg_vol < rules.get('min_volume', 1000):
                    continue

            # 遍历价格序列
            for i in range(len(prices) - rules['min_hold_bars']):
                entry = prices[i]

                # 入场条件
                if not (rules['min_entry'] <= entry['price'] <= rules['max_entry']):
                    continue

                # 模拟持有
                for j in range(i + rules['min_hold_bars'],
                              min(i + rules['max_hold_bars'] + 1, len(prices))):
                    exit_bar = prices[j]
                    pnl_pct = (exit_bar['price'] - entry['price']) / entry['price']

                    # 检查止盈止损
                    if rules.get('profit_target') and pnl_pct >= rules['profit_target']:
                        # 止盈
                        pnl = rules['position_size'] * pnl_pct
                        trades.append({
                            'market': entry['name'][:40],
                            'entry_price': entry['price'],
                            'exit_price': exit_bar['price'],
                            'pnl_pct': pnl_pct * 100,
                            'pnl': pnl,
                            'reason': 'profit',
                            'bars_held': j - i
                        })
                        pnl_list.append(pnl)
                        break
                    elif rules.get('stop_loss') and pnl_pct <= -rules['stop_loss']:
                        # 止损
                        pnl = rules['position_size'] * pnl_pct
                        trades.append({
                            'market': entry['name'][:40],
                            'entry_price': entry['price'],
                            'exit_price': exit_bar['price'],
                            'pnl_pct': pnl_pct * 100,
                            'pnl': pnl,
                            'reason': 'stop_loss',
                            'bars_held': j - i
                        })
                        pnl_list.append(pnl)
                        break
                else:
                    # 时间到期退出
                    exit_bar = prices[min(i + rules['max_hold_bars'], len(prices) - 1)]
                    pnl_pct = (exit_bar['price'] - entry['price']) / entry['price']
                    pnl = rules['position_size'] * pnl_pct
                    trades.append({
                        'market': entry['name'][:40],
                        'entry_price': entry['price'],
                        'exit_price': exit_bar['price'],
                        'pnl_pct': pnl_pct * 100,
                        'pnl': pnl,
                        'reason': 'time_exit',
                        'bars_held': rules['max_hold_bars']
                    })
                    pnl_list.append(pnl)

        return self._calculate_stats(trades, pnl_list)

    def _calculate_stats(self, trades, pnl_list):
        """计算统计数据"""
        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'avg_pnl': 0,
                'total_pnl': 0,
                'max_drawdown': 0,
                'profit_factor': 0,
                'sharpe_ratio': 0,
                'trades': []
            }

        wins = [p for p in pnl_list if p > 0]
        losses = [p for p in pnl_list if p <= 0]

        # 计算累计曲线
        cumulative = []
        total = 0
        for pnl in pnl_list:
            total += pnl
            cumulative.append(total)

        # 最大回撤
        max_dd = 0
        peak = 0
        for val in cumulative:
            if val > peak:
                peak = val
            dd = (peak - val) / max(peak, 1) * 100
            if dd > max_dd:
                max_dd = dd

        # 夏普比率 (简化)
        if np.std(pnl_list) > 0:
            sharpe = np.mean(pnl_list) / np.std(pnl_list) * np.sqrt(len(pnl_list))
        else:
            sharpe = 0

        return {
            'total_trades': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(trades) * 100 if trades else 0,
            'avg_win': sum(wins) / len(wins) if wins else 0,
            'avg_loss': sum(losses) / len(losses) if losses else 0,
            'total_pnl': sum(pnl_list),
            'max_drawdown': max_dd,
            'profit_factor': abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 0,
            'sharpe_ratio': sharpe,
            'avg_bars_held': statistics.mean([t['bars_held'] for t in trades]),
            'trades': trades[:100]  # 只保留前100个交易详情
        }

    def grid_search(self, param_grid):
        """
        网格搜索最优参数

        param_grid = {
            'min_entry': [0.30, 0.40, 0.50],
            'max_entry': [0.50, 0.60, 0.70],
            'stop_loss': [0.10, 0.15, 0.20],
            'profit_target': [0.08, 0.10, 0.15],
        }
        """
        print("\n" + "="*70)
        print("  网格搜索最优参数")
        print("="*70)

        results = []
        total = 1
        for v in param_grid.values():
            total *= len(v)

        print(f"将测试 {total} 种参数组合...\n")

        count = 0
        for params in product(*param_grid.values()):
            rules = dict(zip(param_grid.keys(), params))
            rules['position_size'] = 20  # 固定仓位
            rules['min_hold_bars'] = 1
            rules['max_hold_bars'] = 5

            stats = self.run_backtest(rules)
            results.append({
                'params': params,
                'win_rate': stats['win_rate'],
                'total_pnl': stats['total_pnl'],
                'profit_factor': stats['profit_factor'],
                'sharpe': stats['sharpe_ratio'],
                'trades': stats['total_trades']
            })
            count += 1

            if count % 20 == 0:
                print(f"进度: {count}/{total} ({count/total*100:.0f}%)")

        # 排序并显示最佳结果
        results.sort(key=lambda x: (-x['total_pnl'], -x['win_rate']))

        print(f"\nTop 5 参数组合:")
        print("-"*70)
        print(f"{'参数':<50} {'胜率':>8} {'盈亏':>10} {'夏普':>8}")
        print("-"*70)

        for r in results[:5]:
            params_str = str(r['params'])[:48]
            print(f"{params_str:<50} {r['win_rate']:>7.1f}% ${r['total_pnl']:>9.2f} {r['sharpe']:>7.2f}")

        return results

    def print_report(self, stats):
        """打印报告"""
        print("\n" + "="*70)
        print("  回测报告")
        print("="*70)

        print(f"\n【基本统计】")
        print(f"  总交易数:    {stats['total_trades']}")
        print(f"  盈利次数:    {stats['wins']}")
        print(f"  亏损次数:    {stats['losses']}")
        print(f"  胜率:        {stats['win_rate']:.1f}%")

        print(f"\n【盈亏统计】")
        print(f"  总盈亏:      ${stats['total_pnl']:.2f}")
        print(f"  平均盈利:    ${stats['avg_win']:.2f}")
        print(f"  平均亏损:    ${stats['avg_loss']:.2f}")
        print(f"  盈亏比:      {stats['profit_factor']:.2f}")

        print(f"\n【风险指标】")
        print(f"  最大回撤:    {stats['max_drawdown']:.2f}%")
        print(f"  夏普比率:    {stats['sharpe_ratio']:.2f}")

        print(f"\n【持仓统计】")
        print(f"  平均持仓:    {stats['avg_bars_held']:.1f} 根K线")

        # 交易分布
        if stats['trades']:
            reasons = defaultdict(int)
            for t in stats['trades']:
                reasons[t['reason']] += 1

            print(f"\n【出场原因分布】")
            for reason, count in sorted(reasons.items()):
                pct = count / len(stats['trades']) * 100
                bar = '█' * int(pct / 5)
                print(f"  {reason:<15}: {count:3d} ({pct:5.1f}%) {bar}")

    def monte_carlo_simulation(self, stats, simulations=1000):
        """蒙特卡洛模拟"""
        print("\n" + "="*70)
        print("  蒙特卡洛模拟")
        print("="*70)

        if not stats['trades']:
            print("无交易数据")
            return

        pnl_array = np.array([t['pnl'] for t in stats['trades']])

        results = []
        for _ in range(simulations):
            # 随机抽样
            sample = np.random.choice(pnl_array, size=len(pnl_array), replace=True)
            results.append(sum(sample))

        results = sorted(results)

        print(f"\n模拟 {simulations} 次结果:")
        print(f"  5% 分位数:   ${results[int(simulations*0.05)]:.2f} (最坏情况)")
        print(f"  25% 分位数:  ${results[int(simulations*0.25)]:.2f}")
        print(f"  50% 中位数:  ${results[int(simulations*0.50)]:.2f}")
        print(f"  75% 分位数:  ${results[int(simulations*0.75)]:.2f}")
        print(f"  95% 分位数:  ${results[int(simulations*0.95)]:.2f} (最好情况)")

        # 破产概率
        ruin = sum(1 for r in results if r < -100) / simulations * 100
        print(f"\n  破产概率 (<-$100): {ruin:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="高级回测系统")
    parser.add_argument("--db", default="polymarket_prices.db", help="数据库路径")
    parser.add_argument("--days", type=int, default=7, help="回测天数")
    parser.add_argument("--position", type=float, default=20, help="仓位大小")
    parser.add_argument("--optimize", action="store_true", help="运行优化")
    parser.add_argument("--monte-carlo", action="store_true", help="蒙特卡洛模拟")

    args = parser.parse_args()

    engine = AdvancedBacktest(args.db)
    engine.load_data(days=args.days)

    if args.optimize:
        # 网格搜索
        param_grid = {
            'min_entry': [0.30, 0.40, 0.50],
            'max_entry': [0.50, 0.60, 0.70],
            'stop_loss': [0.10, 0.15, 0.20],
            'profit_target': [0.08, 0.10, 0.15],
        }
        results = engine.grid_search(param_grid)

        # 用最佳参数运行回测
        best = results[0]
        rules = dict(zip(param_grid.keys(), best['params']))
        rules['position_size'] = args.position
        rules['min_hold_bars'] = 1
        rules['max_hold_bars'] = 5

        stats = engine.run_backtest(rules)
        engine.print_report(stats)

        if args.monte_carlo:
            engine.monte_carlo_simulation(stats)

    else:
        # 标准回测
        rules = {
            'min_entry': 0.40,
            'max_entry': 0.60,
            'position_size': args.position,
            'stop_loss': 0.15,
            'profit_target': 0.10,
            'min_hold_bars': 1,
            'max_hold_bars': 5,
            'filter_volume': True,
            'min_volume': 1000,
        }

        stats = engine.run_backtest(rules)
        engine.print_report(stats)

        if args.monte_carlo:
            engine.monte_carlo_simulation(stats)

    print("\n" + "="*70)


if __name__ == "__main__":
    main()
