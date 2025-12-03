import os
from fastapi import FastAPI, WebSocket, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import ccxt.async_support as ccxt
import asyncio
import json
import httpx
import websockets
from dotenv import load_dotenv
import numpy as np
from binance.client import Client as BinanceClient
from binance.exceptions import BinanceAPIException
import traceback
import datetime
import uuid

load_dotenv()

# 币安官方SDK实例（用于余额查询等）
binance_official_client = None

app = FastAPI(title="Candle Auto Trader")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 交易所实例管理
exchange_instances = {}
public_exchange_instances = {}
# WebSocket 连接管理
connected_websockets = set()

async def broadcast_message(message: dict):
    """广播消息给所有连接的 WebSocket 客户端"""
    to_remove = set()
    for ws in connected_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            to_remove.add(ws)
    
    for ws in to_remove:
        connected_websockets.discard(ws)

async def get_exchange_instance(exchange_id: str, market_type: str = 'spot', use_auth: bool = True):
    # 区分现货和合约实例
    key = f"{exchange_id}_{market_type}"
    target_dict = exchange_instances if use_auth else public_exchange_instances
    
    if key in target_dict:
        return target_dict[key]
    
    try:
        if exchange_id not in ['binance', 'okx']:
            return None

        print(f"Initializing {exchange_id} ({market_type}) exchange instance (Auth: {use_auth})...")
        exchange_class = getattr(ccxt, exchange_id)
        exchange_options = {
            'timeout': 30000, 
            'enableRateLimit': True,
            'options': {
                 'defaultType': market_type, 
                 'adjustForTimeDifference': True,
                 'recvWindow': 60000,
            }
        }
        
        # 只有需要认证时才加载 Key
        if use_auth:
            api_key = os.environ.get(f'{exchange_id.upper()}_API_KEY')
            secret = os.environ.get(f'{exchange_id.upper()}_SECRET')
            password = os.environ.get(f'{exchange_id.upper()}_PASSWORD')
            
            if api_key and secret:
                exchange_options['apiKey'] = api_key
                exchange_options['secret'] = secret
                if password:
                    exchange_options['password'] = password
                print(f"Loaded API Credentials for {exchange_id}")
        
        # 统一获取代理
        http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy') or 'http://127.0.0.1:7890'
        
        if http_proxy:
             http_proxy = http_proxy.strip()
             if not http_proxy.startswith('http'):
                 http_proxy = f"http://{http_proxy}"
             exchange_options['aiohttp_proxy'] = http_proxy
             print(f"Using Proxy for {exchange_id}: {http_proxy}")

        exchange = exchange_class(exchange_options)
        
        # 临时硬编码：针对 Binance 开启沙盒模式 (Testnet)
        is_testnet = os.environ.get(f'{exchange_id.upper()}_TESTNET', 'false').lower() == 'true'
        if use_auth and exchange_id == 'binance' and is_testnet:
            print("Enabling Sandbox Mode (Testnet) for Binance...")
            exchange.set_sandbox_mode(True)
            
        target_dict[key] = exchange
        return exchange
    except Exception as e:
        print(f"Exchange Init Error: {e}")
        return None

async def get_exchange(exchange_id: str, market_type: str = 'spot'):
    return await get_exchange_instance(exchange_id, market_type, use_auth=True)

async def get_public_exchange(exchange_id: str, market_type: str = 'spot'):
    return await get_exchange_instance(exchange_id, market_type, use_auth=False)

def get_binance_official_client():
    """获取币安官方SDK客户端（用于余额查询）"""
    global binance_official_client
    
    api_key = os.environ.get('BINANCE_API_KEY')
    secret = os.environ.get('BINANCE_SECRET')
    is_testnet = os.environ.get('BINANCE_TESTNET', 'false').lower() == 'true'
    
    if not api_key or not secret:
        return None
    
    if binance_official_client and hasattr(binance_official_client, '_api_key'):
        if binance_official_client._api_key == api_key:
            return binance_official_client
    
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy') or 'http://127.0.0.1:7890'
    if http_proxy:
        http_proxy = http_proxy.strip()
        if not http_proxy.startswith('http'):
            http_proxy = f"http://{http_proxy}"

    print(f"[官方SDK] Proxy: {http_proxy}")
    
    try:
        client_args = {
            'api_key': api_key,
            'api_secret': secret,
            'requests_params': {'proxies': {'http': http_proxy, 'https': http_proxy}, 'timeout': 30}
        }
        
        if is_testnet:
            client_args['testnet'] = True
        
        client = BinanceClient(**client_args)
        client._api_key = api_key
        binance_official_client = client
        
        print(f"[官方SDK] 创建币安客户端成功 ({'测试网' if is_testnet else '实盘'})")
        return client
    except Exception as e:
        print(f"[官方SDK] 创建客户端失败: {e}")
        traceback.print_exc()
        raise e

def save_keys_to_env(exchange_id, api_key, secret, password=None, is_testnet=False):
    try:
        api_key = api_key.strip()
        secret = secret.strip()
        if password:
            password = password.strip()

        env_path = ".env"
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()
        
        new_lines = []
        keys_found = {'key': False, 'secret': False, 'pass': False, 'testnet': False}
        
        prefix = exchange_id.upper()
        
        for line in lines:
            if line.startswith(f"{prefix}_API_KEY="):
                new_lines.append(f"{prefix}_API_KEY={api_key}\n")
                keys_found['key'] = True
            elif line.startswith(f"{prefix}_SECRET="):
                new_lines.append(f"{prefix}_SECRET={secret}\n")
                keys_found['secret'] = True
            elif line.startswith(f"{prefix}_PASSWORD="):
                if password:
                    new_lines.append(f"{prefix}_PASSWORD={password}\n")
                else:
                    new_lines.append(line)
                keys_found['pass'] = True
            elif line.startswith(f"{prefix}_TESTNET="):
                new_lines.append(f"{prefix}_TESTNET={str(is_testnet).lower()}\n")
                keys_found['testnet'] = True
            else:
                new_lines.append(line)
        
        if not keys_found['key']:
            new_lines.append(f"{prefix}_API_KEY={api_key}\n")
        if not keys_found['secret']:
            new_lines.append(f"{prefix}_SECRET={secret}\n")
        if password and not keys_found['pass']:
            new_lines.append(f"{prefix}_PASSWORD={password}\n")
        if not keys_found['testnet']:
            new_lines.append(f"{prefix}_TESTNET={str(is_testnet).lower()}\n")
            
        with open(env_path, "w") as f:
            f.writelines(new_lines)
            
        os.environ[f"{prefix}_API_KEY"] = api_key
        os.environ[f"{prefix}_SECRET"] = secret
        if password:
            os.environ[f"{prefix}_PASSWORD"] = password
        os.environ[f"{prefix}_TESTNET"] = str(is_testnet).lower()
            
        print(f"Saved keys for {exchange_id} to .env (Testnet: {is_testnet})")
        return True
    except Exception as e:
        print(f"Save Keys Error: {e}")
        return False

# ==========================================
# 策略逻辑
# ==========================================

def check_pinbar(ohlcv, direction='long', body_ratio=0.66):
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
    
    if total_len == 0: return False

    if direction == 'long':
        return lower_shadow > body_len * body_ratio
    elif direction == 'short':
        return upper_shadow > body_len * body_ratio
    
    return False

