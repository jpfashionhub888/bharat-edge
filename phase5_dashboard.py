# phase5_dashboard.py
# BHARAT EDGE - Live Trading Dashboard
# UPGRADED: Live market context

import warnings
warnings.filterwarnings('ignore')
import os
import sys

os.environ['LOKY_MAX_CPU_COUNT'] = '1'
os.environ['PYTHONWARNINGS']     = 'ignore'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import pandas as pd
import numpy as np
from datetime import datetime
import yfinance as yf

import dash
from dash import dcc, html, dash_table, Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from phase3_universe import (
    STOCK_UNIVERSE,
    get_all_stocks,
    get_sector_for_stock,
)
from phase3_sector import run_sector_rotation
from phase3_scanner import run_full_scan
from phase2_models import load_all_models

print("✅ phase5_dashboard.py loaded")

# ============================================================
# SECTION 1: APP SETUP
# ============================================================

app = dash.Dash(
    __name__,
    title                       = "Bharat Edge",
    update_title                = None,
    suppress_callback_exceptions= True,
)

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

CARD_STYLE = {
    'backgroundColor': COLORS['card'],
    'border'         : f"1px solid {COLORS['border']}",
    'borderRadius'   : '12px',
    'padding'        : '20px',
    'marginBottom'   : '16px',
}

HEADER_STYLE = {
    'backgroundColor': COLORS['card2'],
    'border'         : f"1px solid {COLORS['border']}",
    'borderRadius'   : '8px',
    'padding'        : '8px 16px',
    'color'          : COLORS['text_dim'],
    'fontSize'       : '12px',
    'marginBottom'   : '8px',
    'letterSpacing'  : '1px',
}

METRIC_STYLE = {
    'textAlign'      : 'center',
    'padding'        : '16px',
    'borderRadius'   : '10px',
    'backgroundColor': COLORS['card2'],
    'border'         : f"1px solid {COLORS['border']}",
}

# ============================================================
# SECTION 2: LIVE MARKET CONTEXT
# ============================================================

print("\n  Loading live market context...")
try:
    from phase6_market_data import get_live_market_context
    MARKET, MARKET_SNAPSHOT = get_live_market_context()
    print(f"  ✅ VIX   : {MARKET['vix_value']:.2f}")
    print(f"  ✅ SGX   : {MARKET['sgx_gap']:+.2f}%")
    print(f"  ✅ FII   : {MARKET['fii_net']:+,.0f}")
except Exception as e:
    print(f"  ⚠️ Live context failed: {e}")
    MARKET = dict(
        vix_value      = 17.21,
        vix_change     = -4.9,
        fii_net        = 500,
        dii_net        = 300,
        sgx_gap        = 0.65,
        news_sentiment = 0.3,
        news_volume    = 35,
    )
    MARKET_SNAPSHOT = {}


# ============================================================
# SECTION 3: DATA LOADERS
# ============================================================

def load_ensemble():
    try:
        return load_all_models()
    except:
        return {}


def fetch_nifty_chart(period="3mo"):
    try:
        ticker = yf.Ticker("^NSEI")
        df     = ticker.history(period=period)
        df.columns = [c.lower() for c in df.columns]
        df.index   = df.index.tz_localize(None)
        return df
    except:
        return pd.DataFrame()


def get_nifty_stats():
    try:
        ticker = yf.Ticker("^NSEI")
        hist   = ticker.history(period="2d")
        if len(hist) >= 2:
            prev  = float(hist['Close'].iloc[-2])
            curr  = float(hist['Close'].iloc[-1])
            chg   = curr - prev
            chg_p = chg / prev * 100
        else:
            curr = chg = chg_p = 0
        return {
            'price' : round(curr, 2),
            'change': round(chg, 2),
            'pct'   : round(chg_p, 2),
        }
    except:
        return {'price': 0, 'change': 0, 'pct': 0}


# ============================================================
# SECTION 4: CHART BUILDERS
# ============================================================

def build_nifty_chart(df):
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No data",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(color=COLORS['text_dim'], size=14)
        )
        fig.update_layout(
            paper_bgcolor=COLORS['card'],
            plot_bgcolor =COLORS['card'],
            height=380,
        )
        return fig

    df = df.copy()
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes    = True,
        vertical_spacing= 0.03,
        row_heights     = [0.75, 0.25],
    )

    fig.add_trace(go.Candlestick(
        x     = df.index,
        open  = df['open'],
        high  = df['high'],
        low   = df['low'],
        close = df['close'],
        name  = 'Nifty 50',
        increasing_line_color = COLORS['green'],
        decreasing_line_color = COLORS['red'],
        increasing_fillcolor  = COLORS['green'],
        decreasing_fillcolor  = COLORS['red'],
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x    = df.index,
        y    = df['ema20'],
        name = 'EMA 20',
        line = dict(color=COLORS['yellow'], width=1.5),
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x    = df.index,
        y    = df['ema50'],
        name = 'EMA 50',
        line = dict(color=COLORS['blue'], width=1.5),
    ), row=1, col=1)

    bar_colors = [
        COLORS['green'] if c >= o else COLORS['red']
        for c, o in zip(df['close'], df['open'])
    ]
    fig.add_trace(go.Bar(
        x            = df.index,
        y            = df['volume'],
        name         = 'Volume',
        marker_color = bar_colors,
        opacity      = 0.7,
    ), row=2, col=1)

    fig.update_layout(
        paper_bgcolor           = COLORS['card'],
        plot_bgcolor            = COLORS['card'],
        font                    = dict(color=COLORS['text'], size=11),
        legend                  = dict(
            bgcolor    = COLORS['card2'],
            bordercolor= COLORS['border'],
            font       = dict(size=10),
        ),
        margin                  = dict(l=10, r=10, t=10, b=10),
        xaxis_rangeslider_visible=False,
        height                  = 380,
    )
    fig.update_xaxes(gridcolor=COLORS['border'])
    fig.update_yaxes(gridcolor=COLORS['border'])
    return fig


