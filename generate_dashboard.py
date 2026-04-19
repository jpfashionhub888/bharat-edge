# generate_dashboard.py
# BHARAT EDGE - GitHub Pages Dashboard Generator
# Upgraded with Chart.js charts matching phase5_dashboard.py

import os
import json
import pandas as pd
from datetime import datetime

HISTORY_FILE   = "performance_history.csv"
RESULTS_FILE   = "latest_results.csv"
DASHBOARD_DIR  = "docs"
DASHBOARD_FILE = f"{DASHBOARD_DIR}/index.html"

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


def signal_color(signal):
    return {
        'STRONG_BUY' : '#00ff88',
        'BUY'        : '#3b82f6',
        'WEAK_BUY'   : '#ffd700',
        'STRONG_SELL': '#ff4444',
        'SELL'       : '#ff4444',
        'WEAK_SELL'  : '#f97316',
    }.get(signal, '#94a3b8')


def signal_emoji(signal):
    return {
        'STRONG_BUY' : '🟢🟢',
        'BUY'        : '🟢',
        'WEAK_BUY'   : '🔵',
        'STRONG_SELL': '🔴🔴',
        'SELL'       : '🔴',
        'WEAK_SELL'  : '🟠',
    }.get(signal, '⚪')


def sector_color(status):
    return {
        'OVERWEIGHT' : '#00ff88',
        'NEUTRAL'    : '#ffd700',
        'UNDERWEIGHT': '#ff4444',
    }.get(status, '#94a3b8')


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
    try:
        from dotenv import load_dotenv
        load_dotenv()
        from phase6_market_data import get_live_market_context
        market, snapshot = get_live_market_context()
        return market, snapshot
    except:
        return {
            'vix_value'     : 17.21,
            'vix_change'    : -4.9,
            'fii_net'       : -300,
            'dii_net'       : 300,
            'sgx_gap'       : 0.65,
            'news_sentiment': -0.1,
            'news_volume'   : 35,
        }, {}


def load_nifty_data():
    """Load Nifty historical data for chart."""
    try:
        import yfinance as yf
        ticker = yf.Ticker("^NSEI")
        df     = ticker.history(period="3mo")
        df.columns = [c.lower() for c in df.columns]

        # Fix timezone issue
        if df.index.tz is not None:
            df.index = df.index.tz_convert('Asia/Kolkata')
            df.index = df.index.tz_localize(None)

        df = df.tail(60)

        dates  = df.index.strftime('%Y-%m-%d').tolist()
        opens  = df['open'].round(2).tolist()
        highs  = df['high'].round(2).tolist()
        lows   = df['low'].round(2).tolist()
        closes = df['close'].round(2).tolist()
        vols   = df['volume'].tolist()

        ema20  = df['close'].ewm(span=20).mean().round(2).tolist()
        ema50  = df['close'].ewm(span=50).mean().round(2).tolist()

        print(f"  ✅ Nifty data loaded: {len(dates)} candles")

        return {
            'dates' : dates,
            'opens' : opens,
            'highs' : highs,
            'lows'  : lows,
            'closes': closes,
            'vols'  : vols,
            'ema20' : ema20,
            'ema50' : ema50,
        }
    except Exception as e:
        print(f"  ⚠️ Nifty data failed: {e}")
        return {}


def load_sector_data(market):
    """Load sector rotation data."""
    try:
        from phase3_sector import run_sector_rotation
        rotation = run_sector_rotation(
            vix_value = market.get('vix_value', 17),
            fii_net   = market.get('fii_net', 0),
            verbose   = False,
        )
        if rotation is not None and not rotation.empty:
            return rotation
        return pd.DataFrame()
    except Exception as e:
        print(f"  ⚠️ Sector data failed: {e}")
        return pd.DataFrame()


def metric_card(label, value, color, subtitle=""):
    sub = f'<div style="color:{COLORS["text_dim"]};font-size:11px;margin-top:4px;">{subtitle}</div>' if subtitle else ""
    return f"""
    <div class="metric-card"
         onmouseover="this.style.transform='translateY(-3px)';this.style.borderColor='{color}'"
         onmouseout="this.style.transform='translateY(0)';this.style.borderColor='{COLORS['border']}'">
        <div style="font-size:1.8rem;font-weight:700;color:{color};">{value}</div>
        <div style="font-size:0.72rem;color:{COLORS['text_dim']};margin-top:6px;
                    text-transform:uppercase;letter-spacing:1px;">{label}</div>
        {sub}
    </div>"""


