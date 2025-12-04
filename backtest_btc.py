"""
BTC 回测脚本 - Pinbar多周期共振策略 + 1H移动止损

策略说明：
- Pinbar形态: 影线/实体 > 0.67
- 多周期共振: 1H, 4H, 1D 至少2个满足
- 仓位管理: 全仓
- 杠杆: 2倍
- 移动止损: 根据1H K线动态调整（价格走高/走低后移动）

回测周期: 365天（1年）
初始资金: 100,000 USDT
"""
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

# ==========================================
# 策略核心逻辑（从 main.py 复制）
# ==========================================

def check_pinbar(ohlcv, direction='long', body_ratio=0.67):
    """检查是否为 Pinbar 形态"""
    if not ohlcv:
        return False
    
    open_p = ohlcv[1]
    high = ohlcv[2]
    low = ohlcv[3]
    close = ohlcv[4]
    
    total_len = high - low
    body_len = abs(close - open_p)
    upper_shadow = high - max(open_p, close)
    lower_shadow = min(open_p, close) - low
    
    if total_len == 0:
        return False

    # Pinbar检查
    if direction == 'long':
        # 做多：下影线长度 > 实体长度 * body_ratio
        return lower_shadow > body_len * body_ratio
    elif direction == 'short':
        # 做空：上影线长度 > 实体长度 * body_ratio
        return upper_shadow > body_len * body_ratio
    
    return False


def check_multi_timeframe_signal(klines_dict, strategy_config, main_tf='1h'):
    """
    多周期共振检测（严格按照项目策略）
    klines_dict: {'1h': [...], '4h': [...], '1d': [...]}
    返回: ('buy'/'sell'/None, signal_candle, 详细分析)
    """
    timeframes = ['1h', '4h', '1d']
    signals = {'long': 0, 'short': 0}
    signal_candle = None
    
    analysis = {
        'timeframes_checked': [],
        'confluence_found': {'long': [], 'short': []},
        'ratios': {},
        'signals_count': {}
    }
    
    for tf in timeframes:
        if tf not in klines_dict or len(klines_dict[tf]) < 2:
            continue
        
        # 使用倒数第二根K线（已收盘确认的K线）
        candle = klines_dict[tf][-2]
        time_ms, open_p, high, low, close, volume = candle
        
        body = abs(close - open_p)
        upper_wick = high - max(open_p, close)
        lower_wick = min(open_p, close) - low
        
        analysis['timeframes_checked'].append(tf)
        
        # 检查做多信号（下影线长 = Pinbar）
        if check_pinbar(candle, 'long', strategy_config['ratio']):
            signals['long'] += 1
            analysis['confluence_found']['long'].append(tf)
            ratio = lower_wick / body if body > 0 else 0
            analysis['ratios'][tf] = {
                'type': 'Pinbar做多',
                'lower_wick': lower_wick,
                'body': body,
                'ratio': round(ratio, 2)
            }
            if tf == main_tf:
                signal_candle = candle
        
        # 检查做空信号（上影线长 = Shooting Star）
        if check_pinbar(candle, 'short', strategy_config['ratio']):
            signals['short'] += 1
            analysis['confluence_found']['short'].append(tf)
            ratio = upper_wick / body if body > 0 else 0
            analysis['ratios'][tf] = {
                'type': 'Shooting Star做空',
                'upper_wick': upper_wick,
                'body': body,
                'ratio': round(ratio, 2)
            }
            if tf == main_tf:
                signal_candle = candle
    
    required_confluence = strategy_config.get('confluence', 2)
    analysis['required_confluence'] = required_confluence
    analysis['signals_count'] = signals
    
    if signals['long'] >= required_confluence:
        return 'buy', signal_candle, analysis
    if signals['short'] >= required_confluence:
        return 'sell', signal_candle, analysis
    
    return None, None, analysis


# ==========================================
# 回测引擎
# ==========================================

