# monitoring/dashboard.py
# BHARAT EDGE — Bloomberg-Style Live Dashboard
# 7-tab dark terminal UI · IBM Plex Mono · Orange accents
# INR currency · NSE market hours · 60s auto-refresh

from __future__ import annotations
import json, os, re, traceback, threading, time
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import plotly.express as px
from dash import Dash, dcc, html, Input, Output, State
import dash_ag_grid as dag

# ── Paths (always resolved from repo root) ────────────────────
ROOT          = Path(__file__).resolve().parent.parent
LOG           = ROOT / "logs"
TRADES_FILE   = LOG / "bharat_trades.json"
CLOSED_FILE   = LOG / "closed_trades.json"
CIRCUIT_FILE  = LOG / "circuit_breaker.json"
SCAN_FILE     = LOG / "scan_results.json"
SCAN_STATUS_FILE = LOG / "scan_status.json"
EQUITY_FILE    = LOG / "equity_history.json"

STARTING_CAP  = 100_000.0
REFRESH_S     = 60          # dashboard refresh interval (seconds)
HEARTBEAT_S   = 300         # Telegram alert if scan silent > 5 min
MARKET_TTL_S  = 45          # share one market request across callbacks
SCAN_GRACE_S  = 3600        # scheduled scan may run for up to 45 minutes
SCAN_STALLED_S = 3600       # systemd terminates scans after 45 minutes
SCAN_TIMES_UTC = ((3, 50), (7, 0), (9, 45))

_MARKET_LOCK = threading.Lock()
_MARKET_CACHE: dict[str, Any] = {
    "expires": 0.0, "symbols": set(), "prices": {},
    "nifty": None, "vix": None, "fetched_at": None,
    "source": "Yahoo Finance Chart API", "error": None, "stale": True,
}
_EARNINGS_LOCK = threading.Lock()
_EARNINGS_CACHE: dict[str, Any] = {
    "expires": 0.0, "rows": [], "fetched_at": None, "error": None,
    "requested": 0, "verified": 0,
}

# ── Bloomberg terminal palette ────────────────────────────────
BG      = "#07111f"
PANEL   = "#0e1a2b"
PANEL2  = "#111f33"
BORDER  = "#223550"
TEXT    = "#f3f7fc"
DIM     = "#8da2bd"
MUTED   = "#60748f"
ORANGE  = "#31c5f4"  # primary brand accent (legacy variable name)
ORANGE2 = "#8b7cf6"
GREEN   = "#37d39a"
RED     = "#fb7185"
YELLOW  = "#f6c453"
BLUE    = "#60a5fa"
PURPLE  = "#a78bfa"
CYAN    = "#22d3ee"
FONT    = "Inter, Manrope, Segoe UI, sans-serif"
MONO    = "JetBrains Mono, IBM Plex Mono, Consolas, monospace"

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
    found_file = False
    for source_name, src in (("PRIMARY", path), ("BACKUP", bak)):
        if src.exists():
            found_file = True
            try:
                loaded = json.loads(src.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    loaded["_storage_status"] = source_name
                return loaded
            except Exception:
                continue
    if isinstance(default, dict):
        recovered = dict(default)
        recovered["_storage_status"] = "INVALID" if found_file else "MISSING"
        return recovered
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
    state = _safe_load(
        CIRCUIT_FILE, {"triggered": False, "trigger_reason": None})
    if state.get("_storage_status") == "INVALID":
        state.update({
            "triggered": True,
            "trigger_reason": "Circuit-breaker state is unreadable",
        })
    return state


def load_scan() -> dict:
    return _safe_load(SCAN_FILE, {
        "scan_time"    : None,
        "market_regime": {},
        "signals"      : [],
    })


def load_scan_status() -> dict:
    return _safe_load(SCAN_STATUS_FILE, {
        "status": "UNKNOWN",
        "updated_at": None,
        "last_success_at": None,
        "error": None,
    })

def load_equity_history() -> list[dict]:
    value = _safe_load(EQUITY_FILE, {"points": []})
    points = value.get("points", []) if isinstance(value, dict) else []
    return points if isinstance(points, list) else []


def _latest_close(data, symbol: str) -> float | None:
    """Handle both yfinance MultiIndex column layouts."""
    try:
        if getattr(data.columns, "nlevels", 1) > 1:
            level0 = set(data.columns.get_level_values(0))
            level1 = set(data.columns.get_level_values(1))
            series = (data[symbol]["Close"] if symbol in level0
                      else data["Close"][symbol] if symbol in level1
                      else None)
        else:
            series = data["Close"]
        if series is None:
            return None
        clean = series.dropna()
        return float(clean.iloc[-1]) if not clean.empty else None
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _fetch_chart_quote(symbol: str) -> tuple[float, str]:
    """Fetch one quote without yfinance's fragile cookie/cache layer."""
    from urllib.parse import quote
    import requests

    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{quote(symbol, safe='')}?range=5d&interval=5m")
    response = requests.get(
        url, timeout=12, headers={"User-Agent": "BharatEdge/2.0"})
    response.raise_for_status()
    result = response.json().get("chart", {}).get("result") or []
    if not result:
        raise RuntimeError(f"no chart result for {symbol}")
    chart = result[0]
    timestamps = chart.get("timestamp") or []
    closes = (((chart.get("indicators") or {}).get("quote") or [{}])[0]
              .get("close") or [])
    valid = [(ts, value) for ts, value in zip(timestamps, closes)
             if value is not None]
    if not valid:
        raise RuntimeError(f"no valid close for {symbol}")
    ts, value = valid[-1]
    as_of = datetime.fromtimestamp(ts, timezone.utc).astimezone(
        timezone(timedelta(hours=5, minutes=30))).isoformat()
    return float(value), as_of


def get_market_data(symbols: list[str] | None = None) -> dict:
    """Return cached prices with explicit source, timestamp, and stale state."""
    requested = set(symbols or [])
    now = time.time()
    with _MARKET_LOCK:
        cached_symbols = set(_MARKET_CACHE["symbols"])
        if now < _MARKET_CACHE["expires"] and requested <= cached_symbols:
            return dict(_MARKET_CACHE)

        tickers = sorted(requested | cached_symbols | {"^NSEI", "^INDIAVIX"})
        try:
            import concurrent.futures
            prices = dict(_MARKET_CACHE["prices"])
            quotes = {}
            errors = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(_fetch_chart_quote, sym): sym
                           for sym in tickers}
                for future, sym in [(future, futures[future]) for future in futures]:
                    try:
                        quotes[sym] = future.result()
                    except Exception as exc:
                        errors.append(f"{sym}: {exc}")
            if not quotes:
                raise RuntimeError("; ".join(errors) or "provider returned no quotes")
            for sym in requested | cached_symbols:
                if sym in quotes and quotes[sym][0] > 0:
                    prices[sym] = quotes[sym][0]
            nifty = quotes.get("^NSEI", (None, None))[0]
            vix = quotes.get("^INDIAVIX", (None, None))[0]
            fetched_times = [value[1] for value in quotes.values() if value[1]]
            incomplete = bool(
                [sym for sym in requested if sym not in prices]
                or nifty is None or vix is None)
            _MARKET_CACHE.update({
                "expires": now + MARKET_TTL_S,
                "symbols": requested | cached_symbols,
                "prices": prices,
                "nifty": nifty,
                "vix": vix,
                "fetched_at": max(fetched_times) if fetched_times else _ist_now().isoformat(),
                "error": "; ".join(errors) or None,
                "stale": incomplete,
            })
            return dict(_MARKET_CACHE)
        except Exception as exc:
            print(f"[dashboard] market fetch error: {exc}")
            _MARKET_CACHE["error"] = str(exc)
            result = dict(_MARKET_CACHE)
            result["stale"] = True
            return result


