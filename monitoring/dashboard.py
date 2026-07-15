# monitoring/dashboard.py
# BHARAT EDGE - Live Plotly Dash Dashboard
# Mirrors AlphaEdge dashboard style

import json
import os
from datetime import datetime, timezone, timedelta

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dash import Dash, dcc, html, Input, Output, dash_table
import dash_bootstrap_components as dbc

# ── Constants ────────────────────────────────────────────────
TRADES_FILE    = 'logs/bharat_trades.json'
STARTING_CAP   = 100_000.0
REFRESH_MS     = 30_000   # 30 seconds

# ── Dark theme colours ────────────────────────────────────────
BG      = '#0a0e1a'
CARD    = '#111827'
CARD2   = '#1a2235'
BORDER  = '#1e2d45'
TEXT    = '#e2e8f0'
DIM     = '#94a3b8'
GREEN   = '#00ff88'
RED     = '#ff4444'
YELLOW  = '#ffd700'
BLUE    = '#3b82f6'
ORANGE  = '#f97316'
ACCENT  = '#00d4ff'
PURPLE  = '#a855f7'

CARD_STYLE = {
    'background': CARD,
    'border': f'1px solid {BORDER}',
    'borderRadius': '12px',
    'padding': '16px',
}

TABLE_STYLE = {
    'backgroundColor': CARD,
    'color': TEXT,
    'border': f'1px solid {BORDER}',
    'fontFamily': 'Segoe UI, Arial, sans-serif',
    'fontSize': '13px',
}


# ── Helpers ──────────────────────────────────────────────────

def _ist_now():
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

def _is_market_open():
    ist = _ist_now()
    if ist.weekday() >= 5:
        return False
    t = ist.hour * 60 + ist.minute
    return 555 <= t <= 930   # 9:15 – 15:30 IST

