# config/settings.py

import os
from dotenv import load_dotenv

load_dotenv('config/secrets.env')

# ============================================================
# SYSTEM SETTINGS
# ============================================================

SYSTEM_NAME = "BharatEdge"
VERSION = "1.0.0"
MODE = "paper"

# ============================================================
# TIMEZONE (Critical for Indian Market)
# ============================================================

TIMEZONE = "Asia/Kolkata"
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"
PRE_MARKET_START = "08:30"
POST_MARKET_END = "16:00"

# ============================================================
# MARKET SETTINGS
# ============================================================

# Nifty 50 Stocks (NSE)
STOCK_WATCHLIST = [
    # Large Cap IT
    'TCS.NS', 'INFY.NS', 'WIPRO.NS',
    'HCLTECH.NS', 'TECHM.NS',

    # Banking
    'HDFCBANK.NS', 'ICICIBANK.NS',
    'KOTAKBANK.NS', 'AXISBANK.NS',
    'SBIN.NS',

    # Energy
    'RELIANCE.NS', 'ONGC.NS', 'BPCL.NS',

    # FMCG
    'HINDUNILVR.NS', 'ITC.NS',
    'NESTLEIND.NS',

    # Pharma
    'SUNPHARMA.NS', 'DRREDDY.NS',
    'CIPLA.NS',

    # Auto
    'MARUTI.NS', 'TATAMOTORS.NS',
    'BAJAJ-AUTO.NS',

    # Finance
    'BAJFINANCE.NS', 'BAJAJFINSV.NS',

    # Metal/Mining
    'TATASTEEL.NS', 'HINDALCO.NS',
    'JSWSTEEL.NS',

    # Indices
    '^NSEI', '^NSEBANK', '^INDIAVIX',

    # Small/Mid Cap (Your Edge)
    'ADANIENT.NS', 'ADANIPORTS.NS',
    'LTIM.NS', 'PERSISTENT.NS',
    'MPHASIS.NS',
]

# ============================================================
# API CREDENTIALS
# ============================================================

ZERODHA_API_KEY = os.getenv('ZERODHA_API_KEY', '')
ZERODHA_API_SECRET = os.getenv('ZERODHA_API_SECRET', '')
ZERODHA_ACCESS_TOKEN = os.getenv('ZERODHA_ACCESS_TOKEN', '')

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# ============================================================
# RISK MANAGEMENT
# ============================================================

MAX_RISK_PER_TRADE = 0.02
MAX_PORTFOLIO_RISK = 0.06
MAX_POSITION_SIZE = 0.15
MAX_DAILY_LOSS = 0.03
MAX_DRAWDOWN = 0.10
MAX_OPEN_POSITIONS = 5

# India VIX based position sizing
VIX_LEVELS = {
    'very_calm': 12,
    'normal': 16,
    'nervous': 20,
    'fearful': 25,
}

VIX_MULTIPLIERS = {
    'very_calm': 1.5,
    'normal': 1.0,
    'nervous': 0.5,
    'fearful': 0.25,
    'panic': 0.0,
}

# ============================================================
# MODEL SETTINGS
# ============================================================

PREDICTION_THRESHOLD = 0.55
LOOKBACK_DAYS = 730
FORWARD_PERIOD = 5
TOP_FEATURES = 25
RETRAIN_DAYS = 30

# ============================================================
# STRATEGY SETTINGS
# ============================================================

STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.08
TRAILING_STOP_PCT = 0.025

# ============================================================
# LOGGING
# ============================================================

LOG_FILE = 'logs/bharat_edge.log'
LOG_LEVEL = 'INFO'