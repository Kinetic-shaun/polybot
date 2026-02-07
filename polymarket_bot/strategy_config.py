"""
Strategy Configuration Schema - 分析与执行的桥梁

这个文件定义了策略配置的数据结构。
分析模块输出此配置，执行模块读取此配置。
两者通过 JSON 文件解耦。
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class MarketFilter:
    """市场过滤条件"""
    categories: List[str] = field(default_factory=list)  # 关注的领域
    min_volume: float = 0.0  # 最小交易量
    max_age_days: int = 30  # 最大天数
    keywords: List[str] = field(default_factory=list)  # 关键词过滤


@dataclass
class EntryCondition:
    """买入条件"""
    price_range: tuple = (0.1, 0.9)  # 价格区间
    require_volume_above: float = 0.0  # 要求交易量高于
    follow_consensus: bool = True  # 跟随多数派
    max_position_size: float = 50.0  # 最大仓位


@dataclass
class ExitCondition:
    """卖出条件"""
    profit_target: float = 0.5  # 止盈目标 (50%)
    stop_loss: float = 0.3  # 止损线 (30%)
    time_limit_hours: int = 168  # 时间限制 (7天)
    auto_close_on_resolved: bool = True  # 结算时自动平仓


@dataclass
class PositionRule:
    """仓位管理规则"""
    max_single_position: float = 50.0  # 单个最大仓位
    max_total_exposure: float = 500.0  # 总暴露风险
    pyramiding_allowed: bool = False  # 是否允许金字塔加仓
    pyramiding_step: float = 0.0  # 加仓步长


@dataclass
class RiskConfig:
    """风险配置"""
    max_daily_loss: float = 100.0  # 单日最大亏损
    max_trades_per_day: int = 10  # 单日最大交易数
    correlation_check: bool = True  # 相关性检查
    circuit_breaker: bool = True  # 熔断机制


@dataclass
class StrategyConfig:
    """
    策略配置 - 分析与执行的桥梁

    分析模块生成此配置，执行模块读取此配置。
    两者通过 JSON 文件完全解耦。
    """
    # 元数据
    version: str = "1.0.0"
    created_at: str = ""
    updated_at: str = ""
    name: str = ""
    description: str = ""

    # 市场过滤
    market_filter: MarketFilter = field(default_factory=MarketFilter)

    # 交易条件
    entry: EntryCondition = field(default_factory=EntryCondition)
    exit: ExitCondition = field(default_factory=ExitCondition)

    # 仓位管理
    position: PositionRule = field(default_factory=PositionRule)

    # 风险管理
    risk: RiskConfig = field(default_factory=RiskConfig)

    # 目标市场列表（由分析模块生成）
    target_markets: List[Dict] = field(default_factory=list)

    # 分析洞察（只读，不参与执行）
    insights: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典用于 JSON 序列化"""
        return {
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "name": self.name,
            "description": self.description,
            "market_filter": {
                "categories": self.market_filter.categories,
                "min_volume": self.market_filter.min_volume,
                "max_age_days": self.market_filter.max_age_days,
                "keywords": self.market_filter.keywords
            },
            "entry": {
                "price_range": list(self.entry.price_range),
                "require_volume_above": self.entry.require_volume_above,
                "follow_consensus": self.entry.follow_consensus,
                "max_position_size": self.entry.max_position_size
            },
            "exit": {
                "profit_target": self.exit.profit_target,
                "stop_loss": self.exit.stop_loss,
                "time_limit_hours": self.exit.time_limit_hours,
                "auto_close_on_resolved": self.exit.auto_close_on_resolved
            },
            "position": {
                "max_single_position": self.position.max_single_position,
                "max_total_exposure": self.position.max_total_exposure,
                "pyramiding_allowed": self.position.pyramiding_allowed,
                "pyramiding_step": self.position.pyramiding_step
            },
            "risk": {
                "max_daily_loss": self.risk.max_daily_loss,
                "max_trades_per_day": self.risk.max_trades_per_day,
                "correlation_check": self.risk.correlation_check,
                "circuit_breaker": self.risk.circuit_breaker
            },
            "target_markets": self.target_markets,
            "insights": self.insights
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "StrategyConfig":
        """从字典创建配置"""
        config = cls()

        if "version" in data:
            config.version = data["version"]
        if "created_at" in data:
            config.created_at = data["created_at"]
        if "updated_at" in data:
            config.updated_at = data["updated_at"]
        if "name" in data:
            config.name = data["name"]
        if "description" in data:
            config.description = data["description"]

        # Market filter
        if "market_filter" in data:
            mf = data["market_filter"]
            config.market_filter.categories = mf.get("categories", [])
            config.market_filter.min_volume = mf.get("min_volume", 0.0)
            config.market_filter.max_age_days = mf.get("max_age_days", 30)
            config.market_filter.keywords = mf.get("keywords", [])

        # Entry
        if "entry" in data:
            e = data["entry"]
            config.entry.price_range = tuple(e.get("price_range", (0.1, 0.9)))
            config.entry.require_volume_above = e.get("require_volume_above", 0.0)
            config.entry.follow_consensus = e.get("follow_consensus", True)
            config.entry.max_position_size = e.get("max_position_size", 50.0)

        # Exit
        if "exit" in data:
            ex = data["exit"]
            config.exit.profit_target = ex.get("profit_target", 0.5)
            config.exit.stop_loss = ex.get("stop_loss", 0.3)
            config.exit.time_limit_hours = ex.get("time_limit_hours", 168)
            config.exit.auto_close_on_resolved = ex.get("auto_close_on_resolved", True)

        # Position
        if "position" in data:
            p = data["position"]
            config.position.max_single_position = p.get("max_single_position", 50.0)
            config.position.max_total_exposure = p.get("max_total_exposure", 500.0)
            config.position.pyramiding_allowed = p.get("pyramiding_allowed", False)
            config.position.pyramiding_step = p.get("pyramiding_step", 0.0)

        # Risk
        if "risk" in data:
            r = data["risk"]
            config.risk.max_daily_loss = r.get("max_daily_loss", 100.0)
            config.risk.max_trades_per_day = r.get("max_trades_per_day", 10)
            config.risk.correlation_check = r.get("correlation_check", True)
            config.risk.circuit_breaker = r.get("circuit_breaker", True)

        # Target markets
        if "target_markets" in data:
            config.target_markets = data["target_markets"]

        # Insights
        if "insights" in data:
            config.insights = data["insights"]

        return config


def load_strategy_config(filepath: str = "strategy_config.json") -> Optional[StrategyConfig]:
    """加载策略配置"""
    import json
    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return StrategyConfig.from_dict(data)
    except Exception as e:
        print(f"Error loading strategy config: {e}")
        return None


def save_strategy_config(config: StrategyConfig, filepath: str = "strategy_config.json"):
    """保存策略配置"""
    import json

    config.updated_at = datetime.now().isoformat()

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        print(f"Strategy config saved to {filepath}")
    except Exception as e:
        print(f"Error saving strategy config: {e}")


# 导入 os 用于文件操作
import os
