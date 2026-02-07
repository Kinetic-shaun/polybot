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
            try:
                volume = float(volume)
            except (ValueError, TypeError):
                volume = 0
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

    from polymarket_bot.analyzer import TraderAnalyzer, DOMAIN_CATEGORIES
    from datetime import datetime
    import json

    analyzer = TraderAnalyzer()

    try:
        profile = analyzer.analyze_trader(address, days=days)

        if profile.metrics.total_trades == 0:
            print(f"\n未找到该交易人的历史交易记录")
            return

        trades = analyzer.get_trader_trades(address, days=days, limit=100)

        print('=' * 70)
        print('  POLYMARKET 交易人深度分析')
        print('=' * 70)

        print(f'\n📊 获取到 {len(trades)} 笔交易\n')

        if not trades:
            print('未获取到交易数据')
            return

        # 基础统计
        buy_trades = [t for t in trades if t.get('side', '').upper() == 'BUY']
        sell_trades = [t for t in trades if t.get('side', '').upper() == 'SELL']

        total_size = sum(float(t.get('size', 0)) for t in trades)
        avg_size = total_size / len(trades) if trades else 0

        # 价格统计
        prices = [float(t.get('price', 0)) for t in trades if t.get('price')]
        avg_price = sum(prices) / len(prices) if prices else 0

        # 高价/低价交易
        high_price = [t for t in trades if float(t.get('price', 0)) > 0.5]
        low_price = [t for t in trades if float(t.get('price', 0)) <= 0.5]
        high_pct = len(high_price) / len(trades) * 100 if trades else 0

        print('─' * 70)
        print('【交易概览】')
        print('─' * 70)
        print(f'  总交易数:     {len(trades)}')
        print(f'  买入次数:     {len(buy_trades)} ({len(buy_trades)/len(trades)*100:.0f}%)')
        print(f'  卖出次数:     {len(sell_trades)} ({len(sell_trades)/len(trades)*100:.0f}%)')
        print(f'  总交易金额:   ${total_size:,.2f}')
        print(f'  平均每笔:     ${avg_size:,.2f}')
        print(f'  平均价格:     {avg_price:.2%}')

        print('\n─' * 70)
        print('【价格分布】')
        print('─' * 70)
        high_pct = len(high_price) / len(trades) * 100 if trades else 0
        low_pct = len(low_price) / len(trades) * 100 if trades else 0
        print(f'  高价交易 (>50%): {len(high_price)} ({high_pct:.0f}%)')
        print(f'  低价交易 (<=50%): {len(low_price)} ({low_pct:.0f}%)')

        # 时间分析
        print('\n─' * 70)
        print('【时间分布】')
        print('─' * 70)
        timestamps = []
        for t in trades:
            ts = t.get('timestamp')
            if ts:
                try:
                    dt = datetime.fromtimestamp(int(ts))
                    timestamps.append(dt)
                except:
                    pass

        if timestamps:
            timestamps.sort()
            first_ts = timestamps[0]
            last_ts = timestamps[-1]
            days_span = (last_ts - first_ts).days + 1
            trades_per_day = len(trades) / max(days_span, 1)

            print(f'  交易跨度:    {days_span} 天')
            print(f'  日均交易:    {trades_per_day:.1f} 笔')
            print(f'  最早交易:    {first_ts.strftime("%Y-%m-%d")}')
            print(f'  最新交易:    {last_ts.strftime("%Y-%m-%d")}')

        # 标题分析（提取关键词）
        print('\n─' * 70)
        print('【交易主题分析】')
        print('─' * 70)
        titles = [t.get('title', t.get('name', '')) for t in trades]
        title_counts = {}
        for title in titles:
            if not title:
                continue
            # 简单分类
            title_lower = title.lower()
            category = 'Other'
            for cat, config in DOMAIN_CATEGORIES.items():
                if cat == 'Other':
                    continue
                for kw in config['keywords']:
                    if kw.lower() in title_lower:
                        category = cat
                        break
            title_counts[category] = title_counts.get(category, 0) + 1

        print('  领域分布:')
        for cat, count in sorted(title_counts.items(), key=lambda x: -x[1]):
            pct = count / len(trades) * 100
            print(f'    {cat}: {count} 笔 ({pct:.0f}%)')

        # 显示代表性交易
        print('\n─' * 70)
        print('【代表性交易】')
        print('─' * 70)

        # 按金额排序
        sorted_by_size = sorted(trades, key=lambda x: float(x.get('size', 0)), reverse=True)[:5]
        print('  最大金额交易:')
        for i, t in enumerate(sorted_by_size, 1):
            ts = t.get('timestamp', 'N/A')
            if ts:
                try:
                    dt = datetime.fromtimestamp(int(ts))
                    ts_str = dt.strftime("%m-%d %H:%M")
                except:
                    ts_str = ts
            else:
                ts_str = 'N/A'
            title = t.get('title', t.get('name', 'N/A'))[:35]
            print(f'    {i}. ${t.get("size")} | {t.get("side")} | {t.get("price")} | {ts_str}')
            print(f'       {title}')

        # 策略推断
        print('\n' + '─' * 70)
        print('【交易风格推断】')
        print('─' * 70)

        # 价格倾向
        if high_pct > 60:
            bias = "高概率倾向 (倾向于购买 YES/高价选项)"
        elif low_pct > 60:
            bias = "低概率倾向 (倾向于购买 NO/低价选项)"
        else:
            bias = "均衡 (无明显倾向)"

        print(f'  价格倾向:  {bias}')

        # 仓位风格
        if avg_size > 50:
            size_style = "大仓位 (均值 > $50)"
        elif avg_size < 20:
            size_style = "小仓位 (均值 < $20)"
        else:
            size_style = "中等仓位 ($20-50)"
        print(f'  仓位风格:  {size_style}')

        # 综合风格
        if high_pct > 60 and avg_size > 50:
            overall_style = "激进型 - 追涨、大仓位"
        elif low_pct > 60 and avg_size < 20:
            overall_style = "保守型 - 抄底、小仓位"
        elif 40 <= high_pct <= 60:
            overall_style = "均衡型 - 价格均衡、仓位适中"
        else:
            overall_style = "混合型"

        print(f'  综合风格:  {overall_style}')

        # 跟单建议
        print('\n' + '=' * 70)
        print('【跟单建议参数】')
        print('=' * 70)

        if overall_style == "激进型 - 追涨、大仓位":
            copy_amount = 5
            max_copy = 20
            time_window = 180
            allow_dca = False
            rationale = "激进型，建议小仓位试探、短期跟随"
        elif overall_style == "保守型 - 抄底、小仓位":
            copy_amount = 20
            max_copy = 100
            time_window = 600
            allow_dca = True
            rationale = "保守型，建议大仓位、长期跟随、允许加仓"
        else:
            copy_amount = 10
            max_copy = 50
            time_window = 300
            allow_dca = False
            rationale = "均衡型，建议中等参数"

        print(f'\n  建议跟单金额:    ${copy_amount}')
        print(f'  最大跟单金额:    ${max_copy}')
        print(f'  时间窗口:        {time_window} 秒')
        print(f'  允许 DCA:        {"是" if allow_dca else "否"}')
        print(f'\n  理由: {rationale}')

        # 命令示例
        print('\n【执行命令】')
        print(f'\n  python run_bot.py copy \\')
        print(f'    --target-user {address} \\')
        print(f'    --copy-amount {copy_amount} \\')
        print(f'    --max-copy-size {max_copy} \\')
        print(f'    --time-window {time_window}')
        if allow_dca:
            print(f'    --allow-dca')
        print('\n' + '=' * 70)

        # 保存分析结果到JSON
        analysis_result = {
            "address": address,
            "analyzed_at": datetime.now().isoformat(),
            "period_days": days,
            "metrics": {
                "total_trades": len(trades),
                "buy_trades": len(buy_trades),
                "sell_trades": len(sell_trades),
                "total_volume": total_size,
                "avg_trade_size": avg_size,
                "avg_price": avg_price
            },
            "price_distribution": {
                "high_price_count": len(high_price),
                "low_price_count": len(low_price),
                "high_pct": high_pct
            },
            "category_distribution": title_counts,
            "style": {
                "price_bias": bias,
                "position_style": size_style,
                "overall_style": overall_style
            },
            "recommendations": {
                "copy_amount": copy_amount,
                "max_copy_size": max_copy,
                "time_window": time_window,
                "allow_dca": allow_dca,
                "rationale": rationale
            }
        }

        # 保存到文件
        result_file = f"market_analysis/trader_{address[:8]}_analysis.json"
        import os
        os.makedirs("market_analysis", exist_ok=True)
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(analysis_result, f, indent=2, ensure_ascii=False)
        print(f"\n📁 分析结果已保存到: {result_file}")

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