def info_row(label, value, color):
    return f"""
    <div style="display:flex;justify-content:space-between;
                padding:8px 0;border-bottom:1px solid {COLORS['border']};">
        <span style="color:{COLORS['text_dim']};font-size:12px;">{label}</span>
        <span style="color:{color};font-size:13px;font-weight:600;">{value}</span>
    </div>"""


def build_signal_rows(results_df):
    if results_df is None or results_df.empty:
        return f"""<tr><td colspan="6" style="text-align:center;
            color:{COLORS['text_dim']};padding:30px;">
            No signals today. Run the daily scan first.</td></tr>"""

    rows = ""
    for _, row in results_df.iterrows():
        signal  = row.get('signal', 'N/A')
        conf    = float(row.get('adj_confidence', 0))
        color   = signal_color(signal)
        emoji   = signal_emoji(signal)
        sector  = row.get('sector', 'N/A')
        status  = row.get('sector_status', 'N/A')
        votes   = row.get('up_votes', 0)
        sec_col = sector_color(status)
        symbol  = row.get('symbol', 'N/A')
        bar_w   = min(conf, 100)

        rows += f"""
        <tr>
            <td><b style="color:{COLORS['accent']}">{symbol}</b></td>
            <td style="color:{color};font-weight:700;">{emoji} {signal}</td>
            <td>
                <div style="display:flex;align-items:center;gap:8px;">
                    <div style="background:{COLORS['border']};border-radius:4px;
                                height:8px;width:100px;display:inline-block;overflow:hidden;">
                        <div style="background:{color};width:{bar_w:.0f}%;
                                    height:100%;border-radius:4px;"></div>
                    </div>
                    <span style="color:{color};font-weight:600;">{conf:.1f}%</span>
                </div>
            </td>
            <td style="color:{COLORS['text']};">{int(votes)}/4</td>
            <td style="color:{COLORS['text_dim']};">{sector}</td>
            <td style="color:{sec_col};font-weight:600;">{status}</td>
        </tr>"""
    return rows


def build_history_rows(history_df):
    if history_df is None or history_df.empty:
        return f"""<tr><td colspan="6" style="text-align:center;
            color:{COLORS['text_dim']};padding:30px;">
            No history yet. Check back tomorrow!</td></tr>"""

    rows = ""
    for _, row in history_df.tail(20).iloc[::-1].iterrows():
        signal  = row.get('signal', 'N/A')
        color   = signal_color(signal)
        correct = row.get('correct', 'PENDING')
        pnl     = float(row.get('pnl_pct', 0.0))
        conf    = float(row.get('confidence', 0.0))

        res_color = (
            COLORS['green']   if correct == 'YES'  else
            COLORS['red']     if correct == 'NO'   else
            COLORS['text_dim']
        )
        res_emoji = (
            '✅' if correct == 'YES'  else
            '❌' if correct == 'NO'   else
            '⏳'
        )
        pnl_color = COLORS['green'] if pnl >= 0 else COLORS['red']

        rows += f"""
        <tr>
            <td style="color:{COLORS['text_dim']};">{row.get('date','N/A')}</td>
            <td><b style="color:{COLORS['accent']};">{row.get('symbol','N/A')}</b></td>
            <td style="color:{color};font-weight:700;">{signal}</td>
            <td style="color:{COLORS['yellow']};">{conf:.1f}%</td>
            <td style="color:{res_color};font-weight:700;">{res_emoji} {correct}</td>
            <td style="color:{pnl_color};font-weight:600;">{pnl:+.2f}%</td>
        </tr>"""
    return rows


def build_sector_rows(sector_df):
    if sector_df is None or sector_df.empty:
        return f"""<tr><td colspan="6" style="text-align:center;
            color:{COLORS['text_dim']};padding:30px;">
            No sector data available.</td></tr>"""

    rows = ""
    for _, row in sector_df.iterrows():
        status  = row.get('status', 'NEUTRAL')
        color   = sector_color(status)
        score   = float(row.get('score', 0))
        mom_1m  = float(row.get('mom_1m', 0))
        mom_3m  = float(row.get('mom_3m', 0))
        rs      = float(row.get('rs_vs_nifty', 0))
        alloc   = float(row.get('alloc_mult', 1.0))

        mom_1m_color = COLORS['green'] if mom_1m >= 0 else COLORS['red']
        mom_3m_color = COLORS['green'] if mom_3m >= 0 else COLORS['red']
        rs_color     = COLORS['green'] if rs >= 0 else COLORS['red']

        rows += f"""
        <tr>
            <td><b style="color:{COLORS['accent']};">{row.get('sector','N/A')}</b></td>
            <td style="color:{COLORS['yellow']};font-weight:700;">{score:.1f}</td>
            <td style="color:{mom_1m_color};font-weight:600;">{mom_1m:+.1f}%</td>
            <td style="color:{mom_3m_color};font-weight:600;">{mom_3m:+.1f}%</td>
            <td style="color:{rs_color};font-weight:600;">{rs:+.1f}%</td>
            <td style="color:{color};font-weight:700;">{status} ({alloc:.1f}x)</td>
        </tr>"""
    return rows


