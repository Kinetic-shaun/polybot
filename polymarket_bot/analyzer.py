"""
Market Analyzer Module - 垂直领域分析与胜率仪表盘

功能：
1. 市场分类 - 按话题/领域自动分类
2. 历史胜率分析 - 计算各领域历史表现
3. 策略配置生成 - 生成可执行的策略配置（JSON）
4. 交易人分析 - 分析特定交易人的交易策略

注意：此模块只负责分析，不负责执行。
分析结果保存到 strategy_config.json，由执行模块读取。
"""
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import os
import logging
import requests
from collections import defaultdict

# 导入策略配置
from .strategy_config import (
    StrategyConfig, MarketFilter, EntryCondition,
    ExitCondition, PositionRule, RiskConfig
)

logger = logging.getLogger(__name__)


# 领域分类配置
DOMAIN_CATEGORIES = {
    "Politics": {
        "keywords": ["election", "president", "government", "policy", "congress", "senate",
                     "trump", "biden", "harris", "political", "vote", "campaign", "impeach",
                     "ukraine", "russia", "china", "iran", "israel", "war", "nato"],
        "description": "政治相关预测"
    },
    "Crypto": {
        "keywords": ["bitcoin", "btc", "ethereum", "eth", "crypto", "token", "blockchain",
                     "solana", "bnb", "xrp", "ada", "dogecoin", "加密", "eth", "sbf", "ftx"],
        "description": "加密货币相关预测"
    },
    "Sports": {
        "keywords": ["super bowl", "nfl", "nba", "mlb", "world cup", "olympic", "soccer",
                     "football", "basketball", "baseball", "tennis", "golf", "ufc", "boxing",
                     "game", "match", "championship", "season", "winner", "champion"],
        "description": "体育竞技预测"
    },
    "Economics": {
        "keywords": ["inflation", "recession", "interest rate", "fed", "gdp", "unemployment",
                     "stock market", "sp500", "nasdaq", "dow jones", "economy", "financial",
                     "fed rate", "cpi", "pce", "jobs", "economic"],
        "description": "宏观经济预测"
    },
    "Entertainment": {
        "keywords": ["oscar", "grammy", "emmy", "award", "movie", "film", "show", "series",
                     "netflix", "disney", "hbo", "music", "celebrity", "taylor swift", "drake",
                     "box office", "streaming", "chart", "billboard"],
        "description": "娱乐文化预测"
    },
    "Science": {
        "keywords": ["climate", "space", "nasa", "temperature", "carbon", "energy",
                     "ai", "artificial intelligence", "technology", "research", "science"],
        "description": "科学与技术预测"
    },
    "Other": {
        "keywords": [],
        "description": "其他领域"
    }
}


@dataclass
class MarketCategory:
    """市场分类信息"""
    name: str
    display_name: str
    market_count: int = 0
    total_volume: float = 0.0
    avg_price: float = 0.0


@dataclass
class ResolvedMarket:
    """已结算市场信息"""
    market_id: str
    name: str
    category: str
    volume: float
    resolution: str  # "YES" or "NO"
    yes_price_before: float
    no_price_before: float
    end_time: datetime


@dataclass
class CategoryStats:
    """领域统计数据"""
    category: str
    total_markets: int = 0
    resolved_markets: int = 0
    yes_wins: int = 0
    no_wins: int = 0
    total_volume: float = 0.0
    avg_yes_price: float = 0.0
    avg_no_price: float = 0.0
    avg_volume: float = 0.0

    @property
    def yes_rate(self) -> float:
        """YES 胜率"""
        if self.resolved_markets == 0:
            return 0.0
        return self.yes_wins / self.resolved_markets

    @property
    def no_rate(self) -> float:
        """NO 胜率"""
        if self.resolved_markets == 0:
            return 0.0
        return self.no_wins / self.resolved_markets


@dataclass
class DashboardReport:
    """仪表盘报告"""
    generated_at: str
    period: str
    categories: Dict[str, CategoryStats]
    top_markets: List[Dict]
    insights: List[str]
    recommendations: List[str]

    def to_dict(self) -> Dict:
        return {
            "generated_at": self.generated_at,
            "period": self.period,
            "categories": {
                k: {
                    "category": v.category,
                    "total_markets": v.total_markets,
                    "resolved_markets": v.resolved_markets,
                    "yes_wins": v.yes_wins,
                    "no_wins": v.no_wins,
                    "yes_rate": f"{v.yes_rate:.1%}",
                    "no_rate": f"{v.no_rate:.1%}",
                    "total_volume": f"${v.total_volume:,.0f}",
                    "avg_volume": f"${v.avg_volume:,.0f}"
                }
                for k, v in self.categories.items()
            },
            "top_markets": self.top_markets,
            "insights": self.insights,
            "recommendations": self.recommendations
        }


