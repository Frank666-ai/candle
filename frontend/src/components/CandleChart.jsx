import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, CandlestickSeries } from 'lightweight-charts';

export const CandleChart = ({ data, colors = {} }) => {
    const chartContainerRef = useRef();
    const chartRef = useRef();
    const seriesRef = useRef();

    useEffect(() => {
        if (!chartContainerRef.current) return;

        // 初始创建图表
        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: '#141414' },
                textColor: '#d1d4dc',
            },
            grid: {
                vertLines: { color: 'rgba(42, 46, 57, 0.5)' },
                horzLines: { color: 'rgba(42, 46, 57, 0.5)' },
            },
            width: chartContainerRef.current.clientWidth,
            height: 500,
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
            },
        });
        chartRef.current = chart;

        // 添加 K 线 Series
        try {
             // 使用 v5 推荐的 addSeries 方法，避免 addCandlestickSeries 可能不存在的问题
             const newSeries = chart.addSeries(CandlestickSeries, {
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderVisible: false,
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350',
            });
            seriesRef.current = newSeries;
            
            // 初始数据设置
            if (data && data.length > 0) {
                newSeries.setData(data);
                chart.timeScale().fitContent();
            }
        } catch (e) {
            console.error("Series creation failed:", e);
        }

        // 响应式大小调整
        const resizeObserver = new ResizeObserver(entries => {
            if (!chartRef.current) return;
            
            for (const entry of entries) {
                const { width, height } = entry.contentRect;
                chartRef.current.applyOptions({ width, height });
            }
        });

        resizeObserver.observe(chartContainerRef.current);

        return () => {
            resizeObserver.disconnect();
            if (chartRef.current) {
                chartRef.current.remove();
                chartRef.current = null;
            }
        };
    }, []); // 仅在挂载时执行一次初始化

    // 数据更新监听
    useEffect(() => {
        if (seriesRef.current && data && data.length > 0) {
            try {
                 seriesRef.current.setData(data);
            } catch (e) {
                console.error("Data update error:", e);
            }
        } else {
            // console.log("No data to render or series not ready");
        }
    }, [data]);

    return (
        <div 
            ref={chartContainerRef} 
            style={{ 
                position: 'relative', 
                width: '100%', 
                height: '500px'  // 强制高度，防止高度塌陷
            }} 
        />
    );
};