def generate_dashboard():
    print("\n" + "="*55)
    print("  BHARAT EDGE - DASHBOARD GENERATOR")
    print(f"  {datetime.now().strftime('%A, %d %B %Y %H:%M')}")
    print("="*55)

    os.makedirs(DASHBOARD_DIR, exist_ok=True)

    # Load all data
    results_df = load_results()
    history_df = load_history()
    market, _  = load_market()
    nifty_data = load_nifty_data()
    sector_df  = load_sector_data(market)

    # Market values
    vix     = market.get('vix_value', 17.21)
    fii     = market.get('fii_net', 0)
    dii     = market.get('dii_net', 0)
    sgx     = market.get('sgx_gap', 0)
    vix_chg = market.get('vix_change', 0)

    fii_color = COLORS['green'] if fii >= 0 else COLORS['red']
    dii_color = COLORS['green'] if dii >= 0 else COLORS['red']
    sgx_color = COLORS['green'] if sgx >= 0 else COLORS['red']
    vix_color = (
        COLORS['green']  if vix < 15 else
        COLORS['yellow'] if vix < 20 else
        COLORS['orange'] if vix < 25 else
        COLORS['red']
    )
    vix_label = (
        "LOW RISK"  if vix < 15 else
        "CAUTIOUS"  if vix < 20 else
        "HIGH RISK" if vix < 25 else
        "EXTREME"
    )
    fii_label = "BUYING"  if fii >= 0 else "SELLING"
    dii_label = "BUYING"  if dii >= 0 else "SELLING"
    sgx_str   = f"+{sgx:.2f}%" if sgx >= 0 else f"{sgx:.2f}%"

    # Signal stats
    total_signals  = len(results_df)
    strong_signals = 0
    avg_conf       = 0.0
    if not results_df.empty and 'adj_confidence' in results_df.columns:
        strong_signals = len(results_df[results_df['adj_confidence'] >= 65])
        avg_conf       = results_df['adj_confidence'].mean()

    # History stats
    wins     = losses = pending = 0
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

    # Build table rows
    signal_rows  = build_signal_rows(results_df)
    history_rows = build_history_rows(history_df)
    sector_rows  = build_sector_rows(sector_df)

    # Chart.js data
    nifty_json  = json.dumps(nifty_data)

    # Sector chart data
    if not sector_df.empty:
        sec_labels = json.dumps(
            sector_df['sector'].tolist())
        sec_scores = json.dumps(
            sector_df['score'].round(1).tolist())
        sec_colors = json.dumps([
            sector_color(s) for s in sector_df['status']
        ])
    else:
        sec_labels = json.dumps([])
        sec_scores = json.dumps([])
        sec_colors = json.dumps([])

    # Signal chart data
    if not results_df.empty and 'adj_confidence' in results_df.columns:
        top10      = results_df.head(10)
        sig_labels = json.dumps(top10['symbol'].tolist())
        sig_confs  = json.dumps(
            top10['adj_confidence'].round(1).tolist())
        sig_colors = json.dumps([
            signal_color(s) for s in top10['signal']
        ])
    else:
        sig_labels = json.dumps([])
        sig_confs  = json.dumps([])
        sig_colors = json.dumps([])

    now      = datetime.now()
    date_str = now.strftime('%A, %d %B %Y')
    time_str = now.strftime('%H:%M IST')
    vix_pct  = min((vix / 40) * 100, 100)

    # ============================================================
    # HTML
    # ============================================================
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <meta http-equiv="refresh" content="300">
    <title>Bharat Edge — AI Trading Dashboard</title>

    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <!-- Lightweight Charts for Candlestick -->
    <script src="https://cdn.jsdelivr.net/npm/chartjs-chart-financial@0.1.1/dist/chartjs-chart-financial.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/luxon@3.4.4/build/global/luxon.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-luxon@1.3.1/dist/chartjs-adapter-luxon.umd.min.js"></script>

    <style>
        * {{ margin:0;padding:0;box-sizing:border-box; }}
        body {{
            font-family:'Inter','Segoe UI',sans-serif;
            background:{COLORS['bg']};
            color:{COLORS['text']};
            min-height:100vh;
        }}

        /* HEADER */
        .header {{
            background:{COLORS['card']};
            border-bottom:2px solid {COLORS['accent']};
            padding:16px 24px;
            display:flex;
            justify-content:space-between;
            align-items:center;
            position:sticky;top:0;z-index:100;
        }}
        .header h1 {{
            color:{COLORS['accent']};
            font-size:26px;font-weight:800;
            letter-spacing:3px;margin:0;
        }}
        .live-badge {{
            display:inline-block;background:#d50000;
            color:white;padding:2px 8px;
            border-radius:12px;font-size:11px;
            font-weight:700;animation:pulse 2s infinite;
            margin-left:8px;
        }}
        @keyframes pulse {{
            0%,100%{{opacity:1}} 50%{{opacity:0.4}}
        }}

        /* TABS */
        .tabs {{
            display:flex;gap:4px;
            padding:16px 24px 0;
            max-width:1400px;margin:0 auto;
            border-bottom:1px solid {COLORS['border']};
            flex-wrap:wrap;
        }}
        .tab {{
            background:{COLORS['card']};
            color:{COLORS['text_dim']};
            border:1px solid {COLORS['border']};
            border-bottom:none;
            border-radius:8px 8px 0 0;
            padding:10px 16px;font-size:13px;
            font-weight:500;cursor:pointer;
            transition:all 0.2s;
            text-decoration:none;
        }}
        .tab:hover {{ color:{COLORS['text']}; }}
        .tab.active {{
            background:{COLORS['card2']};
            color:{COLORS['accent']};
            border:2px solid {COLORS['accent']};
            border-bottom:2px solid {COLORS['card2']};
            font-weight:700;
        }}

        /* CONTENT */
        .content {{
            max-width:1400px;
            margin:0 auto;
            padding:20px 24px;
        }}

        /* CARDS */
        .card {{
            background:{COLORS['card']};
            border:1px solid {COLORS['border']};
            border-radius:12px;
            padding:20px;margin-bottom:16px;
        }}
        .card-header {{
            background:{COLORS['card2']};
            border:1px solid {COLORS['border']};
            border-radius:8px;padding:8px 16px;
            color:{COLORS['text_dim']};font-size:11px;
            margin-bottom:14px;letter-spacing:1px;
            text-transform:uppercase;font-weight:600;
        }}

        /* METRICS */
        .metrics-row {{
            display:flex;gap:12px;
            flex-wrap:wrap;margin-bottom:16px;
        }}
        .metric-card {{
            background:{COLORS['card2']};
            border:1px solid {COLORS['border']};
            border-radius:10px;padding:18px;
            text-align:center;flex:1;min-width:130px;
            transition:all 0.2s;cursor:default;
        }}

        /* GRIDS */
        .grid-2-1 {{
            display:grid;
            grid-template-columns:2fr 1fr;
            gap:16px;margin-bottom:16px;
        }}
        .grid-2 {{
            display:grid;
            grid-template-columns:1fr 1fr;
            gap:16px;margin-bottom:16px;
        }}

        /* TABLES */
        .table-wrap {{ overflow-x:auto; }}
        table {{ width:100%;border-collapse:collapse; }}
        th {{
            background:{COLORS['card2']};
            color:{COLORS['text_dim']};
            padding:12px 14px;text-align:left;
            font-size:11px;text-transform:uppercase;
            letter-spacing:1px;
            border:1px solid {COLORS['border']};
        }}
        td {{
            padding:11px 14px;
            border:1px solid {COLORS['border']};
            font-size:13px;
        }}
        tr:hover td {{ background:{COLORS['card2']}; }}

        /* TAB PANELS */
        .tab-panel {{ display:none; }}
        .tab-panel.active {{ display:block; }}

        /* VIX GAUGE */
        .vix-gauge {{
            text-align:center;padding:10px 0;
        }}
        .vix-value {{
            font-size:3.5rem;font-weight:800;
        }}
        .vix-label {{
            font-size:1rem;font-weight:700;
            letter-spacing:2px;margin:4px 0;
        }}
        .gauge-bar {{
            background:linear-gradient(90deg,
                {COLORS['green']},{COLORS['yellow']},
                {COLORS['orange']},{COLORS['red']});
            border-radius:8px;height:14px;
            margin:14px 0 6px;overflow:hidden;
            position:relative;
        }}
        .gauge-needle {{
            position:absolute;top:-3px;
            width:4px;height:20px;
            background:white;border-radius:2px;
            transform:translateX(-50%);
        }}

        /* CHART CONTAINERS */
        .chart-container {{
            position:relative;
            width:100%;
        }}

        /* FOOTER */
        .footer {{
            text-align:center;padding:20px;
            margin-top:40px;
            border-top:1px solid {COLORS['border']};
            color:{COLORS['text_dim']};font-size:11px;
        }}

        /* RESPONSIVE */
        @media(max-width:768px) {{
            .grid-2-1,.grid-2 {{
                grid-template-columns:1fr;
            }}
            .header h1 {{ font-size:20px; }}
        }}
    </style>