def build_vix_gauge(vix_value):
    if vix_value < 15:
        color = COLORS['green']
        label = "LOW RISK"
    elif vix_value < 20:
        color = COLORS['yellow']
        label = "CAUTION"
    elif vix_value < 25:
        color = COLORS['orange']
        label = "HIGH RISK"
    else:
        color = COLORS['red']
        label = "EXTREME"

    fig = go.Figure(go.Indicator(
        mode  = "gauge+number+delta",
        value = vix_value,
        title = dict(
            text = f"India VIX  {label}",
            font = dict(color=COLORS['text'], size=13),
        ),
        delta = dict(
            reference  = 20,
            increasing = dict(color=COLORS['red']),
            decreasing = dict(color=COLORS['green']),
        ),
        gauge = dict(
            axis = dict(
                range    = [0, 40],
                tickcolor= COLORS['text_dim'],
                tickfont = dict(color=COLORS['text_dim']),
            ),
            bar         = dict(color=color),
            bgcolor     = COLORS['card2'],
            bordercolor = COLORS['border'],
            steps       = [
                dict(range=[0,  15], color='#0d2b1a'),
                dict(range=[15, 20], color='#2b2b0d'),
                dict(range=[20, 25], color='#2b1a0d'),
                dict(range=[25, 40], color='#2b0d0d'),
            ],
            threshold   = dict(
                line  = dict(color=COLORS['red'], width=2),
                value = 25,
            ),
        ),
        number = dict(font=dict(color=color, size=28)),
    ))

    fig.update_layout(
        paper_bgcolor = COLORS['card'],
        font          = dict(color=COLORS['text']),
        height        = 220,
        margin        = dict(l=20, r=20, t=40, b=10),
    )
    return fig


def build_sector_chart(rotation_df):
    if rotation_df is None or rotation_df.empty:
        fig = go.Figure()
        fig.update_layout(
            paper_bgcolor=COLORS['card'],
            plot_bgcolor =COLORS['card'],
            height       = 300,
        )
        return fig

    colors = []
    for s in rotation_df['status']:
        if s == 'OVERWEIGHT':
            colors.append(COLORS['green'])
        elif s == 'NEUTRAL':
            colors.append(COLORS['yellow'])
        else:
            colors.append(COLORS['red'])

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x            = rotation_df['sector'],
        y            = rotation_df['score'],
        marker_color = colors,
        text         = rotation_df['score'].round(1),
        textposition = 'outside',
        textfont     = dict(color=COLORS['text'], size=11),
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Score: %{y:.1f}<br>"
            "1M: %{customdata[0]:+.1f}%<br>"
            "3M: %{customdata[1]:+.1f}%<br>"
            "RS: %{customdata[2]:+.1f}%<br>"
            "<extra></extra>"
        ),
        customdata=rotation_df[
            ['mom_1m','mom_3m','rs_vs_nifty']].values,
    ))

    fig.add_hline(y=75, line_dash="dash",
                  line_color=COLORS['green'],
                  annotation_text="Overweight",
                  annotation_font_color=COLORS['green'])
    fig.add_hline(y=65, line_dash="dash",
                  line_color=COLORS['red'],
                  annotation_text="Underweight",
                  annotation_font_color=COLORS['red'])

    fig.update_layout(
        paper_bgcolor = COLORS['card'],
        plot_bgcolor  = COLORS['card'],
        font          = dict(color=COLORS['text'], size=11),
        margin        = dict(l=10, r=10, t=10, b=10),
        height        = 300,
        showlegend    = False,
        yaxis         = dict(range=[50,100],
                             gridcolor=COLORS['border']),
        xaxis         = dict(gridcolor=COLORS['border']),
    )
    return fig


