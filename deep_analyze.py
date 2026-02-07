#!/usr/bin/env python3
"""
Deep Trader Analyzer - 深度交易人分析

功能：
1. 持仓分析 - 通过交易记录推断当前持仓
2. 时间模式 - 分析交易频率的日内模式
3. 盈亏估算 - 基于当前价格估算盈亏
4. 市场偏好 - 分析选择市场的标准
5. 入场分析 - 入场价格分布
6. 风险评估 - 生成模拟参数

使用：
python deep_analyze.py --trader 0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d
"""
import sys
import json
import requests
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import os

# 配置
MARKETS_API = "https://gamma-api.polymarket.com/events"
DATA_API = "https://data-api.polymarket.com/trades"


@dataclass
class Position:
    """持仓"""
    token_id: str
    market_name: str
    side: str  # YES or NO
    size: float
    avg_price: float
    first_trade_time: datetime
    last_trade_time: datetime
    trade_count: int
    current_price: Optional[float] = None

    @property
    def unrealized_pnl(self) -> float:
        if not self.current_price:
            return 0
        if self.side == "YES":
            return (self.current_price - self.avg_price) * self.size
        else:  # NO position
            return (self.avg_price - self.current_price) * self.size

    @property
    def pnl_pct(self) -> float:
        if not self.current_price or self.avg_price == 0:
            return 0
        if self.side == "YES":
            return (self.current_price - self.avg_price) / self.avg_price
        else:
            return (self.avg_price - self.current_price) / self.avg_price


@dataclass
class DeepAnalysis:
    """深度分析结果"""
    # 基本信息
    address: str
    analyzed_at: str

    # 持仓分析
    positions: List[Dict] = field(default_factory=list)
    total_position_value: float = 0
    total_unrealized_pnl: float = 0

    # 时间模式
    hourly_distribution: Dict[int, int] = field(default_factory=dict)
    busiest_hour: int = 0
    trading_session: str = ""

    # 价格分析
    avg_entry_price: float = 0
    price_distribution: Dict[str, int] = field(default_factory=dict)
    typical_entry_range: Tuple[float, float] = (0, 0)

    # 市场偏好
    markets_traded: int = 0
    unique_markets: Dict[str, int] = field(default_factory=dict)
    concentration_pct: float = 0

    # 交易频率
    avg_trades_per_day: float = 0
    burst_trading: bool = False

    # 风险评估
    risk_level: str = ""
    max_single_position_pct: float = 0
    correlation_risk: str = ""

    # 模拟参数建议
    recommended_copy_amount: float = 0
    recommended_max_copy: float = 0
    recommended_time_window: int = 0
    recommended_dca: bool = False
    simulation_notes: List[str] = field(default_factory=list)


