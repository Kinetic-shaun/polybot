import requests
import json

# 交易记录的 asset
target_user = "0x7a0da16a1205ee51a56fa862e8baa61e350eff14"
url = "https://data-api.polymarket.com/trades"
params = {"user": target_user, "limit": 3}
resp = requests.get(url, params=params, timeout=10)
trades = resp.json()

trade = trades[0]
asset = trade.get('asset')
outcome = trade.get('outcome', 'N/A')
price = trade.get('price', 0)

print(f"交易 asset: {asset}")
print(f"交易 outcome: {outcome}")
print(f"交易 price: {price}")

# 获取所有 Gamma API 市场
print("\n=== 通过 outcome 和价格匹配 ===")
gamma_url = "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=50"
resp = requests.get(gamma_url, timeout=10)
events = resp.json()

for event in events:
    for market in event.get('markets', []):
        clob_ids = json.loads(market.get('clobTokenIds', '[]'))
        prices = json.loads(market.get('outcomePrices', '[]'))
        default_outcomes = '["Yes", "No"]'
        outcomes = json.loads(market.get('outcomes', default_outcomes))

        for i, token_id in enumerate(clob_ids):
            market_outcome = outcomes[i] if i < len(outcomes) else None
            market_price = float(prices[i]) if i < len(prices) and prices[i] else 0

            # 匹配 outcome 和价格（容差 0.01）
            if market_outcome == outcome and abs(market_price - price) < 0.01:
                print(f"找到匹配!")
                print(f"  event_id: {event.get('id')}")
                print(f"  market slug: {market.get('marketSlug')}")
                print(f"  question: {market.get('question', 'N/A')[:50]}")
                print(f"  token_id: {token_id}")
                print(f"  交易价格: {price}, 市场价格: {market_price}")
                # 验证 orderbook
                orderbook_resp = requests.get("https://clob.polymarket.com/book", params={"token_id": token_id}, timeout=5)
                print(f"  orderbook 状态: {orderbook_resp.status_code}")
                if orderbook_resp.status_code == 200:
                    print("  ✅ Token ID 有效!")
                else:
                    print("  ❌ Token ID 无效")
