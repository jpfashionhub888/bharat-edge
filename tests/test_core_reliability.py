import json

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


@pytest.mark.parametrize("price,strength", [(0, 1), (-1, 1), (100, -2), (100, "BUY")])
def test_invalid_position_inputs_cannot_open_trade(tmp_path, price, strength):
    trader = BharatPaperTrader(log_file=str(tmp_path / "state.json"))
    assert not trader.open_position("TEST.NS", price, strength)


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
