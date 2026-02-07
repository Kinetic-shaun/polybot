"""
Polymarket API Client Wrapper
"""
from typing import Dict, List, Optional, Any
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, ApiCreds, BalanceAllowanceParams, AssetType, TradeParams
from py_clob_client.constants import POLYGON
import logging
import requests
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


logger = logging.getLogger(__name__)


class TradeStatus(Enum):
    """Trade status enum matching Polymarket's status values"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    MATCHED = "MATCHED"
    MINED = "MINED"
    CONFIRMED = "CONFIRMED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class TradeInfo:
    """Enhanced trade information with status"""
    trade_id: str
    market_id: str
    token_id: str
    side: str
    size: float
    price: float
    status: str
    maker_address: Optional[str] = None
    taker_address: Optional[str] = None
    transaction_hash: Optional[str] = None
    match_time: Optional[str] = None
    fee: float = 0.0
    is_settled: bool = False
    settlement_price: Optional[float] = None

    @property
    def is_confirmed(self) -> bool:
        """Check if trade is confirmed/settled"""
        return self.status in [TradeStatus.CONFIRMED.value, TradeStatus.MINED.value]

    @property
    def is_successful(self) -> bool:
        """Check if trade was successful"""
        return self.status in [TradeStatus.CONFIRMED.value, TradeStatus.MINED.value, TradeStatus.MATCHED.value]


class PolymarketClient:
    """Wrapper around Polymarket CLOB client with simplified interface"""

    def __init__(self, api_key: str, api_secret: str, api_passphrase: str, private_key: str, chain_id: int = 137, signature_type: int = 0, funder: str = None):
        """
        Initialize Polymarket client

        Args:
            api_key: Polymarket API key (optional - will be auto-generated if not provided)
            api_secret: Polymarket API secret (optional)
            api_passphrase: Polymarket API passphrase (optional)
            private_key: Ethereum private key for signing transactions
            chain_id: Blockchain chain ID (default: 137 for Polygon)
            signature_type: Signature type (0=EOA/MetaMask, 1=Email/Magic, 2=Browser proxy)
            funder: Optional funder address for proxy wallets
        """
        # Clean private key (remove 0x prefix if present)
        clean_key = private_key.replace("0x", "").replace("0X", "").strip() if private_key else ""

        # Store signature type for later use
        self.signature_type = signature_type

        # Initialize client without credentials first
        try:
            if clean_key:
                # Initialize with private key for authenticated access
                self.client = ClobClient(
                    host="https://clob.polymarket.com",
                    key=clean_key,
                    chain_id=chain_id,
                    signature_type=signature_type,
                    funder=funder
                )

                # Set API credentials using the official method
                # This will auto-generate credentials from the private key
                try:
                    api_creds = self.client.create_or_derive_api_creds()
                    self.client.set_api_creds(api_creds)
                    logger.info("Polymarket client initialized with authentication")
                except Exception as e:
                    logger.warning(f"Failed to derive API credentials: {e}")
                    logger.warning("Client initialized but authentication may not work")
            else:
                # Initialize without auth for public endpoints only
                self.client = ClobClient(
                    host="https://clob.polymarket.com",
                    chain_id=chain_id,
                )
                logger.info("Polymarket client initialized (public endpoints only)")

        except Exception as e:
            logger.error(f"Failed to initialize client: {e}")
            # Fallback to public-only client
            self.client = ClobClient(
                host="https://clob.polymarket.com",
                chain_id=chain_id,
            )
            logger.info("Polymarket client initialized in fallback mode (public endpoints only)")

    def get_markets(self, closed: bool = False, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get all available markets from Gamma API
        使用 Gamma API 获取活跃市场（而不是 CLOB API）

        Args:
            closed: Include closed markets
            limit: Maximum number of events to fetch

        Returns:
            List of market dictionaries compatible with strategy interface
        """
        try:
            # 使用 Gamma API 获取活跃事件
            gamma_url = "https://gamma-api.polymarket.com/events"
            params = {
                "active": "true" if not closed else "false",
                "closed": "false" if not closed else "true",
                "limit": limit
            }

            response = requests.get(gamma_url, params=params, timeout=20)  # 增加超时到20秒
            response.raise_for_status()
            events = response.json()

            # 解析并转换为策略期望的格式
            markets = []
            for event in events:
                event_markets = event.get("markets", [])
                for market in event_markets:
                    # 获取市场基本信息
                    question = market.get("question", "")

                    # Gamma API 返回的是 JSON 字符串，需要解析
                    clob_token_ids_raw = market.get("clobTokenIds", [])
                    outcome_prices_raw = market.get("outcomePrices", [])
                    outcomes_raw = market.get("outcomes", ["Yes", "No"])

                    # 解析 JSON 字符串
                    try:
                        clob_token_ids = json.loads(clob_token_ids_raw) if isinstance(clob_token_ids_raw, str) else clob_token_ids_raw
                        outcome_prices = json.loads(outcome_prices_raw) if isinstance(outcome_prices_raw, str) else outcome_prices_raw
                        outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse market data: {e}")
                        continue

                    # 跳过无效市场
                    if not clob_token_ids or not outcome_prices:
                        continue

                    # 构建兼容格式
                    tokens = []
                    for i, token_id in enumerate(clob_token_ids):
                        if i < len(outcome_prices):
                            try:
                                price = float(outcome_prices[i])
                            except (ValueError, TypeError):
                                price = 0.5  # 默认价格

                            tokens.append({
                                "token_id": token_id,
                                "outcome": outcomes[i] if i < len(outcomes) else f"Outcome {i}",
                                "price": price
                            })

                    # 添加市场（格式兼容原有策略）
                    markets.append({
                        "question": question,
                        "closed": False,  # Gamma API 返回的都是活跃市场
                        "accepting_orders": True,  # Gamma API 返回的市场都接受订单
                        "tokens": tokens,
                        "event_id": event.get("id", ""),
                        "market_slug": market.get("marketSlug", ""),
                    })

            logger.info(f"Fetched {len(markets)} active markets from Gamma API")
            return markets

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching markets from Gamma API: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing markets from Gamma API: {e}")
            return []

    def get_market(self, condition_id: str) -> Optional[Dict[str, Any]]:
        """
        Get specific market by condition ID

        Args:
            condition_id: Market condition ID

        Returns:
            Market dictionary or None if not found
        """
        try:
            return self.client.get_market(condition_id)
        except Exception as e:
            logger.error(f"Error fetching market {condition_id}: {e}")
            return None

    def get_orderbook(self, token_id: str) -> Dict[str, Any]:
        """
        Get orderbook for a specific token

        Args:
            token_id: Token ID

        Returns:
            Orderbook data with bids and asks (converted to dict)
        """
        try:
            # 使用带超时的 requests 直接调用 API
            url = f"https://clob.polymarket.com/book"
            params = {"token_id": token_id}
            resp = requests.get(url, params=params, timeout=2)

            if resp.status_code == 200:
                data = resp.json()
                return {
                    "bids": data.get("bids", []),
                    "asks": data.get("asks", []),
                    "market": token_id,
                }
            else:
                return {"bids": [], "asks": []}

        except requests.exceptions.Timeout:
            logger.debug(f"Orderbook request timeout for {token_id[:20]}...")
            return {"bids": [], "asks": []}
        except Exception as e:
            logger.debug(f"Error fetching orderbook for {token_id[:20]}...: {e}")
            return {"bids": [], "asks": []}

    def get_midpoint_price(self, token_id: str) -> Optional[float]:
        """
        Get midpoint price for a token

        Args:
            token_id: Token ID

        Returns:
            Midpoint price or None if unavailable
        """
        try:
            orderbook = self.get_orderbook(token_id)
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])

            if not bids or not asks:
                return None

            # 处理不同的数据格式
            if isinstance(bids[0], dict):
                best_bid = float(bids[0]["price"])
            else:
                best_bid = float(bids[0].price) if hasattr(bids[0], 'price') else float(bids[0])

            if isinstance(asks[0], dict):
                best_ask = float(asks[0]["price"])
            else:
                best_ask = float(asks[0].price) if hasattr(asks[0], 'price') else float(asks[0])

            return (best_bid + best_ask) / 2
        except Exception as e:
            logger.debug(f"Could not get midpoint price for {token_id}: {e}")
            return None

    def create_market_order(
        self,
        token_id: str,
        side: str,
        amount: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a market order

        Args:
            token_id: Token ID to trade
            side: "BUY" or "SELL"
            amount: Amount in USDC

        Returns:
            Order response or None if failed
        """
        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=0.99 if side == "BUY" else 0.01,  # Will be filled at market
                size=amount,
                side=side.upper(),
                order_type=OrderType.GTC,
            )

            response = self.client.create_order(order_args)
            logger.info(f"Market order created: {side} {amount} of {token_id}")
            return response
        except Exception as e:
            logger.error(f"Error creating market order: {e}")
            return None

    def create_limit_order(
        self,
        token_id: str,
        side: str,
        amount: float,
        price: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a limit order

        Args:
            token_id: Token ID to trade
            side: "BUY" or "SELL"
            amount: Amount in USDC
            price: Limit price

        Returns:
            Order response or None if failed
        """
        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=amount,
                side=side.upper(),
                order_type=OrderType.GTC,
            )

            response = self.client.create_order(order_args)
            logger.info(f"Limit order created: {side} {amount} of {token_id} at {price}")
            return response
        except Exception as e:
            logger.error(f"Error creating limit order: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order

        Args:
            order_id: Order ID to cancel

        Returns:
            True if successful
        """
        try:
            self.client.cancel_order(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Get all open orders

        Returns:
            List of open orders
        """
        try:
            return self.client.get_orders()
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            return []

    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions

        Note: The CLOB API doesn't have a direct positions endpoint.
        This would need to be calculated from order history and fills.
        For now, returns empty list.

        Returns:
            List of positions
        """
        # TODO: Implement position tracking from order fills
        # This requires tracking filled orders and calculating net positions
        return []

    def get_balance(self) -> float:
        """
        Get USDC balance and allowance

        Returns:
            USDC balance
        """
        # 添加重试机制
        max_retries = 3
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
                params = BalanceAllowanceParams(
                    asset_type=AssetType.COLLATERAL,  # USDC is collateral
                    signature_type=self.signature_type
                )
                balance_data = self.client.get_balance_allowance(params)
                # The response includes both balance and allowance
                return float(balance_data.get("balance", 0))
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.debug(f"Balance fetch attempt {attempt + 1} failed, retrying: {e}")
                    import time
                    time.sleep(retry_delay)
                else:
                    logger.debug(f"Balance fetch failed after {max_retries} attempts: {e}")
                    return 0.0

        return 0.0

    def get_trades(
        self,
        maker_address: str = None,
        taker_address: str = None,
        market_id: str = None,
        limit: int = 50,
    ) -> List[TradeInfo]:
        """
        Get trades with status information

        Args:
            maker_address: Filter by maker address
            taker_address: Filter by taker address
            market_id: Filter by market/condition ID
            limit: Maximum number of trades to return

        Returns:
            List of TradeInfo objects with status
        """
        try:
            # Build trade params
            params = TradeParams(
                maker=maker_address,
                taker=taker_address,
                market=market_id,
            )

            # Get trades from ClobClient
            trades = self.client.get_trades(params)

            # Convert to TradeInfo objects
            trade_infos = []
            for trade in trades:
                # Handle different response formats
                if hasattr(trade, '__dict__'):
                    # Object format
                    trade_dict = trade.__dict__
                elif isinstance(trade, dict):
                    trade_dict = trade
                else:
                    continue

                # Extract trade info
                trade_id = trade_dict.get('id', trade_dict.get('orderId', ''))
                market = trade_dict.get('market', trade_dict.get('conditionId', ''))
                token_id = trade_dict.get('asset', trade_dict.get('clobTokenId', ''))
                side = trade_dict.get('side', '')
                size = float(trade_dict.get('size', trade_dict.get('amount', 0)))
                price = float(trade_dict.get('price', trade_dict.get('avgPrice', 0)))
                status = trade_dict.get('status', 'UNKNOWN')

                trade_info = TradeInfo(
                    trade_id=trade_id,
                    market_id=market,
                    token_id=token_id,
                    side=side.upper(),
                    size=size,
                    price=price,
                    status=status,
                    maker_address=trade_dict.get('maker'),
                    taker_address=trade_dict.get('taker'),
                    transaction_hash=trade_dict.get('transactionHash', trade_dict.get('transaction_hash')),
                    match_time=trade_dict.get('matchTime', trade_dict.get('match_time')),
                    fee=float(trade_dict.get('fee', 0)),
                )

                # Determine if trade is settled based on status
                trade_info.is_settled = trade_info.is_confirmed

                trade_infos.append(trade_info)

            logger.debug(f"Fetched {len(trade_infos)} trades")
            return trade_infos

        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            return []

    def get_trade_status(self, trade_id: str) -> Optional[TradeInfo]:
        """
        Get status of a specific trade

        Args:
            trade_id: Trade/Order ID

        Returns:
            TradeInfo object or None if not found
        """
        try:
            trades = self.get_trades(limit=1)
            for trade in trades:
                if trade.trade_id == trade_id:
                    return trade
            return None
        except Exception as e:
            logger.error(f"Error fetching trade status for {trade_id}: {e}")
            return None

    def get_position_by_token(self, token_id: str) -> Optional[Dict[str, Any]]:
        """
        Get position details for a specific token by checking recent trades

        Args:
            token_id: Token ID

        Returns:
            Position dict or None
        """
        try:
            # Get user's recent trades for this token
            trades = self.get_trades(limit=100)

            # Filter by token and calculate net position
            buy_volume = 0.0
            sell_volume = 0.0

            for trade in trades:
                if trade.token_id == token_id and trade.is_successful:
                    if trade.side.upper() == 'BUY':
                        buy_volume += trade.size
                    elif trade.side.upper() == 'SELL':
                        sell_volume += trade.size

            net_size = buy_volume - sell_volume
            if net_size > 0:
                avg_price = 0  # Would need to track this properly
                return {
                    'token_id': token_id,
                    'size': net_size,
                    'average_price': avg_price,
                    'is_real': True
                }

            return None

        except Exception as e:
            logger.error(f"Error getting position for token {token_id}: {e}")
            return None

    def check_market_settled(self, condition_id: str) -> tuple[bool, Optional[float]]:
        """
        Check if a market is settled and get settlement price

        Args:
            condition_id: Market condition ID

        Returns:
            Tuple of (is_settled, settlement_price)
        """
        try:
            # Method 1: Get market info from CLOB API
            url = f"https://clob.polymarket.com/markets/{condition_id}"
            resp = requests.get(url, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                resolution = data.get('resolution', '')
                is_closed = data.get('closed', False)

                if resolution and resolution != 'null':
                    # Market is settled
                    settlement_price = 1.0 if resolution.lower() in ['yes', 'true', '1', 'correct', 'won'] else 0.0
                    return True, settlement_price

                if is_closed:
                    # Market closed but no resolution - might be cancelled
                    return True, 0.5  # Default to mid price

            return False, None

        except Exception as e:
            logger.warning(f"Error checking market settlement for {condition_id}: {e}")
            return False, None
