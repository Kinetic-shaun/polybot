#!/usr/bin/env python3
"""
Market Analyzer - 市场分析独立入口

功能：
1. 市场分析 - 分析历史数据，计算各领域胜率
2. 策略配置生成 - 生成可执行的策略配置
3. 交易人分析 - 分析特定交易人的交易策略

与执行模块完全解耦：
- 分析模块只负责分析和生成配置
- 执行模块负责根据配置执行交易
- 两者通过 strategy_config.json 连接

使用示例：
  python analyze_market.py                    # 默认市场分析
  python analyze_market.py --days 7          # 最近7天
  python analyze_market.py --focus Politics  # 只分析Politics

  python analyze_market.py --trader 0x...   # 分析交易人
  python analyze_market.py --trader 0x... --days 30  # 分析交易人30天历史
"""
import sys
import json
from datetime import datetime
from typing import List, Dict, Any

from polymarket_bot.analyzer import PolymarketAnalyzer, TraderAnalyzer, DOMAIN_CATEGORIES
from polymarket_bot.strategy_config import (
    StrategyConfig, save_strategy_config, load_strategy_config
)


def print_help():
    """打印帮助信息"""
    print("""
======================================================================
                    POLYMARKET 市场分析器
======================================================================

用法:
  python analyze_market.py [命令] [选项]

命令:
  (无命令)        - 默认市场分析（分析各领域胜率）
  trader          - 交易人分析模式

选项:
  --days N             分析最近N天历史数据 (默认: 30)
  --focus CATEGORY     只分析指定领域 (如: Crypto, Politics)
  --config-only        只生成策略配置，不输出详细报告
  --show-config        显示当前策略配置内容
  --load-config        加载并显示已有配置
  --help               显示此帮助信息

交易人分析选项:
  --trader ADDRESS     分析指定交易人地址
  --days N             分析最近N天 (默认: 30)

可用领域:
  Politics       - 政治相关预测
  Crypto         - 加密货币相关预测
  Sports         - 体育竞技预测
  Economics      - 宏观经济预测
  Entertainment  - 娱乐文化预测
  Science        - 科学与技术预测

输出:
  - 市场分析: 仪表盘报告 + strategy_config.json
  - 交易人分析: 交易人画像报告

示例:
  # 市场分析
  python analyze_market.py                           # 默认分析
  python analyze_market.py --days 7 --focus Crypto   # Crypto最近7天
  python analyze_market.py --config-only             # 只生成配置

  # 交易人分析
  python analyze_market.py --trader 0x96489abcb9f583d6835c8ef95ffc923d05a86825
  python analyze_market.py --trader 0x... --days 30  # 分析30天历史

======================================================================
    """)


def print_dashboard(analyzer: PolymarketAnalyzer, report: Dict):
    """打印仪表盘报告"""
    print("\n" + "=" * 70)
    print("  POLYMARKET 市场分析仪表盘")
    print("=" * 70)

    generated_at = report.get("generated_at", "")
    period = report.get("period", "")

    print(f"  生成时间: {generated_at[:19] if generated_at else 'N/A'}")
    print(f"  分析周期: {period}")
    print("=" * 70)

    # 分类统计
    categories = report.get("categories", {})
    if categories:
        print("\n【各领域历史表现】")
        print("-" * 70)
        print(f"{'领域':<15} {'市场数':<8} {'已结算':<8} {'YES胜率':<12} {'总交易量':<15}")
        print("-" * 70)

        sorted_cats = sorted(
            categories.items(),
            key=lambda x: x[1].get("total_volume", 0) if isinstance(x[1], dict) else 0,
            reverse=True
        )

        for cat_name, cat_data in sorted_cats:
            if not isinstance(cat_data, dict):
                continue
            resolved = cat_data.get("resolved_markets", 0)
            yes_rate_str = cat_data.get("yes_rate", "N/A")
            volume = cat_data.get("total_volume", 0)
            volume_str = f"${volume:,.0f}" if volume > 0 else "-"

            print(f"{cat_name:<15} {cat_data.get('total_markets', 0):<8} {resolved:<8} {yes_rate_str:<12} {volume_str:<15}")

    # Top 活跃市场
    top_markets = report.get("top_markets", [])
    if top_markets:
        print("\n\n【活跃市场 Top 10】")
        print("-" * 70)

        for i, market in enumerate(top_markets[:10], 1):
            vol = f"${market.get('volume', 0):,.0f}" if market.get('volume', 0) > 0 else "-"
            name = market.get('name', 'Unknown')[:50]
            if len(market.get('name', '')) > 50:
                name += "..."
            print(f"{i:2}. [{market.get('category', 'Other'):<12}] {name}")
            print(f"    交易量: {vol}")

    # 洞察
    insights = report.get("insights", [])
    if insights:
        print("\n\n【核心洞察】")
        print("-" * 70)
        for insight in insights:
            print(f"  • {insight}")

    # 建议
    recommendations = report.get("recommendations", [])
    if recommendations:
        print("\n\n【策略建议】")
        print("-" * 70)
        for rec in recommendations:
            print(f"  • {rec}")

    print("\n" + "=" * 70)


