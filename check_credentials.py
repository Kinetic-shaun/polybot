#!/usr/bin/env python3
"""
Diagnostic script to check Polymarket credentials
"""
from dotenv import load_dotenv
import os

load_dotenv()

print("=" * 60)
print("POLYMARKET CREDENTIALS CHECK")
print("=" * 60)

# Check environment variables
api_key = os.getenv("POLYMARKET_API_KEY", "")
api_secret = os.getenv("POLYMARKET_API_SECRET", "")
api_passphrase = os.getenv("POLYMARKET_API_PASSPHRASE", "")
private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")

print("\n1. Environment Variables:")
print(f"   API Key: {'✓ Set' if api_key else '✗ Missing'} ({len(api_key)} chars)")
print(f"   API Secret: {'✓ Set' if api_secret else '✗ Missing'} ({len(api_secret)} chars)")
print(f"   API Passphrase: {'✓ Set' if api_passphrase else '✗ Missing'} ({len(api_passphrase)} chars)")
print(f"   Private Key: {'✓ Set' if private_key else '✗ Missing'} ({len(private_key)} chars)")

# Check private key format
print("\n2. Private Key Format:")
if private_key:
    if private_key.startswith("0x"):
        print("   ⚠ Warning: Private key starts with '0x' - remove the '0x' prefix")
        print("   Suggested fix: Remove '0x' from the beginning of your private key")
    elif len(private_key) == 64:
        print("   ✓ Private key appears to be in correct format (64 hex characters)")
    elif len(private_key) == 66:
        print("   ⚠ Private key is 66 characters (likely includes '0x' prefix)")
    else:
        print(f"   ⚠ Unusual private key length: {len(private_key)} characters")
        print("   Expected: 64 characters (hex) without '0x' prefix")

    # Check if it's valid hex
    try:
        int(private_key.replace("0x", ""), 16)
        print("   ✓ Private key is valid hexadecimal")
    except ValueError:
        print("   ✗ Private key contains invalid hexadecimal characters")
else:
    print("   ✗ Private key not set")

# Test public API access
print("\n3. Testing Public API Access:")
try:
    from py_clob_client.client import ClobClient
    client = ClobClient(host='https://clob.polymarket.com', chain_id=137)
    markets = client.get_markets()
    print(f"   ✓ Successfully connected to Polymarket API")
    print(f"   ✓ Fetched {len(markets)} markets")
except Exception as e:
    print(f"   ✗ Failed to connect: {e}")

# Test authenticated access
print("\n4. Testing Authenticated API Access:")
if api_key and api_secret and api_passphrase and private_key:
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds

        clean_key = private_key.replace("0x", "").replace("0X", "").strip()

        # 实例化凭证对象
        creds = ApiCreds(
            api_key=api_key.strip(),
            api_secret=api_secret.strip(),
            api_passphrase=api_passphrase.strip()
        )

        # 分步初始化，防止 SDK 内部 NoneType 冲突
        client = ClobClient(
            host='https://clob.polymarket.com',
            key=clean_key,
            chain_id=137,
            signature_type=0
        )
        
        # 绑定凭证
        client.set_api_creds(creds)

        # 尝试获取余额（这将触发真正的服务器验证）
        balance = client.get_balance_allowance()
        print(f"   ✓ Successfully authenticated!")
        print(f"   ✓ Balance: ${balance.get('balance', 0)}")
    except Exception as e:
        print(f"   ✗ Authentication failed: {e}")
else:
    print("   ⊘ Skipped (missing credentials)")

print("\n" + "=" * 60)
print("\nIf authentication failed, check:")
print("1. Remove '0x' prefix from private key if present")
print("2. Verify API credentials match your Polymarket account")
print("3. Ensure API key has trading permissions")
print("=" * 60)
