"""
快速回测脚本 - 支持多参数测试
"""
import ccxt
import pandas as pd
from datetime import datetime, timedelta
import json
import sys
import os

# 导入回测引擎
sys.path.append(os.path.dirname(__file__))
from backtest_bnb import BacktestEngine, check_multi_timeframe_signal


def run_quick_backtest(symbol, days_back, strategy_config, initial_balance=1000):
    """快速回测函数"""
    print(f"\n{'='*60}")
    print(f"回测配置: {symbol} | {days_back}天 | 初始资金: {initial_balance} USDT")
    print(f"策略参数: {strategy_config}")
    print(f"{'='*60}")
    
    # 初始化交易所
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    
    # 计算时间范围
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days_back)
    since = int(start_time.timestamp() * 1000)
    
    # 初始化回测引擎
    backtest = BacktestEngine(symbol=symbol, initial_balance=initial_balance)
    
    # 获取历史数据
    print("\n正在获取历史数据...")
    klines_data = {}
    for tf in ['1h', '4h', '1d']:
        klines_data[tf] = backtest.fetch_historical_data(exchange, tf, since)
        if not klines_data[tf]:
            print(f"警告: {tf} 数据获取失败")
            return None
    
    # 运行回测
    backtest.run_backtest(klines_data, strategy_config)
    
    return {
        'symbol': symbol,
        'days': days_back,
        'config': strategy_config,
        'final_balance': backtest.balance,
        'total_return': (backtest.balance - initial_balance) / initial_balance * 100,
        'total_trades': len(backtest.trades),
        'win_rate': len([t for t in backtest.trades if t['pnl'] > 0]) / len(backtest.trades) * 100 if backtest.trades else 0,
        'max_drawdown': calculate_max_drawdown(backtest.equity_curve, initial_balance)
    }


def calculate_max_drawdown(equity_curve, initial_balance):
    """计算最大回撤"""
    peak = initial_balance
    max_dd = 0
    for point in equity_curve:
        if point['equity'] > peak:
            peak = point['equity']
        dd = (peak - point['equity']) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return max_dd


def parameter_optimization():
    """参数优化 - 测试多组参数"""
    print("\n" + "="*80)
    print("参数优化模式 - 将测试多组参数组合")
    print("="*80)
    
    # 定义参数范围
    test_configs = [
        # 原始配置
        {'ratio': 0.67, 'confluence': 2, 'tp': 1.5, 'sl': 1.0, 'amount': 100},
        # 更严格的信号（更高比例）
        {'ratio': 1.0, 'confluence': 2, 'tp': 1.5, 'sl': 1.0, 'amount': 100},
        # 更激进的止盈
        {'ratio': 0.67, 'confluence': 2, 'tp': 2.0, 'sl': 1.0, 'amount': 100},
        # 更严格的共振（3个周期）
        {'ratio': 0.67, 'confluence': 3, 'tp': 1.5, 'sl': 1.0, 'amount': 100},
        # 更保守的止损
        {'ratio': 0.67, 'confluence': 2, 'tp': 1.5, 'sl': 0.8, 'amount': 100},
    ]
    
    results = []
    
    for i, config in enumerate(test_configs, 1):
        print(f"\n测试组合 {i}/{len(test_configs)}")
        result = run_quick_backtest('BNB/USDT', 180, config)  # 6个月回测
        if result:
            results.append(result)
    
    # 生成对比报告
    print("\n" + "="*80)
    print("参数优化结果对比")
    print("="*80)
    
    # 按收益率排序
    results.sort(key=lambda x: x['total_return'], reverse=True)
    
    print(f"\n{'排名':<6} {'收益率':<10} {'胜率':<10} {'交易次数':<10} {'最大回撤':<10} {'参数'}")
    print("-" * 80)
    
    for i, r in enumerate(results, 1):
        print(f"{i:<6} {r['total_return']:>8.2f}% {r['win_rate']:>8.2f}% {r['total_trades']:>10} {r['max_drawdown']:>8.2f}% ", end="")
        print(f"ratio={r['config']['ratio']}, conf={r['config']['confluence']}, tp={r['config']['tp']}, sl={r['config']['sl']}")
    
    # 保存结果
    with open('optimization_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n详细结果已保存到: optimization_results.json")
    print("="*80 + "\n")


def multi_symbol_test():
    """多币种测试"""
    print("\n" + "="*80)
    print("多币种测试模式")
    print("="*80)
    
    symbols = ['BNB/USDT', 'ETH/USDT', 'BTC/USDT', 'SOL/USDT']
    config = {'ratio': 0.67, 'confluence': 2, 'tp': 1.5, 'sl': 1.0, 'amount': 100}
    
    results = []
    
    for symbol in symbols:
        print(f"\n正在测试: {symbol}")
        result = run_quick_backtest(symbol, 180, config)  # 6个月
        if result:
            results.append(result)
    
    # 生成对比报告
    print("\n" + "="*80)
    print("多币种测试结果对比")
    print("="*80)
    
    results.sort(key=lambda x: x['total_return'], reverse=True)
    
    print(f"\n{'排名':<6} {'币种':<12} {'收益率':<10} {'胜率':<10} {'交易次数':<10} {'最大回撤':<10}")
    print("-" * 80)
    
    for i, r in enumerate(results, 1):
        print(f"{i:<6} {r['symbol']:<12} {r['total_return']:>8.2f}% {r['win_rate']:>8.2f}% {r['total_trades']:>10} {r['max_drawdown']:>8.2f}%")
    
    # 保存结果
    with open('multi_symbol_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n详细结果已保存到: multi_symbol_results.json")
    print("="*80 + "\n")


def main():
    """主菜单"""
    print("\n" + "="*80)
    print("快速回测工具")
    print("="*80)
    print("\n请选择模式:")
    print("1. 标准回测 (BNB, 1年)")
    print("2. 参数优化 (测试多组参数)")
    print("3. 多币种测试 (BNB, ETH, BTC, SOL)")
    print("4. 自定义回测")
    print("\n0. 退出")
    
    choice = input("\n请输入选项 (0-4): ").strip()
    
    if choice == '1':
        # 标准回测
        config = {'ratio': 0.67, 'confluence': 2, 'tp': 1.5, 'sl': 1.0, 'amount': 100}
        run_quick_backtest('BNB/USDT', 365, config)
    
    elif choice == '2':
        # 参数优化
        parameter_optimization()
    
    elif choice == '3':
        # 多币种测试
        multi_symbol_test()
    
    elif choice == '4':
        # 自定义回测
        print("\n自定义回测设置:")
        symbol = input("交易对 (例如: BNB/USDT): ").strip() or 'BNB/USDT'
        days = int(input("回测天数 (例如: 365): ").strip() or 365)
        
        print("\n策略参数:")
        ratio = float(input("影线/实体比例 (默认: 0.67): ").strip() or 0.67)
        confluence = int(input("共振周期数量 (1-3, 默认: 2): ").strip() or 2)
        tp = float(input("止盈倍数 (默认: 1.5): ").strip() or 1.5)
        sl = float(input("止损倍数 (默认: 1.0): ").strip() or 1.0)
        amount = float(input("开仓金额 USDT (默认: 100): ").strip() or 100)
        
        config = {
            'ratio': ratio,
            'confluence': confluence,
            'tp': tp,
            'sl': sl,
            'amount': amount
        }
        
        run_quick_backtest(symbol, days, config)
    
    elif choice == '0':
        print("\n退出程序...")
        return
    
    else:
        print("\n无效选项，请重新运行程序")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序已中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n按任意键退出...")

