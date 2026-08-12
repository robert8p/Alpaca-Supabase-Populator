from __future__ import annotations

import asyncio
import logging
import os
from typing import Final

from app.db import connection

logger = logging.getLogger(__name__)
_TRUE_VALUES: Final = {"1", "true", "yes", "on"}
_SIGNAL_COLS: Final = {
    "15m": "div15_pct",
    "30m": "div30_pct",
    "60m": "div60_pct",
    "open": "divopen_pct",
}
_EXIT_COLS: Final = {
    "30m": "spread30_pct",
    "60m": "spread60_pct",
    "close": "spreadclose_pct",
}
_MAG_VALUES_SQL: Final = """
(values
 ('all',0.0::double precision,null::double precision),
 ('>=0.05',0.05,null),
 ('>=0.10',0.10,null),
 ('>=0.25',0.25,null),
 ('>=0.50',0.50,null),
 ('>=1.00',1.00,null),
 ('0.05:0.10',0.05,0.10),
 ('0.10:0.25',0.10,0.25),
 ('0.25:0.50',0.25,0.50),
 ('0.50:1.00',0.50,1.00)
) m(mag_rule,lo,hi)
"""


def _enabled() -> bool:
    return os.getenv("BLANKCANVAS_PAIR_LEDGER", "").strip().lower() in _TRUE_VALUES


def _ensure_tables() -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("create schema if not exists research")
            cur.execute(
                """
                create table if not exists research.blankcanvas_pair_candidate_year_v1(
                  signal_name text not null,exit_name text not null,a_symbol text not null,b_symbol text not null,
                  decision_minute int not null,mag_rule text not null,style int not null,yr int not null,n int not null,
                  avg_net10 double precision,median_net10 double precision,win_rate double precision,
                  worst_trade double precision,best_trade double precision,avg_win double precision,avg_loss double precision,
                  primary key(signal_name,exit_name,a_symbol,b_symbol,decision_minute,mag_rule,style,yr)
                )
                """
            )
            cur.execute(
                """
                create table if not exists research.blankcanvas_pair_scan_status_v1(
                  signal_name text not null,exit_name text not null,status text not null,
                  rows_year_stats int not null default 0,started_at timestamptz,completed_at timestamptz,error text,
                  primary key(signal_name,exit_name)
                )
                """
            )
        conn.commit()


