from __future__ import annotations

import asyncio
import logging

from app.db import connection

logger = logging.getLogger(__name__)
_SIGNALS = ("15m", "30m", "60m", "open")


def _table_exists(cur, name: str) -> bool:
    cur.execute("select to_regclass(%s) as rel", (name,))
    return cur.fetchone()["rel"] is not None


def _ensure_provisional() -> int:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("create schema if not exists research")
            cur.execute(
                """
                create table if not exists research.blankcanvas_pair_spyctx_provisional_net5_v1(
                  candidate_id text primary key,signal_name text,exit_name text,a_symbol text,b_symbol text,
                  decision_minute int,mag_rule text,spy_context text,style int,years int,positive_years int,
                  total_n int,min_year_n int,worst_year_avg_net5 double precision,mean_year_avg_net5 double precision,
                  worst_year_win_net10 double precision,worst_trade_net5 double precision,best_trade_net5 double precision
                )
                """
            )
            cur.execute("select count(*)::int as n from research.blankcanvas_pair_spyctx_provisional_net5_v1")
            n = int(cur.fetchone()["n"])
        conn.commit()
    if n:
        return n

    for signal_name in _SIGNALS:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("set local work_mem='128MB'")
                cur.execute(
                    """
                    insert into research.blankcanvas_pair_spyctx_provisional_net5_v1
                    select md5(concat_ws('|',signal_name,exit_name,a_symbol,b_symbol,decision_minute,mag_rule,spy_context,style)),
                           signal_name,exit_name,a_symbol,b_symbol,decision_minute,mag_rule,spy_context,style,
                           count(*)::int,
                           count(*) filter(where avg_net10+0.05>0)::int,
                           sum(n)::int,min(n)::int,min(avg_net10+0.05),avg(avg_net10+0.05),min(win_rate),
                           min(worst_trade+0.05),max(best_trade+0.05)
                    from research.blankcanvas_pair_spyctx_candidate_year_v1
                    where signal_name=%s
                    group by signal_name,exit_name,a_symbol,b_symbol,decision_minute,mag_rule,spy_context,style
                    having count(*)=5
                       and count(*) filter(where avg_net10+0.05>0)>=4
                       and min(n)>=10
                       and avg(avg_net10+0.05)>0
                       and min(avg_net10+0.05)>-0.05
                    on conflict(candidate_id) do nothing
                    """,
                    (signal_name,),
                )
            conn.commit()
        logger.info("5bp provisional aggregation completed for signal=%s", signal_name)

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*)::int as n from research.blankcanvas_pair_spyctx_provisional_net5_v1")
            n = int(cur.fetchone()["n"])
        conn.rollback()
    return n


