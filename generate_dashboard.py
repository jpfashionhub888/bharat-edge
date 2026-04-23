# generate_dashboard.py
# BHARAT EDGE - GitHub Pages Dashboard Generator

import os
import json
from datetime import datetime

TRADES_FILE   = 'logs/bharat_trades.json'
DASHBOARD_DIR = 'docs'
DASHBOARD_FILE= f'{DASHBOARD_DIR}/index.html'

COLORS = {
    'bg'      : '#0a0e1a',
    'card'    : '#111827',
    'card2'   : '#1a2235',
    'border'  : '#1e2d45',
    'text'    : '#e2e8f0',
    'text_dim': '#94a3b8',
    'green'   : '#00ff88',
    'red'     : '#ff4444',
    'yellow'  : '#ffd700',
    'blue'    : '#3b82f6',
    'orange'  : '#f97316',
    'accent'  : '#00d4ff',
}


def load_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception:
        return default


def generate_dashboard():
    os.makedirs(DASHBOARD_DIR, exist_ok=True)

    portfolio = load_json(TRADES_FILE, {
        'capital'         : 100000.0,
        'starting_capital': 100000.0,
        'positions'       : {},
        'trade_history'   : [],
        'saved_at'        : 'Never',
    })

    capital   = portfolio.get('capital', 100000)
    starting  = portfolio.get('starting_capital', 100000)
    positions = portfolio.get('positions', {})
    history   = portfolio.get('trade_history', [])
    saved_at  = portfolio.get('saved_at', 'Never')[:16]

    position_value = sum(
        pos.get('shares', 0) * pos.get(
            'current_price', pos.get('entry_price', 0)
        )
        for pos in positions.values()
    )
    total_value  = capital + position_value
    total_pnl    = total_value - starting
    total_pct    = (total_pnl / starting) * 100

    sells        = [t for t in history if t.get('action') == 'SELL']
    wins         = len([t for t in sells if t.get('pnl', 0) > 0])
    losses       = len([t for t in sells if t.get('pnl', 0) <= 0])
    total_closed = wins + losses
    win_rate     = wins / total_closed * 100 if total_closed > 0 else 0
    realized_pnl = sum(t.get('pnl', 0) for t in sells)

    pnl_color    = COLORS['green'] if total_pnl >= 0 else COLORS['red']
    pnl_sign     = '+' if total_pnl >= 0 else ''
    wr_color     = COLORS['green'] if win_rate >= 50 else COLORS['red']
    now_str      = datetime.now().strftime('%Y-%m-%d %H:%M UTC')

    # Portfolio chart data
    chart_values = [starting]
    chart_labels = ['Start']
    for trade in history:
        if trade.get('action') == 'SELL':
            chart_values.append(
                chart_values[-1] + trade.get('pnl', 0)
            )
            chart_labels.append(trade.get('date', '')[:10])
    chart_values.append(total_value)
    chart_labels.append('Now')

    # Positions HTML
    positions_html = ''
    if positions:
        for sym, pos in positions.items():
            shares  = pos.get('shares', 0)
            entry   = pos.get('entry_price', 0)
            current = pos.get('current_price', entry)
            pnl     = (current - entry) * shares
            pnl_pct = (current - entry) / entry * 100 if entry > 0 else 0
            p_color = COLORS['green'] if pnl >= 0 else COLORS['red']
            p_sign  = '+' if pnl >= 0 else ''
            positions_html += f"""
            <tr>
                <td style="color:{COLORS['accent']};
                font-weight:700">{sym}</td>
                <td>{shares}</td>
                <td>Rs{entry:.2f}</td>
                <td>Rs{current:.2f}</td>
                <td>Rs{pos.get('cost', 0):.2f}</td>
                <td style="color:{p_color};font-weight:700">
                    {p_sign}Rs{pnl:.2f}
                </td>
                <td style="color:{p_color}">
                    {p_sign}{pnl_pct:.2f}%
                </td>
                <td style="color:{COLORS['text_dim']}">
                    {pos.get('entry_date', '')[:10]}
                </td>
                <td style="color:{COLORS['yellow']}">
                    {pos.get('reason', '')}
                </td>
            </tr>"""
    else:
        positions_html = f"""
        <tr>
            <td colspan="9"
            style="color:{COLORS['text_dim']};
            text-align:center;padding:20px">
                No open positions
            </td>
        </tr>"""

    # Trade History HTML
    history_html = ''
    for trade in reversed(history[-30:]):
        action  = trade.get('action', '')
        pnl     = trade.get('pnl', 0)
        a_color = COLORS['green'] if action == 'BUY' else COLORS['red']
        p_color = COLORS['green'] if pnl >= 0 else COLORS['red']
        p_sign  = '+' if pnl >= 0 else ''
        history_html += f"""
        <tr>
            <td style="color:{COLORS['text_dim']}">
                {trade.get('date', '')[:16]}
            </td>
            <td style="color:{a_color};font-weight:700">
                {action}
            </td>
            <td style="color:{COLORS['accent']};font-weight:700">
                {trade.get('symbol', '')}
            </td>
            <td>{trade.get('shares', 0)}</td>
            <td>Rs{trade.get('price', 0):.2f}</td>
            <td style="color:{p_color};font-weight:700">
                {f"{p_sign}Rs{pnl:.2f}"
                if action == 'SELL' else '-'}
            </td>
            <td style="color:{COLORS['text_dim']}">
                {trade.get('reason', '')}
            </td>
        </tr>"""

    if not history_html:
        history_html = f"""
        <tr>
            <td colspan="7"
            style="color:{COLORS['text_dim']};
            text-align:center;padding:20px">
                No trades yet
            </td>
        </tr>"""

    # Allocation chart data
    alloc_labels = ['Cash']
    alloc_values = [round(capital, 2)]
    alloc_colors = [COLORS['blue']]
    pie_colors   = [
        COLORS['green'], COLORS['yellow'],
        COLORS['orange'], COLORS['accent'],
        '#aa88ff', '#ff88aa',
    ]
    for i, (sym, pos) in enumerate(positions.items()):
        val = pos.get('shares', 0) * pos.get(
            'current_price', pos.get('entry_price', 0)
        )
        alloc_labels.append(sym)
        alloc_values.append(round(val, 2))
        alloc_colors.append(pie_colors[i % len(pie_colors)])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
    content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="300">
    <title>BharatEdge Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js">
    </script>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{
            background:{COLORS['bg']};
            color:{COLORS['text']};
            font-family:'Segoe UI',Arial,sans-serif;
            padding:20px;
            min-height:100vh;
        }}
        .header {{
            background:{COLORS['card2']};
            border:1px solid {COLORS['border']};
            border-radius:16px;
            padding:24px 32px;
            margin-bottom:24px;
            display:flex;
            justify-content:space-between;
            align-items:center;
        }}
        .header h1 {{
            color:{COLORS['accent']};
            font-size:26px;
            font-weight:700;
            letter-spacing:1px;
        }}
        .header p {{
            color:{COLORS['text_dim']};
            font-size:13px;
            margin-top:4px;
        }}
        .live-dot {{
            width:10px;height:10px;
            border-radius:50%;
            background:{COLORS['green']};
            display:inline-block;
            margin-right:6px;
            animation:pulse 2s infinite;
        }}
        @keyframes pulse {{
            0%,100% {{ opacity:1; }}
            50% {{ opacity:0.3; }}
        }}
        .cards {{
            display:grid;
            grid-template-columns:repeat(6,1fr);
            gap:16px;
            margin-bottom:24px;
        }}
        .card {{
            background:{COLORS['card']};
            border:1px solid {COLORS['border']};
            border-radius:12px;
            padding:16px;
        }}
        .card-label {{
            color:{COLORS['text_dim']};
            font-size:10px;
            letter-spacing:1px;
            text-transform:uppercase;
            margin-bottom:8px;
        }}
        .card-value {{
            font-size:20px;
            font-weight:700;
            margin-bottom:4px;
        }}
        .card-sub {{
            color:{COLORS['text_dim']};
            font-size:11px;
        }}
        .charts-row {{
            display:grid;
            grid-template-columns:2fr 1fr;
            gap:16px;
            margin-bottom:24px;
        }}
        .panel {{
            background:{COLORS['card']};
            border:1px solid {COLORS['border']};
            border-radius:12px;
            padding:20px;
            margin-bottom:20px;
        }}
        .panel h3 {{
            color:{COLORS['accent']};
            font-size:15px;
            font-weight:600;
            letter-spacing:1px;
            margin-bottom:16px;
            padding-bottom:10px;
            border-bottom:1px solid {COLORS['border']};
        }}
        table {{
            width:100%;
            border-collapse:collapse;
            font-size:13px;
        }}
        th {{
            background:{COLORS['card2']};
            color:{COLORS['text_dim']};
            padding:10px;
            text-align:center;
            font-size:11px;
            letter-spacing:1px;
            text-transform:uppercase;
            border:1px solid {COLORS['border']};
        }}
        td {{
            padding:10px;
            text-align:center;
            border:1px solid {COLORS['border']};
            color:{COLORS['text']};
        }}
        tr:hover td {{
            background:{COLORS['card2']};
        }}
        .footer {{
            text-align:center;
            color:{COLORS['text_dim']};
            font-size:12px;
            padding:20px;
            border-top:1px solid {COLORS['border']};
            margin-top:20px;
        }}
        @media(max-width:768px) {{
            .cards {{
                grid-template-columns:repeat(2,1fr);
            }}
            .charts-row {{
                grid-template-columns:1fr;
            }}
            .header {{
                flex-direction:column;
                gap:10px;
            }}
        }}
    </style>
