# monitoring/dashboard.py  -- BharatEdge Live Dash Dashboard
import json, os, traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, dash_table

ROOT        = Path(__file__).resolve().parent.parent
TRADES_FILE = ROOT / 'logs' / 'bharat_trades.json'
STARTING_CAP = 100_000.0
REFRESH_MS   = 30_000

BG=  '#0d1117'; CARD='#161b22'; CARD2='#21262d'; BORDER='#30363d'
TEXT='#e6edf3'; DIM='#8b949e';  GREEN='#3fb950';  RED='#f85149'
YELLOW='#d29922'; BLUE='#58a6ff'; ORANGE='#db6d28'
ACCENT='#58a6ff'; PURPLE='#bc8cff'

def _ist_now():
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

def _is_market_open():
    ist = _ist_now()
    if ist.weekday() >= 5: return False
    t = ist.hour*60 + ist.minute
    return 555 <= t <= 930

def load_portfolio():
    default = {'capital':STARTING_CAP,'starting_capital':STARTING_CAP,
               'positions':{},'trade_history':[],'saved_at':None}
    if not TRADES_FILE.exists(): return default
    try: return json.loads(TRADES_FILE.read_text(encoding='utf-8'))
    except: return default

def fetch_live_prices(symbols):
    prices = {}
    if not symbols: return prices
    try:
        import yfinance as yf
        data = yf.download(' '.join(symbols), period='1d',
                           interval='1m', progress=False, auto_adjust=True)
        if data.empty: return prices
        cl = data['Close']
        if hasattr(cl, 'columns'):
            for s in symbols:
                try: prices[s] = float(cl[s].dropna().iloc[-1])
                except: pass
        else:
            if symbols:
                try: prices[symbols[0]] = float(cl.dropna().iloc[-1])
                except: pass
    except Exception as e:
        print(f'[price] {e}')
    return prices

def _dark(h=240):
    return dict(paper_bgcolor=CARD, plot_bgcolor=CARD,
                margin=dict(l=50,r=20,t=20,b=40), height=h,
                font=dict(color=TEXT,family='Segoe UI,Arial'),
                xaxis=dict(gridcolor=BORDER,color=DIM,showgrid=True,
                           linecolor=BORDER,zeroline=False),
                yaxis=dict(gridcolor=BORDER,color=DIM,showgrid=True,
                           linecolor=BORDER,zeroline=False),
                showlegend=False, hovermode='x unified')

def _empty(msg='No data'):
    fig = go.Figure()
    fig.add_annotation(text=msg,x=0.5,y=0.5,xref='paper',yref='paper',
                       showarrow=False,font=dict(color=DIM,size=14))
    fig.update_layout(paper_bgcolor=CARD,plot_bgcolor=CARD,
                      margin=dict(l=10,r=10,t=10,b=10),height=240,
                      xaxis=dict(visible=False),yaxis=dict(visible=False))
    return fig

def scard(label, val, sub='', color=ACCENT, top=None):
    return html.Div([
        html.Div(label,style={'color':DIM,'fontSize':'10px','letterSpacing':'1px',
                              'textTransform':'uppercase','marginBottom':'8px'}),
        html.Div(val,style={'color':color,'fontSize':'20px','fontWeight':'700',
                            'marginBottom':'4px'}),
        html.Div(sub,style={'color':DIM,'fontSize':'11px'}),
    ], style={'background':CARD,'border':f'1px solid {BORDER}',
              'borderTop':f'3px solid {top or color}',
              'borderRadius':'10px','padding':'16px'})