def build_signal_chart(scan_df):
    if scan_df is None or scan_df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No signals available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(color=COLORS['text_dim'], size=14)
        )
        fig.update_layout(
            paper_bgcolor=COLORS['card'],
            plot_bgcolor =COLORS['card'],
            height       = 300,
        )
        return fig

    top10  = scan_df.head(10).copy()
    colors = []
    for _, row in top10.iterrows():
        st = row.get('sector_status','')
        if st == 'OVERWEIGHT':
            colors.append(COLORS['green'])
        elif st == 'NEUTRAL':
            colors.append(COLORS['blue'])
        else:
            colors.append(COLORS['yellow'])

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y            = top10['symbol'],
        x            = top10['adj_confidence'],
        orientation  = 'h',
        marker_color = colors,
        text         = top10['adj_confidence'].round(1
                       ).astype(str) + '%',
        textposition = 'outside',
        textfont     = dict(color=COLORS['text'], size=11),
    ))

    fig.add_vline(x=75, line_dash="dash",
                  line_color=COLORS['green'])
    fig.add_vline(x=65, line_dash="dash",
                  line_color=COLORS['yellow'])

    fig.update_layout(
        paper_bgcolor = COLORS['card'],
        plot_bgcolor  = COLORS['card'],
        font          = dict(color=COLORS['text'], size=11),
        height        = max(300, len(top10) * 40),
        margin        = dict(l=10, r=60, t=10, b=10),
        xaxis         = dict(range=[60,105],
                             gridcolor=COLORS['border']),
        yaxis         = dict(gridcolor=COLORS['border'],
                             autorange='reversed'),
        showlegend    = False,
    )
    return fig


def build_monthly_chart():
    trade_log = "trade_log_v2.csv"
    try:
        if not os.path.exists(trade_log):
            raise FileNotFoundError

        df = pd.read_csv(trade_log)
        df['exit_date'] = pd.to_datetime(df['exit_date'])
        df['month']     = df['exit_date'].dt.to_period('M')

        monthly          = df.groupby('month')['pnl'].sum(
                           ).reset_index()
        monthly['month'] = monthly['month'].astype(str)
        monthly['color'] = monthly['pnl'].apply(
            lambda x: COLORS['green'] if x >= 0
            else COLORS['red'])

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x            = monthly['month'],
            y            = monthly['pnl'],
            marker_color = monthly['color'],
            text         = monthly['pnl'].apply(
                lambda x: f"Rs {x:+,.0f}"),
            textposition = 'outside',
            textfont     = dict(color=COLORS['text'], size=10),
        ))
        fig.add_hline(y=0, line_color=COLORS['text_dim'],
                      line_width=1)
        fig.update_layout(
            paper_bgcolor = COLORS['card'],
            plot_bgcolor  = COLORS['card'],
            font          = dict(color=COLORS['text'], size=11),
            height        = 250,
            margin        = dict(l=10,r=10,t=10,b=10),
            xaxis         = dict(gridcolor=COLORS['border']),
            yaxis         = dict(gridcolor=COLORS['border']),
            showlegend    = False,
        )
        return fig

    except:
        fig = go.Figure()
        fig.add_annotation(
            text="No trade log. Run phase2_backtest.py first.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(color=COLORS['text_dim'], size=12)
        )
        fig.update_layout(
            paper_bgcolor=COLORS['card'],
            plot_bgcolor =COLORS['card'],
            height       = 250,
        )
        return fig


# ============================================================
# SECTION 5: HELPER COMPONENTS
# ============================================================

def _tab_style():
    return {
        'backgroundColor': COLORS['card'],
        'color'          : COLORS['text_dim'],
        'border'         : f"1px solid {COLORS['border']}",
        'borderRadius'   : '8px 8px 0 0',
        'padding'        : '10px 16px',
        'fontSize'       : '13px',
        'fontWeight'     : '500',
    }


def _tab_selected():
    return {
        'backgroundColor': COLORS['card2'],
        'color'          : COLORS['accent'],
        'border'         : f"2px solid {COLORS['accent']}",
        'borderBottom'   : 'none',
        'borderRadius'   : '8px 8px 0 0',
        'padding'        : '10px 16px',
        'fontSize'       : '13px',
        'fontWeight'     : '700',
    }


def _metric_card(label, value, color):
    return html.Div([
        html.P(label, style={
            'color'        : COLORS['text_dim'],
            'fontSize'     : '11px',
            'margin'       : '0 0 4px 0',
            'letterSpacing': '1px',
        }),
        html.H3(value, style={
            'color'     : color,
            'fontSize'  : '24px',
            'margin'    : '0',
            'fontWeight': '700',
        }),
    ], style={
        **METRIC_STYLE,
        'flex'    : '1',
        'minWidth': '120px',
    })


def _info_row(label, value, color):
    return html.Div([
        html.Span(label, style={
            'color'  : COLORS['text_dim'],
            'fontSize': '12px',
        }),
        html.Span(value, style={
            'color'     : color,
            'fontSize'  : '13px',
            'fontWeight': '600',
        }),
    ], style={
        'display'       : 'flex',
        'justifyContent': 'space-between',
        'padding'       : '6px 0',
        'borderBottom'  : f"1px solid {COLORS['border']}",
    })