</head>
<body>

<!-- HEADER -->
<div class="header">
    <div>
        <h1>BharatEdge Trading Dashboard</h1>
        <p>AI-Powered Indian Stock Trading System (NSE)</p>
    </div>
    <div style="text-align:right">
        <div>
            <span class="live-dot"></span>
            <span style="color:{COLORS['green']};
            font-weight:600;font-size:13px">LIVE</span>
        </div>
        <p style="color:{COLORS['text_dim']};
        font-size:11px;margin-top:4px">
            Updated: {now_str}
        </p>
        <p style="color:{COLORS['text_dim']};font-size:11px">
            Last scan: {saved_at}
        </p>
        <p style="color:{COLORS['text_dim']};font-size:11px">
            Auto-refresh: 5 min
        </p>
    </div>
</div>

<!-- SUMMARY CARDS -->
<div class="cards">
    <div class="card"
    style="border-top:3px solid {COLORS['accent']}">
        <div class="card-label">Total Value</div>
        <div class="card-value"
        style="color:{COLORS['accent']}">
            Rs{total_value:,.2f}
        </div>
        <div class="card-sub">
            Started: Rs{starting:,.2f}
        </div>
    </div>
    <div class="card"
    style="border-top:3px solid {COLORS['blue']}">
        <div class="card-label">Cash Available</div>
        <div class="card-value"
        style="color:{COLORS['blue']}">
            Rs{capital:,.2f}
        </div>
        <div class="card-sub">
            {capital/total_value*100:.1f}% of portfolio
        </div>
    </div>
    <div class="card"
    style="border-top:3px solid {pnl_color}">
        <div class="card-label">Total P&L</div>
        <div class="card-value"
        style="color:{pnl_color}">
            {pnl_sign}Rs{total_pnl:,.2f}
        </div>
        <div class="card-sub">
            {pnl_sign}{total_pct:.2f}% overall
        </div>
    </div>
    <div class="card"
    style="border-top:3px solid {pnl_color}">
        <div class="card-label">Realized P&L</div>
        <div class="card-value"
        style="color:{pnl_color}">
            {'+' if realized_pnl >= 0 else ''}Rs{realized_pnl:,.2f}
        </div>
        <div class="card-sub">
            From {total_closed} closed trades
        </div>
    </div>
    <div class="card"
    style="border-top:3px solid {COLORS['yellow']}">
        <div class="card-label">Open Positions</div>
        <div class="card-value"
        style="color:{COLORS['yellow']}">
            {len(positions)}
        </div>
        <div class="card-sub">Max 5 allowed</div>
    </div>
    <div class="card"
    style="border-top:3px solid {wr_color}">
        <div class="card-label">Win Rate</div>
        <div class="card-value"
        style="color:{wr_color}">
            {win_rate:.0f}%
        </div>
        <div class="card-sub">{wins}W / {losses}L</div>
    </div>
