# BharatEdge Operations

BharatEdge remains a supervised paper-trading system. Tests establish software
behavior; they do not establish profitability.

## Daily health

Check `/healthz`, the dashboard service, scan timer, and health-guard timer.
Treat degraded, overdue, stalled, invalid storage, or blocked entries as an
incident. Never replace missing market values manually.

## Backups and restore

State is backed up daily under `/var/backups/bharatedge` with SHA-256 checksums.
The `.env` file and credentials are deliberately excluded. Verify an archive:

`sudo /opt/bharatedge/ops/restore_state.sh ARCHIVE --verify-only`

Actual restore stops the scanner and dashboard and requires explicit `--restore`.
Take a fresh backup before any restore.

## Incident response

1. Preserve logs and the latest backup; do not delete damaged state.
2. Stop new scans if accounting, circuit-breaker, or storage integrity fails.
3. Inspect dashboard, scan, and health-guard service logs.
4. Verify backup checksums before recovery.
5. Resume only after `/healthz` and tests pass.

## Production validation

Observe all three weekday scans, provider coverage, equity-history accumulation,
bounded recovery, and Telegram alerts. Real-money trading requires independent
market data and statistically meaningful out-of-sample paper-trade evidence.
