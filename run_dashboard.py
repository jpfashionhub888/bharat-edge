# run_dashboard.py
# BHARAT EDGE - Live Dashboard Launcher

"""
Launch the BharatEdge live dashboard.
Fetches live NSE prices every 30 seconds.
"""

import os
import warnings

os.environ['PYTHONWARNINGS'] = 'ignore'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')

import logging
logging.getLogger('joblib').setLevel(logging.ERROR)
logging.getLogger('sklearn').setLevel(logging.ERROR)

from monitoring.dashboard import create_app

print("\n" + "=" * 50)
print("  BHARAT EDGE LIVE DASHBOARD")
print("=" * 50)
print("\n  Open browser: http://localhost:8050")
print("  Live NSE prices | Refreshes every 30s")
print("  Press Ctrl+C to stop\n")

app = create_app()
app.run(debug=False, host='0.0.0.0', port=8050)
