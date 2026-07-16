# phase9_zerodha.py
# BHARAT EDGE - Phase 9A: Zerodha Kite Connection
# Handles login, authentication and order placement

import os
import sys
import time
import pyotp
import requests
import hashlib
from datetime import datetime
from kiteconnect import KiteConnect

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env loaded")
except:
    pass

# ============================================================
# CREDENTIALS
# ============================================================
API_KEY     = os.environ.get('KITE_API_KEY', '')
API_SECRET  = os.environ.get('KITE_API_SECRET', '')
USER_ID     = os.environ.get('KITE_USER_ID', '')
PASSWORD    = os.environ.get('KITE_PASSWORD', '')
PIN         = os.environ.get('KITE_PIN', '')
TOTP_SECRET = os.environ.get('KITE_TOTP_SECRET', '')

# Token storage file
TOKEN_FILE  = "kite_token.txt"

print("✅ phase9_zerodha.py loaded")


# ============================================================
# SECTION 1: TOTP
# ============================================================

def get_totp() -> str:
    """Generate current TOTP code."""
    try:
        totp = pyotp.TOTP(TOTP_SECRET)
        code = totp.now()
        print(f"  ✅ TOTP generated: {code}")
        return code
    except Exception as e:
        print(f"  ❌ TOTP error: {e}")
        return ""


# ============================================================
# SECTION 2: SAVE / LOAD TOKEN
# ============================================================

def save_token(access_token: str):
    """Save access token to file."""
    today = datetime.now().strftime('%Y-%m-%d')
    with open(TOKEN_FILE, 'w') as f:
        f.write(f"{access_token}\n{today}")
    print(f"  ✅ Token saved for {today}")


def load_token() -> str:
    """Load today's token if available."""
    try:
        if not os.path.exists(TOKEN_FILE):
            return ""
        with open(TOKEN_FILE, 'r') as f:
            lines = f.read().strip().split('\n')
        if len(lines) < 2:
            return ""
        saved_token = lines[0].strip()
        saved_date  = lines[1].strip()
        today       = datetime.now().strftime('%Y-%m-%d')
        if saved_date == today and saved_token:
            return saved_token
        return ""
    except:
        return ""


# ============================================================
# SECTION 3: AUTO LOGIN
# ============================================================

