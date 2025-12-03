"""
使用币安官方Python SDK测试（不用CCXT）
"""
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
except ImportError:
    print("需要安装 python-binance 库")
    print("运行: pip install python-binance")
    exit(1)

def test_official_sdk():
    print("\n" + "="*60)
    print("  使用币安官方Python SDK测试")
    print("  （模仿NOFX的Go SDK方式）")
    print("="*60 + "\n")
    
    api_key = "Lg2ZdYbBrlVIrAR85s2HVQSxdcUmakyzp6Vnh1A5GEVEqXw1epwiIJNizg2Lmrii"
    secret = "ZEDsrnLqaaIniUeRZePu7acMYFuZFJuGAAJDFOsKTqoMxfd3WpPTYe3DZklBuL7i"
    
    print(f"API Key: {api_key[:20]}...{api_key[-20:]}")
    print(f"Secret: {secret[:20]}...{secret[-20:]}\n")
    
    try:
        # 创建客户端（像NOFX一样简单）
        print("【官方SDK方式】创建客户端...\n")
        
        client = Client(
            api_key=api_key,
            api_secret=secret,
            requests_params={'proxies': {
                'http': 'http://127.0.0.1:7890',
                'https': 'http://127.0.0.1:7890'
            }}
        )
        
        # 测试1：获取账户信息
        print("  [1/2] 测试获取账户信息...")
        try:
            account = client.get_account()
            print(f"    ✅ 成功获取账户信息")
            print(f"    账户类型: {account.get('accountType', 'N/A')}")
            
            # 显示余额
            balances = account.get('balances', [])
            print(f"\n    余额列表:")
            for balance in balances:
                free = float(balance['free'])
                locked = float(balance['locked'])
                if free > 0 or locked > 0:
                    print(f"      {balance['asset']}: {free + locked}")
            
            print("\n" + "="*60)
            print("  🎉 测试成功！API Key有效！")
            print("="*60)
            return True
            
        except BinanceAPIException as e:
            print(f"    ❌ 币安API错误")
            print(f"    错误码: {e.code}")
            print(f"    错误信息: {e.message}")
            
            if e.code == -2008:
                print("\n    【-2008分析】")
                print("    币安不认识这个API Key")
                print()
                print("    最后确认：")
                print("    1. 这个Key创建多久了？（需要等10分钟）")
                print("    2. 在币安后台状态是'已启用'？")
                print("    3. 权限勾选了'读取'和'交易'？")
            
            return False
            
    except Exception as e:
        print(f"\n创建客户端失败: {e}")
        return False

if __name__ == "__main__":
    test_official_sdk()
    print()
    input("按回车键退出...")