</div>

<!-- CHARTS ROW -->
<div class="charts-row">
    <div class="panel">
        <h3>Portfolio Performance (INR)</h3>
        <canvas id="portfolio-chart" height="120"></canvas>
    </div>
    <div class="panel">
        <h3>Portfolio Allocation</h3>
        <canvas id="alloc-chart" height="120"></canvas>
    </div>
</div>

<!-- OPEN POSITIONS -->
<div class="panel">
    <h3>Open Positions</h3>
    <div style="overflow-x:auto">
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Shares</th>
                    <th>Entry Price</th>
                    <th>Current Price</th>
                    <th>Cost</th>
                    <th>P&L</th>
                    <th>P&L %</th>
                    <th>Entry Date</th>
                    <th>Reason</th>
                </tr>
            </thead>
            <tbody>{positions_html}</tbody>
        </table>
    </div>
</div>

<!-- TRADE HISTORY -->
<div class="panel">
    <h3>Trade History (Last 30)</h3>
    <div style="overflow-x:auto">
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Action</th>
                    <th>Symbol</th>
                    <th>Shares</th>
                    <th>Price</th>
                    <th>P&L</th>
                    <th>Reason</th>
                </tr>
            </thead>
            <tbody>{history_html}</tbody>
        </table>
    </div>