class DeepTraderAnalyzer:
    """深度交易人分析器"""

    def __init__(self, address: str, days: int = 30):
        self.address = address
        self.days = days
        self.trades: List[Dict] = []
        self.positions: Dict[str, Position] = {}

    def fetch_trades(self) -> List[Dict]:
        """获取交易"""
        print(f"📥 获取交易数据...")
        params = {"user": self.address, "limit": 200}

        try:
            response = requests.get(DATA_API, params=params, timeout=15)
            data = response.json()
            self.trades = data.get('data', []) if isinstance(data, dict) else data
            print(f"   获取到 {len(self.trades)} 笔交易")
            return self.trades
        except Exception as e:
            print(f"   获取交易失败: {e}")
            return []

    def build_positions(self) -> Dict[str, Position]:
        """构建持仓（通过交易记录推断）"""
        print(f"📊 构建持仓...")

        # 按市场分组
        market_trades = defaultdict(list)
        for trade in self.trades:
            market_id = trade.get('conditionId', '')
            if market_id:
                market_trades[market_id].append(trade)

        # 构建每市场的持仓
        for market_id, trades in market_trades.items():
            if not trades:
                continue

            # 按时间排序
            trades.sort(key=lambda x: int(x.get('timestamp', 0)))

            # 基本信息
            first_trade = trades[0]
            last_trade = trades[-1]
            market_name = first_trade.get('title', first_trade.get('name', 'Unknown'))

            # 计算持仓 (BUY = YES position, SELL = closing)
            yes_size = sum(float(t.get('size', 0)) for t in trades if t.get('side', '').upper() == 'BUY')
            no_size = sum(float(t.get('size', 0)) for t in trades if t.get('side', '').upper() == 'SELL')

            # 计算平均价格（加权平均）
            yes_total = 0.0
            yes_weighted = 0.0
            no_total = 0.0
            no_weighted = 0.0

            for t in trades:
                side = t.get('side', '').upper()
                size = float(t.get('size', 0))
                price = t.get('price')
                if price:
                    try:
                        p = float(price)
                        if side == 'BUY':
                            yes_total += size
                            yes_weighted += p * size
                        elif side == 'SELL':
                            no_total += size
                            no_weighted += p * size
                    except (ValueError, TypeError):
                        pass

            yes_avg = yes_weighted / yes_total if yes_total > 0 else 0
            no_avg = no_weighted / no_total if no_total > 0 else 0

            # 保存持仓
            if yes_size > 0:
                self.positions[market_id] = Position(
                    token_id=market_id,
                    market_name=market_name,
                    side="YES",
                    size=yes_size,
                    avg_price=yes_avg,
                    first_trade_time=datetime.fromtimestamp(int(first_trade.get('timestamp', 0))),
                    last_trade_time=datetime.fromtimestamp(int(last_trade.get('timestamp', 0))),
                    trade_count=len(trades)
                )

            if no_size > 0:
                self.positions[market_id] = Position(
                    token_id=market_id,
                    market_name=market_name,
                    side="NO",
                    size=no_size,
                    avg_price=no_avg,
                    first_trade_time=datetime.fromtimestamp(int(first_trade.get('timestamp', 0))),
                    last_trade_time=datetime.fromtimestamp(int(last_trade.get('timestamp', 0))),
                    trade_count=len(trades)
                )

        print(f"   推断出 {len(self.positions)} 个持仓")
        return self.positions

    def fetch_current_prices(self):
        """获取当前价格（用于计算盈亏）"""
        print(f"💰 获取当前价格...")

        if not self.positions:
            return

        # 获取活跃市场
        try:
            response = requests.get(MARKETS_API, params={"active": "true", "closed": "false", "limit": 50}, timeout=10)
            data = response.json()
            markets = data.get('data', []) if isinstance(data, dict) else data

            # 建立价格映射
            price_map = {}
            for market in markets:
                condition_id = market.get('id', '')
                tokens = market.get('tokens', [])
                if tokens:
                    price_map[condition_id] = float(tokens[0].get('price', 0))

            # 更新持仓价格
            for pos_id, position in self.positions.items():
                if pos_id in price_map:
                    position.current_price = price_map[pos_id]

            print(f"   更新了 {sum(1 for p in self.positions.values() if p.current_price)} 个持仓价格")
        except Exception as e:
            print(f"   获取价格失败: {e}")

    def analyze_time_patterns(self) -> Dict[str, Any]:
        """分析时间模式"""
        print(f"⏰ 分析时间模式...")

        hourly = defaultdict(int)
        timestamps = []

        for trade in self.trades:
            ts = trade.get('timestamp')
            if ts:
                try:
                    dt = datetime.fromtimestamp(int(ts))
                    hourly[dt.hour] += 1
                    timestamps.append(dt)
                except:
                    pass

        # 找出最活跃时段
        busiest_hour = max(hourly.items(), key=lambda x: x[1])[0] if hourly else 0

        # 判断交易时段
        if 6 <= busiest_hour < 12:
            session = "早间 (6AM-12PM)"
        elif 12 <= busiest_hour < 18:
            session = "下午 (12PM-6PM)"
        elif 18 <= busiest_hour < 24:
            session = "晚间 (6PM-12AM)"
        else:
            session = "深夜/凌晨 (12AM-6AM)"

        # 检测是否为爆发式交易
        if timestamps:
            timestamps.sort()
            first = timestamps[0]
            last = timestamps[-1]
            hours_span = (last - first).total_seconds() / 3600
            burst_trading = hours_span < 1  # 1小时内完成大部分交易

        return {
            "hourly_distribution": dict(hourly),
            "busiest_hour": busiest_hour,
            "trading_session": session,
            "burst_trading": burst_trading,
            "total_trading_hours": hours_span if 'hours_span' in dir() else 0
        }

    def analyze_price_distribution(self) -> Dict[str, Any]:
        """分析入场价格分布"""
        print(f"📈 分析价格分布...")

        price_ranges = {
            "<10%": 0,
            "10-30%": 0,
            "30-50%": 0,
            "50-70%": 0,
            "70-90%": 0,
            ">90%": 0
        }

        prices = []
        for trade in self.trades:
            price = trade.get('price')
            if price:
                try:
                    p = float(price)
                    prices.append(p)

                    if p < 0.1:
                        price_ranges["<10%"] += 1
                    elif p < 0.3:
                        price_ranges["10-30%"] += 1
                    elif p < 0.5:
                        price_ranges["30-50%"] += 1
                    elif p < 0.7:
                        price_ranges["50-70%"] += 1
                    elif p < 0.9:
                        price_ranges["70-90%"] += 1
                    else:
                        price_ranges[">90%"] += 1
                except:
                    pass

        if prices:
            avg_price = sum(prices) / len(prices)
            typical_low = min(prices)
            typical_high = max(prices)
        else:
            avg_price = 0
            typical_low = 0
            typical_high = 0

        return {
            "price_distribution": price_ranges,
            "avg_entry_price": avg_price,
            "typical_range": (typical_low, typical_high),
            "total_price_samples": len(prices)
        }

    def analyze_market_preference(self) -> Dict[str, Any]:
        """分析市场偏好"""
        print(f"🎯 分析市场偏好...")

        markets = defaultdict(int)
        for trade in self.trades:
            title = trade.get('title', trade.get('name', 'Unknown'))
            markets[title] += 1

        total = sum(markets.values())

        # 计算集中度
        if markets:
            sorted_markets = sorted(markets.values(), reverse=True)
            top_3_pct = sum(sorted_markets[:3]) / total * 100
        else:
            top_3_pct = 0

        return {
            "unique_markets": dict(markets),
            "markets_traded": len(markets),
            "concentration_pct": top_3_pct
        }

    def calculate_position_risk(self) -> Dict[str, Any]:
        """计算持仓风险"""
        print(f"⚠️ 计算持仓风险...")

        if not self.positions:
            return {"risk_level": "N/A", "max_position_pct": 0, "correlation_risk": "无持仓", "total_value": 0}

        # 计算总持仓价值
        total_value = sum(p.size * p.avg_price for p in self.positions.values())

        # 计算单市场最大占比
        if total_value > 0:
            max_position = max(p.size * p.avg_price for p in self.positions.values())
            max_pct = max_position / total_value * 100
        else:
            max_pct = 0

        # 判断风险等级
        if max_pct > 80:
            risk_level = "极高 (持仓高度集中)"
        elif max_pct > 50:
            risk_level = "高 (持仓集中)"
        elif max_pct > 30:
            risk_level = "中等 (分散尚可)"
        else:
            risk_level = "低 (分散良好)"

        # 关联风险（如果多个持仓是同一市场）
        market_groups = defaultdict(float)
        for pos in self.positions.values():
            # 简化：如果名称包含相似关键词，认为是关联市场
            market_groups[pos.market_name[:20]] += pos.size * pos.avg_price

        if len(market_groups) > 1:
            max_group_pct = max(market_groups.values()) / total_value * 100 if total_value > 0 else 0
            if max_group_pct > 70:
                correlation_risk = "高 (多关联市场同时持仓)"
            else:
                correlation_risk = "低"
        else:
            correlation_risk = "无关联风险"

        return {
            "risk_level": risk_level,
            "max_position_pct": max_pct,
            "correlation_risk": correlation_risk,
            "total_value": total_value
        }

    def generate_simulation_params(self, time_analysis: Dict,
                                  price_analysis: Dict,
                                  position_risk: Dict) -> Dict[str, Any]:
        """生成模拟参数"""
        print(f"🎮 生成模拟参数...")

        # 基于分析结果生成参数

        # 时间窗口：基于交易模式
        if time_analysis.get("burst_trading"):
            time_window = 180  # 爆发式交易需要更短的时间窗口
        elif time_analysis.get("busiest_hour", 0) in [0, 1, 2, 3, 4, 5]:
            time_window = 600  # 深夜交易可能需要更长等待
        else:
            time_window = 300  # 标准窗口

        # 金额：基于持仓风险
        risk_level = position_risk.get("risk_level", "")
        if "极高" in risk_level or "高" in risk_level:
            copy_amount = 5
            max_copy = 20
            allow_dca = False
        elif "低" in risk_level:
            copy_amount = 15
            max_copy = 75
            allow_dca = True
        else:
            copy_amount = 10
            max_copy = 50
            allow_dca = False

        # 生成模拟备注
        notes = []

        if time_analysis.get("burst_trading"):
            notes.append("⚠️ 该交易人为爆发式交易风格，需密切关注快速跟单")

        if position_risk.get("correlation_risk", "").startswith("高"):
            notes.append("⚠️ 多关联市场同时持仓，需注意系统性风险")

        avg_price = price_analysis.get("avg_entry_price", 0)
        if avg_price > 0.7:
            notes.append("💡 平均入场价格较高(>70%)，需评估当前价格是否已过高")
        elif avg_price < 0.3:
            notes.append("💡 平均入场价格较低(<30%)，偏好抄底策略")

        return {
            "copy_amount": copy_amount,
            "max_copy": max_copy,
            "time_window": time_window,
            "allow_dca": allow_dca,
            "notes": notes
        }

    def analyze(self) -> DeepAnalysis:
        """执行完整分析"""
        print("=" * 70)
        print(f"  深度交易人分析")
        print("=" * 70)
        print(f"  地址: {self.address}")
        print(f"  分析天数: {self.days} 天")
        print("=" * 70)

        # 1. 获取数据
        self.fetch_trades()
        if not self.trades:
            print("未获取到交易数据")
            return None

        # 2. 构建持仓
        self.build_positions()

        # 3. 获取当前价格
        self.fetch_current_prices()

        # 4. 各维度分析
        time_analysis = self.analyze_time_patterns()
        price_analysis = self.analyze_price_distribution()
        market_analysis = self.analyze_market_preference()
        position_risk = self.calculate_position_risk()

        # 5. 生成模拟参数
        sim_params = self.generate_simulation_params(
            time_analysis, price_analysis, position_risk
        )

        # 6. 汇总分析结果
        analysis = DeepAnalysis(
            address=self.address,
            analyzed_at=datetime.now().isoformat(),

            # 持仓
            positions=[{
                "market_name": p.market_name,
                "side": p.side,
                "size": p.size,
                "avg_price": p.avg_price,
                "current_price": p.current_price,
                "unrealized_pnl": p.unrealized_pnl,
                "pnl_pct": p.pnl_pct
            } for p in self.positions.values()],
            total_position_value=sum(p.size * p.avg_price for p in self.positions.values()),
            total_unrealized_pnl=sum(p.unrealized_pnl for p in self.positions.values()),

            # 时间模式
            hourly_distribution=time_analysis["hourly_distribution"],
            busiest_hour=time_analysis["busiest_hour"],
            trading_session=time_analysis["trading_session"],
            burst_trading=time_analysis.get("burst_trading", False),

            # 价格
            avg_entry_price=price_analysis["avg_entry_price"],
            price_distribution=price_analysis["price_distribution"],
            typical_entry_range=price_analysis["typical_range"],

            # 市场
            markets_traded=market_analysis["markets_traded"],
            unique_markets=market_analysis["unique_markets"],
            concentration_pct=market_analysis["concentration_pct"],

            # 风险
            risk_level=position_risk["risk_level"],
            max_single_position_pct=position_risk["max_position_pct"],
            correlation_risk=position_risk["correlation_risk"],

            # 模拟参数
            recommended_copy_amount=sim_params["copy_amount"],
            recommended_max_copy=sim_params["max_copy"],
            recommended_time_window=sim_params["time_window"],
            recommended_dca=sim_params["allow_dca"],
            simulation_notes=sim_params["notes"]
        )

        return analysis


