#!/usr/bin/env python3
"""
Example script showing how to use the Polymarket bot framework
"""
from dotenv import load_dotenv
from polymarket_bot.config import BotConfig
from polymarket_bot.strategy import ExampleMomentumStrategy, BaseStrategy, Signal
from polymarket_bot.bot import PolymarketBot
from typing import List, Dict, Any


class SimpleStrategy(BaseStrategy):
    """
    A very simple example strategy for demonstration

    This strategy:
    - Looks for markets with price < 0.3 (undervalued)
    - Buys a small position
    - Sells when price reaches 0.5 or higher
    """

    def __init__(self, buy_threshold: float = 0.3, sell_threshold: float = 0.5):
        super().__init__("simple")
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def generate_signals(
        self,
        markets: List[Dict[str, Any]],
        positions: List[Dict[str, Any]],
        balance: float,
    ) -> List[Signal]:
        """Generate buy/sell signals"""
        signals = []

        # Create a map of current positions for easy lookup
        position_map = {p.get("token_id"): p for p in positions}

        for market in markets:
            # Skip closed markets
            if market.get("closed", False):
                continue

            # Get the YES token (usually index 0)
            tokens = market.get("tokens", [])
            if not tokens:
                continue

            token = tokens[0]
            token_id = token.get("token_id")
            current_price = float(token.get("price", 0))

            # Check if we have a position in this market
            if token_id in position_map:
                # We own this - check if we should sell
                if current_price >= self.sell_threshold:
                    position = position_map[token_id]
                    size = float(position.get("size", 0))

                    signals.append(Signal(
                        token_id=token_id,
                        side="SELL",
                        size=size,
                        reason=f"Price reached sell threshold: {current_price:.3f} >= {self.sell_threshold:.3f}"
                    ))
            else:
                # We don't own this - check if we should buy
                if current_price < self.buy_threshold and balance > 10:
                    signals.append(Signal(
                        token_id=token_id,
                        side="BUY",
                        size=10.0,  # Buy $10 worth
                        reason=f"Price below buy threshold: {current_price:.3f} < {self.buy_threshold:.3f}"
                    ))

        return signals


def main():
    """Main function - demonstrates different ways to use the bot"""

    # Load environment variables from .env file
    load_dotenv()

    # Create bot configuration from environment
    config = BotConfig.from_env()

    print("=" * 60)
    print("POLYMARKET BOT FRAMEWORK - EXAMPLE")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  Dry Run: {config.dry_run}")
    print(f"  Poll Interval: {config.poll_interval}s")
    print(f"  Max Position Size: ${config.max_position_size}")
    print(f"  Max Total Exposure: ${config.max_total_exposure}")
    print()

    # Choose which strategy to use
    print("Available strategies:")
    print("  1. Simple Strategy (buy low, sell high)")
    print("  2. Momentum Strategy (trend following)")
    print()

    choice = input("Select strategy (1 or 2, or press Enter for Simple): ").strip()

    if choice == "2":
        # Use momentum strategy
        strategy = ExampleMomentumStrategy(
            momentum_threshold=0.1,    # 10% price movement to trigger
            target_profit=0.15,        # Take profit at 15%
            max_position_per_market=50.0
        )
        print("\nUsing Momentum Strategy")
    else:
        # Use simple strategy
        strategy = SimpleStrategy(
            buy_threshold=0.3,   # Buy when price < 0.3
            sell_threshold=0.5   # Sell when price >= 0.5
        )
        print("\nUsing Simple Strategy")

    print()

    # Create the bot
    bot = PolymarketBot(strategy, config)

    # Ask user how to run
    print("Run modes:")
    print("  1. Single iteration (run once and exit)")
    print("  2. Continuous (keep running)")
    print()

    mode = input("Select run mode (1 or 2, or press Enter for single): ").strip()

    if mode == "2":
        print("\nStarting continuous operation...")
        print("Press Ctrl+C to stop\n")
        bot.run()  # Run continuously
    else:
        print("\nRunning single iteration...\n")
        bot.run_once()  # Run once and exit

    print("\nDone!")


if __name__ == "__main__":
    main()