</div>

<!-- FOOTER -->
<div class="footer">
    <p>
        BharatEdge V2 | ML Ensemble Models |
        NSE Indian Stocks | Sector Rotation |
        Cloud Automated | GitHub Actions FREE
    </p>
</div>

<!-- CHARTS JS -->
<script>
const pCtx = document.getElementById(
    'portfolio-chart').getContext('2d');
const pData = {chart_values};
const pLabels = {chart_labels};
const pColor = pData[pData.length-1] >= pData[0]
    ? '{COLORS['green']}' : '{COLORS['red']}';

new Chart(pCtx, {{
    type: 'line',
    data: {{
        labels: pLabels,
        datasets: [{{
            data: pData,
            borderColor: pColor,
            backgroundColor: pColor + '15',
            borderWidth: 2,
            pointRadius: 4,
            fill: true,
            tension: 0.3,
        }}]
    }},
    options: {{
        responsive: true,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
            y: {{
                grid : {{ color: '{COLORS['border']}' }},
                ticks: {{
                    color: '{COLORS['text_dim']}',
                    callback: v => 'Rs' + v.toLocaleString()
                }},
            }},
            x: {{
                grid : {{ color: '{COLORS['border']}' }},
                ticks: {{
                    color: '{COLORS['text_dim']}'
                }},
            }},
        }},
    }},
}});

const aCtx = document.getElementById(
    'alloc-chart').getContext('2d');
new Chart(aCtx, {{
    type: 'doughnut',
    data: {{
        labels: {alloc_labels},
        datasets: [{{
            data: {alloc_values},
            backgroundColor: {alloc_colors},
            borderColor: '{COLORS['bg']}',
            borderWidth: 2,
        }}]
    }},
    options: {{
        responsive: true,
        plugins: {{
            legend: {{
                position: 'right',
                labels: {{
                    color: '{COLORS['text']}',
                    font: {{ size: 11 }},
                }}
            }}
        }},
    }},
}});
</script>

</body>
</html>"""

    with open(DASHBOARD_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"   Dashboard generated: {DASHBOARD_FILE}")
    print(f"   Total value: Rs{total_value:,.2f}")
    print(f"   Total P&L: {pnl_sign}Rs{total_pnl:,.2f}")
    print(f"   Open positions: {len(positions)}")
    print(f"   Win rate: {win_rate:.1f}%")
    return True


if __name__ == '__main__':
    print("\nGenerating BharatEdge Dashboard...")
    generate_dashboard()
    print("Done!")