from generate_dashboard import load_nifty_data
import json

data = load_nifty_data()
print(f"Keys: {data.keys()}")
print(f"Dates count: {len(data.get('dates', []))}")
print(f"First 3 dates: {data.get('dates', [])[:3]}")
print(f"First 3 closes: {data.get('closes', [])[:3]}")
print(f"\nJSON sample:")
print(json.dumps({
    'dates' : data.get('dates', [])[:3],
    'opens' : data.get('opens', [])[:3],
    'highs' : data.get('highs', [])[:3],
    'lows'  : data.get('lows', [])[:3],
    'closes': data.get('closes', [])[:3],
}, indent=2))