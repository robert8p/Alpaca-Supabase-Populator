"""Startup hotfix enforcing the exact frozen E-003C expansion formulas.

Python imports sitecustomize automatically during interpreter startup. This keeps
live evidence collection exactly aligned with the frozen research rule without
changing the rule version or any thresholds. Remove this module once the same
formulas are folded directly into app.e003c_live._signal_candidates.
"""

from __future__ import annotations

import app.e003c_live as _live


def _frozen_signal_candidates(signal_date):
    previous_date = _live._previous_trade_date(signal_date)
    if previous_date is None:
        return []

    with _live.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH s AS (
                    SELECT symbol, open, high, low, close, volume, bar_count, vwap,
                           return_pct, range_pct,
                           COALESCE(vwap, close) * volume::double precision AS dollar_volume
                    FROM rd_daily_features
                    WHERE trade_date=%s
                      AND timeframe='1Min' AND feed='sip' AND adjustment='raw' AND session_label='all'
                ), p AS (
                    SELECT symbol, range_pct,
                           COALESCE(vwap, close) * volume::double precision AS dollar_volume,
                           bar_count
                    FROM rd_daily_features
                    WHERE trade_date=%s
                      AND timeframe='1Min' AND feed='sip' AND adjustment='raw' AND session_label='all'
                )
                SELECT s.symbol,
                       s.open AS signal_open, s.high AS signal_high, s.low AS signal_low,
                       s.close AS signal_close, s.return_pct AS signal_return_pct,
                       s.range_pct AS signal_range_pct, s.dollar_volume AS signal_dollar_volume,
                       s.bar_count AS signal_bar_count,
                       p.range_pct AS prior_range_pct, p.dollar_volume AS prior_dollar_volume,
                       p.bar_count AS prior_bar_count,
                       ln((s.range_pct + 0.01) / (p.range_pct + 0.01)) AS range_log_change,
                       ln((s.dollar_volume + 1) / (p.dollar_volume + 1)) AS dollar_volume_log_change,
                       ln((s.bar_count + 1)::double precision / (p.bar_count + 1)::double precision) AS bar_count_log_change
                FROM s JOIN p USING(symbol)
                WHERE s.open >= 5
                  AND s.close >= 5
                  AND s.return_pct >= 2
                  AND s.dollar_volume >= 1000000
                  AND s.bar_count >= 200
                  AND s.range_pct > 0 AND p.range_pct > 0
                  AND s.dollar_volume > 0 AND p.dollar_volume > 0
                  AND p.bar_count > 0
                  AND ln((s.range_pct + 0.01) / (p.range_pct + 0.01)) >= %s
                  AND ln((s.dollar_volume + 1) / (p.dollar_volume + 1)) >= %s
                  AND ln((s.bar_count + 1)::double precision / (p.bar_count + 1)::double precision) >= %s
                ORDER BY s.symbol
                """,
                (
                    signal_date,
                    previous_date,
                    _live.RANGE_LOG_CHANGE_MIN,
                    _live.DOLLAR_VOLUME_LOG_CHANGE_MIN,
                    _live.BAR_COUNT_LOG_CHANGE_MIN,
                ),
            )
            rows = cur.fetchall()
        conn.rollback()
    return [dict(row) for row in rows]


_live._signal_candidates = _frozen_signal_candidates