def _build_discovery_pass() -> int:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("set local work_mem='128MB'")
            cur.execute("drop table if exists research.blankcanvas_pair_spyctx_discovery_events_net5_v1")
            cur.execute(
                """
                create table research.blankcanvas_pair_spyctx_discovery_events_net5_v1 as
                with j as (
                  select c.candidate_id,c.signal_name,c.exit_name,c.a_symbol,c.b_symbol,c.decision_minute,
                         c.mag_rule,c.spy_context,c.style,p.trade_date,
                         case c.signal_name when '15m' then p.div15_pct when '30m' then p.div30_pct when '60m' then p.div60_pct when 'open' then p.divopen_pct end div_pct,
                         case c.signal_name when '15m' then p.spy15_pct when '30m' then p.spy30_pct when '60m' then p.spy60_pct when 'open' then p.spyopen_pct end spy_pct,
                         case c.exit_name when '30m' then p.spread30_pct when '60m' then p.spread60_pct when 'close' then p.spreadclose_pct end spread_pct
                  from research.blankcanvas_pair_spyctx_provisional_net5_v1 c
                  join research.blankcanvas_pair_spyctx_v1 p
                    on p.a_symbol=c.a_symbol and p.b_symbol=c.b_symbol and p.decision_minute=c.decision_minute
                  where p.trade_date between date '2017-01-01' and date '2021-12-31'
                ), e as (
                  select *,case when spy_pct < -0.25 then 'strong_down' when spy_pct < -0.10 then 'down'
                                when spy_pct <=0.10 then 'flat' when spy_pct <=0.25 then 'up' else 'strong_up' end actual_spy_context,
                         style*sign(div_pct)*spread_pct-0.05 net5
                  from j where div_pct is not null and spy_pct is not null and spread_pct is not null
                )
                select * from e
                where actual_spy_context=spy_context
                  and case mag_rule
                    when 'all' then true when '>=0.05' then abs(div_pct)>=0.05 when '>=0.10' then abs(div_pct)>=0.10
                    when '>=0.25' then abs(div_pct)>=0.25 when '>=0.50' then abs(div_pct)>=0.50 when '>=1.00' then abs(div_pct)>=1.00
                    when '0.10:0.25' then abs(div_pct)>=0.10 and abs(div_pct)<0.25
                    when '0.25:0.50' then abs(div_pct)>=0.25 and abs(div_pct)<0.50
                    when '0.50:1.00' then abs(div_pct)>=0.50 and abs(div_pct)<1.00 else false end
                """
            )
            cur.execute("create index on research.blankcanvas_pair_spyctx_discovery_events_net5_v1(candidate_id,trade_date)")
            cur.execute("drop table if exists research.blankcanvas_pair_spyctx_discovery_pass_net5_v1")
            cur.execute(
                """
                create table research.blankcanvas_pair_spyctx_discovery_pass_net5_v1 as
                select c.*,
                       count(e.*)::int discovery_n,avg(e.net5) discovery_avg_net5,
                       percentile_cont(0.5) within group(order by e.net5) discovery_median_net5,
                       avg((e.net5>0)::int)*100 discovery_win_rate,
                       min(e.net5) discovery_worst_trade,max(e.net5) discovery_best_trade,
                       avg(e.net5) filter(where e.net5>0) discovery_avg_win,
                       avg(e.net5) filter(where e.net5<0) discovery_avg_loss,
                       now() discovery_frozen_at
                from research.blankcanvas_pair_spyctx_provisional_net5_v1 c
                join research.blankcanvas_pair_spyctx_discovery_events_net5_v1 e using(candidate_id)
                group by c.candidate_id,c.signal_name,c.exit_name,c.a_symbol,c.b_symbol,c.decision_minute,c.mag_rule,c.spy_context,c.style,
                         c.years,c.positive_years,c.total_n,c.min_year_n,c.worst_year_avg_net5,c.mean_year_avg_net5,c.worst_year_win_net10,
                         c.worst_trade_net5,c.best_trade_net5
                having percentile_cont(0.5) within group(order by e.net5)>0
                   and avg((e.net5>0)::int)*100>50
                """
            )
            cur.execute("select count(*)::int as n from research.blankcanvas_pair_spyctx_discovery_pass_net5_v1")
            n = int(cur.fetchone()["n"])
        conn.commit()
    return n