class PolymarketAnalyzer:
    """
    Polymarket 市场分析器

    用于垂直领域分析和胜率统计
    """

    def __init__(self, cache_dir: str = "market_analysis"):
        """
        初始化分析器

        Args:
            cache_dir: 缓存目录
        """
        self.cache_dir = cache_dir
        self._ensure_cache_dir()

        # 市场数据缓存
        self.active_markets: List[Dict] = []
        self.resolved_markets: List[Dict] = []

        # 分析结果缓存
        self.category_stats: Dict[str, CategoryStats] = {}

    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def _make_request(self, url: str, params: Dict = None, timeout: int = 10) -> Optional[Any]:
        """发送 API 请求"""
        try:
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(max_retries=3)
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            response = session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"API request failed: {e}")
            return None

    def categorize_market(self, market: Dict) -> str:
        """
        自动分类市场到指定领域

        Args:
            market: 市场数据

        Returns:
            分类名称
        """
        # 获取市场名称和描述
        name = market.get("question", "").lower() + " " + market.get("description", "").lower()
        name = name.lower()

        # 检查每个分类的关键词
        for category, config in DOMAIN_CATEGORIES.items():
            if category == "Other":
                continue  # 最后处理

            for keyword in config["keywords"]:
                if keyword.lower() in name:
                    return category

        return "Other"

    def get_active_markets(self, limit: int = 100) -> List[Dict]:
        """
        获取活跃市场

        Args:
            limit: 获取数量限制

        Returns:
            活跃市场列表
        """
        url = "https://gamma-api.polymarket.com/events"
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit
        }

        data = self._make_request(url, params)
        if data is None:
            return []

        markets = data.get("data", []) if isinstance(data, dict) else data
        self.active_markets = markets
        return markets

    def get_resolved_markets(self, days: int = 30, limit: int = 200) -> List[Dict]:
        """
        获取已结算市场（用于历史分析）

        Args:
            days: 回溯天数
            limit: 获取数量限制

        Returns:
            已结算市场列表
        """
        url = "https://gamma-api.polymarket.com/events"
        params = {
            "active": "false",
            "closed": "true",
            "limit": limit
        }

        data = self._make_request(url, params)
        if data is None:
            return []

        markets = data.get("data", []) if isinstance(data, dict) else data

        # 按时间过滤
        cutoff_date = datetime.now() - timedelta(days=days)
        filtered_markets = []

        for market in markets:
            end_date_str = market.get("endDate", "")
            if end_date_str:
                try:
                    # 尝试解析日期
                    if 'T' in end_date_str:
                        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                        if end_date >= cutoff_date:
                            filtered_markets.append(market)
                except:
                    filtered_markets.append(market)

        self.resolved_markets = filtered_markets
        return filtered_markets

    def get_market_volume_by_token(self, token_id: str) -> Optional[Dict]:
        """通过 Token API 获取市场的交易量"""
        try:
            url = f"https://clob.polymarket.com/markets/tokens/{token_id}"
            data = self._make_request(url)
            return data
        except Exception as e:
            logger.debug(f"Failed to get token info: {e}")
            return None

    def calculate_category_stats(self, markets: List[Dict]) -> Dict[str, CategoryStats]:
        """
        计算各分类的统计数据

        Args:
            markets: 市场列表（已结算的）

        Returns:
            各分类统计数据
        """
        stats = defaultdict(lambda: CategoryStats(category=""))

        for market in markets:
            category = self.categorize_market(market)

            if stats[category].category == "":
                stats[category].category = category

            stats[category].total_markets += 1

            # 获取交易量
            volume = self._parse_volume(market)
            stats[category].total_volume += volume
            stats[category].avg_volume = stats[category].total_volume / stats[category].total_markets

            # 检查结算结果
            resolution = market.get("resolution", "")
            if resolution and resolution != "null":
                stats[category].resolved_markets += 1

                if resolution.lower() in ["yes", "true", "1", "correct"]:
                    stats[category].yes_wins += 1
                else:
                    stats[category].no_wins += 1

                # 获取价格（结算前的）
                tokens = market.get("tokens", [])
                if tokens:
                    yes_price = float(tokens[0].get("price", 0.5)) if len(tokens) > 0 else 0.5
                    no_price = float(tokens[1].get("price", 0.5)) if len(tokens) > 1 else 0.5
                    stats[category].avg_yes_price = (stats[category].avg_yes_price * (stats[category].resolved_markets - 1) + yes_price) / stats[category].resolved_markets
                    stats[category].avg_no_price = (stats[category].avg_no_price * (stats[category].resolved_markets - 1) + no_price) / stats[category].resolved_markets

        self.category_stats = dict(stats)
        return self.category_stats

    def _parse_volume(self, market: Dict) -> float:
        """解析市场交易量"""
        volume = market.get("volume24h", 0) or market.get("volume", 0)
        try:
            return float(volume)
        except (ValueError, TypeError):
            return 0.0

    def generate_dashboard_report(self, days: int = 30) -> DashboardReport:
        """
        生成分析仪表盘报告

        Args:
            days: 分析回溯天数

        Returns:
            仪表盘报告
        """
        logger.info(f"Generating dashboard report for last {days} days...")

        # 1. 获取已结算市场
        resolved = self.get_resolved_markets(days=days)

        # 2. 计算分类统计
        stats = self.calculate_category_stats(resolved)

        # 3. 获取活跃市场
        active = self.get_active_markets(limit=100)
        active_by_category = defaultdict(list)
        for market in active:
            category = self.categorize_market(market)
            volume = self._parse_volume(market)
            market_info = {
                "name": market.get("question", "Unknown"),
                "volume": volume,
                "category": category,
                "url": f"https://polymarket.com/market/{market.get('slug', market.get('id'))}"
            }
            active_by_category[category].append(market_info)

        # 4. 生成洞察和建议
        insights = self._generate_insights(stats, active_by_category)
        recommendations = self._generate_recommendations(stats, active_by_category)

        # 5. 生成推荐市场列表
        top_markets = self._get_top_markets(active_by_category)

        report = DashboardReport(
            generated_at=datetime.now().isoformat(),
            period=f"Last {days} days",
            categories=stats,
            top_markets=top_markets,
            insights=insights,
            recommendations=recommendations
        )

        # 保存报告
        self._save_report(report)

        return report

    def _generate_insights(self, stats: Dict[str, CategoryStats],
                          active_by_category: Dict[str, List]) -> List[str]:
        """生成分析洞察"""
        insights = []

        # 按胜率排序
        sorted_by_yes_rate = sorted(
            [(k, v) for k, v in stats.items() if v.resolved_markets >= 3],
            key=lambda x: x[1].yes_rate,
            reverse=True
        )

        if sorted_by_yes_rate:
            top = sorted_by_yes_rate[[i for i, (_, s) in enumerate(sorted_by_yes_rate) if s.resolved_markets >= 3][0]] if any(s.resolved_markets >= 3 for _, s in sorted_by_yes_rate) else sorted_by_yes_rate[0]
            insights.append(f"【高胜率领域】{top[0]} 的 YES 胜率为 {top[1].yes_rate:.1%}")

        # 按交易量排序
        sorted_by_volume = sorted(
            [(k, v) for k, v in stats.items()],
            key=lambda x: x[1].total_volume,
            reverse=True
        )

        if sorted_by_volume:
            top_vol = sorted_by_volume[0]
            insights.append(f"【高交易量】{top_vol[0]} 总交易量 ${top_vol[1].total_volume:,.0f}")

        # 分析价格分布
        for category, stat in stats.items():
            if stat.resolved_markets >= 5:
                if stat.avg_yes_price > 0.7:
                    insights.append(f"【高概率倾向】{category} 结算时 YES 平均价格 {stat.avg_yes_price:.2f}")
                elif stat.avg_yes_price < 0.3:
                    insights.append(f"【低概率倾向】{category} 结算时 YES 平均价格 {stat.avg_yes_price:.2f}")

        return insights[:5]

    def _generate_recommendations(self, stats: Dict[str, CategoryStats],
                                  active_by_category: Dict[str, List]) -> List[str]:
        """生成投资建议"""
        recommendations = []

        # 基于历史胜率的建议
        for category, stat in stats.items():
            if stat.resolved_markets < 3:
                continue

            if stat.yes_rate > 0.65:
                recommendations.append(f"[{category}] 历史 YES 胜率高({stat.yes_rate:.0%})，可考虑跟随多数派")
            elif stat.yes_rate < 0.35:
                recommendations.append(f"[{category}] 历史 YES 胜率低({stat.yes_rate:.0%})，逆向思考可能有机会")
            else:
                recommendations.append(f"[{category}] 历史数据均衡({stat.yes_rate:.0%})，需要更多分析")

        # 基于活跃度的建议
        for category, markets in active_by_category.items():
            if len(markets) > 3:
                total_vol = sum(m["volume"] for m in markets)
                recommendations.append(f"[{category}] 当前有 {len(markets)} 个活跃市场，总交易量 ${total_vol:,.0f}")

        return recommendations[:5]

    def _get_top_markets(self, active_by_category: Dict[str, List]) -> List[Dict]:
        """获取推荐关注的活跃市场"""
        all_markets = []
        for category, markets in active_by_category.items():
            for market in markets:
                all_markets.append({
                    **market,
                    "category": category
                })

        # 按交易量排序
        sorted_markets = sorted(all_markets, key=lambda x: x["volume"], reverse=True)

        return sorted_markets[:20]

    def _save_report(self, report: DashboardReport):
        """保存报告"""
        filename = f"{self.cache_dir}/dashboard_report.json"
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"Report saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")

    def print_dashboard(self, report: DashboardReport = None):
        """
        打印仪表盘报告（终端友好格式）

        Args:
            report: 报告对象，如果为 None 则重新生成
        """
        if report is None:
            report = self.generate_dashboard_report()

        print("\n" + "=" * 70)
        print("  POLYMARKET 市场分析仪表盘")
        print("=" * 70)
        print(f"  生成时间: {report.generated_at[:19]}")
        print(f"  分析周期: {report.period}")
        print("=" * 70)

        # 分类统计
        print("\n【各领域历史表现】")
        print("-" * 70)
        print(f"{'领域':<15} {'市场数':<8} {'已结算':<8} {'YES胜率':<12} {'总交易量':<15}")
        print("-" * 70)

        sorted_stats = sorted(
            report.categories.items(),
            key=lambda x: x[1].total_volume,
            reverse=True
        )

        for category, stat in sorted_stats:
            yes_rate = f"{stat.yes_rate:.1%}" if stat.resolved_markets > 0 else "N/A"
            volume_str = f"${stat.total_volume:,.0f}" if stat.total_volume > 0 else "-"

            print(f"{category:<15} {stat.total_markets:<8} {stat.resolved_markets:<8} {yes_rate:<12} {volume_str:<15}")

        # Top 活跃市场
        print("\n\n【活跃市场 Top 10】")
        print("-" * 70)

        for i, market in enumerate(report.top_markets[:10], 1):
            vol = f"${market['volume']:,.0f}" if market['volume'] > 0 else "-"
            name = market['name'][:50] + "..." if len(market['name']) > 50 else market['name']
            print(f"{i:2}. [{market['category']:<12}] {name}")
            print(f"    交易量: {vol:<15} | {market['url']}")

        # 洞察
        print("\n\n【核心洞察】")
        print("-" * 70)
        for insight in report.insights:
            print(f"  • {insight}")

        # 建议
        print("\n\n【策略建议】")
        print("-" * 70)
        for rec in report.recommendations:
            print(f"  • {rec}")

        print("\n" + "=" * 70)

    def get_category_summary(self, category: str) -> Dict:
        """
        获取指定领域的详细摘要

        Args:
            category: 领域名称

        Returns:
            领域详细数据
        """
        if category not in self.category_stats:
            return {}

        stat = self.category_stats[category]
        return {
            "category": category,
            "total_markets": stat.total_markets,
            "resolved_markets": stat.resolved_markets,
            "yes_rate": stat.yes_rate,
            "no_rate": stat.no_rate,
            "total_volume": stat.total_volume,
            "avg_volume": stat.avg_volume,
            "avg_yes_price": stat.avg_yes_price,
            "avg_no_price": stat.avg_no_price
        }

    def analyze_trending_keywords(self, markets: List[Dict] = None) -> Dict[str, int]:
        """
        分析热门关键词

        Args:
            markets: 市场列表，默认使用活跃市场

        Returns:
            关键词频率统计
        """
        if markets is None:
            markets = self.active_markets

        keyword_counts = defaultdict(int)

        # 定义要统计的关键词
        keywords = [
            "election", "trump", "biden", "harris", "crypto", "bitcoin", "inflation",
            "fed", "rate", "war", "nft", "ai", "climate", "space", "olympic",
            "super bowl", "world cup", "oscar", "gdp", "recession", "jobs"
        ]

        for market in markets:
            name = (market.get("question", "") + " " + market.get("description", "")).lower()
            for keyword in keywords:
                if keyword.lower() in name:
                    keyword_counts[keyword] += 1

        return dict(sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True))

    def generate_strategy_config(
        self,
        name: str = "",
        description: str = "",
        focus_categories: List[str] = None,
        days: int = 30,
        save_path: str = "strategy_config.json"
    ) -> StrategyConfig:
        """
        生成策略配置文件

        此方法是分析模块的核心输出。
        根据历史分析生成可执行的策略配置，保存到 JSON 文件。

        Args:
            name: 策略名称
            description: 策略描述
            focus_categories: 关注的领域列表，如果为 None 则自动选择高胜率领域
            days: 历史分析天数
            save_path: 保存路径

        Returns:
            StrategyConfig 对象
        """
        logger.info(f"Generating strategy config: {name}")

        # 1. 获取历史数据进行分析
        resolved = self.get_resolved_markets(days=days)
        active = self.get_active_markets(limit=100)

        # 2. 计算各领域统计
        stats = self.calculate_category_stats(resolved)

        # 3. 根据分析结果确定关注的领域
        if focus_categories is None:
            # 自动选择：优先选择高胜率、高交易量的领域
            sorted_by_score = []
            for category, stat in stats.items():
                if stat.resolved_markets < 3:
                    continue
                # 计算综合分数：胜率 * 0.4 + 交易量标准化 * 0.6
                vol_score = min(stat.total_volume / 100000, 1.0) if stat.total_volume > 0 else 0
                score = stat.yes_rate * 0.4 + vol_score * 0.6
                sorted_by_score.append((category, score, stat))

            # 选择分数最高的领域
            sorted_by_score.sort(key=lambda x: x[1], reverse=True)
            focus_categories = [item[0] for item in sorted_by_score[:3]]

        logger.info(f"Focus categories: {focus_categories}")

        # 4. 生成市场过滤条件
        market_filter = MarketFilter(
            categories=focus_categories,
            min_volume=1000,  # 最小交易量 $1000
            max_age_days=days,
            keywords=[]
        )

        # 5. 根据胜率分析生成交易条件
        # 获取平均胜率用于设置止盈止损
        avg_yes_rate = 0.5
        if stats:
            valid_stats = [s.yes_rate for s in stats.values() if s.resolved_markets >= 3]
            if valid_stats:
                avg_yes_rate = sum(valid_stats) / len(valid_stats)

        # 高胜率领域：跟随多数派；低胜率领域：考虑逆向
        high_yes_rate_categories = [c for c, s in stats.items()
                                   if s.resolved_markets >= 3 and s.yes_rate > 0.55]

        entry = EntryCondition(
            price_range=(0.2, 0.8),
            require_volume_above=1000.0,
            follow_consensus=len(high_yes_rate_categories) >= len(focus_categories) / 2,
            max_position_size=50.0
        )

        exit = ExitCondition(
            profit_target=0.5,  # 50% 止盈
            stop_loss=0.3,  # 30% 止损
            time_limit_hours=168,  # 7天
            auto_close_on_resolved=True
        )

        position = PositionRule(
            max_single_position=50.0,
            max_total_exposure=500.0,
            pyramiding_allowed=False,
            pyramiding_step=0.0
        )

        risk = RiskConfig(
            max_daily_loss=100.0,
            max_trades_per_day=10,
            correlation_check=True,
            circuit_breaker=True
        )

        # 6. 生成目标市场列表
        target_markets = []
        for market in active:
            category = self.categorize_market(market)
            if category not in focus_categories:
                continue

            volume = self._parse_volume(market)
            if volume < market_filter.min_volume:
                continue

            # 获取价格
            tokens = market.get("tokens", [])
            price = float(tokens[0].get("price", 0.5)) if tokens else 0.5

            # 只添加价格符合条件的市场
            if entry.price_range[0] <= price <= entry.price_range[1]:
                target_markets.append({
                    "market_id": market.get("id", ""),
                    "slug": market.get("slug", ""),
                    "name": market.get("question", "Unknown"),
                    "category": category,
                    "token_id": tokens[0].get("token_id", "") if tokens else "",
                    "current_price": price,
                    "volume_24h": volume,
                    "recommended_action": "BUY" if price < 0.5 else "WATCH",
                    "confidence": abs(0.5 - price) * 2,  # 价格越接近0或1，置信度越高
                    "notes": f"Historical {category} YES rate: {stats.get(category, type('s', (), {'yes_rate': 0.5})()).yes_rate:.1%}"
                })

        # 按置信度排序
        target_markets.sort(key=lambda x: x.get("confidence", 0), reverse=True)

        # 7. 生成洞察
        insights = {
            "analysis_date": datetime.now().isoformat(),
            "period_days": days,
            "categories_analyzed": list(stats.keys()),
            "focus_categories": focus_categories,
            "high_yes_rate_categories": high_yes_rate_categories,
            "category_stats": {
                cat: {
                    "total_markets": stat.total_markets,
                    "resolved": stat.resolved_markets,
                    "yes_rate": stat.yes_rate,
                    "no_rate": stat.no_rate,
                    "total_volume": stat.total_volume
                }
                for cat, stat in stats.items()
            },
            "top_opportunities": [
                {
                    "category": m["category"],
                    "name": m["name"][:50],
                    "price": m["current_price"],
                    "confidence": m["confidence"]
                }
                for m in target_markets[:5]
            ]
        }

        # 8. 创建策略配置
        config = StrategyConfig(
            version="1.0.0",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            name=name or f"Auto-generated {days}-day strategy",
            description=description or f"Strategy focusing on {', '.join(focus_categories)} based on historical analysis",
            market_filter=market_filter,
            entry=entry,
            exit=exit,
            position=position,
            risk=risk,
            target_markets=target_markets[:50],  # 最多50个目标市场
            insights=insights
        )

        # 9. 保存配置
        from .strategy_config import save_strategy_config
        save_strategy_config(config, save_path)

        return config


