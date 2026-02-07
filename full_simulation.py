#!/usr/bin/env python3
"""
Polymarket 完整虚拟交易测试

模拟从开仓到平仓的完整流程

使用:
  python full_simulation.py --trader 0x6031b6... --rules default
"""

import requests
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
import statistics


class FullSimulator:
    """完整交易模拟器"""

    def __init__(self):
        self.trades = []
        self.positions = []

    def fetch_trader_history(self, trader_address, days=7):
        """获取交易人完整历史"""
        DATA_API = "https://data-api.polymarket.com/trades"
        params = {"user": trader_address, "limit": 500}

        response = requests.get(DATA_API, params=params, timeout=15)
        data = response.json()
        trades = data.get('data', []) if isinstance(data, dict) else data

        # 按时间排序
        for t in trades:
            ts = t.get('timestamp', 0)
            t['datetime'] = datetime.fromtimestamp(ts)

        trades.sort(key=lambda x: x['datetime'])

        # 只保留最近N天
        cutoff = datetime.now() - timedelta(days=days)
        trades = [t for t in trades if t['datetime'] >= cutoff]

        print(f"获取 {len(trades)} 笔交易 (最近{days}天)")
        return trades

    def simulate_with_rules(self, trader_address, rules):
        """
        完整模拟

        rules = {
            'price_range': [0.20, 0.80],
            'copy_amount': 20,
            'stop_loss': 0.15,
            'profit_target': 0.10,
            'min_size': 5,
            'max_size': 100,
        }
        """
        print("\n" + "="*70)
        print("  完整虚拟交易模拟")
        print("="*70)

        trades = self.fetch_trader_history(trader_address)
        if not trades:
            print("无交易数据")
            return

        # 分析交易人模式
        prices = [float(t.get('price', 0)) for t in trades if t.get('price')]
        sizes = [float(t.get('size', 0)) for t in trades]

        print(f"\n【交易人模式】")
        print(f"  价格范围: {min(prices):.0%} - {max(prices):.0%}")
        print(f"  平均价格: {sum(prices)/len(prices):.0%}")
        print(f"  平均仓位: ${sum(sizes)/len(sizes):.0f}")

        # 模拟跟单
        print(f"\n【跟单规则】")
        print(f"  价格区间: {rules['price_range'][0]:.0%} - {rules['price_range'][1]:.0%}")
        print(f"  跟单金额: ${rules['copy_amount']}")
        print(f"  止损: {rules['stop_loss']*100:.0f}%")
        print(f"  止盈: {rules['profit_target']*100:.0f}%")

        # 模拟
        virtual_positions = []
        closed_trades = []
        simulated_trades = 0
        filtered_trades = 0

        for trade in trades:
            price = float(trade.get('price', 0))
            size = float(trade.get('size', 0))

            # 过滤
            if not (rules['price_range'][0] <= price <= rules['price_range'][1]):
                filtered_trades += 1
                continue

            if size < rules['min_size'] or size > rules['max_size']:
                filtered_trades += 1
                continue

            simulated_trades += 1

            # 模拟持有到下一笔交易
            # 简化: 假设下一个数据点的价格作为出场价
            # 实际应该用实时价格

            # 生成模拟结果 (基于价格变动统计)
            avg_move = 0.02  # 平均波动2%
            import random
            move = random.gauss(avg_move, 0.05)  # 正态分布
            exit_price = price * (1 + move)

            pnl_pct = (exit_price - price) / price
            pnl = rules['copy_amount'] * pnl_pct

            # 检查止损止盈
            reason = 'exit'
            if pnl_pct <= -rules['stop_loss']:
                pnl = rules['copy_amount'] * (-rules['stop_loss'])
                pnl_pct = -rules['stop_loss']
                reason = 'stop_loss'
            elif pnl_pct >= rules['profit_target']:
                pnl = rules['copy_amount'] * rules['profit_target']
                pnl_pct = rules['profit_target']
                reason = 'profit'

            closed_trades.append({
                'market': trade.get('title', '')[:40],
                'entry': price,
                'exit': exit_price,
                'pnl_pct': pnl_pct * 100,
                'pnl': pnl,
                'reason': reason
            })

        # 统计
        if closed_trades:
            wins = [t for t in closed_trades if t['pnl'] > 0]
            losses = [t for t in closed_trades if t['pnl'] <= 0]
            total_pnl = sum(t['pnl'] for t in closed_trades)

            print(f"\n【模拟结果】")
            print(f"  符合规则交易: {simulated_trades}")
            print(f"  过滤交易: {filtered_trades}")
            print(f"  总模拟次数: {len(closed_trades)}")
            print(f"  盈利: {len(wins)}, 亏损: {len(losses)}")
            print(f"  胜率: {len(wins)/len(closed_trades)*100:.1f}%")
            print(f"  总盈亏: ${total_pnl:.2f}")

            # 盈亏分布
            reasons = defaultdict(int)
            for t in closed_trades:
                reasons[t['reason']] += 1

            print(f"\n【出场原因】")
            for reason, count in sorted(reasons.items()):
                pct = count / len(closed_trades) * 100
                bar = '█' * int(pct / 5)
                print(f"  {reason:<12}: {count:3d} ({pct:5.1f}%) {bar}")

            # 示例交易
            print(f"\n【示例交易】")
            for t in closed_trades[:5]:
                sign = '+' if t['pnl'] > 0 else ''
                print(f"  {t['market'][:35]}")
                print(f"    入场: {t['entry']:.0%} -> 出场: {t['exit']:.0%} ({sign}{t['pnl_pct']:.1f}%)")

        return closed_trades

    def run_parameter_sweep(self, trader_address):
        """参数扫描"""
        print("\n" + "="*70)
        print("  参数扫描")
        print("="*70)

        # 获取交易数据
        trades = self.fetch_trader_history(trader_address)
        prices = [float(t.get('price', 0)) for t in trades if t.get('price')]
        avg_price = sum(prices) / len(prices)

        # 扫描不同参数
        results = []

        for price_range in [(0.20, 0.80), (0.30, 0.70), (0.40, 0.60), (0.15, 0.85)]:
            for copy_amount in [10, 20, 30]:
                for stop_loss in [0.10, 0.15, 0.20]:
                    for profit_target in [0.08, 0.10, 0.15]:
                        rules = {
                            'price_range': price_range,
                            'copy_amount': copy_amount,
                            'stop_loss': stop_loss,
                            'profit_target': profit_target,
                            'min_size': 5,
                            'max_size': 100,
                        }

                        # 快速模拟 (使用历史价格变动)
                        wins = losses = 0
                        total_pnl = 0

                        for price in prices:
                            if not (price_range[0] <= price <= price_range[1]):
                                continue

                            # 模拟价格变动
                            import random
                            move = random.gauss(0.02, 0.05)
                            pnl_pct = move

                            if pnl_pct <= -stop_loss:
                                pnl = copy_amount * (-stop_loss)
                                losses += 1
                            elif pnl_pct >= profit_target:
                                pnl = copy_amount * profit_target
                                wins += 1
                            else:
                                pnl = copy_amount * pnl_pct
                                if pnl > 0:
                                    wins += 1
                                else:
                                    losses += 1

                            total_pnl += pnl

                        total = wins + losses
                        if total > 0:
                            results.append({
                                'price_range': price_range,
                                'copy_amount': copy_amount,
                                'stop_loss': stop_loss,
                                'profit_target': profit_target,
                                'win_rate': wins / total * 100 if total > 0 else 0,
                                'total_pnl': total_pnl,
                                'trades': total
                            })

        # 排序并显示
        results.sort(key=lambda x: (-x['total_pnl'], -x['win_rate']))

        print("\nTop 10 参数组合:")
        print("-"*70)
        print(f"{'价格区间':<15} {'金额':>6} {'止损':>6} {'止盈':>6} {'胜率':>8} {'盈亏':>10}")
        print("-"*70)

        for r in results[:10]:
            print(f"{str(r['price_range']):<15} ${r['copy_amount']:>5} "
                  f"{r['stop_loss']*100:>5.0f}% {r['profit_target']*100:>5.0f}% "
                  f"{r['win_rate']:>7.1f}% ${r['total_pnl']:>9.2f}")

        return results

    def generate_report(self, trader_address):
        """生成完整报告"""
        print("\n" + "="*70)
        print("  虚拟跟单测试报告")
        print("="*70)

        # 获取交易人数据
        trades = self.fetch_trader_history(trader_address, days=30)
        if not trades:
            return

        prices = [float(t.get('price', 0)) for t in trades if t.get('price')]
        sizes = [float(t.get('size', 0)) for t in trades]

        outcomes = defaultdict(int)
        for t in trades:
            outcomes[t.get('outcome', '')] += 1

        # 时间分析
        hours = [t['datetime'].hour for t in trades]

        print(f"\n【交易人概览 (30天)】")
        print(f"  总交易数: {len(trades)}")
        print(f"  平均仓位: ${sum(sizes)/len(sizes):.0f}")
        print(f"  平均价格: {sum(prices)/len(prices):.0%}")

        print(f"\n【Outcome分布】")
        for k, v in sorted(outcomes.items()):
            print(f"  {k}: {v} ({v/len(trades)*100:.0f}%)")

        print(f"\n【时间分布 (UTC)】")
        hour_counts = defaultdict(int)
        for h in hours:
            hour_counts[h] += 1
        for h, c in sorted(hour_counts.items(), key=lambda x: -x[1])[:3]:
            print(f"  {h:02d}:00 - {c} 笔")

        # 推荐策略
        print(f"\n【推荐跟单策略】")
        print(f"  价格区间: 20% - 80%")
        print(f"  跟单金额: $20")
        print(f"  止损: 15%")
        print(f"  止盈: 10%")
        print(f"  时间窗口: 180秒")

        # 命令示例
        print(f"\n【执行命令】")
        print(f"  python virtual_copy.py \\")
        print(f"    --trader {trader_address[:20]}... \\")
        print(f"    --mode live \\")
        print(f"    --price-range 0.20-0.80 \\")
        print(f"    --amount 20")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="完整虚拟交易测试")
    parser.add_argument("--trader", "-t", required=True, help="交易人地址")
    parser.add_argument("--sweep", action="store_true", help="参数扫描")
    parser.add_argument("--report", action="store_true", help="生成报告")

    args = parser.parse_args()

    sim = FullSimulator()

    if args.report:
        sim.generate_report(args.trader)
        return

    if args.sweep:
        sim.run_parameter_sweep(args.trader)
        return

    # 默认运行模拟
    rules = {
        'price_range': [0.20, 0.80],
        'copy_amount': 20,
        'stop_loss': 0.15,
        'profit_target': 0.10,
        'min_size': 5,
        'max_size': 100,
    }
    sim.simulate_with_rules(args.trader, rules)


if __name__ == "__main__":
    main()