def print_config(config: StrategyConfig):
    """打印策略配置内容"""
    print("\n" + "=" * 70)
    print("  策略配置内容")
    print("=" * 70)

    print(f"\n【基本信息】")
    print(f"  版本: {config.version}")
    print(f"  名称: {config.name}")
    print(f"  描述: {config.description}")

    print(f"\n【市场过滤】")
    print(f"  关注领域: {', '.join(config.market_filter.categories) if config.market_filter.categories else '未设置'}")
    print(f"  最小交易量: ${config.market_filter.min_volume:,.0f}")
    print(f"  最大天数: {config.market_filter.max_age_days} 天")

    print(f"\n【买入条件】")
    print(f"  价格区间: {config.entry.price_range[0]:.0%} - {config.entry.price_range[1]:.0%}")
    print(f"  最小交易量要求: ${config.entry.require_volume_above:,.0f}")
    print(f"  跟随多数派: {'是' if config.entry.follow_consensus else '否'}")
    print(f"  最大仓位: ${config.entry.max_position_size:,.0f}")

    print(f"\n【卖出条件】")
    print(f"  止盈目标: {config.exit.profit_target:.0%}")
    print(f"  止损线: {config.exit.stop_loss:.0%}")
    print(f"  时间限制: {config.exit.time_limit_hours} 小时")
    print(f"  结算自动平仓: {'是' if config.exit.auto_close_on_resolved else '否'}")

    print(f"\n【仓位管理】")
    print(f"  单个最大仓位: ${config.position.max_single_position:,.0f}")
    print(f"  总暴露风险: ${config.position.max_total_exposure:,.0f}")

    print(f"\n【风险管理】")
    print(f"  单日最大亏损: ${config.risk.max_daily_loss:,.0f}")
    print(f"  单日最大交易数: {config.risk.max_trades_per_day}")
    print(f"  熔断机制: {'开启' if config.risk.circuit_breaker else '关闭'}")

    # 目标市场
    target_count = len(config.target_markets)
    if target_count > 0:
        print(f"\n【目标市场】({target_count} 个)")
        for i, market in enumerate(config.target_markets[:5], 1):
            action = market.get("recommended_action", "WATCH")
            conf = market.get("confidence", 0)
            name = market.get("name", "Unknown")[:40]
            print(f"  {i}. [{action}] {name} (置信度: {conf:.2f})")

        if target_count > 5:
            print(f"  ... 还有 {target_count - 5} 个市场")

    # 洞察
    insights = config.insights
    if insights:
        print(f"\n【分析洞察】")
        if "high_yes_rate_categories" in insights:
            high_cats = insights["high_yes_rate_categories"]
            print(f"  高胜率领域: {', '.join(high_cats) if high_cats else '无'}")

        top_ops = insights.get("top_opportunities", [])
        if top_ops:
            print(f"  Top 机会:")
            for op in top_ops[:3]:
                print(f"    - {op.get('category')}: {op.get('name', '')[:30]} (价格: {op.get('price', 0):.2%})")

    print("\n" + "=" * 70)


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("  POLYMARKET 分析器")
    print("=" * 70)

    # 解析参数
    days = 30
    focus_categories = None
    config_only = False
    show_config = False
    load_only = False
    trader_address = None

    for arg in sys.argv[1:]:
        if arg.startswith('--days='):
            days = int(arg.split('=')[1])
        elif arg.startswith('--focus='):
            focus_cat = arg.split('=')[1]
            if focus_cat in DOMAIN_CATEGORIES:
                focus_categories = [focus_cat]
            else:
                print(f"\n错误: 未知领域 '{focus_cat}'")
                print(f"可用领域: {', '.join(DOMAIN_CATEGORIES.keys())}")
                return
        elif arg == '--config-only':
            config_only = True
        elif arg == '--show-config':
            show_config = True
        elif arg == '--load-config':
            load_only = True
        elif arg.startswith('--trader='):
            trader_address = arg.split('=')[1]
        elif arg == '--help':
            print_help()
            return

    # 如果只是加载并显示配置
    if load_only:
        config = load_strategy_config()
        if config:
            print_config(config)
        else:
            print("\n未找到策略配置，请先运行分析生成配置")
            print("  python analyze_market.py")
        return

    # 显示当前配置
    if show_config:
        config = load_strategy_config()
        if config:
            print_config(config)
        else:
            print("\n未找到策略配置，请先运行分析生成配置")
            print("  python analyze_market.py")
        return

    # 交易人分析模式
    if trader_address:
        run_trader_analysis(trader_address, days)
        return

    # 市场分析模式
    run_market_analysis(days, focus_categories, config_only)


