#!/usr/bin/env python3
"""Polymarket 价格监控器 - 采集历史数据"""

import requests
import sqlite3
import time
import argparse
import json
from datetime import datetime

GAMMA_API = "https://gamma-api.polymarket.com/events"

class PriceMonitor:
    def __init__(self, db_path="polymarket_prices.db", interval=30):
        self.db_path = db_path
        self.interval = interval
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS prices (
            timestamp INTEGER, market_id TEXT, outcome TEXT,
            price REAL, volume REAL,
            PRIMARY KEY (timestamp, market_id, outcome))''')
        c.execute('''CREATE TABLE IF NOT EXISTS markets (
            market_id TEXT PRIMARY KEY, name TEXT,
            category TEXT, volume REAL, created_at INTEGER)''')
        conn.commit()
        conn.close()

    def fetch_prices(self):
        try:
            params = {"active": "true", "limit": 100}
            response = requests.get(GAMMA_API, params=params, timeout=15)
            markets = response.json()

            ts = int(datetime.now().timestamp())
            data = []
            markets_data = []

            for m in markets:
                # 获取嵌套的market详情
                nested = m.get('markets', [])
                for nm in nested:
                    mid = nm.get('id')
                    name = nm.get('question', '')
                    category = m.get('category', '')

                    # 存储市场信息
                    markets_data.append((
                        mid, name, category,
                        float(nm.get('volume', 0) or 0),
                        ts
                    ))

                    # 获取价格 (outcomePrices是数组，与outcomes对应)
                    outcomes_raw = nm.get('outcomes', '[]')
                    prices_raw = nm.get('outcomePrices', '[]')

                    # 解析JSON格式
                    if isinstance(outcomes_raw, str):
                        try:
                            outcomes = json.loads(outcomes_raw)
                        except:
                            outcomes = []
                    else:
                        outcomes = outcomes_raw

                    if isinstance(prices_raw, str):
                        try:
                            prices = json.loads(prices_raw)
                        except:
                            prices = []
                    else:
                        prices = prices_raw

                    for i, outcome in enumerate(outcomes):
                        if i < len(prices):
                            try:
                                # 转换为浮点数
                                price_str = prices[i]
                                if isinstance(price_str, str):
                                    price = float(price_str)
                                else:
                                    price = float(price_str)

                                data.append((ts, mid, outcome, price,
                                            float(nm.get('volume', 0) or 0)))
                            except (ValueError, TypeError):
                                pass

            # 保存
            if data:
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.executemany(
                    'INSERT OR IGNORE INTO prices VALUES (?,?,?,?,?)', data)
                c.executemany(
                    'INSERT OR REPLACE INTO markets VALUES (?,?,?,?,?)',
                    markets_data)
                conn.commit()
                conn.close()

            return len(data)

        except Exception as e:
            print(f"Error: {e}")
            return 0

    def run(self, duration_minutes=None):
        print(f"监控启动: {self.db_path}, 间隔{self.interval}秒")
        start = datetime.now()
        count = 0
        try:
            while True:
                if duration_minutes:
                    if (datetime.now() - start).total_seconds() / 60 >= duration_minutes:
                        break
                n = self.fetch_prices()
                count += n
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {n} 价格点")
                time.sleep(self.interval)
        except KeyboardInterrupt:
            print(f"\n停止, 共采集{count}条价格数据")
        return count

    def show_status(self):
        """显示当前状态"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()

            # 价格点数
            c.execute("SELECT COUNT(*) FROM prices")
            price_count = c.fetchone()[0]

            # 市场数
            c.execute("SELECT COUNT(*) FROM markets")
            market_count = c.fetchone()[0]

            # 最新价格
            c.execute('''
                SELECT m.name, p.outcome, p.price, p.timestamp
                FROM prices p
                JOIN markets m ON p.market_id = m.market_id
                WHERE p.timestamp = (SELECT MAX(timestamp) FROM prices)
                LIMIT 5
            ''')

            print(f"\n{'='*60}")
            print("当前市场状态")
            print(f"{'='*60}")
            print(f"记录价格点: {price_count}")
            print(f"市场数: {market_count}")

            rows = c.fetchall()
            if rows:
                print(f"\n最新价格:")
                for name, outcome, price, ts in rows:
                    time_str = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
                    print(f"  [{time_str}] {name[:35]}")
                    print(f"    {outcome}: {price:.4f}")

            conn.close()

        except Exception as e:
            print(f"状态查询错误: {e}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Polymarket价格监控")
    p.add_argument("--interval", type=int, default=30, help="采样间隔(秒)")
    p.add_argument("--duration", type=float, default=None, help="运行时长(分钟)")
    p.add_argument("--output", default="polymarket_prices.db", help="数据库路径")
    p.add_argument("--status", action="store_true", help="显示当前状态")

    args = p.parse_args()

    monitor = PriceMonitor(args.output, args.interval)

    if args.status:
        monitor.show_status()
    else:
        monitor.run(args.duration)
