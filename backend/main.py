import os
from fastapi import FastAPI, WebSocket, Body
from fastapi.middleware.cors import CORSMiddleware
import ccxt.async_support as ccxt
import asyncio
import json
import httpx
import websockets
from dotenv import load_dotenv
import numpy as np

load_dotenv()

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

async def get_exchange(exchange_id: str):
    if exchange_id in exchange_instances:
        return exchange_instances[exchange_id]
    
    try:
        if exchange_id not in ['binance', 'okx']:
            return None

        print(f"Initializing {exchange_id} exchange instance...")
        exchange_class = getattr(ccxt, exchange_id)
        exchange_options = {
            'timeout': 30000, 
            'enableRateLimit': True,
            'options': {
                 'defaultType': 'spot', 
                 'adjustForTimeDifference': True,
                 # 对于 Binance，禁用自动加载 markets，避免调用需要 API Key 的端点
                 'fetchMarkets': False,  # 禁用自动加载 markets
            }
        }
        
        # 加载 API Keys
        api_key = os.environ.get(f'{exchange_id.upper()}_API_KEY')
        secret = os.environ.get(f'{exchange_id.upper()}_SECRET')
        password = os.environ.get(f'{exchange_id.upper()}_PASSWORD') # OKX 需要
        
        if api_key and secret:
            exchange_options['apiKey'] = api_key
            exchange_options['secret'] = secret
            if password:
                exchange_options['password'] = password
            print(f"Loaded API Credentials for {exchange_id}")
        else:
            print(f"Warning: No API Keys found for {exchange_id}, trading disabled.")
        
        http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
        if http_proxy:
             exchange_options['aiohttp_proxy'] = http_proxy
             print(f"Using Proxy for {exchange_id}: {http_proxy}")

        exchange = exchange_class(exchange_options)
        # 不预加载 markets，按需加载，或者只加载 spot/future
        # await exchange.load_markets() 
        
        exchange_instances[exchange_id] = exchange
        return exchange
    except Exception as e:
        print(f"Exchange Init Error: {e}")
        return None

