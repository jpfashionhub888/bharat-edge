# monitoring/dashboard.py
# BHARAT EDGE — Bloomberg-Style Live Dashboard
# 7-tab dark terminal UI · IBM Plex Mono · Orange accents
# INR currency · NSE market hours · 60s auto-refresh

from __future__ import annotations
import json, os, traceback, threading, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import plotly.express as px
from dash import Dash, dcc, html, Input, Output, State, dash_table

# ── Paths (always resolved from repo root) ────────────────────
ROOT          = Path(__file__).resolve().parent.parent
LOG           = ROOT / "logs"
TRADES_FILE   = LOG / "bharat_trades.json"
CLOSED_FILE   = LOG / "closed_trades.json"
CIRCUIT_FILE  = LOG / "circuit_breaker.json"
SCAN_FILE     = LOG / "scan_results.json"

STARTING_CAP  = 100_000.0
REFRESH_S     = 60          # dashboard refresh interval (seconds)
HEARTBEAT_S   = 300         # Telegram alert if scan silent > 5 min

# ── Bloomberg terminal palette ────────────────────────────────
BG      = "#0a0a0a"
PANEL   = "#111111"
PANEL2  = "#1a1a1a"
BORDER  = "#2a2a2a"
TEXT    = "#e8e8e8"
DIM     = "#666666"
MUTED   = "#444444"
ORANGE  = "#f97316"
ORANGE2 = "#fb923c"
GREEN   = "#22c55e"
RED     = "#ef4444"
YELLOW  = "#eab308"
BLUE    = "#3b82f6"
PURPLE  = "#a855f7"
CYAN    = "#06b6d4"
FONT    = "IBM Plex Mono, Courier New, monospace"

def _rgba(hex_color: str, alpha: float) -> str:
    """Convert '#rrggbb' + alpha float to 'rgba(r,g,b,a)' for Plotly."""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Indian sector map ─────────────────────────────────────────
SECTOR_COLORS = {
    "IT"      : BLUE,
    "BANKING" : ORANGE,
    "NBFC"    : ORANGE2,
    "PHARMA"  : GREEN,
    "AUTO"    : CYAN,
    "ENERGY"  : YELLOW,
    "METAL"   : "#94a3b8",
    "FMCG"    : "#84cc16",
    "INFRA"   : "#f59e0b",
    "CONSUMER": PURPLE,
    "TELECOM" : "#ec4899",
    "REALTY"  : "#14b8a6",
}


# ╔══════════════════════════════════════════════════════════════╗
# ║  DATA HELPERS — all reads from disk, no in-memory caching   ║
# ╚══════════════════════════════════════════════════════════════╝

def _safe_load(path: Path, default: Any) -> Any:
    """Load JSON with .bak fallback and corrupt-file recovery."""
    bak = path.with_suffix(path.suffix + ".bak")
    for src in (path, bak):
        if src.exists():
            try:
                return json.loads(src.read_text(encoding="utf-8"))
            except Exception:
                continue
    return default


def _atomic_write(path: Path, data: Any) -> None:
    """Write JSON atomically: .tmp → rename, backup old file first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    bak = path.with_suffix(path.suffix + ".bak")
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if path.exists():
            import shutil
            shutil.copy2(path, bak)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[dashboard] atomic write failed: {e}")


def load_portfolio() -> dict:
    return _safe_load(TRADES_FILE, {
        "capital"         : STARTING_CAP,
        "starting_capital": STARTING_CAP,
        "positions"       : {},
        "trade_history"   : [],
        "saved_at"        : None,
    })


def load_closed_trades() -> dict:
    return _safe_load(CLOSED_FILE, {"trades": [], "summary": {}})


def load_circuit() -> dict:
    return _safe_load(CIRCUIT_FILE, {"triggered": False, "trigger_reason": None})


def load_scan() -> dict:
    return _safe_load(SCAN_FILE, {
        "scan_time"    : None,
        "market_regime": {},
        "signals"      : [],
    })


def fetch_live_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch latest NSE prices via yfinance. Returns {sym: price}."""
    prices: dict[str, float] = {}
    if not symbols:
        return prices
    try:
        import yfinance as yf
        data = yf.download(
            " ".join(symbols), period="1d", interval="1m",
            progress=False, auto_adjust=True, group_by="ticker",
        )
        if data.empty:
            return prices
        for sym in symbols:
            try:
                if len(symbols) == 1:
                    cl = data["Close"]
                else:
                    cl = data["Close"][sym]
                prices[sym] = float(cl.dropna().iloc[-1])
            except Exception:
                pass
    except Exception as e:
        print(f"[dashboard] price fetch error: {e}")
    return prices


def fetch_nifty_vix() -> tuple[float, float]:
    """Returns (nifty_price, india_vix)."""
    try:
        import yfinance as yf
        data = yf.download("^NSEI ^INDIAVIX", period="1d",
                           interval="1m", progress=False,
                           auto_adjust=True, group_by="ticker")
        nifty = float(data["Close"]["^NSEI"].dropna().iloc[-1])
        vix   = float(data["Close"]["^INDIAVIX"].dropna().iloc[-1])
        return nifty, vix
    except Exception:
        return 0.0, 15.0


# ╔══════════════════════════════════════════════════════════════╗
# ║  TIME HELPERS                                               ║
# ╚══════════════════════════════════════════════════════════════╝

def _ist_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)


def _is_market_open() -> bool:
    ist = _ist_now()
    if ist.weekday() >= 5:
        return False
    t = ist.hour * 60 + ist.minute
    return 555 <= t <= 930   # 9:15 – 15:30


def _scan_age(scan_time_str: str | None) -> str:
    if not scan_time_str:
        return "never"
    try:
        ts  = datetime.fromisoformat(scan_time_str)
        ago = (datetime.now() - ts).total_seconds()
        if ago < 60:
            return f"{int(ago)}s ago"
        if ago < 3600:
            return f"{int(ago/60)}m ago"
        return f"{int(ago/3600)}h ago"
    except Exception:
        return "unknown"


