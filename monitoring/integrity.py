"""Accounting, model provenance, and tamper-evident audit helpers."""
from __future__ import annotations
import hashlib, json, math, os
from datetime import datetime, timezone
from pathlib import Path

def accounting_error(state: dict, tolerance: float = 0.05) -> str | None:
    """Check cash + open cost basis == starting capital + realized P&L."""
    try:
        cash = float(state["capital"]); start = float(state["starting_capital"])
        positions = state.get("positions", {}); trades = state.get("trade_history", [])
        open_cost = sum(float(p["cost"]) for p in positions.values())
        realized = sum(float(t.get("pnl", 0)) for t in trades if t.get("action") == "SELL")
        values = (cash, start, open_cost, realized)
        if not all(math.isfinite(v) for v in values): return "non-finite accounting value"
        difference = (cash + open_cost) - (start + realized)
        if abs(difference) > tolerance:
            return f"book balance differs by {difference:.2f}"
        return None
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return f"accounting fields invalid: {exc}"

def model_provenance(model_dir: str | Path = "models") -> dict:
    files = []
    for path in sorted(Path(model_dir).glob("*.pkl")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({"name": path.name, "sha256": digest,
                      "size_bytes": path.stat().st_size,
                      "modified_utc": datetime.fromtimestamp(
                          path.stat().st_mtime, timezone.utc).isoformat()})
    manifest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest() if files else None
    return {"status": "VERIFIED" if files else "UNAVAILABLE", "files": files,
            "manifest_sha256": manifest,
            "generated_utc": datetime.now(timezone.utc).isoformat()}

def append_audit_record(path: str | Path, event: str, payload: dict) -> dict:
    """Append a hash-chained record; the journal is evidence, not account state."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    previous_hash = None
    if path.exists():
        with path.open("rb") as handle:
            lines = [line for line in handle if line.strip()]
        if lines: previous_hash = json.loads(lines[-1])["record_hash"]
    record = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "event": event, "payload": payload, "previous_hash": previous_hash}
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    record["record_hash"] = hashlib.sha256(canonical).hexdigest()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush(); os.fsync(handle.fileno())
    return record

def verify_audit_journal(path: str | Path) -> tuple[bool, str]:
    previous = None
    try:
        for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip(): continue
            record = json.loads(line); supplied = record.pop("record_hash")
            expected = hashlib.sha256(json.dumps(
                record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if supplied != expected or record.get("previous_hash") != previous:
                return False, f"hash chain invalid at record {number}"
            previous = supplied
        return True, "ok"
    except Exception as exc: return False, str(exc)
