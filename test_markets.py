#!/usr/bin/env python3
"""
Test script to fetch and display Polymarket markets
"""
from py_clob_client.client import ClobClient

print("Fetching Polymarket markets...\n")

# Create client without authentication (public data only)
client = ClobClient(host='https://clob.polymarket.com', chain_id=137)

# Get markets
response = client.get_markets()
markets = response.get('data', [])

print(f"Total markets available: {len(markets)}")

# Filter open markets
open_markets = [m for m in markets if not m.get('closed', False) and m.get('active', False)]
print(f"Open markets: {len(open_markets)}\n")

# Show first 5 open markets
print("Sample of open markets:")
print("=" * 80)

for i, market in enumerate(open_markets[:5], 1):
    print(f"\n{i}. Question: {market.get('question', 'N/A')}")
    print(f"   Condition ID: {market.get('condition_id')}")
    print(f"   Active: {market.get('active')}")
    print(f"   Closed: {market.get('closed')}")
    print(f"   Accepting orders: {market.get('accepting_orders')}")

    # Try to get tokens
    tokens = market.get('tokens', [])
    if tokens:
        print(f"   Tokens: {len(tokens)}")
        for j, token in enumerate(tokens):
            token_id = token.get('token_id', 'N/A')
            outcome = token.get('outcome', 'N/A')
            print(f"     Token {j+1}: {outcome} ({token_id[:10]}...)")

print("\n" + "=" * 80)

# Get orderbook for first token
if open_markets and open_markets[0].get('tokens'):
    token_id = open_markets[0]['tokens'][0]['token_id']
    print(f"\nFetching orderbook for token: {token_id[:20]}...")

    try:
        orderbook = client.get_order_book(token_id)
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])

        print(f"  Bids: {len(bids)}")
        if bids:
            print(f"    Best bid: ${bids[0]['price']} (size: {bids[0]['size']})")

        print(f"  Asks: {len(asks)}")
        if asks:
            print(f"    Best ask: ${asks[0]['price']} (size: {asks[0]['size']})")

        if bids and asks:
            mid = (float(bids[0]['price']) + float(asks[0]['price'])) / 2
            spread = float(asks[0]['price']) - float(bids[0]['price'])
            print(f"  Midpoint: ${mid:.4f}")
            print(f"  Spread: ${spread:.4f} ({spread/mid*100:.2f}%)")
    except Exception as e:
        print(f"  Error fetching orderbook: {e}")

print("\n✓ Markets data is accessible via public API")
