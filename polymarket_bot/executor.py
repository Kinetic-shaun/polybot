"""
Order execution and position management
"""
from typing import List, Optional, Dict, Any
import logging
import json
import os
import csv
import random
import requests
from datetime import datetime
from .client import PolymarketClient
from .strategy import Signal
from .config import BotConfig

logger = logging.getLogger(__name__)


class VirtualPositionManager:
    """
    管理 DRY_RUN 模式下的虚拟持仓
    持久化到 JSON 文件，实现闭环测试
    记录交易历史到 CSV 文件
    """

    def __init__(self, file_path: str = "virtual_positions.json", history_file: str = "trade_history.csv"):
        """
        初始化虚拟持仓管理器

        Args:
            file_path: JSON 文件路径
            history_file: 交易历史 CSV 文件路径
        """
        self.file_path = file_path
        self.history_file = history_file
        self._ensure_file_exists()
        self._ensure_history_file_exists()

    def _ensure_file_exists(self):
        """确保 JSON 文件存在"""
        if not os.path.exists(self.file_path):
            self._save_positions({})

    def _ensure_history_file_exists(self):
        """确保交易历史 CSV 文件存在，如果不存在则创建并写入表头"""
        if not os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'timestamp',           # 交易时间
                        'token_id',            # Token ID
                        'side',                # BUY/SELL
                        'entry_price',         # 买入价
                        'exit_price',          # 卖出价
                        'size',                # 持仓数量
                        'holding_time_seconds',# 持仓时间（秒）
                        'pnl',                 # 盈亏金额
                        'pnl_pct',             # 盈亏百分比
                        'slippage'             # 滑点
                    ])
                logger.info(f"Created trade history file: {self.history_file}")
            except Exception as e:
                logger.error(f"Failed to create trade history file: {e}")

    def _record_trade_history(
        self,
        token_id: str,
        side: str,
        entry_price: float,
        exit_price: float,
        size: float,
        holding_time_seconds: float,
        pnl: float,
        pnl_pct: float,
        slippage: float
    ):
        """
        记录交易历史到 CSV 文件

        Args:
            token_id: Token ID
            side: BUY or SELL
            entry_price: 买入价格
            exit_price: 卖出价格
            size: 交易数量
            holding_time_seconds: 持仓时间（秒）
            pnl: 盈亏金额
            pnl_pct: 盈亏百分比
            slippage: 滑点百分比
        """
        try:
            with open(self.history_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),  # timestamp
                    token_id,                     # token_id
                    side,                         # side (BUY or SELL)
                    f"{entry_price:.6f}",         # entry_price
                    f"{exit_price:.6f}" if exit_price else "",  # exit_price
                    f"{size:.6f}",                # size
                    f"{holding_time_seconds:.2f}" if holding_time_seconds else "",  # holding_time_seconds
                    f"{pnl:.6f}" if pnl else "0", # pnl
                    f"{pnl_pct:.6f}" if pnl_pct else "0",  # pnl_pct
                    f"{slippage:.6f}" if slippage else "0"  # slippage
                ])
            logger.info(f"[TRADE HISTORY] Recorded: {side} {token_id[:20]}... Size: {size:.2f}")
        except Exception as e:
            logger.error(f"Failed to record trade history: {e}")

    def _load_positions(self) -> Dict[str, Dict[str, Any]]:
        """从 JSON 文件加载虚拟持仓"""
        try:
            with open(self.file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load virtual positions: {e}")
            return {}

    def _save_positions(self, positions: Dict[str, Dict[str, Any]]):
        """保存虚拟持仓到 JSON 文件"""
        try:
            with open(self.file_path, 'w') as f:
                json.dump(positions, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save virtual positions: {e}")

    def add_position(self, token_id: str, side: str, size: float, price: float):
        """
        添加虚拟持仓（模拟买入）

        Args:
            token_id: Token ID
            side: BUY or SELL
            size: 持仓数量
            price: 成交价格
        """
        positions = self._load_positions()

        if side == "BUY":
            if token_id in positions:
                # 已有持仓，更新平均价格
                old_pos = positions[token_id]
                old_size = old_pos["size"]
                old_price = old_pos["average_price"]
                new_size = old_size + size
                new_avg_price = (old_size * old_price + size * price) / new_size

                positions[token_id] = {
                    "token_id": token_id,
                    "size": new_size,
                    "average_price": new_avg_price,
                    "entry_time": old_pos["entry_time"],
                    "last_update": datetime.now().isoformat(),
                    "is_virtual": True
                }
            else:
                # 新建持仓
                positions[token_id] = {
                    "token_id": token_id,
                    "size": size,
                    "average_price": price,
                    "entry_time": datetime.now().isoformat(),
                    "last_update": datetime.now().isoformat(),
                    "is_virtual": True
                }

            self._save_positions(positions)
            logger.info(f"[VIRTUAL POSITION] Added: {side} {size} of {token_id} @ ${price:.4f}")

            # 记录 BUY 交易历史
            self._record_trade_history(
                token_id=token_id,
                side=side,
                entry_price=price,
                exit_price=0,  # 还未卖出
                size=size,
                holding_time_seconds=0,  # 刚开始持仓
                pnl=0,  # 未实现盈亏
                pnl_pct=0,
                slippage=0
            )

    def remove_position(self, token_id: str, size: float = None, exit_price: float = None, slippage: float = 0.0, is_settlement: bool = False):
        """
        移除虚拟持仓（模拟卖出）并记录交易历史

        Args:
            token_id: Token ID
            size: 卖出数量（None 表示全部卖出）
            exit_price: 卖出价格
            slippage: 滑点百分比
            is_settlement: 是否为市场结算（结算时使用结算价，无滑点）
        """
        positions = self._load_positions()

        if token_id in positions:
            position = positions[token_id]
            entry_price = position["average_price"]
            trade_size = size if size else position["size"]
            entry_time = datetime.fromisoformat(position["entry_time"])
            exit_time = datetime.now()

            # 计算持仓时间（秒）
            holding_time_seconds = (exit_time - entry_time).total_seconds()

            # 如果是结算，使用结算价（无滑点）
            if is_settlement and exit_price is not None:
                actual_exit_price = exit_price
                actual_slippage = 0.0
            else:
                actual_exit_price = exit_price if exit_price else entry_price
                actual_slippage = slippage

            # 计算盈亏
            if actual_exit_price:
                pnl = (actual_exit_price - entry_price) * trade_size
                pnl_pct = (actual_exit_price - entry_price) / entry_price if entry_price > 0 else 0
            else:
                pnl = 0
                pnl_pct = 0

            # 记录交易历史
            self._record_trade_history(
                token_id=token_id,
                side="SELL",
                entry_price=entry_price,
                exit_price=actual_exit_price,
                size=trade_size,
                holding_time_seconds=holding_time_seconds,
                pnl=pnl,
                pnl_pct=pnl_pct,
                slippage=actual_slippage
            )

            if size is None or size >= position["size"]:
                # 完全卖出
                removed = positions.pop(token_id)
                if is_settlement:
                    logger.info(f"[VIRTUAL POSITION] Settled: {token_id} (sold {removed['size']} shares @ ${actual_exit_price:.2f}, P&L: ${pnl:.2f})")
                else:
                    logger.info(f"[VIRTUAL POSITION] Removed: {token_id} (sold {removed['size']} shares, P&L: ${pnl:.2f})")
            else:
                # 部分卖出
                positions[token_id]["size"] -= size
                positions[token_id]["last_update"] = exit_time.isoformat()
                logger.info(f"[VIRTUAL POSITION] Reduced: {token_id} by {size} shares (P&L: ${pnl:.2f})")

            self._save_positions(positions)

    def close_settled_positions(self) -> Dict[str, Dict[str, Any]]:
        """
        自动平仓所有已结算市场的虚拟持仓

        Returns:
            已平仓的持仓信息字典 {token_id: position_info}
        """
        positions = self._load_positions()
        closed_positions = {}

        for token_id, position in list(positions.items()):
            # 获取市场信息
            market_info = self._get_market_info_by_token(token_id)
            if not market_info:
                continue

            resolution = market_info.get('resolution', '')
            if not resolution or resolution == 'null':
                continue  # 市场未结算

            # 市场已结算，获取结算价
            settlement_price = self._get_settlement_price(market_info, token_id)
            if settlement_price is None:
                settlement_price = 1.0 if resolution.lower() in ['yes', 'true', '1', 'correct', 'won'] else 0.0

            # 移除持仓并记录
            self.remove_position(
                token_id=token_id,
                size=None,
                exit_price=settlement_price,
                slippage=0.0,
                is_settlement=True
            )

            closed_positions[token_id] = {
                **position,
                'settlement_price': settlement_price,
                'resolution': resolution
            }

        if closed_positions:
            logger.info(f"[VIRTUAL POSITION] Auto-closed {len(closed_positions)} settled positions")

        return closed_positions

    def _get_market_info_by_token(self, token_id: str) -> Optional[Dict[str, Any]]:
        """通过 token_id 获取市场信息"""
        try:
            url = f"https://clob.polymarket.com/markets/tokens/{token_id}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"Failed to fetch market info for {token_id[:20]}...: {e}")
        return None

    def _get_settlement_price(self, market_info: Dict, token_id: str) -> Optional[float]:
        """获取市场的结算价"""
        resolution = market_info.get('resolution', '')
        if not resolution or resolution == 'null':
            return None

        resolution_lower = resolution.lower()
        tokens = market_info.get('tokens', [])

        for token in tokens:
            token_outcome = token.get('outcome', '').lower()
            if token.get('token_id') == token_id:
                return 1.0 if resolution_lower == token_outcome else 0.0

        return 1.0 if resolution_lower in ['yes', 'true', '1', 'correct', 'won'] else 0.0

    def get_all_positions(self) -> List[Dict[str, Any]]:
        """
        获取所有虚拟持仓

        Returns:
            虚拟持仓列表
        """
        positions = self._load_positions()
        return list(positions.values())

    def clear_all(self):
        """清空所有虚拟持仓"""
        self._save_positions({})
        logger.info("[VIRTUAL POSITION] Cleared all virtual positions")


class OrderExecutor:
    """
    Handles order execution with risk management and validation
    支持虚拟持仓记录（DRY_RUN 模式）
    """

    def __init__(self, client: PolymarketClient, config: BotConfig):
        """
        Initialize executor

        Args:
            client: Polymarket client
            config: Bot configuration
        """
        self.client = client
        self.config = config
        self.pending_orders: List[Dict[str, Any]] = []
        # 初始化虚拟持仓管理器（仅在 dry_run 模式下使用）
        self.virtual_positions = VirtualPositionManager() if config.dry_run else None

    def execute_signals(self, signals: List[Signal]) -> List[Dict[str, Any]]:
        """
        Execute trading signals with risk checks

        Args:
            signals: List of trading signals to execute

        Returns:
            List of executed orders
        """
        executed_orders = []

        for signal in signals:
            if self._validate_signal(signal):
                order = self._execute_signal(signal)
                if order:
                    executed_orders.append(order)
                    logger.info(
                        f"Executed: {signal.side} {signal.size} of {signal.token_id} "
                        f"- Reason: {signal.reason}"
                    )
                else:
                    logger.warning(f"Failed to execute signal: {signal}")
            else:
                logger.warning(f"Signal validation failed: {signal}")

        return executed_orders

    def _validate_signal(self, signal: Signal) -> bool:
        """
        Validate signal against risk parameters

        Args:
            signal: Trading signal

        Returns:
            True if signal passes validation
        """
        # Check minimum trade size
        if signal.size < self.config.min_trade_size:
            logger.warning(f"Signal size {signal.size} below minimum {self.config.min_trade_size}")
            return False

        # Check maximum position size
        if signal.size > self.config.max_position_size:
            logger.warning(
                f"Signal size {signal.size} exceeds maximum {self.config.max_position_size}"
            )
            return False

        # Check total exposure for buys
        if signal.side == "BUY":
            current_exposure = self._calculate_total_exposure()
            if current_exposure + signal.size > self.config.max_total_exposure:
                logger.warning(
                    f"Signal would exceed max exposure: "
                    f"{current_exposure + signal.size} > {self.config.max_total_exposure}"
                )
                return False

            # Check if we have enough balance (跳过 dry_run 模式下的余额检查)
            if not self.config.dry_run:
                balance = self.client.get_balance()
                if signal.size > balance:
                    logger.warning(f"Insufficient balance: {signal.size} > {balance}")
                    return False

        return True

    def _execute_signal(self, signal: Signal) -> Optional[Dict[str, Any]]:
        """
        Execute a single signal

        Args:
            signal: Trading signal

        Returns:
            Order data if successful
        """
        if self.config.dry_run:
            # 获取真实市场价格（用于模拟成交）
            execution_price = signal.price if signal.price else self.client.get_midpoint_price(signal.token_id)
            if not execution_price:
                execution_price = 0.5  # 如果获取不到价格，使用默认值

            # 添加随机滑点 (0% - 1%)
            slippage = random.uniform(0.0, 0.01)

            # 应用滑点：买入时价格上涨，卖出时价格下跌
            if signal.side == "BUY":
                execution_price_with_slippage = execution_price * (1 + slippage)
            else:  # SELL
                execution_price_with_slippage = execution_price * (1 - slippage)

            logger.info(
                f"[DRY RUN] Would execute: {signal.side} {signal.size} of {signal.token_id} "
                f"@ ${execution_price_with_slippage:.4f} "
                f"(market: ${execution_price:.4f}, slippage: {slippage:.2%})"
            )

            # 记录虚拟持仓（实现闭环）
            if self.virtual_positions:
                if signal.side == "BUY":
                    self.virtual_positions.add_position(
                        token_id=signal.token_id,
                        side=signal.side,
                        size=signal.size,
                        price=execution_price_with_slippage
                    )
                elif signal.side == "SELL":
                    self.virtual_positions.remove_position(
                        token_id=signal.token_id,
                        size=signal.size,
                        exit_price=execution_price_with_slippage,
                        slippage=slippage
                    )

            return {
                "token_id": signal.token_id,
                "side": signal.side,
                "size": signal.size,
                "price": execution_price_with_slippage,
                "market_price": execution_price,
                "slippage": slippage,
                "dry_run": True,
            }

        try:
            if signal.is_market_order:
                return self.client.create_market_order(
                    token_id=signal.token_id,
                    side=signal.side,
                    amount=signal.size,
                )
            else:
                return self.client.create_limit_order(
                    token_id=signal.token_id,
                    side=signal.side,
                    amount=signal.size,
                    price=signal.price,
                )
        except Exception as e:
            logger.error(f"Error executing signal: {e}")
            return None

    def _calculate_total_exposure(self) -> float:
        """
        Calculate total exposure across all positions

        Returns:
            Total exposure in USDC
        """
        positions = self.client.get_positions()
        total = sum(
            float(pos.get("size", 0)) * float(pos.get("average_price", 0)) for pos in positions
        )
        return total

    def cancel_all_orders(self) -> int:
        """
        Cancel all open orders

        Returns:
            Number of orders cancelled
        """
        open_orders = self.client.get_open_orders()
        cancelled = 0

        for order in open_orders:
            order_id = order.get("id")
            if order_id and self.client.cancel_order(order_id):
                cancelled += 1

        logger.info(f"Cancelled {cancelled} orders")
        return cancelled


class PositionManager:
    """
    Manages positions and tracks P&L
    支持虚拟持仓合并（DRY_RUN 模式）
    """

    def __init__(self, client: PolymarketClient, virtual_positions: VirtualPositionManager = None):
        """
        Initialize position manager

        Args:
            client: Polymarket client
            virtual_positions: 虚拟持仓管理器（可选）
        """
        self.client = client
        self.initial_balance = self.client.get_balance()
        self.virtual_positions = virtual_positions

    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get all current positions with enriched data
        合并真实持仓和虚拟持仓（DRY_RUN 模式）
        支持快速中断和超时

        Returns:
            List of positions with P&L data
        """
        # 获取真实持仓
        positions = self.client.get_positions()

        # 合并虚拟持仓（如果存在）
        if self.virtual_positions:
            virtual_pos = self.virtual_positions.get_all_positions()
            positions.extend(virtual_pos)
            if virtual_pos:
                logger.info(f"Merged {len(virtual_pos)} virtual positions with real positions")

        enriched = []

        for pos in positions:
            token_id = pos.get("token_id")
            entry_price = float(pos.get("average_price", 0))
            size = float(pos.get("size", 0))
            is_virtual = pos.get("is_virtual", False)

            # Get current market price (使用真实数据，即使是虚拟持仓)
            # 使用快速超时模式
            current_price = None
            try:
                current_price = self._safe_get_midpoint_price(token_id, timeout=1)
            except Exception:
                current_price = None

            if current_price and entry_price > 0:
                unrealized_pnl = (current_price - entry_price) * size
                unrealized_pnl_pct = (current_price - entry_price) / entry_price
            else:
                unrealized_pnl = 0
                unrealized_pnl_pct = 0
                current_price = None

            enriched.append(
                {
                    **pos,
                    "current_price": current_price,
                    "unrealized_pnl": unrealized_pnl,
                    "unrealized_pnl_pct": unrealized_pnl_pct,
                    "is_virtual": is_virtual,  # 标记虚拟持仓
                }
            )

        return enriched

    def _safe_get_midpoint_price(self, token_id: str, timeout: float = 2) -> Optional[float]:
        """
        安全获取中间价，支持超时

        Args:
            token_id: Token ID
            timeout: 超时时间（秒）

        Returns:
            中间价或 None
        """
        result = [None]
        exception = [None]

        def get_price():
            try:
                result[0] = self.client.get_midpoint_price(token_id)
            except Exception as e:
                exception[0] = e

        # 在单独线程中执行
        thread = threading.Thread(target=get_price)
        thread.daemon = True
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            # 线程仍在运行，表示超时
            return None

        if exception[0]:
            logger.debug(f"Error getting price for {token_id[:20]}...: {exception[0]}")
            return None

        return result[0]

    def get_total_pnl(self) -> Dict[str, float]:
        """
        Calculate total P&L

        Returns:
            Dictionary with realized and unrealized P&L
        """
        current_balance = self.client.get_balance()
        positions = self.get_positions()

        unrealized_pnl = sum(pos.get("unrealized_pnl", 0) for pos in positions)
        total_pnl = (current_balance - self.initial_balance) + unrealized_pnl

        return {
            "initial_balance": self.initial_balance,
            "current_balance": current_balance,
            "unrealized_pnl": unrealized_pnl,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl / self.initial_balance if self.initial_balance > 0 else 0,
        }

    def print_summary(self) -> None:
        """Print position and P&L summary"""
        positions = self.get_positions()
        pnl = self.get_total_pnl()

        print("\n" + "=" * 60)
        print("POSITION SUMMARY")
        print("=" * 60)

        print(f"\nBalance: ${pnl['current_balance']:.2f}")
        print(f"Total P&L: ${pnl['total_pnl']:.2f} ({pnl['total_pnl_pct']:.2%})")
        print(f"Unrealized P&L: ${pnl['unrealized_pnl']:.2f}")

        if positions:
            virtual_count = sum(1 for p in positions if p.get('is_virtual', False))
            real_count = len(positions) - virtual_count
            print(f"\nOpen Positions ({len(positions)} total: {real_count} real, {virtual_count} virtual):")
            print("-" * 60)
            for pos in positions:
                is_virtual = pos.get('is_virtual', False)
                virtual_tag = " [VIRTUAL]" if is_virtual else ""
                current_price = pos.get('current_price', None)
                print(f"\nToken: {pos.get('token_id')}{virtual_tag}")
                print(f"  Size: {pos.get('size')}")
                print(f"  Entry: ${pos.get('average_price', 0):.3f}")
                if current_price is not None:
                    print(f"  Current: ${current_price:.3f}")
                else:
                    print(f"  Current: N/A (no orderbook)")
                print(
                    f"  P&L: ${pos.get('unrealized_pnl', 0):.2f} "
                    f"({pos.get('unrealized_pnl_pct', 0):.2%})"
                )
        else:
            print("\nNo open positions")

        print("=" * 60 + "\n")
