# bharat_correlation.py
# BHARATEDGE - Sector Correlation Filter
# Max 2 stocks per Indian sector

import logging
logger = logging.getLogger(__name__)

INDIAN_STOCK_SECTORS = {
    # IT
    'TCS.NS'        : 'IT',
    'INFY.NS'       : 'IT',
    'WIPRO.NS'      : 'IT',
    'HCLTECH.NS'    : 'IT',
    'TECHM.NS'      : 'IT',
    'MPHASIS.NS'    : 'IT',
    'PERSISTENT.NS' : 'IT',

    # Banking
    'HDFCBANK.NS'   : 'Banking',
    'ICICIBANK.NS'  : 'Banking',
    'SBIN.NS'       : 'Banking',
    'KOTAKBANK.NS'  : 'Banking',
    'AXISBANK.NS'   : 'Banking',
    'INDUSINDBK.NS' : 'Banking',
    'BANDHANBNK.NS' : 'Banking',
    'FEDERALBNK.NS' : 'Banking',

    # NBFC
    'BAJFINANCE.NS' : 'NBFC',
    'BAJAJFINSV.NS' : 'NBFC',
    'CHOLAFIN.NS'   : 'NBFC',
    'MUTHOOTFIN.NS' : 'NBFC',

    # Auto
    'MARUTI.NS'     : 'Auto',
    'M&M.NS'        : 'Auto',
    'BAJAJ-AUTO.NS' : 'Auto',
    'HEROMOTOCO.NS' : 'Auto',
    'EICHERMOT.NS'  : 'Auto',

    # Pharma
    'SUNPHARMA.NS'  : 'Pharma',
    'DRREDDY.NS'    : 'Pharma',
    'CIPLA.NS'      : 'Pharma',
    'DIVISLAB.NS'   : 'Pharma',
    'AUROPHARMA.NS' : 'Pharma',
    'TORNTPHARM.NS' : 'Pharma',

    # Energy
    'RELIANCE.NS'   : 'Energy',
    'ONGC.NS'       : 'Energy',
    'NTPC.NS'       : 'Energy',
    'POWERGRID.NS'  : 'Energy',

    # Metal
    'TATASTEEL.NS'  : 'Metal',
    'HINDALCO.NS'   : 'Metal',
    'JSWSTEEL.NS'   : 'Metal',
    'COALINDIA.NS'  : 'Metal',

    # FMCG
    'HINDUNILVR.NS' : 'FMCG',
    'ITC.NS'        : 'FMCG',
    'NESTLEIND.NS'  : 'FMCG',
    'BRITANNIA.NS'  : 'FMCG',

    # Infra
    'LT.NS'         : 'Infra',
    'ULTRACEMCO.NS' : 'Infra',
    'ADANIPORTS.NS' : 'Infra',
    'DLF.NS'        : 'Infra',

    # Consumer
    'TITAN.NS'      : 'Consumer',
    'ASIANPAINT.NS' : 'Consumer',
    'PIDILITIND.NS' : 'Consumer',
    'HAVELLS.NS'    : 'Consumer',

    # Telecom
    'BHARTIARTL.NS' : 'Telecom',
    'INDUSTOWER.NS' : 'Telecom',
}

MAX_PER_SECTOR = 2


class BharatCorrelationFilter:
    """Prevents overexposure to single Indian sector."""

    def __init__(self, max_per_sector=MAX_PER_SECTOR):
        self.max_per_sector = max_per_sector

    def get_sector(self, symbol):
        return INDIAN_STOCK_SECTORS.get(symbol, 'Unknown')

    def count_sector_positions(self, positions):
        sector_counts = {}
        for symbol in positions.keys():
            sector = self.get_sector(symbol)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        return sector_counts

    def can_add_position(self, symbol, current_positions):
        sector = self.get_sector(symbol)
        if sector == 'Unknown':
            return True

        sector_counts = self.count_sector_positions(current_positions)
        current_count = sector_counts.get(sector, 0)

        if current_count >= self.max_per_sector:
            logger.info(
                f"Correlation filter: {symbol} blocked "
                f"({sector} already has "
                f"{current_count}/{self.max_per_sector})"
            )
            return False
        return True

    def print_portfolio_sectors(self, positions):
        if not positions:
            print("   No open positions")
            return

        sector_counts = self.count_sector_positions(positions)
        print(f"\n   Portfolio Sector Breakdown:")
        for sector, count in sorted(sector_counts.items()):
            bar     = "█" * count
            limit   = "⚠️" if count >= self.max_per_sector else "✅"
            print(f"   {limit} {sector:<15}: {bar} ({count})")


if __name__ == '__main__':
    print("\nTesting BharatEdge Correlation Filter...")
    cf = BharatCorrelationFilter()

    test_positions = {
        'TCS.NS'       : {'shares': 5},
        'INFY.NS'      : {'shares': 3},
        'HDFCBANK.NS'  : {'shares': 4},
        'RELIANCE.NS'  : {'shares': 2},
    }

    print("\nCurrent portfolio:")
    cf.print_portfolio_sectors(test_positions)

    print("\nCan we add WIPRO.NS (IT)?")
    result = cf.can_add_position('WIPRO.NS', test_positions)
    print(f"Result: {'YES' if result else 'NO - Sector limit!'}")

    print("\nCan we add SUNPHARMA.NS (Pharma)?")
    result = cf.can_add_position('SUNPHARMA.NS', test_positions)
    print(f"Result: {'YES' if result else 'NO - Sector limit!'}")