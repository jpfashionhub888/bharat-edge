# BharatEdge reliability and performance audit

Audit date: 2026-08-26

## Outcome

The repaired source tree compiles, the focused reliability suite passes, the
dashboard generates successfully, and the project's own health audit passes
13/13 checks in an isolated environment.

## Corrected defects

- Fixed two source-level failures that prevented `generate_dashboard.py` and
  `phase9_zerodha.py` from compiling.
- Corrected confidence-based position sizing. Scanner confidence uses a 0–100
  percentage, while sizing expected 0–1; this could allocate up to 95% of cash
  despite the configured 15% cap.
- Enforced the circuit breaker at the actual order-entry decision point.
- Changed Telegram pause behavior so it blocks new entries without disabling
  stop-loss, take-profit, and trailing-stop management of existing positions.
- Connected `TradeTracker` to `BharatPaperTrader`, restoring closed-trade
  recording and downstream performance statistics.
- Added atomic persistence for circuit-breaker and trade-tracker state.
- Made corrupt portfolio/trade state fail safely instead of crashing startup.
- Removed model-evaluation leakage: the newest 20% is now held out before any
  model fit, evaluated out of sample, and only then included in a final
  production refit.
- Added missing runtime dependencies (`python-dotenv`, `kiteconnect`).
- Isolated pytest discovery from ad-hoc network scripts and added regression
  coverage for the repaired safety paths.
- Ignored local audit/test environments and caches to prevent multi-gigabyte
  archives such as the supplied ZIP, whose bundled `venv` contained 60,143
  files and expanded the archive to about 2.3 GB.

## Verification

- Python byte-compilation: pass (entire source tree)
- Critical static checks (`E9`, `F63`, `F7`, `F82`): pass
- Regression tests: 9 passed
- Application health audit: 13/13 passed
- Dashboard smoke test: pass (10,523-byte HTML output)
- Telegram identity/read-only connection check: pass

## Important operational boundary

The audit deliberately did not run a live trading scan, place broker orders,
send trade messages, overwrite portfolio state, or deserialize the supplied
pickle model artifacts. Those actions have external/stateful or unsafe-code
execution effects and require a controlled staging run.

## Remaining dependency advisory

`pip-audit` reports `PYSEC-2020-25` in `autobahn==19.11.2`. That version is
strictly pinned by the current `kiteconnect==5.2.1` package. Upgrading Autobahn
directly would create an unsatisfied dependency and was not forced. Broker login
should therefore run in an isolated environment until Zerodha publishes a
compatible dependency update or the broker adapter is replaced.
