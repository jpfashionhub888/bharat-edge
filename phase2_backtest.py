# phase2_backtest.py
# BHARAT EDGE - Phase 3 Backtesting Engine OPTIMIZED v2
# Fixes: Position sizing, ATR stops, trailing stop, confidence threshold

import warnings
warnings.filterwarnings('ignore')
import os
os.environ['LOKY_MAX_CPU_COUNT'] = '1'
os.environ['PYTHONWARNINGS']     = 'ignore'

import pandas as pd
import numpy as np

from phase2_features import build_features, get_feature_columns
from phase2_models import load_all_models

print("✅ phase2_backtest.py loaded")

# ============================================================
# SECTION 1: OPTIMIZED CONFIGURATION
# ============================================================

BACKTEST_CONFIG = {
    # Capital
    'starting_capital'   : 1_000_000,   # Rs 10 Lakhs per symbol

    # ✅ FIX 1: Increased position size
    'max_position_pct'   : 0.35,        # Was 0.20 → now 0.35
    'risk_per_trade_pct' : 0.02,        # Risk 2% per trade

    # Realistic costs
    'brokerage_per_trade': 20,          # Rs 20 Zerodha
    'slippage_pct'       : 0.001,       # 0.1% slippage
    'stt_pct'            : 0.001,       # STT on sell
    'exchange_charges'   : 0.0000345,   # NSE charges

    # ✅ FIX 2: Higher confidence threshold
    'min_confidence'     : 65.0,        # Was 55 → now 65
    'strong_confidence'  : 75.0,        # Was 70 → now 75

    # Position sizing by signal
    'confidence_sizing'  : {
        'STRONG_BUY' : 1.0,            # Full position
        'BUY'        : 0.6,            # 60% position
        'WEAK_BUY'   : 0.0,            # ✅ Skip weak signals
        'WEAK_SELL'  : 0.0,
        'SELL'       : 0.0,
        'STRONG_SELL': 0.0,
    },

    # ✅ FIX 3: ATR-based stop loss
    'use_atr_stop'       : True,
    'atr_stop_multiplier': 1.5,         # 1.5 × ATR
    'fallback_stop_pct'  : 0.02,        # Fallback if ATR unavailable

    # ✅ FIX 4: Extended max hold
    'max_hold_days'      : 8,           # Was 5 → now 8

    # ✅ FIX 5: Trailing stop
    'use_trailing_stop'  : True,
    'trailing_trigger'   : 0.02,        # Activate after 2% gain
    'trailing_distance'  : 0.01,        # Trail by 1%

    # Take profit
    'take_profit_pct'    : 0.05,        # Was 4% → now 5% (2.5:1 R:R)
}


# ============================================================
# SECTION 2: TRADE CLASS (UPGRADED with ATR + Trailing Stop)
# ============================================================