def dtable(rows, cond=None, page_size=10):
    if not rows:
        return html.P('No data',style={'color':DIM,'padding':'20px'})
    cols=[{'name':c,'id':c} for c in rows[0]]
    base=[{'if':{'row_index':'odd'},'backgroundColor':CARD2}]
    return dash_table.DataTable(
        data=rows, columns=cols, page_size=page_size,
        sort_action='native',
        style_table={'overflowX':'auto'},
        style_cell={'backgroundColor':CARD,'color':TEXT,
                    'border':f'1px solid {BORDER}','textAlign':'center',
                    'padding':'9px 12px','fontFamily':'Segoe UI,Arial',
                    'fontSize':'13px','whiteSpace':'nowrap'},
        style_header={'backgroundColor':CARD2,'color':DIM,
                      'fontWeight':'600','letterSpacing':'0.5px',
                      'textTransform':'uppercase','fontSize':'11px',
                      'border':f'1px solid {BORDER}'},
        style_data_conditional=base+(cond or []),
    )

PANEL = {'background':CARD,'border':f'1px solid {BORDER}',
         'borderRadius':'10px','padding':'16px','marginBottom':'16px'}
HDR3  = {'color':ACCENT,'fontSize':'13px','fontWeight':'600',
         'marginBottom':'12px','paddingBottom':'10px',
         'borderBottom':f'1px solid {BORDER}'}

