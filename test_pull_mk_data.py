import requests
import json

def fetch_live_tradeable_markets():
    # 使用 Gamma API，这是官网展示数据的来源
    url = "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=10"
    
    print("=" * 90)
    print(f"{'Market Question':<50} | {'Price':<6} | {'YES Token ID'}")
    print("-" * 90)

    try:
        response = requests.get(url)
        events = response.json()

        for event in events:
            for market in event.get('markets', []):
                question = market.get('question', 'No Title')
                display_q = (question[:47] + '...') if len(question) > 50 else question
                
                # 获取 Token ID (CLOB 交易必需)
                clob_ids = json.loads(market.get('clobTokenIds', '[]'))
                
                # 获取价格
                prices = json.loads(market.get('outcomePrices', '["0", "0"]'))
                
                if clob_ids and len(clob_ids) > 0:
                    yes_token_id = clob_ids[0]
                    yes_price = prices[0]
                    print(f"{display_q:<50} | {yes_price:<6} | {yes_token_id}")

        print("-" * 90)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_live_tradeable_markets()