def _inr(v: float, cr: bool = False) -> str:
    """Format as Indian ₹ with optional lakh/crore suffix."""
    if cr and abs(v) >= 1e7:
        return f"₹{v/1e7:.2f}Cr"
    if cr and abs(v) >= 1e5:
        return f"₹{v/1e5:.2f}L"
    return f"₹{v:,.2f}"


# ╔══════════════════════════════════════════════════════════════╗
# ║  UI PRIMITIVES                                              ║
# ╚══════════════════════════════════════════════════════════════╝

_CELL = {
    "backgroundColor": PANEL,
    "color"          : TEXT,
    "border"         : f"1px solid {BORDER}",
    "textAlign"      : "center",
    "padding"        : "8px 10px",
    "fontFamily"     : FONT,
    "fontSize"       : "12px",
    "whiteSpace"     : "nowrap",
}
_HEADER = {
    "backgroundColor": PANEL2,
    "color"          : ORANGE,
    "fontWeight"     : "700",
    "letterSpacing"  : "1px",
    "textTransform"  : "uppercase",
    "fontSize"       : "10px",
    "border"         : f"1px solid {BORDER}",
    "fontFamily"     : FONT,
}
_ODD = {"if": {"row_index": "odd"}, "backgroundColor": PANEL2}


def _panel(children, style=None):
    s = {
        "background"   : PANEL,
        "border"       : f"1px solid {BORDER}",
        "borderRadius" : "4px",
        "padding"      : "16px",
        "marginBottom" : "14px",
    }
    if style:
        s.update(style)
    return html.Div(children, style=s)


def _section(title: str, children):
    return _panel([
        html.Div(title, style={
            "color"        : ORANGE,
            "fontSize"     : "11px",
            "fontWeight"   : "700",
            "letterSpacing": "2px",
            "textTransform": "uppercase",
            "marginBottom" : "12px",
            "paddingBottom": "8px",
            "borderBottom" : f"1px solid {BORDER}",
            "fontFamily"   : FONT,
        }),
        children,
    ])


def _kpi(label: str, value: str, color: str = TEXT, sub: str = ""):
    return html.Div([
        html.Div(label, style={
            "color"        : DIM,
            "fontSize"     : "9px",
            "letterSpacing": "1.5px",
            "textTransform": "uppercase",
            "fontFamily"   : FONT,
            "marginBottom" : "4px",
        }),
        html.Div(value, style={
            "color"     : color,
            "fontSize"  : "18px",
            "fontWeight": "700",
            "fontFamily": FONT,
            "lineHeight": "1",
        }),
        html.Div(sub, style={
            "color"    : DIM,
            "fontSize" : "10px",
            "fontFamily": FONT,
            "marginTop": "3px",
        }),
    ], style={
        "background"  : PANEL,
        "border"      : f"1px solid {BORDER}",
        "borderLeft"  : f"3px solid {color}",
        "borderRadius": "4px",
        "padding"     : "12px 14px",
    })


def _badge(text: str, color: str = ORANGE):
    return html.Span(text, style={
        "background"  : color + "22",
        "color"       : color,
        "border"      : f"1px solid {color}44",
        "borderRadius": "3px",
        "padding"     : "2px 7px",
        "fontSize"    : "11px",
        "fontFamily"  : FONT,
        "fontWeight"  : "700",
    })


def _dtable(rows: list, cond: list = None, page: int = 15):
    if not rows:
        return html.Div("— no data —", style={
            "color": DIM, "fontFamily": FONT,
            "fontSize": "12px", "padding": "20px", "textAlign": "center",
        })
    cols = [{"name": c, "id": c} for c in rows[0]]
    return dash_table.DataTable(
        data=rows, columns=cols,
        page_size=page, sort_action="native",
        style_table={"overflowX": "auto"},
        style_cell=_CELL,
        style_header=_HEADER,
        style_data_conditional=[_ODD] + (cond or []),
    )


def _signal_color(sig: str) -> str:
    sig = sig.upper()
    if sig in ("STRONG_BUY", "BUY"):
        return GREEN
    if sig in ("STRONG_SELL", "SELL", "AVOID"):
        return RED
    return YELLOW


def _regime_color(regime: str) -> str:
    r = regime.upper()
    if "BULL" in r:
        return GREEN
    if "BEAR" in r:
        return RED
    return YELLOW


def _dark_fig(height: int = 260) -> dict:
    return dict(
        paper_bgcolor=PANEL, plot_bgcolor=PANEL,
        margin=dict(l=55, r=15, t=30, b=40),
        height=height,
        font=dict(color=TEXT, family=FONT, size=11),
        xaxis=dict(gridcolor=BORDER, color=DIM, linecolor=BORDER,
                   showgrid=True, zeroline=False),
        yaxis=dict(gridcolor=BORDER, color=DIM, linecolor=BORDER,
                   showgrid=True, zeroline=False),
        showlegend=False,
        hovermode="x unified",
        hoverlabel=dict(bgcolor=PANEL2, font_family=FONT, font_size=11),
    )


def _empty_fig(msg: str = "No data", height: int = 260) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, x=0.5, y=0.5, xref="paper",
                       yref="paper", showarrow=False,
                       font=dict(color=DIM, size=13, family=FONT))
    fig.update_layout(**_dark_fig(height))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


# ╔══════════════════════════════════════════════════════════════╗
# ║  EARNINGS HELPER                                            ║
# ╚══════════════════════════════════════════════════════════════╝

