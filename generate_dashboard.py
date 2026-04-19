# generate_dashboard.py
# BHARAT EDGE - GitHub Pages Dashboard Generator
# Matches phase5_dashboard.py look and feel exactly

import os
import json
import pandas as pd
from datetime import datetime

HISTORY_FILE   = "performance_history.csv"
RESULTS_FILE   = "latest_results.csv"
DASHBOARD_DIR  = "docs"
DASHBOARD_FILE = f"{DASHBOARD_DIR}/index.html"

# ============================================================
# COLORS — Same as phase5_dashboard.py
# ============================================================
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


# ============================================================
# HELPERS
# ============================================================

def signal_color(signal: str) -> str:
    return {
        'STRONG_BUY' : COLORS['green'],
        'BUY'        : COLORS['blue'],
        'WEAK_BUY'   : COLORS['yellow'],
        'STRONG_SELL': COLORS['red'],
        'SELL'       : COLORS['red'],
        'WEAK_SELL'  : COLORS['orange'],
    }.get(signal, COLORS['text_dim'])


def signal_emoji(signal: str) -> str:
    return {
        'STRONG_BUY' : '🟢🟢',
        'BUY'        : '🟢',
        'WEAK_BUY'   : '🔵',
        'STRONG_SELL': '🔴🔴',
        'SELL'       : '🔴',
        'WEAK_SELL'  : '🟠',
    }.get(signal, '⚪')


def sector_color(status: str) -> str:
    return {
        'OVERWEIGHT' : COLORS['green'],
        'NEUTRAL'    : COLORS['yellow'],
        'UNDERWEIGHT': COLORS['red'],
    }.get(status, COLORS['text_dim'])


# ============================================================
# LOAD DATA
# ============================================================

def load_results():
    if not os.path.exists(RESULTS_FILE):
        return pd.DataFrame()
    try:
        return pd.read_csv(RESULTS_FILE)
    except:
        return pd.DataFrame()


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame()
    try:
        return pd.read_csv(HISTORY_FILE)
    except:
        return pd.DataFrame()