def _build_validation() -> int:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("set local work_mem='128MB'")
            cur.execute("drop table if exists research.blankcanvas_pair_spyctx_validation_events_net5_v1")
            cur.execute(
                """
                create table research.blankcanvas_pair_spyctx_validation_events_net5_v1 as
                with j as (
                  select c.candidate_id,c.signal_name,c.exit_name,c.a_symbol,c.b_symbol,c.decision_minute,
                         c.mag_rule,c.spy_context,c.style,p.trade_date,
                         case c.signal_name when '15m' then p.div15_pct when '30m' then p.div30_pct when '60m' then p.div60_pct when 'open' then p.divopen_pct end div_pct,
                         case c.signal_name when '15m' then p.spy15_pct when '30m' then p.spy30_pct when '60m' then p.spy60_pct when 'open' then p.spyopen_pct end spy_pct,
                         case c.exit_name when '30m' then p.spread30_pct when '60m' then p.spread60_pct when 'close' then p.spreadclose_pct end spread_pct
                  from research.blankcanvas_pair_spyctx_discovery_pass_net5_v1 c
                  join research.blankcanvas_pair_spyctx_v1 p
                    on p.a_symbol=c.a_symbol and p.b_symbol=c.b_symbol and p.decision_minute=c.decision_minute
                  where p.trade_date between date '2022-01-01' and date '2024-12-31'
                ), e as (
                  select *,case when spy_pct < -0.25 then 'strong_down' when spy_pct < -0.10 then 'down'
                                when spy_pct <=0.10 then 'flat' when spy_pct <=0.25 then 'up' else 'strong_up' end actual_spy_context,
                         style*sign(div_pct)*spread_pct-0.05 net5
                  from j where div_pct is not null and spy_pct is not null and spread_pct is not null
                )
                select * from e
                where actual_spy_context=spy_context
                  and case mag_rule
                    when 'all' then true when '>=0.05' then abs(div_pct)>=0.05 when '>=0.10' then abs(div_pct)>=0.10
                    when '>=0.25' then abs(div_pct)>=0.25 when '>=0.50' then abs(div_pct)>=0.50 when '>=1.00' then abs(div_pct)>=1.00
                    when '0.10:0.25' then abs(div_pct)>=0.10 and abs(div_pct)<0.25
                    when '0.25:0.50' then abs(div_pct)>=0.25 and abs(div_pct)<0.50
                    when '0.50:1.00' then abs(div_pct)>=0.50 and abs(div_pct)<1.00 else false end
                """
            )
            cur.execute("create index on research.blankcanvas_pair_spyctx_validation_events_net5_v1(candidate_id,trade_date)")
            cur.execute("drop table if exists research.blankcanvas_pair_spyctx_validation_year_net5_v1")
            cur.execute(
                """
                create table research.blankcanvas_pair_spyctx_validation_year_net5_v1 as
                select candidate_id,extract(year from trade_date)::int yr,count(*)::int n,avg(net5) avg_net5,
                       percentile_cont(0.5) within group(order by net5) median_net5,
                       avg((net5>0)::int)*100 win_rate,min(net5) worst_trade,max(net5) best_trade
                from research.blankcanvas_pair_spyctx_validation_events_net5_v1
                group by candidate_id,extract(year from trade_date)
                """
            )
            cur.execute("drop table if exists research.blankcanvas_pair_spyctx_preholdout_freeze_net5_v1")
            cur.execute(
                """
                create table research.blankcanvas_pair_spyctx_preholdout_freeze_net5_v1 as
                with a as (
                  select candidate_id,count(*)::int validation_n,avg(net5) validation_avg_net5,
                         percentile_cont(0.5) within group(order by net5) validation_median_net5,
                         avg((net5>0)::int)*100 validation_win_rate,min(net5) validation_worst_trade,max(net5) validation_best_trade,
                         avg(net5) filter(where net5>0) validation_avg_win,avg(net5) filter(where net5<0) validation_avg_loss
                  from research.blankcanvas_pair_spyctx_validation_events_net5_v1 group by candidate_id
                ), y as (
                  select candidate_id,count(*)::int validation_years,
                         count(*) filter(where avg_net5>0)::int validation_positive_years,
                         min(n)::int validation_min_year_n,min(avg_net5) validation_worst_year_avg,
                         min(median_net5) validation_worst_year_median,min(win_rate) validation_worst_year_win
                  from research.blankcanvas_pair_spyctx_validation_year_net5_v1 group by candidate_id
                )
                select c.*,a.validation_n,a.validation_avg_net5,a.validation_median_net5,a.validation_win_rate,
                       a.validation_worst_trade,a.validation_best_trade,a.validation_avg_win,a.validation_avg_loss,
                       y.validation_years,y.validation_positive_years,y.validation_min_year_n,y.validation_worst_year_avg,
                       y.validation_worst_year_median,y.validation_worst_year_win,now() preholdout_frozen_at
                from research.blankcanvas_pair_spyctx_discovery_pass_net5_v1 c
                join a using(candidate_id) join y using(candidate_id)
                where y.validation_years=3 and y.validation_positive_years=3 and y.validation_min_year_n>=5
                  and a.validation_avg_net5>0 and a.validation_median_net5>0 and a.validation_win_rate>50
                """
            )
            cur.execute("select count(*)::int as n from research.blankcanvas_pair_spyctx_preholdout_freeze_net5_v1")
            n = int(cur.fetchone()["n"])
        conn.commit()
    return n


def run_net5_postprocess() -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            if _table_exists(cur, 'research.blankcanvas_pair_spyctx_preholdout_freeze_net5_v1'):
                cur.execute("select count(*)::int n from research.blankcanvas_pair_spyctx_preholdout_freeze_net5_v1")
                existing = int(cur.fetchone()["n"])
                conn.rollback()
                logger.info("5bp postprocess already complete; frozen=%s", existing)
                return
        conn.rollback()

    provisional = _ensure_provisional()
    logger.warning("5bp SPY-context provisional candidates=%s", provisional)
    discovery = _build_discovery_pass() if provisional else 0
    logger.warning("5bp SPY-context exact discovery passes=%s", discovery)
    frozen = _build_validation() if discovery else 0
    if not discovery:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("drop table if exists research.blankcanvas_pair_spyctx_preholdout_freeze_net5_v1")
                cur.execute("create table research.blankcanvas_pair_spyctx_preholdout_freeze_net5_v1(candidate_id text,preholdout_frozen_at timestamptz)")
            conn.commit()
    logger.warning("5bp SPY-context preholdout frozen candidates=%s", frozen)


async def run_net5_postprocess_async() -> None:
    await asyncio.to_thread(run_net5_postprocess)