def _upcoming_earnings() -> list[dict]:
    """
    Fetch earnings calendar for NSE stocks via yfinance.
    Returns list of dicts with symbol, date, epsEstimate.
    """
    from config.settings import STOCK_WATCHLIST
    rows = []
    try:
        import yfinance as yf
        watch = [s for s in STOCK_WATCHLIST if ".NS" in s][:20]
        for sym in watch:
            try:
                cal = yf.Ticker(sym).calendar
                if cal is None:
                    continue
                # yfinance returns a dict or DataFrame
                if hasattr(cal, "to_dict"):
                    cal = cal.to_dict()
                date_val = (cal.get("Earnings Date") or
                            cal.get("earningsDate") or
                            cal.get("Earnings Dates", [None])
                            )
                if isinstance(date_val, list):
                    date_val = date_val[0] if date_val else None
                if date_val is None:
                    continue
                if hasattr(date_val, "date"):
                    date_val = str(date_val.date())
                else:
                    date_val = str(date_val)[:10]
                rows.append({
                    "Symbol"       : sym.replace(".NS", ""),
                    "Earnings Date": date_val,
                    "EPS Est"      : cal.get("EPS Estimate", "—"),
                    "Revenue Est"  : cal.get("Revenue Estimate", "—"),
                })
            except Exception:
                pass
    except Exception:
        pass
    rows.sort(key=lambda r: r["Earnings Date"])
    return rows


# ╔══════════════════════════════════════════════════════════════╗
# ║  APP FACTORY                                                ║
# ╚══════════════════════════════════════════════════════════════╝

