"""
Utility functions and helpers
"""
import logging
import sys
from typing import Dict, Any
from datetime import datetime


def setup_logging(log_level: str = "WARNING", log_file: str = None) -> None:
    """
    Configure logging for the bot

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
    """
    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(getattr(logging, log_level.upper()))
        root_logger.addHandler(file_handler)

    # Suppress noisy third-party libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    logging.info("Logging configured")


def format_price(price: float) -> str:
    """
    Format price for display

    Args:
        price: Price value

    Returns:
        Formatted price string
    """
    return f"${price:.3f}"


def format_percentage(value: float) -> str:
    """
    Format percentage for display

    Args:
        value: Percentage value (0.15 = 15%)

    Returns:
        Formatted percentage string
    """
    return f"{value * 100:.2f}%"


def format_timestamp(timestamp: int = None) -> str:
    """
    Format Unix timestamp for display

    Args:
        timestamp: Unix timestamp (seconds). If None, uses current time

    Returns:
        Formatted timestamp string
    """
    if timestamp is None:
        dt = datetime.now()
    else:
        dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def calculate_market_stats(orderbook: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate market statistics from orderbook

    Args:
        orderbook: Orderbook data

    Returns:
        Dictionary with market statistics
    """
    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])

    if not bids or not asks:
        return {
            "best_bid": None,
            "best_ask": None,
            "spread": None,
            "spread_pct": None,
            "mid_price": None,
        }

    best_bid = float(bids[0]["price"])
    best_ask = float(asks[0]["price"])
    spread = best_ask - best_bid
    mid_price = (best_bid + best_ask) / 2
    spread_pct = spread / mid_price if mid_price > 0 else 0

    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "spread_pct": spread_pct,
        "mid_price": mid_price,
        "bid_volume": sum(float(b.get("size", 0)) for b in bids[:5]),  # Top 5 levels
        "ask_volume": sum(float(a.get("size", 0)) for a in asks[:5]),
    }


def validate_config(config: Any) -> bool:
    """
    Validate bot configuration

    Args:
        config: Bot configuration

    Returns:
        True if valid, raises ValueError if invalid
    """
    # API credentials are now auto-generated, so we only need private key
    if not config.private_key:
        raise ValueError("Private key not configured")

    if config.max_position_size <= 0:
        raise ValueError("max_position_size must be positive")

    if config.max_slippage < 0 or config.max_slippage > 1:
        raise ValueError("max_slippage must be between 0 and 1")

    if config.poll_interval < 1:
        raise ValueError("poll_interval must be at least 1 second")

    return True


class RateLimiter:
    """Simple rate limiter for API calls"""

    def __init__(self, max_calls: int, period: int):
        """
        Initialize rate limiter

        Args:
            max_calls: Maximum number of calls
            period: Period in seconds
        """
        self.max_calls = max_calls
        self.period = period
        self.calls = []

    def can_call(self) -> bool:
        """
        Check if a call can be made

        Returns:
            True if call is allowed
        """
        now = datetime.now().timestamp()
        # Remove old calls
        self.calls = [c for c in self.calls if now - c < self.period]
        return len(self.calls) < self.max_calls

    def record_call(self) -> None:
        """Record a call"""
        self.calls.append(datetime.now().timestamp())


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert value to float

    Args:
        value: Value to convert
        default: Default value if conversion fails

    Returns:
        Float value
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_get(dictionary: Dict, key: str, default: Any = None) -> Any:
    """
    Safely get value from dictionary with nested key support

    Args:
        dictionary: Dictionary to search
        key: Key (can use dot notation for nested keys)
        default: Default value if key not found

    Returns:
        Value or default
    """
    keys = key.split(".")
    value = dictionary

    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return default

        if value is None:
            return default

    return value