def _build_signal_table(scan_df):
    if scan_df is None or scan_df.empty:
        return html.P(
            "No signals today",
            style={'color': COLORS['text_dim'],
                   'textAlign': 'center',
                   'padding': '20px'}
        )

    cols = ['symbol','sector','sector_status',
            'signal','adj_confidence','up_votes','alloc_mult']
    df   = scan_df[[c for c in cols
                    if c in scan_df.columns]].copy()

    if 'adj_confidence' in df.columns:
        df['adj_confidence'] = df['adj_confidence'].apply(
            lambda x: f"{x:.1f}%")
    if 'alloc_mult' in df.columns:
        df['alloc_mult'] = df['alloc_mult'].apply(
            lambda x: f"{x:.1f}x")
    if 'up_votes' in df.columns:
        df['up_votes'] = df['up_votes'].apply(
            lambda x: f"{x}/4")

    df.columns = [c.replace('_',' ').upper()
                  for c in df.columns]

    return dash_table.DataTable(
        data    = df.to_dict('records'),
        columns = [{"name":c,"id":c} for c in df.columns],
        style_table = {
            'overflowX'      : 'auto',
            'backgroundColor': COLORS['card'],
        },
        style_header = {
            'backgroundColor': COLORS['card2'],
            'color'          : COLORS['text_dim'],
            'fontWeight'     : '600',
            'fontSize'       : '11px',
            'border'         : f"1px solid {COLORS['border']}",
            'letterSpacing'  : '1px',
        },
        style_cell = {
            'backgroundColor': COLORS['card'],
            'color'          : COLORS['text'],
            'border'         : f"1px solid {COLORS['border']}",
            'fontSize'       : '12px',
            'padding'        : '8px 12px',
            'textAlign'      : 'center',
        },
        style_data_conditional=[
            {
                'if': {'filter_query':
                       '{SIGNAL} = "STRONG_BUY"'},
                'backgroundColor': '#0d2b1a',
                'color'          : COLORS['green'],
                'fontWeight'     : '700',
            },
            {
                'if': {'filter_query':
                       '{SIGNAL} = "BUY"'},
                'backgroundColor': '#0d1a2b',
                'color'          : COLORS['blue'],
            },
        ],
        page_size   = 10,
        sort_action = 'native',
    )


def _build_sector_table(rotation_df):
    if rotation_df is None or rotation_df.empty:
        return html.P("No sector data",
                      style={'color': COLORS['text_dim']})

    cols = ['sector','score','mom_1w','mom_1m',
            'mom_3m','rs_vs_nifty','trend_score',
            'status','alloc_mult']
    df   = rotation_df[
        [c for c in cols if c in rotation_df.columns]
    ].copy()

    for col in ['mom_1w','mom_1m','mom_3m','rs_vs_nifty']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: f"{x:+.1f}%")
    if 'score' in df.columns:
        df['score'] = df['score'].apply(lambda x: f"{x:.1f}")
    if 'trend_score' in df.columns:
        df['trend_score'] = df['trend_score'].apply(
            lambda x: f"{x:.0f}")
    if 'alloc_mult' in df.columns:
        df['alloc_mult'] = df['alloc_mult'].apply(
            lambda x: f"{x:.1f}x")

    df.columns = [c.replace('_',' ').upper()
                  for c in df.columns]

    return dash_table.DataTable(
        data    = df.to_dict('records'),
        columns = [{"name":c,"id":c} for c in df.columns],
        style_table = {
            'overflowX'      : 'auto',
            'backgroundColor': COLORS['card'],
        },
        style_header = {
            'backgroundColor': COLORS['card2'],
            'color'          : COLORS['text_dim'],
            'fontWeight'     : '600',
            'fontSize'       : '11px',
            'border'         : f"1px solid {COLORS['border']}",
        },
        style_cell = {
            'backgroundColor': COLORS['card'],
            'color'          : COLORS['text'],
            'border'         : f"1px solid {COLORS['border']}",
            'fontSize'       : '12px',
            'padding'        : '10px 14px',
            'textAlign'      : 'center',
        },
        style_data_conditional=[
            {
                'if': {'filter_query':
                       '{STATUS} = "OVERWEIGHT"'},
                'backgroundColor': '#0d2b1a',
                'color'          : COLORS['green'],
                'fontWeight'     : '700',
            },
            {
                'if': {'filter_query':
                       '{STATUS} = "UNDERWEIGHT"'},
                'backgroundColor': '#2b0d0d',
                'color'          : COLORS['red'],
            },
        ],
        sort_action = 'native',
    )


def _build_trade_table():
    trade_log = "trade_log_v2.csv"
    try:
        if not os.path.exists(trade_log):
            return html.P(
                "No trade log. Run phase2_backtest.py first!",
                style={'color': COLORS['text_dim'],
                       'padding': '20px',
                       'textAlign': 'center'}
            )

        df   = pd.read_csv(trade_log)
        df   = df.sort_values('exit_date',
                              ascending=False).head(20)
        cols = ['symbol','entry_date','exit_date',
                'entry_price','exit_price','shares',
                'pnl','pnl_pct','exit_reason','hold_days']
        df   = df[[c for c in cols
                   if c in df.columns]].copy()

        if 'pnl' in df.columns:
            df['pnl'] = df['pnl'].apply(
                lambda x: f"Rs {x:+,.0f}"
                if pd.notna(x) else "N/A")
        if 'pnl_pct' in df.columns:
            df['pnl_pct'] = df['pnl_pct'].apply(
                lambda x: f"{x:+.2f}%"
                if pd.notna(x) else "N/A")
        if 'entry_price' in df.columns:
            df['entry_price'] = df['entry_price'].apply(
                lambda x: f"Rs {x:,.2f}"
                if pd.notna(x) else "N/A")
        if 'exit_price' in df.columns:
            df['exit_price'] = df['exit_price'].apply(
                lambda x: f"Rs {x:,.2f}"
                if pd.notna(x) else "N/A")

        df.columns = [c.replace('_',' ').upper()
                      for c in df.columns]

        return dash_table.DataTable(
            data    = df.to_dict('records'),
            columns = [{"name":c,"id":c}
                       for c in df.columns],
            style_table = {
                'overflowX'      : 'auto',
                'backgroundColor': COLORS['card'],
            },
            style_header = {
                'backgroundColor': COLORS['card2'],
                'color'          : COLORS['text_dim'],
                'fontWeight'     : '600',
                'fontSize'       : '11px',
                'border'         : f"1px solid {COLORS['border']}",
            },
            style_cell = {
                'backgroundColor': COLORS['card'],
                'color'          : COLORS['text'],
                'border'         : f"1px solid {COLORS['border']}",
                'fontSize'       : '11px',
                'padding'        : '8px 10px',
                'textAlign'      : 'center',
            },
            style_data_conditional=[
                {
                    'if': {
                        'filter_query':
                        '{PNL PCT} contains "+"',
                    },
                    'color': COLORS['green'],
                },
                {
                    'if': {
                        'filter_query':
                        '{PNL PCT} contains "-"',
                    },
                    'color': COLORS['red'],
                },
            ],
            page_size   = 10,
            sort_action = 'native',
        )
    except Exception as e:
        return html.P(
            f"Error: {e}",
            style={'color': COLORS['red']}
        )


