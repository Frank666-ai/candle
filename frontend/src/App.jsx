import React, { useState, useEffect } from 'react';
import { Layout, Card, Select, Button, InputNumber, Radio, Switch, Tabs, List, Tag, Row, Col, Typography, Space, Segmented, Input, Menu } from 'antd';
import { Activity, Zap, Settings, PlayCircle, StopCircle, Key, TrendingUp, TrendingDown } from 'lucide-react';
import { CandleChart } from './components/CandleChart';
import useWebSocket from 'react-use-websocket';
import axios from 'axios';

const { Header, Content, Sider } = Layout;
const { Option } = Select;
const { Title, Text } = Typography;

// 周期对应的秒数
const TIMEFRAMES = {
    '1m': 60,
    '15m': 900,
    '1h': 3600,
    '4h': 14400,
    '1d': 86400
};

function App() {
    const [exchange, setExchange] = useState('binance');
    const [symbol, setSymbol] = useState('BTC/USDT');
    
    // 预设的主流币种列表
    const COIN_LIST = [
        'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
        'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'TRX/USDT', 'DOT/USDT',
        'LINK/USDT', 'MATIC/USDT', 'LTC/USDT', 'SHIB/USDT', 'UNI/USDT',
        'BCH/USDT', 'ATOM/USDT', 'XLM/USDT', 'ETC/USDT', 'FIL/USDT'
    ];
    
    const [marketTickers, setMarketTickers] = useState({});

    const [timeframe, setTimeframe] = useState('1m');

    // 轮询获取行情列表数据
    useEffect(() => {
        const fetchTickers = async () => {
            try {
                // 前端直接构造 url，避免 localhost 跨域或端口问题
                // 在生产环境中应使用相对路径或配置好的 API_BASE_URL
                const response = await axios.post(`http://localhost:8000/api/tickers/${exchange}`, COIN_LIST);
                if (response.data && !response.data.error) {
                    setMarketTickers(response.data);
                }
            } catch (e) {
                // console.error("Fetch tickers failed", e);
            }
        };

        // 立即执行一次
        fetchTickers();
        
        const interval = setInterval(fetchTickers, 5000); 
        return () => clearInterval(interval);
    }, [exchange]);
    const [marketType, setMarketType] = useState('spot'); 
    
    const [chartData, setChartData] = useState([]);
    const [isRunning, setIsRunning] = useState(false);
    const [logs, setLogs] = useState([{ time: new Date().toLocaleTimeString(), msg: '系统初始化完成', type: 'info' }]);
    const [price, setPrice] = useState(0);
    const [aiEnabled, setAiEnabled] = useState(false);
    const [assets, setAssets] = useState({ USDT: 0, BTC: 0 });

    // API Key 配置状态
    const [apiConfig, setApiConfig] = useState({
        apiKey: '',
        secret: '',
        password: '' // OKX only
    });
    
    // API Key 状态 (是否存在)
    const [keyStatus, setKeyStatus] = useState({ binance: false, okx: false });

    // 检查 API Key 状态
    useEffect(() => {
        const checkStatus = async () => {
            try {
                const res = await axios.get('http://localhost:8000/api/keys/status');
                if (res.data) {
                    setKeyStatus(res.data);
                }
            } catch (e) {
                // console.error(e);
            }
        };
        checkStatus();
    }, []); // 仅挂载时检查

    const updateApiKeys = () => {
        sendMessage(JSON.stringify({
            action: 'update_keys',
            ...apiConfig
        }));
        addLog('已发送 API Key 更新请求', 'info');
        // 延迟后清空输入框，重新检查状态，并刷新余额
        setTimeout(async () => {
             setApiConfig({ apiKey: '', secret: '', password: '' });
             try {
                const res = await axios.get('http://localhost:8000/api/keys/status');
                if (res.data) setKeyStatus(res.data);
                
                // 主动刷新余额
                try {
                    const balanceRes = await axios.get(`http://localhost:8000/api/balance/${exchange}`);
                    if (balanceRes.data && !balanceRes.data.error && balanceRes.data.total) {
                        setAssets({
                            USDT: balanceRes.data.total.USDT || 0,
                            BTC: balanceRes.data.total.BTC || 0
                        });
                        addLog(`余额已更新: USDT ${balanceRes.data.total.USDT || 0}, BTC ${balanceRes.data.total.BTC || 0}`, 'success');
                    } else if (balanceRes.data && balanceRes.data.info) {
                        addLog(`余额查询: ${balanceRes.data.info}`, 'warning');
                    }
                } catch (balanceErr) {
                    addLog(`余额查询失败: ${balanceErr.message}`, 'error');
                }
             } catch (e) {}
        }, 2000);
    };
    
    // 轮询获取资产数据
    useEffect(() => {
        const fetchBalance = async () => {
            try {
                const response = await axios.get(`http://localhost:8000/api/balance/${exchange}`);
                if (response.data && !response.data.error && response.data.total) {
                    setAssets({
                        USDT: response.data.total.USDT || 0,
                        BTC: response.data.total.BTC || 0
                    });
                } else if (response.data && response.data.error) {
                    // 如果有错误，也记录一下（但不频繁显示）
                    console.log("Balance fetch error:", response.data.error);
                }
            } catch (e) {
                console.error("Balance fetch exception:", e);
            }
        };

        // 立即执行一次
        fetchBalance();
        // 设置定时间隔，每10秒刷新一次
        const interval = setInterval(fetchBalance, 10000);
        return () => clearInterval(interval);
    }, [exchange, isRunning, keyStatus]); // 当交易所切换、策略启动状态或API Key状态变化时刷新
    
    // 策略配置状态
    const [strategyConfig, setStrategyConfig] = useState({
        enableStrategy: false, // 总开关
        upperRatio: 0.66, // 上影线比例
        lowerRatio: 0.66, // 下影线比例
        confluenceCount: 2,
        takeProfit: 1.5,
        stopLoss: 1.0,
        leverage: 5,
        orderAmount: 10, // 默认下单金额 (USDT)
        trailingStop: false, // 移动止盈开关
        trailingCallback: 0.5, // 回调比例 (如 0.5%)
    });
    
    // 节流 Ref
    const lastPriceUpdateRef = React.useRef(0);

    // 当周期变化时，重新生成初始数据
    useEffect(() => {
        setChartData([]);
        addLog(`切换周期至 ${timeframe} (等待真实数据...)`, 'info');
    }, [timeframe]);

    // WebSocket 连接
    const { sendMessage, lastMessage } = useWebSocket(`ws://localhost:8000/ws/ticker/${exchange}/${symbol.replace('/', '')}/${timeframe}/${marketType}`, {
        shouldReconnect: (closeEvent) => true,
        onOpen: () => {
            addLog(`WebSocket 已连接 (${marketType.toUpperCase()} ${timeframe})`, 'success');
            // setIsMock(false); 
        },
    });

    // 实时数据处理
    useEffect(() => {
        if (lastMessage !== null) {
            const data = JSON.parse(lastMessage.data);
            
            // 处理后端日志消息
            if (data.log) {
                addLog(data.log, data.type || 'info');
                if (data.type === 'warning' && data.log.includes('模拟')) {
                    // setIsMock(true);
                }
                // 如果是策略触发，高亮显示并记录
                if (data.signal) {
                     addLog(`🔥 信号触发: ${data.signal.toUpperCase()} | 价格: ${data.price} | TP: ${data.tp} | SL: ${data.sl}`, 'error');
                }
                // 如果API Key设置成功，主动刷新余额和Key状态
                if (data.type === 'success' && data.log.includes('API Key')) {
                    setTimeout(async () => {
                        try {
                            // 刷新Key状态
                            const res = await axios.get('http://localhost:8000/api/keys/status');
                            if (res.data) setKeyStatus(res.data);
                            
                            // 刷新余额
                            const balanceRes = await axios.get(`http://localhost:8000/api/balance/${exchange}`);
                            if (balanceRes.data && !balanceRes.data.error && balanceRes.data.total) {
                                setAssets({
                                    USDT: balanceRes.data.total.USDT || 0,
                                    BTC: balanceRes.data.total.BTC || 0
                                });
                            }
                        } catch (e) {
                            console.error("Failed to refresh after API Key update:", e);
                        }
                    }, 1000);
                }
                return;
            }
            
            // 处理历史数据包
            if (data.type === 'history') {
                addLog(`收到 ${data.data.length} 条历史 K 线数据`, 'success');
                const sortedData = data.data.sort((a, b) => a.time - b.time);
                setChartData(sortedData);
                if (sortedData.length > 0) {
                    setPrice(sortedData[sortedData.length - 1].close);
                }
                return;
            }
            
            // 处理实时高频 Trade 数据
            if (data.type === 'trade') {
                const now = Date.now();
                // 限制 UI 更新频率
                if (now - lastPriceUpdateRef.current > 100) {
                    setPrice(data.price);
                    lastPriceUpdateRef.current = now;
                    
                    // 同时更新图表最后一根 K 线，实现秒级动态跳动
                    setChartData(prev => {
                        if (prev.length === 0) return prev;
                        
                        const lastCandle = prev[prev.length - 1];
                        const tradeTime = Math.floor(data.time);
                        const interval = TIMEFRAMES[timeframe];
                        
                        // 简单校验：如果 trade 时间远超当前 K 线范围，不盲目新建，等待 kline 推送
                        // 这里只做当前 K 线内部的实时 Close/High/Low 更新
                        if (tradeTime < lastCandle.time) return prev;
                        
                        // 如果已经到了下一根 K 线的时间段，这里不主动新建 (交给 kline 事件处理)，只更新当前这根?
                        // 或者，如果 kline 推送有延迟，我们这里可以预先更新？
                        // 为了防止不同步，我们只更新 "当前正在进行的 K 线"
                        // 如果 tradeTime 超过了 lastCandle.time + interval，说明是新 K 线了。
                        // 稳健起见，只更新当前 K 线。
                        if (tradeTime >= lastCandle.time + interval) {
                             return prev; 
                        }

                        return [...prev.slice(0, -1), {
                            ...lastCandle,
                            close: data.price,
                            high: Math.max(lastCandle.high, data.price),
                            low: Math.min(lastCandle.low, data.price)
                        }];
                    });
                }
                return; 
            }

            if (data.is_mock !== undefined) {
                // setIsMock(data.is_mock);
            }

            if (data.price) {
                setPrice(data.price);
                
                setChartData(prev => {
                    if (prev.length === 0) {
                        return [{
                            time: Math.floor(data.time),
                            open: data.price,
                            high: data.price,
                            low: data.price,
                            close: data.price
                        }];
                    }
                    
                    const lastCandle = prev[prev.length - 1];
                    const currentTime = Math.floor(data.time); 
                    const interval = TIMEFRAMES[timeframe];

                    if (currentTime < lastCandle.time) {
                        return prev;
                    }

                    const updatedLast = {
                        ...lastCandle,
                        close: data.price,
                        high: Math.max(lastCandle.high, data.price),
                        low: Math.min(lastCandle.low, data.price),
                    };
                    
                    if (currentTime - lastCandle.time >= interval) {
                         const newCandle = {
                             time: lastCandle.time + interval, 
                             open: data.price,
                             high: data.price,
                             low: data.price,
                             close: data.price
                         };
                         return [...prev, newCandle];
                    }

                    return [...prev.slice(0, -1), updatedLast];
                });
            }
        }
    }, [lastMessage, timeframe]); 

    const addLog = (msg, type = 'info') => {
        setLogs(prev => [{ time: new Date().toLocaleTimeString(), msg, type }, ...prev].slice(0, 50));
    };

    const handleTrade = (side) => {
        addLog(`尝试${side === 'buy' ? '买入' : '卖出'} ${symbol}...`, 'warning');
        setTimeout(() => {
            addLog(`${side === 'buy' ? '买入' : '卖出'} 成功`, 'success');
        }, 1000);
    };

    const toggleAutoTrade = () => {
        const newRunningState = !isRunning;
        setIsRunning(newRunningState);
        addLog(newRunningState ? '自动交易已启动' : '自动交易已停止', newRunningState ? 'success' : 'warning');
        
        // 发送策略配置给后端
        if (newRunningState) {
            sendMessage(JSON.stringify({ 
                action: 'update_strategy', 
                config: strategyConfig 
            }));
        } else {
            sendMessage(JSON.stringify({ 
                action: 'stop_strategy'
            }));
        }
    };

    const tabItems = [
        {
            key: '3',
            label: 'API 设置',
            children: (
                <div style={{ display: 'flex', flexDirection: 'column', width: '100%', gap: 8 }}>
                    <div style={{ background: '#1f1f1f', padding: 10, borderRadius: 4, marginBottom: 10 }}>
                        <Row align="middle">
                            <Key size={16} style={{ marginRight: 8, color: '#F0B90B' }} />
                            <Text strong style={{ color: '#fff' }}>交易所鉴权</Text>
                        </Row>
                        <div style={{ fontSize: 12, color: '#888', marginTop: 5 }}>
                           请输入 API Key 以启用实盘交易。
                        </div>
                    </div>

                    <div style={{ marginBottom: 10 }}>
                        <Text type="secondary">选择交易所</Text>
                        <Select 
                            style={{ width: '100%', marginTop: 5 }} 
                            value={exchange} 
                            onChange={setExchange}
                        >
                            <Option value="binance">Binance (币安)</Option>
                            <Option value="okx">OKX (欧易)</Option>
                        </Select>
                        {keyStatus[exchange] && (
                            <Tag color="success" style={{ marginTop: 5 }}>当前交易所已配置 API Key</Tag>
                        )}
                    </div>

                    <div style={{ marginBottom: 10 }}>
                        <Text type="secondary">API Key</Text>
                        <Input.Password 
                            value={apiConfig.apiKey} 
                            onChange={e => setApiConfig(prev => ({ ...prev, apiKey: e.target.value }))}
                            placeholder={keyStatus[exchange] ? "已配置 (如需修改请直接输入)" : "输入 API Key"}
                        />
                    </div>
                    <div style={{ marginBottom: 10 }}>
                        <Text type="secondary">Secret Key</Text>
                        <Input.Password 
                            value={apiConfig.secret} 
                            onChange={e => setApiConfig(prev => ({ ...prev, secret: e.target.value }))}
                            placeholder="输入 Secret Key" 
                        />
                    </div>
                    {exchange === 'okx' && (
                         <div style={{ marginBottom: 10 }}>
                            <Text type="secondary">Passphrase (OKX)</Text>
                            <Input.Password 
                                value={apiConfig.password} 
                                onChange={e => setApiConfig(prev => ({ ...prev, password: e.target.value }))}
                                placeholder="输入 Passphrase" 
                            />
                        </div>
                    )}
                    
                    <Button type="primary" block onClick={updateApiKeys} style={{ marginTop: 10 }}>
                        保存并启用
                    </Button>
                </div>
            )
        },
        {
            key: '1',
            label: '手动交易',
            children: (
                <div style={{ display: 'flex', flexDirection: 'column', width: '100%', gap: 8 }}>
                    <div style={{ marginBottom: 10 }}>
                        <Text>价格 (USDT)</Text>
                        <InputNumber style={{ width: '100%' }} defaultValue={50000} />
                    </div>
                    <div style={{ marginBottom: 10 }}>
                        <Text>数量 (BTC)</Text>
                        <InputNumber style={{ width: '100%' }} defaultValue={0.01} />
                    </div>
                    <Row gutter={8}>
                        <Col span={12}>
                            <Button type="primary" block style={{ background: '#26a69a' }} onClick={() => handleTrade('buy')}>买入 (Long)</Button>
                        </Col>
                        <Col span={12}>
                            <Button type="primary" danger block onClick={() => handleTrade('sell')}>卖出 (Short)</Button>
                        </Col>
                    </Row>
                </div>
            ),
        },
        {
            key: '2',
            label: '策略参数',
            children: (
                <div style={{ display: 'flex', flexDirection: 'column', width: '100%', gap: 8 }}>
                    <div style={{ background: '#1f1f1f', padding: 10, borderRadius: 4, marginBottom: 10 }}>
                        <Row justify="space-between" align="middle">
                            <Text strong style={{ color: '#F0B90B' }}>Pinbar 共振策略</Text>
                            <Switch 
                                checked={strategyConfig.enableStrategy} 
                                onChange={v => {
                                    setStrategyConfig(prev => ({ ...prev, enableStrategy: v }));
                                    // 如果处于运行状态，立即发送更新
                                    if (isRunning) {
                                        // 稍后发送，这里主要更新 UI 状态
                                    }
                                }}
                                checkedChildren="开启"
                                unCheckedChildren="关闭"
                            />
                        </Row>
                        <div style={{ fontSize: 12, color: '#888', marginTop: 5 }}>
                            当 1h/4h/1d 中两个周期同时满足影线条件时自动开单。
                        </div>
                    </div>

                    <Row gutter={8} style={{ marginBottom: 10 }}>
                        <Col span={12}>
                            <Text type="secondary" style={{ fontSize: 12 }}>上影线比例 (做空)</Text>
                            <InputNumber 
                                style={{ width: '100%' }} 
                                value={strategyConfig.upperRatio}
                                step={0.01}
                                min={0.1}
                                max={5.0}
                                onChange={v => setStrategyConfig(prev => ({ ...prev, upperRatio: v }))} 
                            />
                        </Col>
                        <Col span={12}>
                            <Text type="secondary" style={{ fontSize: 12 }}>下影线比例 (做多)</Text>
                            <InputNumber 
                                style={{ width: '100%' }} 
                                value={strategyConfig.lowerRatio}
                                step={0.01}
                                min={0.1}
                                max={5.0}
                                onChange={v => setStrategyConfig(prev => ({ ...prev, lowerRatio: v }))} 
                            />
                        </Col>
                    </Row>

                    <Row gutter={8} style={{ marginBottom: 10 }}>
                        <Col span={12}>
                            <Text type="secondary" style={{ fontSize: 12 }}>共振周期数</Text>
                            <InputNumber 
                                style={{ width: '100%' }} 
                                value={strategyConfig.confluenceCount}
                                min={1}
                                max={3}
                                onChange={v => setStrategyConfig(prev => ({ ...prev, confluenceCount: v }))} 
                            />
                        </Col>
                        <Col span={12}>
                            <Text type="secondary" style={{ fontSize: 12 }}>杠杆倍数</Text>
                            <Select 
                                style={{ width: '100%' }}
                                value={strategyConfig.leverage}
                                onChange={v => setStrategyConfig(prev => ({ ...prev, leverage: v }))}
                            >
                                <Option value={1}>1x</Option>
                                <Option value={5}>5x</Option>
                                <Option value={10}>10x</Option>
                                <Option value={20}>20x</Option>
                                <Option value={50}>50x</Option>
                            </Select>
                        </Col>
                        <Col span={12}>
                            <Text type="secondary" style={{ fontSize: 12 }}>单笔金额 (USDT)</Text>
                            <InputNumber 
                                style={{ width: '100%' }} 
                                value={strategyConfig.orderAmount}
                                min={5}
                                max={10000}
                                onChange={v => setStrategyConfig(prev => ({ ...prev, orderAmount: v }))} 
                            />
                        </Col>
                    </Row>

                    <div style={{ borderTop: '1px solid #303030', margin: '10px 0' }} />
                    
                    <Row gutter={8} style={{ marginBottom: 10 }}>
                        <Col span={12}>
                            <Text type="secondary" style={{ fontSize: 12 }}>止盈 (R:R)</Text>
                            <InputNumber 
                                style={{ width: '100%' }} 
                                value={strategyConfig.takeProfit}
                                step={0.1}
                                prefix="R"
                                onChange={v => setStrategyConfig(prev => ({ ...prev, takeProfit: v }))} 
                            />
                        </Col>
                        <Col span={12}>
                            <Text type="secondary" style={{ fontSize: 12 }}>止损 (Risk:Reward)</Text>
                            <InputNumber 
                                style={{ width: '100%' }} 
                                value={strategyConfig.stopLoss}
                                step={0.1}
                                prefix="R"
                                onChange={v => setStrategyConfig(prev => ({ ...prev, stopLoss: v }))} 
                            />
                        </Col>
                    </Row>

                    <Row justify="space-between" align="middle" style={{ marginBottom: 5 }}>
                        <Text type="secondary">移动止盈 (Trailing Stop)</Text>
                        <Switch 
                            size="small"
                            checked={strategyConfig.trailingStop} 
                            onChange={v => setStrategyConfig(prev => ({ ...prev, trailingStop: v }))} 
                        />
                    </Row>
                    {strategyConfig.trailingStop && (
                        <Row gutter={8}>
                            <Col span={24}>
                                <Text type="secondary" style={{ fontSize: 12 }}>回调比例 (%)</Text>
                                <InputNumber 
                                    style={{ width: '100%' }} 
                                    value={strategyConfig.trailingCallback}
                                    step={0.1}
                                    min={0.1}
                                    max={10.0}
                                    suffix="%"
                                    onChange={v => setStrategyConfig(prev => ({ ...prev, trailingCallback: v }))} 
                                />
                            </Col>
                        </Row>
                    )}

                    <Row justify="space-between" style={{ marginTop: 10 }}>
                        <Text>启用 AI 分析</Text>
                        <Switch checked={aiEnabled} onChange={setAiEnabled} />
                    </Row>
                    
                    <Row justify="space-between" style={{ marginTop: 10 }}>
                        <Text>交易模式</Text>
                        <Select defaultValue="spot" size="small" value={marketType} onChange={(val) => {
                            setMarketType(val);
                            setChartData([]); 
                            addLog(`切换交易模式至 ${val === 'spot' ? '现货' : '合约'}`, 'info');
                        }}>
                            <Option value="spot">现货</Option>
                            <Option value="future">合约 (U本位)</Option>
                        </Select>
                    </Row>
                </div>
            ),
        }
    ];

    return (
        <Layout style={{ minHeight: '100vh' }}>
            <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', color: '#fff' }}>
                    <Activity size={24} style={{ marginRight: 10, color: '#F0B90B' }} />
                    <Title level={4} style={{ color: '#fff', margin: 0 }}>Candle Auto Trader</Title>
                </div>
                <Space>
                    <Button type={isRunning ? 'primary' : 'default'} danger={isRunning} icon={isRunning ? <StopCircle /> : <PlayCircle />} onClick={toggleAutoTrade}>
                        {isRunning ? '停止交易' : '开始自动交易'}
                    </Button>
                </Space>
            </Header>
            <Layout>
                <Sider width={260} style={{ background: '#141414', borderRight: '1px solid #303030', overflowY: 'auto' }}>
                    <div style={{ padding: '10px 15px', borderBottom: '1px solid #303030' }}>
                        <Text strong style={{ color: '#fff' }}>主流币种行情</Text>
                    </div>
                    <Menu
                        mode="vertical"
                        selectedKeys={[symbol]}
                        style={{ background: 'transparent', borderRight: 0 }}
                        items={COIN_LIST.map(coin => {
                            const ticker = marketTickers[coin];
                            const change = ticker ? (ticker.percentage !== undefined ? parseFloat(ticker.percentage) : 0) : 0;
                            const color = change >= 0 ? '#26a69a' : '#ef5350';
                            const Icon = change >= 0 ? TrendingUp : TrendingDown;
                            
                            return {
                                key: coin,
                                label: (
                                    <div onClick={() => setSymbol(coin)} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                                            <span style={{ color: '#fff', fontWeight: 500 }}>{coin.split('/')[0]}</span>
                                            <span style={{ fontSize: 10, color: '#666' }}>/USDT</span>
                                        </div>
                                        {ticker ? (
                                            <div style={{ textAlign: 'right' }}>
                                                <div style={{ color: '#fff' }}>{parseFloat(ticker.last).toLocaleString()}</div>
                                                <div style={{ color, fontSize: 12, display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
                                                    {change >= 0 ? '+' : ''}{change.toFixed(2)}%
                                                </div>
                                            </div>
                                        ) : (
                                            <span style={{ color: '#444' }}>--</span>
                                        )}
                                    </div>
                                ),
                                style: { height: 60, margin: 0, paddingLeft: 15, paddingRight: 15 }
                            };
                        })}
                    />
                </Sider>
            <Content style={{ padding: '20px' }}>
                <Row gutter={[16, 16]}>
                    {/* 左侧图表区 */}
                    <Col span={18}>
                        <Card 
                            title={
                                <Space>
                                    <Title level={5} style={{ color: '#fff', margin: 0 }}>{symbol}</Title>
                                    <Tag color={marketType === 'future' ? 'purple' : 'blue'}>
                                        {marketType === 'future' ? '永续合约' : '现货'}
                                    </Tag>
                                    <Segmented 
                                        options={['1m', '15m', '1h', '4h', '1d']} 
                                        value={timeframe}
                                        onChange={setTimeframe}
                                        size="small"
                                    />
                                </Space>
                            } 
                            variant="borderless" 
                            extra={
                                <Space>
                                    <Text>当前价格: <span style={{ color: '#26a69a', fontSize: '1.2em' }}>{price.toFixed(2)}</span></Text>
                                </Space>
                            }
                        >
                            <CandleChart data={chartData} />
                        </Card>
                        
                        <Card title="实时日志" size="small" style={{ marginTop: 16 }}>
                            <div style={{ height: 200, overflowY: 'auto' }}>
                                <ul style={{ padding: 0, margin: 0, listStyle: 'none' }}>
                                    {logs.map((item, index) => (
                                        <li key={index} style={{ 
                                            padding: '8px 12px', 
                                            borderBottom: '1px solid #303030',
                                            fontSize: '14px'
                                        }}>
                                            <Text type="secondary" style={{ marginRight: 8 }}>[{item.time}]</Text> 
                                            <Tag color={item.type === 'success' ? 'green' : item.type === 'warning' ? 'orange' : 'blue'}>{item.type.toUpperCase()}</Tag>
                                            <span style={{ color: '#d9d9d9' }}>{item.msg}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        </Card>
                    </Col>

                    {/* 右侧控制区 */}
                    <Col span={6}>
                        <Card title="交易控制" variant="borderless">
                            <Tabs defaultActiveKey="3" items={tabItems} />
                        </Card>

                        <Card title="账户资产" variant="borderless" style={{ marginTop: 16 }}>
                            <Row justify="space-between">
                                <Text>USDT 余额:</Text>
                                <Text strong>{assets.USDT.toFixed(2)}</Text>
                            </Row>
                            <Row justify="space-between" style={{ marginTop: 8 }}>
                                <Text>BTC 余额:</Text>
                                <Text strong>{assets.BTC.toFixed(4)}</Text>
                            </Row>
                        </Card>
                    </Col>
                </Row>
            </Content>
            </Layout>
        </Layout>
    );
}

export default App;
