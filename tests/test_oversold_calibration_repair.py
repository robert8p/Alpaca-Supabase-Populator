from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import oversold_calibration as calibration
from app import oversold_calibration_runtime as runtime
from app import oversold_calibration_status as health
from app import oversold_outcomes as outcomes
from app import oversold_outcomes_v33 as paths
from app import oversold_three_session_target as target

NOW = datetime(2026, 9, 7, 22, 0, tzinfo=UTC)


def row(**changes):
    value = dict(outcome_id=1, signal_timestamp=NOW - timedelta(days=8),
                 last_evaluated_at=NOW, error=None, path_error=None,
                 corporate_action_status='unchecked', window_end=NOW - timedelta(days=4),
                 target_definition=health.TARGET, target_matured='true', path_matured='true',
                 path_contract='completed_sessions_v2', calendar_verified='true',
                 target_contract='three_session_target_v3')
    return {**value, **changes}


def sample_rows(count=360, *, outcome_days=3):
    start = datetime(2025, 9, 1, 21, 0, tzinfo=UTC)
    return [dict(score=80.0 if i % 2 else 20.0, target=bool(i % 2),
                 signal_timestamp=start + timedelta(days=i),
                 outcome_end=start + timedelta(days=i + outcome_days),
                 run_kind='original', evidence_snapshot_id=i + 1, symbol=f'S{i}', sector='unknown')
            for i in range(count)]


def test_unmatured_current_model_does_not_borrow_old_scores():
    future = row(window_end=NOW + timedelta(days=3), target_matured=False, path_matured=False,
                 calendar_verified=False, last_evaluated_at=None)
    result = health.build_pipeline_status([future] * 36, [], now=NOW,
                                          historical_signals=673, excluded_rescores=2000)
    assert result['stage'] == 'collecting_outcomes'
    assert result['model_status'] == 'uncalibrated'
    assert result['counts']['scored_signals'] == 36
    assert result['counts']['independent_eligible_samples'] == 0
    assert result['counts']['older_model_originals_excluded'] == 673
    assert result['next_target_window_end'] == (NOW + timedelta(days=3)).isoformat()
    assert result['next_policy_review_at'] == (NOW + timedelta(days=33)).isoformat()
    assert result['readiness']['requirements']['minimum_matured_signals'] == 300
    assert result['readiness']['requirements']['minimum_independent_signal_days'] == 30


@pytest.mark.parametrize('change', [
    {'window_end': NOW + timedelta(seconds=1)},
    {'window_end': None}, {'window_end': NOW - timedelta(days=20)},
    {'target_matured': False}, {'path_matured': False}, {'calendar_verified': False},
    {'path_contract': 'old'}, {'target_contract': 'old'}, {'target_definition': 'six_weeks'},
])
def test_maturity_requires_every_contract_check(change):
    result = health.build_pipeline_status([row(**change)], [], now=NOW)
    assert result['counts']['matured_outcomes'] == 0
    assert result['model_status'] == 'uncalibrated'


def test_review_policy_lag_is_not_removed_to_make_calibration_pass():
    result = health.build_pipeline_status([row()], [], now=NOW)
    assert result['stage'] == 'waiting_for_review'
    assert result['counts']['waiting_review_lag'] == 1
    assert result['counts']['reviews_due'] == 0
    assert result['corporate_action_review_lag_days'] == 30
    assert result['next_policy_review_at'] == (NOW + timedelta(days=26)).isoformat()


def test_reviews_past_policy_date_are_reported_as_due():
    result = health.build_pipeline_status([row(signal_timestamp=NOW - timedelta(days=40),
                                              window_end=NOW - timedelta(days=35))], [], now=NOW)
    assert result['stage'] == 'processing_due'
    assert result['counts']['reviews_due'] == 1


@pytest.mark.parametrize('change', [{'outcome_id': None}, {'error': 'provider error'},
                                   {'path_error': 'ValueError'}, {'corporate_action_status': 'review_error'}])
def test_processing_errors_are_not_silently_reported_as_zero_evidence(change):
    result = health.build_pipeline_status([row(**change)], [], now=NOW)
    assert result['stage'] == 'data_issue'
    assert result['model_status'] == 'uncalibrated'


def test_only_passed_fitted_calibration_enables_probability():
    result = health.build_pipeline_status([], sample_rows(), now=NOW)
    assert result['stage'] == 'ready_for_validation'
    assert result['model_status'] == 'uncalibrated'
    result = health.build_pipeline_status([], sample_rows(), now=NOW, latest_calibration={'passed': False})
    assert result['stage'] == 'failed_quality_checks'
    assert result['model_status'] == 'uncalibrated'
    result = health.build_pipeline_status([], sample_rows(), now=NOW, latest_calibration={'passed': True})
    assert result['stage'] == 'calibrated'
    assert result['probability_target'] == 'price_target_touch_not_net_profit'


def test_last_scheduled_error_remains_visible():
    result = health.build_pipeline_status([], [], now=NOW, last_check={'result': {'status': 'error'}})
    assert result['stage'] == 'processing_error'


def test_readiness_deduplicates_overlapping_events():
    rows = sample_rows(360)
    for item in rows:
        item.update(symbol='ONE', signal_timestamp=NOW - timedelta(days=6), outcome_end=NOW - timedelta(days=3))
    result = calibration.calibration_readiness(rows)
    assert result['sample_count'] == 1
    assert result['independent_signal_days'] == 1
    assert not result['ready']