class Trade:
    def __init__(
        self,
        symbol        : str,
        entry_date    : pd.Timestamp,
        entry_price   : float,
        shares        : int,
        signal        : str,
        confidence    : float,
        capital_used  : float,
        atr_value     : float = None,
    ):
        cfg = BACKTEST_CONFIG

        self.symbol       = symbol
        self.entry_date   = entry_date
        self.entry_price  = entry_price
        self.shares       = shares
        self.signal       = signal
        self.confidence   = confidence
        self.capital_used = capital_used
        self.atr_value    = atr_value

        # ✅ ATR-based stop loss
        if cfg['use_atr_stop'] and atr_value and atr_value > 0:
            self.stop_loss = entry_price - (
                atr_value * cfg['atr_stop_multiplier'])
            self.stop_type = 'ATR'
        else:
            self.stop_loss = entry_price * (
                1 - cfg['fallback_stop_pct'])
            self.stop_type = 'FIXED'

        # Ensure stop is not too tight or too wide
        min_stop = entry_price * 0.98   # Min 2% below
        max_stop = entry_price * 0.985  # Max 1.5% below
        self.stop_loss = max(self.stop_loss, min_stop * 0.97)

        self.take_profit      = entry_price * (
            1 + cfg['take_profit_pct'])

        # ✅ Trailing stop
        self.trailing_active  = False
        self.trailing_stop    = None
        self.highest_price    = entry_price

        self.exit_date        = None
        self.exit_price       = None
        self.exit_reason      = None
        self.pnl              = None
        self.pnl_pct          = None
        self.is_open          = True
        self.hold_days        = 0

    def update_trailing_stop(self, current_high: float):
        """Update trailing stop based on new high price."""
        cfg = BACKTEST_CONFIG

        if not cfg['use_trailing_stop']:
            return

        # Track highest price
        if current_high > self.highest_price:
            self.highest_price = current_high

        # Activate trailing stop after trigger gain
        gain_pct = (self.highest_price - self.entry_price) / self.entry_price
        if gain_pct >= cfg['trailing_trigger']:
            self.trailing_active = True
            new_trail = self.highest_price * (
                1 - cfg['trailing_distance'])
            # Only move stop UP never down
            if self.trailing_stop is None or new_trail > self.trailing_stop:
                self.trailing_stop = new_trail

    def get_effective_stop(self) -> float:
        """Get the current effective stop loss level."""
        if self.trailing_active and self.trailing_stop:
            return max(self.stop_loss, self.trailing_stop)
        return self.stop_loss

    def close(self, exit_date, exit_price, exit_reason):
        """Close trade and calculate net P&L."""
        cfg = BACKTEST_CONFIG

        self.exit_date   = exit_date
        self.exit_price  = exit_price
        self.exit_reason = exit_reason
        self.is_open     = False

        entry_cost = (
            cfg['brokerage_per_trade'] +
            self.entry_price * self.shares * cfg['slippage_pct']
        )
        exit_cost = (
            cfg['brokerage_per_trade'] +
            self.exit_price * self.shares * cfg['slippage_pct'] +
            self.exit_price * self.shares * cfg['stt_pct'] +
            self.exit_price * self.shares * cfg['exchange_charges']
        )

        gross_pnl  = (self.exit_price - self.entry_price) * self.shares
        self.pnl   = gross_pnl - entry_cost - exit_cost
        self.pnl_pct = self.pnl / self.capital_used * 100
        return self.pnl

    def to_dict(self):
        return {
            'symbol'      : self.symbol,
            'entry_date'  : self.entry_date,
            'exit_date'   : self.exit_date,
            'entry_price' : round(self.entry_price, 2),
            'exit_price'  : round(self.exit_price, 2) if self.exit_price else None,
            'shares'      : self.shares,
            'signal'      : self.signal,
            'confidence'  : round(self.confidence, 1),
            'stop_type'   : self.stop_type,
            'stop_loss'   : round(self.stop_loss, 2),
            'take_profit' : round(self.take_profit, 2),
            'capital_used': round(self.capital_used, 2),
            'pnl'         : round(self.pnl, 2) if self.pnl is not None else None,
            'pnl_pct'     : round(self.pnl_pct, 2) if self.pnl_pct is not None else None,
            'exit_reason' : self.exit_reason,
            'hold_days'   : self.hold_days,
            'trailing_activated': self.trailing_active,
        }


# ============================================================
# SECTION 3: SIGNAL GENERATOR
# ============================================================

def generate_signal_from_row(
    row          : pd.Series,
    base_models  : dict,
    feature_names: list,
) -> dict:
    """Generate ML signal from one feature row."""
    row_data = {}
    for feat in feature_names:
        val = row.get(feat, 0.0)
        if isinstance(val, float) and (
                np.isnan(val) or np.isinf(val)):
            val = 0.0
        row_data[feat] = val

    X_row = pd.DataFrame([row_data], columns=feature_names)

    individual = {}
    for name, model in base_models.items():
        try:
            if hasattr(model, 'n_jobs'):
                model.n_jobs = 1
            prob = float(model.predict_proba(X_row)[0][1])
            individual[name] = prob
        except:
            individual[name] = 0.5

    avg_prob  = float(np.mean(list(individual.values())))
    direction = 'UP' if avg_prob >= 0.5 else 'DOWN'
    up_votes  = sum(1 for p in individual.values() if p >= 0.5)

    base_conf = avg_prob if direction == 'UP' else (1 - avg_prob)
    agreement = (up_votes / len(individual) if direction == 'UP'
                 else (len(individual) - up_votes) / len(individual))
    std_dev   = float(np.std(list(individual.values())))

    confidence = float(min(99, max(1,
        base_conf * 100
        + (agreement - 0.5) * 30
        - std_dev * 20
    )))

    if direction == 'UP':
        if confidence >= 75:
            signal = 'STRONG_BUY'
        elif confidence >= 65:
            signal = 'BUY'
        else:
            signal = 'WEAK_BUY'
    else:
        if confidence >= 75:
            signal = 'STRONG_SELL'
        elif confidence >= 65:
            signal = 'SELL'
        else:
            signal = 'WEAK_SELL'

    return {
        'direction' : direction,
        'signal'    : signal,
        'confidence': confidence,
        'avg_prob'  : avg_prob,
        'up_votes'  : up_votes,
    }