# ============================================================
# SECTION 6: TAB BUILDERS
# ============================================================

def build_overview_tab():
    nifty_stats = get_nifty_stats()
    nifty_df    = fetch_nifty_chart("3mo")

    price     = nifty_stats['price']
    chg       = nifty_stats['change']
    pct       = nifty_stats['pct']
    chg_color = COLORS['green'] if pct >= 0 else COLORS['red']
    chg_sign  = "+" if pct >= 0 else ""

    vix       = MARKET['vix_value']
    if vix < 15:
        vix_label = "LOW RISK"
        vix_color = COLORS['green']
    elif vix < 20:
        vix_label = "CAUTIOUS"
        vix_color = COLORS['yellow']
    elif vix < 25:
        vix_label = "HIGH RISK"
        vix_color = COLORS['orange']
    else:
        vix_label = "EXTREME"
        vix_color = COLORS['red']

    fii       = MARKET['fii_net']
    fii_color = COLORS['green'] if fii >= 0 else COLORS['red']
    fii_label = "BUYING" if fii >= 0 else "SELLING"

    dii       = MARKET['dii_net']
    dii_color = COLORS['green'] if dii >= 0 else COLORS['red']
    dii_label = "BUYING" if dii >= 0 else "SELLING"

    sgx       = MARKET['sgx_gap']
    sgx_color = COLORS['green'] if sgx >= 0 else COLORS['red']

    # Nifty regime from snapshot
    nifty_regime = ""
    if MARKET_SNAPSHOT:
        nifty_data   = MARKET_SNAPSHOT.get('nifty', {})
        nifty_regime = nifty_data.get('regime', '')

    return html.Div([
        html.Div([
            html.Div([
                html.P("NIFTY 50", style={
                    'color':'#94a3b8','fontSize':'11px',
                    'margin':'0 0 4px 0','letterSpacing':'1px'}),
                html.H2(f"{price:,.2f}", style={
                    'color':COLORS['text'],'fontSize':'28px',
                    'margin':'0','fontWeight':'700'}),
                html.P(
                    f"{chg_sign}{pct:.2f}%  "
                    f"({chg_sign}{chg:,.2f})",
                    style={'color':chg_color,'fontSize':'14px',
                           'margin':'4px 0 0 0',
                           'fontWeight':'600'}),
                html.P(
                    f"Regime: {nifty_regime}" if nifty_regime else "",
                    style={'color':COLORS['text_dim'],
                           'fontSize':'11px',
                           'margin':'2px 0 0 0'}),
            ], style={**METRIC_STYLE,'flex':'1'}),

            html.Div([
                html.P("INDIA VIX", style={
                    'color':'#94a3b8','fontSize':'11px',
                    'margin':'0 0 4px 0','letterSpacing':'1px'}),
                html.H2(f"{vix:.2f}", style={
                    'color':vix_color,'fontSize':'28px',
                    'margin':'0','fontWeight':'700'}),
                html.P(vix_label, style={
                    'color':vix_color,'fontSize':'14px',
                    'margin':'4px 0 0 0','fontWeight':'600'}),
            ], style={**METRIC_STYLE,'flex':'1'}),

            html.Div([
                html.P("FII FLOW", style={
                    'color':'#94a3b8','fontSize':'11px',
                    'margin':'0 0 4px 0','letterSpacing':'1px'}),
                html.H2(f"Rs {fii:+,.0f} Cr", style={
                    'color':fii_color,'fontSize':'22px',
                    'margin':'0','fontWeight':'700'}),
                html.P(fii_label, style={
                    'color':fii_color,'fontSize':'14px',
                    'margin':'4px 0 0 0','fontWeight':'600'}),
            ], style={**METRIC_STYLE,'flex':'1'}),

            html.Div([
                html.P("SGX NIFTY GAP", style={
                    'color':'#94a3b8','fontSize':'11px',
                    'margin':'0 0 4px 0','letterSpacing':'1px'}),
                html.H2(f"{sgx:+.2f}%", style={
                    'color':sgx_color,'fontSize':'28px',
                    'margin':'0','fontWeight':'700'}),
                html.P("PRE-MARKET", style={
                    'color':COLORS['text_dim'],'fontSize':'14px',
                    'margin':'4px 0 0 0'}),
            ], style={**METRIC_STYLE,'flex':'1'}),

            html.Div([
                html.P("DII FLOW", style={
                    'color':'#94a3b8','fontSize':'11px',
                    'margin':'0 0 4px 0','letterSpacing':'1px'}),
                html.H2(f"Rs {dii:+,.0f} Cr", style={
                    'color':dii_color,'fontSize':'22px',
                    'margin':'0','fontWeight':'700'}),
                html.P(dii_label, style={
                    'color':dii_color,'fontSize':'14px',
                    'margin':'4px 0 0 0','fontWeight':'600'}),
            ], style={**METRIC_STYLE,'flex':'1'}),

        ], style={
            'display':'flex','gap':'12px',
            'marginBottom':'16px',
        }),

        html.Div([
            html.Div([
                html.Div("NIFTY 50 — 3 Month Chart",
                         style=HEADER_STYLE),
                dcc.Graph(
                    figure = build_nifty_chart(nifty_df),
                    config = {'displayModeBar': False},
                ),
            ], style={**CARD_STYLE,'flex':'2'}),

            html.Div([
                html.Div("MARKET RISK GAUGE",
                         style=HEADER_STYLE),
                dcc.Graph(
                    figure = build_vix_gauge(vix),
                    config = {'displayModeBar': False},
                ),
                html.Hr(style={
                    'borderColor':COLORS['border'],
                    'margin':'12px 0'}),
                _info_row("VIX Change",
                          f"{MARKET['vix_change']:+.1f}%",
                          COLORS['green']
                          if MARKET['vix_change'] < 0
                          else COLORS['red']),
                _info_row("FII (Today)",
                          f"Rs {fii:+,.0f} Cr",
                          fii_color),
                _info_row("DII (Today)",
                          f"Rs {dii:+,.0f} Cr",
                          dii_color),
                _info_row("SGX Gap",
                          f"{sgx:+.2f}%",
                          sgx_color),
                _info_row("Nifty Regime",
                          nifty_regime,
                          COLORS['green']
                          if 'BULL' in nifty_regime
                          else COLORS['red']),
            ], style={**CARD_STYLE,'flex':'1'}),

        ], style={'display':'flex','gap':'16px'}),
    ])