def load_portfolio():
    if not os.path.exists(TRADES_FILE):
        return {
            'capital': STARTING_CAP,
            'starting_capital': STARTING_CAP,
            'positions': {},
            'trade_history': [],
            'saved_at': None,
        }
    try:
        with open(TRADES_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {
            'capital': STARTING_CAP,
            'starting_capital': STARTING_CAP,
            'positions': {},
            'trade_history': [],
            'saved_at': None,
        }

def fetch_live_prices(symbols):
    """Fetch latest prices via yfinance. Returns {sym: price}."""
    prices = {}
    if not symbols:
        return prices
    try:
        import yfinance as yf
        tickers = yf.Tickers(' '.join(symbols))
        for sym in symbols:
            try:
                info = tickers.tickers[sym].fast_info
                p = getattr(info, 'last_price', None)
                if p and p > 0:
                    prices[sym] = float(p)
            except Exception:
                pass
    except Exception as e:
        print(f'[dashboard] price fetch error: {e}')
    return prices

def build_equity_curve(history, starting_cap):
    """Build equity curve from trade history."""
    curve = [starting_cap]
    dates = ['Start']
    running = starting_cap
    for t in history:
        if t.get('action') == 'SELL':
            running += t.get('pnl', 0)
            curve.append(running)
            dates.append(t.get('date', '')[:10])
    return dates, curve


# ── Layout helpers ───────────────────────────────────────────

def _stat_card(label, value, sub='', color=ACCENT, border_color=None):
    return html.Div([
        html.Div(label, style={'color': DIM, 'fontSize': '10px',
                               'letterSpacing': '1px',
                               'textTransform': 'uppercase',
                               'marginBottom': '8px'}),
        html.Div(value, style={'color': color, 'fontSize': '22px',
                               'fontWeight': '700'}),
        html.Div(sub,   style={'color': DIM, 'fontSize': '11px',
                               'marginTop': '4px'}),
    ], style={**CARD_STYLE,
              'borderTop': f'3px solid {border_color or color}'})


def create_app():
    app = Dash(
        __name__,
        external_stylesheets=[dbc.themes.CYBORG],
        title='BharatEdge Dashboard',
        update_title=None,
    )

    app.layout = html.Div(style={
        'backgroundColor': BG,
        'minHeight': '100vh',
        'padding': '20px',
        'fontFamily': 'Segoe UI, Arial, sans-serif',
        'color': TEXT,
    }, children=[

        # ── Auto-refresh interval ─────────────────────────────
        dcc.Interval(id='refresh', interval=REFRESH_MS, n_intervals=0),

        # ── Header ───────────────────────────────────────────
        html.Div(style={
            'background': CARD2,
            'border': f'1px solid {BORDER}',
            'borderRadius': '16px',
            'padding': '20px 32px',
            'marginBottom': '24px',
            'display': 'flex',
            'justifyContent': 'space-between',
            'alignItems': 'center',
        }, children=[
            html.Div([
                html.H1('BharatEdge Trading Dashboard',
                        style={'color': ACCENT, 'fontSize': '24px',
                               'fontWeight': '700', 'letterSpacing': '1px',
                               'margin': '0'}),
                html.P('AI-Powered NSE Stock Trading System',
                       style={'color': DIM, 'fontSize': '13px',
                              'margin': '4px 0 0'}),
            ]),
            html.Div([
                html.Div(id='market-status', style={'marginBottom': '6px'}),
                html.Div(id='last-updated',
                         style={'color': DIM, 'fontSize': '11px'}),
            ], style={'textAlign': 'right'}),
        ]),

        # ── Stat cards ────────────────────────────────────────
        html.Div(id='stat-cards', style={
            'display': 'grid',
            'gridTemplateColumns': 'repeat(6, 1fr)',
            'gap': '16px',
            'marginBottom': '24px',
        }),

        # ── Charts row ────────────────────────────────────────
        html.Div(style={
            'display': 'grid',
            'gridTemplateColumns': '2fr 1fr',
            'gap': '16px',
            'marginBottom': '24px',
        }, children=[
            html.Div([
                html.H3('Portfolio Performance (INR)',
                        style={'color': ACCENT, 'fontSize': '14px',
                               'marginBottom': '12px'}),
                dcc.Graph(id='equity-chart',
                          config={'displayModeBar': False}),
            ], style=CARD_STYLE),

            html.Div([
                html.H3('Allocation',
                        style={'color': ACCENT, 'fontSize': '14px',
                               'marginBottom': '12px'}),
                dcc.Graph(id='alloc-chart',
                          config={'displayModeBar': False}),
            ], style=CARD_STYLE),
        ]),

        # ── Open Positions ────────────────────────────────────
        html.Div([
            html.H3('Open Positions',
                    style={'color': ACCENT, 'fontSize': '14px',
                           'marginBottom': '12px',
                           'paddingBottom': '10px',
                           'borderBottom': f'1px solid {BORDER}'}),
            html.Div(id='positions-table'),
        ], style={**CARD_STYLE, 'marginBottom': '20px'}),

        # ── Trade History ─────────────────────────────────────
        html.Div([
            html.H3('Trade History (Last 40)',
                    style={'color': ACCENT, 'fontSize': '14px',
                           'marginBottom': '12px',
                           'paddingBottom': '10px',
                           'borderBottom': f'1px solid {BORDER}'}),
            html.Div(id='history-table'),
        ], style={**CARD_STYLE, 'marginBottom': '20px'}),

        # ── Footer ────────────────────────────────────────────
        html.Div(
            'BharatEdge V2 | ML Ensemble | NSE India | '
            'Paper Trading | Auto-refresh 30s',
            style={'textAlign': 'center', 'color': DIM,
                   'fontSize': '12px', 'padding': '20px',
                   'borderTop': f'1px solid {BORDER}'}
        ),
    ])

    # ── Callbacks ────────────────────────────────────────────

    @app.callback(
        Output('market-status', 'children'),
        Output('last-updated',  'children'),
        Output('stat-cards',    'children'),
        Output('equity-chart',  'figure'),
        Output('alloc-chart',   'figure'),
        Output('positions-table', 'children'),
        Output('history-table',   'children'),
        Input('refresh', 'n_intervals'),
    )
    def update_all(_n):
        port     = load_portfolio()
        capital  = port.get('capital', STARTING_CAP)
        starting = port.get('starting_capital', STARTING_CAP)
        positions= port.get('positions', {})
        history  = port.get('trade_history', [])

        # Live prices
        live = fetch_live_prices(list(positions.keys()))
        for sym, pos in positions.items():
            if sym in live:
                pos['current_price'] = live[sym]
            elif 'current_price' not in pos:
                pos['current_price'] = pos['entry_price']

        # Portfolio maths
        pos_value = sum(
            p['shares'] * p.get('current_price', p['entry_price'])
            for p in positions.values()
        )
        total_val = capital + pos_value
        total_pnl = total_val - starting
        total_pct = total_pnl / starting * 100

        sells     = [t for t in history if t.get('action') == 'SELL']
        wins      = sum(1 for t in sells if t.get('pnl', 0) > 0)
        losses    = len(sells) - wins
        win_rate  = wins / len(sells) * 100 if sells else 0
        realized  = sum(t.get('pnl', 0) for t in sells)

        pnl_col   = GREEN if total_pnl >= 0 else RED
        wr_col    = GREEN if win_rate >= 50 else RED

        # ── Market status badge ───────────────────────────────
        mkt_open  = _is_market_open()
        mkt_badge = html.Span([
            html.Span(style={
                'display': 'inline-block',
                'width': '10px', 'height': '10px',
                'borderRadius': '50%',
                'background': GREEN if mkt_open else RED,
                'marginRight': '6px',
                'animation': 'pulse 2s infinite' if mkt_open else 'none',
            }),
            html.Span(
                'NSE OPEN' if mkt_open else 'NSE CLOSED',
                style={'color': GREEN if mkt_open else RED,
                       'fontWeight': '700', 'fontSize': '13px'}
            ),
        ])

        now_ist   = _ist_now().strftime('%Y-%m-%d %H:%M IST')
        updated   = f'Updated: {now_ist} | Auto-refresh: 30s'

        # ── Stat cards ────────────────────────────────────────
        cards = [
            _stat_card('Total Value',
                       f'Rs{total_val:,.2f}',
                       f'Started: Rs{starting:,.0f}',
                       ACCENT),
            _stat_card('Cash',
                       f'Rs{capital:,.2f}',
                       f'{capital/total_val*100:.1f}% of portfolio',
                       BLUE),
            _stat_card('Total P&L',
                       f'{("+" if total_pnl>=0 else "")}Rs{total_pnl:,.2f}',
                       f'{("+" if total_pct>=0 else "")}{total_pct:.2f}%',
                       pnl_col),
            _stat_card('Realized P&L',
                       f'{("+" if realized>=0 else "")}Rs{realized:,.2f}',
                       f'{len(sells)} closed trades',
                       pnl_col),
            _stat_card('Positions',
                       str(len(positions)),
                       'Max 5 allowed',
                       YELLOW, YELLOW),
            _stat_card('Win Rate',
                       f'{win_rate:.0f}%',
                       f'{wins}W / {losses}L',
                       wr_col),
        ]

        # ── Equity curve ──────────────────────────────────────
        dates, curve = build_equity_curve(history, starting)
        curve.append(total_val)
        dates.append(_ist_now().strftime('%H:%M'))
        eq_color = GREEN if curve[-1] >= curve[0] else RED

        eq_fig = go.Figure(go.Scatter(
            x=dates, y=curve,
            mode='lines+markers',
            line=dict(color=eq_color, width=2),
            fill='tozeroy',
            fillcolor=eq_color + '18',
            marker=dict(size=4),
        ))
        eq_fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=0, b=0),
            height=220,
            xaxis=dict(gridcolor=BORDER, color=DIM, showgrid=True),
            yaxis=dict(gridcolor=BORDER, color=DIM, showgrid=True,
                       tickprefix='Rs'),
            showlegend=False,
            hovermode='x unified',
        )

        # ── Allocation donut ──────────────────────────────────
        alloc_labels = ['Cash'] + list(positions.keys())
        alloc_values = [round(capital, 2)] + [
            round(p['shares'] * p.get('current_price', p['entry_price']), 2)
            for p in positions.values()
        ]
        pie_colors = [BLUE, GREEN, YELLOW, ORANGE, ACCENT, PURPLE, RED]

        al_fig = go.Figure(go.Pie(
            labels=alloc_labels,
            values=alloc_values,
            hole=0.5,
            marker=dict(colors=pie_colors[:len(alloc_labels)],
                        line=dict(color=BG, width=2)),
        ))
        al_fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=0, b=0),
            height=220,
            legend=dict(font=dict(color=TEXT, size=11),
                        bgcolor='rgba(0,0,0,0)'),
            showlegend=True,
        )

        # ── Positions table ───────────────────────────────────
        if positions:
            rows = []
            for sym, pos in positions.items():
                entry   = pos['entry_price']
                current = pos.get('current_price', entry)
                shares  = pos['shares']
                pnl     = (current - entry) * shares
                pct     = (current - entry) / entry * 100 if entry > 0 else 0
                pc      = GREEN if pnl >= 0 else RED
                rows.append({
                    'Symbol'      : sym,
                    'Shares'      : shares,
                    'Entry (Rs)'  : f'{entry:.2f}',
                    'Current (Rs)': f'{current:.2f}',
                    'Cost (Rs)'   : f'{pos.get("cost",0):.2f}',
                    'P&L (Rs)'    : f'{("+" if pnl>=0 else "")}{pnl:.2f}',
                    'P&L %'       : f'{("+" if pct>=0 else "")}{pct:.2f}%',
                    'Entry Date'  : pos.get('entry_date','')[:10],
                    'Reason'      : pos.get('reason',''),
                })
            pos_table = dash_table.DataTable(
                data=rows,
                columns=[{'name': c, 'id': c} for c in rows[0]],
                style_table={'overflowX': 'auto'},
                style_cell={
                    'backgroundColor': CARD,
                    'color': TEXT,
                    'border': f'1px solid {BORDER}',
                    'textAlign': 'center',
                    'padding': '10px',
                    'fontFamily': 'Segoe UI, Arial',
                    'fontSize': '13px',
                },
                style_header={
                    'backgroundColor': CARD2,
                    'color': DIM,
                    'fontWeight': '600',
                    'letterSpacing': '1px',
                    'textTransform': 'uppercase',
                    'fontSize': '11px',
                },
                style_data_conditional=[
                    {'if': {'filter_query': '{P&L (Rs)} contains "+"'},
                     'color': GREEN},
                    {'if': {'filter_query': '{P&L (Rs)} contains "-"'},
                     'color': RED},
                    {'if': {'row_index': 'odd'},
                     'backgroundColor': CARD2},
                ],
                page_size=10,
            )
        else:
            pos_table = html.P('No open positions',
                               style={'color': DIM, 'textAlign': 'center',
                                      'padding': '20px'})

        # ── Trade history table ───────────────────────────────
        hist_rows = []
        for t in reversed(history[-40:]):
            action = t.get('action','')
            pnl    = t.get('pnl', 0)
            hist_rows.append({
                'Date'      : t.get('date','')[:16],
                'Action'    : action,
                'Symbol'    : t.get('symbol',''),
                'Shares'    : t.get('shares', 0),
                'Price (Rs)': f'{t.get("price",0):.2f}',
                'P&L (Rs)'  : (f'{("+" if pnl>=0 else "")}{pnl:.2f}'
                               if action == 'SELL' else '-'),
                'Reason'    : t.get('reason',''),
            })

        hist_table = dash_table.DataTable(
            data=hist_rows,
            columns=[{'name': c, 'id': c} for c in hist_rows[0]] if hist_rows else [],
            style_table={'overflowX': 'auto'},
            style_cell={
                'backgroundColor': CARD,
                'color': TEXT,
                'border': f'1px solid {BORDER}',
                'textAlign': 'center',
                'padding': '10px',
                'fontFamily': 'Segoe UI, Arial',
                'fontSize': '13px',
            },
            style_header={
                'backgroundColor': CARD2,
                'color': DIM,
                'fontWeight': '600',
                'letterSpacing': '1px',
                'textTransform': 'uppercase',
                'fontSize': '11px',
            },
            style_data_conditional=[
                {'if': {'filter_query': '{Action} = "BUY"'},
                 'color': GREEN, 'fontWeight': '700'},
                {'if': {'filter_query': '{Action} = "SELL"'},
                 'color': RED, 'fontWeight': '700'},
                {'if': {'filter_query': '{P&L (Rs)} contains "+"'},
                 'color': GREEN},
                {'if': {'filter_query': '{P&L (Rs)} contains "-"'},
                 'color': RED},
                {'if': {'row_index': 'odd'},
                 'backgroundColor': CARD2},
            ],
            page_size=15,
            sort_action='native',
        )

        return (mkt_badge, updated, cards,
                eq_fig, al_fig, pos_table, hist_table)

    return app