class BacktestEngine:
    def __init__(self, symbol='BNB/USDT', initial_balance=1000):
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.position = None  # {'side': 'buy'/'sell', 'entry_price': float, 'quantity': float, 'entry_time': datetime}
        self.trades = []  # 交易历史
        self.equity_curve = []  # 权益曲线
        
    def fetch_historical_data(self, exchange, timeframe, since, limit=1000):
        """获取历史K线数据"""
        print(f"正在获取 {self.symbol} {timeframe} 历史数据...")
        all_data = []
        current_since = since
        
        while True:
            try:
                klines = exchange.fetch_ohlcv(self.symbol, timeframe, since=current_since, limit=limit)
                if not klines:
                    break
                
                all_data.extend(klines)
                
                # 如果返回的数据少于limit，说明已经到最新
                if len(klines) < limit:
                    break
                
                # 更新since为最后一根K线的时间
                current_since = klines[-1][0] + 1
                
                # 避免过于频繁的请求
                import time
                time.sleep(0.5)
                
            except Exception as e:
                print(f"获取数据失败: {e}")
                break
        
        print(f"获取到 {len(all_data)} 根 {timeframe} K线")
        return all_data
    
    def calculate_tp_sl(self, signal, entry_price, signal_candle, strategy_config):
        """计算止盈止损价格（严格按照项目策略）"""
        k_high = signal_candle[2]
        k_low = signal_candle[3]
        
        if signal == 'buy':
            sl_price = k_low
            risk = entry_price - sl_price
            if risk <= 0:
                sl_price = entry_price * 0.99
                risk = entry_price - sl_price
            tp_price = entry_price + (risk * strategy_config['tp'])
            sl_price = entry_price - (risk * strategy_config['sl'])  # Double check（项目策略）
        else:  # sell
            sl_price = k_high
            risk = sl_price - entry_price
            if risk <= 0:
                sl_price = entry_price * 1.01
                risk = sl_price - entry_price
            tp_price = entry_price - (risk * strategy_config['tp'])
            sl_price = entry_price + (risk * strategy_config['sl'])  # Double check（项目策略）
        
        return tp_price, sl_price
    
    def open_position(self, side, entry_price, entry_time, tp_price, sl_price, strategy_config):
        """开仓（全仓2倍杠杆）"""
        if self.position:
            return  # 已有持仓，不重复开仓
        
        # 全仓2倍杠杆：使用全部余额作为保证金
        leverage = 2
        margin = self.balance  # 保证金（全部余额）
        position_size = margin * leverage  # 实际仓位 = 保证金 × 杠杆
        quantity = position_size / entry_price
        
        self.position = {
            'side': side,
            'entry_price': entry_price,
            'entry_time': entry_time,
            'quantity': quantity,
            'position_size': position_size,
            'margin': margin,
            'leverage': leverage,
            'tp_price': tp_price,
            'sl_price': sl_price
        }
        
        print(f"\n{'='*60}")
        print(f"[开仓] {side.upper()} {self.symbol}")
        print(f"  时间: {entry_time}")
        print(f"  价格: {entry_price:.4f}")
        print(f"  数量: {quantity:.4f}")
        print(f"  保证金: {margin:.2f} USDT (全仓)")
        print(f"  杠杆: {leverage}x")
        print(f"  仓位价值: {position_size:.2f} USDT")
        print(f"  当前余额: {self.balance:.2f} USDT")
        print(f"  止盈: {tp_price:.4f}")
        print(f"  止损: {sl_price:.4f}")
        print(f"{'='*60}")
    
    def close_position(self, exit_price, exit_time, reason):
        """平仓"""
        if not self.position:
            return
        
        # 计算盈亏
        if self.position['side'] == 'buy':
            pnl = (exit_price - self.position['entry_price']) * self.position['quantity']
        else:  # sell
            pnl = (self.position['entry_price'] - exit_price) * self.position['quantity']
        
        pnl_percent = (pnl / self.position['position_size']) * 100
        
        self.balance += pnl
        
        trade_record = {
            'entry_time': self.position['entry_time'],
            'exit_time': exit_time,
            'side': self.position['side'],
            'entry_price': self.position['entry_price'],
            'exit_price': exit_price,
            'quantity': self.position['quantity'],
            'pnl': pnl,
            'pnl_percent': pnl_percent,
            'reason': reason,
            'balance': self.balance,
            'trailing_stop_history': self.position.get('trailing_stop_history', [])
        }
        
        self.trades.append(trade_record)
        
        print(f"\n[平仓] {reason}")
        print(f"  时间: {exit_time}")
        print(f"  价格: {exit_price:.4f}")
        print(f"  盈亏: {pnl:.2f} USDT ({pnl_percent:.2f}%)")
        print(f"  余额: {self.balance:.2f} USDT")
        
        self.position = None
    
    def check_exit_conditions(self, current_candle):
        """检查是否触发止盈止损"""
        if not self.position:
            return False
        
        time_ms, open_p, high, low, close, volume = current_candle
        exit_time = datetime.fromtimestamp(time_ms / 1000)
        
        if self.position['side'] == 'buy':
            # 做多：检查止盈和止损
            if high >= self.position['tp_price']:
                self.close_position(self.position['tp_price'], exit_time, '止盈')
                return True
            elif low <= self.position['sl_price']:
                self.close_position(self.position['sl_price'], exit_time, '止损')
                return True
        else:  # sell
            # 做空：检查止盈和止损
            if low <= self.position['tp_price']:
                self.close_position(self.position['tp_price'], exit_time, '止盈')
                return True
            elif high >= self.position['sl_price']:
                self.close_position(self.position['sl_price'], exit_time, '止损')
                return True
        
        return False
    
    def update_trailing_stop(self, klines_1h, current_time):
        """移动止损（根据1H K线，检测价格走高/走低后移动）"""
        if not self.position:
            return
        
        # 找到最近的3根已收盘1H K线（用于判断走势）
        recent_candles = []
        for k in reversed(klines_1h):
            if k[0] < current_time:
                recent_candles.insert(0, k)
                if len(recent_candles) >= 3:
                    break
        
        if len(recent_candles) < 3:
            return
        
        # 最新一根K线（用于判断价格走势）
        current_candle = recent_candles[-1]
        # 倒数第二根K线（已收盘，用作止损基准）
        prev_candle = recent_candles[-2]
        
        current_time_ms, current_open, current_high, current_low, current_close, current_vol = current_candle
        prev_time_ms, prev_open, prev_high, prev_low, prev_close, prev_vol = prev_candle
        
        current_sl = self.position['sl_price']
        new_sl = None
        should_update = False
        reason = ""
        
        if self.position['side'] == 'buy':
            # 做多：检测价格是否走高（当前1H K线最高价 > 倒数第二根1H K线最高价）
            if current_high > prev_high:
                # 价格走高，移动止损到倒数第二根1H K线的最低点
                new_sl = prev_low
                # 只有新止损更高时才移动（向上移动止损，保护利润）
                if new_sl > current_sl:
                    should_update = True
                    reason = f"多单止损上移(1H): {current_sl:.4f} → {new_sl:.4f} (当前1H走高至{current_high:.4f}，止损移至前1H低点{prev_low:.4f})"
        else:  # sell
            # 做空：检测价格是否走低（当前1H K线最低价 < 倒数第二根1H K线最低价）
            if current_low < prev_low:
                # 价格走低，移动止损到倒数第二根1H K线的最高点
                new_sl = prev_high
                # 只有新止损更低时才移动（向下移动止损，保护利润）
                if new_sl < current_sl:
                    should_update = True
                    reason = f"空单止损下移(1H): {current_sl:.4f} → {new_sl:.4f} (当前1H走低至{current_low:.4f}，止损移至前1H高点{prev_high:.4f})"
        
        if should_update:
            print(f"[移动止损-1H] {reason}")
            self.position['sl_price'] = new_sl
            
            # 记录移动止损历史
            if 'trailing_stop_history' not in self.position:
                self.position['trailing_stop_history'] = []
            self.position['trailing_stop_history'].append({
                'time': datetime.fromtimestamp(current_time_ms / 1000),
                'old_sl': current_sl,
                'new_sl': new_sl,
                'prev_candle_time': datetime.fromtimestamp(prev_time_ms / 1000),
                'current_candle_time': datetime.fromtimestamp(current_time_ms / 1000),
                'prev_candle_low': prev_low if self.position['side'] == 'buy' else None,
                'prev_candle_high': prev_high if self.position['side'] == 'sell' else None,
                'current_high': current_high if self.position['side'] == 'buy' else None,
                'current_low': current_low if self.position['side'] == 'sell' else None
            })
    
    def run_backtest(self, klines_data, strategy_config):
        """运行回测"""
        print(f"\n{'='*60}")
        print(f"开始回测 {self.symbol}")
        print(f"初始资金: {self.initial_balance} USDT")
        print(f"策略参数: {strategy_config}")
        print(f"{'='*60}\n")
        
        # 准备数据：将数据按时间对齐
        # 使用1h K线作为主时间轴
        main_klines = klines_data['1h']
        
        for i in range(len(main_klines)):
            current_time = main_klines[i][0]
            current_datetime = datetime.fromtimestamp(current_time / 1000)
            
            # 检查是否触发平仓
            if self.position:
                self.check_exit_conditions(main_klines[i])
            
            # 移动止损检查（每个1H周期检查一次）
            if self.position:  # 每1小时检查一次
                self.update_trailing_stop(klines_data['1h'], current_time)
            
            # 如果没有持仓，检查是否有开仓信号
            if not self.position and i > 1:  # 确保有足够的历史K线
                # 获取当前时刻各周期的K线数据（包含至少2根以取倒数第二根）
                current_klines = {}
                
                # 1h: 获取到当前时间的所有K线
                current_klines['1h'] = [k for k in main_klines[:i+1] if k[0] <= current_time]
                
                # 4h: 找到所有到当前时间的4h K线
                current_klines['4h'] = [k for k in klines_data['4h'] if k[0] <= current_time]
                
                # 1d: 找到所有到当前时间的1d K线
                current_klines['1d'] = [k for k in klines_data['1d'] if k[0] <= current_time]
                
                # 检查信号（使用倒数第二根K线）
                signal, signal_candle, analysis = check_multi_timeframe_signal(current_klines, strategy_config, '1h')
                
                if signal and signal_candle:
                    # 使用当前K线的开盘价作为入场价（模拟真实情况）
                    entry_price = main_klines[i][1]
                    tp_price, sl_price = self.calculate_tp_sl(signal, entry_price, signal_candle, strategy_config)
                    
                    self.open_position(signal, entry_price, current_datetime, tp_price, sl_price, strategy_config)
            
            # 记录权益曲线
            current_equity = self.balance
            if self.position:
                current_price = main_klines[i][4]  # 收盘价
                if self.position['side'] == 'buy':
                    unrealized_pnl = (current_price - self.position['entry_price']) * self.position['quantity']
                else:
                    unrealized_pnl = (self.position['entry_price'] - current_price) * self.position['quantity']
                current_equity = self.balance + unrealized_pnl
            
            self.equity_curve.append({
                'time': current_datetime,
                'equity': current_equity
            })
        
        # 如果回测结束时还有持仓，强制平仓
        if self.position:
            last_candle = main_klines[-1]
            exit_price = last_candle[4]
            exit_time = datetime.fromtimestamp(last_candle[0] / 1000)
            self.close_position(exit_price, exit_time, '回测结束强制平仓')
        
        # 生成回测报告
        self.generate_report()
    
    def generate_report(self):
        """生成回测报告"""
        print(f"\n{'='*60}")
        print("回测报告")
        print(f"{'='*60}")
        
        if not self.trades:
            print("没有完成任何交易")
            return
        
        # 基本统计
        total_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t['pnl'] > 0]
        losing_trades = [t for t in self.trades if t['pnl'] <= 0]
        
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
        
        total_pnl = sum(t['pnl'] for t in self.trades)
        total_return = (self.balance - self.initial_balance) / self.initial_balance * 100
        
        avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
        
        profit_factor = abs(sum(t['pnl'] for t in winning_trades) / sum(t['pnl'] for t in losing_trades)) if losing_trades and sum(t['pnl'] for t in losing_trades) != 0 else float('inf')
        
        # 最大回撤
        peak = self.initial_balance
        max_drawdown = 0
        for point in self.equity_curve:
            if point['equity'] > peak:
                peak = point['equity']
            drawdown = (peak - point['equity']) / peak * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        print(f"\n总交易次数: {total_trades}")
        print(f"盈利次数: {len(winning_trades)}")
        print(f"亏损次数: {len(losing_trades)}")
        print(f"胜率: {win_rate:.2f}%")
        print(f"\n初始资金: {self.initial_balance:.2f} USDT")
        print(f"最终资金: {self.balance:.2f} USDT")
        print(f"总盈亏: {total_pnl:.2f} USDT")
        print(f"总收益率: {total_return:.2f}%")
        print(f"\n平均盈利: {avg_win:.2f} USDT")
        print(f"平均亏损: {avg_loss:.2f} USDT")
        print(f"盈亏比: {abs(avg_win/avg_loss) if avg_loss != 0 else float('inf'):.2f}")
        print(f"盈利因子: {profit_factor:.2f}")
        print(f"最大回撤: {max_drawdown:.2f}%")
        
        # 移动止损统计
        trailing_stop_count = sum(1 for t in self.trades if 'trailing_stop_history' in t and t.get('trailing_stop_history'))
        if trailing_stop_count > 0:
            print(f"\n移动止损:")
            print(f"  触发移动止损的交易: {trailing_stop_count}/{total_trades}")
        
        # 保存详细交易记录到文件
        trades_df = pd.DataFrame(self.trades)
        trades_df.to_csv('backtest_trades_btc.csv', index=False)
        print(f"\n详细交易记录已保存到: backtest_trades_btc.csv")
        
        # 保存权益曲线
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df.to_csv('backtest_equity_btc.csv', index=False)
        print(f"权益曲线已保存到: backtest_equity_btc.csv")
        
        # 保存报告摘要
        report = {
            'symbol': self.symbol,
            'initial_balance': self.initial_balance,
            'final_balance': self.balance,
            'total_pnl': total_pnl,
            'total_return': total_return,
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown,
            'trailing_stop_count': trailing_stop_count
        }
        
        with open('backtest_report_btc.json', 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"回测报告已保存到: backtest_report_btc.json")
        
        print(f"{'='*60}\n")