def load_market():
    """Try to load latest market context."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        from phase6_market_data import get_live_market_context
        market, snapshot = get_live_market_context()
        return market
    except:
        return {
            'vix_value'     : 17.21,
            'vix_change'    : -4.9,
            'fii_net'       : -300,
            'dii_net'       : 300,
            'sgx_gap'       : 0.65,
            'news_sentiment': -0.1,
            'news_volume'   : 35,
        }


# ============================================================
# BUILD SIGNAL ROWS
# ============================================================

def build_signal_rows(results_df):
    if results_df is None or results_df.empty:
        return """
        <tr>
            <td colspan="6" style="text-align:center;
                color:#94a3b8;padding:30px;">
                No signals today. Run the daily scan first.
            </td>
        </tr>"""

    rows = ""
    for _, row in results_df.iterrows():
        signal  = row.get('signal', 'N/A')
        conf    = row.get('adj_confidence', 0)
        color   = signal_color(signal)
        emoji   = signal_emoji(signal)
        sector  = row.get('sector', 'N/A')
        status  = row.get('sector_status', 'N/A')
        votes   = row.get('up_votes', 0)
        sec_col = sector_color(status)
        symbol  = row.get('symbol', 'N/A')

        bar_width = min(float(conf), 100)

        rows += f"""
        <tr>
            <td><b style="color:{COLORS['accent']}">
                {symbol}</b></td>
            <td style="color:{color};font-weight:700;">
                {emoji} {signal}</td>
            <td>
                <div style="display:flex;
                            align-items:center;gap:8px;">
                    <div style="background:{COLORS['border']};
                                border-radius:4px;height:8px;
                                width:100px;display:inline-block;">
                        <div style="background:{color};
                                    width:{bar_width:.0f}%;
                                    height:100%;
                                    border-radius:4px;">
                        </div>
                    </div>
                    <span style="color:{color};
                                 font-weight:600;">
                        {conf:.1f}%</span>
                </div>
            </td>
            <td style="color:{COLORS['text']};">
                {int(votes)}/4</td>
            <td style="color:{COLORS['text_dim']};">
                {sector}</td>
            <td style="color:{sec_col};font-weight:600;">
                {status}</td>
        </tr>"""
    return rows


# ============================================================
# BUILD HISTORY ROWS
# ============================================================

def build_history_rows(history_df):
    if history_df is None or history_df.empty:
        return """
        <tr>
            <td colspan="6" style="text-align:center;
                color:#94a3b8;padding:30px;">
                No history yet. Check back tomorrow!
            </td>
        </tr>"""

    rows = ""
    for _, row in history_df.tail(20).iloc[::-1].iterrows():
        signal  = row.get('signal', 'N/A')
        color   = signal_color(signal)
        correct = row.get('correct', 'PENDING')
        pnl     = float(row.get('pnl_pct', 0.0))
        conf    = float(row.get('confidence', 0.0))

        res_color = (
            COLORS['green']  if correct == 'YES'  else
            COLORS['red']    if correct == 'NO'   else
            COLORS['text_dim']
        )
        res_emoji = (
            '✅' if correct == 'YES'  else
            '❌' if correct == 'NO'   else
            '⏳'
        )
        pnl_color = (
            COLORS['green'] if pnl >= 0
            else COLORS['red']
        )

        rows += f"""
        <tr>
            <td style="color:{COLORS['text_dim']};">
                {row.get('date','N/A')}</td>
            <td><b style="color:{COLORS['accent']};">
                {row.get('symbol','N/A')}</b></td>
            <td style="color:{color};font-weight:700;">
                {signal}</td>
            <td style="color:{COLORS['yellow']};">
                {conf:.1f}%</td>
            <td style="color:{res_color};font-weight:700;">
                {res_emoji} {correct}</td>
            <td style="color:{pnl_color};font-weight:600;">
                {pnl:+.2f}%</td>
        </tr>"""
    return rows


# ============================================================
# BUILD METRIC CARD
# ============================================================

def metric_card(label, value, color):
    return f"""
    <div style="background:{COLORS['card2']};
                border:1px solid {COLORS['border']};
                border-radius:10px;padding:20px;
                text-align:center;flex:1;min-width:140px;
                transition:transform 0.2s;"
         onmouseover="this.style.transform='translateY(-3px)'"
         onmouseout="this.style.transform='translateY(0)'">
        <div style="font-size:1.8rem;font-weight:700;
                    color:{color};">{value}</div>
        <div style="font-size:0.75rem;color:{COLORS['text_dim']};
                    margin-top:6px;text-transform:uppercase;
                    letter-spacing:1px;">{label}</div>
    </div>"""


# ============================================================
# BUILD VIX BADGE
# ============================================================

def vix_badge(vix):
    if vix < 15:
        color = COLORS['green']
        label = "LOW RISK"
    elif vix < 20:
        color = COLORS['yellow']
        label = "CAUTIOUS"
    elif vix < 25:
        color = COLORS['orange']
        label = "HIGH RISK"
    else:
        color = COLORS['red']
        label = "EXTREME"

    pct = min((vix / 40) * 100, 100)

    return f"""
    <div style="text-align:center;">
        <div style="font-size:3rem;font-weight:800;
                    color:{color};">{vix:.2f}</div>
        <div style="color:{color};font-weight:700;
                    font-size:1rem;letter-spacing:2px;
                    margin:4px 0;">{label}</div>
        <div style="background:{COLORS['border']};
                    border-radius:8px;height:12px;
                    margin:12px 0;overflow:hidden;">
            <div style="background:linear-gradient(
                            90deg,{COLORS['green']},
                            {COLORS['yellow']},{COLORS['red']});
                        width:{pct:.0f}%;height:100%;
                        border-radius:8px;">
            </div>
        </div>
        <div style="display:flex;justify-content:space-between;
                    font-size:10px;color:{COLORS['text_dim']};">
            <span>0</span>
            <span>LOW</span>
            <span>HIGH</span>
            <span>40</span>
        </div>
    </div>"""


# ============================================================
# INFO ROW
# ============================================================

def info_row(label, value, color):
    return f"""
    <div style="display:flex;justify-content:space-between;
                padding:8px 0;
                border-bottom:1px solid {COLORS['border']};">
        <span style="color:{COLORS['text_dim']};
                     font-size:12px;">{label}</span>
        <span style="color:{color};font-size:13px;
                     font-weight:600;">{value}</span>
    </div>"""


# ============================================================
# MAIN GENERATE FUNCTION
# ============================================================

def generate_dashboard():
    print("\n" + "="*55)
    print("  BHARAT EDGE - DASHBOARD GENERATOR")
    print(f"  {datetime.now().strftime('%A, %d %B %Y %H:%M')}")
    print("="*55)

    os.makedirs(DASHBOARD_DIR, exist_ok=True)

    # Load data
    results_df = load_results()
    history_df = load_history()
    market     = load_market()

    # Market values
    vix = market.get('vix_value', 17.21)
    fii = market.get('fii_net', 0)
    dii = market.get('dii_net', 0)
    sgx = market.get('sgx_gap', 0)
    vix_chg = market.get('vix_change', 0)

    fii_color = COLORS['green'] if fii >= 0 else COLORS['red']
    dii_color = COLORS['green'] if dii >= 0 else COLORS['red']
    sgx_color = COLORS['green'] if sgx >= 0 else COLORS['red']
    vix_chg_color = COLORS['green'] if vix_chg <= 0 else COLORS['red']

    fii_label = "BUYING"  if fii >= 0 else "SELLING"
    dii_label = "BUYING"  if dii >= 0 else "SELLING"
    sgx_str   = f"+{sgx:.2f}%" if sgx >= 0 else f"{sgx:.2f}%"

    # Stats
    total_signals  = len(results_df)
    strong_signals = 0
    avg_conf       = 0.0

    if not results_df.empty and 'adj_confidence' in results_df.columns:
        strong_signals = len(
            results_df[results_df['adj_confidence'] >= 65])
        avg_conf = results_df['adj_confidence'].mean()

    # History stats
    wins    = 0
    losses  = 0
    pending = 0
    win_rate = 0.0

    if not history_df.empty:
        wins    = len(history_df[history_df['correct'] == 'YES'])
        losses  = len(history_df[history_df['correct'] == 'NO'])
        pending = len(history_df[history_df['correct'] == 'PENDING'])
        total   = wins + losses
        win_rate = (wins / total * 100) if total > 0 else 0.0

    wr_color = (
        COLORS['green']  if win_rate >= 60 else
        COLORS['yellow'] if win_rate >= 50 else
        COLORS['red']
    )

    # Build rows
    signal_rows  = build_signal_rows(results_df)
    history_rows = build_history_rows(history_df)

    # Date/time
    now      = datetime.now()
    date_str = now.strftime('%A, %d %B %Y')
    time_str = now.strftime('%H:%M IST')

    # ============================================================
    # HTML
    # ============================================================
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="300">
    <title>Bharat Edge — AI Trading Dashboard</title>
    <style>
        * {{
            margin     : 0;
            padding    : 0;
            box-sizing : border-box;
        }}
        body {{
            font-family: 'Inter','Segoe UI',
                         Tahoma,Geneva,Verdana,sans-serif;
            background : {COLORS['bg']};
            color      : {COLORS['text']};
            min-height : 100vh;
        }}

        /* HEADER */
        .header {{
            background     : {COLORS['card']};
            border-bottom  : 2px solid {COLORS['accent']};
            padding        : 16px 24px;
            display        : flex;
            justify-content: space-between;
            align-items    : center;
            position       : sticky;
            top            : 0;
            z-index        : 100;
        }}
        .header h1 {{
            color         : {COLORS['accent']};
            font-size     : 28px;
            font-weight   : 800;
            letter-spacing: 3px;
            margin        : 0;
        }}
        .header .subtitle {{
            color     : {COLORS['text_dim']};
            font-size : 13px;
            margin-top: 2px;
        }}
        .live-time {{
            text-align: right;
        }}
        .live-time .date {{
            color      : {COLORS['text']};
            font-weight: 600;
            font-size  : 13px;
        }}
        .live-time .time {{
            color      : {COLORS['accent']};
            font-size  : 18px;
            font-weight: 700;
        }}

        /* TABS */
        .tabs {{
            display        : flex;
            gap            : 4px;
            padding        : 16px 24px 0;
            max-width      : 1400px;
            margin         : 0 auto;
            border-bottom  : 1px solid {COLORS['border']};
        }}
        .tab {{
            background   : {COLORS['card']};
            color        : {COLORS['text_dim']};
            border       : 1px solid {COLORS['border']};
            border-bottom: none;
            border-radius: 8px 8px 0 0;
            padding      : 10px 16px;
            font-size    : 13px;
            font-weight  : 500;
            cursor       : pointer;
            transition   : all 0.2s;
            text-decoration: none;
        }}
        .tab:hover {{
            color: {COLORS['text']};
        }}
        .tab.active {{
            background   : {COLORS['card2']};
            color        : {COLORS['accent']};
            border       : 2px solid {COLORS['accent']};
            border-bottom: none;
            font-weight  : 700;
        }}

        /* CONTENT */
        .content {{
            max-width: 1400px;
            margin   : 0 auto;
            padding  : 20px 24px;
        }}

        /* CARDS */
        .card {{
            background   : {COLORS['card']};
            border       : 1px solid {COLORS['border']};
            border-radius: 12px;
            padding      : 20px;
            margin-bottom: 16px;
        }}
        .card-header {{
            background    : {COLORS['card2']};
            border        : 1px solid {COLORS['border']};
            border-radius : 8px;
            padding       : 8px 16px;
            color         : {COLORS['text_dim']};
            font-size     : 12px;
            margin-bottom : 12px;
            letter-spacing: 1px;
            text-transform: uppercase;
        }}

        /* METRICS ROW */
        .metrics-row {{
            display  : flex;
            gap      : 12px;
            flex-wrap: wrap;
            margin-bottom: 16px;
        }}

        /* GRID */
        .grid-2 {{
            display              : grid;
            grid-template-columns: 2fr 1fr;
            gap                  : 16px;
            margin-bottom        : 16px;
        }}
        .grid-equal {{
            display              : grid;
            grid-template-columns: 1fr 1fr;
            gap                  : 16px;
            margin-bottom        : 16px;
        }}

        /* TABLES */
        table {{
            width          : 100%;
            border-collapse: collapse;
        }}
        th {{
            background    : {COLORS['card2']};
            color         : {COLORS['text_dim']};
            padding       : 12px 14px;
            text-align    : left;
            font-size     : 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            border        : 1px solid {COLORS['border']};
        }}
        td {{
            padding      : 12px 14px;
            border-bottom: 1px solid {COLORS['border']};
            font-size    : 13px;
            border       : 1px solid {COLORS['border']};
        }}
        tr:hover td {{
            background: {COLORS['card2']};
        }}

        /* TAB PANELS */
        .tab-panel {{
            display: none;
        }}
        .tab-panel.active {{
            display: block;
        }}

        /* LIVE BADGE */
        .live-badge {{
            display      : inline-block;
            background   : #d50000;
            color        : white;
            padding      : 2px 8px;
            border-radius: 12px;
            font-size    : 11px;
            font-weight  : 700;
            animation    : pulse 2s infinite;
            margin-left  : 8px;
        }}
        @keyframes pulse {{
            0%   {{ opacity: 1; }}
            50%  {{ opacity: 0.4; }}
            100% {{ opacity: 1; }}
        }}

        /* NIFTY BANNER */
        .nifty-banner {{
            background     : {COLORS['card2']};
            border         : 1px solid {COLORS['border']};
            border-radius  : 10px;
            padding        : 20px;
            display        : flex;
            align-items    : center;
            justify-content: space-between;
            margin-bottom  : 16px;
        }}

        /* FOOTER */
        .footer {{
            text-align : center;
            padding    : 20px;
            margin-top : 40px;
            border-top : 1px solid {COLORS['border']};
            color      : {COLORS['text_dim']};
            font-size  : 11px;
        }}

        /* RESPONSIVE */
        @media (max-width: 768px) {{
            .grid-2, .grid-equal {{
                grid-template-columns: 1fr;
            }}
            .header h1 {{
                font-size: 20px;
            }}
        }}
    </style>
</head>
<body>

<!-- ============ HEADER ============ -->
<div class="header">
    <div>
        <h1>🇮🇳 BHARAT EDGE
            <span class="live-badge">● LIVE</span>
        </h1>
        <div class="subtitle">
            AI-Powered Indian Market Intelligence
        </div>
    </div>
    <div class="live-time">
        <div class="date">{date_str}</div>
        <div class="time">{time_str}</div>
        <div style="color:{COLORS['text_dim']};
                    font-size:10px;margin-top:2px;">
            Auto-refreshes every 5 min
        </div>
    </div>
</div>

<!-- ============ TABS ============ -->
<div class="tabs">
    <a class="tab active"
       onclick="showTab('overview')"
       href="#">Market Overview</a>
    <a class="tab"
       onclick="showTab('scanner')"
       href="#">Signal Scanner</a>
    <a class="tab"
       onclick="showTab('history')"
       href="#">Performance History</a>
</div>

<!-- ============ CONTENT ============ -->
<div class="content">

    <!-- ===== OVERVIEW TAB ===== -->
    <div id="tab-overview" class="tab-panel active">

        <!-- Market Metrics -->
        <div class="metrics-row">
            {metric_card("NIFTY 50", "24,353", COLORS['text'])}
            {metric_card("India VIX", f"{vix:.2f}", COLORS['yellow'])}
            {metric_card("FII Flow",
                         f"₹{fii:+,.0f}Cr", fii_color)}
            {metric_card("DII Flow",
                         f"₹{dii:+,.0f}Cr", dii_color)}
            {metric_card("SGX Gap", sgx_str, sgx_color)}
        </div>

        <!-- VIX + Market Info -->
        <div class="grid-2">
            <div class="card">
                <div class="card-header">
                    MARKET RISK INDICATOR — INDIA VIX
                </div>
                {vix_badge(vix)}
            </div>
            <div class="card">
                <div class="card-header">
                    MARKET CONTEXT
                </div>
                {info_row("VIX", f"{vix:.2f}", COLORS['yellow'])}
                {info_row("VIX Change",
                          f"{vix_chg:+.1f}%", vix_chg_color)}
                {info_row("FII Flow",
                          f"₹{fii:+,.0f} Cr ({fii_label})",
                          fii_color)}
                {info_row("DII Flow",
                          f"₹{dii:+,.0f} Cr ({dii_label})",
                          dii_color)}
                {info_row("SGX Nifty Gap", sgx_str, sgx_color)}
                {info_row("Last Updated", time_str,
                          COLORS['accent'])}
            </div>
        </div>

        <!-- Scan Summary -->
        <div class="card">
            <div class="card-header">TODAY'S SCAN SUMMARY</div>
            <div class="metrics-row">
                {metric_card("Total Signals",
                             str(total_signals),
                             COLORS['accent'])}
                {metric_card("Strong Signals",
                             str(strong_signals),
                             COLORS['green'])}
                {metric_card("Avg Confidence",
                             f"{avg_conf:.1f}%",
                             COLORS['blue'])}
                {metric_card("Win Rate",
                             f"{win_rate:.1f}%", wr_color)}
                {metric_card("Total Tracked",
                             str(wins + losses + pending),
                             COLORS['text_dim'])}
                {metric_card("Pending",
                             str(pending),
                             COLORS['text_dim'])}
            </div>
        </div>

    </div>

    <!-- ===== SCANNER TAB ===== -->
    <div id="tab-scanner" class="tab-panel">

        <div class="metrics-row">
            {metric_card("Total Signals",
                         str(total_signals), COLORS['accent'])}
            {metric_card("Strong (≥65%)",
                         str(strong_signals), COLORS['green'])}
            {metric_card("Avg Confidence",
                         f"{avg_conf:.1f}%", COLORS['blue'])}
            {metric_card("Scanned", "54", COLORS['text_dim'])}
        </div>

        <div class="card">
            <div class="card-header">
                SIGNAL SCANNER — TODAY'S RESULTS
                ({date_str})
            </div>
            <div style="overflow-x:auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Signal</th>
                            <th>Confidence</th>
                            <th>Votes</th>
                            <th>Sector</th>
                            <th>Sector Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {signal_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="card" style="padding:12px 20px;">
            <span style="color:{COLORS['text_dim']};
                         font-size:12px;">
                🟢🟢 STRONG BUY &nbsp;|&nbsp;
                🟢 BUY &nbsp;|&nbsp;
                🔵 WEAK BUY &nbsp;|&nbsp;
                🔴🔴 STRONG SELL &nbsp;|&nbsp;
                🔴 SELL &nbsp;|&nbsp;
                ⚠️ Not financial advice. DYOR.
            </span>
        </div>

    </div>

    <!-- ===== HISTORY TAB ===== -->
    <div id="tab-history" class="tab-panel">

        <div class="metrics-row">
            {metric_card("Total Signals",
                         str(wins + losses + pending),
                         COLORS['accent'])}
            {metric_card("Wins", str(wins), COLORS['green'])}
            {metric_card("Losses", str(losses), COLORS['red'])}
            {metric_card("Win Rate",
                         f"{win_rate:.1f}%", wr_color)}
            {metric_card("Pending",
                         str(pending), COLORS['text_dim'])}
        </div>

        <div class="card">
            <div class="card-header">
                PERFORMANCE HISTORY (Last 20 Signals)
            </div>
            <div style="overflow-x:auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Symbol</th>
                            <th>Signal</th>
                            <th>Confidence</th>
                            <th>Result</th>
                            <th>PnL %</th>
                        </tr>
                    </thead>
                    <tbody>
                        {history_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="card" style="padding:12px 20px;">
            <span style="color:{COLORS['text_dim']};
                         font-size:12px;">
                ✅ Correct &nbsp;|&nbsp;
                ❌ Wrong &nbsp;|&nbsp;
                ⏳ Pending (update manually in
                performance_history.csv)
            </span>
        </div>

    </div>

</div>

<!-- ============ FOOTER ============ -->
<div class="footer">
    <p>
        🤖 Bharat Edge AI &nbsp;|&nbsp;
        XGBoost + LightGBM + Random Forest + Extra Trees
        &nbsp;|&nbsp;
        Auto-updated daily by GitHub Actions
    </p>
    <p style="margin-top:6px;">
        ⚠️ Not financial advice.
        For educational purposes only. Always DYOR.
    </p>
</div>

<!-- ============ TAB SCRIPT ============ -->
<script>
    function showTab(name) {{
        // Hide all panels
        document.querySelectorAll('.tab-panel').forEach(p => {{
            p.classList.remove('active');
        }});
        // Deactivate all tabs
        document.querySelectorAll('.tab').forEach(t => {{
            t.classList.remove('active');
        }});
        // Show selected panel
        document.getElementById('tab-' + name)
                .classList.add('active');
        // Activate selected tab
        event.target.classList.add('active');
    }}

    // Live clock update
    function updateClock() {{
        const now  = new Date();
        const opts = {{
            weekday: 'long', day: '2-digit',
            month: 'long', year: 'numeric'
        }};
        const h = String(now.getHours()).padStart(2,'0');
        const m = String(now.getMinutes()).padStart(2,'0');
        const s = String(now.getSeconds()).padStart(2,'0');
        document.querySelector('.live-time .time').textContent
            = h + ':' + m + ':' + s + ' IST';
    }}
    setInterval(updateClock, 1000);
</script>

</body>
</html>"""

    # Write file
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  ✅ Dashboard generated : {DASHBOARD_FILE}")
    print(f"  📊 Signals today       : {total_signals}")
    print(f"  🎯 Strong signals      : {strong_signals}")
    print(f"  🏆 Win rate            : {win_rate:.1f}%")
    print(f"  📈 VIX                 : {vix:.2f}")
    print(f"  💰 FII                 : ₹{fii:+,.0f} Cr")
    return True


if __name__ == "__main__":
    generate_dashboard()
    print("\n  ✅ Done!")
    print("  Run: git add docs/ && "
          "git commit -m 'Upgrade dashboard' && git push")