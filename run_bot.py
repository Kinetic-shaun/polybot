#!/usr/bin/env python3
"""
Simple bot runner - no interactive prompts
支持多种策略：simple、momentum、copy_trading
增强的持续运行模式，带实时状态显示
"""
from dotenv import load_dotenv
from polymarket_bot.config import BotConfig
from polymarket_bot.strategy import ExampleMomentumStrategy, CopyTradingStrategy, BaseStrategy, Signal
from polymarket_bot.bot import PolymarketBot
from typing import List, Dict, Any
import sys
import time
from datetime import datetime


class SimpleStrategy(BaseStrategy):
    """
    A very simple example strategy for demonstration

    This strategy:
    - Looks for markets with price < 0.3 (undervalued)
    - Buys a small position
    - Sells when price reaches 0.5 or higher
    - Supports virtual balance for dry-run testing
    - Quick sell on ±1% price change for fast closed-loop testing
    """

    def __init__(self, buy_threshold: float = 0.3, sell_threshold: float = 0.5, enable_quick_test: bool = False):
        super().__init__("simple")
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.enable_quick_test = enable_quick_test  # 快速闭环测试开关

    def generate_signals(
        self,
        markets: List[Dict[str, Any]],
        positions: List[Dict[str, Any]],
        balance: float,
    ) -> List[Signal]:
        """Generate buy/sell signals with virtual balance support"""
        signals = []

        # 注入虚拟余额：如果真实余额为0，使用1000作为虚拟余额进行判断
        effective_balance = balance if balance > 0 else 1000.0
        if balance == 0:
            self.logger.info(f"Using virtual balance: ${effective_balance:.2f} for signal generation")

        # Create a map of current positions for easy lookup
        position_map = {p.get("token_id"): p for p in positions}

        for market in markets:
            # Skip closed markets or markets not accepting orders
            if market.get("closed", False) or not market.get("accepting_orders", False):
                continue

            # Get the YES token (usually index 0)
            tokens = market.get("tokens", [])
            if not tokens:
                continue

            token = tokens[0]
            token_id = token.get("token_id")
            current_price = float(token.get("price", 0))

            # 跳过价格为0的无效市场
            if current_price <= 0:
                continue

            # Check if we have a position in this market
            if token_id in position_map:
                position = position_map[token_id]
                size = float(position.get("size", 0))
                entry_price = float(position.get("average_price", 0))

                # 快速闭环测试：价格波动超过±1%就卖出
                if self.enable_quick_test and entry_price > 0:
                    price_change_pct = (current_price - entry_price) / entry_price
                    if abs(price_change_pct) >= 0.01:  # ±1% 波动
                        signals.append(Signal(
                            token_id=token_id,
                            side="SELL",
                            size=size,
                            reason=f"Quick test: price changed {price_change_pct:.2%} (entry: {entry_price:.3f} -> now: {current_price:.3f})"
                        ))
                        continue  # 已经生成卖出信号，跳过后续判断

                # 原有的常规卖出逻辑
                if current_price >= self.sell_threshold:
                    signals.append(Signal(
                        token_id=token_id,
                        side="SELL",
                        size=size,
                        reason=f"Price reached sell threshold: {current_price:.3f} >= {self.sell_threshold:.3f}"
                    ))
            else:
                # We don't own this - check if we should buy
                # 使用有效余额（真实或虚拟）进行判断，解除买入限制
                if current_price < self.buy_threshold and effective_balance >= 10.0:
                    buy_size = min(10.0, effective_balance * 0.1)  # 买入10美元或有效余额的10%
                    signals.append(Signal(
                        token_id=token_id,
                        side="BUY",
                        size=buy_size,
                        reason=f"Price below buy threshold: {current_price:.3f} < {self.buy_threshold:.3f} (effective balance: ${effective_balance:.2f})"
                    ))

        return signals