def fetch_live_prices(symbols: list[str]) -> dict[str, float]:
    """Compatibility wrapper returning only successfully sourced prices."""
    return get_market_data(symbols)["prices"]


def fetch_nifty_vix() -> tuple[float | None, float | None]:
    market = get_market_data([])
    return market["nifty"], market["vix"]


# ╔══════════════════════════════════════════════════════════════╗
# ║  TIME HELPERS                                               ║
# ╚══════════════════════════════════════════════════════════════╝

def _ist_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata"))


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
        ts = datetime.fromisoformat(scan_time_str)
        now = datetime.now(ts.tzinfo) if ts.tzinfo else datetime.now()
        ago = max(0, (now - ts).total_seconds())
        if ago < 60:
            return f"{int(ago)}s ago"
        if ago < 3600:
            return f"{int(ago/60)}m ago"
        return f"{int(ago/3600)}h ago"
    except Exception:
        return "unknown"


def _scan_is_overdue(last_success: str | None, now: datetime | None = None) -> bool:
    """Return true only after a weekday scan deadline plus its grace period."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    latest_due = None
    for days_back in range(8):
        day = (current - timedelta(days=days_back)).date()
        if day.weekday() >= 5:
            continue
        for hour, minute in SCAN_TIMES_UTC:
            scheduled = datetime(
                day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
            if scheduled + timedelta(seconds=SCAN_GRACE_S) <= current:
                latest_due = max(latest_due, scheduled) if latest_due else scheduled
        if latest_due is not None:
            break

    if latest_due is None:
        return False
    if not last_success:
        return True
    try:
        success = datetime.fromisoformat(last_success)
        if success.tzinfo is None:
            success = success.replace(tzinfo=timezone.utc)
        return success.astimezone(timezone.utc) < latest_due
    except (TypeError, ValueError):
        return True


def _scan_run_stalled(scan_status: dict, now: datetime | None = None) -> bool:
    """Detect a RUNNING marker left behind by a killed or timed-out process."""
    if scan_status.get("status") != "RUNNING":
        return False
    started_at = scan_status.get("started_at") or scan_status.get("updated_at")
    if not started_at:
        return True
    try:
        started = datetime.fromisoformat(started_at)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return (current.astimezone(timezone.utc)
                - started.astimezone(timezone.utc)).total_seconds() > SCAN_STALLED_S
    except (TypeError, ValueError):
        return True


def _inr(v: float, cr: bool = False) -> str:
    """Format as Indian ₹ with optional lakh/crore suffix."""
    if cr and abs(v) >= 1e7:
        return f"₹{v/1e7:.2f}Cr"
    if cr and abs(v) >= 1e5:
        return f"₹{v/1e5:.2f}L"
    return f"₹{v:,.2f}"

def _fmt_metric(value: Any, spec: str, suffix: str = "") -> str:
    """Format a genuine finite number; never turn missing data into zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "UNAVAILABLE"
    if not math.isfinite(float(value)):
        return "UNAVAILABLE"
    return f"{format(float(value), spec)}{suffix}"


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
        "borderRadius" : "16px",
        "padding"      : "18px",
        "marginBottom" : "16px",
        "boxShadow"    : "0 18px 45px rgba(0,0,0,.22)",
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
            "letterSpacing": "1.2px",
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
            "fontSize"  : "21px",
            "fontWeight": "700",
            "fontFamily": MONO,
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
        "borderRadius": "14px",
        "padding"     : "15px 16px",
        "boxShadow"   : "0 12px 28px rgba(0,0,0,.18)",
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
    row_conditions = []
    column_styles = {}
    for rule in cond or []:
        selector = rule.get("if", {})
        style = {key: value for key, value in rule.items() if key != "if"}
        column_id = selector.get("column_id")
        query = selector.get("filter_query")
        if column_id and not query:
            column_styles.setdefault(column_id, {}).update(style)
            continue
        if not query:
            continue
        contains = re.fullmatch(r"\{(.+?)\}\s+contains\s+'(.*)'", query)
        equals = re.fullmatch(r"\{(.+?)\}\s*=\s*'?([^']*)'?", query)
        if contains:
            field, value = contains.groups()
            expression = (
                f"params.data && String(params.data[{json.dumps(field)}] || '')"
                f".includes({json.dumps(value)})"
            )
        elif equals:
            field, value = equals.groups()
            expression = (
                f"params.data && String(params.data[{json.dumps(field)}] || '')"
                f" === {json.dumps(value)}"
            )
        else:
            continue
        row_conditions.append({"condition": expression, "style": style})

    columns = []
    for field in rows[0]:
        definition = {
            "field": field,
            "headerName": field,
            "minWidth": 110,
            "flex": 1,
        }
        if field in column_styles:
            definition["cellStyle"] = column_styles[field]
        columns.append(definition)

    grid_options = {
        "theme": "themeQuartz",
        "pagination": len(rows) > page,
        "paginationPageSize": page,
        "paginationPageSizeSelector": False,
        "animateRows": False,
        "suppressCellFocus": True,
        "domLayout": "autoHeight",
    }
    return dag.AgGrid(
        rowData=rows,
        columnDefs=columns,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        getRowStyle={"styleConditions": row_conditions} if row_conditions else None,
        dashGridOptions=grid_options,
        columnSize="responsiveSizeToFit",
        className="be-grid",
        style={
            "width": "100%",
            "--ag-background-color": PANEL,
            "--ag-foreground-color": TEXT,
            "--ag-header-background-color": PANEL2,
            "--ag-header-foreground-color": ORANGE,
            "--ag-border-color": BORDER,
            "--ag-row-border-color": BORDER,
            "--ag-odd-row-background-color": PANEL2,
            "--ag-font-family": FONT,
            "--ag-font-size": "11px",
        },
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
    now = time.time()
    with _EARNINGS_LOCK:
        if now < _EARNINGS_CACHE["expires"]:
            return list(_EARNINGS_CACHE["rows"])
        rows = []
        errors = []
        try:
            import concurrent.futures
            import yfinance as yf
            from config.yfinance_runtime import configure_yfinance
            configure_yfinance(yf)
            watch = [s for s in STOCK_WATCHLIST if ".NS" in s][:20]
            requested = len(watch)

            def fetch_one(sym):
                try:
                    cal = yf.Ticker(sym).calendar
                    if cal is None:
                        return None
                    if hasattr(cal, "to_dict"):
                        cal = cal.to_dict()
                    date_val = (cal.get("Earnings Date") or
                                cal.get("earningsDate") or
                                cal.get("Earnings Dates", [None]))
                    if isinstance(date_val, list):
                        date_val = date_val[0] if date_val else None
                    if date_val is None:
                        return None
                    date_val = (str(date_val.date()) if hasattr(date_val, "date")
                                else str(date_val)[:10])
                    earnings_date = datetime.fromisoformat(date_val).date()
                    today = _ist_now().date()
                    if earnings_date < today or earnings_date > today + timedelta(days=180):
                        return None
                    return {
                        "Symbol": sym.replace(".NS", ""),
                        "Earnings Date": date_val,
                        "EPS Est": cal.get("EPS Estimate", "—"),
                        "Revenue Est": cal.get("Revenue Estimate", "—"),
                        "Source": "Yahoo Finance",
                        "Fetched At": _ist_now().isoformat()[:19],
                    }
                except Exception as exc:
                    errors.append(f"{sym}: {exc}")
                    return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                for result in executor.map(fetch_one, watch):
                    if result:
                        rows.append(result)
        except Exception as exc:
            errors.append(str(exc))
        rows.sort(key=lambda r: r["Earnings Date"])
        _EARNINGS_CACHE.update({
            "expires": now + 21_600,
            "rows": rows,
            "fetched_at": _ist_now().isoformat(),
            "error": "; ".join(errors[:3]) or None,
            "requested": locals().get("requested", 0),
            "verified": len(rows),
        })
        return list(rows)


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
        meta_tags=[{
            "name": "viewport",
            "content": "width=device-width, initial-scale=1, maximum-scale=1",
        }],
        update_title=None,
        suppress_callback_exceptions=True,
    )

    @app.server.get("/healthz")
    def healthz():
        """Fast local health probe with no external network dependency."""
        scan_status = load_scan_status()
        scan = load_scan()
        portfolio = load_portfolio()
        circuit = load_circuit()
        overdue = _scan_is_overdue(scan_status.get("last_success_at"))
        stalled = _scan_run_stalled(scan_status)
        storage_bad = any(value.get("_storage_status") in {"INVALID", "MISSING"}
                          for value in (portfolio, circuit, scan))
        return {
            "status": "degraded" if overdue or stalled or storage_bad else "ok",
            "service": "bharatedge-dashboard",
            "time_utc": datetime.now(timezone.utc).isoformat(),
            "last_scan_status": scan_status.get("status", "UNKNOWN"),
            "last_scan_success": scan_status.get("last_success_at"),
            "scan_overdue": overdue,
            "scan_stalled": stalled,
            "portfolio_storage": portfolio.get("_storage_status", "UNKNOWN"),
            "circuit_storage": circuit.get("_storage_status", "UNKNOWN"),
            "scan_storage": scan.get("_storage_status", "UNKNOWN"),
            "scan_signal_count": len(scan.get("signals", [])),
            "scan_universe_count": scan.get("data_quality", {}).get("universe_count"),
            "scan_price_history_count": scan.get("data_quality", {}).get("price_history_count"),
        }, 200

    # ── Google Font + global CSS ──────────────────────────────
    app.index_string = (
        "<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>"
        "{%favicon%}{%css%}"
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&display=swap' rel='stylesheet'>"
        "<style>"
        f"*{{margin:0;padding:0;box-sizing:border-box}}"
        f"body{{background:radial-gradient(circle at 82% -8%,#163651 0,{BG} 38%);color:{TEXT};font-family:{FONT};letter-spacing:-.01em}}"
        "button{font-family:inherit;transition:.2s ease}button:hover{transform:translateY(-1px);filter:brightness(1.15)}"
        ".be-tabs{display:flex!important;flex-direction:row!important;flex-wrap:nowrap!important;overflow-x:auto;overflow-y:hidden;white-space:nowrap;height:58px!important}.be-tab{display:flex!important;align-items:center;justify-content:center;width:140px!important;min-width:140px!important;max-width:140px!important;height:42px!important;min-height:42px!important;flex:0 0 140px!important}"
        ".be-status{overflow-x:auto;white-space:nowrap}"
        ".be-kpis{display:grid;grid-template-columns:repeat(7,minmax(145px,1fr));gap:12px}"
        ".be-charts{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:14px}"
        ".be-history-kpis{display:grid;grid-template-columns:repeat(6,minmax(145px,1fr));gap:10px}"
        ".be-two-col{display:grid;grid-template-columns:1fr 1fr;gap:14px}"
        "@media(max-width:900px){.be-kpis,.be-history-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.be-charts,.be-two-col{grid-template-columns:1fr}.be-title-sub{display:none}}"
        "@media(max-width:800px){.be-kpis,.be-history-kpis{grid-template-columns:1fr}#topbar-right{display:none}.be-status{padding-left:10px!important}}"
        "@media(max-width:520px){.be-kpis,.be-history-kpis{grid-template-columns:1fr}.be-shell{padding-left:8px!important;padding-right:8px!important}.be-top{padding:10px!important}#topbar-right{display:none}.be-status{padding-left:10px!important}.be-tab{width:125px!important;min-width:125px!important;flex-basis:125px!important}}"
        "::-webkit-scrollbar{width:5px;height:5px}"
        f"::-webkit-scrollbar-track{{background:{BG}}}"
        f"::-webkit-scrollbar-thumb{{background:{BORDER};border-radius:2px}}"
        f".tab--selected{{color:{TEXT}!important;background:#19334a!important;border-color:{ORANGE}55!important;box-shadow:inset 0 0 0 1px {ORANGE}33!important}}"
        ".be-grid{border-radius:12px;overflow:hidden}"
        ".dash-table-container .row{margin:0}"
        "@keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}"
        "</style></head><body>{%app_entry%}"
        "<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"
    )

    # ── Top status bar ────────────────────────────────────────
    status_bar = html.Div(id="status-bar", className="be-status", style={
        "background"  : "rgba(10,24,40,.94)",
        "borderBottom": f"1px solid {BORDER}",
        "padding"     : "6px 20px",
        "display"     : "flex",
        "alignItems"  : "center",
        "gap"         : "24px",
        "fontSize"    : "11px",
        "fontFamily"  : MONO,
        "position"    : "sticky",
        "top"         : "0",
        "zIndex"      : "1000",
    })

    # ── Tab styles ────────────────────────────────────────────
    TAB_STYLE = {
        "background"  : "transparent",
        "color"       : DIM,
        "border"      : f"1px solid {BORDER}",
        "borderRadius": "10px",
        "padding"     : "10px 16px",
        "margin"      : "7px 4px",
        "fontFamily"  : FONT,
        "fontSize"    : "10px",
        "fontWeight"  : "600",
        "letterSpacing": ".7px",
    }
    TAB_SEL = {
        **TAB_STYLE,
        "color"      : ORANGE,
        "border"     : f"1px solid {ORANGE}66",
        "background" : "#19334a",
    }

    # ── Main layout ───────────────────────────────────────────
    app.layout = html.Div(style={"backgroundColor": BG, "minHeight": "100vh"}, children=[
        dcc.Interval(id="iv", interval=REFRESH_S * 1000, n_intervals=0),

        # Title bar
        html.Div(className="be-top", style={
            "background"  : "rgba(8,20,34,.96)",
            "borderBottom": f"1px solid {BORDER}",
            "padding"     : "15px 20px",
            "display"     : "flex",
            "justifyContent": "space-between",
            "alignItems"  : "center",
        }, children=[
            html.Div([
                html.Span("BHARAT", style={"color": ORANGE, "fontWeight": "700",
                                           "fontSize": "19px", "letterSpacing": "1px"}),
                html.Span("EDGE", style={"color": TEXT, "fontWeight": "700",
                                         "fontSize": "19px", "letterSpacing": "1px"}),
                html.Span(" TERMINAL", className="be-title-sub", style={"color": DIM, "fontSize": "11px",
                                              "letterSpacing": "2px", "marginLeft": "10px"}),
            ]),
            html.Div([
                html.Button("↻ REFRESH DATA", id="refresh-now", n_clicks=0, style={
                    "background": "linear-gradient(135deg,#1d4058,#163047)", "color": TEXT,
                    "border": f"1px solid {ORANGE}66", "borderRadius": "8px",
                    "padding": "8px 12px", "fontSize": "10px", "fontWeight": "700",
                    "cursor": "pointer", "marginRight": "12px",
                }),
                html.Span(id="topbar-right", style={"fontSize": "11px", "color": DIM}),
            ], style={"display": "flex", "alignItems": "center"}),
        ]),

        # Status bar
        status_bar,

        # Tabs
        html.Div(className="be-shell", style={"padding": "0 16px"}, children=[
            dcc.Tabs(id="tabs", className="be-tabs", value="overview", style={
                "borderBottom": f"1px solid {BORDER}",
                "fontFamily"  : FONT,
            }, children=[
                dcc.Tab(label="01 OVERVIEW", className="be-tab", value="overview",
                        style=TAB_STYLE, selected_style=TAB_SEL),
                dcc.Tab(label="02 POSITIONS", className="be-tab", value="positions",
                        style=TAB_STYLE, selected_style=TAB_SEL),
                dcc.Tab(label="03 SIGNALS", className="be-tab", value="signals",
                        style=TAB_STYLE, selected_style=TAB_SEL),
                dcc.Tab(label="04 SECTORS", className="be-tab", value="sectors",
                        style=TAB_STYLE, selected_style=TAB_SEL),
                dcc.Tab(label="05 EARNINGS", className="be-tab", value="earnings",
                        style=TAB_STYLE, selected_style=TAB_SEL),
                dcc.Tab(label="06 HISTORY", className="be-tab", value="history",
                        style=TAB_STYLE, selected_style=TAB_SEL),
                dcc.Tab(label="07 SYS CONFIG", className="be-tab", value="sysconfig",
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
            html.Span(f"Auto-refresh: {REFRESH_S}s  ·  Market data: Yahoo Finance"),
        ]),
    ])

    # ─────────────────────────────────────────────────────────
    # CALLBACK: status bar + topbar (every refresh)
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("status-bar",   "children"),
        Output("topbar-right", "children"),
        Input("iv", "n_intervals"),
        Input("refresh-now", "n_clicks"),
    )
    def update_status(_n, _clicks):
        try:
            port    = load_portfolio()
            scan    = load_scan()
            scan_status = load_scan_status()
            circuit = load_circuit()
            ist     = _ist_now()
            mkt_open = _is_market_open()
            regime  = scan.get("market_regime", {})
            quality = scan.get("data_quality", {})
            market  = get_market_data(list(port.get("positions", {}).keys()))

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
            live_prices = (market.get("prices", {})
                           if not market.get("stale") else {})
            valuation_available = not pos or all(sym in live_prices for sym in pos)
            pos_val = (sum(p["shares"] * live_prices[sym]
                           for sym, p in pos.items())
                       if valuation_available else None)
            total = capital + pos_val if pos_val is not None else None
            pnl = total - start if total is not None else None
            pnl_col = GREEN if pnl is not None and pnl >= 0 else RED
            regime_name = regime.get("regime", "UNKNOWN")

            cb_triggered = circuit.get("triggered", False)
            cb_color     = RED if cb_triggered else GREEN
            cb_text      = "CB: TRIGGERED" if cb_triggered else "CB: OK"
            portfolio_storage = port.get("_storage_status", "UNKNOWN")

            scan_age = _scan_age(scan.get("scan_time"))
            coverage = float(quality.get("price_coverage", 0) or 0)
            entries_blocked = bool(quality.get("new_entries_blocked", False))
            context_status = quality.get("market_context", {}).get("status", "UNKNOWN")
            run_status = scan_status.get("status", "UNKNOWN")
            scan_overdue = _scan_is_overdue(scan_status.get("last_success_at"))
            scan_stalled = _scan_run_stalled(scan_status)
            if run_status == "FAILED":
                quality_label, quality_color = "SCAN FAILED", RED
            elif scan_stalled:
                quality_label, quality_color = "SCAN STALLED", RED
            elif run_status == "RUNNING":
                quality_label, quality_color = "SCANNING", YELLOW
            elif scan_overdue:
                quality_label, quality_color = "SCAN OVERDUE", RED
            elif entries_blocked:
                quality_label, quality_color = "ENTRY BLOCKED", RED
            elif context_status == "DEGRADED" or coverage < 1:
                quality_label, quality_color = "DEGRADED", YELLOW
            else:
                quality_label, quality_color = "VALID", GREEN

            items = [
                (dot, mkt_label, dot_color),
            ]

            bar = [
                dot,
                html.Span(mkt_label, style={"color": dot_color,
                          "fontWeight": "700", "marginRight": "20px"}),
                html.Span("NIFTY: ", style={"color": DIM}),
                html.Span(
                    f"{market['nifty']:,.2f}" if market.get("nifty") else "UNAVAILABLE",
                    style={"color": TEXT if market.get("nifty") else RED,
                           "marginRight": "20px"}),
                html.Span("VIX: ", style={"color": DIM}),
                html.Span(
                    f"{market['vix']:.2f}" if market.get("vix") else "UNAVAILABLE",
                    style={"color": YELLOW if market.get("vix") else RED,
                           "marginRight": "20px"}),
                html.Span("REGIME: ", style={"color": DIM}),
                html.Span(regime_name, style={"color": _regime_color(regime_name),
                          "fontWeight": "700", "marginRight": "20px"}),
                html.Span("VALUE: ", style={"color": DIM}),
                html.Span(_inr(total) if total is not None else "UNAVAILABLE",
                          style={"color": TEXT if total is not None else RED,
                                 "marginRight": "20px"}),
                html.Span("P&L: ", style={"color": DIM}),
                html.Span((f"{'+' if pnl >= 0 else ''}{_inr(pnl)}"
                           if pnl is not None else "UNAVAILABLE"), style={
                    "color": pnl_col, "fontWeight": "700", "marginRight": "20px"}),
                html.Span(cb_text, style={"color": cb_color, "fontWeight": "700", "marginRight": "20px"}),
                html.Span(
                    "PORTFOLIO DATA INVALID",
                    style={"color": RED, "fontWeight": "700", "marginRight": "20px"},
                ) if portfolio_storage == "INVALID" else html.Span(),
                html.Span("LAST SCAN: ", style={"color": DIM}),
                html.Span(scan_age, style={"color": TEXT}),
                html.Span("  SCAN QUALITY: ", style={"color": DIM, "marginLeft": "20px"}),
                html.Span(
                    quality_label,
                    title=(f"Coverage {coverage:.0%} · Context {context_status}"
                           + (f" · {scan_status.get('error')}" if scan_status.get('error') else "")),
                    style={"color": quality_color, "fontWeight": "700"}),
                html.Span("  DATA: ", style={"color": DIM, "marginLeft": "20px"}),
                html.Span(
                    "STALE" if market.get("stale") else "LIVE/CLOSE",
                    title=(f"Yahoo Finance · {market.get('fetched_at') or 'never'}"
                           + (f" · {market.get('error')}" if market.get('error') else "")),
                    style={"color": RED if market.get("stale") else GREEN,
                           "fontWeight": "700"}),
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
        Input("refresh-now",  "n_clicks"),
    )
    def render_tab(tab, _n, _clicks):
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

    syms = list(pos.keys())
    market = get_market_data(syms)
    live = market.get("prices", {}) if not market.get("stale") else {}
    for sym, p in pos.items():
        lp = live.get(sym)
        if lp and lp > 0:
            p["current_price"] = lp

    valuation_available = not pos or all(sym in live for sym in pos)
    pos_val = (sum(p["shares"] * live[sym] for sym, p in pos.items())
               if valuation_available else None)
    total = capital + pos_val if pos_val is not None else None
    pnl = total - start if total is not None else None
    pnl_pct = pnl / start * 100 if pnl is not None and start else None
    pnl_col = GREEN if pnl is not None and pnl >= 0 else RED

    sells    = [t for t in history if t.get("action") == "SELL"]
    wins     = sum(1 for t in sells if t.get("pnl", 0) > 0)
    losses   = len(sells) - wins
    wr       = wins / len(sells) * 100 if sells else 0
    wr_col   = GREEN if wr >= 50 else RED
    realized = sum(t.get("pnl", 0) for t in sells)
    unrealized = pnl - realized if pnl is not None else None

    pf       = summary.get("profit_factor", 0)
    avg_win  = summary.get("avg_win", 0)
    avg_loss = summary.get("avg_loss", 0)

    sg = lambda v: "+" if v >= 0 else ""

    # KPI row
    kpis = html.Div(className="be-kpis", style={
        "marginBottom": "14px",
    }, children=[
        _kpi("Total Value",   _inr(total) if total is not None else "UNAVAILABLE",
             ORANGE if total is not None else RED,
             f"Start: {_inr(start)}"),
        _kpi("Cash",          _inr(capital),  BLUE,
             (f"{capital/total*100:.1f}% of portfolio"
              if total else "Valuation unavailable")),
        _kpi("Total P&L", (f"{sg(pnl)}{_inr(pnl)}" if pnl is not None else "UNAVAILABLE"),
             pnl_col, ((f"Realized {sg(realized)}{_inr(realized)} · "
                        f"Open {sg(unrealized)}{_inr(unrealized)}")
                       if unrealized is not None else "Needs fresh quotes")),
        _kpi("Realized P&L",  f"{sg(realized)}{_inr(realized)}",
             GREEN if realized >= 0 else RED,
             f"{len(sells)} closed trades"),
        _kpi("Open Positions", str(len(pos)), YELLOW, "Max 5"),
        _kpi("Win Rate",      f"{wr:.0f}%" if sells else "N/A",  wr_col, f"{wins}W  {losses}L"),
        _kpi("Profit Factor", f"{pf:.2f}" if sells else "N/A",   GREEN if sells and pf >= 1 else RED,
             f"W:{_inr(avg_win)} / L:{_inr(avg_loss)}"),
    ])

    # Equity curve
    equity = [p for p in load_equity_history()
              if p.get("timestamp") and isinstance(p.get("total_value"), (int, float))]
    if len(equity) >= 2:
        eq_vals = [p["total_value"] for p in equity]
        eq_dates = [p["timestamp"] for p in equity]
        ec = GREEN if eq_vals[-1] >= eq_vals[0] else RED
        fig = go.Figure(go.Scatter(x=eq_dates, y=eq_vals, mode="lines+markers",
            line=dict(color=ec, width=2), fill="tozeroy", fillcolor=_rgba(ec, 0.094),
            marker=dict(size=4, color=ec),
            hovertemplate="%{x}<br>₹%{y:,.0f}<extra></extra>"))
        fig.update_layout(**_dark_fig(280))
        fig.update_yaxes(tickprefix="₹", tickformat=",.0f")
    else:
        fig = _empty_fig("Equity history starts after two successful scans", 280)

    # Allocation donut
    al_labels = ["Cash"] + syms if valuation_available else []
    al_vals = ([round(capital, 2)]
               + [round(p["shares"] * live[sym], 2) for sym, p in pos.items()]
               if valuation_available else [])
    pie_colors = [BLUE, ORANGE, GREEN, YELLOW, CYAN, PURPLE, RED, ORANGE2]

    pie = (go.Figure(go.Pie(
        labels=al_labels, values=al_vals, hole=0.6,
        marker=dict(colors=pie_colors[:len(al_labels)],
                    line=dict(color=BG, width=2)),
        textfont=dict(color=TEXT, size=11, family=FONT),
        hovertemplate="%{label}<br>₹%{value:,.0f}<br>%{percent}<extra></extra>",
    )) if valuation_available else _empty_fig("Fresh quotes required", 280))
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
        html.Div(
            f"Market data: Yahoo Finance · as of {market.get('fetched_at') or 'unavailable'}"
            f" · {'STALE — cached portfolio prices excluded' if market.get('stale') else 'current provider snapshot'}",
            style={"color": RED if market.get("stale") else DIM,
                   "fontFamily": FONT, "fontSize": "10px", "marginBottom": "10px"}),
        kpis,
        html.Div(className="be-charts", style={"marginBottom": "14px"}, children=[
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
    market = get_market_data(syms)
    live = market.get("prices", {}) if not market.get("stale") else {}

    rows = []
    for sym, p in pos.items():
        entry   = p.get("entry_price", 0)
        is_live = sym in live
        curr = live.get(sym)
        if is_live:
            p["current_price"] = curr
        shares  = p.get("shares", 0)
        cost    = p.get("cost", entry * shares)
        upnl = (curr - entry) * shares if is_live else None
        upct = ((curr - entry) / entry * 100
                if is_live and entry else None)
        sl_pct  = p.get("stop_loss_pct", 0.04)
        sl_px   = entry * (1 - sl_pct)
        highest = p.get("highest_price")
        trail = ((highest - curr) / highest * 100
                 if is_live and highest else None)
        sig     = p.get("signal", 0)
        sector  = p.get("reason", "—")

        rows.append({
            "Symbol"    : sym.replace(".NS", ""),
            "Sector"    : sector,
            "Shares"    : shares,
            "Entry ₹"   : f"{entry:,.2f}",
            "Current ₹" : f"{curr:,.2f}" if is_live else "UNAVAILABLE",
            "Cost ₹"    : f"{cost:,.2f}",
            "Unreal P&L": (f"{'+' if upnl >= 0 else ''}{upnl:,.2f}"
                           if upnl is not None else "UNAVAILABLE"),
            "Chg %"     : (f"{'+' if upct >= 0 else ''}{upct:.2f}%"
                           if upct is not None else "UNAVAILABLE"),
            "Stop ₹"    : f"{sl_px:,.2f}",
            "Trail %"   : f"{trail:.2f}%" if trail is not None else "UNAVAILABLE",
            "AI Score"  : f"{sig:.3f}",
            "Entry Date": p.get("entry_date", "")[:10],
            "Price Status": "PROVIDER" if is_live else "UNAVAILABLE",
            "Price As Of": ((market.get("fetched_at") or "—")[:19]
                            if is_live else "—"),
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
    status = "PROVIDER SNAPSHOT" if not market.get("stale") else "LIVE VALUES UNAVAILABLE"
    return _section(f"OPEN POSITIONS — {status}", _dtable(rows, cond, page=10))


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
            html.Span(_fmt_metric(regime.get('vix'), ".1f"),
                      style={"color": YELLOW if regime.get('vix') is not None else RED, "fontWeight": "700",
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
        price = s.get("price")
        price_valid = isinstance(price, (int, float)) and price > 0
        rows.append({
            "Symbol"       : s.get("symbol", "").replace(".NS", ""),
            "Signal"       : sig,
            "AI Score"     : _fmt_metric(s.get("confidence"), ".3f"),
            "Price ₹"      : f"{price:,.2f}" if price_valid else "UNAVAILABLE",
            "Price Source" : s.get("price_source", "UNAVAILABLE") if price_valid else "UNAVAILABLE",
            "Price As Of"  : (s.get("price_as_of") or "—")[:19] if price_valid else "—",
            "Model"        : (s.get("model_manifest") or "UNAVAILABLE")[:12],
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
    snapshot = scan.get("sectors", [])

    if snapshot:
        rows = [{
            "Sector": item.get("sector", "UNKNOWN"),
            "Status": item.get("status", "NEUTRAL"),
            "Score": _fmt_metric(item.get("score"), ".2f"),
            "1W %": _fmt_metric(item.get("momentum_1w"), "+.2f", "%"),
            "1M %": _fmt_metric(item.get("momentum_1m"), "+.2f", "%"),
            "3M %": _fmt_metric(item.get("momentum_3m"), "+.2f", "%"),
            "RS vs Nifty": _fmt_metric(item.get("relative_strength"), "+.2f", "%"),
            "Trend": _fmt_metric(item.get("trend_score"), ".1f"),
            "Allocation": _fmt_metric(item.get("allocation_multiplier"), ".2f", "×"),
            "Source": item.get("source", "UNAVAILABLE"),
        } for item in snapshot]
    else:
        rows = []

    # Compatibility fallback for older scan files that predate sector snapshots.
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
    if not rows:
        for sec, d in sorted(sector_data.items()):
            sigs = d["signals"]
            buys = sum(1 for x in sigs if "BUY" in x)
            sells = sum(1 for x in sigs if "SELL" in x or x == "AVOID")
            avg = sum(d["scores"]) / len(d["scores"]) if d["scores"] else 0
            status = d["status"]
            rows.append({
                "Sector": sec,
                "Status": status,
                "Score": f"{avg * 100:.2f}",
                "BUY Sigs": buys,
                "SELL Sigs": sells,
                "Total": len(sigs),
                "Outlook": ("BULLISH" if buys > sells else
                            "BEARISH" if sells > buys else "NEUTRAL"),
                "Source": "Derived from qualifying signals",
            })

    # Bar chart of avg scores
    if rows:
        sectors = [r["Sector"] for r in rows]
        chart_rows = [r for r in rows if r.get("Score") != "UNAVAILABLE"]
        sectors = [r["Sector"] for r in chart_rows]
        scores  = [float(r["Score"]) for r in chart_rows]
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
        bar_fig.update_yaxes(range=[0, 100], tickformat=".0f")
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
        html.Div(
            f"Sector snapshot as of {scan.get('scan_time') or 'unavailable'} · "
            "Values are computed from provider market data; unavailable data is not fabricated.",
            style={"color": DIM, "fontSize": "11px", "marginBottom": "12px"},
        ),
        _section("SECTOR MOMENTUM SCORES", chart),
        _section("SECTOR ROTATION TABLE", _dtable(rows, cond, page=15)),
    ])


# ╔══════════════════════════════════════════════════════════════╗
# ║  TAB 5: EARNINGS                                            ║
# ╚══════════════════════════════════════════════════════════════╝

def _tab_earnings() -> html.Div:
    rows = _upcoming_earnings()

    if not rows:
        rows = [{"Status": "No provider-verified upcoming earnings dates are currently available."}]

    now_date = _ist_now().strftime("%Y-%m-%d")
    cond = [
        {"if": {"filter_query": f"{{Earnings Date}} = '{now_date}'"},
         "backgroundColor": ORANGE + "22", "color": ORANGE, "fontWeight": "700"},
        {"if": {"column_id": "Symbol"}, "color": ORANGE, "fontWeight": "700"},
    ]
    return _section("NSE EARNINGS CALENDAR", html.Div([
        html.Div(
            f"Today: {now_date} · Yahoo Finance · verified "
            f"{_EARNINGS_CACHE.get('verified', 0)}/{_EARNINGS_CACHE.get('requested', 0)} tracked symbols"
            f" · fetched {_EARNINGS_CACHE.get('fetched_at') or 'not yet'}"
            + (f" · provider errors: {_EARNINGS_CACHE.get('error')}" if _EARNINGS_CACHE.get('error') else ""),
            style={"color": RED if _EARNINGS_CACHE.get("error") else DIM,
                   "fontSize": "11px", "fontFamily": FONT, "marginBottom": "12px"}),
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

    kpis = html.Div(className="be-history-kpis", style={
        "marginBottom": "14px",
    }, children=[
        _kpi("Total Trades", str(wins + losses), ORANGE),
        _kpi("Win Rate",     f"{wr:.0f}%" if wins + losses else "N/A", wr_col, f"{wins}W  {losses}L"),
        _kpi("Total P&L",    f"{_inr(tot_pnl)}",  pnl_col),
        _kpi("Profit Factor",f"{pf:.2f}" if wins + losses else "N/A", GREEN if wins + losses and pf >= 1 else RED),
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
    quality = scan.get("data_quality", {})

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
        ("Daily Limit",     f"{cfg.MAX_DAILY_LOSS*100:.0f}%",  RED),
        ("Weekly Limit",    f"{cfg.MAX_WEEKLY_LOSS*100:.0f}%", RED),
        ("Total Limit",     f"{cfg.MAX_DRAWDOWN*100:.0f}%", RED),
    ]

    # Scan state
    scan_cfg = [
        ("Last Scan",       scan.get("scan_time", "Never")[:19] if scan.get("scan_time") else "Never", TEXT),
        ("Signals Found",   len(scan.get("signals", [])), ORANGE),
        ("Universe Symbols", quality.get("universe_count", "UNAVAILABLE"), TEXT),
        ("Price Histories", quality.get("price_history_count", "UNAVAILABLE"), TEXT),
        ("Regime",          scan.get("market_regime",{}).get("regime","--"), TEXT),
        ("VIX",             _fmt_metric(scan.get('market_regime',{}).get('vix'), ".1f"), YELLOW),
        ("Can Trade",       scan.get("market_regime",{}).get("can_trade","--"), TEXT),
        ("Price Coverage",  f"{float(quality.get('price_coverage', 0) or 0):.0%}", TEXT),
        ("Context Quality", quality.get("market_context", {}).get("status", "UNKNOWN"),
         YELLOW if quality.get("market_context", {}).get("status") == "DEGRADED" else TEXT),
        ("Entries Blocked", quality.get("new_entries_blocked", "--"),
         RED if quality.get("new_entries_blocked") else TEXT),
    ]

    return html.Div([
        html.Div(className="be-two-col", children=[
            _section("MARKET & STRATEGY SETTINGS", _table(market_cfg)),
            html.Div([
                _section("PORTFOLIO STATE",    _table(port_cfg)),
                _section("CIRCUIT BREAKER",    _table(cb_cfg)),
                _section("LAST SCAN STATE",    _table(scan_cfg)),
            ]),
        ]),
    ])
