import json
from datetime import datetime, timedelta, timezone

import pytest

import risk_circuit_breaker
from bharat_paper_trader import BharatPaperTrader
from monitoring.trade_tracker import TradeTracker


def test_percentage_confidence_respects_position_limit(tmp_path):
    trader = BharatPaperTrader(
        starting_capital=100_000,
        max_position_pct=0.15,
        log_file=str(tmp_path / "state.json"),
    )

    assert trader.open_position("TEST.NS", 100, 75)
    assert trader.positions["TEST.NS"]["cost"] == 11_200
    assert trader.positions["TEST.NS"]["cost"] <= 15_000
    buy = trader.trade_history[-1]
    assert buy["signal"] == 75
    assert buy["stop_loss_pct"] == 0.03


def test_regime_multiplier_reduces_size_without_losing_signal(tmp_path):
    trader = BharatPaperTrader(
        starting_capital=100_000,
        max_position_pct=0.15,
        log_file=str(tmp_path / "state.json"),
    )

    assert trader.open_position("TEST.NS", 100, 1.0, position_multiplier=0.5)
    assert trader.positions["TEST.NS"]["cost"] == 7_500
    assert trader.positions["TEST.NS"]["signal"] == 1.0
    assert trader.positions["TEST.NS"]["position_multiplier"] == 0.5


def test_position_mutations_are_persisted_immediately(tmp_path):
    state_file = tmp_path / "state.json"
    trader = BharatPaperTrader(log_file=str(state_file))

    assert trader.open_position("TEST.NS", 100, 1)
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert "TEST.NS" in saved["positions"]

    assert trader.close_position("TEST.NS", 110, "take_profit")
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert "TEST.NS" not in saved["positions"]
    assert saved["trade_history"][-1]["action"] == "SELL"


def test_failed_position_persistence_rolls_back_memory(tmp_path, monkeypatch):
    trader = BharatPaperTrader(log_file=str(tmp_path / "state.json"))
    starting_capital = trader.capital
    monkeypatch.setattr(
        trader,
        "save_state",
        lambda: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OSError, match="disk full"):
        trader.open_position("TEST.NS", 100, 1)

    assert trader.capital == starting_capital
    assert trader.positions == {}
    assert trader.trade_history == []


@pytest.mark.parametrize("price,strength", [(0, 1), (-1, 1), (100, -2), (100, "BUY")])
def test_invalid_position_inputs_cannot_open_trade(tmp_path, price, strength):
    trader = BharatPaperTrader(log_file=str(tmp_path / "state.json"))
    assert not trader.open_position("TEST.NS", price, strength)


@pytest.mark.parametrize("price,strength", [(float("nan"), 1), (100, float("nan")), (float("inf"), 1)])
def test_non_finite_position_inputs_cannot_open_trade(tmp_path, price, strength):
    trader = BharatPaperTrader(log_file=str(tmp_path / "state.json"))
    assert not trader.open_position("TEST.NS", price, strength)


def test_non_finite_price_cannot_update_position(tmp_path):
    trader = BharatPaperTrader(log_file=str(tmp_path / "state.json"))
    assert trader.open_position("TEST.NS", 100, 1)
    original = dict(trader.positions["TEST.NS"])

    assert not trader.update_position("TEST.NS", float("nan"))
    assert trader.positions["TEST.NS"] == original