# ============================================================
# SECTION 4: POSITION SIZER (UPGRADED)
# ============================================================

def calculate_position_size(
    capital    : float,
    price      : float,
    signal     : str,
    confidence : float,
    atr_value  : float = None,
) -> tuple:
    """
    Calculate position size.
    Uses ATR for risk-based sizing when available.
    """
    cfg         = BACKTEST_CONFIG
    signal_mult = cfg['confidence_sizing'].get(signal, 0.0)

    if signal_mult == 0.0 or price <= 0:
        return 0, 0.0

    # Confidence scaling (65% → 0.0, 99% → 1.0)
    conf_scale  = min(1.0, max(0.1, (confidence - 60) / 40))

    # Max capital allocation
    max_capital = (capital * cfg['max_position_pct']
                   * signal_mult * conf_scale)

    # ATR-based risk sizing
    if atr_value and atr_value > 0:
        stop_distance = atr_value * cfg['atr_stop_multiplier']
    else:
        stop_distance = price * cfg['fallback_stop_pct']

    stop_distance = max(stop_distance, price * 0.005)  # Min 0.5%

    risk_amount  = capital * cfg['risk_per_trade_pct']
    risk_shares  = int(risk_amount / stop_distance)
    price_shares = int(max_capital / price)

    shares       = max(1, min(risk_shares, price_shares))
    capital_used = shares * price

    # Don't use more than 35% of capital
    if capital_used > capital * cfg['max_position_pct']:
        shares       = int(capital * cfg['max_position_pct'] / price)
        capital_used = shares * price

    return shares, capital_used


# ============================================================
# SECTION 5: SINGLE SYMBOL BACKTEST (UPGRADED)
# ============================================================