def create_app(telegram=None) -> Dash:
    """
    Build and return the Dash application.
    Pass a BharatTelegram instance to enable heartbeat alerts.
    """

    app = Dash(
        __name__,
        title="BharatEdge Terminal",
        update_title=None,
        suppress_callback_exceptions=True,
    )

    # ── Google Font + global CSS ──────────────────────────────
    app.index_string = (
        "<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>"
        "{%favicon%}{%css%}"
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link href='https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;700&display=swap' rel='stylesheet'>"
        "<style>"
        f"*{{margin:0;padding:0;box-sizing:border-box}}"
        f"body{{background:{BG};color:{TEXT};font-family:{FONT}}}"
        "::-webkit-scrollbar{width:5px;height:5px}"
        f"::-webkit-scrollbar-track{{background:{BG}}}"
        f"::-webkit-scrollbar-thumb{{background:{BORDER};border-radius:2px}}"
        f".tab--selected{{border-top:2px solid {ORANGE} !important;color:{ORANGE} !important}}"
        ".dash-table-container .row{margin:0}"
        "@keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}"
        "</style></head><body>{%app_entry%}"
        "<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"
    )

    # ── Top status bar ────────────────────────────────────────
    status_bar = html.Div(id="status-bar", style={
        "background"  : PANEL2,
        "borderBottom": f"1px solid {BORDER}",
        "padding"     : "6px 20px",
        "display"     : "flex",
        "alignItems"  : "center",
        "gap"         : "24px",
        "fontSize"    : "11px",
        "fontFamily"  : FONT,
        "position"    : "sticky",
        "top"         : "0",
        "zIndex"      : "1000",
    })

    # ── Tab styles ────────────────────────────────────────────
    TAB_STYLE = {
        "background"  : PANEL2,
        "color"       : DIM,
        "border"      : f"1px solid {BORDER}",
        "borderBottom": "none",
        "padding"     : "10px 18px",
        "fontFamily"  : FONT,
        "fontSize"    : "11px",
        "fontWeight"  : "700",
        "letterSpacing": "1px",
    }
    TAB_SEL = {
        **TAB_STYLE,
        "color"      : ORANGE,
        "borderTop"  : f"2px solid {ORANGE}",
        "background" : PANEL,
    }

    # ── Main layout ───────────────────────────────────────────
    app.layout = html.Div(style={"backgroundColor": BG, "minHeight": "100vh"}, children=[
        dcc.Interval(id="iv", interval=REFRESH_S * 1000, n_intervals=0),

        # Title bar
        html.Div(style={
            "background"  : PANEL2,
            "borderBottom": f"2px solid {ORANGE}",
            "padding"     : "12px 20px",
            "display"     : "flex",
            "justifyContent": "space-between",
            "alignItems"  : "center",
        }, children=[
            html.Div([
                html.Span("BHARAT", style={"color": ORANGE, "fontWeight": "700",
                                           "fontSize": "18px", "letterSpacing": "3px"}),
                html.Span("EDGE", style={"color": TEXT, "fontWeight": "400",
                                         "fontSize": "18px", "letterSpacing": "3px"}),
                html.Span(" TERMINAL", style={"color": DIM, "fontSize": "11px",
                                              "letterSpacing": "4px", "marginLeft": "8px"}),
            ]),
            html.Div(id="topbar-right", style={"fontSize": "11px", "color": DIM}),
        ]),

        # Status bar
        status_bar,

        # Tabs
        html.Div(style={"padding": "0 16px"}, children=[
            dcc.Tabs(id="tabs", value="overview", style={
                "borderBottom": f"1px solid {BORDER}",
                "fontFamily"  : FONT,
            }, children=[
                dcc.Tab(label="01 OVERVIEW",  value="overview",
                        style=TAB_STYLE, selected_style=TAB_SEL),
                dcc.Tab(label="02 POSITIONS", value="positions",
                        style=TAB_STYLE, selected_style=TAB_SEL),
                dcc.Tab(label="03 SIGNALS",   value="signals",
                        style=TAB_STYLE, selected_style=TAB_SEL),
                dcc.Tab(label="04 SECTORS",   value="sectors",
                        style=TAB_STYLE, selected_style=TAB_SEL),
                dcc.Tab(label="05 EARNINGS",  value="earnings",
                        style=TAB_STYLE, selected_style=TAB_SEL),
                dcc.Tab(label="06 HISTORY",   value="history",
                        style=TAB_STYLE, selected_style=TAB_SEL),
                dcc.Tab(label="07 SYS CONFIG",value="sysconfig",
                        style=TAB_STYLE, selected_style=TAB_SEL),
            ]),
            html.Div(id="tab-content",
                     style={"padding": "16px 0", "minHeight": "80vh"}),
        ]),

        # Footer
        html.Div(style={
            "borderTop": f"1px solid {BORDER}",
            "padding"  : "8px 20px",
            "display"  : "flex",
            "justifyContent": "space-between",
            "fontSize" : "10px",
            "color"    : MUTED,
            "fontFamily": FONT,
        }, children=[
            html.Span("BharatEdge V2  ·  ML Ensemble  ·  NSE/BSE India  ·  Paper Trading"),
            html.Span(f"Auto-refresh: {REFRESH_S}s  ·  Zerodha Kite API"),
        ]),
    ])

    # ─────────────────────────────────────────────────────────
    # CALLBACK: status bar + topbar (every refresh)
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("status-bar",   "children"),
        Output("topbar-right", "children"),
        Input("iv", "n_intervals"),
    )
    def update_status(_n):
        try:
            port    = load_portfolio()
            scan    = load_scan()
            circuit = load_circuit()
            ist     = _ist_now()
            mkt_open = _is_market_open()
            regime  = scan.get("market_regime", {})

            # Market dot
            dot_color = GREEN if mkt_open else RED
            dot = html.Span(style={
                "display": "inline-block", "width": "7px", "height": "7px",
                "borderRadius": "50%", "background": dot_color,
                "marginRight": "6px", "verticalAlign": "middle",
                "animation": "blink 2s infinite" if mkt_open else "none",
            })
            mkt_label = "NSE OPEN" if mkt_open else "NSE CLOSED"

            capital  = float(port.get("capital", STARTING_CAP))
            start    = float(port.get("starting_capital", STARTING_CAP))
            pos      = port.get("positions", {})
            pos_val  = sum(
                p["shares"] * p.get("current_price", p.get("entry_price", 0))
                for p in pos.values()
            )
            total    = capital + pos_val
            pnl      = total - start
            pnl_col  = GREEN if pnl >= 0 else RED
            regime_name = regime.get("regime", "UNKNOWN")

            cb_triggered = circuit.get("triggered", False)
            cb_color     = RED if cb_triggered else GREEN
            cb_text      = "CB: TRIGGERED" if cb_triggered else "CB: OK"

            scan_age = _scan_age(scan.get("scan_time"))

            items = [
                (dot, mkt_label, dot_color),
            ]

            bar = [
                dot,
                html.Span(mkt_label, style={"color": dot_color,
                          "fontWeight": "700", "marginRight": "20px"}),
                html.Span("NIFTY: ", style={"color": DIM}),
                html.Span("—", style={"color": TEXT, "marginRight": "20px"}),
                html.Span("VIX: ", style={"color": DIM}),
                html.Span(f"{regime.get('vix', 0):.1f}", style={"color": YELLOW, "marginRight": "20px"}),
                html.Span("REGIME: ", style={"color": DIM}),
                html.Span(regime_name, style={"color": _regime_color(regime_name),
                          "fontWeight": "700", "marginRight": "20px"}),
                html.Span("VALUE: ", style={"color": DIM}),
                html.Span(_inr(total), style={"color": TEXT, "marginRight": "20px"}),
                html.Span("P&L: ", style={"color": DIM}),
                html.Span(f"{'+' if pnl >= 0 else ''}{_inr(pnl)}", style={
                    "color": pnl_col, "fontWeight": "700", "marginRight": "20px"}),
                html.Span(cb_text, style={"color": cb_color, "fontWeight": "700", "marginRight": "20px"}),
                html.Span("LAST SCAN: ", style={"color": DIM}),
                html.Span(scan_age, style={"color": TEXT}),
            ]

            topbar = html.Span(ist.strftime("%A %d %b %Y  %H:%M:%S IST"))
            return bar, topbar

        except Exception:
            traceback.print_exc()
            return [html.Span("Loading...", style={"color": DIM})], html.Span("")

    # ─────────────────────────────────────────────────────────
    # CALLBACK: tab content router
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("tab-content", "children"),
        Input("tabs",         "value"),
        Input("iv",           "n_intervals"),
    )
    def render_tab(tab, _n):
        try:
            if tab == "overview":  return _tab_overview()
            if tab == "positions": return _tab_positions()
            if tab == "signals":   return _tab_signals()
            if tab == "sectors":   return _tab_sectors()
            if tab == "earnings":  return _tab_earnings()
            if tab == "history":   return _tab_history()
            if tab == "sysconfig": return _tab_sysconfig()
        except Exception:
            tb = traceback.format_exc()
            print(tb)
            return html.Div([
                html.Div("TAB ERROR — details below:",
                         style={"color": RED, "fontWeight": "700",
                                "fontFamily": FONT, "marginBottom": "10px"}),
                html.Pre(tb, style={
                    "color": "#ff8888", "fontFamily": FONT,
                    "fontSize": "11px", "background": PANEL2,
                    "padding": "16px", "borderRadius": "4px",
                    "overflowX": "auto", "whiteSpace": "pre-wrap",
                }),
            ], style={"padding": "20px"})
        return html.Div()

    return app


# ╔══════════════════════════════════════════════════════════════╗
# ║  TAB 1: OVERVIEW                                            ║
# ╚══════════════════════════════════════════════════════════════╝