</head>
<body>

<!-- HEADER -->
<div class="header">
    <div>
        <h1>🇮🇳 BHARAT EDGE
            <span class="live-badge">● LIVE</span>
        </h1>
        <div style="color:{COLORS['text_dim']};font-size:13px;margin-top:2px;">
            AI-Powered Indian Market Intelligence
        </div>
    </div>
    <div style="text-align:right;">
        <div style="color:{COLORS['text']};font-weight:600;font-size:13px;">
            {date_str}
        </div>
        <div id="live-clock" style="color:{COLORS['accent']};
             font-size:20px;font-weight:700;">{time_str}</div>
        <div style="color:{COLORS['text_dim']};font-size:10px;margin-top:2px;">
            Auto-refreshes every 5 min
        </div>
    </div>
</div>

<!-- TABS -->
<div class="tabs">
    <a class="tab active" onclick="showTab('overview',this)" href="#">
        📊 Market Overview</a>
    <a class="tab" onclick="showTab('scanner',this)" href="#">
        📡 Signal Scanner</a>
    <a class="tab" onclick="showTab('sector',this)" href="#">
        🔄 Sector Rotation</a>
    <a class="tab" onclick="showTab('history',this)" href="#">
        📈 Performance</a>
</div>

<div class="content">

<!-- ==================== OVERVIEW TAB ==================== -->
<div id="tab-overview" class="tab-panel active">

    <!-- Top Metrics -->
    <div class="metrics-row">
        {metric_card("NIFTY 50", "24,353", COLORS['text'],
                     "Live Index")}
        {metric_card("India VIX", f"{vix:.2f}", vix_color,
                     vix_label)}
        {metric_card("FII Flow",
                     f"₹{fii:+,.0f}Cr", fii_color, fii_label)}
        {metric_card("DII Flow",
                     f"₹{dii:+,.0f}Cr", dii_color, dii_label)}
        {metric_card("SGX Gap", sgx_str, sgx_color,
                     "Pre-Market")}
    </div>

    <!-- Nifty Chart + VIX Panel -->
    <div class="grid-2-1">
        <div class="card">
            <div class="card-header">
                📈 NIFTY 50 — 3 Month Candlestick Chart
            </div>
            <div id="nifty-chart"
                 style="width:100%;height:380px;">
            </div>
        </div>
        <div class="card">
            <div class="card-header">⚡ MARKET RISK GAUGE</div>
            <div class="vix-gauge">
                <div class="vix-value"
                     style="color:{vix_color};">{vix:.2f}</div>
                <div class="vix-label"
                     style="color:{vix_color};">{vix_label}</div>
                <div class="gauge-bar">
                    <div class="gauge-needle"
                         style="left:{vix_pct:.1f}%;">
                    </div>
                </div>
                <div style="display:flex;
                            justify-content:space-between;
                            font-size:10px;
                            color:{COLORS['text_dim']};">
                    <span>0 Safe</span>
                    <span>20 Caution</span>
                    <span>40 Danger</span>
                </div>
            </div>
            <hr style="border-color:{COLORS['border']};
                       margin:16px 0;">
            {info_row("VIX", f"{vix:.2f}", vix_color)}
            {info_row("VIX Change",
                      f"{vix_chg:+.1f}%",
                      COLORS['green'] if vix_chg <= 0
                      else COLORS['red'])}
            {info_row("FII Flow",
                      f"₹{fii:+,.0f} Cr", fii_color)}
            {info_row("DII Flow",
                      f"₹{dii:+,.0f} Cr", dii_color)}
            {info_row("SGX Gap", sgx_str, sgx_color)}
            {info_row("Updated", time_str, COLORS['accent'])}
        </div>
    </div>

    <!-- Scan Summary -->
    <div class="card">
        <div class="card-header">🎯 TODAY'S SCAN SUMMARY</div>
        <div class="metrics-row">
            {metric_card("Total Signals",
                         str(total_signals), COLORS['accent'])}
            {metric_card("Strong (≥65%)",
                         str(strong_signals), COLORS['green'])}
            {metric_card("Avg Confidence",
                         f"{avg_conf:.1f}%", COLORS['blue'])}
            {metric_card("Win Rate",
                         f"{win_rate:.1f}%", wr_color)}
            {metric_card("Wins", str(wins), COLORS['green'])}
            {metric_card("Losses", str(losses), COLORS['red'])}
            {metric_card("Pending",
                         str(pending), COLORS['text_dim'])}
        </div>
    </div>

