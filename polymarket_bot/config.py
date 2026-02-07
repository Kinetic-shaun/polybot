"""
Configuration management for Polymarket bot
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class BotConfig:
    """Bot configuration settings"""

    # API Configuration
    api_key: str
    api_secret: str
    api_passphrase: str
    private_key: str  # Ethereum private key for signing transactions

    # Network Configuration
    chain_id: int = 137  # Polygon mainnet
    rpc_url: str = "https://polygon-rpc.com"
    signature_type: int = 0  # 0=EOA/MetaMask, 1=Email/Magic, 2=Browser proxy
    funder: str = ""  # Optional funder address for proxy wallets

    # Trading Configuration
    max_position_size: float = 100.0  # Maximum position size in USDC
    max_slippage: float = 0.02  # 2% max slippage
    min_trade_size: float = 1.0  # Minimum trade size in USDC

    # Risk Management
    max_total_exposure: float = 1000.0  # Maximum total exposure across all markets
    stop_loss_pct: Optional[float] = None  # Optional stop loss percentage

    # Bot Behavior
    poll_interval: int = 60  # Seconds between strategy execution
    dry_run: bool = True  # If True, don't execute real trades

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = "bot.log"

    @classmethod
    def from_env(cls) -> "BotConfig":
        """Load configuration from environment variables"""
        return cls(
            api_key=os.getenv("POLYMARKET_API_KEY", ""),
            api_secret=os.getenv("POLYMARKET_API_SECRET", ""),
            api_passphrase=os.getenv("POLYMARKET_API_PASSPHRASE", ""),
            private_key=os.getenv("POLYMARKET_PRIVATE_KEY", ""),
            chain_id=int(os.getenv("CHAIN_ID", "137")),
            rpc_url=os.getenv("RPC_URL", "https://polygon-rpc.com"),
            signature_type=int(os.getenv("SIGNATURE_TYPE", "0")),
            funder=os.getenv("FUNDER", ""),
            max_position_size=float(os.getenv("MAX_POSITION_SIZE", "100.0")),
            max_slippage=float(os.getenv("MAX_SLIPPAGE", "0.02")),
            dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
        )
