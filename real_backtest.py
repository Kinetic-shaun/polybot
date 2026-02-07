#!/usr/bin/env python3
"""
Polymarket 真实历史回测系统

使用真实的采集数据模拟跟单交易

功能:
1. 使用真实的历史价格数据
2. 保存完整的交易日志
3. 可视化盈亏分析

使用:
  python real_backtest.py --days 7
  python real_backtest.py --report
"""

import sqlite3
import json
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
import statistics


class RealBacktest:
    """真实历史回测"""

    def __init__(self, db_path="polymarket_prices.db"):
        self.db_path = db_path
        self.trades = []
        self.positions = {}
        self.logs = []

    def load_data(self, days=7):
        """加载真实历史数据"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        min_ts = int((datetime.now() - timedelta(days=days)).timestamp())

        c.execute('''
            SELECT p.timestamp, p.market_id, m.name, p.outcome, p.price, p.volume
            FROM prices p
            JOIN markets m ON p.market_id = m.market_id
            WHERE p.timestamp > ?
            ORDER BY p.timestamp
        ''', (min_ts,))

        rows = c.fetchall()
        conn.close()

        # 按市场分组，保留时间序列
        self.market_data = defaultdict(list)
        for ts, mid, name, outcome, price, vol in rows:
            self.market_data[mid].append({
                'timestamp': ts,
                'datetime': datetime.fromtimestamp(ts),
                'name': name,
                'outcome': outcome,
                'price': price,
                'volume': vol
            })

        # 过滤样本数
        self.market_data = {k: v for k, v in self.market_data.items() if len(v) >= 5}

        print(f"加载 {len(self.market_data)} 个市场")
        return self.market_data

    def run_backtest(self, rules):
        """
        使用真实数据进行回测

        rules = {
            'price_range': [0.20, 0.80],
            'position_size': 20,
            'stop_loss': 0.15,
            'profit_target': 0.10,
            'min_hold_bars': 1,
            'max_hold_bars': 10,
        }
        """
        print("\n" + "="*70)
        print("  真实历史回测")
        print("="*70)

        self.positions = {}
        self.closed_trades = []
        self.logs = []

        start_cash = 100.0
        cash = start_cash

        log_entry(f"开始回测, 初始资金: ${start_cash}")
        log_entry(f"规则: 价格{rules['price_range'][0]:.0%}-{rules['price_range'][1]:.0%}, "
                  f"仓位${rules['position_size']}, 止损{rules['stop_loss']*100:.0f}%, 止盈{rules['profit_target']*100:.0f}%")

        entry_count = 0
        for mid, prices in self.market_data.items():
            if len(prices) < 2:
                continue

            name = prices[0]['name'][:40]

            for i in range(len(prices) - 1):
                bar = prices[i]

                # 简化: 只开第一个outcome
                if bar['outcome'] != prices[0]['outcome']:
                    continue

                # 入场条件
                if rules['price_range'][0] <= bar['price'] <= rules['price_range'][1]:
                    # 检查是否已持仓
                    pos_id = f"{mid}"
                    if pos_id in self.positions:
                        continue

                    # 开仓
                    entry_price = bar['price']
                    quantity = rules['position_size'] / entry_price

                    self.positions[pos_id] = {
                        'market_id': mid,
                        'market_name': name,
                        'outcome': bar['outcome'],
                        'entry_price': entry_price,
                        'quantity': quantity,
                        'entry_time': bar['timestamp'],
                        'entry_bar': i
                    }

                    log_entry(f"[{bar['datetime'].strftime('%H:%M:%S')}] 开仓: {name}")
                    log_entry(f"  {bar['outcome']} @ {entry_price:.4f}, ${rules['position_size']}")
                    entry_count += 1

                # 检查持仓出场
                pos_id = f"{mid}"
                if pos_id in self.positions:
                    pos = self.positions[pos_id]
                    bars_held = i - pos['entry_bar']

                    if bars_held < rules['min_hold_bars']:
                        continue

                    # 检查止损止盈
                    current_price = bar['price']
                    pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
                    pnl = pos['quantity'] * (current_price - pos['entry_price']) * pos['quantity']

                    reason = 'time_exit'

                    if pnl_pct <= -rules['stop_loss']:
                        reason = 'stop_loss'
                        pnl = rules['position_size'] * (-rules['stop_loss'])
                        pnl_pct = -rules['stop_loss']
                    elif pnl_pct >= rules['profit_target']:
                        reason = 'profit'
                        pnl = rules['position_size'] * rules['profit_target']
                        pnl_pct = rules['profit_target']

                    # 平仓
                    del self.positions[pos_id]
                    self.closed_trades.append({
                        **pos,
                        'exit_price': current_price,
                        'exit_time': bar['timestamp'],
                        'exit_bar': i,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct * 100,
                        'reason': reason,
                        'bars_held': bars_held
                    })

                    cash += pnl

                    log_entry(f"[{bar['datetime'].strftime('%H:%M:%S')}] 平仓 ({reason})")
                    log_entry(f"  入场 {pos['entry_price']:.4f} -> 出场 {current_price:.4f}")
                    log_entry(f"  盈亏: ${pnl:.2f} ({pnl_pct*100:+.1f}%)")

        # 剩余持仓按最后价格平仓
        for pos_id, pos in self.positions.items():
            prices = self.market_data.get(pos['market_id'], [])
            if prices:
                last_price = prices[-1]['price']
                pnl_pct = (last_price - pos['entry_price']) / pos['entry_price']
                pnl = rules['position_size'] * pnl_pct

                self.closed_trades.append({
                    **pos,
                    'exit_price': last_price,
                    'exit_time': prices[-1]['timestamp'],
                    'pnl': pnl,
                    'pnl_pct': pnl_pct * 100,
                    'reason': 'end',
                    'bars_held': len(prices) - pos['entry_bar']
                })
                cash += pnl

        log_entry(f"回测结束, 最终资金: ${cash:.2f}")
        log_entry(f"总交易: {len(self.closed_trades)}, 开仓次数: {entry_count}")

        return self.closed_trades, cash

    def print_report(self, final_cash=100.0):
        """打印报告"""
        if not self.closed_trades:
            print("\n无交易记录")
            return

        wins = [t for t in self.closed_trades if t.get('pnl', 0) > 0]
        losses = [t for t in self.closed_trades if t.get('pnl', 0) <= 0]
        total_pnl = sum(t.get('pnl', 0) for t in self.closed_trades)

        print(f"\n【回测结果】")
        print(f"  初始资金: ${final_cash:.2f}")
        print(f"  最终资金: ${final_cash + total_pnl:.2f}")
        print(f"  总盈亏: ${total_pnl:.2f} ({total_pnl/final_cash*100:+.2f}%)")

        print(f"\n【交易统计】")
        print(f"  总交易数: {len(self.closed_trades)}")
        print(f"  盈利: {len(wins)}, 亏损: {len(losses)}")
        print(f"  胜率: {len(wins)/len(self.closed_trades)*100:.1f}%")

        if wins:
            print(f"\n【盈利统计】")
            print(f"  平均盈利: ${sum(t['pnl'] for t in wins)/len(wins):.2f}")
            print(f"  最大盈利: ${max(t['pnl'] for t in wins):.2f}")

        if losses:
            print(f"\n【亏损统计】")
            print(f"  平均亏损: ${sum(t['pnl'] for t in losses)/len(losses):.2f}")
            print(f"  最大亏损: ${min(t['pnl'] for t in losses):.2f}")

        # 出场分布
        reasons = defaultdict(int)
        for t in self.closed_trades:
            reasons[t['reason']] += 1

        print(f"\n【出场原因】")
        for reason, count in sorted(reasons.items()):
            pct = count / len(self.closed_trades) * 100
            bar = '█' * int(pct / 5)
            print(f"  {reason:<12}: {count:3d} ({pct:5.1f}%) {bar}")

        # 盈亏曲线
        cumulative = 0
        curve = []
        for t in self.closed_trades:
            cumulative += t.get('pnl', 0)
            curve.append(cumulative)

        print(f"\n【盈亏曲线】")
        if curve:
            max_dd = 0
            peak = 0
            for val in curve:
                if val > peak:
                    peak = val
                dd = peak - val
                if dd > max_dd:
                    max_dd = dd
            print(f"  最大回撤: ${max_dd:.2f}")

        return {
            'total_pnl': total_pnl,
            'win_rate': len(wins) / len(self.closed_trades) * 100,
            'max_drawdown': max_dd if 'max_dd' in dir() else 0
        }

    def save_logs(self, filename="backtest_log.txt"):
        """保存日志"""
        with open(filename, 'w') as f:
            f.write('\n'.join(self.logs))
        print(f"\n日志已保存: {filename}")

    def save_trades(self, filename="backtest_trades.json"):
        """保存交易记录"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'total_trades': len(self.closed_trades),
            'total_pnl': sum(t.get('pnl', 0) for t in self.closed_trades),
            'trades': self.closed_trades
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"交易记录已保存: {filename}")


