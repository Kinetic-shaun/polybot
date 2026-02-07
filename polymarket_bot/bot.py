"""
Main bot runner
"""
import time
import signal
import sys
import threading
from typing import Optional
import logging

from .config import BotConfig
from .client import PolymarketClient
from .strategy import BaseStrategy
from .executor import OrderExecutor, PositionManager
from .utils import setup_logging, validate_config

logger = logging.getLogger(__name__)


class TimeoutException(Exception):
    """超时异常"""
    pass


def timeout_handler(signum, frame):
    """超时处理函数"""
    raise TimeoutException("Operation timed out")


class PolymarketBot:
    """
    Main bot orchestrator

    Coordinates strategy, execution, and position management
    """

    def __init__(self, strategy: BaseStrategy, config: BotConfig):
        """
        Initialize bot

        Args:
            strategy: Trading strategy instance
            config: Bot configuration
        """
        self.strategy = strategy
        self.config = config
        self.running = False

        # Validate configuration
        validate_config(config)

        # Setup logging
        setup_logging(config.log_level, config.log_file)

        # Initialize components
        self.client = PolymarketClient(
            api_key=config.api_key,
            api_secret=config.api_secret,
            api_passphrase=config.api_passphrase,
            private_key=config.private_key,
            chain_id=config.chain_id,
            signature_type=config.signature_type,
            funder=config.funder if config.funder else None,
        )
        self.executor = OrderExecutor(self.client, config)

        # Setup signal handlers for graceful shutdown BEFORE PositionManager
        # (PositionManager.__init__ calls get_balance() which can block)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # PositionManager 需要访问虚拟持仓管理器（如果存在）
        self.position_manager = PositionManager(self.client, self.executor.virtual_positions)

        logger.info(f"Bot initialized with strategy: {strategy.name}")
        if config.dry_run:
            logger.warning("Running in DRY RUN mode - no real trades will be executed")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals - 强制停止"""
        # 设置停止标志
        self.running = False
        # 同时停止策略
        if hasattr(self.strategy, 'running'):
            self.strategy.running = False
        logger.info("Shutdown signal received, stopping...")
        # 强制退出当前阻塞操作
        import threading
        for thread in threading.enumerate():
            if thread != threading.current_thread() and thread.daemon:
                # 设置守护线程的超时标志
                pass

    def run(self) -> None:
        """
        Run the bot main loop

        Continuously executes the strategy at configured intervals
        支持通过 Ctrl+C 优雅停止
        """
        logger.info("Starting bot...")
        self.running = True

        try:
            while self.running:
                # 每次循环开始时检查停止标志
                if not self.running:
                    break

                try:
                    self._run_iteration()
                except Exception as e:
                    logger.error(f"Error in bot iteration: {e}", exc_info=True)

                # 使用可中断的短睡眠，支持快速响应 Ctrl+C
                if self.running:
                    self._interruptible_sleep(self.config.poll_interval)

        except KeyboardInterrupt:
            # KeyboardInterrupt 也会触发这里，确保正确停止
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()

    def _interruptible_sleep(self, seconds: int):
        """
        可中断的睡眠，支持快速响应 Ctrl+C

        Args:
            seconds: 睡眠总时长（秒）
        """
        check_interval = 1  # 每 1 秒检查一次停止标志
        elapsed = 0

        while elapsed < seconds and self.running:
            time.sleep(check_interval)
            elapsed += check_interval

    def _run_iteration_with_timeout(self, timeout: float = 20) -> None:
        """
        带超时的迭代执行

        Args:
            timeout: 超时时间（秒）
        """
        result = [None]
        exception = [None]
        timed_out = [False]

        def run_iteration():
            try:
                self._run_iteration_impl()
                result[0] = "success"
            except Exception as e:
                exception[0] = e
                result[0] = "error"

        # 在单独线程中执行
        thread = threading.Thread(target=run_iteration)
        thread.daemon = True
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            logger.warning(f"Iteration timed out after {timeout} seconds")
            timed_out[0] = True
            # 超时不设置 running = False，只记录警告
            # 继续下一次迭代

        if exception[0]:
            logger.error(f"Iteration error: {exception[0]}", exc_info=True)

    def _run_iteration_impl(self) -> None:
        """实际的迭代逻辑 - 无超时包装"""
        start_time = time.time()
        max_iteration_time = 30  # 最大迭代时间 30 秒

        # 每次操作前检查停止标志
        if not self.running:
            return

        try:
            # Get current state (with timeout protection)
            markets = self._safe_get_markets()
            if not self.running:
                return

            # 检查是否超时
            if time.time() - start_time > max_iteration_time:
                logger.warning("Iteration timeout, skipping remaining operations")
                return

            # 使用 position_manager 获取持仓（会自动合并虚拟持仓）
            positions = self.position_manager.get_positions()
            if not self.running:
                return

            # 检查是否超时
            if time.time() - start_time > max_iteration_time:
                logger.warning("Iteration timeout, skipping remaining operations")
                return

            balance = self.client.get_balance()
            if not self.running:
                return

            # 1. 自动平仓已结算市场的持仓（真实持仓）
            if hasattr(self.strategy, '_close_settled_positions'):
                settlement_signals = self.strategy._close_settled_positions(positions)
                if settlement_signals:
                    logger.info(f"检测到 {len(settlement_signals)} 个已结算市场的持仓需要平仓")
                    self.executor.execute_signals(settlement_signals)
                    # 刷新持仓列表
                    positions = self.position_manager.get_positions()

            # 2. 自动平仓已结算市场的虚拟持仓（dry_run 模式）
            if self.config.dry_run and self.executor.virtual_positions:
                closed = self.executor.virtual_positions.close_settled_positions()
                if closed:
                    logger.info(f"自动平仓了 {len(closed)} 个已结算市场的虚拟持仓")
                    # 刷新持仓列表
                    positions = self.position_manager.get_positions()

            if not self.running:
                return

            # Generate signals from strategy
            signals = self.strategy.generate_signals(markets, positions, balance)

            if signals:
                # 只在有信号时记录
                logger.info(f"策略生成 {len(signals)} 个信号")

                # Execute signals
                executed = self.executor.execute_signals(signals)
                logger.info(f"执行 {len(executed)} 个订单")

            iteration_time = time.time() - start_time
            logger.debug(f"Iteration completed in {iteration_time:.2f} seconds")

        except Exception as e:
            logger.error(f"Error in bot iteration: {e}", exc_info=True)

    def _safe_get_markets(self):
        """安全获取市场数据，支持中断"""
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            # 创建带重试和超时的 session
            session = requests.Session()
            retry = Retry(total=1, backoff_factor=0.1)
            adapter = HTTPAdapter(max_retries=retry)
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            gamma_url = "https://gamma-api.polymarket.com/events"
            params = {"active": "true", "closed": "false", "limit": 20}

            response = session.get(gamma_url, params=params, timeout=5)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.warning(f"Error fetching markets: {e}")
            return []

    def stop(self) -> None:
        """Stop the bot gracefully"""
        if not self.running:
            return

        logger.info("Stopping bot...")
        self.running = False

        # 同时停止策略
        if hasattr(self.strategy, 'running'):
            self.strategy.running = False

        # Print final summary
        self.print_summary()

        logger.info("Bot stopped")

    def run_once(self) -> None:
        """
        Run the bot for a single iteration (useful for testing)
        """
        logger.info("Running single iteration...")
        self._run_iteration_impl()
        self.print_summary()

    def print_summary(self) -> None:
        """Print bot status summary"""
        self.position_manager.print_summary()

    def backtest(self, historical_data: list) -> dict:
        """
        Run backtest on historical data

        Args:
            historical_data: List of historical market snapshots

        Returns:
            Backtest results
        """
        logger.info("Starting backtest...")

        # This is a placeholder for backtesting functionality
        # You would need to implement historical data replay
        # and simulate order execution

        raise NotImplementedError("Backtesting not yet implemented")


def main():
    """
    Example main function

    Shows how to initialize and run the bot
    """
    from dotenv import load_dotenv
    from .strategy import ExampleMomentumStrategy

    # Load environment variables
    load_dotenv()

    # Load configuration
    config = BotConfig.from_env()

    # Create strategy
    strategy = ExampleMomentumStrategy(
        momentum_threshold=0.1,
        target_profit=0.15,
        max_position_per_market=50.0,
    )

    # Create and run bot
    bot = PolymarketBot(strategy, config)

    # Run once for testing or run continuously
    # bot.run_once()  # Single iteration
    bot.run()  # Continuous operation


if __name__ == "__main__":
    main()