def print_strategy_help():
    """打印策略帮助信息"""
    print("""
========================================
    POLYMARKET BOT - 策略选择
========================================

可用策略:
  simple       - 简单低买高卖策略
                参数: buy_threshold(默认0.3), sell_threshold(默认0.5)

  momentum     - 动量策略（价格快速上涨时买入）
                参数: momentum_threshold(默认0.1), target_profit(默认0.15)

  copy         - 自动跟单策略（推荐）
                追踪并复制目标用户的交易
                参数:
                  target_user: 目标用户地址
                  copy_amount: 固定跟单金额（默认$10）
                  copy_ratio: 跟单比例（可选，如0.5表示50%复制）
                  time_window: 时间窗口秒数（默认300秒）
                  max_copy_size: 最大跟单金额（默认$100）

使用示例:
  # 简单策略，单次运行
  python run_bot.py simple

  # 动量策略，连续运行
  python run_bot.py momentum continuous

  # 跟单策略，使用默认设置
  python run_bot.py copy

  # 跟单策略，自定义参数
  python run_bot.py copy --target-user 0x... --copy-amount 20 --time-window 600

  # 查看策略状态
  python run_bot.py copy status

========================================
    """)


def run_continuous_with_status(bot: PolymarketBot, poll_interval: int = 60):
    """
    增强的持续运行模式，带实时状态显示

    特点：
    - 清晰的运行状态头部
    - 实时收益显示
    - 新交易通知
    - 简洁的循环状态
    - 支持 Ctrl+C 优雅停止
    """
    print("\n" + "=" * 70)
    print("  🤖 自动跟单机器人运行中 (按 Ctrl+C 停止)")
    print("=" * 70)
    print()

    start_time = time.time()
    iteration = 0

    # 初始状态
    print(f"  📋 初始持仓数量: {len(bot.position_manager.get_positions())}")
    print()

    try:
        while bot.running:  # 检查停止标志
            iteration += 1
            loop_start = time.time()

            # 打印循环头部
            print(f"\n{'─' * 70}")
            now_str = datetime.now().strftime('%H:%M:%S')
            print(f"  #{iteration} | {now_str} | 等待API响应...")
            print(f"{'─' * 70}")

            try:
                # 执行一次迭代（带超时保护）
                bot._run_iteration_with_timeout(timeout=20)

                # 打印持仓状态
                print()
                bot.position_manager.print_summary()

                # 打印交易统计
                pnl = bot.position_manager.get_total_pnl()
                elapsed = time.time() - start_time
                runs_per_minute = iteration / (elapsed / 60) if elapsed > 60 else iteration

                print(f"{'─' * 70}")
                print(f"  📊 统计:")
                print(f"     运行时间: {format_duration(elapsed)}")
                print(f"     执行次数: {iteration}")
                if elapsed > 60:
                    print(f"     运行时速: {runs_per_minute:.1f} 次/分钟")
                print(f"     💰 总利润: ${pnl['total_pnl']:.4f} ({pnl['total_pnl_pct']:.2%})")
                if abs(pnl['unrealized_pnl']) > 0.001:
                    unrealized_sign = '+' if pnl['unrealized_pnl'] > 0 else ''
                    print(f"     📈 未实现: {unrealized_sign}${pnl['unrealized_pnl']:.4f}")
                print(f"{'─' * 70}")

                # 检查是否需要等待（可中断的等待）
                loop_time = time.time() - loop_start
                if loop_time < poll_interval and bot.running:
                    sleep_time = poll_interval - loop_time
                    print(f"  ⏳ 等待 {int(sleep_time)} 秒后继续监控...")
                    # 使用可中断的等待
                    for _ in range(int(sleep_time)):
                        if not bot.running:
                            break
                        time.sleep(1)

            except Exception as e:
                print(f"\n  ❌ 迭代 #{iteration} 出错: {e}")
                print("  10 秒后重试...")
                # 可中断的重试等待
                for _ in range(10):
                    if not bot.running:
                        break
                    time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n" + "=" * 70)
        print("  🛑 用户停止运行")
        print("=" * 70)

        # 打印最终状态
        elapsed = time.time() - start_time
        pnl = bot.position_manager.get_total_pnl()

        print(f"\n  📈 最终统计:")
        print(f"     总运行时长: {format_duration(elapsed)}")
        print(f"     迭代次数: {iteration}")
        print(f"     💰 总利润: ${pnl['total_pnl']:.4f} ({pnl['total_pnl_pct']:.2%})")
        print(f"     📈 未实现利润: ${pnl['unrealized_pnl']:.4f}")
        print()

        bot.stop()


