"""Deterministic writable cache configuration for yfinance."""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def configure_yfinance(yf_module) -> Path:
    """Point yfinance's SQLite caches at a writable application directory."""
    configured = os.getenv("YFINANCE_CACHE_DIR", "").strip()
    cache_dir = Path(configured).expanduser() if configured else ROOT / "logs" / ".yfinance-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    yf_module.set_tz_cache_location(str(cache_dir.resolve()))
    return cache_dir
