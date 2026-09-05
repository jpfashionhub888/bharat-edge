"""Durable, bounded portfolio valuation history recorded after real scans."""
from __future__ import annotations
import json, math, os, shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT / "logs" / "equity_history.json"
MAX_POINTS = 1000

def load_history(path: Path = HISTORY_FILE) -> list[dict]:
    for candidate in (path, path.with_suffix(path.suffix + ".bak")):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            points = data.get("points") if isinstance(data, dict) else None
            if isinstance(points, list): return points
        except (OSError, ValueError, TypeError): pass
    return []

def record_snapshot(total_value, realized_pnl, unrealized_pnl,
                    open_positions, at=None, path: Path = HISTORY_FILE):
    numbers = (total_value, realized_pnl, unrealized_pnl)
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in numbers):
        raise ValueError("equity snapshot contains a non-finite value")
    if total_value <= 0 or not isinstance(open_positions, int) or open_positions < 0:
        raise ValueError("equity snapshot values are invalid")
    stamp = at or datetime.now(timezone.utc).isoformat()
    points = load_history(path)
    point = {"timestamp": stamp, "total_value": round(float(total_value), 2),
             "realized_pnl": round(float(realized_pnl), 2),
             "unrealized_pnl": round(float(unrealized_pnl), 2),
             "open_positions": open_positions}
    if points and points[-1].get("timestamp") == stamp: points[-1] = point
    else: points.append(point)
    points = points[-MAX_POINTS:]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp, backup = path.with_suffix(".tmp"), path.with_suffix(path.suffix + ".bak")
    tmp.write_text(json.dumps({"points": points}, indent=2), encoding="utf-8")
    if path.exists(): shutil.copy2(path, backup)
    os.replace(tmp, path)
    return point