def format_duration(seconds: float) -> str:
    """格式化时长"""
    if seconds < 60:
        return f"{int(seconds)}秒"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}分{secs}秒"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}时{mins}分"


def parse_strategy_args(args: List[str]) -> Dict[str, Any]:
    """解析策略参数"""
    params = {}

    i = 0
    while i < len(args):
        arg = args[i]

        if arg.startswith('--'):
            # 将连字符转换为下划线 (time-window -> time_window)
            key = arg[2:].replace('-', '_')
            value = args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith('--') else None

            if value:
                # 尝试转换为数字
                try:
                    if '.' in value:
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    pass  # 保持字符串
                params[key] = value
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1

    return params


def main():
    """Main function"""

    # Load environment variables from .env file
    load_dotenv()

    print("=" * 60)
    print("POLYMARKET BOT FRAMEWORK")
    print("=" * 60)

    # 检查命令行参数
    if len(sys.argv) < 2:
        print("\n用法:")
        print("  python run_bot.py simple [once|continuous]")
        print("  python run_bot.py momentum [once|continuous]")
        print("  python run_bot.py copy [once|continuous|status]")
        print("  python run_bot.py help")
        print()
        return

    command = sys.argv[1].lower()

    # 帮助命令
    if command == "help":
        print("\n用法:")
        print("  python run_bot.py simple [once|continuous]")
        print("  python run_bot.py momentum [once|continuous]")
        print("  python run_bot.py copy [once|continuous|status]")
        print("\n市场分析请使用:")
        print("  python analyze_market.py --help")
        print()
        return

    # Load configuration (for strategy commands)
    config = BotConfig.from_env()

    print(f"\nConfiguration:")
    print(f"  Dry Run: {config.dry_run}")
    print(f"  Poll Interval: {config.poll_interval}s")
    print(f"  Max Position Size: ${config.max_position_size}")
    print(f"  Max Total Exposure: ${config.max_total_exposure}")

    # 检查命令行参数
    if len(sys.argv) < 2:
        print_strategy_help()
        return

    strategy_choice = sys.argv[1].lower()
    run_mode = "once"  # 默认单次运行
    extra_args = []

    # 解析其他参数
    for i, arg in enumerate(sys.argv[2:]):
        if arg in ['once', 'continuous', 'status']:
            run_mode = arg
        elif arg.startswith('--'):
            extra_args.append(arg)
        elif sys.argv[2 + i - 1] == 'status':
            pass
        else:
            extra_args.append(arg)

    # 解析额外参数
    strategy_params = parse_strategy_args(extra_args)

    # 创建策略
    strategy = None

    if strategy_choice == "copy":
        # 自动跟单策略
        target_user = strategy_params.get('target_user')
        copy_amount = strategy_params.get('copy_amount', 10.0)
        copy_ratio = strategy_params.get('copy_ratio')
        time_window = strategy_params.get('time_window', 300)
        max_copy_size = strategy_params.get('max_copy_size', 100.0)
        allow_dca = strategy_params.get('allow_dca', False)

        strategy = CopyTradingStrategy(
            target_user=target_user,
            copy_amount=copy_amount,
            copy_ratio=copy_ratio,
            time_window=time_window,
            max_copy_size=max_copy_size,
            allow_dca=allow_dca,
        )
        print(f"\n使用: Copy Trading 策略 (自动跟单)")
        print(f"  目标用户: {strategy.target_user[:10]}...{strategy.target_user[-6:]}")
        print(f"  跟单金额: ${copy_amount}")
        if copy_ratio:
            print(f"  跟单比例: {copy_ratio:.1%}")
        print(f"  DCA 加仓: {'开启' if allow_dca else '关闭'}")
        print(f"  最大仓位: ${max_copy_size}")
        print(f"  时间窗口: {time_window}s")
        print(f"  最大跟单金额: ${max_copy_size}")

        # 如果是 status 模式，打印状态并退出
        if run_mode == "status":
            status = strategy.get_status()
            print("\n" + "=" * 40)
            print("策略状态:")
            print("=" * 40)
            for key, value in status.items():
                print(f"  {key}: {value}")
            print("=" * 40)
            return

    elif strategy_choice == "momentum":
        # 动量策略
        momentum_threshold = strategy_params.get('momentum_threshold', 0.1)
        target_profit = strategy_params.get('target_profit', 0.15)

        strategy = ExampleMomentumStrategy(
            momentum_threshold=momentum_threshold,
            target_profit=target_profit,
            max_position_per_market=50.0
        )
        print(f"\n使用: Momentum Strategy (动量策略)")
        print(f"  动量阈值: {momentum_threshold:.1%}")
        print(f"  止盈目标: {target_profit:.1%}")

    elif strategy_choice == "simple":
        # 简单策略
        buy_threshold = strategy_params.get('buy_threshold', 0.3)
        sell_threshold = strategy_params.get('sell_threshold', 0.5)

        strategy = SimpleStrategy(
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold
        )
        print(f"\n使用: Simple Strategy (简单策略)")
        print(f"  买入阈值: {buy_threshold:.1%}")
        print(f"  卖出阈值: {sell_threshold:.1%}")

    else:
        print(f"\n未知策略: {strategy_choice}")
        print_strategy_help()
        return

    print(f"\n运行模式: {run_mode}")
    print()

    # Create the bot
    bot = PolymarketBot(strategy, config)

    # Run based on mode
    if run_mode == "continuous":
        bot.running = True  # 设置运行标志为 True
        print("Starting continuous operation...")
        print("Press Ctrl+C to stop\n")
        # 使用增强的持续运行模式
        run_continuous_with_status(bot, config.poll_interval)
    elif run_mode == "status":
        pass  # 已在上面处理
    else:
        print("Running single iteration...\n")
        bot.run_once()  # Run once and exit

    print("\nDone!")