def build_scanner_tab(ensemble):
    if not ensemble:
        return html.Div([
            html.P(
                "Models not loaded. "
                "Run phase2_models.py first!",
                style={'color':COLORS['red'],
                       'textAlign':'center',
                       'padding':'40px'}
            )
        ])

    try:
        scan_df = run_full_scan(
            ensemble=ensemble,
            verbose=False,
            **MARKET,
        )
    except Exception as e:
        scan_df = pd.DataFrame()
        print(f"Scan error: {e}")

    if scan_df is None:
        scan_df = pd.DataFrame()

    total_sigs  = len(scan_df)
    strong_buys = len(scan_df[
        scan_df['signal']=='STRONG_BUY']
    ) if not scan_df.empty else 0
    avg_conf    = (f"{scan_df['adj_confidence'].mean():.1f}%"
                   if not scan_df.empty else "N/A")
    ow_count    = len(scan_df[
        scan_df['sector_status']=='OVERWEIGHT']
    ) if not scan_df.empty else 0

    return html.Div([
        html.Div([
            _metric_card("Total Signals",
                         str(total_sigs), COLORS['accent']),
            _metric_card("Strong Buy",
                         str(strong_buys), COLORS['green']),
            _metric_card("Avg Confidence",
                         avg_conf, COLORS['blue']),
            _metric_card("Overweight",
                         str(ow_count), COLORS['green']),
            _metric_card("Scanned", "30",
                         COLORS['text_dim']),
            _metric_card("Universe", "54",
                         COLORS['text_dim']),
        ], style={
            'display':'flex','gap':'12px',
            'marginBottom':'16px','flexWrap':'wrap',
        }),

        html.Div([
            html.Div([
                html.Div("SIGNAL CONFIDENCE RANKING",
                         style=HEADER_STYLE),
                dcc.Graph(
                    figure = build_signal_chart(scan_df),
                    config = {'displayModeBar': False},
                ),
            ], style={**CARD_STYLE,'flex':'1'}),

            html.Div([
                html.Div("SIGNAL DETAILS TABLE",
                         style=HEADER_STYLE),
                _build_signal_table(scan_df),
            ], style={**CARD_STYLE,'flex':'1.5'}),

        ], style={'display':'flex','gap':'16px'}),
    ])


