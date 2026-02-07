import requests
from datetime import datetime, timezone, timedelta

def convert_to_cst(timestamp_raw):
    """
    将时间戳或ISO时间字符串转换为中国标准时间 (UTC+8)
    """
    if not timestamp_raw:
        return "未知时间"
    
    # 定义中国时区 (UTC+8)
    china_tz = timezone(timedelta(hours=8))
    
    dt_obj = None
    try:
        # 尝试情况1: Unix 时间戳 (字符串或数字)，例如 "1635331200"
        ts_float = float(timestamp_raw)
        dt_obj = datetime.fromtimestamp(ts_float, timezone.utc)
    except (ValueError, TypeError):
        # 尝试情况2: ISO 8601 字符串，例如 "2023-10-27T10:00:00Z"
        try:
            # 处理可能带有的 'Z' 结尾
            if isinstance(timestamp_raw, str):
                timestamp_raw = timestamp_raw.replace('Z', '+00:00')
            dt_obj = datetime.fromisoformat(timestamp_raw)
        except Exception:
            return str(timestamp_raw) # 转换失败返回原值

    # 转换为中国时间并格式化
    return dt_obj.astimezone(china_tz).strftime('%Y-%m-%d %H:%M:%S (CST)')

# ================= 主逻辑 =================

# 使用 Session 可以复用 TCP 连接，显著提高循环请求的速度
session = requests.Session()

# 1. 获取交易列表
trades_url = "https://data-api.polymarket.com/trades"
params = {
    "user": "0x96489abcb9f583d6835c8ef95ffc923d05a86825",
    "limit": 10
}

print("正在获取交易数据...")
try:
    response = session.get(trades_url, params=params)
    response.raise_for_status() # 检查 HTTP 错误
    trades = response.json()
except Exception as e:
    print(f"请求失败: {e}")
    trades = []

# 简单的内存缓存，避免重复请求同一个 Market 的详情
market_cache = {}

if trades:
    # 兼容处理：API 有时返回列表，有时返回 {'data': [...]}
    if isinstance(trades, dict) and 'data' in trades:
        trades_list = trades['data']
    elif isinstance(trades, list):
        trades_list = trades
    else:
        trades_list = []
        print("未识别的数据格式")

    print(f"成功获取 {len(trades_list)} 条交易记录")
    print("=" * 60)

    for trade in trades_list:
        condition_id = trade.get('conditionId')
        
        # --- 获取 Market 详情 (带缓存优化) ---
        market_question = "获取失败"
        if condition_id:
            if condition_id in market_cache:
                # 命中缓存，直接使用
                market_question = market_cache[condition_id]
            else:
                # 未命中，请求 API
                try:
                    market_url = f"https://clob.polymarket.com/markets/{condition_id}"
                    m_resp = session.get(market_url)
                    if m_resp.status_code == 200:
                        m_data = m_resp.json()
                        market_question = m_data.get('question', '未知问题')
                        # 存入缓存
                        market_cache[condition_id] = market_question
                except Exception as e:
                    print(f"  [Warn] Market详情获取出错: {e}")

        # --- 时间转换 ---
        raw_time = trade.get('createdAt') or trade.get('timestamp')
        china_time = convert_to_cst(raw_time)

        # --- 打印结果 ---
        print(f"时间:   {china_time}")
        print(f"问题:   {market_question}")
        print(f"方向:   {trade.get('side')} | 价格: {trade.get('price')} | 数量: {trade.get('size')}")
        print(f"资产:   {trade.get('asset')}")
        print(f"哈希:   {trade.get('transactionHash')}")
        print("-" * 60)

else:
    print("未获取到交易数据或返回为空")