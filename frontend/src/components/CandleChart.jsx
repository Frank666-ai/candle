import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, CandlestickSeries } from 'lightweight-charts';

export const CandleChart = ({ data, colors = {} }) => {
    const chartContainerRef = useRef();
    const chartRef = useRef(null);
    const seriesRef = useRef(null);

    useEffect(() => {
        if (!chartContainerRef.current) return;

        // 0. 清理旧图表实例
        if (chartRef.current) {
            try {
                chartRef.current.remove();
            } catch (e) {
                // 忽略移除错误
            }
            chartRef.current = null;
        }

        // 1. 创建图表实例
        try {
            const chart = createChart(chartContainerRef.current, {
                layout: {
                    background: { type: ColorType.Solid, color: '#141414' },
                    textColor: '#d1d4dc',
                },
                grid: {
                    vertLines: { color: 'rgba(42, 46, 57, 0.2)' },
                    horzLines: { color: 'rgba(42, 46, 57, 0.2)' },
                },
                width: chartContainerRef.current.clientWidth,
                height: 500,
                timeScale: {
                    timeVisible: true,
                    secondsVisible: false,
                    borderColor: '#2B2B43',
                },
                rightPriceScale: {
                    borderColor: '#2B2B43',
                },
            });
            
            chartRef.current = chart;

            // 2. 添加 K 线 Series
            // 使用 lightweight-charts v5 标准 API: addSeries(CandlestickSeries, options)
            const newSeries = chart.addSeries(CandlestickSeries, {
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderVisible: false,
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350',
            });
            
            seriesRef.current = newSeries;

            // 3. 初始数据设置 (带去重和排序)
            if (data && data.length > 0) {
                processAndSetData(newSeries, data, chart);
            }
        } catch (err) {
            console.error("Chart initialization failed:", err);
        }

        // 4. 响应式大小调整
        const handleResize = () => {
            if (chartContainerRef.current && chartRef.current) {
                chartRef.current.applyOptions({ 
                    width: chartContainerRef.current.clientWidth 
                });
            }
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            if (chartRef.current) {
                try {
                    chartRef.current.remove();
                } catch(e) {}
                chartRef.current = null;
            }
        };
    }, []); 

    // 数据更新监听
    useEffect(() => {
        if (seriesRef.current && data && data.length > 0) {
            processAndSetData(seriesRef.current, data);
        }
    }, [data]);

    // 辅助函数：处理数据去重、排序并设置
    const processAndSetData = (series, rawData, chartInstance = null) => {
        try {
            const sortedData = [...rawData]
                .filter(item => item && item.time != null)
                .sort((a, b) => a.time - b.time)
                .map(item => ({
                    time: item.time,
                    open: Number(item.open),
                    high: Number(item.high),
                    low: Number(item.low),
                    close: Number(item.close),
                }));
            
            // 严格去重：同一时间戳只保留最后一个
            const uniqueMap = new Map();
            for (const item of sortedData) {
                uniqueMap.set(item.time, item);
            }
            const uniqueData = Array.from(uniqueMap.values());

            if (uniqueData.length > 0) {
                series.setData(uniqueData);
                if (chartInstance) {
                    chartInstance.timeScale().fitContent();
                }
            }
        } catch (e) {
            console.error("Data processing error:", e);
        }
    };

    return (
        <div
            ref={chartContainerRef}
            style={{
                position: 'relative',
                width: '100%',
                height: '500px'
            }}
        />
    );
};