def backtest_symbol(
    symbol          : str,
    base_models     : dict,
    feature_names   : list,
    period          : str   = "2y",
    vix_value       : float = 15.0,
    vix_change      : float = 0.0,
    fii_net         : float = 0.0,
    dii_net         : float = 0.0,
    sgx_gap         : float = 0.0,
    news_sentiment  : float = 0.0,
    news_volume     : int   = 0,
    starting_capital: float = None,
    verbose         : bool  = True,
) -> dict:
    cfg     = BACKTEST_CONFIG
    capital = starting_capital or cfg['starting_capital']

    if verbose:
        print(f"\n{'='*55}")
        print(f"  BACKTEST: {symbol}")
        print(f"  Capital : Rs {capital:,.0f}")
        print(f"  Config  : ATR-Stop={cfg['use_atr_stop']} "
              f"Trail={cfg['use_trailing_stop']} "
              f"MaxHold={cfg['max_hold_days']}d "
              f"MinConf={cfg['min_confidence']}%")
        print(f"{'='*55}")

    try:
        df = build_features(
            symbol=symbol, period=period,
            vix_value=vix_value, vix_change=vix_change,
            fii_net=fii_net, dii_net=dii_net,
            sgx_gap=sgx_gap, news_sentiment=news_sentiment,
            news_volume=news_volume, verbose=False,
        )
    except Exception as e:
        print(f"  ❌ Data error: {e}")
        return {}

    if df.empty or len(df) < 60:
        print(f"  ❌ Insufficient data")
        return {}

    feat_cols = get_feature_columns()
    available = [c for c in feat_cols if c in df.columns]

    trades        = []
    open_trade    = None
    equity_curve  = []
    daily_capital = capital

    for i in range(50, len(df)):
        try:
            row         = df.iloc[i]
            today       = df.index[i]
            today_high  = float(row['high'])
            today_low   = float(row['low'])
            today_close = float(row['close'])

            # Get ATR for today
            atr_today = float(row.get('atr_14', 0)) if 'atr_14' in row.index else None

            # ── Manage open trade ─────────────────────────
            if open_trade is not None:
                open_trade.hold_days += 1

                # Update trailing stop with today's high
                open_trade.update_trailing_stop(today_high)

                # Get effective stop (regular or trailing)
                effective_stop = open_trade.get_effective_stop()

                # Check stop loss (including trailing)
                if today_low <= effective_stop:
                    exit_reason = ('TRAILING_STOP'
                                   if open_trade.trailing_active
                                   else f'STOP_LOSS_{open_trade.stop_type}')
                    pnl = open_trade.close(
                        today, effective_stop, exit_reason)
                    daily_capital += open_trade.capital_used + pnl
                    trades.append(open_trade)
                    open_trade = None

                # Check take profit
                elif today_high >= open_trade.take_profit:
                    pnl = open_trade.close(
                        today, open_trade.take_profit, 'TAKE_PROFIT')
                    daily_capital += open_trade.capital_used + pnl
                    trades.append(open_trade)
                    open_trade = None

                # Max hold exceeded
                elif open_trade.hold_days >= cfg['max_hold_days']:
                    pnl = open_trade.close(
                        today, today_close, 'MAX_HOLD')
                    daily_capital += open_trade.capital_used + pnl
                    trades.append(open_trade)
                    open_trade = None

            # ── Generate signal ───────────────────────────
            if open_trade is None:
                signal_info = generate_signal_from_row(
                    row, base_models, available)

                signal     = signal_info['signal']
                confidence = signal_info['confidence']
                direction  = signal_info['direction']

                # ✅ Only trade high confidence BUY signals
                is_buy     = direction == 'UP'
                is_valid   = confidence >= cfg['min_confidence']
                is_tradeable = cfg['confidence_sizing'].get(
                    signal, 0.0) > 0

                if is_buy and is_valid and is_tradeable:
                    if i + 1 < len(df):
                        next_row  = df.iloc[i+1]
                        next_open = float(next_row['open'])

                        if next_open > 0:
                            shares, cap_used = calculate_position_size(
                                daily_capital, next_open,
                                signal, confidence, atr_today)

                            if shares > 0 and cap_used <= daily_capital * 0.95:
                                open_trade = Trade(
                                    symbol       = symbol,
                                    entry_date   = df.index[i+1],
                                    entry_price  = next_open,
                                    shares       = shares,
                                    signal       = signal,
                                    confidence   = confidence,
                                    capital_used = cap_used,
                                    atr_value    = atr_today,
                                )
                                daily_capital -= cap_used

            # ── Track equity ──────────────────────────────
            unrealized = 0.0
            held_cap   = 0.0
            if open_trade is not None:
                unrealized = ((today_close - open_trade.entry_price)
                              * open_trade.shares)
                held_cap   = open_trade.capital_used

            equity_curve.append({
                'date'      : today,
                'capital'   : daily_capital,
                'unrealized': unrealized,
                'total'     : daily_capital + held_cap + unrealized,
            })

        except Exception as e:
            continue

    # Close remaining trade
    if open_trade is not None:
        try:
            last_close = float(df.iloc[-1]['close'])
            pnl = open_trade.close(
                df.index[-1], last_close, 'END_OF_BACKTEST')
            daily_capital += open_trade.capital_used + pnl
            trades.append(open_trade)
        except:
            pass

    stats = calculate_statistics(
        trades       = trades,
        equity_curve = equity_curve,
        start_capital= cfg['starting_capital'],
        symbol       = symbol,
        verbose      = verbose,
    )

    return {
        'symbol'       : symbol,
        'trades'       : trades,
        'equity_curve' : pd.DataFrame(equity_curve),
        'stats'        : stats,
        'final_capital': daily_capital,
    }


# ============================================================
# SECTION 6: STATISTICS CALCULATOR
# ============================================================