def _tab_overview() -> html.Div:
    port    = load_portfolio()
    circuit = load_circuit()
    closed  = load_closed_trades()
    summary = closed.get("summary", {})

    capital  = float(port.get("capital", STARTING_CAP))
    start    = float(port.get("starting_capital", STARTING_CAP))
    pos      = port.get("positions", {})
    history  = port.get("trade_history", [])

    # Live position values (threaded with timeout so slow yfinance won't hang)
    syms = list(pos.keys())
    live: dict = {}
    if syms:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(fetch_live_prices, syms)
            try:
                live = fut.result(timeout=10)
            except Exception:
                live = {}
    for sym, p in pos.items():
        lp = live.get(sym)
        if lp and lp > 0:
            p["current_price"] = lp

    pos_val = sum(
        p["shares"] * p.get("current_price", p.get("entry_price", 0))
        for p in pos.values()
    )
    total    = capital + pos_val
    pnl      = total - start
    pnl_pct  = pnl / start * 100 if start else 0
    pnl_col  = GREEN if pnl >= 0 else RED

    sells    = [t for t in history if t.get("action") == "SELL"]
    wins     = sum(1 for t in sells if t.get("pnl", 0) > 0)
    losses   = len(sells) - wins
    wr       = wins / len(sells) * 100 if sells else 0
    wr_col   = GREEN if wr >= 50 else RED
    realized = sum(t.get("pnl", 0) for t in sells)

    pf       = summary.get("profit_factor", 0)
    avg_win  = summary.get("avg_win", 0)
    avg_loss = summary.get("avg_loss", 0)

    sg = lambda v: "+" if v >= 0 else ""

    # KPI row
    kpis = html.Div(style={
        "display": "grid",
        "gridTemplateColumns": "repeat(7, 1fr)",
        "gap": "10px",
        "marginBottom": "14px",
    }, children=[
        _kpi("Total Value",   _inr(total),   ORANGE,
             f"Start: {_inr(start)}"),
        _kpi("Cash",          _inr(capital),  BLUE,
             f"{capital/total*100:.1f}% of portfolio" if total else ""),
        _kpi("Total P&L",     f"{sg(pnl)}{_inr(pnl)}", pnl_col,
             f"{sg(pnl_pct)}{pnl_pct:.2f}%"),
        _kpi("Realized P&L",  f"{sg(realized)}{_inr(realized)}", pnl_col,
             f"{len(sells)} closed trades"),
        _kpi("Open Positions", str(len(pos)), YELLOW, "Max 5"),
        _kpi("Win Rate",      f"{wr:.0f}%",  wr_col, f"{wins}W  {losses}L"),
        _kpi("Profit Factor", f"{pf:.2f}",   GREEN if pf >= 1 else RED,
             f"W:{_inr(avg_win)} / L:{_inr(avg_loss)}"),
    ])

    # Equity curve
    eq_vals  = [start]
    eq_dates = ["Start"]
    running  = start
    for t in history:
        if t.get("action") == "SELL":
            running  += t.get("pnl", 0)
            eq_vals.append(running)
            eq_dates.append(t.get("date", "")[:10])
    eq_vals.append(total)
    eq_dates.append("Now")

    ec  = GREEN if eq_vals[-1] >= eq_vals[0] else RED
    fig = go.Figure(go.Scatter(
        x=eq_dates, y=eq_vals,
        mode="lines+markers",
        line=dict(color=ec, width=2),
        fill="tozeroy", fillcolor=_rgba(ec, 0.094),
        marker=dict(size=4, color=ec),
        hovertemplate="%{x}<br>₹%{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(**_dark_fig(280))
    fig.update_yaxes(tickprefix="₹", tickformat=",.0f")

    # Allocation donut
    al_labels = ["Cash"] + syms
    al_vals   = [round(capital, 2)] + [
        round(p["shares"] * p.get("current_price", p.get("entry_price", 0)), 2)
        for p in pos.values()
    ]
    pie_colors = [BLUE, ORANGE, GREEN, YELLOW, CYAN, PURPLE, RED, ORANGE2]

    pie = go.Figure(go.Pie(
        labels=al_labels, values=al_vals, hole=0.6,
        marker=dict(colors=pie_colors[:len(al_labels)],
                    line=dict(color=BG, width=2)),
        textfont=dict(color=TEXT, size=11, family=FONT),
        hovertemplate="%{label}<br>₹%{value:,.0f}<br>%{percent}<extra></extra>",
    ))
    pie.update_layout(
        paper_bgcolor=PANEL, plot_bgcolor=PANEL,
        margin=dict(l=10, r=10, t=30, b=10), height=280,
        font=dict(color=TEXT, family=FONT, size=11),
        legend=dict(font=dict(color=TEXT, size=10, family=FONT),
                    bgcolor="rgba(0,0,0,0)"),
        showlegend=True,
    )

    # Circuit breaker banner
    cb = circuit.get("triggered", False)
    cb_banner = html.Div(
        f"⚡ CIRCUIT BREAKER ACTIVE — {circuit.get('trigger_reason', '')}",
        style={
            "background": RED + "22", "color": RED,
            "border": f"1px solid {RED}", "borderRadius": "4px",
            "padding": "10px 16px", "marginBottom": "14px",
            "fontFamily": FONT, "fontSize": "12px", "fontWeight": "700",
        }
    ) if cb else html.Div()

    return html.Div([
        cb_banner,
        kpis,
        html.Div(style={"display": "grid", "gridTemplateColumns": "2fr 1fr",
                        "gap": "14px", "marginBottom": "14px"}, children=[
            _section("PORTFOLIO EQUITY CURVE (₹)",
                     dcc.Graph(figure=fig, config={"displayModeBar": False})),
            _section("CAPITAL ALLOCATION",
                     dcc.Graph(figure=pie, config={"displayModeBar": False})),
        ]),
    ])


# ╔══════════════════════════════════════════════════════════════╗
# ║  TAB 2: POSITIONS                                           ║
# ╚══════════════════════════════════════════════════════════════╝

def _tab_positions() -> html.Div:
    port = load_portfolio()
    pos  = port.get("positions", {})

    if not pos:
        return _section("OPEN POSITIONS", html.Div(
            "No open positions", style={"color": DIM, "fontFamily": FONT,
                                        "padding": "30px", "textAlign": "center"}))

    syms = list(pos.keys())
    live: dict = {}
    if syms:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(fetch_live_prices, syms)
            try:
                live = fut.result(timeout=10)
            except Exception:
                live = {}

    rows = []
    for sym, p in pos.items():
        entry   = p.get("entry_price", 0)
        curr    = live.get(sym, p.get("current_price", entry))
        p["current_price"] = curr
        shares  = p.get("shares", 0)
        cost    = p.get("cost", entry * shares)
        upnl    = (curr - entry) * shares
        upct    = (curr - entry) / entry * 100 if entry else 0
        sl_pct  = p.get("stop_loss_pct", 0.04)
        sl_px   = entry * (1 - sl_pct)
        highest = p.get("highest_price", curr)
        trail   = (highest - curr) / highest * 100 if highest else 0
        sig     = p.get("signal", 0)
        sector  = p.get("reason", "—")

        rows.append({
            "Symbol"    : sym.replace(".NS", ""),
            "Sector"    : sector,
            "Shares"    : shares,
            "Entry ₹"   : f"{entry:,.2f}",
            "Current ₹" : f"{curr:,.2f}",
            "Cost ₹"    : f"{cost:,.2f}",
            "Unreal P&L": f"{'+' if upnl >= 0 else ''}{upnl:,.2f}",
            "Chg %"     : f"{'+' if upct >= 0 else ''}{upct:.2f}%",
            "Stop ₹"    : f"{sl_px:,.2f}",
            "Trail %"   : f"{trail:.2f}%",
            "AI Score"  : f"{sig:.3f}",
            "Entry Date": p.get("entry_date", "")[:10],
        })

    cond = [
        {"if": {"filter_query": "{Unreal P&L} contains '+'"},
         "color": GREEN},
        {"if": {"filter_query": "{Unreal P&L} contains '-'"},
         "color": RED},
        {"if": {"column_id": "Symbol"},
         "color": ORANGE, "fontWeight": "700"},
        {"if": {"column_id": "Stop ₹"},
         "color": RED},
    ]
    return _section("OPEN POSITIONS — LIVE PRICES", _dtable(rows, cond, page=10))


# ╔══════════════════════════════════════════════════════════════╗
# ║  TAB 3: SIGNALS                                             ║
# ╚══════════════════════════════════════════════════════════════╝

def _tab_signals() -> html.Div:
    scan    = load_scan()
    signals = scan.get("signals", [])
    regime  = scan.get("market_regime", {})
    age     = _scan_age(scan.get("scan_time"))

    # Header with scan age
    header = html.Div(style={
        "display": "flex", "justifyContent": "space-between",
        "alignItems": "center", "marginBottom": "14px",
    }, children=[
        html.Div([
            html.Span("LAST SCANNED: ", style={"color": DIM, "fontSize": "11px"}),
            html.Span(age, style={"color": ORANGE, "fontWeight": "700",
                                  "fontSize": "11px", "fontFamily": FONT}),
        ]),
        html.Div([
            html.Span("REGIME: ", style={"color": DIM, "fontSize": "11px"}),
            html.Span(regime.get("regime", "—"),
                      style={"color": _regime_color(regime.get("regime", "")),
                             "fontWeight": "700", "fontSize": "11px"}),
            html.Span("  VIX: ", style={"color": DIM, "fontSize": "11px"}),
            html.Span(f"{regime.get('vix', 0):.1f}",
                      style={"color": YELLOW, "fontWeight": "700",
                             "fontSize": "11px"}),
        ]),
    ])

    if not signals:
        return _section("AI SCAN SIGNALS", html.Div([
            header,
            html.Div("No signals — run bharat_cloud_scan.py to generate",
                     style={"color": DIM, "fontFamily": FONT, "padding": "20px"})
        ]))

    rows = []
    for s in sorted(signals, key=lambda x: x.get("confidence", 0), reverse=True):
        sig = s.get("signal", "HOLD")
        rows.append({
            "Symbol"       : s.get("symbol", "").replace(".NS", ""),
            "Signal"       : sig,
            "AI Score"     : f"{s.get('confidence', 0):.3f}",
            "Price ₹"      : f"{s.get('price', 0):,.2f}",
            "Sector"       : s.get("sector", "—"),
            "Sector Status": s.get("sector_status", "NEUTRAL"),
            "Regime"       : regime.get("regime", "—"),
        })

    cond = [
        {"if": {"filter_query": "{Signal} = STRONG_BUY"},
         "color": GREEN, "fontWeight": "700"},
        {"if": {"filter_query": "{Signal} = BUY"},
         "color": GREEN},
        {"if": {"filter_query": "{Signal} = SELL"},
         "color": RED},
        {"if": {"filter_query": "{Signal} = AVOID"},
         "color": RED, "fontWeight": "700"},
        {"if": {"filter_query": "{Sector Status} = OVERWEIGHT"},
         "color": GREEN},
        {"if": {"filter_query": "{Sector Status} = UNDERWEIGHT"},
         "color": RED},
        {"if": {"column_id": "Symbol"},
         "color": ORANGE, "fontWeight": "700"},
    ]
    return _section("AI SCAN SIGNALS", html.Div([header, _dtable(rows, cond)]))


# ╔══════════════════════════════════════════════════════════════╗
# ║  TAB 4: SECTORS                                             ║
# ╚══════════════════════════════════════════════════════════════╝

def _tab_sectors() -> html.Div:
    scan    = load_scan()
    signals = scan.get("signals", [])

    # Aggregate signals by sector
    sector_data: dict[str, dict] = {}
    for s in signals:
        sec = s.get("sector", "UNKNOWN")
        if sec not in sector_data:
            sector_data[sec] = {
                "signals": [], "scores": [], "status": s.get("sector_status", "NEUTRAL")
            }
        sector_data[sec]["signals"].append(s.get("signal", "HOLD"))
        sector_data[sec]["scores"].append(s.get("confidence", 0))

    # Build summary rows
    rows = []
    for sec, d in sorted(sector_data.items()):
        sigs  = d["signals"]
        buys  = sum(1 for x in sigs if "BUY" in x)
        sells = sum(1 for x in sigs if "SELL" in x or x == "AVOID")
        avg   = sum(d["scores"]) / len(d["scores"]) if d["scores"] else 0
        status = d["status"]
        rows.append({
            "Sector"   : sec,
            "Status"   : status,
            "Avg Score": f"{avg:.3f}",
            "BUY Sigs" : buys,
            "SELL Sigs": sells,
            "Total"    : len(sigs),
            "Outlook"  : ("BULLISH" if buys > sells else
                          "BEARISH" if sells > buys else "NEUTRAL"),
        })

    # Bar chart of avg scores
    if rows:
        sectors = [r["Sector"] for r in rows]
        scores  = [float(r["Avg Score"]) for r in rows]
        colors  = [SECTOR_COLORS.get(s, ORANGE) for s in sectors]

        bar_fig = go.Figure(go.Bar(
            x=sectors, y=scores,
            marker_color=colors,
            text=[f"{s:.3f}" for s in scores],
            textposition="outside",
            textfont=dict(color=TEXT, family=FONT, size=10),
        ))
        bar_fig.update_layout(**_dark_fig(220))
        bar_fig.update_xaxes(tickfont=dict(size=10))
        bar_fig.update_yaxes(range=[0, 1], tickformat=".2f")
        chart = dcc.Graph(figure=bar_fig, config={"displayModeBar": False})
    else:
        chart = html.Div("Run a scan to populate sector data",
                         style={"color": DIM, "padding": "20px", "fontFamily": FONT})

    cond = [
        {"if": {"filter_query": "{Status} = OVERWEIGHT"}, "color": GREEN},
        {"if": {"filter_query": "{Status} = UNDERWEIGHT"}, "color": RED},
        {"if": {"filter_query": "{Outlook} = BULLISH"}, "color": GREEN},
        {"if": {"filter_query": "{Outlook} = BEARISH"}, "color": RED},
        {"if": {"column_id": "Sector"}, "color": ORANGE, "fontWeight": "700"},
    ]

    return html.Div([
        _section("SECTOR MOMENTUM SCORES", chart),
        _section("SECTOR ROTATION TABLE", _dtable(rows, cond, page=15)),
    ])


# ╔══════════════════════════════════════════════════════════════╗
# ║  TAB 5: EARNINGS                                            ║
# ╚══════════════════════════════════════════════════════════════╝

def _tab_earnings() -> html.Div:
    rows = _upcoming_earnings()

    if not rows:
        rows = [{"Note": "Earnings calendar requires live internet. Run dashboard with network access."}]

    now_date = _ist_now().strftime("%Y-%m-%d")
    cond = [
        {"if": {"filter_query": f"{{Earnings Date}} = '{now_date}'"},
         "backgroundColor": ORANGE + "22", "color": ORANGE, "fontWeight": "700"},
        {"if": {"column_id": "Symbol"}, "color": ORANGE, "fontWeight": "700"},
    ]
    return _section("NSE EARNINGS CALENDAR", html.Div([
        html.Div(f"Today: {now_date}  |  Showing upcoming results for tracked NSE stocks",
                 style={"color": DIM, "fontSize": "11px", "fontFamily": FONT,
                        "marginBottom": "12px"}),
        _dtable(rows, cond, page=20),
    ]))


# ╔══════════════════════════════════════════════════════════════╗
# ║  TAB 6: HISTORY                                             ║
# ╚══════════════════════════════════════════════════════════════╝

def _tab_history() -> html.Div:
    port    = load_portfolio()
    closed  = load_closed_trades()
    summary = closed.get("summary", {})
    trades  = closed.get("trades", [])

    # Also read raw history from trades file as fallback
    raw_hist = port.get("trade_history", [])
    sells    = [t for t in raw_hist if t.get("action") == "SELL"]

    # Summary KPIs
    wins     = summary.get("wins", 0) or sum(1 for t in sells if t.get("pnl", 0) > 0)
    losses   = summary.get("losses", 0) or len(sells) - wins
    wr       = summary.get("win_rate", wins / len(sells) if sells else 0) * 100 if summary.get("win_rate") else (wins / len(sells) * 100 if sells else 0)
    tot_pnl  = summary.get("total_pnl", sum(t.get("pnl", 0) for t in sells))
    pf       = summary.get("profit_factor", 0)
    avg_w    = summary.get("avg_win", 0)
    avg_l    = summary.get("avg_loss", 0)
    pnl_col  = GREEN if tot_pnl >= 0 else RED
    wr_col   = GREEN if wr >= 50 else RED

    kpis = html.Div(style={
        "display": "grid", "gridTemplateColumns": "repeat(6,1fr)",
        "gap": "10px", "marginBottom": "14px",
    }, children=[
        _kpi("Total Trades", str(wins + losses), ORANGE),
        _kpi("Win Rate",     f"{wr:.0f}%",        wr_col, f"{wins}W  {losses}L"),
        _kpi("Total P&L",    f"{_inr(tot_pnl)}",  pnl_col),
        _kpi("Profit Factor",f"{pf:.2f}",          GREEN if pf >= 1 else RED),
        _kpi("Avg Win",      f"{_inr(avg_w)}",     GREEN),
        _kpi("Avg Loss",     f"{_inr(avg_l)}",     RED),
    ])

    # Use TradeTracker trades if available, else fallback to raw history
    if trades:
        rows = [{
            "ID"        : t.get("id", ""),
            "Date"      : t.get("exit_time", "")[:16].replace("T", " "),
            "Symbol"    : t.get("symbol", ""),
            "Entry ₹"   : f"{t.get('entry_price', 0):,.2f}",
            "Exit ₹"    : f"{t.get('exit_price', 0):,.2f}",
            "Shares"    : t.get("shares", 0),
            "P&L ₹"     : f"{'+' if t.get('pnl_inr',0)>=0 else ''}{t.get('pnl_inr',0):,.2f}",
            "P&L %"     : f"{'+' if t.get('pnl_pct',0)>=0 else ''}{t.get('pnl_pct',0):.2f}%",
            "Hold Days" : t.get("hold_days", "—"),
            "Reason"    : t.get("reason", ""),
        } for t in reversed(trades[-40:])]
    else:
        rows = [{
            "Date"   : t.get("date", "")[:16].replace("T", " "),
            "Action" : t.get("action", ""),
            "Symbol" : t.get("symbol", "").replace(".NS", ""),
            "Shares" : t.get("shares", 0),
            "Price ₹": f"{t.get('price', 0):,.2f}",
            "P&L ₹"  : (f"{'+' if t.get('pnl',0)>=0 else ''}{t.get('pnl',0):,.2f}"
                        if t.get("action") == "SELL" else "—"),
            "Reason" : t.get("reason", ""),
        } for t in reversed(raw_hist[-40:])]

    cond = [
        {"if": {"filter_query": "{P&L ₹} contains '+'"},
         "color": GREEN},
        {"if": {"filter_query": "{P&L ₹} contains '-'"},
         "color": RED},
        {"if": {"column_id": "Symbol"},
         "color": ORANGE, "fontWeight": "700"},
        {"if": {"filter_query": "{Action} = BUY"},
         "color": GREEN, "fontWeight": "700"},
        {"if": {"filter_query": "{Action} = SELL"},
         "color": RED, "fontWeight": "700"},
    ]
    return html.Div([kpis, _section("TRADE EXECUTION LOG", _dtable(rows, cond))])


# ╔══════════════════════════════════════════════════════════════╗
# ║  TAB 7: SYS CONFIG                                          ║
# ╚══════════════════════════════════════════════════════════════╝

def _tab_sysconfig() -> html.Div:
    circuit = load_circuit()
    port    = load_portfolio()
    scan    = load_scan()

    def _row(k, v, vc=TEXT):
        return html.Tr([
            html.Td(k, style={"color": DIM, "fontFamily": FONT,
                               "fontSize": "11px", "padding": "7px 12px",
                               "letterSpacing": "0.5px"}),
            html.Td(str(v), style={"color": vc, "fontFamily": FONT,
                                    "fontSize": "12px", "padding": "7px 12px",
                                    "fontWeight": "500"}),
        ], style={"borderBottom": f"1px solid {BORDER}"})

    def _table(rows_data):
        return html.Table(
            [html.Tbody([_row(k, v, c) for k, v, c in rows_data])],
            style={"width": "100%", "borderCollapse": "collapse"},
        )

    # Configs from settings
    try:
        from config import settings as cfg
        market_cfg = [
            ("System",          cfg.SYSTEM_NAME,    ORANGE),
            ("Version",         cfg.VERSION,         TEXT),
            ("Mode",            cfg.MODE.upper(),    YELLOW if cfg.MODE == "paper" else GREEN),
            ("Timezone",        cfg.TIMEZONE,        TEXT),
            ("Market Open",     cfg.MARKET_OPEN,     TEXT),
            ("Market Close",    cfg.MARKET_CLOSE,    TEXT),
            ("Max Positions",   cfg.MAX_OPEN_POSITIONS, TEXT),
            ("Max Pos Size",    f"{cfg.MAX_POSITION_SIZE*100:.0f}%", TEXT),
            ("Stop Loss",       f"{cfg.STOP_LOSS_PCT*100:.1f}%", RED),
            ("Take Profit",     f"{cfg.TAKE_PROFIT_PCT*100:.1f}%", GREEN),
            ("Trailing Stop",   f"{cfg.TRAILING_STOP_PCT*100:.1f}%", YELLOW),
            ("Daily Loss Limit",f"{cfg.MAX_DAILY_LOSS*100:.0f}%", RED),
            ("Max Drawdown",    f"{cfg.MAX_DRAWDOWN*100:.0f}%", RED),
            ("Pred Threshold",  f"{cfg.PREDICTION_THRESHOLD:.2f}", TEXT),
            ("Retrain Days",    cfg.RETRAIN_DAYS,    TEXT),
        ]
    except Exception:
        market_cfg = [("Config", "Could not load config/settings.py", RED)]

    # Portfolio state
    capital  = port.get("capital", STARTING_CAP)
    start    = port.get("starting_capital", STARTING_CAP)
    saved_at = port.get("saved_at", "Unknown")
    port_cfg = [
        ("Starting Capital", _inr(start),              ORANGE),
        ("Current Cash",     _inr(capital),             TEXT),
        ("Open Positions",   len(port.get("positions",{})), TEXT),
        ("Total Trades",     len(port.get("trade_history",[])), TEXT),
        ("Last Saved",       str(saved_at)[:19],        TEXT),
        ("Trades File",      str(TRADES_FILE),           DIM),
        ("Closed File",      str(CLOSED_FILE),           DIM),
        ("Scan File",        str(SCAN_FILE),             DIM),
    ]

    # Circuit breaker
    cb = circuit.get("triggered", False)
    cb_cfg = [
        ("Status",          "TRIGGERED" if cb else "OK", RED if cb else GREEN),
        ("Reason",          circuit.get("trigger_reason") or "--", RED if cb else DIM),
        ("Daily Limit",     "5%",  RED),
        ("Weekly Limit",    "7%",  RED),
        ("Total Limit",     "10%", RED),
    ]

    # Scan state
    scan_cfg = [
        ("Last Scan",       scan.get("scan_time", "Never")[:19] if scan.get("scan_time") else "Never", TEXT),
        ("Signals Found",   len(scan.get("signals", [])), ORANGE),
        ("Regime",          scan.get("market_regime",{}).get("regime","--"), TEXT),
        ("VIX",             f"{scan.get('market_regime',{}).get('vix',0):.1f}", YELLOW),
        ("Can Trade",       scan.get("market_regime",{}).get("can_trade","--"), TEXT),
    ]

    return html.Div([
        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                        "gap": "14px"}, children=[
            _section("MARKET & STRATEGY SETTINGS", _table(market_cfg)),
            html.Div([
                _section("PORTFOLIO STATE",    _table(port_cfg)),
                _section("CIRCUIT BREAKER",    _table(cb_cfg)),
                _section("LAST SCAN STATE",    _table(scan_cfg)),
            ]),
        ]),
    ])