def test_corrupt_portfolio_state_fails_safe(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text("not-json", encoding="utf-8")
    trader = BharatPaperTrader(starting_capital=123_456, log_file=str(state_file))
    trader.load_state()
    assert trader.capital == 123_456
    assert trader.positions == {}
    assert trader.state_healthy is False
    assert not trader.open_position("TEST.NS", 100, 1)


def test_invalid_saved_position_blocks_new_trades(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({
        "capital": 90_000,
        "starting_capital": 100_000,
        "positions": {
            "BROKEN.NS": {
                "shares": 10,
                "entry_price": 0,
                "highest_price": 100,
                "cost": 1_000,
            },
        },
        "trade_history": [],
    }), encoding="utf-8")
    trader = BharatPaperTrader(log_file=str(state_file))

    trader.load_state()

    assert trader.state_healthy is False
    assert not trader.open_position("TEST.NS", 100, 1)


def test_closed_trade_is_persisted_and_reloaded(tmp_path):
    trades_file = tmp_path / "closed.json"
    tracker = TradeTracker(str(trades_file))
    tracker.record_trade("TEST.NS", 100, 110, 2, "TAKE PROFIT")

    reloaded = TradeTracker(str(trades_file))
    assert reloaded.get_stats()["total"] == 1
    assert reloaded.get_stats()["total_pnl"] == 20


@pytest.mark.parametrize(
    "entry,exit_price,shares",
    [(0, 110, 2), (100, float("nan"), 2), (100, 110, 0), (100, 110, True)],
)
def test_invalid_closed_trade_is_rejected(tmp_path, entry, exit_price, shares):
    tracker = TradeTracker(str(tmp_path / "closed.json"))
    with pytest.raises(ValueError):
        tracker.record_trade("TEST.NS", entry, exit_price, shares, "SIGNAL")
    assert tracker.get_stats()["total"] == 0


def test_closed_trade_write_failure_is_not_reported_as_success(tmp_path, monkeypatch):
    tracker = TradeTracker(str(tmp_path / "closed.json"))
    monkeypatch.setattr(
        tracker,
        "_save",
        lambda: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OSError, match="disk full"):
        tracker.record_trade("TEST.NS", 100, 110, 2, "TAKE PROFIT")

    assert tracker.get_trades() == []
    assert tracker.get_stats()["total"] == 0


def test_corrupt_closed_trade_history_blocks_overwrite(tmp_path):
    trades_file = tmp_path / "closed.json"
    trades_file.write_text("not-json", encoding="utf-8")
    tracker = TradeTracker(str(trades_file))

    assert tracker.healthy is False
    with pytest.raises(RuntimeError, match="unhealthy"):
        tracker.record_trade("TEST.NS", 100, 110, 2, "TAKE PROFIT")
    assert trades_file.read_text(encoding="utf-8") == "not-json"


def test_circuit_breaker_blocks_total_loss_and_writes_valid_state(tmp_path, monkeypatch):
    state_file = tmp_path / "circuit.json"
    monkeypatch.setattr(risk_circuit_breaker, "CIRCUIT_BREAKER_FILE", str(state_file))
    breaker = risk_circuit_breaker.RiskCircuitBreaker()

    assert breaker.check(89_000, 100_000)
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["triggered"] is True
    assert "Total loss limit" in saved["trigger_reason"]


def test_circuit_breaker_fails_closed_for_invalid_valuation(tmp_path, monkeypatch):
    state_file = tmp_path / "circuit.json"
    monkeypatch.setattr(risk_circuit_breaker, "CIRCUIT_BREAKER_FILE", str(state_file))
    breaker = risk_circuit_breaker.RiskCircuitBreaker()

    assert breaker.check(float("nan"), 100_000)
    assert breaker.is_triggered()


@pytest.mark.parametrize(
    "contents",
    ["not-json", "[]", '{"triggered": "no"}', '{"triggered": false, "daily_start_val": "bad"}'],
)
def test_corrupt_circuit_breaker_state_fails_closed(tmp_path, monkeypatch, contents):
    state_file = tmp_path / "circuit.json"
    state_file.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(risk_circuit_breaker, "CIRCUIT_BREAKER_FILE", str(state_file))

    breaker = risk_circuit_breaker.RiskCircuitBreaker()

    assert breaker.is_triggered()
    assert "manual review" in breaker.get_status()["reason"]


def test_expired_breaker_rechecks_persistent_loss(tmp_path, monkeypatch):
    state_file = tmp_path / "circuit.json"
    monkeypatch.setattr(risk_circuit_breaker, "CIRCUIT_BREAKER_FILE", str(state_file))
    breaker = risk_circuit_breaker.RiskCircuitBreaker()
    breaker.state.update({
        "triggered": True,
        "trigger_reason": "prior loss",
        "trigger_date": (datetime.now() - timedelta(days=2)).isoformat(),
        "daily_start": datetime.now().strftime("%Y-%m-%d"),
        "daily_start_val": 100_000,
        "weekly_start": (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d"),
        "weekly_start_val": 100_000,
    })

    assert breaker.check(89_000, 100_000)
    assert breaker.is_triggered()


def test_weekly_loss_limit_stops_trading(tmp_path, monkeypatch):
    state_file = tmp_path / "circuit.json"
    monkeypatch.setattr(risk_circuit_breaker, "CIRCUIT_BREAKER_FILE", str(state_file))
    breaker = risk_circuit_breaker.RiskCircuitBreaker()
    now = datetime.now()
    breaker.state.update({
        "weekly_start": (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d"),
        "weekly_start_val": 100_000,
        "daily_start": now.strftime("%Y-%m-%d"),
        "daily_start_val": 93_000,
    })

    assert breaker.check(92_900, 100_000)
    assert "Weekly loss limit" in breaker.state["trigger_reason"]


def test_dashboard_health_endpoint():
    from monitoring.dashboard import _ist_now, create_app

    client = create_app().server.test_client()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json()["status"] in {"ok", "degraded"}
    assert _ist_now().utcoffset() == timedelta(hours=5, minutes=30)


def test_dashboard_marks_corrupt_state_instead_of_presenting_default_as_real(tmp_path):
    from monitoring.dashboard import _safe_load

    state_file = tmp_path / "portfolio.json"
    state_file.write_text("not-json", encoding="utf-8")

    loaded = _safe_load(state_file, {"capital": 100_000})

    assert loaded["capital"] == 100_000
    assert loaded["_storage_status"] == "INVALID"


def test_dashboard_identifies_backup_recovery(tmp_path):
    from monitoring.dashboard import _safe_load

    state_file = tmp_path / "portfolio.json"
    state_file.write_text("not-json", encoding="utf-8")
    backup = state_file.with_suffix(".json.bak")
    backup.write_text(json.dumps({"capital": 91_000}), encoding="utf-8")

    loaded = _safe_load(state_file, {"capital": 100_000})

    assert loaded["capital"] == 91_000
    assert loaded["_storage_status"] == "BACKUP"


def test_dashboard_refresh_control_and_all_tabs_are_wired(monkeypatch):
    import monitoring.dashboard as dashboard

    monkeypatch.setattr(dashboard, "get_market_data", lambda symbols=None: {
        "prices": {}, "nifty": None, "vix": None, "fetched_at": None,
        "error": "offline", "stale": True,
    })
    monkeypatch.setattr(dashboard, "_upcoming_earnings", lambda: [])
    app = dashboard.create_app()

    def component_ids(component):
        found = set()
        component_id = getattr(component, "id", None)
        if component_id:
            found.add(component_id)
        children = getattr(component, "children", None)
        if children is None:
            return found
        if not isinstance(children, (list, tuple)):
            children = [children]
        for child in children:
            if hasattr(child, "children") or getattr(child, "id", None):
                found.update(component_ids(child))
        return found

    ids = component_ids(app.layout)
    assert {"refresh-now", "tabs", "status-bar", "tab-content"} <= ids
    callback_inputs = str(app.callback_map)
    assert "refresh-now" in callback_inputs
    assert "width=device-width" in str(app.config.meta_tags)


def test_every_dashboard_tab_renders_without_external_data(monkeypatch):
    import monitoring.dashboard as dashboard

    monkeypatch.setattr(dashboard, "get_market_data", lambda symbols=None: {
        "prices": {}, "nifty": None, "vix": None, "fetched_at": None,
        "error": "offline", "stale": True,
    })
    monkeypatch.setattr(dashboard, "_upcoming_earnings", lambda: [])

    renderers = (
        dashboard._tab_overview,
        dashboard._tab_positions,
        dashboard._tab_signals,
        dashboard._tab_sectors,
        dashboard._tab_earnings,
        dashboard._tab_history,
        dashboard._tab_sysconfig,
    )
    for renderer in renderers:
        rendered = renderer()
        assert getattr(rendered, "children", None) is not None


def test_dashboard_tables_use_supported_sortable_grid():
    import dash_ag_grid as dag
    from monitoring.dashboard import _dtable

    grid = _dtable([{"Symbol": "TEST", "Signal": "BUY"}], page=10)

    assert isinstance(grid, dag.AgGrid)
    assert grid.defaultColDef["sortable"] is True
    assert grid.defaultColDef["filter"] is True
    assert grid.dashGridOptions["paginationPageSize"] == 10


def test_dashboard_does_not_calculate_unrealized_values_from_stale_prices(monkeypatch):
    import monitoring.dashboard as dashboard

    monkeypatch.setattr(dashboard, "load_portfolio", lambda: {
        "capital": 90_000,
        "starting_capital": 100_000,
        "positions": {"TEST.NS": {
            "shares": 10, "entry_price": 100, "current_price": 999,
            "cost": 1_000, "highest_price": 999, "signal": 0.8,
        }},
        "trade_history": [],
    })
    monkeypatch.setattr(dashboard, "get_market_data", lambda symbols=None: {
        "prices": {"TEST.NS": 999}, "nifty": None, "vix": None,
        "fetched_at": "2026-09-01T10:00:00+05:30",
        "error": "provider offline", "stale": True,
    })

    rendered = str(dashboard._tab_positions())

    assert "UNAVAILABLE" in rendered
    assert "STALE/FALLBACK" not in rendered
    assert "+8,990.00" not in rendered


def test_scan_lifecycle_records_success(tmp_path, monkeypatch):
    import bharat_cloud_scan

    status_file = tmp_path / "scan_status.json"
    monkeypatch.setattr(bharat_cloud_scan, "SCAN_STATUS_FILE", str(status_file))
    monkeypatch.setattr(bharat_cloud_scan, "run_bharat_scan", lambda: None)

    bharat_cloud_scan.main(force=True)

    status = json.loads(status_file.read_text(encoding="utf-8"))
    assert status["status"] == "SUCCESS"
    assert status["last_success_at"]
    assert status["duration_seconds"] >= 0


def test_scan_lifecycle_records_failure(tmp_path, monkeypatch):
    import bharat_cloud_scan

    status_file = tmp_path / "scan_status.json"
    monkeypatch.setattr(bharat_cloud_scan, "SCAN_STATUS_FILE", str(status_file))
    monkeypatch.setattr(
        bharat_cloud_scan,
        "run_bharat_scan",
        lambda: (_ for _ in ()).throw(RuntimeError("provider offline")),
    )

    with pytest.raises(SystemExit):
        bharat_cloud_scan.main(force=True)

    status = json.loads(status_file.read_text(encoding="utf-8"))
    assert status["status"] == "FAILED"
    assert "provider offline" in status["error"]


def test_failed_scan_preserves_previous_success_time(tmp_path, monkeypatch):
    import bharat_cloud_scan

    status_file = tmp_path / "scan_status.json"
    last_success = "2026-09-04T09:50:00+05:30"
    status_file.write_text(json.dumps({
        "status": "SUCCESS",
        "last_success_at": last_success,
    }), encoding="utf-8")
    monkeypatch.setattr(bharat_cloud_scan, "SCAN_STATUS_FILE", str(status_file))

    bharat_cloud_scan._write_scan_status("FAILED", error="offline")

    status = json.loads(status_file.read_text(encoding="utf-8"))
    assert status["status"] == "FAILED"
    assert status["last_success_at"] == last_success


def test_scan_overdue_respects_schedule_and_grace_period():
    from monitoring.dashboard import _scan_is_overdue

    # Friday's 09:45 UTC scan is not overdue until its one-hour grace expires.
    before_deadline = datetime(2026, 9, 4, 10, 30, tzinfo=timezone.utc)
    assert not _scan_is_overdue("2026-09-04T07:05:00+00:00", before_deadline)

    after_deadline = datetime(2026, 9, 4, 10, 50, tzinfo=timezone.utc)
    assert _scan_is_overdue("2026-09-04T07:05:00+00:00", after_deadline)
    assert not _scan_is_overdue("2026-09-04T09:50:00+00:00", after_deadline)


def test_scan_overdue_does_not_expect_weekend_runs():
    from monitoring.dashboard import _scan_is_overdue

    saturday = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
    assert not _scan_is_overdue("2026-09-04T09:50:00+00:00", saturday)


def test_stalled_scan_is_distinguished_from_active_scan():
    from monitoring.dashboard import _scan_run_stalled

    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    assert not _scan_run_stalled({
        "status": "RUNNING",
        "started_at": "2026-09-04T11:30:00+00:00",
    }, now)
    assert _scan_run_stalled({
        "status": "RUNNING",
        "started_at": "2026-09-04T10:30:00+00:00",
    }, now)
    assert not _scan_run_stalled({
        "status": "SUCCESS",
        "started_at": "2026-09-04T10:30:00+00:00",
    }, now)


def test_scan_workflow_retries_publish_without_force_push():
    from pathlib import Path

    workflow_path = (
        Path(__file__).resolve().parents[1]
        / ".github" / "workflows" / "daily_scan.yml"
    )
    if not workflow_path.exists():
        pytest.skip("CI workflow metadata is not part of this runtime package")
    workflow = workflow_path.read_text(encoding="utf-8")
    assert "git fetch origin main" in workflow
    assert "git rebase origin/main" in workflow
    assert "for attempt in 1 2 3" in workflow
    assert "push --force" not in workflow
    assert "push -f" not in workflow


@pytest.mark.parametrize("cache", [
    {"last_trained": "not-a-date", "retrain_days": 30},
    {"last_trained": datetime.now().isoformat(), "retrain_days": 0},
    {"last_trained": datetime.now().isoformat(), "retrain_days": 9999},
    {"last_trained": "2999-01-01T00:00:00", "retrain_days": 30},
])
def test_invalid_model_cache_metadata_requires_retraining(tmp_path, monkeypatch, cache):
    import bharat_model_cache

    cache_file = tmp_path / "cache.json"
    cache_file.write_text(json.dumps(cache), encoding="utf-8")
    monkeypatch.setattr(bharat_model_cache, "CACHE_INFO_FILE", str(cache_file))

    assert bharat_model_cache.should_retrain() is True


def test_model_cache_save_is_valid_json(tmp_path, monkeypatch):
    import bharat_model_cache

    cache_file = tmp_path / "cache.json"
    monkeypatch.setattr(bharat_model_cache, "CACHE_INFO_FILE", str(cache_file))
    bharat_model_cache.save_cache_info({"last_trained": "2026-09-04T00:00:00"})

    assert json.loads(cache_file.read_text(encoding="utf-8"))["last_trained"]
    assert not (tmp_path / "cache.json.tmp").exists()


def test_market_regime_fails_closed_without_nifty(monkeypatch):
    from bharat_market_regime import BharatMarketRegimeFilter

    regime = BharatMarketRegimeFilter()
    monkeypatch.setattr(regime, "get_nifty_data", lambda: None)
    result = regime.analyze()

    assert result["can_trade"] is False
    assert result["regime"] == "UNKNOWN"
    assert result["data_status"] == "UNAVAILABLE"


def test_market_regime_fails_closed_for_stale_nifty(monkeypatch):
    import pandas as pd
    from bharat_market_regime import BharatMarketRegimeFilter

    regime = BharatMarketRegimeFilter()
    old_index = pd.date_range(end=datetime.now() - timedelta(days=10), periods=70, freq="D")
    history = pd.DataFrame({"close": range(100, 170)}, index=old_index)
    monkeypatch.setattr(regime, "get_nifty_data", lambda: history)
    monkeypatch.setattr(regime, "get_india_vix", lambda: 14.0)

    result = regime.analyze()
    assert result["can_trade"] is False
    assert "stale" in result["reason"].lower()


def test_caution_regime_reduces_position_size(monkeypatch):
    import pandas as pd
    from bharat_market_regime import BharatMarketRegimeFilter

    regime = BharatMarketRegimeFilter()
    index = pd.date_range(end=datetime.now(), periods=70, freq="D")
    close = [100.0] * 49 + list(pd.Series(range(21)).map(lambda i: 100 - i * 0.2))
    history = pd.DataFrame({"close": close}, index=index)
    monkeypatch.setattr(regime, "get_nifty_data", lambda: history)
    monkeypatch.setattr(regime, "get_india_vix", lambda: 14.0)

    result = regime.analyze()
    assert result["regime"] == "CAUTION"
    assert result["can_trade"] is True
    assert result["position_multiplier"] == 0.5


def test_market_context_rejects_missing_critical_sources(monkeypatch):
    import phase6_market_data

    monkeypatch.setattr(phase6_market_data, "get_market_snapshot", lambda: {
        "timestamp": "2026-09-03T00:00:00+00:00",
        "vix": {"available": False, "error": "offline"},
        "nifty": {"available": True, "regime": "BULL", "price": 25000},
        "fii_dii": {"available": False, "direction": "UNKNOWN"},
        "sgx": {"available": False, "is_proxy": True},
    })

    with pytest.raises(phase6_market_data.MarketDataUnavailable):
        phase6_market_data.get_live_market_context()


def test_market_context_does_not_invent_flow_or_gift_values(monkeypatch):
    import phase6_market_data

    observed = datetime.now(timezone.utc).isoformat()

    monkeypatch.setattr(phase6_market_data, "get_market_snapshot", lambda: {
        "timestamp": "2026-09-03T00:00:00+00:00",
        "vix": {"available": True, "value": 14.2, "change_pct": -1.0, "regime": "LOW_RISK", "as_of": observed},
        "nifty": {"available": True, "regime": "BULL", "price": 25000, "as_of": observed},
        "fii_dii": {"available": True, "direction": "INFLOW", "is_proxy": True},
        "sgx": {"available": True, "gap_pct": 1.5, "is_proxy": True},
    })

    context, _ = phase6_market_data.get_live_market_context()
    assert context["fii_net"] == 0.0
    assert context["sgx_gap"] == 0.0
    assert context["news_volume"] == 0
    assert context["_data_quality"]["status"] == "DEGRADED"


def test_market_context_rejects_stale_critical_quotes(monkeypatch):
    import phase6_market_data

    stale = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    monkeypatch.setattr(phase6_market_data, "get_market_snapshot", lambda: {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vix": {"available": True, "value": 14.2, "change_pct": 0.0, "as_of": stale},
        "nifty": {"available": True, "regime": "BULL", "price": 25000, "as_of": stale},
        "fii_dii": {"available": False, "direction": "UNKNOWN"},
        "sgx": {"available": False, "is_proxy": True},
    })

    with pytest.raises(phase6_market_data.MarketDataUnavailable, match="stale"):
        phase6_market_data.get_live_market_context()


def test_runtime_risk_limits_match_displayed_configuration():
    from config import settings

    assert risk_circuit_breaker.DAILY_LOSS_LIMIT == settings.MAX_DAILY_LOSS
    assert risk_circuit_breaker.WEEKLY_LOSS_LIMIT == settings.MAX_WEEKLY_LOSS
    assert risk_circuit_breaker.TOTAL_LOSS_LIMIT == settings.MAX_DRAWDOWN


def test_dashboard_parses_both_yahoo_column_layouts():
    import pandas as pd
    from monitoring.dashboard import _latest_close

    index = pd.date_range("2026-08-26 09:15", periods=2, freq="min")
    ticker_first = pd.DataFrame(
        [[100.0], [105.0]], index=index,
        columns=pd.MultiIndex.from_tuples([("TEST.NS", "Close")]),
    )
    field_first = pd.DataFrame(
        [[100.0], [106.0]], index=index,
        columns=pd.MultiIndex.from_tuples([("Close", "TEST.NS")]),
    )

    assert _latest_close(ticker_first, "TEST.NS") == 105.0
    assert _latest_close(field_first, "TEST.NS") == 106.0


def test_sector_tab_uses_real_snapshot_when_no_stock_signals(monkeypatch):
    import monitoring.dashboard as dashboard

    monkeypatch.setattr(dashboard, "load_scan", lambda: {
        "scan_time": "2026-09-04T09:15:00+05:30",
        "signals": [],
        "sectors": [{
            "sector": "BANKING",
            "status": "OVERWEIGHT",
            "score": 72.5,
            "momentum_1w": 1.2,
            "momentum_1m": 3.4,
            "momentum_3m": 7.8,
            "relative_strength": 2.1,
            "trend_score": 80.0,
            "volatility_score": 65.0,
            "allocation_multiplier": 1.2,
            "source": "Yahoo Finance sector proxies",
        }],
    })

    rendered = str(dashboard._tab_sectors().to_plotly_json())
    assert "BANKING" in rendered
    assert "Yahoo Finance sector proxies" in rendered
    assert "Run a scan to populate sector data" not in rendered


def test_health_guard_scan_retry_is_bounded(tmp_path, monkeypatch):
    import monitoring.health_guard as guard
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(guard, "STATE_FILE", tmp_path / "guard.json")
    monkeypatch.setattr(guard, "_notify", lambda message: None)
    monkeypatch.setattr(guard.shutil, "disk_usage", lambda path: type(
        "Usage", (), {"total": 100, "free": 50})())
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self): return json.dumps({
            "scan_overdue": True, "scan_stalled": False,
            "portfolio_storage": "PRIMARY", "circuit_storage": "PRIMARY"}).encode()
    monkeypatch.setattr(guard, "urlopen", lambda *args, **kwargs: Response())
    calls = []
    monkeypatch.setattr(guard, "_systemctl", lambda *args: (
        calls.append(args) or type("Result", (), {"returncode": 3})()))
    guard.run_guard(now)
    guard.run_guard(now + timedelta(minutes=5))
    assert calls.count(("start", "--no-block", "bharatedge-scan.service")) == 1


def test_equity_history_records_only_real_bounded_snapshots(tmp_path):
    import monitoring.equity_history as equity
    path = tmp_path / "equity.json"
    equity.record_snapshot(100100, 50, 50, 1, at="2026-09-05T10:00:00+05:30", path=path)
    equity.record_snapshot(100250, 50, 200, 1, at="2026-09-05T12:00:00+05:30", path=path)
    points = equity.load_history(path)
    assert [p["total_value"] for p in points] == [100100.0, 100250.0]
    assert points[-1]["realized_pnl"] + points[-1]["unrealized_pnl"] == 250
    with pytest.raises(ValueError):
        equity.record_snapshot(float("nan"), 0, 0, 0, path=path)


def test_cloud_scan_does_not_feed_fixed_vix_to_sector_rotation():
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "bharat_cloud_scan.py").read_text(encoding="utf-8")
    assert "vix_value=17.0" not in source
    assert "fii_net=None" in source
    assert "validated India VIX unavailable; sector rotation withheld" in source


def test_alternate_production_runners_do_not_invent_market_context():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    daily = (root / "run_daily.py").read_text(encoding="utf-8")
    retrain = (root / "retrain_and_upload.py").read_text(encoding="utf-8")
    assert "vix_value=17.0" not in daily
    assert "validated market context unavailable; scan withheld" in daily
    for invented in ("vix_value   = 17.21", "fii_net     = 500", "sgx_gap     = 0.65"):
        assert invented not in retrain


def test_earnings_tab_discloses_provider_coverage(monkeypatch):
    import monitoring.dashboard as dashboard
    monkeypatch.setattr(dashboard, "_upcoming_earnings", lambda: [])
    monkeypatch.setitem(dashboard._EARNINGS_CACHE, "requested", 20)
    monkeypatch.setitem(dashboard._EARNINGS_CACHE, "verified", 0)
    monkeypatch.setitem(dashboard._EARNINGS_CACHE, "error", "provider unavailable")
    rendered = str(dashboard._tab_earnings().to_plotly_json())
    assert "verified 0/20" in rendered
    assert "provider unavailable" in rendered
    assert "No provider-verified upcoming earnings dates" in rendered


def test_fii_fetch_failure_is_not_numeric_neutral():
    from data.fii_dii_data import FIIDIIFetcher
    unavailable = FIIDIIFetcher()._get_default()
    assert unavailable["available"] is False
    assert unavailable["fii_net"] is None
    assert unavailable["dii_net"] is None
    assert unavailable["fii_signal"] == "UNAVAILABLE"


def test_telegram_morning_report_has_no_fixed_market_scenario():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "phase6_telegram.py").read_text(encoding="utf-8")
    assert "vix_value = 17.21" not in source
    assert "fii_net   = 500" not in source
    assert "fii_net=None" in source


