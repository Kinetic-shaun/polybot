#!/usr/bin/env python3
"""
闭环测试脚本 - 验证虚拟持仓记录功能

此脚本演示如何在 DRY_RUN 模式下实现完整的交易闭环：
1. 生成 BUY 信号并记录虚拟持仓
2. 下次运行时识别虚拟持仓
3. 价格波动触发 SELL 信号并清除虚拟持仓
"""
import os
from dotenv import load_dotenv
from polymarket_bot.config import BotConfig
from polymarket_bot.strategy import BaseStrategy, Signal
from polymarket_bot.bot import PolymarketBot
from typing import List, Dict, Any


class ClosedLoopTestStrategy(BaseStrategy):
    """
    闭环测试策略

    买入条件：价格 < 0.5 且无持仓
    卖出条件：持仓存在 且 价格变动 > ±0.5%（极敏感，用于快速测试）
    """

    def __init__(self):
        super().__init__("closed_loop_test")
        self.buy_threshold = 0.51  # 买入阈值（调整为 0.51，因为当前市场价格都是 0.5）
        self.sell_threshold_pct = 0.005  # 0.5% 价格波动就卖出

    def generate_signals(
        self,
        markets: List[Dict[str, Any]],
        positions: List[Dict[str, Any]],
        balance: float,
    ) -> List[Signal]:
        """生成闭环测试信号"""
        signals = []

        # 使用虚拟余额
        effective_balance = balance if balance > 0 else 1000.0
        if balance == 0:
            self.logger.info(f"[TEST] Using virtual balance: ${effective_balance:.2f}")

        # 创建持仓映射
        position_map = {p.get("token_id"): p for p in positions}

        # 统计持仓情况
        if positions:
            self.logger.info(f"[TEST] Found {len(positions)} existing positions")

        for market in markets:
            # 只处理未关闭的市场（暂时不检查 accepting_orders，因为当前无市场接受订单）
            if market.get("closed", False):
                continue

            tokens = market.get("tokens", [])
            if not tokens:
                continue

            token = tokens[0]
            token_id = token.get("token_id")
            current_price = float(token.get("price", 0))

            if current_price <= 0:
                continue

            # 检查是否已有持仓
            if token_id in position_map:
                position = position_map[token_id]
                entry_price = float(position.get("average_price", 0))
                size = float(position.get("size", 0))

                if entry_price > 0:
                    # 计算价格变动
                    price_change_pct = abs((current_price - entry_price) / entry_price)

                    if price_change_pct >= self.sell_threshold_pct:
                        # 触发卖出
                        signals.append(Signal(
                            token_id=token_id,
                            side="SELL",
                            size=size,
                            reason=f"[CLOSED LOOP TEST] Price changed {price_change_pct:.3%} (entry: ${entry_price:.4f} -> now: ${current_price:.4f})"
                        ))
                        self.logger.info(f"[TEST] Generated SELL signal for existing position")
            else:
                # 没有持仓 - 寻找买入机会
                if current_price < self.buy_threshold and effective_balance >= 5.0:
                    buy_size = 5.0  # 小额测试
                    signals.append(Signal(
                        token_id=token_id,
                        side="BUY",
                        size=buy_size,
                        reason=f"[CLOSED LOOP TEST] Price ${current_price:.4f} < ${self.buy_threshold:.4f}"
                    ))
                    self.logger.info(f"[TEST] Generated BUY signal for new position")

                    # 限制：每次只买一个（方便测试）
                    if len(signals) >= 1:
                        break

        return signals


def main():
    """主测试函数"""
    print("=" * 70)
    print("闭环测试 - 虚拟持仓记录系统")
    print("=" * 70)

    # 加载配置
    load_dotenv()
    config = BotConfig.from_env()

    # 确保是 dry_run 模式
    if not config.dry_run:
        print("\n⚠️  警告：必须在 DRY_RUN=true 模式下运行此测试！")
        print("请在 .env 文件中设置 DRY_RUN=true")
        return

    print(f"\n配置:")
    print(f"  模式: DRY RUN (虚拟交易)")
    print(f"  虚拟持仓文件: virtual_positions.json")

    # 检查虚拟持仓文件
    if os.path.exists("virtual_positions.json"):
        import json
        with open("virtual_positions.json", "r") as f:
            vpos = json.load(f)
        print(f"  现有虚拟持仓: {len(vpos)} 个")
        if vpos:
            print(f"  持仓列表:")
            for token_id, pos in vpos.items():
                print(f"    - {token_id[:20]}... @ ${pos['average_price']:.4f} x {pos['size']}")
    else:
        print(f"  现有虚拟持仓: 0 个（新建）")

    # 创建测试策略
    strategy = ClosedLoopTestStrategy()

    # 创建并运行机器人
    print(f"\n开始执行测试...")
    print("-" * 70)

    bot = PolymarketBot(strategy, config)
    bot.run_once()

    print("-" * 70)
    print("\n测试完成！")

    # 显示虚拟持仓状态
    if os.path.exists("virtual_positions.json"):
        import json
        with open("virtual_positions.json", "r") as f:
            vpos = json.load(f)
        print(f"\n最终虚拟持仓: {len(vpos)} 个")
        if vpos:
            print(f"持仓详情:")
            for token_id, pos in vpos.items():
                print(f"  - {token_id}")
                print(f"    数量: {pos['size']}")
                print(f"    平均价: ${pos['average_price']:.4f}")
                print(f"    入场时间: {pos['entry_time']}")

    print("\n" + "=" * 70)
    print("下次运行说明：")
    print("1. 再次运行此脚本，机器人将识别虚拟持仓")
    print("2. 如果市场价格变化 > 0.5%，将自动生成 SELL 信号")
    print("3. 执行 SELL 后，虚拟持仓将被清除")
    print("4. 实现完整的 BUY -> SELL 闭环测试")
    print("=" * 70)


if __name__ == "__main__":
    main()