def run_trader_analysis(address: str, days: int):
    """运行交易人分析"""
    print(f"\n正在分析交易人: {address[:10]}... (最近 {days} 天)")

    analyzer = TraderAnalyzer()

    try:
        profile = analyzer.analyze_trader(address, days=days)

        if profile.metrics.total_trades == 0:
            print(f"\n未找到该交易人的历史交易记录")
            return

        analyzer.print_trader_report(profile)

        # 生成跟单建议
        recommendations = analyzer.get_copy_trading_recommendations(profile)

        print("\n【基于分析生成的跟单配置】")
        print(f"\n运行跟单:")
        print(f"  python run_bot.py copy \\")
        print(f"    --target-user {address} \\")
        print(f"    --copy-amount {recommendations['copy_amount']:.0f} \\")
        print(f"    --max-copy-size {recommendations['max_copy_size']:.0f} \\")
        print(f"    --time-window {recommendations['time_window']}")

        if recommendations['allow_dca']:
            print(f"    --allow-dca")

        print("\n" + "=" * 70)

    except Exception as e:
        print(f"\n分析出错: {e}")
        import traceback
        traceback.print_exc()


def run_market_analysis(days: int, focus_categories: List[str], config_only: bool):
    """运行市场分析"""
    print(f"\n正在分析最近 {days} 天的市场数据...")
    analyzer = PolymarketAnalyzer()

    try:
        # 生成报告
        report = analyzer.generate_dashboard_report(days=days)
        report_dict = report.to_dict() if hasattr(report, 'to_dict') else report

        # 生成策略配置
        print(f"\n正在生成策略配置...")
        config = analyzer.generate_strategy_config(
            name=f"{days}-Day Analysis Strategy",
            description=f"Auto-generated strategy based on {days}-day historical analysis",
            focus_categories=focus_categories,
            days=days,
            save_path="strategy_config.json"
        )

        # 输出仪表盘
        if not config_only:
            print_dashboard(analyzer, report_dict)

        # 显示配置
        print_config(config)

        print("\n" + "=" * 70)
        print("  分析完成!")
        print("=" * 70)
        print(f"\n策略配置已保存到: strategy_config.json")
        print(f"执行模块可以使用此配置进行交易")
        print("\n执行交易:")
        print("  python run_bot.py copy continuous")
        print("\n" + "=" * 70)

    except Exception as e:
        print(f"\n分析出错: {e}")
        import traceback
        traceback.print_exc()
        return


if __name__ == "__main__":
    main()
