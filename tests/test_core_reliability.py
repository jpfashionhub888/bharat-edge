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


def test_closed_trade_is_persisted_and_reloaded(tmp_path):
    trades_file = tmp_path / "closed.json"
    tracker = TradeTracker(str(trades_file))
    tracker.record_trade("TEST.NS", 100, 110, 2, "TAKE PROFIT")

    reloaded = TradeTracker(str(trades_file))
    assert reloaded.get_stats()["total"] == 1
    assert reloaded.get_stats()["total_pnl"] == 20


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
    assert response.get_json()["status"] == "ok"
    assert _ist_now().utcoffset() == timedelta(hours=5, minutes=30)


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