# ============================================================================
# 交易人分析模块 - Trader Analyzer
# ============================================================================


@dataclass
class TradeMetrics:
    """交易指标"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_volume: float = 0.0
    total_pnl: float = 0.0
    avg_holding_period_hours: float = 0.0
    avg_trade_size: float = 0.0
    avg_price_change: float = 0.0

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def avg_pnl_per_trade(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.total_pnl / self.total_trades


@dataclass
class TraderProfile:
    """交易人画像"""
    address: str
    metrics: TradeMetrics = field(default_factory=TradeMetrics)
    category_distribution: Dict[str, int] = field(default_factory=dict)
    trading_style: str = ""  # "aggressive", "moderate", "conservative"
    avg_entry_price: float = 0.0
    best_category: str = ""
    worst_category: str = ""
    avg_trades_per_day: float = 0.0
    price_bias: str = ""  # "high_probability", "low_probability", "neutral"

    def to_dict(self) -> Dict:
        return {
            "address": self.address,
            "metrics": {
                "total_trades": self.metrics.total_trades,
                "winning_trades": self.metrics.winning_trades,
                "losing_trades": self.metrics.losing_trades,
                "win_rate": f"{self.metrics.win_rate:.1%}",
                "total_volume": f"${self.metrics.total_volume:,.2f}",
                "total_pnl": f"${self.metrics.total_pnl:,.2f}",
                "avg_pnl_per_trade": f"${self.metrics.avg_pnl_per_trade:,.2f}",
                "avg_holding_period_hours": f"{self.metrics.avg_holding_period_hours:.1f}",
                "avg_trade_size": f"${self.metrics.avg_trade_size:,.2f}"
            },
            "category_distribution": self.category_distribution,
            "trading_style": self.trading_style,
            "avg_entry_price": self.avg_entry_price,
            "best_category": self.best_category,
            "worst_category": self.worst_category,
            "avg_trades_per_day": f"{self.avg_trades_per_day:.2f}",
            "price_bias": self.price_bias
        }


class TraderAnalyzer:
    """
    交易人分析器

    功能：
    1. 获取并分析特定交易人的历史交易
    2. 计算关键指标（胜率、ROI、持仓时间等）
    3. 生成交易人画像
    4. 产出优化的跟单参数建议
    """

    def __init__(self):
        self.cache_dir = "market_analysis"
        self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def _make_request(self, url: str, params: Dict = None, timeout: int = 15) -> Optional[Any]:
        """发送 API 请求"""
        try:
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(max_retries=3)
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            response = session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"API request failed: {e}")
            return None

    def categorize_market(self, market: Dict) -> str:
        """分类市场"""
        name = (market.get("question", "") + " " + market.get("description", "")).lower()

        for category, config in DOMAIN_CATEGORIES.items():
            if category == "Other":
                continue
            for keyword in config["keywords"]:
                if keyword.lower() in name:
                    return category
        return "Other"

    def get_trader_trades(self, address: str, days: int = 30, limit: int = 100) -> List[Dict]:
        """
        获取交易人的历史交易

        Args:
            address: 交易人地址
            days: 回溯天数
            limit: 获取数量限制

        Returns:
            交易列表
        """
        url = "https://data-api.polymarket.com/trades"
        params = {
            "user": address,
            "limit": limit
        }

        data = self._make_request(url, params)
        if data is None:
            return []

        trades = data.get('data', []) if isinstance(data, dict) else data

        # 按时间过滤
        cutoff_date = datetime.now() - timedelta(days=days)
        filtered_trades = []

        for trade in trades:
            timestamp = trade.get('timestamp') or trade.get('createdAt') or trade.get('time')
            if timestamp:
                try:
                    if 'T' in timestamp:
                        trade_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        if trade_date >= cutoff_date:
                            filtered_trades.append(trade)
                    else:
                        filtered_trades.append(trade)
                except:
                    filtered_trades.append(trade)
            else:
                filtered_trades.append(trade)

        return filtered_trades[:limit]

    def analyze_trader(self, address: str, days: int = 30) -> TraderProfile:
        """
        分析交易人

        Args:
            address: 交易人地址
            days: 分析回溯天数

        Returns:
            交易人画像
        """
        logger.info(f"Analyzing trader: {address[:10]}... (last {days} days)")

        trades = self.get_trader_trades(address, days=days)

        if not trades:
            logger.warning(f"No trades found for {address[:10]}...")
            return TraderProfile(address=address)

        # 获取市场信息用于分类
        markets = self._get_markets_for_trades(trades)

        # 计算指标
        metrics = self._calculate_metrics(trades, markets)

        # 分析领域分布
        category_dist = self._analyze_category_distribution(trades, markets)

        # 判断交易风格
        style = self._determine_trading_style(metrics, trades)

        # 判断价格倾向
        price_bias = self._analyze_price_bias(trades, markets)

        # 找出最佳/最差领域
        best_cat, worst_cat = self._find_best_worst_categories(category_dist, trades, markets)

        # 计算日均交易数
        unique_days = set()
        for trade in trades:
            timestamp = trade.get('timestamp') or trade.get('createdAt') or ''
            if 'T' in timestamp:
                day = timestamp.split('T')[0]
                unique_days.add(day)
        days_active = max(len(unique_days), 1)
        avg_trades_per_day = len(trades) / days_active

        profile = TraderProfile(
            address=address,
            metrics=metrics,
            category_distribution=category_dist,
            trading_style=style,
            avg_entry_price=self._calc_avg_entry_price(trades),
            best_category=best_cat,
            worst_category=worst_cat,
            avg_trades_per_day=avg_trades_per_day,
            price_bias=price_bias
        )

        # 保存分析结果
        self._save_trader_profile(profile)

        return profile

    def _get_markets_for_trades(self, trades: List[Dict]) -> Dict[str, Dict]:
        """获取交易相关的市场信息"""
        markets = {}

        # 从交易中提取市场ID
        for trade in trades:
            condition_id = trade.get('conditionId') or trade.get('condition_id')
            if not condition_id:
                continue

            if condition_id in markets:
                continue

            # 获取市场信息
            url = "https://gamma-api.polymarket.com/events"
            params = {"id": condition_id}

            data = self._make_request(url, params)
            if data and isinstance(data, dict):
                market = data.get('data', data) if 'data' in data else data
                if market:
                    markets[condition_id] = market

        return markets

    def _calculate_metrics(self, trades: List[Dict], markets: Dict[str, Dict]) -> TradeMetrics:
        """计算交易指标"""
        metrics = TradeMetrics()
        metrics.total_trades = len(trades)

        if not trades:
            return metrics

        total_size = 0
        total_holding_hours = 0
        holding_count = 0
        price_changes = []

        for trade in trades:
            side = trade.get('side', '').upper()
            size = float(trade.get('size', 0) or trade.get('amount', 0))
            price = float(trade.get('price', 0) or trade.get('avgPrice', 0))

            if size <= 0:
                continue

            metrics.total_volume += size
            total_size += size

            # 估算盈亏
            if side == 'BUY':
                metrics.total_pnl += size * (0.5 - price)  # 假设以当前价卖出计算盈亏
            elif side == 'SELL':
                metrics.total_pnl += size * (price - 0.5)

            # 计算价格变化
            if price > 0:
                price_changes.append(price)

            # 持仓时间（如果有）
            timestamp = trade.get('timestamp') or trade.get('createdAt') or ''
            if timestamp:
                try:
                    if 'T' in timestamp:
                        trade_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        # 假设2小时后平仓
                        holding_hours = 2.0
                        total_holding_hours += holding_hours
                        holding_count += 1
                except:
                    pass

        if total_size > 0:
            metrics.avg_trade_size = metrics.total_volume / metrics.total_trades

        if holding_count > 0:
            metrics.avg_holding_period_hours = total_holding_hours / holding_count

        if price_changes:
            metrics.avg_price_change = sum(price_changes) / len(price_changes)

        # 计算胜负
        # 根据交易方向和价格判断
        for trade in trades:
            side = trade.get('side', '').upper()
            price = float(trade.get('price', 0))
            if side == 'BUY' and price < 0.5:
                metrics.winning_trades += 1
            elif side == 'SELL' and price > 0.5:
                metrics.winning_trades += 1
            else:
                metrics.losing_trades += 1

        return metrics

    def _analyze_category_distribution(self, trades: List[Dict], markets: Dict[str, Dict]) -> Dict[str, int]:
        """分析领域分布"""
        distribution = defaultdict(int)

        for trade in trades:
            condition_id = trade.get('conditionId') or trade.get('condition_id')

            if condition_id and condition_id in markets:
                category = self.categorize_market(markets[condition_id])
            else:
                category = "Unknown"

            distribution[category] += 1

        return dict(distribution)

    def _determine_trading_style(self, metrics: TradeMetrics, trades: List[Dict]) -> str:
        """判断交易风格"""
        avg_holding = metrics.avg_holding_period_hours
        avg_size = metrics.avg_trade_size
        win_rate = metrics.win_rate

        # 根据持仓时间和仓位判断
        if avg_holding < 4 and avg_size > 50:
            return "aggressive"  # 激进型：短持仓、大仓位
        elif avg_holding > 48 and avg_size < 20:
            return "conservative"  # 保守型：长持仓、小仓位
        else:
            return "moderate"  # 均衡型

    def _analyze_price_bias(self, trades: List[Dict], markets: Dict[str, Dict]) -> str:
        """分析价格倾向（高概率倾向还是低概率倾向）"""
        high_price_trades = 0  # 价格 > 0.5
        low_price_trades = 0  # 价格 < 0.5

        for trade in trades:
            price = float(trade.get('price', 0) or trade.get('avgPrice', 0))
            if price > 0.5:
                high_price_trades += 1
            elif price < 0.5:
                low_price_trades += 1

        if high_price_trades > low_price_trades * 1.5:
            return "high_probability"  # 高概率倾向（买YES）
        elif low_price_trades > high_price_trades * 1.5:
            return "low_probability"  # 低概率倾向（买NO）
        else:
            return "neutral"  # 均衡

    def _find_best_worst_categories(
        self,
        category_dist: Dict[str, int],
        trades: List[Dict],
        markets: Dict[str, Dict]
    ) -> Tuple[str, str]:
        """找出最佳和最差领域"""
        category_returns = {}

        for trade in trades:
            condition_id = trade.get('conditionId') or trade.get('condition_id')
            side = trade.get('side', '').upper()
            price = float(trade.get('price', 0))

            if condition_id not in markets:
                continue

            category = self.categorize_market(markets[condition_id])

            if category not in category_returns:
                category_returns[category] = []

            # 估算收益
            if side == 'BUY':
                category_returns[category].append(0.5 - price)
            else:
                category_returns[category].append(price - 0.5)

        best_cat = ""
        worst_cat = ""
        best_return = float('-inf')
        worst_return = float('inf')

        for cat, returns in category_returns.items():
            if not returns:
                continue
            avg_return = sum(returns) / len(returns)
            if avg_return > best_return:
                best_return = avg_return
                best_cat = cat
            if avg_return < worst_return:
                worst_return = avg_return
                worst_cat = cat

        return best_cat, worst_cat

    def _calc_avg_entry_price(self, trades: List[Dict]) -> float:
        """计算平均入场价格"""
        prices = []
        for trade in trades:
            price = float(trade.get('price', 0) or trade.get('avgPrice', 0))
            if price > 0:
                prices.append(price)

        if prices:
            return sum(prices) / len(prices)
        return 0.0

    def _save_trader_profile(self, profile: TraderProfile):
        """保存交易人画像"""
        filename = f"{self.cache_dir}/trader_{profile.address[:8]}.json"
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"Trader profile saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to save trader profile: {e}")

    def get_copy_trading_recommendations(self, profile: TraderProfile) -> Dict[str, Any]:
        """
        根据交易人画像生成跟单建议

        Returns:
            跟单参数建议
        """
        style = profile.trading_style
        price_bias = profile.price_bias

        # 基于交易风格推荐配置
        if style == "aggressive":
            return {
                "copy_amount": 5.0,  # 小仓位试探
                "max_copy_size": 20.0,
                "time_window": 180,  # 更短的时间窗口
                "allow_dca": False,  # 不加仓
                "rationale": "激进型交易者，建议小仓位、短期跟随"
            }
        elif style == "conservative":
            return {
                "copy_amount": 20.0,
                "max_copy_size": 100.0,
                "time_window": 600,
                "allow_dca": True,
                "rationale": "保守型交易者，建议大仓位、长期跟随、允许加仓"
            }
        else:  # moderate
            return {
                "copy_amount": 10.0,
                "max_copy_size": 50.0,
                "time_window": 300,
                "allow_dca": False,
                "rationale": "均衡型交易者，建议中等参数"
            }

    def print_trader_report(self, profile: TraderProfile):
        """打印交易人分析报告"""
        print("\n" + "=" * 70)
        print("  交易人分析报告")
        print("=" * 70)

        print(f"\n【基本信息】")
        print(f"  地址: {profile.address}")
        print(f"  分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        m = profile.metrics
        print(f"\n【核心指标】")
        print(f"  总交易数: {m.total_trades}")
        print(f"  胜率: {m.win_rate:.1%}")
        print(f"  总交易量: ${m.total_volume:,.2f}")
        print(f"  平均每笔盈亏: ${m.avg_pnl_per_trade:,.2f}")
        print(f"  平均持仓时间: {m.avg_holding_period_hours:.1f} 小时")
        print(f"  日均交易数: {profile.avg_trades_per_day:.1f}")

        print(f"\n【交易风格】")
        style_names = {
            "aggressive": "激进型",
            "moderate": "均衡型",
            "conservative": "保守型"
        }
        print(f"  风格: {style_names.get(profile.trading_style, profile.trading_style)}")

        bias_names = {
            "high_probability": "高概率倾向（追涨）",
            "low_probability": "低概率倾向（抄底）",
            "neutral": "均衡"
        }
        print(f"  价格倾向: {bias_names.get(profile.price_bias, profile.price_bias)}")

        print(f"\n【领域分布】")
        for cat, count in sorted(profile.category_distribution.items(), key=lambda x: -x[1]):
            pct = count / sum(profile.category_distribution.values()) * 100
            print(f"  {cat}: {count} 笔 ({pct:.0f}%)")

        print(f"\n【擅长领域】")
        print(f"  最佳: {profile.best_category or 'N/A'}")
        print(f"  最差: {profile.worst_category or 'N/A'}")

        # 跟单建议
        recommendations = self.get_copy_trading_recommendations(profile)
        print(f"\n【跟单建议】")
        print(f"  建议跟单金额: ${recommendations['copy_amount']}")
        print(f"  最大跟单金额: ${recommendations['max_copy_size']}")
        print(f"  时间窗口: {recommendations['time_window']} 秒")
        print(f"  允许 DCA: {'是' if recommendations['allow_dca'] else '否'}")
        print(f"  理由: {recommendations['rationale']}")

        print("\n" + "=" * 70)
