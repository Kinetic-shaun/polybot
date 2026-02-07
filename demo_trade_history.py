#!/usr/bin/env python3
"""
演示交易历史记录功能

此脚本演示完整的 BUY → SELL 流程和交易历史记录：
1. 第一次运行：执行 BUY 并记录虚拟持仓
2. 第二次运行：执行 SELL 并记录到 trade_history.csv
"""
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from polymarket_bot.config import BotConfig
from polymarket_bot.strategy import BaseStrategy, Signal
from polymarket_bot.bot import PolymarketBot
from typing import List, Dict, Any


class DemoStrategy(BaseStrategy):
    """
    演示策略 - 用于测试交易历史记录

    第一次运行：买入一个便宜的市场
    第二次运行：立即卖出（触发条件：有持仓即卖出）
    """

    def __init__(self):
        super().__init__("demo_strategy")
        self.force_sell = os.environ.get("FORCE_SELL", "false").lower() == "true"

    def generate_signals(
        self,
        markets: List[Dict[str, Any]],
        positions: List[Dict[str, Any]],
        balance: float,
    ) -> List[Signal]:
        signals = []

        # 使用虚拟余额
        effective_balance = balance if balance > 0 else 1000.0

        # 创建持仓映射
        position_map = {p.get("token_id"): p for p in positions}

        self.logger.info(f"=== Demo Strategy Status ===")
        self.logger.info(f"Force sell mode: {self.force_sell}")
        self.logger.info(f"Current positions: {len(positions)}")
        self.logger.info(f"Effective balance: ${effective_balance:.2f}")

        if self.force_sell and positions:
            # 第二次运行：强制卖出所有持仓
            self.logger.info("🔴 FORCE SELL MODE - Selling all positions")
            for pos in positions:
                token_id = pos.get("token_id")
                size = pos.get("size", 0)
                entry_price = pos.get("average_price", 0)

                signals.append(Signal(
                    token_id=token_id,
                    side="SELL",
                    size=size,
                    reason=f"[DEMO] Force sell (entry: ${entry_price:.4f})"
                ))
            return signals

        # 第一次运行：寻找买入机会
        if not positions and effective_balance >= 10.0:
            self.logger.info("🟢 BUY MODE - Looking for entry opportunity")
            for market in markets[:5]:  # 只检查前5个市场
                if market.get("closed", False):
                    continue

                tokens = market.get("tokens", [])
                if not tokens:
                    continue

                token = tokens[0]
                token_id = token.get("token_id")
                current_price = float(token.get("price", 0))

                # 买入价格 < 0.6 的市场
                if 0.2 < current_price < 0.6:
                    buy_size = 10.0
                    signals.append(Signal(
                        token_id=token_id,
                        side="BUY",
                        size=buy_size,
                        reason=f"[DEMO] Entry signal @ ${current_price:.4f}"
                    ))
                    self.logger.info(f"✅ Generated BUY signal: {buy_size} shares @ ${current_price:.4f}")
                    break  # 只买一个

        return signals


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("交易历史记录演示")
    print("=" * 70)

    # 加载配置
    load_dotenv()
    config = BotConfig.from_env()

    # 确保是 dry_run 模式
    if not config.dry_run:
        print("\n⚠️  必须在 DRY_RUN=true 模式下运行！")
        return

    # 检查当前状态
    has_positions = os.path.exists("virtual_positions.json")
    has_history = os.path.exists("trade_history.csv")

    print(f"\n当前状态:")
    print(f"  虚拟持仓文件: {'存在' if has_positions else '不存在'}")
    print(f"  交易历史文件: {'存在' if has_history else '不存在'}")

    if has_positions:
        with open("virtual_positions.json", "r") as f:
            vpos = json.load(f)
        print(f"  虚拟持仓数量: {len(vpos)}")

        if vpos:
            print(f"\n现有持仓:")
            for token_id, pos in vpos.items():
                print(f"  - Token: {token_id[:20]}...")
                print(f"    Size: {pos['size']}, Entry: ${pos['average_price']:.4f}")

    # 创建策略
    strategy = DemoStrategy()

    # 创建并运行机器人
    print(f"\n{'=' * 70}")
    print("开始执行...")
    print("=" * 70 + "\n")

    bot = PolymarketBot(strategy, config)
    bot.run_once()

    print("\n" + "=" * 70)
    print("执行完成！")
    print("=" * 70)

    # 显示结果
    if os.path.exists("virtual_positions.json"):
        with open("virtual_positions.json", "r") as f:
            vpos = json.load(f)
        print(f"\n虚拟持仓: {len(vpos)} 个")

        if vpos:
            for token_id, pos in vpos.items():
                print(f"  Token: {token_id}")
                print(f"    Size: {pos['size']}, Entry: ${pos['average_price']:.4f}")
                print(f"    入场时间: {pos['entry_time']}")
    else:
        print(f"\n虚拟持仓: 0 个")

    # 检查交易历史
    if os.path.exists("trade_history.csv"):
        with open("trade_history.csv", "r") as f:
            lines = f.readlines()

        trade_count = len(lines) - 1  # 减去表头
        print(f"\n交易历史: {trade_count} 条记录")

        if trade_count > 0:
            print(f"\n最近交易:")
            print(lines[0].strip())  # 表头
            for line in lines[-3:]:  # 最后3条记录
                if line.strip() and line != lines[0]:
                    print(line.strip())

    # 提示下一步
    print("\n" + "=" * 70)
    if has_positions and len(vpos) > 0:
        print("💡 下一步操作:")
        print("   运行: FORCE_SELL=true python demo_trade_history.py")
        print("   这将卖出所有持仓并记录到 trade_history.csv")
    elif not has_positions or len(vpos) == 0:
        print("💡 下一步操作:")
        print("   1. 首先运行: python demo_trade_history.py")
        print("      (这将执行一个 BUY 订单)")
        print("   2. 然后运行: FORCE_SELL=true python demo_trade_history.py")
        print("      (这将执行 SELL 并记录交易历史)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