</div>

<!-- ==================== SCANNER TAB ==================== -->
<div id="tab-scanner" class="tab-panel">

    <div class="metrics-row">
        {metric_card("Total Signals",
                     str(total_signals), COLORS['accent'])}
        {metric_card("Strong (≥65%)",
                     str(strong_signals), COLORS['green'])}
        {metric_card("Avg Confidence",
                     f"{avg_conf:.1f}%", COLORS['blue'])}
        {metric_card("Models", "4", COLORS['text_dim'],
                     "XGB+LGB+RF+ET")}
    </div>

    <div class="grid-2">
        <!-- Signal Confidence Chart -->
        <div class="card">
            <div class="card-header">
                📊 SIGNAL CONFIDENCE RANKING
            </div>
            <div class="chart-container" style="height:320px;">
                <canvas id="signal-chart"></canvas>
            </div>
        </div>

        <!-- Signal Table -->
        <div class="card">
            <div class="card-header">
                📋 SIGNAL DETAILS TABLE — {date_str}
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Signal</th>
                            <th>Confidence</th>
                            <th>Votes</th>
                            <th>Sector</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>{signal_rows}</tbody>
                </table>
            </div>
        </div>
    </div>

    <div class="card" style="padding:12px 20px;">
        <span style="color:{COLORS['text_dim']};font-size:12px;">
            🟢🟢 STRONG BUY &nbsp;|&nbsp;
            🟢 BUY &nbsp;|&nbsp;
            🔵 WEAK BUY &nbsp;|&nbsp;
            🔴🔴 STRONG SELL &nbsp;|&nbsp;
            🔴 SELL &nbsp;|&nbsp;
            ⚠️ Not financial advice. DYOR.
        </span>
    </div>