def print_analysis_report(analysis: DeepAnalysis):
    """打印分析报告"""
    print("\n" + "=" * 70)
    print("  📊 深度分析报告")
    print("=" * 70)

    # 1. 持仓分析
    print("\n【当前持仓分析】")
    print("-" * 70)
    print(f"  持仓数量: {len(analysis.positions)} 个市场")
    print(f"  持仓总价值: ${analysis.total_position_value:,.2f}")

    if analysis.total_unrealized_pnl > 0:
        print(f"  📈 未实现盈亏: +${analysis.total_unrealized_pnl:,.2f}")
    elif analysis.total_unrealized_pnl < 0:
        print(f"  📉 未实现盈亏: ${analysis.total_unrealized_pnl:,.2f}")
    else:
        print(f"  ➖ 未实现盈亏: $0.00")

    # 显示主要持仓
    if analysis.positions:
        print("\n  主要持仓:")
        sorted_positions = sorted(analysis.positions,
                                   key=lambda x: x.get('size', 0) * x.get('avg_price', 0),
                                   reverse=True)[:5]
        for i, pos in enumerate(sorted_positions, 1):
            pnl_str = f"+${pos['unrealized_pnl']:.2f}" if pos['unrealized_pnl'] > 0 else f"${pos['unrealized_pnl']:.2f}"
            curr_str = f"{pos['current_price']:.2f}" if pos['current_price'] else "N/A"
            print(f"    {i}. {pos['market_name'][:35]}")
            print(f"       {pos['side']} | ${pos['size']:.0f} @ {pos['avg_price']:.2f} | 当前: {curr_str} | P&L: {pnl_str}")

    # 2. 时间模式
    print("\n【交易时间模式】")
    print("-" * 70)
    print(f"  最活跃时段: {analysis.trading_session} ({analysis.busiest_hour}:00)")
    print(f"  爆发式交易: {'是 ⚡' if analysis.burst_trading else '否'}")

    # 显示小时分布
    if analysis.hourly_distribution:
        hours = sorted(analysis.hourly_distribution.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"  Top 5 交易时段:")
        for hour, count in hours:
            print(f"    {hour:02d}:00 - {count} 笔")

    # 3. 价格分布
    print("\n【入场价格分布】")
    print("-" * 70)
    print(f"  平均入场价格: {analysis.avg_entry_price:.2%}")
    print(f"  典型入场区间: {analysis.typical_entry_range[0]:.2%} - {analysis.typical_entry_range[1]:.2%}")

    print("  价格区间分布:")
    for range_name, count in analysis.price_distribution.items():
        pct = count / max(sum(analysis.price_distribution.values()), 1) * 100
        bar = "█" * int(pct / 5)
        print(f"    {range_name:>10}: {count:3} ({pct:5.1f}%) {bar}")

    # 4. 市场偏好
    print("\n【市场偏好】")
    print("-" * 70)
    print(f"  交易市场数: {analysis.markets_traded} 个")
    print(f"  持仓集中度: Top 3 占 {analysis.concentration_pct:.1f}%")

    if analysis.unique_markets:
        sorted_markets = sorted(analysis.unique_markets.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"  交易最多的市场:")
        for name, count in sorted_markets:
            print(f"    - {name[:40]}: {count} 笔")

    # 5. 风险评估
    print("\n【风险评估】")
    print("-" * 70)
    risk_emoji = {"极高": "🔴", "高": "🟠", "中等": "🟡", "低": "🟢"}
    emoji = risk_emoji.get(analysis.risk_level.split(" ")[0], "⚪")
    print(f"  风险等级: {emoji} {analysis.risk_level}")
    print(f"  单市场最大占比: {analysis.max_single_position_pct:.1f}%")
    print(f"  关联风险: {analysis.correlation_risk}")

    # 6. 模拟建议
    print("\n" + "=" * 70)
    print("  🎮 模拟交易参数建议")
    print("=" * 70)

    print(f"\n  建议跟单金额:    ${analysis.recommended_copy_amount}")
    print(f"  最大跟单金额:    ${analysis.recommended_max_copy}")
    print(f"  时间窗口:        {analysis.recommended_time_window} 秒")
    print(f"  允许 DCA:        {'是' if analysis.recommended_dca else '否'}")

    if analysis.simulation_notes:
        print("\n  模拟注意事项:")
        for note in analysis.simulation_notes:
            print(f"    {note}")

    # 7. 执行命令
    print("\n【执行命令】")
    print("-" * 70)
    print(f"\n  python run_bot.py copy \\")
    print(f"    --target-user {analysis.address} \\")
    print(f"    --copy-amount {analysis.recommended_copy_amount} \\")
    print(f"    --max-copy-size {analysis.recommended_max_copy} \\")
    print(f"    --time-window {analysis.recommended_time_window}")
    if analysis.recommended_dca:
        print(f"    --allow-dca")
    print("\n" + "=" * 70)

    return analysis