def build_sector_tab():
    rotation_df = run_sector_rotation(
        vix_value = MARKET['vix_value'],
        fii_net   = MARKET['fii_net'],
        verbose   = False,
    )

    return html.Div([
        html.Div([
            html.Div("SECTOR ROTATION SCORES (LIVE)",
                     style=HEADER_STYLE),
            dcc.Graph(
                figure = build_sector_chart(rotation_df),
                config = {'displayModeBar': False},
            ),
        ], style=CARD_STYLE),

        html.Div([
            html.Div("SECTOR DETAILS TABLE",
                     style=HEADER_STYLE),
            _build_sector_table(rotation_df),
        ], style=CARD_STYLE),

        html.Div([
            html.Div([
                html.Span(
                    "GREEN=OVERWEIGHT(1.5x)  |  "
                    "YELLOW=NEUTRAL(1.0x)  |  "
                    "RED=UNDERWEIGHT(0.3x)",
                    style={'color':COLORS['text_dim'],
                           'fontSize':'12px'}),
            ]),
        ], style={**CARD_STYLE,'padding':'12px 20px'}),
    ])


def build_backtest_tab():
    trade_log = "trade_log_v2.csv"

    if os.path.exists(trade_log):
        try:
            df            = pd.read_csv(trade_log)
            total_trades  = len(df)
            winning       = df[df['pnl'] > 0]
            losing        = df[df['pnl'] <= 0]
            win_rate      = len(winning)/total_trades*100
            total_pnl     = df['pnl'].sum()
            avg_win       = (winning['pnl'].mean()
                             if len(winning) > 0 else 0)
            avg_loss      = (losing['pnl'].mean()
                             if len(losing) > 0 else 0)
        except:
            total_trades = win_rate = total_pnl = 0
            avg_win = avg_loss = 0
    else:
        total_trades = win_rate = total_pnl = 0
        avg_win = avg_loss = 0

    pnl_color = (COLORS['green']
                 if total_pnl >= 0 else COLORS['red'])
    wr_color  = (COLORS['green'] if win_rate > 55
                 else COLORS['yellow'] if win_rate > 45
                 else COLORS['red'])

    return html.Div([
        html.Div([
            _metric_card("Total Trades",
                         str(total_trades), COLORS['accent']),
            _metric_card("Win Rate",
                         f"{win_rate:.1f}%", wr_color),
            _metric_card("Total P&L",
                         f"Rs {total_pnl:+,.0f}", pnl_color),
            _metric_card("Avg Win",
                         f"Rs {avg_win:+,.0f}",
                         COLORS['green']),
            _metric_card("Avg Loss",
                         f"Rs {avg_loss:+,.0f}",
                         COLORS['red']),
            _metric_card("Capital",
                         "Rs 80L", COLORS['text_dim']),
        ], style={
            'display':'flex','gap':'12px',
            'marginBottom':'16px','flexWrap':'wrap',
        }),

        html.Div([
            html.Div("MONTHLY P&L (Backtest v2)",
                     style=HEADER_STYLE),
            dcc.Graph(
                figure = build_monthly_chart(),
                config = {'displayModeBar': False},
            ),
        ], style=CARD_STYLE),

        html.Div([
            html.Div("RECENT TRADES (Last 20)",
                     style=HEADER_STYLE),
            _build_trade_table(),
        ], style=CARD_STYLE),
    ])


def build_report_tab():
    report_path = "daily_report.txt"

    if os.path.exists(report_path):
        try:
            with open(report_path,'r',
                      encoding='utf-8') as f:
                report_text = f.read()
        except:
            report_text = "Error reading report."
    else:
        report_text = (
            "No report found.\n"
            "Run phase3_scanner.py to generate."
        )

    date_str  = datetime.now().strftime('%A, %d %B %Y')
    time_str  = datetime.now().strftime('%H:%M:%S')
    sgx       = MARKET['sgx_gap']
    sgx_str   = f"+{sgx:.2f}%" if sgx >= 0 else f"{sgx:.2f}%"
    sgx_color = COLORS['green'] if sgx >= 0 else COLORS['red']
    vix       = MARKET['vix_value']
    fii       = MARKET['fii_net']
    fii_color = COLORS['green'] if fii >= 0 else COLORS['red']
    fii_str   = f"Rs {fii:+,.0f} Cr"

    return html.Div([
        html.Div([
            html.H3("Daily Market Report", style={
                'color':COLORS['accent'],
                'margin':'0 0 8px 0','fontSize':'18px'}),
            html.P(
                f"Last updated: {date_str}  {time_str}",
                style={'color':COLORS['text_dim'],
                       'fontSize':'12px','margin':'0'}),
        ], style={**CARD_STYLE,'marginBottom':'16px'}),

        html.Div([
            html.Pre(report_text, style={
                'color'          : COLORS['text'],
                'fontSize'       : '13px',
                'lineHeight'     : '1.8',
                'fontFamily'     : '"Courier New", monospace',
                'whiteSpace'     : 'pre-wrap',
                'margin'         : '0',
                'backgroundColor': 'transparent',
            }),
        ], style=CARD_STYLE),

        html.Div([
            html.Div("TELEGRAM BOT PREVIEW",
                     style=HEADER_STYLE),
            html.Div([
                html.P("BHARAT EDGE REPORT", style={
                    'color':COLORS['accent'],
                    'fontWeight':'700','fontSize':'14px',
                    'margin':'0 0 8px 0'}),
                html.P(date_str, style={
                    'color':COLORS['text_dim'],
                    'fontSize':'12px','margin':'0 0 12px 0'}),
                _info_row("SGX Nifty", sgx_str,  sgx_color),
                _info_row("India VIX",
                          f"{vix:.2f}", COLORS['yellow']),
                _info_row("FII Flow",  fii_str, fii_color),
                html.Hr(style={
                    'borderColor':COLORS['border'],
                    'margin':'12px 0'}),
                html.P(
                    "Run scanner for latest signals",
                    style={'color':COLORS['text_dim'],
                           'fontSize':'12px'}),
            ], style={
                'backgroundColor': COLORS['card2'],
                'borderRadius'   : '12px',
                'padding'        : '16px',
                'maxWidth'       : '400px',
                'border'         : f"1px solid {COLORS['border']}",
            }),
        ], style=CARD_STYLE),
    ])


