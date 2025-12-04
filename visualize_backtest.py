"""
回测结果可视化
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import json
import os

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

def load_backtest_data():
    """加载回测数据"""
    if not os.path.exists('backtest_report_btc.json'):
        print("错误: 未找到回测报告文件，请先运行回测！")
        return None, None, None
    
    # 加载报告
    with open('backtest_report_btc.json', 'r', encoding='utf-8') as f:
        report = json.load(f)
    
    # 加载交易记录
    if os.path.exists('backtest_trades_btc.csv'):
        trades_df = pd.read_csv('backtest_trades_btc.csv')
        trades_df['entry_time'] = pd.to_datetime(trades_df['entry_time'])
        trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
    else:
        trades_df = None
    
    # 加载权益曲线
    if os.path.exists('backtest_equity_btc.csv'):
        equity_df = pd.read_csv('backtest_equity_btc.csv')
        equity_df['time'] = pd.to_datetime(equity_df['time'])
    else:
        equity_df = None
    
    return report, trades_df, equity_df


def plot_equity_curve(equity_df, report):
    """绘制权益曲线"""
    fig, ax = plt.subplots(figsize=(15, 6))
    
    ax.plot(equity_df['time'], equity_df['equity'], 
            linewidth=2, color='#2196F3', label='账户权益')
    
    # 添加初始资金参考线
    ax.axhline(y=report['initial_balance'], 
               color='gray', linestyle='--', linewidth=1, 
               label=f"初始资金 ({report['initial_balance']:.2f} USDT)")
    
    ax.set_xlabel('日期', fontsize=12)
    ax.set_ylabel('账户权益 (USDT)', fontsize=12)
    ax.set_title(f"BTC 回测权益曲线 - 收益率: {report['total_return']:.2f}%", fontsize=14, fontweight='bold')
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)
    
    # 格式化x轴日期
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.xticks(rotation=45)
    
    # 填充盈利区域
    ax.fill_between(equity_df['time'], report['initial_balance'], equity_df['equity'],
                     where=equity_df['equity'] >= report['initial_balance'],
                     alpha=0.3, color='green', interpolate=True)
    
    # 填充亏损区域
    ax.fill_between(equity_df['time'], report['initial_balance'], equity_df['equity'],
                     where=equity_df['equity'] < report['initial_balance'],
                     alpha=0.3, color='red', interpolate=True)
    
    plt.tight_layout()
    plt.savefig('backtest_equity_curve.png', dpi=300, bbox_inches='tight')
    print("✓ 权益曲线图已保存: backtest_equity_curve.png")
    plt.close()


def plot_trade_distribution(trades_df):
    """绘制交易分布"""
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    
    # 1. 盈亏分布直方图
    ax1 = axes[0, 0]
    colors = ['green' if x > 0 else 'red' for x in trades_df['pnl']]
    ax1.bar(range(len(trades_df)), trades_df['pnl'], color=colors, alpha=0.7)
    ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax1.set_xlabel('交易序号', fontsize=11)
    ax1.set_ylabel('盈亏 (USDT)', fontsize=11)
    ax1.set_title('每笔交易盈亏分布', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3, axis='y')
    
    # 2. 盈亏百分比分布
    ax2 = axes[0, 1]
    colors = ['green' if x > 0 else 'red' for x in trades_df['pnl_percent']]
    ax2.bar(range(len(trades_df)), trades_df['pnl_percent'], color=colors, alpha=0.7)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax2.set_xlabel('交易序号', fontsize=11)
    ax2.set_ylabel('收益率 (%)', fontsize=11)
    ax2.set_title('每笔交易收益率分布', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3, axis='y')
    
    # 3. 盈亏统计饼图
    ax3 = axes[1, 0]
    win_count = len(trades_df[trades_df['pnl'] > 0])
    loss_count = len(trades_df[trades_df['pnl'] <= 0])
    
    colors_pie = ['#4CAF50', '#F44336']
    explode = (0.05, 0)
    ax3.pie([win_count, loss_count], 
            labels=[f'盈利 ({win_count}笔)', f'亏损 ({loss_count}笔)'],
            colors=colors_pie, autopct='%1.1f%%', explode=explode,
            startangle=90, textprops={'fontsize': 11})
    ax3.set_title('交易胜负分布', fontsize=12, fontweight='bold')
    
    # 4. 持仓时长分布
    ax4 = axes[1, 1]
    trades_df['hold_time'] = (trades_df['exit_time'] - trades_df['entry_time']).dt.total_seconds() / 3600
    ax4.hist(trades_df['hold_time'], bins=20, color='skyblue', edgecolor='black', alpha=0.7)
    ax4.set_xlabel('持仓时长 (小时)', fontsize=11)
    ax4.set_ylabel('交易次数', fontsize=11)
    ax4.set_title('持仓时长分布', fontsize=12, fontweight='bold')
    ax4.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig('backtest_trade_distribution.png', dpi=300, bbox_inches='tight')
    print("✓ 交易分布图已保存: backtest_trade_distribution.png")
    plt.close()


def plot_monthly_returns(trades_df):
    """绘制月度收益"""
    trades_df['month'] = trades_df['exit_time'].dt.to_period('M')
    monthly_pnl = trades_df.groupby('month')['pnl'].sum()
    
    fig, ax = plt.subplots(figsize=(15, 6))
    
    colors = ['green' if x > 0 else 'red' for x in monthly_pnl.values]
    bars = ax.bar(range(len(monthly_pnl)), monthly_pnl.values, color=colors, alpha=0.7)
    
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.set_xlabel('月份', fontsize=12)
    ax.set_ylabel('月度盈亏 (USDT)', fontsize=12)
    ax.set_title('月度收益分布', fontsize=14, fontweight='bold')
    ax.set_xticks(range(len(monthly_pnl)))
    ax.set_xticklabels([str(m) for m in monthly_pnl.index], rotation=45, ha='right')
    ax.grid(True, alpha=0.3, axis='y')
    
    # 在柱子上显示数值
    for i, (bar, value) in enumerate(zip(bars, monthly_pnl.values)):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{value:.1f}',
                ha='center', va='bottom' if value > 0 else 'top',
                fontsize=9)
    
    plt.tight_layout()
    plt.savefig('backtest_monthly_returns.png', dpi=300, bbox_inches='tight')
    print("✓ 月度收益图已保存: backtest_monthly_returns.png")
    plt.close()


def generate_report_summary(report):
    """生成报告摘要图"""
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.axis('off')
    
    # 标题
    title_text = f"BTC 回测报告摘要\nPinbar多周期共振策略"
    ax.text(0.5, 0.95, title_text, ha='center', va='top', 
            fontsize=18, fontweight='bold', color='#1976D2')
    
    # 分组显示指标
    metrics = [
        ("基础信息", [
            f"交易对: {report['symbol']}",
            f"初始资金: {report['initial_balance']:.2f} USDT",
            f"最终资金: {report['final_balance']:.2f} USDT",
        ]),
        ("收益指标", [
            f"总盈亏: {report['total_pnl']:.2f} USDT",
            f"总收益率: {report['total_return']:.2f}%",
            f"最大回撤: {report['max_drawdown']:.2f}%",
        ]),
        ("交易统计", [
            f"总交易次数: {report['total_trades']}",
            f"盈利次数: {report['winning_trades']}",
            f"亏损次数: {report['losing_trades']}",
            f"胜率: {report['win_rate']:.2f}%",
        ]),
        ("风险收益", [
            f"平均盈利: {report['avg_win']:.2f} USDT",
            f"平均亏损: {report['avg_loss']:.2f} USDT",
            f"盈亏比: {abs(report['avg_win']/report['avg_loss']) if report['avg_loss'] != 0 else float('inf'):.2f}",
            f"盈利因子: {report['profit_factor']:.2f}",
        ])
    ]
    
    y_pos = 0.85
    for section_title, items in metrics:
        # 分组标题
        ax.text(0.1, y_pos, section_title, ha='left', va='top',
                fontsize=14, fontweight='bold', color='#424242')
        y_pos -= 0.05
        
        # 指标内容
        for item in items:
            # 根据关键词设置颜色
            if '盈' in item or '胜率' in item or '总收益率' in item:
                if report['total_return'] > 0:
                    color = '#4CAF50'  # 绿色
                else:
                    color = '#F44336'  # 红色
            elif '亏' in item or '回撤' in item:
                color = '#FF9800'  # 橙色
            else:
                color = '#616161'  # 灰色
            
            ax.text(0.15, y_pos, item, ha='left', va='top',
                    fontsize=12, color=color)
            y_pos -= 0.04
        
        y_pos -= 0.03
    
    # 添加策略说明
    ax.text(0.1, 0.15, "策略说明:", ha='left', va='top',
            fontsize=12, fontweight='bold', color='#424242')
    strategy_desc = [
        "• Pinbar形态: 影线/实体 > 0.67 (2/3)",
        "• 多周期共振: 1H, 4H, 1D 至少2个周期满足",
        "• 风险管理: 止盈 1.5R, 止损 1.0R",
        "• 开仓金额: 100 USDT",
        "• 回测周期: 最近1年"
    ]
    y_pos = 0.11
    for desc in strategy_desc:
        ax.text(0.15, y_pos, desc, ha='left', va='top',
                fontsize=10, color='#757575')
        y_pos -= 0.03
    
    # 添加底部时间戳
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ax.text(0.5, 0.02, f"生成时间: {timestamp}", ha='center', va='bottom',
            fontsize=9, color='#BDBDBD')
    
    plt.tight_layout()
    plt.savefig('backtest_report_summary.png', dpi=300, bbox_inches='tight')
    print("✓ 报告摘要图已保存: backtest_report_summary.png")
    plt.close()


def main():
    print("\n" + "="*60)
    print("BTC 回测结果可视化")
    print("="*60 + "\n")
    
    # 加载数据
    report, trades_df, equity_df = load_backtest_data()
    
    if report is None:
        return
    
    print("正在生成可视化图表...\n")
    
    # 生成各种图表
    if equity_df is not None:
        plot_equity_curve(equity_df, report)
    
    if trades_df is not None and len(trades_df) > 0:
        plot_trade_distribution(trades_df)
        plot_monthly_returns(trades_df)
    
    generate_report_summary(report)
    
    print("\n" + "="*60)
    print("可视化完成！已生成以下文件:")
    print("  1. backtest_equity_curve.png      - 权益曲线图")
    print("  2. backtest_trade_distribution.png - 交易分布图")
    print("  3. backtest_monthly_returns.png    - 月度收益图")
    print("  4. backtest_report_summary.png     - 报告摘要图")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()