def create_app():
    app = Dash(__name__, title='BharatEdge Dashboard',
               update_title=None, suppress_callback_exceptions=True)

    app.index_string = (
        '<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>'
        '{%favicon%}{%css%}<style>'
        f'*{{margin:0;padding:0;box-sizing:border-box}}'
        f'body{{background:{BG};color:{TEXT};font-family:Segoe UI,Arial,sans-serif}}'
        '@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}'
        '::-webkit-scrollbar{width:6px;height:6px}'
        f'::-webkit-scrollbar-track{{background:{CARD}}}'
        f'::-webkit-scrollbar-thumb{{background:{BORDER};border-radius:3px}}'
        '</style></head><body>{%app_entry%}'
        '<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>'
    )

    app.layout = html.Div(style={'backgroundColor':BG,'minHeight':'100vh','padding':'20px'},
    children=[
        dcc.Interval(id='iv', interval=REFRESH_MS, n_intervals=0),

        # Header
        html.Div(style={'background':CARD2,'border':f'1px solid {BORDER}',
                        'borderRadius':'12px','padding':'20px 28px',
                        'marginBottom':'20px','display':'flex',
                        'justifyContent':'space-between','alignItems':'center'},
        children=[
            html.Div([
                html.H1('BharatEdge Trading Dashboard',
                        style={'color':ACCENT,'fontSize':'22px','fontWeight':'700',
                               'letterSpacing':'1px'}),
                html.P('AI-Powered NSE Stock Trading  ·  Paper Trading Engine',
                       style={'color':DIM,'fontSize':'12px','marginTop':'4px'}),
            ]),
            html.Div(id='hdr', style={'textAlign':'right'}),
        ]),

        # Stat cards
        html.Div(id='cards',style={'display':'grid',
                                   'gridTemplateColumns':'repeat(6,1fr)',
                                   'gap':'14px','marginBottom':'20px'}),

        # Charts row
        html.Div(style={'display':'grid','gridTemplateColumns':'2fr 1fr',
                        'gap':'14px','marginBottom':'20px'},
        children=[
            html.Div([html.Div('Portfolio Equity Curve',style=HDR3),
                      dcc.Graph(id='eq',config={'displayModeBar':False})],
                     style=PANEL),
            html.Div([html.Div('Portfolio Allocation',style=HDR3),
                      dcc.Graph(id='al',config={'displayModeBar':False})],
                     style=PANEL),
        ]),

        html.Div([html.Div('Open Positions',style=HDR3),
                  html.Div(id='ptbl')], style=PANEL),

        html.Div([html.Div('Trade History (Last 40)',style=HDR3),
                  html.Div(id='htbl')], style=PANEL),

        html.Div('BharatEdge V2  ·  ML Ensemble  ·  NSE India  ·  Auto-refresh 30s',
                 style={'textAlign':'center','color':DIM,'fontSize':'11px',
                        'padding':'16px','borderTop':f'1px solid {BORDER}'}),
    ])

    @app.callback(
        Output('hdr','children'), Output('cards','children'),
        Output('eq','figure'),   Output('al','figure'),
        Output('ptbl','children'), Output('htbl','children'),
        Input('iv','n_intervals'),
    )
    def refresh(_n):
        try:
            port    = load_portfolio()
            capital = float(port.get('capital', STARTING_CAP))
            start   = float(port.get('starting_capital', STARTING_CAP))
            pos     = port.get('positions', {})
            hist    = port.get('trade_history', [])

            live = fetch_live_prices(list(pos.keys()))
            for sym, p in pos.items():
                lp = live.get(sym)
                if lp and lp > 0: p['current_price'] = lp
                elif 'current_price' not in p:
                    p['current_price'] = p.get('entry_price', 0)

            pos_val = sum(p['shares']*p.get('current_price',p.get('entry_price',0))
                          for p in pos.values())
            total   = capital + pos_val
            pnl     = total - start
            pnl_pct = pnl/start*100 if start else 0
            sells   = [t for t in hist if t.get('action')=='SELL']
            wins    = sum(1 for t in sells if t.get('pnl',0)>0)
            losses  = len(sells)-wins
            wr      = wins/len(sells)*100 if sells else 0
            realized= sum(t.get('pnl',0) for t in sells)

            pc = GREEN if pnl>=0 else RED
            wc = GREEN if wr>=50 else RED
            sg = lambda v: '+' if v>=0 else ''

            # Header right
            mkt = _is_market_open()
            ist = _ist_now().strftime('%Y-%m-%d %H:%M IST')
            hdr = html.Div([
                html.Div([
                    html.Span(style={'display':'inline-block','width':'9px',
                                     'height':'9px','borderRadius':'50%',
                                     'background':GREEN if mkt else RED,
                                     'marginRight':'7px','verticalAlign':'middle',
                                     'animation':'pulse 2s infinite' if mkt else 'none'}),
                    html.Span('NSE OPEN' if mkt else 'NSE CLOSED',
                              style={'color':GREEN if mkt else RED,
                                     'fontWeight':'700','fontSize':'13px'}),
                ], style={'marginBottom':'4px'}),
                html.Div(f'Updated: {ist}',style={'color':DIM,'fontSize':'11px'}),
                html.Div('Auto-refresh: 30s',style={'color':DIM,'fontSize':'11px'}),
            ])

            # Cards
            cards = [
                scard('Total Value',     f'Rs {total:,.0f}', f'Started: Rs {start:,.0f}', ACCENT),
                scard('Cash',            f'Rs {capital:,.0f}', f'{capital/total*100:.1f}% of portfolio' if total else '', BLUE),
                scard('Total P&L',       f'{sg(pnl)}Rs {pnl:,.0f}', f'{sg(pnl_pct)}{pnl_pct:.2f}%', pc),
                scard('Realized P&L',    f'{sg(realized)}Rs {realized:,.0f}', f'{len(sells)} closed trades', pc),
                scard('Positions',       str(len(pos)), f'Max 5', YELLOW, YELLOW),
                scard('Win Rate',        f'{wr:.0f}%', f'{wins}W  /  {losses}L', wc),
            ]

            # Equity curve
            ev=[start]; ed=['Start']; run=start
            for t in hist:
                if t.get('action')=='SELL':
                    run += t.get('pnl',0); ev.append(run)
                    ed.append(t.get('date','')[:10])
            ev.append(total); ed.append('Now')
            ec = GREEN if ev[-1]>=ev[0] else RED
            eq = go.Figure(go.Scatter(x=ed,y=ev,mode='lines+markers',
                line=dict(color=ec,width=2),fill='tozeroy',fillcolor=ec+'22',
                marker=dict(size=4,color=ec),
                hovertemplate='%{x}<br>Rs %{y:,.0f}<extra></extra>'))
            eq.update_layout(**_dark(240))
            eq.update_yaxes(tickprefix='Rs ', tickformat=',.0f')

            # Allocation donut
            syms  = list(pos.keys())
            al_l  = ['Cash']+syms
            al_v  = [round(capital,2)]+[
                round(p['shares']*p.get('current_price',p.get('entry_price',0)),2)
                for p in pos.values()]
            pcols = [BLUE,GREEN,YELLOW,ORANGE,ACCENT,PURPLE,RED]
            al = go.Figure(go.Pie(labels=al_l,values=al_v,hole=0.55,
                marker=dict(colors=pcols[:len(al_l)],
                            line=dict(color=BG,width=2)),
                textfont=dict(color=TEXT,size=12),
                hovertemplate='%{label}<br>Rs %{value:,.0f}<br>%{percent}<extra></extra>'))
            al.update_layout(paper_bgcolor=CARD,plot_bgcolor=CARD,
                margin=dict(l=10,r=10,t=10,b=10),height=240,
                font=dict(color=TEXT,family='Segoe UI,Arial'),
                legend=dict(font=dict(color=TEXT,size=11),
                            bgcolor='rgba(0,0,0,0)'),showlegend=True)

            # Positions table
            if pos:
                rows=[]
                for sym,p in pos.items():
                    e=p.get('entry_price',0); c=p.get('current_price',e)
                    sh=p.get('shares',0); up=(c-e)*sh; upct=(c-e)/e*100 if e else 0
                    rows.append({'Symbol':sym,'Shares':sh,
                        'Entry Rs':f'{e:,.2f}','Current Rs':f'{c:,.2f}',
                        'Cost Rs':f'{p.get("cost",0):,.2f}',
                        'Unrealized':f'{sg(up)}{up:,.2f}',
                        'Chg %':f'{sg(upct)}{upct:.2f}%',
                        'Entry Date':p.get('entry_date','')[:10],
                        'Reason':p.get('reason','')})
                ptbl = dtable(rows,[
                    {'if':{'filter_query':'{Unrealized} contains "+"'},'color':GREEN},
                    {'if':{'filter_query':'{Unrealized} contains "-"'},'color':RED},
                    {'if':{'column_id':'Symbol'},'color':ACCENT,'fontWeight':'700'},
                ])
            else:
                ptbl = html.P('No open positions',
                              style={'color':DIM,'textAlign':'center','padding':'24px'})

            # History table
            hrows=[]
            for t in reversed(hist[-40:]):
                a=t.get('action',''); pt=t.get('pnl',0)
                hrows.append({'Date':t.get('date','')[:16].replace('T',' '),
                    'Action':a,'Symbol':t.get('symbol',''),
                    'Shares':t.get('shares',0),
                    'Price Rs':f'{t.get("price",0):,.2f}',
                    'P&L Rs':f'{sg(pt)}{pt:,.2f}' if a=='SELL' else '—',
                    'Reason':t.get('reason','')})
            htbl = dtable(hrows,[
                {'if':{'filter_query':'{Action} = BUY'},'color':GREEN,'fontWeight':'700'},
                {'if':{'filter_query':'{Action} = SELL'},'color':RED,'fontWeight':'700'},
                {'if':{'filter_query':'{P&L Rs} contains "+"'},'color':GREEN},
                {'if':{'filter_query':'{P&L Rs} contains "-"'},'color':RED},
            ],15) if hrows else html.P('No trades yet',
                style={'color':DIM,'textAlign':'center','padding':'24px'})

            return hdr, cards, eq, al, ptbl, htbl

        except Exception:
            traceback.print_exc()
            e=_empty('Error — check terminal')
            err=html.P('Error loading data',style={'color':RED,'padding':'20px'})
            return html.Div('Error',style={'color':RED}), [], e, e, err, err

    return app