def calculate_statistics(
    trades       : list,
    equity_curve : list,
    start_capital: float,
    symbol       : str,
    verbose      : bool = True,
) -> dict:
    if not trades:
        if verbose:
            print(f"  ⚠️ No trades for {symbol}")
        return {}

    trade_df = pd.DataFrame([t.to_dict() for t in trades])
    trade_df = trade_df.dropna(subset=['pnl'])

    if trade_df.empty:
        return {}

    eq_df = pd.DataFrame(equity_curve)

    total_trades  = len(trade_df)
    winning       = trade_df[trade_df['pnl'] > 0]
    losing        = trade_df[trade_df['pnl'] <= 0]
    win_rate      = len(winning) / total_trades * 100
    total_pnl     = trade_df['pnl'].sum()
    avg_win       = winning['pnl'].mean() if len(winning) > 0 else 0
    avg_loss      = losing['pnl'].mean()  if len(losing)  > 0 else 0
    best_trade    = trade_df['pnl'].max()
    worst_trade   = trade_df['pnl'].min()

    gross_profit  = winning['pnl'].sum() if len(winning) > 0 else 0
    gross_loss    = abs(losing['pnl'].sum()) if len(losing) > 0 else 1
    profit_factor = gross_profit / max(gross_loss, 1)

    final_capital = start_capital + total_pnl
    total_return  = (final_capital - start_capital) / start_capital * 100

    trading_days  = max(len(eq_df), 1)
    years         = trading_days / 250
    cagr = ((final_capital / start_capital) ** (
        1 / max(years, 0.1)) - 1) * 100

    if len(eq_df) > 1 and 'total' in eq_df.columns:
        eq_series    = eq_df['total']
        rolling_max  = eq_series.cummax()
        drawdown     = (eq_series - rolling_max) / rolling_max * 100
        max_drawdown = drawdown.min()
        daily_rets   = eq_series.pct_change().dropna()
        sharpe = (
            (daily_rets.mean() / daily_rets.std()) * np.sqrt(250)
            if daily_rets.std() > 0 else 0
        )
    else:
        max_drawdown = 0.0
        sharpe       = 0.0

    avg_hold    = trade_df['hold_days'].mean()
    exit_counts = trade_df['exit_reason'].value_counts().to_dict()

    # Signal performance
    signal_perf = {}
    for sig in trade_df['signal'].unique():
        sig_df = trade_df[trade_df['signal'] == sig]
        signal_perf[sig] = {
            'count'   : len(sig_df),
            'win_rate': (sig_df['pnl'] > 0).sum() / len(sig_df) * 100,
            'avg_pnl' : sig_df['pnl'].mean(),
        }

    # Trailing stop analysis
    trail_count = (
        trade_df['exit_reason'].str.contains('TRAIL', na=False).sum()
        if 'exit_reason' in trade_df.columns else 0
    )

    # Monthly returns
    monthly = {}
    if len(eq_df) > 0 and 'date' in eq_df.columns:
        try:
            eq_df['date']  = pd.to_datetime(eq_df['date'])
            eq_df['month'] = eq_df['date'].dt.to_period('M')
            monthly_eq     = eq_df.groupby('month')['total'].last()
            monthly_ret    = monthly_eq.pct_change() * 100
            monthly = {
                str(k): round(v, 2)
                for k, v in monthly_ret.dropna().items()
            }
        except:
            pass

    stats = {
        'symbol'          : symbol,
        'total_trades'    : total_trades,
        'winning_trades'  : len(winning),
        'losing_trades'   : len(losing),
        'win_rate'        : round(win_rate, 2),
        'total_pnl'       : round(total_pnl, 2),
        'avg_win'         : round(avg_win, 2),
        'avg_loss'        : round(avg_loss, 2),
        'best_trade'      : round(best_trade, 2),
        'worst_trade'     : round(worst_trade, 2),
        'profit_factor'   : round(profit_factor, 3),
        'total_return'    : round(total_return, 2),
        'cagr'            : round(cagr, 2),
        'max_drawdown'    : round(max_drawdown, 2),
        'sharpe_ratio'    : round(sharpe, 3),
        'avg_hold_days'   : round(avg_hold, 1),
        'start_capital'   : start_capital,
        'final_capital'   : round(final_capital, 2),
        'exit_reasons'    : exit_counts,
        'signal_perf'     : signal_perf,
        'trailing_exits'  : int(trail_count),
        'monthly_returns' : monthly,
    }

    if verbose:
        _print_stats(stats)

    return stats