</div>

<!-- ==================== SECTOR TAB ==================== -->
<div id="tab-sector" class="tab-panel">

    <div class="card">
        <div class="card-header">
            🔄 SECTOR ROTATION SCORES (LIVE)
        </div>
        <div class="chart-container" style="height:320px;">
            <canvas id="sector-chart"></canvas>
        </div>
    </div>

    <div class="card">
        <div class="card-header">📋 SECTOR DETAILS TABLE</div>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Sector</th>
                        <th>Score</th>
                        <th>1M Mom</th>
                        <th>3M Mom</th>
                        <th>RS vs Nifty</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>{sector_rows}</tbody>
            </table>
        </div>
    </div>

    <div class="card" style="padding:12px 20px;">
        <span style="color:{COLORS['text_dim']};font-size:12px;">
            🟢 OVERWEIGHT (1.5x) &nbsp;|&nbsp;
            🟡 NEUTRAL (1.0x) &nbsp;|&nbsp;
            🔴 UNDERWEIGHT (0.3x) &nbsp;|&nbsp;
            Score &gt; 75 = Overweight &nbsp;|&nbsp;
            Score &lt; 65 = Underweight
        </span>
    </div>

</div>

<!-- ==================== HISTORY TAB ==================== -->
<div id="tab-history" class="tab-panel">

    <div class="metrics-row">
        {metric_card("Total Tracked",
                     str(wins+losses+pending),
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
            📈 PERFORMANCE HISTORY (Last 20 Signals)
        </div>
        <div class="table-wrap">
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
                <tbody>{history_rows}</tbody>
            </table>
        </div>
    </div>

    <div class="card" style="padding:12px 20px;">
        <span style="color:{COLORS['text_dim']};font-size:12px;">
            ✅ Correct &nbsp;|&nbsp;
            ❌ Wrong &nbsp;|&nbsp;
            ⏳ Pending — Update results manually in
            <b>performance_history.csv</b>
        </span>
    </div>

</div>

</div><!-- end content -->

<!-- FOOTER -->
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

<!-- ==================== SCRIPTS ==================== -->
<script>

// ---- TAB SWITCHING ----
function showTab(name, el) {{
    document.querySelectorAll('.tab-panel').forEach(
        p => p.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(
        t => t.classList.remove('active'));
    document.getElementById('tab-' + name)
            .classList.add('active');
    if (el) el.classList.add('active');
    return false;
}}

// ---- LIVE CLOCK ----
function updateClock() {{
    const now = new Date();
    const h = String(now.getHours()).padStart(2,'0');
    const m = String(now.getMinutes()).padStart(2,'0');
    const s = String(now.getSeconds()).padStart(2,'0');
    const el = document.getElementById('live-clock');
    if (el) el.textContent = h+':'+m+':'+s+' IST';
}}
setInterval(updateClock, 1000);

// ---- NIFTY CANDLESTICK CHART ----
const niftyData = {nifty_json};

function renderNiftyChart() {{
    const container = document.getElementById('nifty-chart');
    if (!container) return;

    if (!niftyData || !niftyData.dates ||
        niftyData.dates.length === 0) {{
        container.innerHTML =
            '<div style="display:flex;align-items:center;' +
            'justify-content:center;height:380px;' +
            'color:#94a3b8;">No chart data available</div>';
        return;
    }}

    try {{
        // Build canvas inside container
        container.innerHTML =
            '<canvas id="nifty-canvas"></canvas>';
        const ctx = document.getElementById(
            'nifty-canvas').getContext('2d');

        // Build OHLC data for candlestick
        const ohlcData = niftyData.dates.map((d, i) => ({{
            x    : new Date(d).getTime(),
            o    : niftyData.opens[i],
            h    : niftyData.highs[i],
            l    : niftyData.lows[i],
            c    : niftyData.closes[i],
        }}));

        // EMA line data
        const ema20Data = niftyData.dates.map((d, i) => ({{
            x: new Date(d).getTime(),
            y: niftyData.ema20[i],
        }}));
        const ema50Data = niftyData.dates.map((d, i) => ({{
            x: new Date(d).getTime(),
            y: niftyData.ema50[i],
        }}));

        new Chart(ctx, {{
            type: 'candlestick',
            data: {{
                datasets: [
                    {{
                        label          : 'NIFTY 50',
                        data           : ohlcData,
                        color          : {{
                            up  : '{COLORS['green']}',
                            down: '{COLORS['red']}',
                            unchanged: '{COLORS['yellow']}',
                        }},
                    }},
                    {{
                        type     : 'line',
                        label    : 'EMA 20',
                        data     : ema20Data,
                        borderColor    : '{COLORS['yellow']}',
                        borderWidth    : 2,
                        pointRadius    : 0,
                        tension        : 0.1,
                    }},
                    {{
                        type     : 'line',
                        label    : 'EMA 50',
                        data     : ema50Data,
                        borderColor    : '{COLORS['blue']}',
                        borderWidth    : 2,
                        pointRadius    : 0,
                        tension        : 0.1,
                    }},
                ],
            }},
            options: {{
                responsive         : true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        display: true,
                        labels : {{
                            color: '{COLORS['text_dim']}',
                        }},
                    }},
                    tooltip: {{ mode: 'index' }},
                }},
                scales: {{
                    x: {{
                        type : 'timeseries',
                        time : {{
                            unit           : 'day',
                            tooltipFormat  : 'dd MMM yyyy',
                            displayFormats : {{
                                day: 'dd MMM',
                            }},
                        }},
                        grid : {{ color: '{COLORS['border']}' }},
                        ticks: {{ color: '{COLORS['text_dim']}',
                                  maxTicksLimit: 10 }},
                    }},
                    y: {{
                        grid : {{ color: '{COLORS['border']}' }},
                        ticks: {{ color: '{COLORS['text_dim']}' }},
                    }},
                }},
            }},
        }});

        console.log('✅ Nifty chart rendered: ' +
                    ohlcData.length + ' candles');

    }} catch(e) {{
        console.error('Chart error:', e);
        container.innerHTML =
            '<div style="display:flex;align-items:center;' +
            'justify-content:center;height:380px;' +
            'color:#ff4444;">Chart error: ' +
            e.message + '</div>';
    }}
}}

