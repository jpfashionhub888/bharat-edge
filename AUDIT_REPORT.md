# BharatEdge reliability and performance audit

Audit dates: 2026-08-26 and 2026-09-02

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
- Added missing runtime configuration support through `python-dotenv`.
- Isolated pytest discovery from ad-hoc network scripts and added regression
  coverage for the repaired safety paths.
- Ignored local audit/test environments and caches to prevent multi-gigabyte
  archives such as the supplied ZIP, whose bundled `venv` contained 60,143
  files and expanded the archive to about 2.3 GB.

## September 2026 upgrade

- Rejects NaN, infinite, negative, boolean, and malformed valuation inputs before
  they can crash or corrupt paper-trading state.
- Makes weekly loss a true circuit-breaker limit instead of a warning.
- Rechecks every risk condition after the 24-hour reset window, preventing an
  unsafe restart while drawdown remains above the configured limit.
- Loads `.env` files relative to the repository and accepts the same Telegram
  and Kite variable names used by deployment and GitHub Actions.
- Adds `/healthz` for dependency-free service monitoring.
- Removes fixed pytest temp paths that became undeletable on Windows.
- Adds GitHub Actions concurrency, regression tests, pip caching, and visible
  failures; runtime circuit-breaker/control state is no longer committed.
- Adds compatible dependency ranges to prevent uncontrolled major-version drift.
- Removes Kite Connect from the core paper-mode environment because its current
  release forces a vulnerable Autobahn dependency. The broker adapter now
  degrades safely when optional broker libraries are absent.

## Verification

- Python byte-compilation: pass (entire source tree)
- Critical static checks (`E9`, `F63`, `F7`, `F82`): pass
- Regression tests: 18 passed on a clean Python 3.14 environment
- Dependency consistency (`pip check`): pass
- Known-vulnerability audit (`pip-audit`): no known vulnerabilities in core
- GitHub Actions workflow YAML validation: pass
- Dashboard `/healthz` smoke test: pass
- Application health audit: 13/13 passed
- Dashboard smoke test: pass (10,523-byte HTML output)
- Telegram identity/read-only connection check: pass

## Important operational boundary

The audit deliberately did not run a live trading scan, place broker orders,
send trade messages, overwrite portfolio state, or deserialize the supplied
pickle model artifacts. Those actions have external/stateful or unsafe-code
execution effects and require a controlled staging run.

## Remaining dependency advisory

`kiteconnect==5.2.1` strictly pins `autobahn==19.11.2`, which is affected by
`PYSEC-2020-25`. It is excluded from the core/paper installation. Live broker
login remains disabled until Zerodha publishes a safe compatible dependency or
the broker adapter is replaced.