def test_readiness_reports_same_purge_as_fitting():
    rows = sample_rows()
    result = calibration.calibration_readiness(rows)
    training, holdout = calibration.purged_temporal_split(rows, 100)
    assert result['ready']
    assert result['training_count'] == len(training)
    assert result['holdout_count'] == len(holdout)
    assert max(r['outcome_end'] for r in training) < min(r['signal_timestamp'] for r in holdout)


def test_sample_totals_cannot_hide_empty_training_after_purge():
    result = calibration.calibration_readiness(sample_rows(outcome_days=1000))
    assert result['sample_count'] == 360
    assert result['training_count'] == 0
    assert not result['ready']
    assert any('embargo' in reason for reason in result['reasons'])


@pytest.mark.parametrize('state', ['not_ready', 'unchanged', 'passed', 'failed'])
def test_every_scheduled_check_is_recorded_without_altering_result(monkeypatch, state):
    result = {'status': state}
    saved = []
    monkeypatch.setattr(runtime, '_run_calibration_if_changed', lambda: result)
    monkeypatch.setattr(health, 'record_calibration_check', saved.append)
    assert runtime.run_calibration_if_changed() is result
    assert saved == [result]


def test_scheduled_failure_is_recorded_and_reraised(monkeypatch):
    def fail():
        raise RuntimeError('sensitive connection details')
    saved = []
    monkeypatch.setattr(runtime, '_run_calibration_if_changed', fail)
    monkeypatch.setattr(health, 'record_calibration_check', saved.append)
    with pytest.raises(RuntimeError):
        runtime.run_calibration_if_changed()
    assert saved[0]['status'] == 'error'
    assert saved[0]['error_type'] == 'RuntimeError'
    assert 'sensitive' not in json.dumps(saved)


class Cursor:
    def __init__(self, rows=()):
        self.rows, self.calls = list(rows), []

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Connection:
    def __init__(self, cursor):
        self.c = cursor

    def cursor(self):
        return self.c

    def rollback(self):
        pass

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_outcome_queue_prioritises_never_evaluated_not_oldest_signal(monkeypatch):
    cursor = Cursor()
    monkeypatch.setattr(outcomes, 'connection', lambda: Connection(cursor))
    outcomes._load_due(limit=500)
    query, params = cursor.calls[0]
    assert 'ORDER BY last_evaluated_at ASC NULLS FIRST,signal_timestamp,id' in query
    assert params == (500,)
    # Simulate two bounded cycles: all 709 records become reachable, not only the
    # first 500 repeatedly selected by original signal order.
    queue = [{'id': i, 'evaluated': NOW if i < 500 else None} for i in range(709)]
    due = sorted(queue, key=lambda r: (r['evaluated'] is not None, r['evaluated'] or NOW, r['id']))[:500]
    assert sum(r['evaluated'] is None for r in due) == 209


def test_three_session_loader_requires_originals_and_clear_completed_outcomes(monkeypatch):
    cursor = Cursor()
    monkeypatch.setattr(target, 'connection', lambda: Connection(cursor))
    assert target._calibration_samples() == []
    query, params = cursor.calls[0]
    for required in ["mr.run_kind='original'", "so.corporate_action_status='clear'",
                     "three_session_path_matured'='true'", "::timestamptz <= now()",
                     "::timestamptz > so.signal_timestamp"]:
        assert required in query
    assert params[2] == health.TARGET


def test_path_network_error_records_attempt_for_fair_retry():
    cursor = Cursor([{'id': 1, 'symbol': 'TEST', 'signal_timestamp': NOW - timedelta(days=8)}])
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            raise RuntimeError('provider unavailable')
        async def __aexit__(self, *args):
            return False
    async def original(**kwargs):
        return {}
    module = SimpleNamespace(connection=lambda: Connection(cursor), capture_signal_outcomes=original,
                             AlpacaClient=Client, Jsonb=lambda x:x, logger=logging.getLogger(__name__))
    paths.install_patch(module)
    result = asyncio.run(module.enrich_three_session_paths())
    assert result['errors'] == 1
    query = cursor.calls[0][0]
    assert "three_session_calendar_verified' IS DISTINCT FROM 'true'" in query
    assert "three_session_path_evaluated_at" in query
    payload = cursor.calls[1][1][0]
    assert payload['three_session_path_error'] == 'RuntimeError'
    assert 'three_session_path_evaluated_at' in payload
    assert 'three_session_path_matured' not in payload


def test_reliability_rounding_is_numeric_not_double():
    source = Path('app/oversold_v34_diagnostics.py').read_text()
    assert "::numeric - final_score::numeric" in source


def test_status_widget_handles_missing_data_without_fabricating_zero():
    source = r'''
const assert = require('node:assert/strict');
const {viewModel} = require('./app/static/oversold_calibration_status.js');
assert.throws(() => viewModel({}), /unsupported/);
const data = {version:'calibration_pipeline_health_v1', counts:{scored_signals:36,independent_eligible_samples:0},readiness:{requirements:{minimum_matured_signals:300}},reasons:[],label:'Collecting outcomes',model_status:'uncalibrated'};
let v = viewModel(data);
assert.match(v.summary, /36 current-model/);
assert.match(v.summary, /0 \/ 300/);
assert.match(v.probability, /not a probability/);
assert.match(v.rows.find(x=>x[0]==='Positive outcomes')[1], /Unavailable/);
assert.match(v.note, /not promised/);
'''
    completed = subprocess.run(['node', '-e', source], text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr


def test_both_templates_include_shared_status():
    for name in ['oversold.html', 'oversold_v2.html']:
        content = Path('app/templates', name).read_text()
        assert content.count('/static/oversold_calibration_status.js?v=1') == 1
    assert 'within 6 weeks' not in Path('app/static/oversold_score_ui.js').read_text()
