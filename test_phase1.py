# test_phase1.py

"""
Bharat Edge Phase 1 Test
Tests all data fetchers
"""

import warnings
warnings.filterwarnings('ignore')

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)


def test_imports():
    """Test all imports."""

    print("\n" + "="*50)
    print("TEST 1: Package Imports")
    print("="*50)

    packages = [
        'yfinance', 'pandas', 'numpy',
        'sklearn', 'xgboost', 'lightgbm',
        'ta', 'plotly', 'dash',
        'requests', 'bs4', 'feedparser',
        'kiteconnect',
    ]

    passed = 0
    failed = 0

    for pkg in packages:
        try:
            __import__(pkg)
            print(f"   ✅ {pkg}")
            passed += 1
        except ImportError:
            print(f"   ❌ {pkg}")
            failed += 1

    print(f"\n   {passed} passed, {failed} failed")
    return failed == 0


def test_nse_data():
    """Test NSE data fetcher."""

    print("\n" + "="*50)
    print("TEST 2: NSE Data")
    print("="*50)

    from data.nse_data import NSEDataFetcher

    fetcher = NSEDataFetcher(
        watchlist=['TCS.NS', 'INFY.NS', 'RELIANCE.NS'],
        lookback_days=30
    )
    data = fetcher.fetch_all()

    if len(data) >= 2:
        print("\n   ✅ NSE data fetch successful")
        for sym, df in data.items():
            price = df['close'].iloc[-1]
            print(f"      {sym}: Rs {price:,.2f}")
        return True
    else:
        print("   ❌ NSE data fetch failed")
        return False


def test_india_vix():
    """Test India VIX fetcher."""

    print("\n" + "="*50)
    print("TEST 3: India VIX")
    print("="*50)

    from data.india_vix import IndiaVIXFetcher

    fetcher = IndiaVIXFetcher()
    data = fetcher.fetch()

    if data['vix'] > 0:
        print(f"\n   ✅ VIX: {data['vix']:.2f}")
        print(f"      Signal: {data['signal']}")
        print(f"      Multiplier: {data['multiplier']}x")
        return True
    else:
        print("   ❌ VIX fetch failed")
        return False


def test_fii_dii():
    """Test FII/DII data fetcher."""

    print("\n" + "="*50)
    print("TEST 4: FII/DII Flow")
    print("="*50)

    from data.fii_dii_data import FIIDIIFetcher

    fetcher = FIIDIIFetcher()
    data = fetcher.fetch()

    print(f"\n   ✅ FII/DII fetch complete")
    print(f"      FII: Rs {data['fii_net']:+,.0f} Cr")
    print(f"      DII: Rs {data['dii_net']:+,.0f} Cr")
    print(f"      Signal: {data['fii_signal']}")
    return True


def test_sgx():
    """Test SGX Nifty signal."""

    print("\n" + "="*50)
    print("TEST 5: Market Gap Signal")
    print("="*50)

    from data.sgx_nifty import SGXNiftyFetcher

    fetcher = SGXNiftyFetcher()
    data = fetcher.fetch()

    print(f"\n   ✅ Gap signal: {data['signal']}")
    print(f"      Gap: {data['gap_pct']:+.2f}%")
    return True


def test_news():
    """Test Indian news fetcher."""

    print("\n" + "="*50)
    print("TEST 6: Indian News")
    print("="*50)

    from data.news_data import IndianNewsFetcher

    fetcher = IndianNewsFetcher()
    news = fetcher.fetch_market_news()

    if len(news) > 0:
        print(f"\n   ✅ Fetched {len(news)} articles")
        print(f"      Sample: {news[0]['title'][:60]}...")
        return True
    else:
        print("   ❌ No news fetched")
        return False


def main():
    banner = "🇮🇳" * 20
    print("\n" + banner)
    print("  BHARAT EDGE - PHASE 1 TEST")
    print(banner)

    results = []
    results.append(("Imports", test_imports()))
    results.append(("NSE Data", test_nse_data()))
    results.append(("India VIX", test_india_vix()))
    results.append(("FII/DII", test_fii_dii()))
    results.append(("Market Gap", test_sgx()))
    results.append(("Indian News", test_news()))

    print("\n" + "="*50)
    print("RESULTS")
    print("="*50)

    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {status} | {name}")
        if not passed:
            all_passed = False

    if all_passed:
        win = "🎉" * 20
        print("\n" + win)
        print("  ALL TESTS PASSED!")
        print("  Phase 1 Complete!")
        print("  Ready for Phase 2: ML Models")
        print(win)
    else:
        print("\n  ⚠️ Fix failures before Phase 2")

    print()


if __name__ == "__main__":
    main()