async def strategy_check(exchange, symbol, main_tf, strategy_config):
    timeframes = ['1h', '4h', '1d']
    signals = {'long': 0, 'short': 0}
    signal_candle = None
    
    try:
        # 获取更多K线以确保包含上一根已收盘K线
        tasks = [exchange.fetch_ohlcv(symbol, tf, limit=5) for tf in timeframes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, res in enumerate(results):
            if isinstance(res, Exception) or len(res) < 2:
                continue
            
            # 使用倒数第二根K线（res[-2]），即上一根已收盘确认的K线
            candle = res[-2] 
            
            if check_pinbar(candle, 'long', strategy_config['ratio']):
                signals['long'] += 1
                if timeframes[i] == main_tf:
                    signal_candle = candle
            if check_pinbar(candle, 'short', strategy_config['ratio']):
                signals['short'] += 1
                if timeframes[i] == main_tf:
                    signal_candle = candle
        
        required_confluence = strategy_config.get('confluence', 2)
        
        if signals['long'] >= required_confluence:
            return 'buy', signal_candle
        if signals['short'] >= required_confluence:
            return 'sell', signal_candle
            
    except Exception as e:
        print(f"Strategy Engine Error: {e}")
    
    return None, None

# ==========================================
# 策略管理器 (Global Strategy Manager)
# ==========================================

class StrategyManager:
    STRATEGIES_FILE = "strategies.json"
    
    def __init__(self):
        self.strategies = {} # id -> dict
        self.tasks = {} # id -> asyncio.Task
        self._load_strategies()
    
    def _save_strategies(self):
        """保存策略到文件"""
        try:
            # 只保存配置和必要的状态，不保存运行时数据
            save_data = {}
            for sid, sdata in self.strategies.items():
                save_data[sid] = {
                    "config": sdata["config"],
                    "start_time": sdata.get("start_time"),
                    "status": sdata.get("status", "running")
                }
            
            with open(self.STRATEGIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            print(f"[StrategyManager] 已保存 {len(save_data)} 个策略到文件")
        except Exception as e:
            print(f"[StrategyManager] 保存策略失败: {e}")
    
    def _load_strategies(self):
        """从文件加载策略（仅加载配置，不自动启动）"""
        try:
            if not os.path.exists(self.STRATEGIES_FILE):
                print(f"[StrategyManager] 策略文件不存在，跳过加载")
                return
            
            with open(self.STRATEGIES_FILE, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
            
            # 只加载到内存，不启动任务（任务需要在 asyncio 环境中启动）
            for sid, sdata in saved_data.items():
                self.strategies[sid] = {
                    "id": sid,
                    "config": sdata["config"],
                    "status": "loaded",  # 标记为已加载但未运行
                    "start_time": sdata.get("start_time"),
                    "last_processed_time": 0,
                    "logs": []
                }
            
            print(f"[StrategyManager] 已从文件加载 {len(saved_data)} 个策略配置")
        except Exception as e:
            print(f"[StrategyManager] 加载策略失败: {e}")
    
    async def restore_strategies(self):
        """恢复所有已加载的策略（服务启动时调用）"""
        restored_count = 0
        for sid, sdata in list(self.strategies.items()):
            if sdata.get("status") == "loaded":
                try:
                    # 重新启动策略任务
                    sdata["status"] = "running"
                    self.tasks[sid] = asyncio.create_task(self._run_strategy(sid))
                    restored_count += 1
                    print(f"[StrategyManager] 已恢复策略: {sdata['config']['symbol']}")
                except Exception as e:
                    print(f"[StrategyManager] 恢复策略失败 {sid}: {e}")
        
        if restored_count > 0:
            print(f"[StrategyManager] 共恢复 {restored_count} 个策略")
            self._save_strategies()  # 更新状态到文件
    
    def get_all(self):
        return [
            {
                "id": k,
                "config": v["config"],
                "status": v["status"],
                "last_signal": v.get("last_signal"),
                "start_time": v.get("start_time")
            }
            for k, v in self.strategies.items()
        ]
    
    def exists(self, exchange_id, symbol, market_type):
        """检查是否存在冲突的策略 (同一交易所+交易对+类型)"""
        for s in self.strategies.values():
            cfg = s['config']
            if (cfg['exchange'] == exchange_id and 
                cfg['symbol'] == symbol and 
                cfg['marketType'] == market_type):
                return True
        return False

    async def start_strategy(self, config: dict):
        exchange_id = config.get('exchange', 'binance')
        symbol = config.get('symbol')
        market_type = config.get('marketType', 'spot')
        
        # 冲突检查
        if self.exists(exchange_id, symbol, market_type):
             raise ValueError(f"策略冲突: {exchange_id} {symbol} {market_type} 已存在运行中的策略。请先停止它。")

        strategy_id = str(uuid.uuid4())
        
        strategy_state = {
            "id": strategy_id,
            "config": config,
            "status": "running",
            "start_time": datetime.datetime.now().isoformat(),
            "last_processed_time": 0,
            "logs": []
        }
        
        self.strategies[strategy_id] = strategy_state
        self.tasks[strategy_id] = asyncio.create_task(self._run_strategy(strategy_id))
        
        # 保存到文件
        self._save_strategies()
        
        print(f"[StrategyManager] Started strategy {strategy_id} for {symbol}")
        return strategy_id

    async def stop_strategy(self, strategy_id):
        if strategy_id in self.tasks:
            self.tasks[strategy_id].cancel()
            try:
                await self.tasks[strategy_id]
            except asyncio.CancelledError:
                pass
            del self.tasks[strategy_id]
        
        if strategy_id in self.strategies:
            self.strategies[strategy_id]['status'] = "stopped"
            # 删除策略
            del self.strategies[strategy_id]
            # 保存到文件
            self._save_strategies()
            print(f"[StrategyManager] Stopped and removed strategy {strategy_id}")
            return True
        return False

    async def _run_strategy(self, strategy_id):
        """策略后台运行主循环"""
        try:
            if strategy_id not in self.strategies:
                return

            strategy_data = self.strategies[strategy_id]
            config = strategy_data['config']
            
            exchange_id = config.get('exchange')
            symbol = config.get('symbol')
            market_type = config.get('marketType')
            timeframe = config.get('timeframe', '1h')
            
            # 构造策略参数
            strategy_config_params = {
                'enabled': True,
                'ratio': float(config.get('ratio', 0.66)),
                'confluence': int(config.get('confluence', 2)),
                'tp': float(config.get('tp', 1.5)),
                'sl': float(config.get('sl', 1.0)),
                'leverage': int(config.get('leverage', 5)),
                'amount': float(config.get('amount', 10))
            }

            # 获取 Exchange 实例
            exchange = await get_exchange(exchange_id, market_type)
            if not exchange:
                print(f"Strategy {strategy_id} failed to init exchange")
                return
            
            # 币安：查询持仓模式（策略初始化时查询一次）
            is_hedge_mode = False  # 默认为单向持仓模式（更安全，兼容性更好）
            if exchange_id == 'binance' and market_type == 'future':
                try:
                    position_mode_response = await exchange.fapiPrivate_get_positionside_dual()
                    is_hedge_mode = position_mode_response.get('dualSidePosition', False)
                    print(f"[策略-持仓模式] API返回: {position_mode_response}, 双向持仓: {is_hedge_mode}")
                except Exception as mode_err:
                    print(f"[策略-持仓模式] 查询失败，默认为单向模式: {mode_err}")
                    is_hedge_mode = False  # 修复：查询失败时默认为单向模式，避免误加 positionSide 参数
                
            await broadcast_message({
                "type": "strategy_log", 
                "id": strategy_id, 
                "msg": f"策略已启动: {symbol} {market_type} {timeframe}",
                "level": "success"
            })

            while True:
                try:
                    # 检查是否停止
                    if strategy_id not in self.strategies:
                        break
                        
                    # 1. 检查信号
                    signal, signal_candle = await strategy_check(exchange, symbol, timeframe, strategy_config_params)
                    
                    if signal and signal_candle:
                         # K线时间戳检查
                        last_time = strategy_data.get('last_processed_time', 0)
                        if signal_candle[0] <= last_time:
                            await asyncio.sleep(5)
                            continue
                        
                        # 标记该K线信号已处理
                        strategy_data['last_processed_time'] = signal_candle[0]
                        strategy_data['last_signal'] = f"{signal.upper()} @ {datetime.datetime.fromtimestamp(signal_candle[0]/1000)}"
                        
                        # 2. 持仓检查（参考NOFX：检查同币种同方向持仓）
                        has_position = False
                        has_same_direction_position = False
                        if market_type == 'future':
                            try:
                                positions = await exchange.fetch_positions()
                                target_side = 'long' if signal == 'buy' else 'short'
                                
                                for pos in positions:
                                    amt = float(pos.get('contracts', 0) or pos.get('info', {}).get('positionAmt', 0))
                                    if pos['symbol'] == symbol and abs(amt) > 0:
                                        has_position = True
                                        # 检查是否同方向（NOFX的防重复逻辑）
                                        pos_side_raw = pos.get('info', {}).get('positionSide', '')
                                        if pos_side_raw in ['LONG', 'SHORT']:
                                            pos_side = pos_side_raw.lower()
                                        else:
                                            pos_side = 'long' if amt > 0 else 'short'
                                        
                                        if pos_side == target_side:
                                            has_same_direction_position = True
                                            break
                            except Exception as e:
                                print(f"Pos check error: {e}")
                        
                        if has_same_direction_position:
                            msg = f"信号忽略: {symbol} 已有{target_side}仓，拒绝重复开仓"
                            await broadcast_message({"type": "strategy_log", "id": strategy_id, "msg": msg, "level": "warning"})
                            print(f"[策略] {msg}")
                            continue
                        
                        if has_position:
                            msg = f"信号忽略: {symbol} 已有持仓（方向不同）"
                            await broadcast_message({"type": "strategy_log", "id": strategy_id, "msg": msg, "level": "warning"})
                            continue

                        # 3. 执行交易
                        # 获取现价
                        ticker = await exchange.fetch_ticker(symbol)
                        current_price = ticker['last']
                        
                        # 计算 TP/SL
                        tp_price = 0
                        sl_price = 0
                        
                        # (使用之前严谨的 TP/SL 计算逻辑)
                        if signal_candle:
                            k_high = signal_candle[2]
                            k_low = signal_candle[3]
                            if signal == 'buy':
                                sl_price = k_low
                                risk = current_price - sl_price
                                if risk <= 0: 
                                    sl_price = current_price * 0.99
                                    risk = current_price - sl_price
                                tp_price = current_price + (risk * strategy_config_params['tp'])
                                sl_price = current_price - (risk * strategy_config_params['sl']) # Double check
                            else:
                                sl_price = k_high
                                risk = sl_price - current_price
                                if risk <= 0:
                                    sl_price = current_price * 1.01
                                    risk = sl_price - current_price
                                tp_price = current_price - (risk * strategy_config_params['tp'])
                                sl_price = current_price + (risk * strategy_config_params['sl'])
                        
                        log_msg = f"触发交易: {signal.upper()} {symbol} @ {current_price}"
                        await broadcast_message({"type": "strategy_log", "id": strategy_id, "msg": log_msg, "level": "success"})

                        # 下单逻辑
                        try:
                            # 参考NOFX：开仓前先取消该币种的所有委托单（清理旧的止损止盈）
                            if market_type == 'future':
                                try:
                                    await exchange.cancel_all_orders(symbol)
                                    print(f"[策略] 已取消 {symbol} 的所有旧委托单")
                                except Exception as cancel_err:
                                    print(f"[策略] 取消旧委托单失败（可能没有）: {cancel_err}")
                            
                            # 设置杠杆
                            if market_type == 'future':
                                try:
                                    await exchange.set_leverage(strategy_config_params['leverage'], symbol)
                                    print(f"[策略] 杠杆已设置为 {strategy_config_params['leverage']}x")
                                except Exception as lev_err:
                                    print(f"[策略] 设置杠杆失败: {lev_err}")

                            # 计算数量
                            usdt_amount = strategy_config_params['amount']
                            
                            # 币安最小订单金额检查
                            if exchange_id == 'binance' and market_type == 'future':
                                min_notional = 5.0  # 币安合约最小订单价值 5 USDT
                                if usdt_amount < min_notional:
                                    msg = f"订单金额 {usdt_amount} USDT 小于最小要求 {min_notional} USDT，跳过下单"
                                    await broadcast_message({"type": "strategy_log", "id": strategy_id, "msg": msg, "level": "warning"})
                                    print(f"[策略警告] {msg}")
                                    continue
                            
                            coin_amount = usdt_amount / current_price
                            
                            # 精度处理... (简化版，详细逻辑复用之前代码)
                            coin_amount = round(coin_amount, 5) 

                            # 市价单开仓
                            open_params = {}
                            # 币安合约：总是指定 positionSide（参考NOFX实现）
                            # 单向模式下币安会自动忽略此参数，双向模式下必须指定
                            if exchange_id == 'binance' and market_type == 'future':
                                position_side = 'LONG' if signal == 'buy' else 'SHORT'
                                open_params['positionSide'] = position_side
                                print(f"[策略开仓] {signal.upper()} positionSide={position_side}")
                            
                            # 执行开仓（参考NOFX）
                            print(f"[策略开仓] {'📈 开多仓' if signal == 'buy' else '📉 开空仓'}: {symbol}")
                            print(f"[策略开仓] 数量: {coin_amount:.4f} | 价格: {current_price:.4f} | 总值: {usdt_amount:.2f} USDT")
                            
                            order = await exchange.create_market_order(symbol, signal, coin_amount, open_params)
                            
                            print(f"[策略开仓] ✓ 开仓成功，订单ID: {order['id']}")
                            await broadcast_message({"type": "strategy_log", "id": strategy_id, "msg": f"✓ {signal.upper()} {symbol} 成功，订单: {order['id']}", "level": "success"})
                            
                            # 止盈止损（合约）
                            if market_type == 'future':
                                exit_side = 'sell' if signal == 'buy' else 'buy'
                                position_side = 'LONG' if signal == 'buy' else 'SHORT'
                                
                                # 止盈止损参数
                                sl_params = {'stopPrice': sl_price, 'closePosition': True}
                                tp_params = {'stopPrice': tp_price, 'closePosition': True}
                                
                                # 币安合约：总是指定 positionSide
                                if exchange_id == 'binance':
                                    sl_params['positionSide'] = position_side
                                    tp_params['positionSide'] = position_side
                                    print(f"[策略止盈止损] positionSide={position_side}")
                                
                                # SL
                                try:
                                    await exchange.create_order(symbol, 'STOP_MARKET', exit_side, coin_amount, sl_params)
                                    print(f"[策略止损] ✓ 止损价设置: {sl_price:.4f}")
                                except Exception as sl_err:
                                    print(f"[策略止损] ⚠ 设置止损失败: {sl_err}")
                                    await broadcast_message({"type": "strategy_log", "id": strategy_id, "msg": f"⚠ 止损设置失败: {sl_err}", "level": "warning"})
                                
                                # TP
                                try:
                                    await exchange.create_order(symbol, 'TAKE_PROFIT_MARKET', exit_side, coin_amount, tp_params)
                                    print(f"[策略止盈] ✓ 止盈价设置: {tp_price:.4f}")
                                    await broadcast_message({"type": "strategy_log", "id": strategy_id, "msg": "✓ 止盈止损已设置", "level": "success"})
                                except Exception as tp_err:
                                    print(f"[策略止盈] ⚠ 设置止盈失败: {tp_err}")
                                    await broadcast_message({"type": "strategy_log", "id": strategy_id, "msg": f"⚠ 止盈设置失败: {tp_err}", "level": "warning"})

                        except Exception as trade_err:
                            error_msg = f"交易失败: {str(trade_err)}"
                            print(f"[策略] ❌ {error_msg}")
                            traceback.print_exc()
                            await broadcast_message({"type": "strategy_log", "id": strategy_id, "msg": f"❌ {error_msg}", "level": "error"})

                    await asyncio.sleep(10) # 10秒检查一次
                except Exception as loop_err:
                    print(f"Strategy Loop Error ({symbol}): {loop_err}")
                    await asyncio.sleep(10)

        except asyncio.CancelledError:
            print(f"Strategy {strategy_id} cancelled")
        except Exception as e:
            print(f"Strategy fatal error: {e}")

strategy_manager = StrategyManager()

# ==========================================
# HTTP Endpoints
# ==========================================

async def initialize_exchanges_task():
    """后台初始化任务"""
    try:
        print("Starting background exchange initialization...")
        # 预热现货和合约
        await get_exchange('binance', 'spot')
        await get_exchange('binance', 'future') # 预初始化合约实例
        print("Background exchange initialization completed.")
    except Exception as e:
        print(f"Warning: Background initialization failed: {e}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(initialize_exchanges_task())
    # 恢复之前保存的策略
    asyncio.create_task(strategy_manager.restore_strategies())

@app.on_event("shutdown")
async def shutdown_event():
    for exchange in exchange_instances.values():
        await exchange.close()
    for exchange in public_exchange_instances.values():
        await exchange.close()

@app.get("/")
async def root():
    return {"message": "Candle Trader API is running"}

@app.get("/api/strategies/list")
async def list_strategies():
    return strategy_manager.get_all()

@app.post("/api/strategies/start")
async def start_strategy(config: dict = Body(...)):
    try:
        strategy_id = await strategy_manager.start_strategy(config)
        return {"success": True, "id": strategy_id, "message": "策略已启动"}
    except ValueError as ve:
        return {"success": False, "message": str(ve)}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/strategies/stop")
async def stop_strategy(data: dict = Body(...)):
    strategy_id = data.get('id')
    if not strategy_id:
        return {"success": False, "message": "Missing ID"}
    success = await strategy_manager.stop_strategy(strategy_id)
    if success:
        return {"success": True, "message": "策略已停止"}
    else:
        return {"success": False, "message": "策略未找到"}

@app.get("/api/markets/{exchange_id}")
async def get_markets(exchange_id: str):
    try:
        if exchange_id not in ['binance', 'okx']:
            return {"error": "Unsupported exchange"}
        
        exchange_class = getattr(ccxt, exchange_id)
        async with exchange_class() as exchange:
            markets = await exchange.load_markets()
            return list(markets.keys())
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/tickers/{exchange_id}")
async def get_tickers(exchange_id: str, symbols: list[str] = Body([])):
    try:
        if exchange_id not in ['binance', 'okx']:
             return {"error": "Unsupported exchange"}

        # 默认使用 spot 获取行情
        exchange = await get_exchange(exchange_id, 'spot')
        if not exchange:
             exchange = await get_exchange(exchange_id, 'spot')
             if not exchange:
                  return {"error": "Exchange init failed"}
             
        if not symbols:
            return {}

        try:
            tickers = await exchange.fetch_tickers(symbols)
        except Exception as fetch_err:
            print(f"Batch fetch failed: {fetch_err}. Trying sequential fetch...")
            tickers = {}
            for sym in symbols:
                try:
                    ticker = await exchange.fetch_ticker(sym)
                    tickers[sym] = ticker
                except:
                    pass
        
        result = {}
        for symbol, ticker in tickers.items():
            percentage = ticker.get('percentage')
            if percentage is None:
                try:
                    if ticker.get('open') and float(ticker['open']) > 0:
                        percentage = (float(ticker['last']) - float(ticker['open'])) / float(ticker['open']) * 100
                    else:
                        percentage = 0
                except:
                    percentage = 0
            
            result[symbol] = {
                'last': ticker['last'],
                'percentage': percentage
            }
        return result
    except Exception as e:
        print(f"Fetch Tickers Error: {e}")
        return {"error": str(e)}

@app.get("/api/balance/{exchange_id}")
async def get_balance(exchange_id: str):
    """获取余额：包含现货和合约"""
    try:
        is_testnet = os.environ.get(f'{exchange_id.upper()}_TESTNET', 'false').lower() == 'true'
        print(f"\n{'='*60}")
        print(f"[余额查询] 交易所: {exchange_id}")
        
        if exchange_id == 'binance':
            try:
                client = get_binance_official_client()
            except Exception as init_err:
                return {"total": {"spot_USDT": 0, "future_USDT": 0}, "error": f"初始化异常: {str(init_err)}"}
                
            if not client:
                return {"total": {"spot_USDT": 0, "future_USDT": 0}, "info": "未配置 API Key"}
            
            response_data = {
                "total": {"spot_USDT": 0.0, "future_USDT": 0.0},
                "info": "查询成功",
                "testnet": is_testnet
            }
            
            # 1. 查询现货余额
            try:
                print(f"[余额查询] 查询现货账户...")
                account = client.get_account()
                balances = account.get('balances', [])
                for balance in balances:
                    if balance['asset'] == 'USDT':
                        free = float(balance['free'])
                        locked = float(balance['locked'])
                        response_data["total"]["spot_USDT"] = free + locked
                        break
            except Exception as e:
                print(f"[余额查询] 现货查询失败: {e}")
                response_data["spot_error"] = str(e)

            # 2. 查询合约余额 (U本位)
            try:
                print(f"[余额查询] 查询合约账户...")
                futures_account = client.futures_account()
                total_wallet_balance = float(futures_account.get('totalWalletBalance', 0))
                total_unrealized_profit = float(futures_account.get('totalUnrealizedProfit', 0))
                total_equity = total_wallet_balance + total_unrealized_profit
                
                response_data["total"]["future_USDT"] = total_equity
                print(f"[余额查询] 合约总权益 (Wallet + Unrealized): {total_equity}")
                
            except Exception as e:
                print(f"[余额查询] 合约查询失败: {e}")
                response_data["future_error"] = str(e)
            
            print(f"[余额查询] 结果: {response_data['total']}")
            print(f"{'='*60}\n")
            return response_data
                
        else:
            # OKX (保持原样)
            exchange = await get_exchange(exchange_id, 'spot')
            if not exchange or not exchange.apiKey:
                return {"total": {"spot_USDT": 0, "future_USDT": 0}, "info": "未配置 API Key"}
            
            balance = await exchange.fetch_balance()
            total_usdt = float(balance.get('USDT', {}).get('total', 0) or 0)
            
            return {
                "total": {
                    "spot_USDT": total_usdt, 
                    "future_USDT": 0 
                },
                "info": "查询成功"
            }
            
    except Exception as e:
        error_msg = str(e)
        print(f"[余额查询] 错误: {error_msg}")
        return {
            "error": error_msg[:100],
            "total": {"spot_USDT": 0, "future_USDT": 0}
        }

@app.get("/api/positions/{exchange_id}")
async def get_current_positions(exchange_id: str):
    """获取当前持仓（合约）"""
    try:
        print(f"\n[持仓查询] 交易所: {exchange_id}")
        
        exchange = await get_exchange(exchange_id, 'future')
        if not exchange or not exchange.apiKey:
            return {"positions": [], "info": "未配置 API Key"}
            
        raw_positions = await exchange.fetch_positions()
        
        positions = []
        
        for pos in raw_positions:
            # 兼容不同交易所字段
            # contracts: 合约数量 (通常是正数)
            # info.positionAmt: 原始持仓数量 (带正负号)
            
            raw_amt = float(pos.get('info', {}).get('positionAmt', 0) or pos.get('contracts', 0))
            if abs(raw_amt) == 0:
                continue
                
                symbol = pos['symbol']
                
            # ========== 判定持仓方向 ==========
            # 优先读取 positionSide (LONG/SHORT/BOTH)
            pos_side_raw = pos.get('info', {}).get('positionSide')
            
            side = None
            if pos_side_raw and pos_side_raw in ['LONG', 'SHORT']:
                side = pos_side_raw.lower()
            else:
                # 单向模式 (BOTH) 或其他交易所：根据数量正负判断
                # positionAmt > 0 => long, < 0 => short
                if raw_amt > 0:
                    side = 'long'
                elif raw_amt < 0:
                    side = 'short'
                else:
                    # 理论上不会进这里，因为上面 check 了 != 0
                    # 但如果 contracts > 0 而 positionAmt 缺失...
                    side = 'long' 
            
            # ========== 判定杠杆倍数 ==========
            leverage = 1
            # 1. CCXT 标准字段
            if pos.get('leverage'):
                        leverage = int(float(pos['leverage']))
            # 2. 原始信息
            elif pos.get('info', {}).get('leverage'):
                leverage = int(float(pos['info']['leverage']))
                
                positions.append({
                    'symbol': pos['symbol'],
                'side': side,
                'amount': abs(raw_amt),
                    'entryPrice': float(pos['entryPrice'] or 0),
                    'unrealizedPnl': float(pos['unrealizedPnl'] or 0),
                    'leverage': leverage,
                    'liquidationPrice': float(pos['liquidationPrice'] or 0),
                    'markPrice': float(pos.get('markPrice') or 0),
                # 传递原始 positionSide 供前端参考或调试
                'positionSide': pos_side_raw 
                })
                
            # print(f"  - {symbol}: {side} {abs(raw_amt)} (原始: {pos_side_raw})")
        
        print(f"[持仓查询] 返回 {len(positions)} 个持仓")
        return {"positions": positions}
        
    except Exception as e:
        print(f"Positions Query Error: {e}")
        traceback.print_exc()
        return {"error": str(e), "positions": []}

@app.post("/api/history/orders")
async def get_history_orders(data: dict = Body(...)):
    """获取历史委托（已关闭订单）- 包含所有市场类型"""
    try:
        exchange_id = data.get('exchange', 'binance')
        symbol = data.get('symbol', 'BTC/USDT')
        market_type = data.get('marketType', 'spot')
        limit = data.get('limit', 50)
        
        print(f"\n[历史委托查询] 交易所: {exchange_id}, 交易对: {symbol}, 类型: {market_type}")
        
        exchange = await get_exchange(exchange_id, market_type)
        if not exchange or not exchange.apiKey:
            return {"error": "Exchange not ready or API Key missing"}
            
        # 获取历史订单（已关闭的订单：已成交、已取消、已拒绝等）
        orders = []
        try:
            # 尝试获取指定交易对的历史订单
            orders = await exchange.fetch_closed_orders(symbol, limit=limit)
            print(f"[历史委托查询] 从 {symbol} 获取到 {len(orders)} 条记录")
        except Exception as fetch_err:
            # 如果失败，尝试获取所有交易对的历史订单
            print(f"[历史委托查询] 单交易对查询失败: {fetch_err}，尝试获取所有订单")
            try:
                orders = await exchange.fetch_closed_orders(limit=limit)
                print(f"[历史委托查询] 从所有交易对获取到 {len(orders)} 条记录")
            except Exception as fetch_all_err:
                print(f"[历史委托查询] 全部查询失败: {fetch_all_err}")
                return {"error": str(fetch_all_err)}
        
        result = []
        for o in orders:
            result.append({
                'id': o['id'],
                'time': o['timestamp'],
                'datetime': o['datetime'],
                'symbol': o['symbol'],
                'side': o['side'],
                'type': o['type'],
                'price': float(o['price'] or 0),
                'avgPrice': float(o['average'] or 0),
                'amount': float(o['amount'] or 0),
                'filled': float(o['filled'] or 0),
                'status': o['status'],
                'cost': float(o['cost'] or 0)
            })
            
        # 按时间倒序
        result.sort(key=lambda x: x['time'], reverse=True)
        print(f"[历史委托查询] 返回 {len(result)} 条记录")
        return result
    except Exception as e:
        print(f"History Orders Error: {e}")
        traceback.print_exc()
        return {"error": str(e)}

@app.post("/api/positions/close")
async def close_position(data: dict = Body(...)):
    """平仓接口（市价平仓）- 自动检测币安持仓模式"""
    try:
        exchange_id = data.get('exchange', 'binance')
        symbol = data.get('symbol', 'BTC/USDT')
        req_side = data.get('side', 'long')  # 前端请求的平仓方向
        req_amount = data.get('amount')  # 可选
        
        print(f"\n{'='*80}")
        print(f"[平仓请求] 交易所: {exchange_id}, 交易对: {symbol}, 方向: {req_side}, 数量: {req_amount}")
        
        # 获取合约 exchange 实例
        exchange = await get_exchange(exchange_id, 'future')
        if not exchange or not exchange.apiKey:
            return {"success": False, "error": "Exchange not ready or API Key missing"}
        
        # 1. 先判断持仓模式 (Hedge Mode)
        is_hedge_mode = False  # 默认为单向持仓模式（更安全，避免误加 positionSide）
        if exchange_id == 'binance':
            try:
                position_mode_response = await exchange.fapiPrivate_get_positionside_dual()
                is_hedge_mode = position_mode_response.get('dualSidePosition', False)
                print(f"[持仓模式] 双向持仓: {is_hedge_mode}")
            except Exception as mode_err:
                print(f"[持仓模式] 查询失败，默认为单向: {mode_err}")
                is_hedge_mode = False
        
        # 2. 获取该币种的实际持仓
        # 注意：fetch_positions([symbol]) 可能返回多个持仓（多和空）
            positions = await exchange.fetch_positions([symbol])
        
        target_pos = None
        real_amt = 0.0
        real_side = None
        
        # 3. 寻找匹配的持仓
        # 逻辑：遍历所有持仓，找到有数量的那一个。
        # 如果是双向模式，且同时有多空双向持仓（锁仓），则根据 req_side 匹配 positionSide
        
        valid_positions = []
        for pos in positions:
            raw_amt = float(pos.get('info', {}).get('positionAmt', 0))
            if abs(raw_amt) == 0: continue # 过滤掉数量为0的
            valid_positions.append(pos)

        # 如果指定了 symbol 但没查到持仓，尝试不传 symbol 查所有（防止 ccxt 过滤逻辑问题）
        if not valid_positions and symbol:
             try:
                 all_positions = await exchange.fetch_positions()
                 for pos in all_positions:
                     # 简单过滤：symbol 必须包含
                     if pos['symbol'] == symbol or pos['symbol'].replace('/', '') == symbol.replace('/', ''):
                         raw_amt = float(pos.get('info', {}).get('positionAmt', 0))
                         if abs(raw_amt) > 0:
                             valid_positions.append(pos)
             except:
                 pass

        if not valid_positions:
             return {"success": False, "error": "当前无持仓"}

        # 尝试匹配逻辑
        # 优先根据 positionSide 匹配 (兼容 LONG/SHORT)
        for pos in valid_positions:
             pos_side_field = pos.get('info', {}).get('positionSide') # LONG / SHORT / BOTH
             if pos_side_field and pos_side_field.upper() in ['LONG', 'SHORT']:
                 # 双向持仓：严格匹配
                 if pos_side_field.lower() == req_side.lower():
                     target_pos = pos
                     break
             else:
                 # 单向持仓(BOTH) 或 其他：根据数量正负判断方向
                # 单向持仓(BOTH) 或 其他：根据数量正负判断方向
                raw_amt = float(pos.get('info', {}).get('positionAmt', 0))
                calculated_side = 'long' if raw_amt > 0 else 'short'
                if calculated_side == req_side.lower():
                    target_pos = pos
                    break
            
        # 如果没严格匹配到（比如前端传错 side），但只有一个持仓，就默认用那个
        if not target_pos and len(valid_positions) == 1:
            target_pos = valid_positions[0]
            print(f"[平仓修正] 未匹配到 {req_side}，自动选择唯一持仓")

        if not target_pos:
            return {"success": False, "error": f"未找到匹配 {req_side} 的持仓"}
        
        # 4. 解析目标持仓的真实数据
        real_raw_amt = float(target_pos.get('info', {}).get('positionAmt', 0))
        real_amt = abs(real_raw_amt)
        
        # 确定真实方向 (关键修正：兼容 BOTH)
        real_side = None
        pos_side_field = target_pos.get('info', {}).get('positionSide')
        
        if pos_side_field and pos_side_field.upper() in ['LONG', 'SHORT']:
            real_side = pos_side_field.lower()
        else:
            # 如果是 BOTH 或 None，则由数量正负决定
            real_side = 'long' if real_raw_amt > 0 else 'short'

        # 确定下单数量
        amount = float(req_amount) if req_amount else real_amt
        if amount > real_amt:
            amount = real_amt # 不能超平

        # 5. 确定买卖方向
        close_side = 'sell' if real_side == 'long' else 'buy'
        
        print(f"[平仓执行] {close_side.upper()} {amount} {symbol}")
        print(f"  → 真实持仓方向: {real_side} (原始: {pos_side_field}, 数量: {real_raw_amt})")
        
        # 6. 构建参数
        params = {'reduceOnly': True}
        
        # 仅当明确检测到双向持仓模式且当前仓位也是双向属性时，才加 positionSide
        # (或者简单点：只要是币安合约，就根据 real_side 加 positionSide，因为单向模式加了也不报错，只要是 BOTH 就行？
        #  不对，单向模式下加 positionSide 可能会报错。所以还是要准确判断)
        
        if exchange_id == 'binance':
            if pos_side_field and pos_side_field.upper() in ['LONG', 'SHORT']:
                # 确实是双向持仓中的某一个
                params['positionSide'] = pos_side_field.upper()
                print(f"  → [参数] positionSide={params['positionSide']}")
            elif is_hedge_mode: 
                # 账户是双向模式，但这个仓位标记怪怪的？安全起见，还是带上
                params['positionSide'] = 'LONG' if real_side == 'long' else 'SHORT'
                print(f"  → [参数-Hedge] positionSide={params['positionSide']}")
        
        # 7. 下单
        order = await exchange.create_market_order(
            symbol,
            close_side,
            amount,
            params
        )
        
        print(f"[平仓成功] 订单ID: {order['id']}")
        
        return {
            "success": True,
            "orderId": order['id'],
            "symbol": symbol,
            "side": close_side,
            "amount": amount
        }
        
    except Exception as e:
        print(f"Close Position Error: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@app.post("/api/positions/close_all")
async def close_all_positions(data: dict = Body(...)):
    """全部平仓接口 - 自动检测币安持仓模式"""
    try:
        exchange_id = data.get('exchange', 'binance')
        
        print(f"\n[全部平仓请求] 交易所: {exchange_id}")
        
        exchange = await get_exchange(exchange_id, 'future')
        if not exchange or not exchange.apiKey:
            return {"success": False, "error": "Exchange not ready or API Key missing"}
        
        # 币安：查询用户的持仓模式
        is_hedge_mode = False  # 默认为单向持仓模式（更安全，避免误加 positionSide）
        if exchange_id == 'binance':
            try:
                position_mode_response = await exchange.fapiPrivate_get_positionside_dual()
                is_hedge_mode = position_mode_response.get('dualSidePosition', False)
                print(f"[持仓模式-全部] API返回: {position_mode_response}, 双向持仓: {is_hedge_mode}")
            except Exception as mode_err:
                print(f"[持仓模式-全部] 查询失败，默认为单向模式: {mode_err}")
                is_hedge_mode = False  # 修复：查询失败时默认为单向模式
        
        # 获取所有持仓
        positions = await exchange.fetch_positions()
        closed_positions = []
        errors = []
        
        for pos in positions:
            # 1. 严谨获取持仓数量 (带正负号)
            raw_amt = float(pos.get('info', {}).get('positionAmt', 0))
            if raw_amt == 0: continue

            symbol = pos['symbol']
            
            # 2. 判定持仓方向 (双向模式依赖 positionSide, 单向模式依赖 amt 正负)
            side = None
            
            if is_hedge_mode:
                # 双向模式：直接读取 positionSide
                pos_side = pos.get('info', {}).get('positionSide')
                if pos_side in ['LONG', 'SHORT']:
                    side = pos_side.lower()
            
            if not side:
                # 单向模式或回退逻辑：根据数量正负判断
                side = 'long' if raw_amt > 0 else 'short'
            
            # 3. 决定平仓的买卖方向
            # 平多(long) -> 卖出(sell)
            # 平空(short) -> 买入(buy)
            close_side = 'sell' if side == 'long' else 'buy'
            
            try:
                print(f"[平仓] {symbol}: {close_side.upper()} {abs(raw_amt)} (持仓方向: {side})")
                
                # 市价单平仓参数
                params = {'reduceOnly': True}
                
                # 4. 币安双向持仓模式：必须指定 positionSide
                if exchange_id == 'binance' and is_hedge_mode:
                    # 关键修正：平仓时，positionSide 必须与持仓方向一致
                    # 平多 -> 操作 LONG 仓位 -> positionSide='LONG'
                    # 平空 -> 操作 SHORT 仓位 -> positionSide='SHORT'
                    params['positionSide'] = 'LONG' if side == 'long' else 'SHORT'
                    print(f"[平仓参数] {symbol}: positionSide={params['positionSide']}")
                
                order = await exchange.create_market_order(
                    symbol,
                    close_side,
                    abs(raw_amt), # 下单数量始终为正数
                    params
                )
                closed_positions.append({
                    "symbol": symbol,
                    "orderId": order['id'],
                    "amount": abs(raw_amt)
                })
            except Exception as e:
                errors.append({"symbol": symbol, "error": str(e)})
                print(f"[平仓失败] {symbol}: {e}")
        
        print(f"[全部平仓完成] 成功: {len(closed_positions)}, 失败: {len(errors)}")
        
        return {
            "success": True,
            "closed": closed_positions,
            "errors": errors,
            "total": len(closed_positions) + len(errors)
        }
        
    except Exception as e:
        print(f"Close All Positions Error: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@app.post("/api/history/trades")
async def get_history_trades(data: dict = Body(...)):
    """获取成交历史（包含手续费和已实现盈亏）- 包含所有市场类型"""
    try:
        exchange_id = data.get('exchange', 'binance')
        symbol = data.get('symbol', 'BTC/USDT')
        market_type = data.get('marketType', 'spot')
        limit = data.get('limit', 50)
        
        print(f"\n[成交历史查询] 交易所: {exchange_id}, 交易对: {symbol}, 类型: {market_type}")
        
        exchange = await get_exchange(exchange_id, market_type)
        if not exchange or not exchange.apiKey:
            return {"error": "Exchange not ready or API Key missing"}
            
        # 获取成交历史（实际成交的订单，包含手续费和盈亏）
        trades = []
        try:
            # 尝试获取指定交易对的成交历史
            trades = await exchange.fetch_my_trades(symbol, limit=limit)
            print(f"[成交历史查询] 从 {symbol} 获取到 {len(trades)} 条记录")
        except Exception as fetch_err:
            # 如果失败，尝试获取所有交易对的成交
            print(f"[成交历史查询] 单交易对查询失败: {fetch_err}，尝试获取所有成交")
            try:
                trades = await exchange.fetch_my_trades(limit=limit)
                print(f"[成交历史查询] 从所有交易对获取到 {len(trades)} 条记录")
            except Exception as fetch_all_err:
                print(f"[成交历史查询] 全部查询失败: {fetch_all_err}")
                return {"error": str(fetch_all_err)}
        
        result = []
        for t in trades:
            fee_cost = 0
            fee_currency = 'USDT'
            if t.get('fee'):
                fee_cost = float(t['fee'].get('cost', 0) or 0)
                fee_currency = t['fee'].get('currency', 'USDT')
                
            result.append({
                'id': t['id'],
                'time': t['timestamp'],
                'datetime': t['datetime'],
                'symbol': t['symbol'],
                'side': t['side'],
                'price': float(t['price'] or 0),
                'amount': float(t['amount'] or 0),
                'cost': float(t['cost'] or 0),
                'fee': fee_cost,
                'feeCurrency': fee_currency,
                # 简单的已实现盈亏估算（仅供参考，实际需要根据开平仓配对计算，这里仅返回原始数据）
                'realizedPnl': float(t.get('info', {}).get('realizedPnl', 0) or 0) 
            })
            
        # 按时间倒序
        result.sort(key=lambda x: x['time'], reverse=True)
        print(f"[成交历史查询] 返回 {len(result)} 条记录")
        return result
    except Exception as e:
        print(f"History Trades Error: {e}")
        traceback.print_exc()
        return {"error": str(e)}

@app.get("/api/keys/status")
async def get_keys_status():
    status = {}
    for ex in ['binance', 'okx']:
        key = os.environ.get(f'{ex.upper()}_API_KEY')
        is_testnet = os.environ.get(f'{ex.upper()}_TESTNET', 'false').lower() == 'true'
        status[ex] = {
            'configured': bool(key and len(key) > 5),
            'testnet': is_testnet
        }
    return status

@app.post("/api/keys/update")
async def update_api_keys(data: dict = Body(...)):
    try:
        exchange_id = data.get('exchange')
        api_key = str(data.get('apiKey', '')).strip()
        secret = str(data.get('secret', '')).strip()
        password = str(data.get('password', '')).strip() if data.get('password') else None
        is_testnet = data.get('isTestnet', False)
        
        if not exchange_id or not api_key or not secret:
            return {"success": False, "message": "缺少必要参数"}
        
        if exchange_id not in ['binance', 'okx']:
            return {"success": False, "message": "不支持的交易所"}
        
        print(f"\n{'='*60}")
        print(f"[API Key 更新] 交易所: {exchange_id}")
        print(f"{'='*60}\n")
        
        save_keys_to_env(exchange_id, api_key, secret, password, is_testnet)
        
        # 清理所有相关实例
        keys_to_remove = [k for k in exchange_instances.keys() if k.startswith(exchange_id)]
        for k in keys_to_remove:
            try:
                await exchange_instances[k].close()
            except:
                pass
            del exchange_instances[k]
        
        if exchange_id == 'binance':
            global binance_official_client
            binance_official_client = None
            
            try:
                client = get_binance_official_client()
                if not client:
                    return {"success": False, "message": "API Key 保存失败或未读取到"}
                
                print(f"[验证] 使用官方SDK验证 API Key...")
                account = client.get_account()
                print(f"[验证] 验证成功")
                
                return {
                    "success": True,
                    "message": f"API Key 设置成功！{'已连接测试网' if is_testnet else '已连接实盘'}",
                    "testnet": is_testnet
                }
            except BinanceAPIException as e:
                error_msg = f"[{e.code}] {e.message}"
                print(f"[验证失败] {error_msg}")
                
                friendly_msg = e.message
                if e.code == -2015:
                    friendly_msg = "权限不足！请在币安后台勾选：允许读取 + 允许现货及杠杆交易"
                elif e.code == -2008:
                    friendly_msg = "API Key 无效，请检查是否复制正确"
                
                return {"success": False, "message": friendly_msg, "detail": error_msg}
            except Exception as e:
                error_str = str(e)
                print(f"[客户端创建异常] {error_str}")
                return {"success": False, "message": f"初始化错误: {error_str}"}
        else:
            new_exchange = await get_exchange(exchange_id, 'spot')
            if not new_exchange:
                return {"success": False, "message": "Exchange 初始化失败"}
            
            try:
                balance = await new_exchange.fetch_balance()
                return {
                    "success": True,
                    "message": "API Key 设置成功",
                    "testnet": is_testnet
                }
            except Exception as e:
                return {"success": False, "message": str(e)[:100]}
            
    except Exception as e:
        print(f"[错误] API Key 更新失败: {str(e)}")
        return {"success": False, "message": f"更新失败: {str(e)}"}


# WebSocket 实时数据推送示例
@app.websocket("/ws/ticker/{exchange_id}/{symbol}/{timeframe}/{market_type}")
async def websocket_endpoint(websocket: WebSocket, exchange_id: str, symbol: str, timeframe: str = "1m", market_type: str = "spot"):
    await websocket.accept()
    connected_websockets.add(websocket)
    
    # 根据市场类型获取对应的 exchange 实例 (spot 或 future)
    exchange = await get_exchange(exchange_id, market_type)
    public_exchange = await get_public_exchange(exchange_id, market_type)
    
    if not exchange or not public_exchange:
        await websocket.close(code=1008, reason="Exchange not found or failed to init")
        return

    formatted_symbol = symbol
    if '/' not in formatted_symbol and len(symbol) > 4:
         if symbol.endswith('USDT'):
             formatted_symbol = f"{symbol[:-4]}/{symbol[-4:]}"
         elif symbol.endswith('BTC'):
              formatted_symbol = f"{symbol[:-3]}/{symbol[-3:]}"
         else:
              formatted_symbol = f"{symbol[:-4]}/{symbol[-4:]}"
    
    # 用户数据推送任务 (持仓、订单)
    async def push_user_data():
        last_positions_count = -1  # 用于检测持仓变化
        while True:
            try:
                if exchange.apiKey:
                    # 1. 获取持仓 (始终尝试获取合约持仓，即使当前在现货模式)
                    positions = []
                    try:
                        # 获取合约 exchange 实例来读取持仓
                        futures_exchange = await get_exchange(exchange_id, 'future')
                        if futures_exchange and futures_exchange.apiKey:
                            raw_positions = await futures_exchange.fetch_positions()
                            
                            # 币安合约：需要单独获取杠杆信息
                            leverage_map = {}
                            if exchange_id == 'binance':
                                try:
                                    account_info = await futures_exchange.fapiPrivate_get_account()
                                    if account_info and 'positions' in account_info:
                                        for pos_info in account_info['positions']:
                                            symbol_raw = pos_info.get('symbol', '')
                                            lev = pos_info.get('leverage', '1')
                                            if symbol_raw.endswith('USDT'):
                                                symbol_std = f"{symbol_raw[:-4]}/{symbol_raw[-4:]}:USDT"
                                                leverage_map[symbol_std] = int(lev)
                                    if last_positions_count == -1:
                                        print(f"[WS-杠杆查询] 获取到 {len(leverage_map)} 个交易对的杠杆信息")
                                except Exception as lev_err:
                                    if last_positions_count == -1:
                                        print(f"[WS-杠杆查询] 失败: {lev_err}")
                            
                            for pos in raw_positions:
                                amt = float(pos.get('contracts', 0) or pos.get('info', {}).get('positionAmt', 0))
                                if abs(amt) > 0.0001:  # 使用更小的阈值来检测持仓
                                    symbol = pos['symbol']
                                    
                                    # ========== 严格读取持仓方向（币安双向持仓模式兼容）==========
                                    side = None
                                    if pos.get('info') and pos['info'].get('positionSide'):
                                        position_side_raw = pos['info']['positionSide']
                                        if position_side_raw in ['LONG', 'SHORT']:
                                            side = position_side_raw.lower()
                                    
                                    # 如果没有 positionSide 或是 'BOTH'（单向持仓模式），则根据数量判断
                                    if not side or side == 'both':
                                        side = 'long' if amt > 0 else 'short'
                                    
                                    # 严格读取杠杆倍数
                                    leverage = 1
                                    
                                    # 方法1: 优先从杠杆映射表读取（币安专用）
                                    if symbol in leverage_map:
                                        leverage = leverage_map[symbol]
                                    
                                    # 方法2: 尝试从CCXT标准化字段读取
                                    elif pos.get('leverage') and pos['leverage'] not in [None, 0]:
                                        try:
                                            leverage = int(float(pos['leverage']))
                                        except (ValueError, TypeError):
                                            pass
                                    
                                    # 方法3: 从原始info读取
                                    elif pos.get('info') and pos['info'].get('leverage'):
                                        try:
                                            raw_lev = pos['info']['leverage']
                                            if raw_lev not in [None, 0, '0', '']:
                                                leverage = int(float(str(raw_lev)))
                                        except (ValueError, TypeError):
                                            pass
                                    
                                    positions.append({
                                        'symbol': pos['symbol'],
                                        'side': side,  # 使用严格判断后的side
                                        'amount': abs(amt),
                                        'entryPrice': float(pos['entryPrice'] or 0),
                                        'unrealizedPnl': float(pos['unrealizedPnl'] or 0),
                                        'leverage': leverage,
                                        'liquidationPrice': float(pos['liquidationPrice'] or 0),
                                        'markPrice': float(pos.get('markPrice') or 0),
                                    })
                            
                            # 检测持仓数量变化并打印日志
                            if len(positions) != last_positions_count:
                                print(f"[持仓更新] 当前持仓数: {len(positions)}")
                                last_positions_count = len(positions)
                    
                    except Exception as e:
                        # print(f"Pos Error: {e}")
                        pass

                    # 2. 获取当前委托（所有交易对，不限于当前图表的交易对）
                    orders = []
                    try:
                        # 获取所有未完成的委托订单
                        raw_orders = await exchange.fetch_open_orders()
                        for ord in raw_orders:
                            orders.append({
                                'id': ord['id'],
                                'symbol': ord['symbol'],
                                'type': ord['type'],
                                'side': ord['side'],
                                'price': float(ord['price'] or 0),
                                'amount': float(ord['amount'] or 0),
                                'filled': float(ord['filled'] or 0),
                                'status': ord['status'],
                                'time': ord['timestamp']
                            })
                        # 只在有订单时才输出日志，减少日志刷屏
                        if len(orders) > 0:
                            print(f"[当前委托] 获取到 {len(orders)} 个未完成订单")
                    except Exception as order_err:
                        # 忽略委托查询错误，避免日志刷屏
                        pass

                    if positions or orders:
                        await websocket.send_json({
                            'type': 'user_data',
                            'positions': positions,
                            'orders': orders
                        })

                await asyncio.sleep(3.0) # 3秒轮询（优化：从1秒改为3秒，减少API压力）
            except Exception as e:
                print(f"Push User Data Error: {e}")
                await asyncio.sleep(3.0)

    user_data_task = asyncio.create_task(push_user_data())

    try:
        try:
            print(f"Fetching initial OHLCV for {formatted_symbol} {timeframe} ({market_type})...")
            
            try:
                if not public_exchange.markets:
                    print("Loading markets (public)...")
                    await public_exchange.load_markets()
            except Exception as load_err:
                print(f"Warning: Failed to load markets: {load_err}")
            
            ohlcv = await public_exchange.fetch_ohlcv(formatted_symbol, timeframe, limit=100)
            
            history_data = []
            for x in ohlcv:
                history_data.append({
                    'time': int(x[0] / 1000), 
                    'open': x[1],
                    'high': x[2],
                    'low': x[3],
                    'close': x[4],
                    'vol': x[5] if len(x) > 5 else 0
                })
            
            await websocket.send_json({
                'type': 'history',
                'data': history_data,
                'symbol': formatted_symbol,
                'timeframe': timeframe,
                'market_type': market_type
            })
            
        except Exception as e:
            error_msg = str(e)
            print(f"Fetch History Error: {error_msg}")
            await websocket.send_json({
                "log": f"获取历史K线失败: {error_msg[:50]}", 
                "type": "error"
            })

        if exchange_id == 'binance':
            ws_symbol = formatted_symbol.replace('/', '').lower()
            
            if market_type == 'future':
                ws_base = "wss://fstream.binance.com/stream"
            else:
                ws_base = "wss://stream.binance.com:9443/stream"
            
            streams = f"{ws_symbol}@kline_{timeframe}/{ws_symbol}@aggTrade"
            ws_url = f"{ws_base}?streams={streams}"

            try:
                 async with websockets.connect(ws_url) as binance_ws:
                    while True:
                        msg = await binance_ws.recv()
                        payload = json.loads(msg)
                        
                        stream_name = payload.get('stream', '')
                        data_content = payload.get('data', {})
                        
                        response_data = {}
                        
                        if '@kline' in stream_name and 'k' in data_content:
                            k = data_content['k']
                            response_data = {
                                'type': 'kline',
                                'time': k['t'] / 1000,
                                'open': float(k['o']),
                                'high': float(k['h']),
                                'low': float(k['l']),
                                'close': float(k['c']),
                                'vol': float(k['v']),
                                'timeframe': timeframe,
                                'market_type': market_type,
                                'price': float(k['c'])
                            }
                        
                        elif '@aggTrade' in stream_name:
                            response_data = {
                                'type': 'trade',
                                'price': float(data_content['p']),
                                'time': data_content['T'] / 1000
                            }
                        
                        if response_data:
                            await websocket.send_json(response_data)
            except Exception as ws_e:
                print(f"Binance WS Error: {ws_e}. Fallback to REST Polling.")
                pass

        consecutive_errors = 0
        while True:
            try:
                ticker = await public_exchange.fetch_ticker(formatted_symbol)
                consecutive_errors = 0
                data = {
                    'time': ticker['timestamp'] / 1000,
                    'price': ticker['last'],
                    'high': ticker['high'],
                    'low': ticker['low'],
                    'vol': ticker['baseVolume'],
                    'timeframe': timeframe
                }
                await websocket.send_json(data)
                await asyncio.sleep(1) 
            except Exception as e:
                consecutive_errors += 1
                error_msg = str(e)
                
                if consecutive_errors <= 3 or consecutive_errors % 10 == 0:
                    friendly_msg = f"获取实时数据失败: {error_msg[:50]}"
                    await websocket.send_json({
                        "log": friendly_msg, 
                        "type": "error"
                    })
                
                wait_time = min(3 + consecutive_errors, 10)
                await asyncio.sleep(wait_time)
                
    except Exception as e:
        print(f"WS Critical Error: {e}")
        try:
            await websocket.close()
        except:
            pass
    finally:
        user_data_task.cancel()
        connected_websockets.discard(websocket)