def start_local_server():
    """Start a local server to catch the redirect token."""
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse, parse_qs

    captured = {'token': None}

    class TokenHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                token  = params.get(
                    'request_token', [None])[0]
                if token:
                    captured['token'] = token
                    self.send_response(200)
                    self.send_header(
                        'Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(b"""
                    <html><body style='background:#0a0e1a;
                    color:#00ff88;font-family:sans-serif;
                    text-align:center;padding:50px;'>
                    <h1>✅ BHARAT EDGE</h1>
                    <h2>Login Successful!</h2>
                    <p>You can close this window.</p>
                    </body></html>
                    """)
                else:
                    self.send_response(200)
                    self.end_headers()
            except:
                pass

        def log_message(self, format, *args):
            pass  # Suppress server logs

    server = HTTPServer(('127.0.0.1', 80), TokenHandler)
    server.timeout = 60

    def run():
        server.handle_request()

    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()

    return server, captured


def auto_login() -> KiteConnect:
    """
    Automatically login to Zerodha Kite.
    Returns authenticated KiteConnect instance.
    """
    print("\n" + "="*50)
    print("  BHARAT EDGE - ZERODHA LOGIN")
    print("="*50)

    # Validate credentials
    if not all([API_KEY, API_SECRET,
                USER_ID, PASSWORD, TOTP_SECRET]):
        print("  ❌ Missing credentials in .env!")
        return None

    kite = KiteConnect(api_key=API_KEY)

    # Try saved token first
    saved_token = load_token()
    if saved_token:
        print("  ✅ Found saved token for today")
        kite.set_access_token(saved_token)
        try:
            profile = kite.profile()
            print(f"  ✅ Logged in as: "
                  f"{profile['user_name']}")
            return kite
        except:
            print("  ⚠️ Saved token expired."
                  " Re-logging in...")

    # Fresh login
    print("  🔐 Performing fresh login...")

    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64;'
                ' x64) AppleWebKit/537.36 (KHTML, like'
                ' Gecko) Chrome/120.0.0.0 Safari/537.36'
            ),
            'X-Kite-Version': '3',
        })

        # Step 1: Password login
        print("  📝 Step 1: Password login...")
        resp1 = session.post(
            "https://kite.zerodha.com/api/login",
            data={
                "user_id" : USER_ID,
                "password": PASSWORD,
            },
            timeout=30,
        )
        data1 = resp1.json()

        if data1.get('status') != 'success':
            print(f"  ❌ Login failed: "
                  f"{data1.get('message')}")
            return None

        request_id = data1['data']['request_id']
        print("  ✅ Step 1 done!")

        # Step 2: TOTP
        print("  📝 Step 2: TOTP 2FA...")
        time.sleep(1)
        totp_code = get_totp()
        if not totp_code:
            return None

        resp2 = session.post(
            "https://kite.zerodha.com/api/twofa",
            data={
                "user_id"     : USER_ID,
                "request_id"  : request_id,
                "twofa_value" : totp_code,
                "twofa_type"  : "totp",
                "skip_session": "",
            },
            timeout=30,
        )
        data2 = resp2.json()

        if data2.get('status') != 'success':
            print(f"  ❌ 2FA failed: "
                  f"{data2.get('message')}")
            return None

        print("  ✅ Step 2 done!")

        # Step 3: Get request token
        print("  📝 Step 3: Getting request token...")
        time.sleep(1)

        request_token = None

        # Method 1: Try with allow_redirects=False
        try:
            connect_url = (
                f"https://kite.zerodha.com/connect/login"
                f"?v=3&api_key={API_KEY}"
            )
            resp3 = session.get(
                connect_url,
                allow_redirects=False,
                timeout=30,
            )
            loc = resp3.headers.get('location', '')
            print(f"  📍 Location: {loc[:80]}")
            if 'request_token=' in loc:
                request_token = (
                    loc.split('request_token=')[1]
                       .split('&')[0].strip()
                )
        except Exception as e3:
            err = str(e3)
            print(f"  ⚠️ Method 1 error: {err[:50]}")
            # Extract from error string
            if 'request_token=' in err:
                try:
                    part = err.split(
                        'request_token=')[1]
                    for d in [' ','&',"'",'"',
                              ')','(','\n']:
                        part = part.split(d)[0]
                    request_token = part.strip()
                    print(f"  ✅ Token from error!")
                except:
                    pass

        # Method 2: Start local server
        if not request_token:
            print("  📝 Method 2: Local server...")
            try:
                server, captured = start_local_server()
                connect_url = (
                    f"https://kite.zerodha.com"
                    f"/connect/login"
                    f"?v=3&api_key={API_KEY}"
                )
                try:
                    session.get(
                        connect_url,
                        allow_redirects=True,
                        timeout=10,
                    )
                except:
                    pass
                # Wait for token
                for _ in range(30):
                    if captured['token']:
                        break
                    time.sleep(0.5)
                request_token = captured.get('token')
                if request_token:
                    print(f"  ✅ Token from server!")
            except Exception as e_srv:
                print(f"  ⚠️ Server method: {e_srv}")

        # Method 3: Manual input
        if not request_token:
            print("\n  ⚠️ Auto methods failed!")
            print("  📋 MANUAL METHOD:")
            print(f"\n  Open this URL in browser:")
            login_url = kite.login_url()
            print(f"  {login_url}")
            print(f"\n  After login copy the")
            print(f"  request_token from URL and")
            print(f"  paste below:")
            print()
            request_token = input(
                "  request_token: "
            ).strip()

            if not request_token:
                print("  ❌ No token!")
                return None

        print(f"  ✅ Step 3 done! "
              f"Token: {request_token[:8]}...")

        # Step 4: Generate access token
        print("  📝 Step 4: Access token...")
        time.sleep(1)

        session_data = kite.generate_session(
            request_token,
            api_secret=API_SECRET,
        )
        access_token = session_data['access_token']
        kite.set_access_token(access_token)
        save_token(access_token)

        # Verify
        profile = kite.profile()
        print(f"\n  ✅ LOGIN SUCCESSFUL!")
        print(f"  👤 Name  : {profile['user_name']}")
        print(f"  📧 Email : {profile['email']}")
        print(f"  🏦 Broker: {profile['broker']}")

        return kite

    except Exception as e:
        print(f"  ❌ Login error: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============================================================
# SECTION 4: ACCOUNT INFO
# ============================================================

def get_account_info(kite: KiteConnect) -> dict:
    """Get account balance and margins."""
    try:
        margins   = kite.margins()
        equity    = margins.get('equity', {})
        available = float(
            equity.get('available', {})
                  .get('live_balance', 0)
        )
        used      = float(
            equity.get('utilised', {})
                  .get('debits', 0)
        )
        total     = available + used

        info = {
            'available': round(available, 2),
            'used'     : round(used, 2),
            'total'    : round(total, 2),
        }

        print(f"\n  💰 ACCOUNT BALANCE")
        print(f"  {'─'*30}")
        print(f"  Total     : Rs {total:,.2f}")
        print(f"  Available : Rs {available:,.2f}")
        print(f"  Used      : Rs {used:,.2f}")

        return info

    except Exception as e:
        print(f"  ❌ Account info error: {e}")
        return {}


# ============================================================
# SECTION 5: GET POSITIONS
# ============================================================

def get_positions(kite: KiteConnect) -> dict:
    """Get current open positions."""
    try:
        positions = kite.positions()
        net       = positions.get('net', [])
        open_pos  = [p for p in net
                     if p['quantity'] != 0]

        print(f"\n  📊 OPEN POSITIONS: {len(open_pos)}")
        if open_pos:
            for p in open_pos:
                pnl   = p.get('pnl', 0)
                emoji = "✅" if pnl >= 0 else "❌"
                print(f"  {emoji} {p['tradingsymbol']}: "
                      f"Qty={p['quantity']} "
                      f"PnL=Rs {pnl:+,.2f}")
        else:
            print("  No open positions.")

        return {
            'net'  : net,
            'open' : open_pos,
            'count': len(open_pos),
        }

    except Exception as e:
        print(f"  ❌ Positions error: {e}")
        return {}


# ============================================================
# SECTION 6: GET HOLDINGS
# ============================================================

def get_holdings(kite: KiteConnect) -> list:
    """Get current holdings."""
    try:
        holdings = kite.holdings()
        print(f"\n  📦 HOLDINGS: {len(holdings)}")
        for h in holdings:
            pnl   = h.get('pnl', 0)
            emoji = "✅" if pnl >= 0 else "❌"
            print(f"  {emoji} {h['tradingsymbol']}: "
                  f"Qty={h['quantity']} "
                  f"Avg=Rs {h['average_price']:,.2f} "
                  f"PnL=Rs {pnl:+,.2f}")
        return holdings
    except Exception as e:
        print(f"  ❌ Holdings error: {e}")
        return []


# ============================================================
# SECTION 7: GET LIVE QUOTE (Using yfinance)
# ============================================================

def get_quote(kite: KiteConnect,
              symbol: str) -> dict:
    """Get live quote using yfinance (free)."""
    try:
        import yfinance as yf

        # Convert symbol format
        yf_symbol = symbol.replace(
            '.NS', '').upper() + '.NS'

        ticker = yf.Ticker(yf_symbol)
        info   = ticker.fast_info

        price  = float(info.last_price)
        high   = float(info.day_high)
        low    = float(info.day_low)
        open_  = float(info.open)
        volume = int(info.three_month_average_volume)
        prev   = float(info.previous_close)
        change = round(price - prev, 2)
        pct    = round((change / prev) * 100, 2)

        print(f"  📈 {yf_symbol}: Rs {price:,.2f} "
              f"({change:+.2f} / {pct:+.2f}%)")

        return {
            'symbol': yf_symbol,
            'price' : price,
            'change': change,
            'pct'   : pct,
            'high'  : high,
            'low'   : low,
            'open'  : open_,
            'prev'  : prev,
            'volume': volume,
        }

    except Exception as e:
        print(f"  ❌ Quote error {symbol}: {e}")
        return {}


def get_multiple_quotes(symbols: list) -> dict:
    """Get quotes for multiple symbols at once."""
    try:
        import yfinance as yf

        # Convert all symbols
        yf_symbols = [
            s.replace('.NS','').upper() + '.NS'
            for s in symbols
        ]

        # Download all at once (faster)
        tickers = yf.download(
            yf_symbols,
            period    = '2d',
            interval  = '1d',
            progress  = False,
            auto_adjust= True,
        )

        quotes = {}
        for sym in yf_symbols:
            try:
                close  = float(
                    tickers['Close'][sym].iloc[-1])
                prev   = float(
                    tickers['Close'][sym].iloc[-2])
                high   = float(
                    tickers['High'][sym].iloc[-1])
                low    = float(
                    tickers['Low'][sym].iloc[-1])
                open_  = float(
                    tickers['Open'][sym].iloc[-1])
                change = round(close - prev, 2)
                pct    = round(
                    (change / prev) * 100, 2)

                quotes[sym] = {
                    'symbol': sym,
                    'price' : close,
                    'change': change,
                    'pct'   : pct,
                    'high'  : high,
                    'low'   : low,
                    'open'  : open_,
                    'prev'  : prev,
                }
                print(f"  📈 {sym}: "
                      f"Rs {close:,.2f} "
                      f"({pct:+.2f}%)")
            except:
                pass

        return quotes

    except Exception as e:
        print(f"  ❌ Multi-quote error: {e}")
        return {}

# ============================================================
# SECTION 8: PLACE ORDER
# ============================================================

def place_order(
        kite      : KiteConnect,
        symbol    : str,
        action    : str,
        quantity  : int,
        price     : float = 0,
        stop_loss : float = 0,
        target    : float = 0,
        paper_mode: bool  = True,
) -> dict:
    """
    Place an order on Zerodha.
    paper_mode=True  → Simulate only (SAFE)
    paper_mode=False → Actually place order (LIVE)
    """
    symbol = symbol.replace('.NS', '').upper()

    mode_str = "📝 PAPER" if paper_mode else "🚨 LIVE"
    print(f"\n  {mode_str} ORDER:")
    print(f"  {'─'*30}")
    print(f"  Symbol    : {symbol}")
    print(f"  Action    : {action}")
    print(f"  Quantity  : {quantity}")
    if stop_loss:
        print(f"  Stop Loss : Rs {stop_loss:,.2f}")
    if target:
        print(f"  Target    : Rs {target:,.2f}")

    # ── PAPER MODE ──
    if paper_mode:
        result = {
            'order_id'  : f"PAPER_{int(time.time())}",
            'symbol'    : symbol,
            'action'    : action,
            'quantity'  : quantity,
            'stop_loss' : stop_loss,
            'target'    : target,
            'status'    : 'PAPER',
            'paper_mode': True,
            'timestamp' : datetime.now().isoformat(),
        }
        print(f"  ✅ PAPER ORDER SIMULATED")
        print(f"  Order ID: {result['order_id']}")
        return result

    # ── LIVE MODE ──
    try:
        trans_type = (
            kite.TRANSACTION_TYPE_BUY
            if action == 'BUY'
            else kite.TRANSACTION_TYPE_SELL
        )

        # Main order
        order_id = kite.place_order(
            variety         = kite.VARIETY_REGULAR,
            exchange        = kite.EXCHANGE_NSE,
            tradingsymbol   = symbol,
            transaction_type= trans_type,
            quantity        = quantity,
            product         = kite.PRODUCT_CNC,
            order_type      = kite.ORDER_TYPE_MARKET,
        )
        print(f"  ✅ LIVE ORDER PLACED!")
        print(f"  Order ID : {order_id}")

        # Stop Loss order
        sl_order_id = None
        if stop_loss > 0:
            sl_trans = (
                kite.TRANSACTION_TYPE_SELL
                if action == 'BUY'
                else kite.TRANSACTION_TYPE_BUY
            )
            sl_order_id = kite.place_order(
                variety         = kite.VARIETY_REGULAR,
                exchange        = kite.EXCHANGE_NSE,
                tradingsymbol   = symbol,
                transaction_type= sl_trans,
                quantity        = quantity,
                product         = kite.PRODUCT_CNC,
                order_type      = kite.ORDER_TYPE_SL_M,
                trigger_price   = round(stop_loss, 2),
            )
            print(f"  ✅ SL Order  : {sl_order_id}")

        return {
            'order_id'   : order_id,
            'sl_order_id': sl_order_id,
            'symbol'     : symbol,
            'action'     : action,
            'quantity'   : quantity,
            'stop_loss'  : stop_loss,
            'target'     : target,
            'status'     : 'PLACED',
            'paper_mode' : False,
            'timestamp'  : datetime.now().isoformat(),
        }

    except Exception as e:
        print(f"  ❌ Order error: {e}")
        return {}


# ============================================================
# SECTION 9: CANCEL ORDER
# ============================================================

def cancel_order(kite      : KiteConnect,
                 order_id  : str,
                 paper_mode: bool = True) -> bool:
    """Cancel an open order."""
    if paper_mode:
        print(f"  ✅ PAPER: Order {order_id} cancelled")
        return True
    try:
        kite.cancel_order(
            variety  = kite.VARIETY_REGULAR,
            order_id = order_id,
        )
        print(f"  ✅ Order {order_id} cancelled!")
        return True
    except Exception as e:
        print(f"  ❌ Cancel error: {e}")
        return False


# ============================================================
# SECTION 10: GET ORDERS
# ============================================================

def get_orders(kite: KiteConnect) -> list:
    """Get today's orders."""
    try:
        orders = kite.orders()
        print(f"\n  📋 TODAY'S ORDERS: {len(orders)}")
        for o in orders[-5:]:
            print(f"  {o['tradingsymbol']} "
                  f"{o['transaction_type']} "
                  f"Qty={o['quantity']} "
                  f"Status={o['status']}")
        return orders
    except Exception as e:
        print(f"  ❌ Orders error: {e}")
        return []


# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*55)
    print("  BHARAT EDGE - PHASE 9A: ZERODHA CONNECTION")
    print(f"  {datetime.now().strftime('%A, %d %B %Y %H:%M')}")
    print("="*55)

    # Step 1: Login
    kite = auto_login()

    if not kite:
        print("\n  ❌ Login failed! Check credentials.")
        sys.exit(1)

    # Step 2: Account info
    account = get_account_info(kite)

    # Step 3: Holdings
    holdings = get_holdings(kite)

    # Step 4: Positions
    positions = get_positions(kite)

    # Step 5: Today's orders
    orders = get_orders(kite)

    # Step 6: Live quote test
    print("\n  📈 Testing live quotes...")
    symbols = ["RELIANCE.NS", "INFY.NS", "HDFCBANK.NS"]
    quotes  = {}
    for sym in symbols:
        q = get_quote(kite, sym)
        if q:
            quotes[sym] = q

        # Step 7: Paper order test
    if quotes.get("RELIANCE.NS"):
        price = quotes["RELIANCE.NS"]["price"]
        print(f"\n  🧪 Testing paper order...")
        order = place_order(
            kite       = kite,
            symbol     = "RELIANCE",
            action     = "BUY",
            quantity   = 1,
            stop_loss  = round(price * 0.98, 2),
            target     = round(price * 1.03, 2),
            paper_mode = True,
        )

    print(f"\n{'='*55}")
    print(f"  ✅ PHASE 9A COMPLETE!")
    print(f"  Zerodha connection working!")
    print(f"  Ready for Phase 9B: Strategy Engine")
    print(f"{'='*55}")