def _print_stats(s: dict):
    emoji_r = "🟢" if s['total_return'] > 0  else "🔴"
    emoji_w = "🟢" if s['win_rate'] > 55      else "🟡" \
              if s['win_rate'] > 45 else "🔴"
    emoji_s = "🟢" if s['sharpe_ratio'] > 1.5 else "🟡" \
              if s['sharpe_ratio'] > 0.5 else "🔴"
    emoji_d = "🟢" if s['max_drawdown'] > -10 else "🟡" \
              if s['max_drawdown'] > -20 else "🔴"

    print(f"\n  {'─'*52}")
    print(f"  📊 RESULTS: {s['symbol']}")
    print(f"  {'─'*52}")
    print(f"  💰 Capital")
    print(f"     Start         : Rs {s['start_capital']:>12,.0f}")
    print(f"     End           : Rs {s['final_capital']:>12,.0f}")
    print(f"     P&L           : Rs {s['total_pnl']:>+12,.0f}")
    print(f"  {'─'*52}")
    print(f"  📈 Returns")
    print(f"     Total Return  : {emoji_r} {s['total_return']:>+8.2f}%")
    print(f"     CAGR          : {emoji_r} {s['cagr']:>+8.2f}%")
    print(f"  {'─'*52}")
    print(f"  🎯 Trades")
    print(f"     Total         :    {s['total_trades']:>6}")
    print(f"     Won           :    {s['winning_trades']:>6}")
    print(f"     Lost          :    {s['losing_trades']:>6}")
    print(f"     Win Rate      : {emoji_w} {s['win_rate']:>8.2f}%")
    print(f"     Avg Win       : Rs {s['avg_win']:>+10,.0f}")
    print(f"     Avg Loss      : Rs {s['avg_loss']:>+10,.0f}")
    print(f"     Best Trade    : Rs {s['best_trade']:>+10,.0f}")
    print(f"     Worst Trade   : Rs {s['worst_trade']:>+10,.0f}")
    print(f"     Profit Factor :    {s['profit_factor']:>6.3f}")
    print(f"     Avg Hold Days :    {s['avg_hold_days']:>6.1f} days")
    print(f"     Trailing Exits:    {s['trailing_exits']:>6}")
    print(f"  {'─'*52}")
    print(f"  ⚡ Risk")
    print(f"     Sharpe Ratio  : {emoji_s} {s['sharpe_ratio']:>8.3f}")
    print(f"     Max Drawdown  : {emoji_d} {s['max_drawdown']:>8.2f}%")
    print(f"  {'─'*52}")
    print(f"  🚪 Exit Reasons")
    for reason, count in s['exit_reasons'].items():
        pct = count / s['total_trades'] * 100
        print(f"     {reason:<25}: {count:>4} ({pct:.1f}%)")
    print(f"  {'─'*52}")
    print(f"  🎯 Signal Performance")
    for sig, perf in s['signal_perf'].items():
        print(f"     {sig:<15}: "
              f"n={perf['count']:>4}  "
              f"WR={perf['win_rate']:>5.1f}%  "
              f"AvgPnL=Rs{perf['avg_pnl']:>+8,.0f}")
    if s['monthly_returns']:
        print(f"  {'─'*52}")
        print(f"  📅 Monthly Returns (last 12)")
        for month, ret in list(s['monthly_returns'].items())[-12:]:
            bar   = "█" * int(abs(ret) / 2)
            sign  = "+" if ret >= 0 else "-"
            emoji = "🟢" if ret >= 0 else "🔴"
            print(f"     {str(month):<10}: "
                  f"{emoji} {sign}{abs(ret):>5.2f}%  {bar}")


# ============================================================
# SECTION 7: PORTFOLIO BACKTEST
# ============================================================

