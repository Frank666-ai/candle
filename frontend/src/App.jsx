import React, { useState, useEffect } from 'react';
import { Layout, Card, Select, Button, InputNumber, Radio, Switch, Tabs, Tag, Row, Col, Typography, Space, Segmented, Input, Menu, message, Table, Empty, Statistic, Form, Modal, Popconfirm, Badge } from 'antd';
import { Activity, Zap, Settings, PlayCircle, StopCircle, Key, TrendingUp, TrendingDown, RefreshCcw, History, FileText, Plus, Trash2 } from 'lucide-react';
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
                const response = await axios.post(`http://localhost:8000/api/tickers/${exchange}`, COIN_LIST, { timeout: 5000 });
                if (response.data && !response.data.error) {
                    setMarketTickers(response.data);
                }
            } catch (e) {
                // console.warn("Fetch tickers failed", e.message);
            }
        };

        // 立即执行一次
        fetchTickers();

        const interval = setInterval(fetchTickers, 5000);
        return () => clearInterval(interval);
    }, [exchange]);
    const [marketType, setMarketType] = useState('spot');

    const [chartData, setChartData] = useState([]);
    // const [isRunning, setIsRunning] = useState(false); // 移除全局运行状态，改为策略管理
    const [logs, setLogs] = useState([{ time: new Date().toLocaleTimeString(), msg: '系统初始化完成', type: 'info' }]);
    const [price, setPrice] = useState(0);
    const [aiEnabled, setAiEnabled] = useState(false);

    // 资产状态：包含现货和合约 USDT
    const [assets, setAssets] = useState({ spot_USDT: 0, future_USDT: 0 });

    // 持仓与订单数据
    const [positions, setPositions] = useState([]);
    const [openOrders, setOpenOrders] = useState([]);

    // 手动刷新持仓
    const fetchPositions = async () => {
        try {
            const res = await axios.get(`http://localhost:8000/api/positions/${exchange}`);
            if (res.data && Array.isArray(res.data.positions)) {
                setPositions(res.data.positions);
                console.log(`刷新持仓: ${res.data.positions.length} 个`);
            }
        } catch (e) {
            console.error("Fetch positions failed:", e);
        }
    };

    // 历史数据状态
    const [historyOrders, setHistoryOrders] = useState([]);
    const [historyTrades, setHistoryTrades] = useState([]);
    const [isLoadingHistory, setIsLoadingHistory] = useState(false);

    // API Key 配置状态
    const [apiConfig, setApiConfig] = useState({
        apiKey: '',
        secret: '',
        password: '', // OKX only
        isTestnet: false
    });

    // API Key 状态 (是否存在)
    const [keyStatus, setKeyStatus] = useState({ binance: false, okx: false });

    const [messageApi, contextHolder] = message.useMessage();

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

    const updateApiKeys = async () => {
        if (!apiConfig.apiKey || !apiConfig.secret) {
            addLog('请输入 API Key 和 Secret Key', 'error');
            return;
        }

        addLog(`正在保存 ${exchange.toUpperCase()} API Key...`, 'info');
        addLog(`模式: ${apiConfig.isTestnet ? '测试网 (Testnet)' : '实盘 (Live)'}`, 'info');

        try {
            const response = await axios.post('http://localhost:8000/api/keys/update', {
                exchange: exchange,
                apiKey: apiConfig.apiKey,
                secret: apiConfig.secret,
                password: apiConfig.password,
                isTestnet: apiConfig.isTestnet
            });

            if (response.data.success) {
                addLog(response.data.message, 'success');
                setApiConfig({ apiKey: '', secret: '', password: '', isTestnet: false });
                const statusRes = await axios.get('http://localhost:8000/api/keys/status');
                if (statusRes.data) {
                    setKeyStatus(statusRes.data);
                }
                setTimeout(() => fetchBalance(true), 1000);
            } else {
                addLog(response.data.message, 'error');
                if (response.data.detail) {
                    console.error('详细错误:', response.data.detail);
                }
            }
        } catch (error) {
            const errorMsg = error.response?.data?.message || error.message || '未知错误';
            addLog(`API Key 更新失败: ${errorMsg}`, 'error');
        }
    };

    const fetchBalance = async (isManual = false) => {
        if (isManual) messageApi.open({ type: 'loading', content: '正在刷新余额...', key: 'balanceRefresh', duration: 0 });

        try {
            const response = await axios.get(`http://localhost:8000/api/balance/${exchange}`);

            if (response.data && !response.data.error && response.data.total) {
                const { spot_USDT, future_USDT } = response.data.total;

                setAssets({
                    spot_USDT: spot_USDT || 0,
                    future_USDT: future_USDT || 0
                });

                if (isManual) {
                    messageApi.open({ type: 'success', content: '余额刷新成功', key: 'balanceRefresh' });
                }
            } else {
                if (isManual) {
                    messageApi.open({ type: 'error', content: `刷新失败: ${response.data.error || '未知错误'}`, key: 'balanceRefresh' });
                    if (response.data.detail) {
                        console.error('Balance Detail:', response.data.detail);
                    }
                }
            }
        } catch (e) {
            console.error("Balance fetch exception:", e);
            if (isManual) messageApi.open({ type: 'error', content: '请求失败，请检查网络', key: 'balanceRefresh' });
        }
    };

    useEffect(() => {
        fetchBalance(false);
        const interval = setInterval(() => fetchBalance(false), 30000); // 每30秒刷新余额（优化：从10秒改为30秒）
        return () => clearInterval(interval);
    }, [exchange, keyStatus]);

    const fetchHistory = async (type) => {
        setIsLoadingHistory(true);
        try {
            const endpoint = type === 'orders' ? 'orders' : 'trades';
            const response = await axios.post(`http://localhost:8000/api/history/${endpoint}`, {
                exchange,
                symbol,
                marketType,
                limit: 100  // 增加到100条记录
            });

            if (Array.isArray(response.data)) {
                if (type === 'orders') {
                    setHistoryOrders(response.data);
                    console.log(`加载了 ${response.data.length} 条历史委托`);
                } else {
                    setHistoryTrades(response.data);
                    console.log(`加载了 ${response.data.length} 条成交记录`);
                }
            } else if (response.data.error) {
                messageApi.error(`加载失败: ${response.data.error}`);
            }
        } catch (e) {
            console.error(`Fetch history ${type} failed:`, e);
            messageApi.error(`加载${type === 'orders' ? '历史委托' : '成交记录'}失败: ${e.message}`);
        } finally {
            setIsLoadingHistory(false);
        }
    };

    const handleTabChange = (key) => {
        if (key === 'historyOrders') {
            messageApi.loading({ content: '加载历史委托...', key: 'historyLoad', duration: 0 });
            fetchHistory('orders').then(() => {
                messageApi.success({ content: '历史委托加载完成', key: 'historyLoad' });
            });
        } else if (key === 'historyTrades') {
            messageApi.loading({ content: '加载成交历史...', key: 'historyLoad', duration: 0 });
            fetchHistory('trades').then(() => {
                messageApi.success({ content: '成交历史加载完成', key: 'historyLoad' });
            });
        }
    };

    // ==================================================================
    // 策略管理相关状态与逻辑
    // ==================================================================
    const [strategies, setStrategies] = useState([]);
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [isCreatingStrategy, setIsCreatingStrategy] = useState(false);
    const [createForm] = Form.useForm();

    // 打开Modal时设置初始值
    const openCreateModal = () => {
        createForm.setFieldsValue({
            symbol: symbol,
            marketType: marketType,
            timeframe: '1h',
            ratio: 0.67,
            confluence: 2,
            leverage: 5,
            amount: 10,
            tp: 1.5,
            sl: 1.0
        });
        setIsCreateModalOpen(true);
    };

    const fetchStrategies = async () => {
        try {
            const res = await axios.get('http://localhost:8000/api/strategies/list');
            if (Array.isArray(res.data)) {
                setStrategies(res.data);
            }
        } catch (e) {
            console.error("Failed to fetch strategies:", e);
        }
    };

    useEffect(() => {
        fetchStrategies();
        const interval = setInterval(fetchStrategies, 10000); // 每10秒刷新策略状态（优化：从5秒改为10秒）
        return () => clearInterval(interval);
    }, []);

    // 定期刷新持仓（即使WebSocket不在合约模式）
    useEffect(() => {
        fetchPositions(); // 立即执行一次
        const interval = setInterval(fetchPositions, 5000); // 每5秒刷新持仓（优化：从2秒改为5秒）
        return () => clearInterval(interval);
    }, [exchange]);

    const handleCreateStrategy = async (values) => {
        if (isCreatingStrategy) return; // 防止重复提交

        setIsCreatingStrategy(true);
        try {
            const payload = {
                exchange: exchange, // 默认使用当前选择的交易所
                symbol: values.symbol,
                marketType: values.marketType,
                timeframe: values.timeframe,
                // 策略参数
                ratio: values.ratio,
                confluence: values.confluence,
                tp: values.tp,
                sl: values.sl,
                leverage: values.leverage,
                amount: values.amount
            };

            const res = await axios.post('http://localhost:8000/api/strategies/start', payload);
            if (res.data.success) {
                messageApi.success('策略已创建并启动');
                setIsCreateModalOpen(false);
                createForm.resetFields();
                fetchStrategies();
            } else {
                messageApi.error(`创建失败: ${res.data.message}`);
            }
        } catch (e) {
            messageApi.error(`请求错误: ${e.message}`);
        } finally {
            setIsCreatingStrategy(false);
        }
    };

    const handleStopStrategy = async (id) => {
        try {
            const res = await axios.post('http://localhost:8000/api/strategies/stop', { id });
            if (res.data.success) {
                messageApi.success('策略已停止');
                fetchStrategies();
            } else {
                messageApi.error(res.data.message);
            }
        } catch (e) {
            messageApi.error(e.message);
        }
    };

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
        },
    });

    // 实时数据处理
    useEffect(() => {
        if (lastMessage !== null) {
            const data = JSON.parse(lastMessage.data);

            // 处理 user_data (持仓和订单)
            if (data.type === 'user_data') {
                if (data.positions) setPositions(data.positions);
                if (data.orders) setOpenOrders(data.orders);
                return;
            }

            // 处理策略日志消息 (全局或当前)
            if (data.type === 'strategy_log') {
                addLog(data.msg, data.level || 'info');
                // 如果有重要信号，可以在这里弹窗或提醒
                return;
            }

            // 处理后端日志消息 (旧格式兼容)
            if (data.log) {
                addLog(data.log, data.type || 'info');
                if (data.type === 'success' && data.log.includes('API Key')) {
                    setTimeout(async () => {
                        try {
                            const res = await axios.get('http://localhost:8000/api/keys/status');
                            if (res.data) setKeyStatus(res.data);
                            fetchBalance(true); // 触发刷新
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
                if (now - lastPriceUpdateRef.current > 100) {
                    setPrice(data.price);
                    lastPriceUpdateRef.current = now;
                    setChartData(prev => {
                        if (prev.length === 0) return prev;
                        const lastCandle = prev[prev.length - 1];
                        const tradeTime = Math.floor(data.time);
                        const interval = TIMEFRAMES[timeframe];
                        if (tradeTime < lastCandle.time) return prev;
                        if (tradeTime >= lastCandle.time + interval) return prev; // New candle handled by kline event
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

                    if (currentTime < lastCandle.time) return prev;

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

    // 持仓表格列定义
    // 平仓函数
    const handleClosePosition = async (record) => {
        try {
            messageApi.open({ type: 'loading', content: '平仓中...', key: 'close', duration: 0 });
            const response = await axios.post('http://localhost:8000/api/positions/close', {
                exchange,
                symbol: record.symbol,
                side: record.side, // 前端显示的 side ('long' or 'short')
                amount: record.amount
            });

            if (response.data.success) {
                messageApi.open({ type: 'success', content: `${record.symbol} 平仓成功`, key: 'close' });
                fetchPositions(); // 刷新持仓
            } else {
                messageApi.open({ type: 'error', content: `平仓失败: ${response.data.error}`, key: 'close' });
            }
        } catch (e) {
            const errMsg = e.response?.data?.message || e.message || '网络错误';
            messageApi.open({ type: 'error', content: `平仓错误: ${errMsg}`, key: 'close' });
        }
    };

    // 全部平仓函数
    const handleCloseAllPositions = async () => {
        try {
            messageApi.open({ type: 'loading', content: '全部平仓中...', key: 'closeAll', duration: 0 });
            const response = await axios.post('http://localhost:8000/api/positions/close_all', {
                exchange
            });

            if (response.data.success) {
                const { closed, errors } = response.data;
                if (errors && errors.length > 0) {
                    messageApi.open({
                        type: 'warning',
                        content: `平仓完成: 成功 ${closed.length} 个, 失败 ${errors.length} 个`,
                        key: 'closeAll',
                        duration: 5
                    });
                } else {
                    messageApi.open({
                        type: 'success',
                        content: `全部平仓成功 (${closed.length} 个)`,
                        key: 'closeAll'
                    });
                }
                fetchPositions();
            } else {
                messageApi.open({ type: 'error', content: `全部平仓失败: ${response.data.error}`, key: 'closeAll' });
            }
        } catch (e) {
            const errMsg = e.response?.data?.message || e.message || '网络错误';
            messageApi.open({ type: 'error', content: `平仓错误: ${errMsg}`, key: 'closeAll' });
        }
    };

    const positionColumns = [
        {
            title: '合约',
            dataIndex: 'symbol',
            key: 'symbol',
            render: (text, record) => (
                <Space>
                    <Text strong style={{ color: '#fff' }}>{text}</Text>
                    <Tag color={record.leverage > 10 ? 'red' : 'blue'}>{record.leverage}x</Tag>
                </Space>
            )
        },
        {
            title: '数量',
            dataIndex: 'amount',
            key: 'amount',
            render: (text, record) => (
                <Text style={{ color: record.side === 'long' ? '#26a69a' : '#ef5350' }}>
                    {record.side === 'long' ? '+' : '-'}{text}
                </Text>
            )
        },
        {
            title: '开仓价格',
            dataIndex: 'entryPrice',
            key: 'entryPrice',
            render: (text) => parseFloat(text).toFixed(4)
        },
        {
            title: '标记价格',
            dataIndex: 'markPrice',
            key: 'markPrice',
            render: (text) => parseFloat(text || 0).toFixed(4)
        },
        {
            title: '强平价格',
            dataIndex: 'liquidationPrice',
            key: 'liquidationPrice',
            render: (text) => parseFloat(text || 0) > 0 ? parseFloat(text).toFixed(4) : '--'
        },
        {
            title: '未实现盈亏 (ROE)',
            dataIndex: 'unrealizedPnl',
            key: 'unrealizedPnl',
            render: (text, record) => {
                const pnl = parseFloat(text);
                const roe = record.amount * record.entryPrice > 0
                    ? (pnl / (record.amount * record.entryPrice / record.leverage) * 100).toFixed(2)
                    : 0;
                const color = pnl >= 0 ? '#26a69a' : '#ef5350';
                return (
                    <div style={{ color }}>
                        <div>{pnl.toFixed(2)} USDT</div>
                        <div style={{ fontSize: 12 }}>{roe}%</div>
                    </div>
                );
            }
        },
        {
            title: '操作',
            key: 'action',
            width: 100,
            render: (_, record) => (
                <Popconfirm
                    title="确定市价平仓?"
                    description={`将以市价平仓 ${record.symbol} ${record.side === 'long' ? '多单' : '空单'}`}
                    onConfirm={() => handleClosePosition(record)}
                    okText="确定"
                    cancelText="取消"
                >
                    <Button type="primary" danger size="small">
                        平仓
                    </Button>
                </Popconfirm>
            )
        }
    ];

    // 委托表格列定义
    const orderColumns = [
        {
            title: '时间',
            dataIndex: 'time',
            key: 'time',
            render: (text) => new Date(text).toLocaleTimeString()
        },
        { title: '合约', dataIndex: 'symbol', key: 'symbol' },
        { title: '类型', dataIndex: 'type', key: 'type', render: (text) => <Tag>{text.toUpperCase()}</Tag> },
        {
            title: '方向', dataIndex: 'side', key: 'side',
            render: (text) => <Tag color={text === 'buy' ? 'green' : 'red'}>{text === 'buy' ? '买入' : '卖出'}</Tag>
        },
        { title: '价格', dataIndex: 'price', key: 'price' },
        { title: '数量', dataIndex: 'amount', key: 'amount' },
        { title: '已成交', dataIndex: 'filled', key: 'filled' },
        { title: '状态', dataIndex: 'status', key: 'status' }
    ];

    // 历史委托列
    const historyOrderColumns = [
        {
            title: '时间', dataIndex: 'time', key: 'time', width: 160,
            render: (text) => new Date(text).toLocaleString()
        },
        { title: '合约', dataIndex: 'symbol', key: 'symbol' },
        {
            title: '方向', dataIndex: 'side', key: 'side',
            render: (text) => <Tag color={text === 'buy' ? 'green' : 'red'}>{text.toUpperCase()}</Tag>
        },
        {
            title: '类型', dataIndex: 'type', key: 'type',
            render: (text) => <Tag>{text.toUpperCase()}</Tag>
        },
        { title: '成交均价', dataIndex: 'avgPrice', key: 'avgPrice', render: t => parseFloat(t).toFixed(4) },
        { title: '数量', dataIndex: 'amount', key: 'amount' },
        { title: '状态', dataIndex: 'status', key: 'status' },
    ];

    // 成交历史列
    const historyTradeColumns = [
        {
            title: '时间', dataIndex: 'time', key: 'time', width: 160,
            render: (text) => new Date(text).toLocaleString()
        },
        { title: '合约', dataIndex: 'symbol', key: 'symbol' },
        {
            title: '方向', dataIndex: 'side', key: 'side',
            render: (text) => <Tag color={text === 'buy' ? 'green' : 'red'}>{text.toUpperCase()}</Tag>
        },
        { title: '价格', dataIndex: 'price', key: 'price', render: t => parseFloat(t).toFixed(4) },
        { title: '数量', dataIndex: 'amount', key: 'amount' },
        {
            title: '手续费', dataIndex: 'fee', key: 'fee',
            render: (text, record) => <span style={{ color: '#ffa940' }}>{text} {record.feeCurrency}</span>
        },
        {
            title: '已实现盈亏', dataIndex: 'realizedPnl', key: 'realizedPnl',
            render: (text) => {
                const val = parseFloat(text);
                return val !== 0 ? (
                    <span style={{ color: val > 0 ? '#26a69a' : '#ef5350' }}>{val.toFixed(4)}</span>
                ) : '--';
            }
        },
    ];

    const tabItems = [
        {
            key: '3',
            label: 'API 设置',
            children: (
                <form autoComplete="off">
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
                            {keyStatus[exchange]?.configured && (
                                <div style={{ marginTop: 5 }}>
                                    <Tag color="success">已配置 API Key</Tag>
                                    {keyStatus[exchange]?.testnet ? (
                                        <Tag color="orange">测试网</Tag>
                                    ) : (
                                        <Tag color="red">实盘</Tag>
                                    )}
                                </div>
                            )}
                        </div>

                        <div style={{ marginBottom: 10 }}>
                            <Text type="secondary">API Key</Text>
                            <Input.Password
                                value={apiConfig.apiKey}
                                onChange={e => setApiConfig(prev => ({ ...prev, apiKey: e.target.value }))}
                                placeholder={keyStatus[exchange]?.configured ? "已配置 (如需修改请直接输入)" : "输入 API Key"}
                                autoComplete="new-password"
                            />
                        </div>
                        <div style={{ marginBottom: 10 }}>
                            <Text type="secondary">Secret Key</Text>
                            <Input.Password
                                value={apiConfig.secret}
                                onChange={e => setApiConfig(prev => ({ ...prev, secret: e.target.value }))}
                                placeholder="输入 Secret Key"
                                autoComplete="new-password"
                            />
                        </div>
                        {exchange === 'okx' && (
                            <div style={{ marginBottom: 10 }}>
                                <Text type="secondary">Passphrase (OKX)</Text>
                                <Input.Password
                                    value={apiConfig.password}
                                    onChange={e => setApiConfig(prev => ({ ...prev, password: e.target.value }))}
                                    placeholder="输入 Passphrase"
                                    autoComplete="new-password"
                                />
                            </div>
                        )}

                        <div style={{ marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Text type="secondary">使用模拟盘 (Testnet)</Text>
                            <Switch
                                checked={apiConfig.isTestnet}
                                onChange={v => setApiConfig(prev => ({ ...prev, isTestnet: v }))}
                            />
                        </div>

                        <Button type="primary" block onClick={updateApiKeys} style={{ marginTop: 10 }}>
                            保存并启用
                        </Button>
                    </div>
                </form>
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
            label: '策略管理',
            children: (
                <div style={{ display: 'flex', flexDirection: 'column', width: '100%', gap: 12 }}>
                    <Button type="primary" icon={<Plus />} onClick={openCreateModal}>
                        新建策略
                    </Button>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {strategies.length === 0 ? (
                            <Empty description="暂无运行策略" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                        ) : (
                            strategies.map(item => (
                                <div
                                    key={item.id}
                                    style={{
                                        padding: '12px',
                                        borderBottom: '1px solid #303030',
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                        background: '#1a1a1a',
                                        borderRadius: 4
                                    }}
                                >
                                    <div style={{ flex: 1 }}>
                                        <div style={{ marginBottom: 8 }}>
                                            <Space>
                                                <Text strong style={{ color: '#fff' }}>{item.config.symbol}</Text>
                                                <Tag color="blue">{item.config.timeframe}</Tag>
                                                <Tag color={item.config.marketType === 'future' ? 'purple' : 'orange'}>
                                                    {item.config.marketType === 'future' ? '合约' : '现货'}
                                                </Tag>
                                            </Space>
                                        </div>
                                        <div style={{ fontSize: 12 }}>
                                            <div><Text type="secondary">状态: </Text><Tag color="green">运行中</Tag></div>
                                            {item.last_signal && (
                                                <div style={{ marginTop: 4 }}>
                                                    <Text type="secondary">信号: </Text>
                                                    <Text style={{ color: '#faad14' }}>{item.last_signal}</Text>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    <Popconfirm title="确定停止并删除?" onConfirm={() => handleStopStrategy(item.id)}>
                                        <Button type="text" danger icon={<Trash2 />} size="small" />
                                    </Popconfirm>
                                </div>
                            ))
                        )}
                    </div>

                    {/* 新建策略 Modal */}
                    <Modal
                        title="创建多周期 Pinbar 共振策略"
                        open={isCreateModalOpen}
                        onOk={createForm.submit}
                        onCancel={() => {
                            setIsCreateModalOpen(false);
                            createForm.resetFields();
                        }}
                        okText="启动策略"
                        cancelText="取消"
                        width={600}
                        destroyOnClose
                        maskClosable={false}
                        confirmLoading={isCreatingStrategy}
                    >
                        <div style={{ marginBottom: 20, padding: '10px', background: '#262626', borderRadius: 4, fontSize: '13px', color: '#d9d9d9' }}>
                            <Space vertical size={2}>
                                <Text strong style={{ color: '#fff' }}>策略逻辑说明：</Text>
                                <Text style={{ color: '#bbb' }}>1. <span style={{ color: '#F0B90B' }}>形态监测</span>：监测 <span style={{ color: '#fff' }}>主周期</span> K线的影线长度是否大于实体的 <span style={{ color: '#fff' }}>N倍</span> (默认2/3)。</Text>
                                <Text style={{ color: '#bbb' }}>2. <span style={{ color: '#F0B90B' }}>多周期共振</span>：同时检测 <span style={{ color: '#fff' }}>1H, 4H, 1D</span> 三个周期。若其中至少有 <span style={{ color: '#fff' }}>M个</span> 周期同时满足上述形态，则触发信号。</Text>
                                <Text style={{ color: '#bbb' }}>3. <span style={{ color: '#F0B90B' }}>自动执行</span>：信号确认后（K线收盘），在下一根K线的<span style={{ color: '#fff' }}>开盘时刻</span>立即市价买入。</Text>
                                <Text style={{ color: '#bbb' }}>• <span style={{ color: '#26a69a' }}>做多条件</span>：下影线长 (Pinbar) {'->'} 买入</Text>
                                <Text style={{ color: '#bbb' }}>• <span style={{ color: '#ef5350' }}>做空条件</span>：上影线长 (Shooting Star) {'->'} 卖出</Text>
                            </Space>
                        </div>

                        <Form form={createForm} layout="vertical" onFinish={handleCreateStrategy}>
                            <Row gutter={16}>
                                <Col span={12}>
                                    <Form.Item name="symbol" label="交易对 (Symbol)" rules={[{ required: true }]}>
                                        <Select showSearch options={COIN_LIST.map(c => ({ label: c, value: c }))} />
                                    </Form.Item>
                                </Col>
                                <Col span={12}>
                                    <Form.Item name="marketType" label="市场类型 (Market Type)">
                                        <Select>
                                            <Option value="spot">现货 (Spot)</Option>
                                            <Option value="future">合约 (Futures)</Option>
                                        </Select>
                                    </Form.Item>
                                </Col>
                            </Row>
                            <Row gutter={16}>
                                <Col span={12}>
                                    <Form.Item name="timeframe" label="主监控周期 (Main Timeframe)" help="策略主要基于此周期信号触发，建议 1H">
                                        <Select>
                                            <Option value="15m">15分钟</Option>
                                            <Option value="1h">1小时 (推荐)</Option>
                                            <Option value="4h">4小时</Option>
                                        </Select>
                                    </Form.Item>
                                </Col>
                                <Col span={12}>
                                    <Form.Item name="confluence" label="共振周期数量 (Confluence)" help="在 1H, 4H, 1D 中满足条件的最小数量">
                                        <InputNumber min={1} max={3} style={{ width: '100%' }} />
                                    </Form.Item>
                                </Col>
                            </Row>

                            <div style={{ borderTop: '1px solid #303030', margin: '15px 0' }} />
                            <Text strong style={{ display: 'block', marginBottom: 10 }}>形态与风控参数</Text>

                            <Row gutter={16}>
                                <Col span={12}>
                                    <Form.Item name="ratio" label="影线/实体 比例阈值" help="默认 0.67 即大于 2/3">
                                        <InputNumber step={0.01} min={0.1} max={5} style={{ width: '100%' }} />
                                    </Form.Item>
                                </Col>
                                <Col span={12}>
                                    <Form.Item
                                        name="amount"
                                        label="单笔开仓金额 (USDT)"
                                        rules={[
                                            { required: true, message: '请输入开仓金额' },
                                            { type: 'number', min: 5, message: '币安合约最小金额为 5 USDT' }
                                        ]}
                                    >
                                        <InputNumber min={5} style={{ width: '100%' }} placeholder="最小 5 USDT" />
                                    </Form.Item>
                                </Col>
                            </Row>
                            <Row gutter={16}>
                                <Col span={12}>
                                    <Form.Item name="leverage" label="合约杠杆倍数">
                                        <Select>
                                            <Option value={1}>1x</Option>
                                            <Option value={3}>3x</Option>
                                            <Option value={5}>5x</Option>
                                            <Option value={10}>10x</Option>
                                            <Option value={20}>20x</Option>
                                            <Option value={50}>50x</Option>
                                        </Select>
                                    </Form.Item>
                                </Col>
                                <Col span={12}>
                                    <div style={{ display: 'flex', gap: 10 }}>
                                        <Form.Item name="tp" label="止盈 (R倍数)" style={{ flex: 1 }}>
                                            <InputNumber step={0.1} style={{ width: '100%' }} />
                                        </Form.Item>
                                        <Form.Item name="sl" label="止损 (R倍数)" style={{ flex: 1 }}>
                                            <InputNumber step={0.1} style={{ width: '100%' }} />
                                        </Form.Item>
                                    </div>
                                </Col>
                            </Row>
                        </Form>
                    </Modal>
                </div>
            ),
        }
    ];

    return (
        <Layout style={{ minHeight: '100vh' }}>
            {contextHolder}
            <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', color: '#fff' }}>
                    <Activity size={24} style={{ marginRight: 10, color: '#F0B90B' }} />
                    <Title level={4} style={{ color: '#fff', margin: 0 }}>Candle Auto Trader</Title>
                </div>
                <Space>
                    {/* 全局状态指示器 */}
                    <Tag color={strategies.length > 0 ? "processing" : "default"}>
                        {strategies.length > 0 ? `运行中策略: ${strategies.length}` : "无运行策略"}
                    </Tag>
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

                            {/* 底部：持仓、订单、历史信息 */}
                            <Card
                                style={{ marginTop: 16 }}
                                size="small"
                                variant="borderless"
                                styles={{ body: { padding: 0 } }}
                                extra={
                                    <Button
                                        type="text"
                                        size="small"
                                        icon={<RefreshCcw size={14} />}
                                        onClick={() => {
                                            messageApi.loading({ content: '刷新中...', key: 'refreshAll', duration: 0 });
                                            // 同时刷新持仓、委托和历史记录
                                            Promise.all([
                                                fetchPositions(),
                                                fetchHistory('orders'),
                                                fetchHistory('trades')
                                            ]).then(() => {
                                                messageApi.success({ content: '刷新完成', key: 'refreshAll' });
                                            }).catch(() => {
                                                messageApi.error({ content: '刷新失败', key: 'refreshAll' });
                                            });
                                        }}
                                        title="刷新持仓和历史记录"
                                    >
                                        刷新
                                    </Button>
                                }
                            >
                                <Tabs
                                    defaultActiveKey="positions"
                                    onChange={handleTabChange}
                                    tabBarStyle={{ paddingLeft: 16, marginBottom: 0 }}
                                    items={[
                                        {
                                            key: 'positions',
                                            label: `当前持仓 (${positions.length})`,
                                            children: (
                                                <div>
                                                    <Table
                                                        dataSource={positions}
                                                        columns={positionColumns}
                                                        rowKey="symbol"
                                                        pagination={false}
                                                        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无持仓" /> }}
                                                        size="small"
                                                    />
                                                    {positions.length > 0 && (
                                                        <div style={{ marginTop: 12, textAlign: 'center' }}>
                                                            <Popconfirm
                                                                title="确定全部平仓?"
                                                                description={`将以市价平掉所有持仓 (${positions.length} 个)`}
                                                                onConfirm={handleCloseAllPositions}
                                                                okText="确定"
                                                                cancelText="取消"
                                                            >
                                                                <Button type="primary" danger>
                                                                    全部平仓 ({positions.length})
                                                                </Button>
                                                            </Popconfirm>
                                                        </div>
                                                    )}
                                                </div>
                                            )
                                        },
                                        {
                                            key: 'orders',
                                            label: `当前委托 (${openOrders.length})`,
                                            children: (
                                                <Table
                                                    dataSource={openOrders}
                                                    columns={orderColumns}
                                                    rowKey="id"
                                                    pagination={false}
                                                    locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无委托" /> }}
                                                    size="small"
                                                />
                                            )
                                        },
                                        {
                                            key: 'historyOrders',
                                            label: '历史委托',
                                            children: (
                                                <Table
                                                    dataSource={historyOrders}
                                                    columns={historyOrderColumns}
                                                    rowKey="id"
                                                    pagination={{ pageSize: 10 }}
                                                    loading={isLoadingHistory}
                                                    locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" /> }}
                                                    size="small"
                                                />
                                            )
                                        },
                                        {
                                            key: 'historyTrades',
                                            label: '成交历史 (盈亏)',
                                            children: (
                                                <div>
                                                    <div style={{
                                                        marginBottom: 10,
                                                        padding: '8px 12px',
                                                        background: '#1f1f1f',
                                                        borderRadius: 4,
                                                        display: 'flex',
                                                        gap: 20,
                                                        fontSize: 13
                                                    }}>
                                                        <span>
                                                            <Text type="secondary">总盈亏: </Text>
                                                            <Text strong style={{ color: historyTrades.reduce((acc, cur) => acc + (parseFloat(cur.realizedPnl) || 0), 0) >= 0 ? '#26a69a' : '#ef5350' }}>
                                                                {historyTrades.reduce((acc, cur) => acc + (parseFloat(cur.realizedPnl) || 0), 0).toFixed(4)} USDT
                                                            </Text>
                                                        </span>
                                                        <span>
                                                            <Text type="secondary">总手续费: </Text>
                                                            <Text style={{ color: '#ffa940' }}>
                                                                {historyTrades.reduce((acc, cur) => acc + (parseFloat(cur.fee) || 0), 0).toFixed(4)}
                                                            </Text>
                                                        </span>
                                                        <span>
                                                            <Text type="secondary">胜率: </Text>
                                                            <Text>
                                                                {(() => {
                                                                    const validTrades = historyTrades.filter(t => parseFloat(t.realizedPnl) !== 0);
                                                                    if (validTrades.length === 0) return '0.00%';
                                                                    const wins = validTrades.filter(t => parseFloat(t.realizedPnl) > 0).length;
                                                                    return `${(wins / validTrades.length * 100).toFixed(2)}%`;
                                                                })()}
                                                            </Text>
                                                        </span>
                                                    </div>
                                                    <Table
                                                        dataSource={historyTrades}
                                                        columns={historyTradeColumns}
                                                        rowKey="id"
                                                        pagination={{ pageSize: 10 }}
                                                        loading={isLoadingHistory}
                                                        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" /> }}
                                                        size="small"
                                                    />
                                                </div>
                                            )
                                        }
                                    ]}
                                />
                            </Card>

                            <Card title="实时日志" size="small" style={{ marginTop: 16 }}>
                                <div style={{ height: 150, overflowY: 'auto' }}>
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
                                <Tabs defaultActiveKey="2" items={tabItems} />
                            </Card>

                            <Card
                                title="账户资产"
                                variant="borderless"
                                style={{ marginTop: 16 }}
                                extra={
                                    <Button
                                        type="text"
                                        icon={<RefreshCcw size={14} />}
                                        onClick={() => fetchBalance(true)}
                                        title="手动刷新余额"
                                    />
                                }
                            >
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                    <Row justify="space-between" align="middle">
                                        <Text type="secondary">现货 USDT</Text>
                                        <Text strong style={{ fontSize: 16 }}>
                                            {Number(assets.spot_USDT || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                        </Text>
                                    </Row>
                                    <div style={{ borderTop: '1px solid #303030' }} />
                                    <Row justify="space-between" align="middle">
                                        <Text type="secondary">合约 USDT</Text>
                                        <Text strong style={{ fontSize: 16, color: '#d4b106' }}>
                                            {Number(assets.future_USDT || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                        </Text>
                                    </Row>
                                </div>
                            </Card>
                        </Col>
                    </Row>
                </Content>
            </Layout>
        </Layout>
    );
}

export default App;