# ==========================================
# 主程序
# ==========================================

def main():
    # 策略配置（严格按照项目策略）
    strategy_config = {
        'ratio': 0.67,          # 影线/实体比例（Pinbar形态识别）
        'confluence': 2,        # 共振周期数量（1H, 4H, 1D 中至少2个满足）
        'tp': 1.5,              # 止盈倍数
        'sl': 1.0,              # 止损倍数
    }
    
    # 回测参数
    symbol = 'BTC/USDT'
    initial_balance = 100000  # 初始资金
    days_back = 365         # 回测天数（1年）
    
    print("\n" + "="*60)
    print("BTC 回测 - Pinbar多周期共振策略 + 1H移动止损")
    print("="*60)
    print("策略说明:")
    print("  - Pinbar形态: 影线/实体 > 0.67")
    print("  - 多周期共振: 1H, 4H, 1D 至少2个满足")
    print("  - 仓位管理: 全仓")
    print("  - 杠杆: 2倍")
    print("  - 移动止损: 根据1H K线动态调整（价格走高/走低后移动）")
    print("="*60 + "\n")
    
    # 初始化交易所（使用公开API，不需要key）
    # 按照项目配置方式
    http_proxy = 'http://127.0.0.1:7890'
    
    exchange = ccxt.binance({
        'timeout': 30000,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'adjustForTimeDifference': True,
        },
        'proxies': {
            'http': http_proxy,
            'https': http_proxy,
        }
    })
    
    # 计算起始时间
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days_back)
    since = int(start_time.timestamp() * 1000)
    
    # 初始化回测引擎
    backtest = BacktestEngine(symbol=symbol, initial_balance=initial_balance)
    
    # 获取多周期历史数据
    klines_data = {}
    for tf in ['1h', '4h', '1d']:
        klines_data[tf] = backtest.fetch_historical_data(exchange, tf, since)
    
    # 运行回测
    backtest.run_backtest(klines_data, strategy_config)


if __name__ == '__main__':
    main()