window.addEventListener('load', renderNiftyChart);// ---- SIGNAL CONFIDENCE CHART (Chart.js) ----
const sigLabels = {sig_labels};
const sigConfs  = {sig_confs};
const sigColors = {sig_colors};

if (sigLabels.length > 0) {{
    const sigCtx = document.getElementById(
        'signal-chart').getContext('2d');
    new Chart(sigCtx, {{
        type: 'bar',
        data: {{
            labels  : sigLabels,
            datasets: [{{
                label          : 'Confidence %',
                data           : sigConfs,
                backgroundColor: sigColors.map(
                    c => c + '99'),
                borderColor    : sigColors,
                borderWidth    : 2,
                borderRadius   : 6,
            }}],
        }},
        options: {{
            indexAxis   : 'y',
            responsive  : true,
            maintainAspectRatio: false,
            plugins: {{
                legend: {{ display: false }},
                tooltip: {{
                    callbacks: {{
                        label: ctx =>
                            ` ${{ctx.raw.toFixed(1)}}%`
                    }}
                }},
            }},
            scales: {{
                x: {{
                    min        : 45,
                    max        : 100,
                    grid       : {{
                        color: '{COLORS['border']}'
                    }},
                    ticks      : {{
                        color   : '{COLORS['text_dim']}',
                        callback: v => v + '%'
                    }},
                }},
                y: {{
                    grid : {{ color: '{COLORS['border']}' }},
                    ticks: {{ color: '{COLORS['text']}' }},
                }},
            }},
        }},
    }});
}} else {{
    document.getElementById('signal-chart')
        .parentElement.innerHTML =
        '<div style="display:flex;align-items:center;' +
        'justify-content:center;height:320px;' +
        'color:{COLORS["text_dim"]};">' +
        'No signal data available</div>';
}}

