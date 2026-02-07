#!/usr/bin/env python3
"""
Polymarket 虚拟跟单测试系统

功能:
1. 模拟跟单交易人信号
2. 虚拟仓位管理
3. 实时盈亏跟踪
4. 跟单效果评估

使用:
  python virtual_copy.py --trader 0x6031b6... --mode test
  python virtual_copy.py --trader 0x6031b6... --mode live
  python virtual_copy.py --report
"""

import requests
import sqlite3
import argparse
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict
import statistics


class VirtualCopyTrader:
    """虚拟跟单交易器"""

    def __init__(self, db_path="virtual_positions.db"):
        self.db_path = db_path
        self.positions = {}  # 当前持仓
        self.closed_trades = []  # 已平仓交易
        self.pending_orders = []  # 待执行订单
        self.cash = 100.0  # 虚拟现金
        self.trader_address = None

        self.init_db()

    def init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # 持仓表
        c.execute('''CREATE TABLE IF NOT EXISTS positions (
            id TEXT PRIMARY KEY,
            market_id TEXT,
            market_name TEXT,
            outcome TEXT,
            entry_price REAL,
            quantity REAL,
            entry_time INTEGER,
            status TEXT
        )''')

        # 交易记录表
        c.execute('''CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY,
            market_id TEXT,
            market_name TEXT,
            outcome TEXT,
            side TEXT,
            price REAL,
            quantity REAL,
            pnl REAL,
            profit_pct REAL,
            entry_time INTEGER,
            exit_time INTEGER,
            duration_seconds INTEGER,
            reason TEXT
        )''')

        # 设置表
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')

        conn.commit()
        conn.close()

    def fetch_trader_trades(self, trader_address, limit=50):
        """获取交易人最新交易"""
        DATA_API = "https://data-api.polymarket.com/trades"
        params = {"user": trader_address, "limit": limit}

        try:
            response = requests.get(DATA_API, params=params, timeout=15)
            data = response.json()
            trades = data.get('data', []) if isinstance(data, dict) else data
            return trades
        except Exception as e:
            print(f"获取交易失败: {e}")
            return []

    def check_new_signals(self, trader_address, lookback_minutes=60):
        """检测新信号"""
        trades = self.fetch_trader_trades(trader_address, limit=20)

        if not trades:
            return []

        now = datetime.now()
        signals = []

        for trade in trades:
            ts = int(trade.get('timestamp', 0))
            trade_time = datetime.fromtimestamp(ts)

            # 只看最近N分钟的交易
            if (now - trade_time).total_seconds() > lookback_minutes * 60:
                continue

            # 排除已处理的交易
            trade_id = trade.get('transactionHash', str(ts))
            if self.is_trade_processed(trade_id):
                continue

            signals.append({
                'id': trade_id,
                'market_id': trade.get('conditionId'),
                'market_name': trade.get('title', ''),
                'outcome': trade.get('outcome'),  # Yes/No
                'side': trade.get('side'),  # BUY/SELL
                'price': float(trade.get('price', 0)),
                'size': float(trade.get('size', 0)),
                'timestamp': ts
            })

        return signals

    def is_trade_processed(self, trade_id):
        """检查交易是否已处理"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT 1 FROM trades WHERE id=?", (trade_id,))
        result = c.fetchone()
        conn.close()
        return result is not None

    def execute_order(self, signal, rules):
        """执行订单"""
        # 检查过滤条件
        if not self._pass_filters(signal, rules):
            return False

        # 计算跟单金额
        copy_amount = self._calculate_copy_amount(signal, rules)
        if copy_amount <= 0:
            return False

        # 简化: 假设总是开仓 BUY
        position_id = f"{signal['market_id']}_{signal['outcome']}"

        if position_id in self.positions:
            # 已持仓，更新或跳过
            existing = self.positions[position_id]
            if rules.get('allow_dca', False):
                # 加仓
                new_quantity = existing['quantity'] + copy_amount / signal['price']
                new_avg = (existing['entry_price'] * existing['quantity'] +
                          signal['price'] * copy_amount / signal['price']) / new_quantity
                self.positions[position_id].update({
                    'quantity': new_quantity,
                    'entry_price': new_avg,
                    'entry_time': signal['timestamp']
                })
            # 跳过
        else:
            # 新建持仓
            self.positions[position_id] = {
                'id': position_id,
                'market_id': signal['market_id'],
                'market_name': signal['market_name'][:50],
                'outcome': signal['outcome'],
                'entry_price': signal['price'],
                'quantity': copy_amount / signal['price'],
                'entry_time': signal['timestamp']
            }

            # 记录交易
            self._save_trade({
                'id': signal['id'],
                'market_id': signal['market_id'],
                'market_name': signal['market_name'],
                'outcome': signal['outcome'],
                'side': 'BUY',
                'price': signal['price'],
                'quantity': copy_amount / signal['price'],
                'pnl': 0,
                'profit_pct': 0,
                'entry_time': signal['timestamp'],
                'exit_time': None,
                'duration_seconds': 0,
                'reason': 'signal'
            })

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 开仓信号!")
            print(f"  市场: {signal['market_name'][:40]}")
            print(f"  方向: {signal['outcome']} @ {signal['price']:.2%}")
            print(f"  金额: ${copy_amount:.2f}")
            print(f"  数量: {copy_amount/signal['price']:.2f}")

        return True

    def _pass_filters(self, signal, rules):
        """通过过滤器检查"""
        # 价格过滤
        if 'price_range' in rules:
            low, high = rules['price_range']
            if not (low <= signal['price'] <= high):
                return False

        # 金额过滤
        if 'min_size' in rules and signal['size'] < rules['min_size']:
            return False
        if 'max_size' in rules and signal['size'] > rules['max_size']:
            return False

        # 关键词过滤
        if 'keywords' in rules and rules['keywords']:
            name = signal.get('market_name', '').lower()
            if not any(kw.lower() in name for kw in rules['keywords']):
                return False

        return True

    def _calculate_copy_amount(self, signal, rules):
        """计算跟单金额"""
        # 基于信号金额按比例
        if 'scale_factor' in rules:
            return signal['size'] * rules['scale_factor']

        # 固定金额
        if 'fixed_amount' in rules:
            return rules['fixed_amount']

        # 范围随机
        if 'min_amount' in rules and 'max_amount' in rules:
            return statistics.mean([rules['min_amount'], rules['max_amount']])

        return 20  # 默认

    def _save_trade(self, trade):
        """保存交易记录"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO trades
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (trade['id'], trade['market_id'], trade['market_name'],
             trade['outcome'], trade['side'], trade['price'],
             trade['quantity'], trade['pnl'], trade['profit_pct'],
             trade['entry_time'], trade['exit_time'],
             trade['duration_seconds'], trade['reason']))
        conn.commit()
        conn.close()

    def update_positions(self, current_prices, rules):
        """更新持仓 (检查止损/止盈)"""
        closed = []

        for pos_id, pos in list(self.positions.items()):
            # 获取当前价格
            if pos['market_id'] not in current_prices:
                continue

            market_prices = current_prices[pos['market_id']]
            current_price = market_prices.get(pos['outcome'], pos['entry_price'])

            # 计算盈亏
            pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']

            # 检查止损
            if 'stop_loss' in rules and pnl_pct <= -rules['stop_loss']:
                self._close_position(pos, current_price, pnl_pct, 'stop_loss')
                closed.append(pos_id)
                continue

            # 检查止盈
            if 'profit_target' in rules and pnl_pct >= rules['profit_target']:
                self._close_position(pos, current_price, pnl_pct, 'profit')
                closed.append(pos_id)
                continue

            # 检查时间到期
            if 'max_hold_hours' in rules:
                hold_time = datetime.now() - datetime.fromtimestamp(pos['entry_time'])
                if hold_time.total_seconds() > rules['max_hold_hours'] * 3600:
                    self._close_position(pos, current_price, pnl_pct, 'time_exit')
                    closed.append(pos_id)

        return closed

    def _close_position(self, pos, exit_price, pnl_pct, reason):
        """平仓"""
        pnl = pos['quantity'] * (exit_price - pos['entry_price']) * pos['quantity']

        # 更新交易记录
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''UPDATE trades SET
            exit_price=?, pnl=?, profit_pct=?, exit_time=?,
            duration_seconds=?, reason=?
            WHERE id=?''',
            (exit_price, pnl, pnl_pct * 100,
             int(datetime.now().timestamp()),
             int(datetime.now().timestamp()) - pos['entry_time'],
             reason, pos['id']))
        conn.commit()
        conn.close()

        # 记录
        sign = '+' if pnl >= 0 else ''
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 平仓 {reason}")
        print(f"  市场: {pos['market_name'][:40]}")
        print(f"  入场: {pos['entry_price']:.2%} -> 出场: {exit_price:.2%}")
        print(f"  盈亏: {sign}${pnl:.2f} ({sign}{pnl_pct*100:.1f}%)")

        self.closed_trades.append({
            **pos,
            'exit_price': exit_price,
            'pnl': pnl,
            'profit_pct': pnl_pct * 100
        })

    def run_test_mode(self, trader_address, rules, duration_minutes=60):
        """测试模式 - 回放历史信号"""
        print("\n" + "="*70)
        print("  虚拟跟单测试模式")
        print("="*70)

        self.trader_address = trader_address
        print(f"\n目标交易人: {trader_address[:20]}...")
        print(f"规则: {rules}")
        print(f"测试时长: {duration_minutes} 分钟")

        # 获取历史交易
        trades = self.fetch_trader_trades(trader_address, limit=100)

        if not trades:
            print("未找到交易数据")
            return

        # 按时间排序
        trades.sort(key=lambda x: x.get('timestamp', 0))

        # 只取最近的N笔
        recent_trades = trades[-50:]

        print(f"\n模拟 {len(recent_trades)} 笔历史交易...\n")

        # 模拟执行
        for trade in recent_trades:
            signal = {
                'id': trade.get('transactionHash', str(trade.get('timestamp'))),
                'market_id': trade.get('conditionId'),
                'market_name': trade.get('title', ''),
                'outcome': trade.get('outcome'),
                'side': trade.get('side'),
                'price': float(trade.get('price', 0)),
                'size': float(trade.get('size', 0)),
                'timestamp': trade.get('timestamp', 0)
            }

            if self._pass_filters(signal, rules):
                self.execute_order(signal, rules)

        # 汇总
        self.print_summary()

    def run_live_mode(self, trader_address, rules, duration_minutes=None):
        """实时模式 - 监控并跟单"""
        print("\n" + "="*70)
        print("  虚拟跟单实时模式")
        print("="*70)

        self.trader_address = trader_address
        print(f"\n目标交易人: {trader_address[:20]}...")
        print(f"规则: {rules}")

        print(f"\n开始监控信号 (Ctrl+C 停止)...")

        start_time = datetime.now()
        check_interval = rules.get('check_interval', 30)

        try:
            while True:
                if duration_minutes:
                    elapsed = (datetime.now() - start_time).total_seconds() / 60
                    if elapsed >= duration_minutes:
                        print(f"\n测试时间到，停止监控")
                        break

                # 检测新信号
                signals = self.check_new_signals(trader_address, lookback_minutes=60)

                if signals:
                    print(f"\n发现 {len(signals)} 个新信号")
                    for signal in signals:
                        self.execute_order(signal, rules)

                # 获取当前价格并更新持仓
                current_prices = self._fetch_current_prices()
                self.update_positions(current_prices, rules)

                # 状态报告
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 持仓: {len(self.positions)}, "
                      f"已平仓: {len(self.closed_trades)}")

                time.sleep(check_interval)

        except KeyboardInterrupt:
            print("\n\n手动停止监控")

        self.print_summary()

    def _fetch_current_prices(self):
        """获取当前价格"""
        prices = {}
        try:
            response = requests.get("https://gamma-api.polymarket.com/events",
                                   params={"active": "true", "limit": 100}, timeout=15)
            markets = response.json()

            for m in markets:
                nested = m.get('markets', [])
                for nm in nested:
                    mid = nm.get('id')
                    outcomes = nm.get('outcomes', [])
                    outcome_prices = nm.get('outcomePrices', [])

                    if isinstance(outcomes, str):
                        import json
                        try:
                            outcomes = json.loads(outcomes)
                            outcome_prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
                        except:
                            continue

                    prices[mid] = {}
                    for i, outcome in enumerate(outcomes):
                        if i < len(outcome_prices):
                            try:
                                prices[mid][outcome] = float(outcome_prices[i])
                            except:
                                pass

        except Exception as e:
            print(f"获取价格失败: {e}")

        return prices

    def print_summary(self):
        """打印汇总报告"""
        print("\n" + "="*70)
        print("  虚拟跟单汇总报告")
        print("="*70)

        if not self.closed_trades:
            print("\n暂无已平仓交易")
            return

        wins = [t for t in self.closed_trades if t.get('pnl', 0) > 0]
        losses = [t for t in self.closed_trades if t.get('pnl', 0) <= 0]
        total_pnl = sum(t.get('pnl', 0) for t in self.closed_trades)

        print(f"\n【交易统计】")
        print(f"  总交易数:    {len(self.closed_trades)}")
        print(f"  盈利:        {len(wins)}")
        print(f"  亏损:        {len(losses)}")
        print(f"  胜率:        {len(wins)/len(self.closed_trades)*100:.1f}%")

        print(f"\n【盈亏统计】")
        print(f"  总盈亏:      ${total_pnl:.2f}")
        if wins:
            print(f"  平均盈利:    ${sum(t['pnl'] for t in wins)/len(wins):.2f}")
        if losses:
            print(f"  平均亏损:    ${sum(t['pnl'] for t in losses)/len(losses):.2f}")

        print(f"\n【当前持仓】")
        print(f"  持仓数:      {len(self.positions)}")
        for pos_id, pos in self.positions.items():
            print(f"  - {pos['market_name'][:40]}: {pos['outcome']} @ {pos['entry_price']:.2%}")

    def reset(self):
        """重置所有数据"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM positions")
        c.execute("DELETE FROM trades")
        conn.commit()
        conn.close()
        self.positions = {}
        self.closed_trades = []
        print("数据已重置")


def main():
    parser = argparse.ArgumentParser(description="虚拟跟单测试")
    parser.add_argument("--trader", "-t", help="交易人地址")
    parser.add_argument("--mode", choices=["test", "live"], default="test",
                        help="模式: test-历史回放, live-实时监控")
    parser.add_argument("--duration", type=int, default=60, help="运行时长(分钟)")
    parser.add_argument("--report", action="store_true", help="显示报告")

    # 规则参数
    parser.add_argument("--price-range", type=str, default="0.20-0.80",
                        help="价格区间, 如 0.20-0.80")
    parser.add_argument("--min-size", type=float, default=5, help="最小信号金额")
    parser.add_argument("--max-size", type=float, default=100, help="最大信号金额")
    parser.add_argument("--stop-loss", type=float, default=0.15, help="止损比例")
    parser.add_argument("--profit-target", type=float, default=0.10, help="止盈比例")
    parser.add_argument("--amount", type=float, default=20, help="跟单金额")

    args = parser.parse_args()

    # 解析价格区间
    price_range = [float(x) for x in args.price_range.split('-')]

    rules = {
        'price_range': price_range,
        'min_size': args.min_size,
        'max_size': args.max_size,
        'stop_loss': args.stop_loss,
        'profit_target': args.profit_target,
        'fixed_amount': args.amount,
        'check_interval': 30,
        'max_hold_hours': 24,
        'allow_dca': False,
    }

    trader = VirtualCopyTrader()

    if args.report:
        trader.print_summary()
        return

    if not args.trader:
        print("请指定交易人地址: --trader 0x...")
        return

    if args.mode == "test":
        trader.run_test_mode(args.trader, rules, args.duration)
    else:
        trader.run_live_mode(args.trader, rules, args.duration)


if __name__ == "__main__":
    main()