def log_entry(message):
    """日志条目"""
    print(message)
    import sys
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="真实历史回测")
    parser.add_argument("--db", default="polymarket_prices.db", help="数据库路径")
    parser.add_argument("--days", type=int, default=7, help="回测天数")
    parser.add_argument("--report", action="store_true", help="显示报告")
    parser.add_argument("--save", action="store_true", help="保存日志")

    # 参数
    parser.add_argument("--min-entry", type=float, default=0.20)
    parser.add_argument("--max-entry", type=float, default=0.80)
    parser.add_argument("--position", type=float, default=20)
    parser.add_argument("--stop-loss", type=float, default=0.15)
    parser.add_argument("--profit-target", type=float, default=0.10)

    args = parser.parse_args()

    backtest = RealBacktest(args.db)
    backtest.load_data(days=args.days)

    rules = {
        'price_range': [args.min_entry, args.max_entry],
        'position_size': args.position,
        'stop_loss': args.stop_loss,
        'profit_target': args.profit_target,
        'min_hold_bars': 1,
        'max_hold_bars': 10,
    }

    trades, final_cash = backtest.run_backtest(rules)

    if args.report:
        backtest.print_report(100.0)

    if args.save:
        backtest.save_logs()
        backtest.save_trades()


if __name__ == "__main__":
    main()