def backtest_portfolio(
    symbols        : list,
    base_models    : dict,
    feature_names  : list,
    period         : str   = "2y",
    vix_value      : float = 15.0,
    vix_change     : float = 0.0,
    fii_net        : float = 0.0,
    dii_net        : float = 0.0,
    sgx_gap        : float = 0.0,
    news_sentiment : float = 0.0,
    news_volume    : int   = 0,
) -> pd.DataFrame:
    cfg = BACKTEST_CONFIG

    print(f"\n{'🔥'*20}")
    print(f"  PORTFOLIO BACKTEST v2 — OPTIMIZED")
    print(f"  Symbols      : {len(symbols)}")
    print(f"  Capital/sym  : Rs {cfg['starting_capital']:,.0f}")
    print(f"  Min Conf     : {cfg['min_confidence']}%")
    print(f"  Max Position : {cfg['max_position_pct']*100:.0f}%")
    print(f"  ATR Stop     : {cfg['atr_stop_multiplier']}x ATR")
    print(f"  Max Hold     : {cfg['max_hold_days']} days")
    print(f"  Take Profit  : {cfg['take_profit_pct']*100:.0f}%")
    print(f"  Trailing Stop: {cfg['use_trailing_stop']}")
    print(f"{'🔥'*20}")

    all_results = []
    all_stats   = []

    for symbol in symbols:
        print(f"\n  ▶️  {symbol}...")
        try:
            result = backtest_symbol(
                symbol          = symbol,
                base_models     = base_models,
                feature_names   = feature_names,
                period          = period,
                vix_value       = vix_value,
                vix_change      = vix_change,
                fii_net         = fii_net,
                dii_net         = dii_net,
                sgx_gap         = sgx_gap,
                news_sentiment  = news_sentiment,
                news_volume     = news_volume,
                starting_capital= cfg['starting_capital'],
                verbose         = True,
            )
            if result and result.get('stats'):
                all_results.append(result)
                all_stats.append(result['stats'])
        except Exception as e:
            print(f"  ❌ {symbol}: {e}")
            continue

    if not all_stats:
        print("❌ No results!")
        return pd.DataFrame()

    stats_df = pd.DataFrame(all_stats)

    # ── Portfolio Summary Table ───────────────────────────
    print(f"\n{'='*76}")
    print(f"  📊 OPTIMIZED PORTFOLIO SUMMARY")
    print(f"{'='*76}")
    print(f"  {'Symbol':<14} {'Return':>8} {'CAGR':>8} "
          f"{'WinRate':>9} {'Sharpe':>8} {'MaxDD':>8} "
          f"{'Trades':>8} {'PF':>7}")
    print(f"  {'-'*76}")

    for _, row in stats_df.iterrows():
        r_emoji = "🟢" if row['total_return'] > 0 else "🔴"
        print(
            f"  {row['symbol']:<14} "
            f"{r_emoji}{row['total_return']:>+7.1f}% "
            f"{row['cagr']:>+7.1f}% "
            f"{row['win_rate']:>8.1f}% "
            f"{row['sharpe_ratio']:>8.3f} "
            f"{row['max_drawdown']:>7.1f}% "
            f"{row['total_trades']:>8} "
            f"{row['profit_factor']:>7.3f}"
        )

    print(f"  {'-'*76}")

    # Aggregates
    total_start  = cfg['starting_capital'] * len(all_stats)
    total_pnl    = stats_df['total_pnl'].sum()
    total_end    = total_start + total_pnl
    port_ret     = total_pnl / total_start * 100
    avg_win_rate = stats_df['win_rate'].mean()
    avg_sharpe   = stats_df['sharpe_ratio'].mean()
    avg_dd       = stats_df['max_drawdown'].mean()
    total_trades = stats_df['total_trades'].sum()
    avg_pf       = stats_df['profit_factor'].mean()

    p_emoji = "🟢" if port_ret > 0 else "🔴"
    print(
        f"\n  {'PORTFOLIO':<14} "
        f"{p_emoji}{port_ret:>+7.1f}% "
        f"{'':>8} "
        f"{avg_win_rate:>8.1f}% "
        f"{avg_sharpe:>8.3f} "
        f"{avg_dd:>7.1f}% "
        f"{total_trades:>8} "
        f"{avg_pf:>7.3f}"
    )

    print(f"\n  💰 Capital Summary:")
    print(f"     Invested  : Rs {total_start:>14,.0f}")
    print(f"     Value     : Rs {total_end:>14,.0f}")
    print(f"     P&L       : Rs {total_pnl:>+14,.0f}")
    print(f"     Return    :    {port_ret:>+10.2f}%")

    # Comparison with v1
    print(f"\n  📊 Improvement vs v1 (Before Optimization):")
    print(f"     Return    : +1.13% → {port_ret:>+.2f}%")
    print(f"     Win Rate  : 52.0%  → {avg_win_rate:>.1f}%")
    print(f"     Sharpe    : 0.610  → {avg_sharpe:.3f}")
    print(f"     Trades    : 334    → {total_trades}")

    # Performance rating
    ratings = []
    if port_ret     > 5   : ratings.append("✅ Return > 5%")
    if port_ret     > 15  : ratings.append("✅ Return > 15%")
    if port_ret     > 20  : ratings.append("✅ Return > 20%")
    if avg_win_rate > 55  : ratings.append("✅ Win Rate > 55%")
    if avg_sharpe   > 1.0 : ratings.append("✅ Sharpe > 1.0")
    if avg_sharpe   > 1.5 : ratings.append("✅ Sharpe > 1.5")
    if avg_dd       > -15 : ratings.append("✅ Drawdown < 15%")
    if avg_pf       > 1.3 : ratings.append("✅ Profit Factor > 1.3")
    if avg_pf       > 1.5 : ratings.append("✅ Profit Factor > 1.5")

    grade = (
        "🏆 EXCELLENT" if avg_sharpe > 1.5 and avg_win_rate > 55 else
        "🥈 GOOD"      if avg_sharpe > 1.0 and port_ret > 5      else
        "🥉 AVERAGE"   if port_ret > 0                            else
        "⚠️  NEEDS WORK"
    )

    print(f"\n  🏆 Performance Rating:")
    for r in ratings:
        print(f"     {r}")
    print(f"\n     Grade: {grade}")

    # Export trade log
    all_trades = []
    for result in all_results:
        for trade in result.get('trades', []):
            all_trades.append(trade.to_dict())

    if all_trades:
        trade_log = pd.DataFrame(all_trades)
        trade_log.to_csv("trade_log_v2.csv", index=False)
        print(f"\n  💾 Trade log: trade_log_v2.csv")
        print(f"     Trades : {len(trade_log)}")
        print(f"     P&L    : Rs {trade_log['pnl'].sum():>+,.0f}")

        # Trailing stop stats
        trail = trade_log[
            trade_log['exit_reason'].str.contains(
                'TRAIL', na=False)]
        if len(trail) > 0:
            print(f"     Trailing stop exits : {len(trail)}")
            print(f"     Trailing stop P&L   : "
                  f"Rs {trail['pnl'].sum():>+,.0f}")

    return stats_df


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("\n" + "📈"*20)
    print("  BHARAT EDGE - OPTIMIZED BACKTEST v2")
    print("📈"*20)

    # Load models
    ensemble = load_all_models()
    if not ensemble:
        print("❌ Run phase2_models.py first!")
        exit()

    base_models   = ensemble['base_models']
    feature_names = ensemble['feature_names']
    print(f"  ✅ Models: {list(base_models.keys())}")
    print(f"  ✅ Features: {len(feature_names)}")

    MARKET = dict(
        vix_value      = 17.21,
        vix_change     = -4.9,
        fii_net        = 500,
        dii_net        = 300,
        sgx_gap        = 0.65,
        news_sentiment = 0.3,
        news_volume    = 35,
    )

    # ✅ FIX 6: Replaced HDFCBANK with BAJAJ-AUTO
    SYMBOLS = [
        "TCS.NS",
        "INFY.NS",
        "RELIANCE.NS",
        "BAJAJ-AUTO.NS",   # ✅ Replacing HDFCBANK
        "ICICIBANK.NS",
        "WIPRO.NS",
        "SBIN.NS",
        "BAJFINANCE.NS",
    ]

    stats_df = backtest_portfolio(
        symbols       = SYMBOLS,
        base_models   = base_models,
        feature_names = feature_names,
        period        = "2y",
        **MARKET,
    )

    print(f"\n{'='*55}")
    print(f"  ✅ OPTIMIZED BACKTEST COMPLETE!")
    print(f"  📁 trade_log_v2.csv saved")
    print(f"  🚀 Ready for Option B: 50 Stocks + Sector Rotation!")
    print(f"{'='*55}")