// ---- SECTOR ROTATION CHART (Chart.js) ----
const secLabels = {sec_labels};
const secScores = {sec_scores};
const secColors = {sec_colors};

if (secLabels.length > 0) {{
    const secCtx = document.getElementById(
        'sector-chart').getContext('2d');
    new Chart(secCtx, {{
        type: 'bar',
        data: {{
            labels  : secLabels,
            datasets: [{{
                label          : 'Score',
                data           : secScores,
                backgroundColor: secColors.map(
                    c => c + '99'),
                borderColor    : secColors,
                borderWidth    : 2,
                borderRadius   : 6,
            }}],
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{
                legend: {{ display: false }},
                annotation: {{
                    annotations: {{
                        ow: {{
                            type       : 'line',
                            yMin       : 75,
                            yMax       : 75,
                            borderColor: '{COLORS['green']}',
                            borderWidth: 2,
                            borderDash : [6,4],
                            label: {{
                                content   : 'Overweight',
                                display   : true,
                                color     : '{COLORS['green']}',
                                position  : 'end',
                            }},
                        }},
                        uw: {{
                            type       : 'line',
                            yMin       : 65,
                            yMax       : 65,
                            borderColor: '{COLORS['red']}',
                            borderWidth: 2,
                            borderDash : [6,4],
                            label: {{
                                content : 'Underweight',
                                display : true,
                                color   : '{COLORS['red']}',
                                position: 'end',
                            }},
                        }},
                    }},
                }},
            }},
            scales: {{
                y: {{
                    min  : 50,
                    max  : 100,
                    grid : {{ color: '{COLORS['border']}' }},
                    ticks: {{ color: '{COLORS['text_dim']}' }},
                }},
                x: {{
                    grid : {{ color: '{COLORS['border']}' }},
                    ticks: {{ color: '{COLORS['text']}' }},
                }},
            }},
        }},
    }});
}} else {{
    document.getElementById('sector-chart')
        .parentElement.innerHTML =
        '<div style="display:flex;align-items:center;' +
        'justify-content:center;height:320px;' +
        'color:{COLORS["text_dim"]};">' +
        'No sector data available</div>';
}}

</script>
</body>
</html>"""

    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  ✅ Dashboard generated : {DASHBOARD_FILE}")
    print(f"  📊 Signals today       : {total_signals}")
    print(f"  🎯 Strong signals      : {strong_signals}")
    print(f"  🔄 Sectors loaded      : {len(sector_df)}")
    print(f"  🏆 Win rate            : {win_rate:.1f}%")
    print(f"  📈 VIX                 : {vix:.2f} ({vix_label})")
    return True


if __name__ == "__main__":
    generate_dashboard()
    print("\n  ✅ Done!")
    print("  Run: git add docs/ && "
          "git commit -m 'Upgrade dashboard v2' && git push")