# ============================================================
# SECTION 7: MAIN LAYOUT
# ============================================================

app.layout = html.Div([

    dcc.Interval(id='interval-clock',
                 interval=1000, n_intervals=0),
    dcc.Interval(id='interval-market',
                 interval=300_000, n_intervals=0),

    # Header
    html.Div([
        html.Div([
            html.H1("BHARAT EDGE", style={
                'color'        : COLORS['accent'],
                'fontSize'     : '28px',
                'fontWeight'   : '800',
                'margin'       : '0',
                'letterSpacing': '3px',
            }),
            html.P(
                "AI-Powered Indian Market Intelligence",
                style={'color':COLORS['text_dim'],
                       'fontSize':'13px',
                       'margin':'2px 0 0 0'}),
        ]),
        html.Div(id='live-clock', style={
            'color'    : COLORS['text_dim'],
            'fontSize' : '13px',
            'textAlign': 'right',
        }),
    ], style={
        'display'        : 'flex',
        'justifyContent' : 'space-between',
        'alignItems'     : 'center',
        'backgroundColor': COLORS['card'],
        'padding'        : '16px 24px',
        'borderBottom'   : f"2px solid {COLORS['accent']}",
        'marginBottom'   : '20px',
    }),

    # Main content
    html.Div([
        dcc.Tabs(
            id    = 'main-tabs',
            value = 'tab-overview',
            style = {'marginBottom':'20px'},
            colors= {
                'border'    : COLORS['border'],
                'primary'   : COLORS['accent'],
                'background': COLORS['card'],
            },
            children=[
                dcc.Tab(label='Market Overview',
                        value='tab-overview',
                        style=_tab_style(),
                        selected_style=_tab_selected()),
                dcc.Tab(label='Signal Scanner',
                        value='tab-scanner',
                        style=_tab_style(),
                        selected_style=_tab_selected()),
                dcc.Tab(label='Sector Rotation',
                        value='tab-sector',
                        style=_tab_style(),
                        selected_style=_tab_selected()),
                dcc.Tab(label='Backtest Results',
                        value='tab-backtest',
                        style=_tab_style(),
                        selected_style=_tab_selected()),
                dcc.Tab(label='Daily Report',
                        value='tab-report',
                        style=_tab_style(),
                        selected_style=_tab_selected()),
            ],
        ),
        html.Div(id='tab-content'),
    ], style={
        'maxWidth': '1400px',
        'margin'  : '0 auto',
        'padding' : '0 20px',
    }),

    # Footer
    html.Div([
        html.P(
            "Bharat Edge AI — Educational purposes only. "
            "Not financial advice.",
            style={'color':COLORS['text_dim'],
                   'fontSize':'11px',
                   'textAlign':'center',
                   'margin':'0'}),
    ], style={
        'padding'  : '16px',
        'marginTop': '40px',
        'borderTop': f"1px solid {COLORS['border']}",
    }),

], style={
    'backgroundColor': COLORS['bg'],
    'minHeight'      : '100vh',
    'fontFamily'     : '"Inter","Segoe UI",sans-serif',
    'color'          : COLORS['text'],
})


# ============================================================
# SECTION 8: CALLBACKS
# ============================================================

@app.callback(
    Output('live-clock', 'children'),
    Input('interval-clock', 'n_intervals'),
)
def update_clock(n):
    now = datetime.now()
    return [
        html.Div(
            now.strftime('%A, %d %B %Y'),
            style={'fontWeight':'600',
                   'color':COLORS['text']}
        ),
        html.Div(
            now.strftime('%H:%M:%S IST'),
            style={'color'     : COLORS['accent'],
                   'fontSize'  : '16px',
                   'fontWeight': '700'}
        ),
    ]


@app.callback(
    Output('tab-content', 'children'),
    Input('main-tabs', 'value'),
    Input('interval-market', 'n_intervals'),
)
def render_tab(tab, n):
    ensemble = load_ensemble()
    if tab == 'tab-overview':
        return build_overview_tab()
    elif tab == 'tab-scanner':
        return build_scanner_tab(ensemble)
    elif tab == 'tab-sector':
        return build_sector_tab()
    elif tab == 'tab-backtest':
        return build_backtest_tab()
    elif tab == 'tab-report':
        return build_report_tab()
    else:
        return build_overview_tab()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*55)
    print("  BHARAT EDGE - LIVE DASHBOARD")
    print("="*55)
    print(f"\n  Open browser:")
    print(f"  http://127.0.0.1:8050")
    print(f"\n  Press Ctrl+C to stop")
    print(f"{'='*55}\n")

    app.run(
        debug        = False,
        host         = '0.0.0.0',
        port         = 8050,
        use_reloader = False,
    )