def test_model_holdout_is_not_used_for_initial_fit(monkeypatch):
    import numpy as np
    import pandas as pd
    import phase2_models

    X = pd.DataFrame({"feature": np.arange(20)})
    y = pd.Series([0, 1] * 10)

    class FakeModel:
        def __init__(self):
            self.fit_sizes = []

        def fit(self, features, target):
            self.fit_sizes.append(len(features))
            return self

        def predict_proba(self, features):
            up = (features["feature"].to_numpy() % 2).astype(float) * 0.6 + 0.2
            return np.column_stack([1 - up, up])

        def predict(self, features):
            return (self.predict_proba(features)[:, 1] >= 0.5).astype(int)

    class FakeScaler:
        def __init__(self):
            self.fit_sizes = []

        def fit(self, features):
            self.fit_sizes.append(len(features))
            return self

    model = FakeModel()
    scaler = FakeScaler()
    monkeypatch.setattr(
        phase2_models,
        "prepare_training_data",
        lambda **kwargs: (X, y, ["feature"]),
    )
    def fake_train(features, target, n_splits):
        model.fit(features, target)
        scaler.fit(features)
        return {"fake": model}, {}, scaler

    monkeypatch.setattr(phase2_models, "train_base_models", fake_train)

    result = phase2_models.train_full_ensemble(["TEST"], save_models=False)
    assert result
    assert model.fit_sizes == [16, 20]
    assert scaler.fit_sizes == [16, 20]
