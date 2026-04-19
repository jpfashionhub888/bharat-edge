# performance_tracker.py
# BHARAT EDGE - Performance Tracker
# Appends daily scan results to performance_history.csv

import os
import pandas as pd
from datetime import datetime

HISTORY_FILE = "performance_history.csv"

def update_performance_history(scan_df: pd.DataFrame) -> bool:
    """
    Appends today's scan results to performance_history.csv
    """
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        time_str = datetime.now().strftime('%H:%M')

        if scan_df is None or scan_df.empty:
            # Still log the date even if no signals
            new_rows = pd.DataFrame([{
                "date"          : today,
                "time"          : time_str,
                "symbol"        : "NO_SIGNALS",
                "signal"        : "NONE",
                "confidence"    : 0.0,
                "sector"        : "N/A",
                "sector_status" : "N/A",
                "up_votes"      : 0,
                "result"        : "PENDING",
                "pnl_pct"       : 0.0,
                "correct"       : "PENDING",
            }])
        else:
            rows = []
            for _, row in scan_df.iterrows():
                rows.append({
                    "date"          : today,
                    "time"          : time_str,
                    "symbol"        : row.get("symbol", ""),
                    "signal"        : row.get("signal", ""),
                    "confidence"    : round(row.get("adj_confidence", 0), 2),
                    "sector"        : row.get("sector", ""),
                    "sector_status" : row.get("sector_status", ""),
                    "up_votes"      : row.get("up_votes", 0),
                    "result"        : "PENDING",
                    "pnl_pct"       : 0.0,
                    "correct"       : "PENDING",
                })
            new_rows = pd.DataFrame(rows)

        # Load existing history or create new
        if os.path.exists(HISTORY_FILE):
            history = pd.read_csv(HISTORY_FILE)
            # Avoid duplicate entries for same date + symbol
            history = history[
                ~((history['date'] == today) &
                  (history['symbol'].isin(new_rows['symbol'])))
            ]
            history = pd.concat(
                [history, new_rows], ignore_index=True)
        else:
            history = new_rows

        history.to_csv(HISTORY_FILE, index=False)
        print(f"  ✅ Performance history updated: "
              f"{len(new_rows)} rows added to {HISTORY_FILE}")
        return True

    except Exception as e:
        print(f"  ❌ Performance tracker error: {e}")
        return False


def get_performance_summary() -> dict:
    """
    Returns win/loss summary from history
    """
    try:
        if not os.path.exists(HISTORY_FILE):
            return {}

        df = pd.read_csv(HISTORY_FILE)

        # Only look at completed trades (not PENDING)
        completed = df[df['correct'] != 'PENDING']

        if completed.empty:
            total    = len(df)
            pending  = len(df[df['correct'] == 'PENDING'])
            return {
                "total_signals" : total,
                "pending"       : pending,
                "wins"          : 0,
                "losses"        : 0,
                "win_rate"      : 0.0,
                "avg_pnl"       : 0.0,
            }

        wins   = len(completed[completed['correct'] == 'YES'])
        losses = len(completed[completed['correct'] == 'NO'])
        total  = wins + losses

        return {
            "total_signals" : len(df),
            "pending"       : len(df[df['correct'] == 'PENDING']),
            "wins"          : wins,
            "losses"        : losses,
            "win_rate"      : round((wins / total * 100), 1) if total > 0 else 0.0,
            "avg_pnl"       : round(completed['pnl_pct'].mean(), 2),
        }

    except Exception as e:
        print(f"  ❌ Summary error: {e}")
        return {}


def print_performance_summary():
    """Prints a nice summary to console."""
    summary = get_performance_summary()
    if not summary:
        print("  ⚠️ No performance history found.")
        return

    print("\n" + "="*50)
    print("  BHARAT EDGE - PERFORMANCE SUMMARY")
    print("="*50)
    print(f"  Total Signals : {summary['total_signals']}")
    print(f"  Pending       : {summary['pending']}")
    print(f"  Wins          : {summary['wins']}")
    print(f"  Losses        : {summary['losses']}")
    print(f"  Win Rate      : {summary['win_rate']}%")
    print(f"  Avg PnL       : {summary['avg_pnl']}%")
    print("="*50)


if __name__ == "__main__":
    print("\n" + "="*50)
    print("  BHARAT EDGE - PERFORMANCE TRACKER")
    print(f"  {datetime.now().strftime('%A, %d %B %Y %H:%M')}")
    print("="*50)

    # Test with dummy data
    test_df = pd.DataFrame([
        {
            "symbol"        : "RELIANCE.NS",
            "signal"        : "STRONG_BUY",
            "adj_confidence": 71.8,
            "sector"        : "Energy",
            "sector_status" : "OVERWEIGHT",
            "up_votes"      : 4,
        },
        {
            "symbol"        : "INFY.NS",
            "signal"        : "STRONG_BUY",
            "adj_confidence": 71.6,
            "sector"        : "IT",
            "sector_status" : "OVERWEIGHT",
            "up_votes"      : 4,
        },
    ])

    update_performance_history(test_df)
    print_performance_summary()