def main():
    parser = argparse.ArgumentParser(description="深度交易人分析")
    parser.add_argument("--trader", "-t", required=True, help="交易人地址")
    parser.add_argument("--days", "-d", type=int, default=30, help="分析天数")
    parser.add_argument("--save", "-s", action="store_true", help="保存分析结果")

    args = parser.parse_args()

    analyzer = DeepTraderAnalyzer(args.trader, args.days)
    analysis = analyzer.analyze()

    if analysis:
        print_analysis_report(analysis)

        if args.save:
            os.makedirs("market_analysis", exist_ok=True)
            filename = f"market_analysis/deep_analysis_{args.trader[:8]}_{datetime.now().strftime('%Y%m%d')}.json"
            with open(filename, 'w') as f:
                json.dump({
                    "address": analysis.address,
                    "analyzed_at": analysis.analyzed_at,
                    "positions": analysis.positions,
                    "total_value": analysis.total_position_value,
                    "total_unrealized_pnl": analysis.total_unrealized_pnl,
                    "time_pattern": {
                        "busiest_hour": analysis.busiest_hour,
                        "session": analysis.trading_session,
                        "burst_trading": analysis.burst_trading,
                        "hourly_distribution": analysis.hourly_distribution
                    },
                    "price_distribution": analysis.price_distribution,
                    "avg_entry_price": analysis.avg_entry_price,
                    "market_preference": {
                        "markets_traded": analysis.markets_traded,
                        "concentration_pct": analysis.concentration_pct,
                        "unique_markets": analysis.unique_markets
                    },
                    "risk_assessment": {
                        "risk_level": analysis.risk_level,
                        "max_position_pct": analysis.max_single_position_pct,
                        "correlation_risk": analysis.correlation_risk
                    },
                    "simulation_params": {
                        "copy_amount": analysis.recommended_copy_amount,
                        "max_copy": analysis.recommended_max_copy,
                        "time_window": analysis.recommended_time_window,
                        "allow_dca": analysis.recommended_dca,
                        "notes": analysis.simulation_notes
                    }
                }, f, indent=2, default=str)
            print(f"\n📁 分析结果已保存到: {filename}")


if __name__ == "__main__":
    main()