def save_keys_to_env(exchange_id, api_key, secret, password=None):
    try:
        env_path = ".env"
        # 读取现有内容
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()
        
        new_lines = []
        keys_found = {'key': False, 'secret': False, 'pass': False}
        
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
                    new_lines.append(line) # 保留原样或清空? 这里选择更新
                keys_found['pass'] = True
            else:
                new_lines.append(line)
        
        # 如果没找到，追加到文件末尾
        if not keys_found['key']:
            new_lines.append(f"{prefix}_API_KEY={api_key}\n")
        if not keys_found['secret']:
            new_lines.append(f"{prefix}_SECRET={secret}\n")
        if password and not keys_found['pass']:
            new_lines.append(f"{prefix}_PASSWORD={password}\n")
            
        with open(env_path, "w") as f:
            f.writelines(new_lines)
            
        # 更新环境变量
        os.environ[f"{prefix}_API_KEY"] = api_key
        os.environ[f"{prefix}_SECRET"] = secret
        if password:
            os.environ[f"{prefix}_PASSWORD"] = password
            
        print(f"Saved keys for {exchange_id} to .env")
        return True
    except Exception as e:
        print(f"Save Keys Error: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    # 预初始化
    await get_exchange('binance')
    await get_exchange('okx')

@app.on_event("shutdown")
async def shutdown_event():
    for exchange in exchange_instances.values():
        await exchange.close()

@app.get("/")
async def root():
    return {"message": "Candle Trader API is running"}

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

        exchange = await get_exchange(exchange_id)
        if not exchange:
             # 尝试初始化
             exchange = await get_exchange(exchange_id)
             if not exchange:
                  return {"error": "Exchange init failed"}
             
        # 如果列表为空，默认不获取所有，避免太重
        if not symbols:
            return {}

        # 尝试获取所有 tickers
        try:
            tickers = await exchange.fetch_tickers(symbols)
        except Exception as fetch_err:
            # 如果批量获取失败（部分交易所不支持），尝试逐个获取
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
            # 兼容性处理：有些交易所可能没有 percentage 字段
            percentage = ticker.get('percentage')
            if percentage is None:
                # 尝试自行计算: (last - open) / open * 100
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
    try:
        # 确保 Exchange 实例存在
        exchange = await get_exchange(exchange_id)
        if not exchange:
            # 尝试初始化
            exchange = await get_exchange(exchange_id)
            if not exchange:
                return {"error": "Exchange not init"}
        
        # 检查 API Key 是否已配置，如果没有，尝试从环境变量重新加载
        if not exchange.apiKey:
            # 尝试从环境变量重新加载
            api_key = os.environ.get(f'{exchange_id.upper()}_API_KEY')
            secret = os.environ.get(f'{exchange_id.upper()}_SECRET')
            password = os.environ.get(f'{exchange_id.upper()}_PASSWORD')
            
            if api_key and secret:
                exchange.apiKey = api_key
                exchange.secret = secret
                if password:
                    exchange.password = password
                print(f"Reloaded API Keys from env for {exchange_id}")
            else:
                return {"total": {"USDT": 0, "BTC": 0}, "info": "No API Key"}

        # 获取余额 (尝试获取统一账户或默认类型)
        # 对于 Binance，fetch_balance() 默认是 spot，fetch_balance({'type': 'future'}) 是合约
        # 我们尝试合并两者
        
        total_usdt = 0.0
        total_btc = 0.0
        
        try:
            # 1. 尝试获取 Spot
            spot_bal = await exchange.fetch_balance()
            total_usdt += float(spot_bal.get('USDT', {}).get('total', 0) or 0)
            total_btc += float(spot_bal.get('BTC', {}).get('total', 0) or 0)
        except:
            pass
            
        try:
            # 2. 尝试获取 Future (如果是 Binance 或支持的交易所)
            if exchange_id == 'binance':
                future_bal = await exchange.fetch_balance({'type': 'future'})
                total_usdt += float(future_bal.get('USDT', {}).get('total', 0) or 0)
                total_btc += float(future_bal.get('BTC', {}).get('total', 0) or 0)
            # OKX 是统一账户，fetch_balance 通常返回所有
        except:
            pass

        return {
            "total": {"USDT": total_usdt, "BTC": total_btc}, 
            "info": "Success"
        }
    except Exception as e:
        print(f"Fetch Balance Error: {e}")
        return {"error": str(e)}

@app.get("/api/keys/status")
async def get_keys_status():
    status = {}
    for ex in ['binance', 'okx']:
        key = os.environ.get(f'{ex.upper()}_API_KEY')
        status[ex] = bool(key and len(key) > 5)
    return status

# 策略引擎：检查 Pinbar 形态
def check_pinbar(ohlcv, direction='long', body_ratio=0.66):
    # ohlcv: [time, open, high, low, close, vol]
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
        # 下影线 > 实体的 2/3 (即 body_ratio)
        # 这里的描述可能有歧义，按用户描述：下影线 > 实体 * 2/3 ? 
        # 用户原话："下影线大于当前实体蜡烛台的实体3分之2" -> lower_shadow > body_len * (2/3)
        return lower_shadow > body_len * body_ratio
    elif direction == 'short':
        # 上影线 > 实体 * 2/3
        return upper_shadow > body_len * body_ratio
    
    return False

# 策略引擎：多周期共振检查
async def strategy_check(exchange, symbol, main_tf, strategy_config):
    # strategy_config: { 'enabled': bool, 'ratio': float, 'confluence': int }
    if not strategy_config.get('enabled'):
        return None, None

    timeframes = ['1h', '4h', '1d']
    signals = {'long': 0, 'short': 0}
    
    # 用来存储信号K线的高低点，用于动态止损
    signal_candle = None
    
    try:
        # 并行获取多周期 K 线 (只取最近一根完成的)
        tasks = [exchange.fetch_ohlcv(symbol, tf, limit=2) for tf in timeframes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                print(f"Strategy data fetch error ({timeframes[i]}): {res}")
                continue
            
            # 取倒数第二根（刚完成的那根），或者倒数第一根（当前正在进行的）？
            # 这里为了稳健，我们检查“当前正在进行”的 K 线形态（实时信号）
            candle = res[-1] 
            
            if check_pinbar(candle, 'long', strategy_config['ratio']):
                signals['long'] += 1
                if timeframes[i] == main_tf: # 如果是主周期，记录为信号K线
                    signal_candle = candle
            if check_pinbar(candle, 'short', strategy_config['ratio']):
                signals['short'] += 1
                if timeframes[i] == main_tf: # 如果是主周期，记录为信号K线
                    signal_candle = candle
        
        required_confluence = strategy_config.get('confluence', 2)
        
        if signals['long'] >= required_confluence:
            return 'buy', signal_candle
        if signals['short'] >= required_confluence:
            return 'sell', signal_candle
            
    except Exception as e:
        print(f"Strategy Engine Error: {e}")
    
    return None, None


# WebSocket 实时数据推送示例
@app.websocket("/ws/ticker/{exchange_id}/{symbol}/{timeframe}/{market_type}")
async def websocket_endpoint(websocket: WebSocket, exchange_id: str, symbol: str, timeframe: str = "1m", market_type: str = "spot"):
    await websocket.accept()
    
    # 获取全局 Exchange 实例
    exchange = await get_exchange(exchange_id)
    if not exchange:
        await websocket.close(code=1008, reason="Exchange not found or failed to init")
        return

    # 格式化 symbol
    formatted_symbol = symbol
    if '/' not in formatted_symbol and len(symbol) > 4:
         # 尝试智能推断，默认最后4位是 Quote (如 USDT)
         if symbol.endswith('USDT'):
             formatted_symbol = f"{symbol[:-4]}/{symbol[-4:]}"
         elif symbol.endswith('BTC'):
              formatted_symbol = f"{symbol[:-3]}/{symbol[-3:]}"
         else:
              formatted_symbol = f"{symbol[:-4]}/{symbol[-4:]}"
    
    # 策略配置状态 (从 WebSocket 接收更新)
    strategy_state = {
        'config': {
            'enabled': False, 
            'ratio': 0.66,
            'confluence': 2,
            'tp': 1.5,
            'sl': 1.0,
            'leverage': 5
        }
    }

    # 处理前端发送的指令
    async def handle_client_messages():
        try:
            while True:
                data = await websocket.receive_json()
                if data.get('action') == 'update_strategy':
                    cfg = data.get('config', {})
                    strategy_state['config'] = {
                        'enabled': True,
                        'ratio': float(cfg.get('shadowRatio', 0.66)),
                        'confluence': int(cfg.get('confluenceCount', 2)),
                        'tp': float(cfg.get('takeProfit', 1.5)),
                        'sl': float(cfg.get('stopLoss', 1.0)),
                        'leverage': int(cfg.get('leverage', 5)),
                        'amount': float(cfg.get('orderAmount', 10))
                    }
                    print(f"Strategy Updated: {strategy_state['config']}")
                    await websocket.send_json({"log": "策略参数已更新", "type": "info"})
                
                elif data.get('action') == 'stop_strategy':
                    strategy_state['config']['enabled'] = False
                    print("Strategy Stopped")
                    await websocket.send_json({"log": "策略已停止", "type": "warning"})
                
                elif data.get('action') == 'update_keys':
                    try:
                        # 动态更新 API Key
                        new_key = data.get('apiKey')
                        new_secret = data.get('secret')
                        new_pass = data.get('password')
                        
                        if new_key and new_secret:
                            # 先保存到 .env 文件和环境变量
                            save_keys_to_env(exchange_id, new_key, new_secret, new_pass)
                            
                            # 更新全局实例（包括WebSocket中的和全局字典中的）
                            if exchange:
                                exchange.apiKey = new_key
                                exchange.secret = new_secret
                                if new_pass:
                                    exchange.password = new_pass
                            
                            # 同时更新全局exchange_instances字典中的实例
                            if exchange_id in exchange_instances:
                                global_exchange = exchange_instances[exchange_id]
                                global_exchange.apiKey = new_key
                                global_exchange.secret = new_secret
                                if new_pass:
                                    global_exchange.password = new_pass
                            
                            # 验证 Key 是否有效
                            try:
                                await exchange.load_markets()
                                
                                print(f"API Keys updated and verified for {exchange_id}")
                                await websocket.send_json({"log": "API Key 设置成功并验证通过", "type": "success"})
                            except Exception as verify_err:
                                print(f"Key verification failed: {verify_err}")
                                await websocket.send_json({"log": f"API Key 格式可能错误或网络不通: {str(verify_err)}", "type": "warning"})
                        else:
                            await websocket.send_json({"log": "API Key 或 Secret 不能为空", "type": "error"})
                    except Exception as e:
                        print(f"Update Keys Error: {e}")
                        await websocket.send_json({"log": f"API Key 设置失败: {str(e)}", "type": "error"})

        except Exception as e:
            pass

    asyncio.create_task(handle_client_messages())

    try:
        # 1. 首次连接，先获取历史 K 线数据 (OHLCV)
        try:
            print(f"Fetching initial OHLCV for {formatted_symbol} {timeframe} ({market_type})...")
            # 注意：这里直接使用全局 exchange 实例，不再用 async with 上下文管理器创建新实例
            # 但 ccxt 实例本身是长连接友好的
            
            # 先尝试加载 markets（如果还没加载），但捕获错误
            try:
                if not exchange.markets:
                    await exchange.load_markets()
            except Exception as load_err:
                print(f"Warning: Failed to load markets, trying public endpoint: {load_err}")
                # 如果加载 markets 失败，继续尝试获取 K 线（公共端点不需要 API Key）
            
            ohlcv = await exchange.fetch_ohlcv(formatted_symbol, timeframe, limit=100)
            
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
            print(f"Sent {len(history_data)} history candles.")
            
        except Exception as e:
            error_msg = str(e)
            print(f"Fetch History Error: {error_msg}")
            
            # 提供更友好的错误信息
            if "capital/config/getall" in error_msg or "Connection" in error_msg:
                friendly_msg = "网络连接失败，请检查：1) 网络连接是否正常 2) 是否需要配置代理 3) API Key 权限是否正确"
            elif "API" in error_msg or "key" in error_msg.lower():
                friendly_msg = "API Key 验证失败，请检查 API Key 是否正确或是否有足够权限"
            else:
                friendly_msg = f"获取历史K线失败: {error_msg[:100]}"
            
            await websocket.send_json({
                "log": friendly_msg, 
                "type": "error"
            })

        # 2. 针对 Binance 使用官方 WebSocket 获取毫秒级实时数据
        if exchange_id == 'binance':
            ws_symbol = formatted_symbol.replace('/', '').lower()
            
            if market_type == 'future':
                ws_base = "wss://fstream.binance.com/stream"
            else:
                ws_base = "wss://stream.binance.com:9443/stream"
            
            # 订阅 kline 和 aggTrade
            streams = f"{ws_symbol}@kline_{timeframe}/{ws_symbol}@aggTrade"
            ws_url = f"{ws_base}?streams={streams}"
            
            print(f"Connecting to Binance Combined WS ({market_type}): {ws_url}")
            
            # 策略循环任务
            async def run_strategy_loop():
                while True:
                    try:
                        # 从状态中获取最新配置
                        current_config = strategy_state['config']
                        
                        if current_config['enabled']:
                            # 每 5 秒检查一次策略信号
                            signal, signal_candle = await strategy_check(exchange, formatted_symbol, timeframe, current_config)
                            if signal:
                                # 计算止盈止损价格
                                current_price = 0
                                # 获取当前价格
                                try:
                                    ticker = await exchange.fetch_ticker(formatted_symbol)
                                    current_price = ticker['last']
                                except:
                                    pass
                                
                                if current_price > 0:
                                    # 动态止损逻辑：
                                    # BUY: 止损 = 信号K线 Low
                                    # SELL: 止损 = 信号K线 High
                                    # 如果没有获取到信号K线 (极端情况)，回退到百分比止损
                                    
                                    sl_price = 0
                                    tp_price = 0
                                    
                                    if signal_candle:
                                        # signal_candle format: [time, open, high, low, close, vol]
                                        k_high = signal_candle[2]
                                        k_low = signal_candle[3]
                                        
                                        if signal == 'buy':
                                            sl_price = k_low
                                            # 止盈根据风险回报比 (TP R:R) 计算
                                            # Risk = Entry - SL
                                            risk = current_price - sl_price
                                            if risk > 0:
                                                tp_price = current_price + (risk * current_config['tp'])
                                            else:
                                                # 异常：现价低于止损价（已经破位），或者逻辑错误
                                                # 回退到简单百分比
                                                sl_price = current_price * (1 - 0.01 * current_config['sl'])
                                                tp_price = current_price * (1 + 0.01 * current_config['tp'])
                                                
                                        else: # sell
                                            sl_price = k_high
                                            # Risk = SL - Entry
                                            risk = sl_price - current_price
                                            if risk > 0:
                                                tp_price = current_price - (risk * current_config['tp'])
                                            else:
                                                 # 异常
                                                sl_price = current_price * (1 + 0.01 * current_config['sl'])
                                                tp_price = current_price * (1 - 0.01 * current_config['tp'])
                                    else:
                                        # Fallback logic (same as before)
                                        sl_dist = current_price * 0.01 
                                        if signal == 'buy':
                                            sl_price = current_price - sl_dist * current_config['sl']
                                            tp_price = current_price + sl_dist * current_config['tp']
                                        else:
                                            sl_price = current_price + sl_dist * current_config['sl']
                                            tp_price = current_price - sl_dist * current_config['tp']

                                    log_msg = f"策略触发: 多周期 Pinbar -> {signal.upper()} @ {current_price} (TP: {tp_price:.2f}, SL: {sl_price:.2f} [基于K线极值])"
                                    await websocket.send_json({
                                        "log": log_msg,
                                        "type": "success",
                                        "signal": signal,
                                        "price": current_price,
                                        "tp": tp_price,
                                        "sl": sl_price
                                    })
                                
                                # 实盘下单逻辑
                                try:
                                    if not exchange.apiKey:
                                        await websocket.send_json({"log": "未配置 API Key，无法下单", "type": "error"})
                                        continue

                                    # 1. 设置杠杆 (如果是合约)
                                    if market_type == 'future':
                                        try:
                                            await exchange.set_leverage(current_config['leverage'], formatted_symbol)
                                        except Exception as lev_err:
                                            print(f"Set Leverage Error: {lev_err}")

                                    # 2. 计算数量 (Coin)
                                    # 假设 amount 是 USDT 金额
                                    usdt_amount = current_config.get('amount', 10)
                                    coin_amount = usdt_amount / current_price
                                    
                                    # 处理精度 (简单处理，保留4位小数，具体应参照 exchange.markets[symbol]['precision'])
                                    # 为了稳健，先获取精度信息
                                    try:
                                        market = exchange.market(formatted_symbol)
                                        amount_precision = market['precision']['amount'] if market else 4
                                        # 如果 precision 是 float (如 0.0001)，转为小数位
                                        if isinstance(amount_precision, float):
                                            import math
                                            decimals = int(abs(math.log10(amount_precision)))
                                            coin_amount = round(coin_amount, decimals)
                                        else:
                                            coin_amount = round(coin_amount, int(amount_precision))
                                    except:
                                        coin_amount = round(coin_amount, 4)

                                    if coin_amount <= 0:
                                        await websocket.send_json({"log": "计算下单数量错误 (Too small)", "type": "error"})
                                        continue

                                    side = signal # 'buy' or 'sell'
                                    
                                    # 3. 发送市价单
                                    print(f"Placing Order: {side} {coin_amount} {formatted_symbol}")
                                    order = await exchange.create_market_order(formatted_symbol, side, coin_amount)
                                    
                                    await websocket.send_json({
                                        "log": f"实盘下单成功: {side} {coin_amount} {formatted_symbol} (ID: {order['id']})", 
                                        "type": "success"
                                    })
                                    
                                    # 4. 尝试挂止盈止损 (如果支持 OCO 或 独立 stop order)
                                    # 这里简化处理，仅提示，或如果 exchange 支持 params 附带 sl/tp
                                    # Binance Futures 支持在 create_order 中带 stopLossPrice/takeProfitPrice (部分端点)
                                    # 但通用性起见，建议后续补充单独的 SL/TP 单逻辑
                                    
                                except Exception as trade_err:
                                    err_msg = f"下单失败: {str(trade_err)}"
                                    print(err_msg)
                                    await websocket.send_json({"log": err_msg, "type": "error"})

                        await asyncio.sleep(5)
                    except Exception as se:
                        print(f"Strategy Loop Error: {se}")
                        await asyncio.sleep(5)

            # 启动策略后台任务
            strategy_task = asyncio.create_task(run_strategy_loop())

            try:
                 async with websockets.connect(ws_url) as binance_ws:
                    while True:
                        msg = await binance_ws.recv()
                        payload = json.loads(msg)
                        
                        stream_name = payload.get('stream', '')
                        data_content = payload.get('data', {})
                        
                        response_data = {}
                        
                        # 处理 K 线数据
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
                        
                        # 处理实时成交数据
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
            finally:
                strategy_task.cancel() # 清理任务

        # 3. 进入实时 Ticker 轮询 (通用/回退模式)
        consecutive_errors = 0
        while True:
            try:
                ticker = await exchange.fetch_ticker(formatted_symbol)
                consecutive_errors = 0  # 重置错误计数
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
                print(f"Fetch Real Data Error: {error_msg}")
                
                # 提供更友好的错误信息
                if "capital/config/getall" in error_msg or "Connection" in error_msg:
                    friendly_msg = "网络连接失败，请检查网络或代理设置"
                elif "API" in error_msg or "key" in error_msg.lower():
                    friendly_msg = "API Key 验证失败，请检查 API Key 配置"
                else:
                    friendly_msg = f"获取实时数据失败: {error_msg[:80]}"
                
                # 避免频繁发送错误消息
                if consecutive_errors <= 3 or consecutive_errors % 10 == 0:
                    await websocket.send_json({
                        "log": friendly_msg, 
                        "type": "error"
                    })
                
                # 如果连续错误太多，增加等待时间
                wait_time = min(3 + consecutive_errors, 30)
                await asyncio.sleep(wait_time)
                
    except Exception as e:
        print(f"WS Critical Error: {e}")
        try:
            await websocket.close()
        except:
            pass
    finally:
        pass
