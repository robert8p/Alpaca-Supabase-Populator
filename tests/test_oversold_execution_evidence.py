from app.oversold_features import _prior_history, _rsi14, _benchmark_return, execution_evidence
from datetime import datetime, UTC


def test_duplicate_and_invalid_history_cannot_create_extra_observations():
    good = {'t': '2026-08-31T04:00:00Z', 'c': 10, 'h': 11, 'l': 9}
    candidate = {'evidence_cutoff': '2026-09-02T15:00:00Z', 'history_bars': [good, dict(good), {'t':'2026-09-01T04:00:00Z','c':20,'h':11,'l':9}]}
    assert _prior_history(candidate) == [good]


def test_flat_prices_are_neutral_rsi():
    assert _rsi14([10.0] * 14, 10.0) == 50.0


def test_future_benchmark_cannot_create_relative_strength():
    context = {'snapshot': {'prevDailyBar': {'c':100}, 'latestTrade': {'p':90, 't':'2026-09-01T16:00:01Z'}, 'dailyBar': {'c':90}}}
    assert _benchmark_return(context, datetime(2026,9,1,16,tzinfo=UTC)) is None


def test_missing_crossed_and_future_quotes_are_explicit():
    empty = execution_evidence({})
    assert empty['spread_pct'] is None
    assert not empty['point_in_time_valid']
    candidate = {'evidence_cutoff':'2026-09-01T16:00:00Z', 'raw_snapshot': {'latestQuote': {'bp':11,'ap':10,'t':'2026-09-01T16:00:01Z'}, 'latestTrade': {'t':'2026-09-01T15:59:59Z'}}}
    actual = execution_evidence(candidate)
    assert actual['current_quote_valid'] is False
    assert actual['point_in_time_valid'] is False
    assert actual['quote_age_seconds'] == -1
    assert actual['spread_pct'] is None


def test_observed_quote_retains_friction_and_age_without_promising_fill():
    result = execution_evidence({'evidence_cutoff':'2026-09-01T16:00:00Z', 'raw_snapshot': {'latestQuote': {'bp':99,'ap':101,'t':'2026-09-01T15:59:58Z'}, 'latestTrade': {'t':'2026-09-01T15:59:59Z'}}})
    assert result['current_quote_valid'] and result['point_in_time_valid']
    assert result['spread_pct'] == 2.0
    assert result['quote_age_seconds'] == 2.0
    assert result['execution_price_basis'] == 'observed_quote_not_a_guaranteed_fill'


def test_minute_evidence_survives_active_scoring_chain():
    from app.oversold_scoring import score_candidate
    bars = [{'t':'2026-09-01T15:58:00Z','o':10,'h':11,'l':9,'c':10}]
    candidate = {'symbol':'TEST','name':'Test Issuer','last_price':10,'prev_close':12,'drop_pct':-16.67,
                 'prev_dollar_volume':10_000_000,'spread_pct':0.2,'evidence_cutoff':'2026-09-01T16:00:00Z',
                 'history_bars':[],'intraday_bars':bars}
    result = score_candidate(candidate, [], 'U', [])
    assert result['point_in_time_enrichment']['intraday_bars'] == bars
    assert '_v38_intraday_bars' not in candidate


def test_minute_fetch_excludes_unfinished_bar(monkeypatch):
    from types import SimpleNamespace
    from app import oversold_live_enrichment as live
    monkeypatch.setattr(live, 'get_settings', lambda: SimpleNamespace(alpaca_data_base_url='https://data.invalid', alpaca_headers={}))
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, params):
            assert params['timeframe'] == '1Min'
            assert params['adjustment'] == 'raw'
            return SimpleNamespace(raise_for_status=lambda:None, json=lambda:{'bars':{'TEST':[{'t':'2026-09-01T15:58:00Z'},{'t':'2026-09-01T15:59:00Z'},{'t':'2026-09-01T16:00:00Z'}]}})
    monkeypatch.setattr(live.httpx,'Client',Client)
    bars, count=live._fetch_intraday_evidence('TEST',datetime(2026,9,1,16,tzinfo=UTC))
    assert count == 1
    assert len(bars) == 2
    assert live._fetch_intraday_evidence('TEST',datetime(2026,9,6,16,tzinfo=UTC)) == ([],0)