if __name__ == "__main__":
    print("""
Usage:
  python run_bot.py [strategy] [mode] [options]

Arguments:
  strategy: 'simple', 'momentum', or 'copy' (required)
  mode: 'once', 'continuous', or 'status' (default: once)

Copy Strategy Options:
  --target-user  地址    目标用户地址
  --copy-amount  金额    固定跟单金额（默认10）
  --copy-ratio   比例    跟单比例（如0.5表示50%）
  --time-window  秒数    时间窗口（默认300）
  --max-copy-size 金额   最大跟单金额（默认100）
  --allow-dca            开启 DCA 加仓模式（追加买入已持仓市场）

Examples:
  python run_bot.py                    # 显示帮助
  python run_bot.py simple             # 简单策略，单次运行
  python run_bot.py copy               # 跟单策略，单次运行
  python run_bot.py copy continuous    # 跟单策略，连续运行
  python run_bot.py copy status        # 查看跟单策略状态
  python run_bot.py copy --copy-amount 20    # 跟单金额$20
  python run_bot.py copy --copy-ratio 0.5    # 50%比例跟单
  python run_bot.py copy --time-window 600   # 10分钟内交易
  python run_bot.py copy --allow-dca         # 开启 DCA 加仓模式

Market Analysis:
  python analyze_market.py --help       # 查看分析命令帮助
    """)
    main()