def _populate_family(signal_name: str, signal_col: str, exit_name: str, exit_col: str) -> int:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into research.blankcanvas_pair_scan_status_v1(signal_name,exit_name,status,started_at,completed_at,error)
                values(%s,%s,'running',now(),null,null)
                on conflict(signal_name,exit_name) do update set status='running',started_at=now(),completed_at=null,error=null
                """,
                (signal_name, exit_name),
            )
            cur.execute(
                "delete from research.blankcanvas_pair_candidate_year_v1 where signal_name=%s and exit_name=%s",
                (signal_name, exit_name),
            )
            sql = f"""
                insert into research.blankcanvas_pair_candidate_year_v1
                with e as (
                  select trade_date,decision_minute,a_symbol,b_symbol,{signal_col} as div_pct,{exit_col} as spread_pct
                  from research.blankcanvas_pair_intraday_v1
                  where trade_date between date '2017-01-01' and date '2021-12-31'
                    and {signal_col} is not null and {exit_col} is not null
                ), x as (
                  select e.*,m.mag_rule,s.style,(s.style*sign(e.div_pct)*e.spread_pct-0.10) as net10
                  from e
                  cross join {_MAG_VALUES_SQL}
                  cross join (values (1),(-1)) s(style)
                  where abs(e.div_pct)>=m.lo and (m.hi is null or abs(e.div_pct)<m.hi)
                )
                select %s,%s,a_symbol,b_symbol,decision_minute,mag_rule,style,
                       extract(year from trade_date)::int,count(*)::int,
                       avg(net10),percentile_cont(0.5) within group(order by net10),
                       avg((net10>0)::int)*100,min(net10),max(net10),
                       avg(net10) filter(where net10>0),avg(net10) filter(where net10<0)
                from x
                group by a_symbol,b_symbol,decision_minute,mag_rule,style,extract(year from trade_date)
            """
            cur.execute(sql, (signal_name, exit_name))
            rows = cur.rowcount or 0
            cur.execute(
                """
                update research.blankcanvas_pair_scan_status_v1
                set status='completed',rows_year_stats=%s,completed_at=now(),error=null
                where signal_name=%s and exit_name=%s
                """,
                (rows, signal_name, exit_name),
            )
        conn.commit()
    return rows


def _build_summaries() -> tuple[int, int]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("drop table if exists research.blankcanvas_pair_candidate_summary_v1")
            cur.execute(
                """
                create table research.blankcanvas_pair_candidate_summary_v1 as
                select md5(concat_ws('|',signal_name,exit_name,a_symbol,b_symbol,decision_minute,mag_rule,style)) as candidate_id,
                       signal_name,exit_name,a_symbol,b_symbol,decision_minute,mag_rule,style,
                       count(*)::int as years,
                       count(*) filter(where avg_net10>0)::int as positive_years,
                       sum(n)::int as total_n,min(n)::int as min_year_n,
                       min(avg_net10) as worst_year_avg,avg(avg_net10) as mean_year_avg,
                       min(median_net10) as worst_year_median,min(win_rate) as worst_year_win,
                       min(worst_trade) as worst_trade,max(best_trade) as best_trade,
                       avg(avg_win) as mean_year_avg_win,avg(avg_loss) as mean_year_avg_loss
                from research.blankcanvas_pair_candidate_year_v1
                group by signal_name,exit_name,a_symbol,b_symbol,decision_minute,mag_rule,style
                having count(*)=5
                   and count(*) filter(where avg_net10>0)>=4
                   and min(n)>=15
                   and avg(avg_net10)>0
                   and min(avg_net10)>-0.10
                """
            )
            cur.execute("create unique index on research.blankcanvas_pair_candidate_summary_v1(candidate_id)")
            cur.execute("select count(*) as n from research.blankcanvas_pair_candidate_summary_v1")
            discovery_n = int(cur.fetchone()["n"])

            cur.execute("drop table if exists research.blankcanvas_pair_validation_events_v1")
            cur.execute(
                """
                create table research.blankcanvas_pair_validation_events_v1 as
                with j as (
                  select c.candidate_id,c.signal_name,c.exit_name,c.a_symbol,c.b_symbol,c.decision_minute,c.mag_rule,c.style,
                         p.trade_date,
                         case c.signal_name when '15m' then p.div15_pct when '30m' then p.div30_pct when '60m' then p.div60_pct when 'open' then p.divopen_pct end as div_pct,
                         case c.exit_name when '30m' then p.spread30_pct when '60m' then p.spread60_pct when 'close' then p.spreadclose_pct end as spread_pct
                  from research.blankcanvas_pair_candidate_summary_v1 c
                  join research.blankcanvas_pair_intraday_v1 p
                    on p.a_symbol=c.a_symbol and p.b_symbol=c.b_symbol and p.decision_minute=c.decision_minute
                  where p.trade_date between date '2022-01-01' and date '2024-12-31'
                )
                select *, (style*sign(div_pct)*spread_pct-0.10) as net10
                from j
                where div_pct is not null and spread_pct is not null
                  and case mag_rule
                    when 'all' then true
                    when '>=0.05' then abs(div_pct)>=0.05
                    when '>=0.10' then abs(div_pct)>=0.10
                    when '>=0.25' then abs(div_pct)>=0.25
                    when '>=0.50' then abs(div_pct)>=0.50
                    when '>=1.00' then abs(div_pct)>=1.00
                    when '0.05:0.10' then abs(div_pct)>=0.05 and abs(div_pct)<0.10
                    when '0.10:0.25' then abs(div_pct)>=0.10 and abs(div_pct)<0.25
                    when '0.25:0.50' then abs(div_pct)>=0.25 and abs(div_pct)<0.50
                    when '0.50:1.00' then abs(div_pct)>=0.50 and abs(div_pct)<1.00
                    else false end
                """
            )
            cur.execute("create index on research.blankcanvas_pair_validation_events_v1(candidate_id,trade_date)")
            cur.execute("drop table if exists research.blankcanvas_pair_validation_summary_v1")
            cur.execute(
                """
                create table research.blankcanvas_pair_validation_summary_v1 as
                with y as (
                  select candidate_id,extract(year from trade_date)::int as yr,count(*)::int as n,
                         avg(net10) as avg_net10,percentile_cont(0.5) within group(order by net10) as median_net10,
                         avg((net10>0)::int)*100 as win_rate
                  from research.blankcanvas_pair_validation_events_v1
                  group by candidate_id,extract(year from trade_date)
                ), a as (
                  select candidate_id,count(*)::int as n,avg(net10) as avg_net10,
                         percentile_cont(0.5) within group(order by net10) as median_net10,
                         avg((net10>0)::int)*100 as win_rate,min(net10) as worst_trade,max(net10) as best_trade,
                         avg(net10) filter(where net10>0) as avg_win,avg(net10) filter(where net10<0) as avg_loss
                  from research.blankcanvas_pair_validation_events_v1 group by candidate_id
                )
                select c.*,a.n as validation_n,a.avg_net10 as validation_avg_net10,a.median_net10 as validation_median_net10,
                       a.win_rate as validation_win_rate,a.worst_trade as validation_worst_trade,a.best_trade as validation_best_trade,
                       a.avg_win as validation_avg_win,a.avg_loss as validation_avg_loss,
                       count(y.*)::int as validation_years,
                       count(*) filter(where y.avg_net10>0)::int as validation_positive_years,
                       min(y.n)::int as validation_min_year_n,min(y.avg_net10) as validation_worst_year_avg,
                       min(y.median_net10) as validation_worst_year_median,min(y.win_rate) as validation_worst_year_win
                from research.blankcanvas_pair_candidate_summary_v1 c
                join a using(candidate_id)
                join y using(candidate_id)
                group by c.candidate_id,c.signal_name,c.exit_name,c.a_symbol,c.b_symbol,c.decision_minute,c.mag_rule,c.style,
                         c.years,c.positive_years,c.total_n,c.min_year_n,c.worst_year_avg,c.mean_year_avg,c.worst_year_median,c.worst_year_win,
                         c.worst_trade,c.best_trade,c.mean_year_avg_win,c.mean_year_avg_loss,
                         a.n,a.avg_net10,a.median_net10,a.win_rate,a.worst_trade,a.best_trade,a.avg_win,a.avg_loss
                """
            )
            cur.execute("drop table if exists research.blankcanvas_pair_preholdout_freeze_v1")
            cur.execute(
                """
                create table research.blankcanvas_pair_preholdout_freeze_v1 as
                select *,now() as frozen_at
                from research.blankcanvas_pair_validation_summary_v1
                where validation_years=3
                  and validation_positive_years=3
                  and validation_min_year_n>=5
                  and validation_avg_net10>0
                  and validation_median_net10>0
                  and validation_win_rate>50
                """
            )
            cur.execute("select count(*) as n from research.blankcanvas_pair_preholdout_freeze_v1")
            frozen_n = int(cur.fetchone()["n"])
        conn.commit()
    return discovery_n, frozen_n


def _run_scan() -> None:
    _ensure_tables()
    theoretical_candidates = len(_SIGNAL_COLS) * len(_EXIT_COLS) * 15 * 11 * 10 * 2
    logger.warning("Pair candidate ledger scan started; registered candidate definitions=%s", theoretical_candidates)
    for signal_name, signal_col in _SIGNAL_COLS.items():
        for exit_name, exit_col in _EXIT_COLS.items():
            try:
                rows = _populate_family(signal_name, signal_col, exit_name, exit_col)
                logger.info("Pair ledger completed %s->%s: %s year-stat rows", signal_name, exit_name, rows)
            except Exception as exc:
                logger.exception("Pair ledger failed %s->%s", signal_name, exit_name)
                with connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            insert into research.blankcanvas_pair_scan_status_v1(signal_name,exit_name,status,error,started_at)
                            values(%s,%s,'failed',%s,now())
                            on conflict(signal_name,exit_name) do update set status='failed',error=excluded.error
                            """,
                            (signal_name, exit_name, str(exc)[:2000]),
                        )
                    conn.commit()
                raise
    discovery_n, frozen_n = _build_summaries()
    logger.warning("Pair candidate scan complete: discovery survivors=%s; pre-holdout frozen survivors=%s", discovery_n, frozen_n)
    if frozen_n:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select candidate_id,signal_name,exit_name,a_symbol,b_symbol,decision_minute,mag_rule,style,
                           positive_years,mean_year_avg,worst_year_avg,validation_n,validation_avg_net10,
                           validation_median_net10,validation_win_rate,validation_worst_year_avg,validation_worst_trade
                    from research.blankcanvas_pair_preholdout_freeze_v1
                    order by validation_worst_year_avg desc,validation_avg_net10 desc
                    limit 20
                    """
                )
                for row in cur.fetchall():
                    logger.warning("PAIR_PREHOLDOUT %s", dict(row))
                conn.rollback()


async def run_pair_candidate_ledger(stop_event: asyncio.Event) -> None:
    if not _enabled() or stop_event.is_set():
        return
    await asyncio.to_thread(_run_scan)
