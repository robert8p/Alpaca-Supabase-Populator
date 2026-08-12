from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, timedelta

from app.db import connection

logger = logging.getLogger(__name__)
_TRUE_VALUES = {"1", "true", "yes", "on"}
_SYMBOLS_SQL = "'DIA','HYG','QQQ','SPY','TLT','USO'"


def _enabled() -> bool:
    return os.getenv("BLANKCANVAS_INTRADAY_COMPACTOR", "").strip().lower() in _TRUE_VALUES


def _months(start_year: int = 2017, start_month: int = 1, end_year: int = 2026, end_month: int = 8):
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        yield year, month
        month += 1
        if month == 13:
            year += 1
            month = 1


def _compact_month(year: int, month: int) -> int:
    table = f"rd_bars_{year}{month:02d}"
    month_start = date(year, month, 1)
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    month_end = next_month - timedelta(days=1)

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select to_regclass(%s) as rel", (f"public.{table}",))
            if cur.fetchone()["rel"] is None:
                cur.execute(
                    """
                    insert into public.blankcanvas_intraday_compactor_status_v1(
                      month_start,table_name,status,error,updated_at
                    ) values(%s,%s,'missing','partition not found',now())
                    on conflict(month_start) do update set
                      table_name=excluded.table_name,status='missing',error=excluded.error,updated_at=now()
                    """,
                    (month_start, table),
                )
                conn.commit()
                return 0

            cur.execute(
                """
                select status from public.blankcanvas_intraday_compactor_status_v1
                where month_start=%s
                """,
                (month_start,),
            )
            prior = cur.fetchone()
            if prior and prior["status"] == "completed":
                conn.rollback()
                return 0

            cur.execute(
                """
                insert into public.blankcanvas_intraday_compactor_status_v1(
                  month_start,table_name,status,started_at,error,updated_at
                ) values(%s,%s,'running',now(),null,now())
                on conflict(month_start) do update set
                  table_name=excluded.table_name,status='running',started_at=now(),error=null,updated_at=now()
                """,
                (month_start, table),
            )
            conn.commit()

        # Generate the small set of exact market-clock timestamps first, then join once to the
        # physical monthly partition. This avoids repeatedly applying timezone functions across
        # every minute row and benchmarks at roughly one second per month on the research DB.
        sql = f"""
            with days as (
              select d::date trade_date
              from generate_series(date '{month_start.isoformat()}', date '{month_end.isoformat()}', interval '1 day') d
              where extract(isodow from d) < 6
            ), mins as (
              select m as minute_et
              from generate_series(570,959) m
              where m=959
                 or mod(m-570,30)=0
                 or mod(m-585,30)=0
                 or mod(m-601,30)=0
            ), grid as (
              select s.symbol,d.trade_date,m.minute_et,
                ((d.trade_date + make_time((m.minute_et/60)::int,(m.minute_et%60)::int,0))
                  at time zone 'America/New_York') bar_ts
              from days d
              cross join mins m
              cross join (values('DIA'),('HYG'),('QQQ'),('SPY'),('TLT'),('USO')) s(symbol)
            )
            insert into public.blankcanvas_intraday_snapshots_v1(symbol,trade_date,minute_et,open,close)
            select g.symbol,g.trade_date,g.minute_et,b.open,b.close
            from grid g
            join public.{table} b
              on b.symbol=g.symbol
             and b.timeframe='1Min'
             and b.feed='sip'
             and b.adjustment='raw'
             and b.session_label='regular'
             and b.bar_ts=g.bar_ts
            on conflict(symbol,trade_date,minute_et) do update set
              open=excluded.open,close=excluded.close
        """
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.rowcount or 0
            cur.execute(
                """
                update public.blankcanvas_intraday_compactor_status_v1
                set status='completed',rows_upserted=%s,completed_at=now(),error=null,updated_at=now()
                where month_start=%s
                """,
                (rows, month_start),
            )
        conn.commit()
        return rows


async def run_intraday_snapshot_compactor(stop_event: asyncio.Event) -> None:
    """Low-priority one-off compaction of selected intraday clock points.

    The task is inert unless BLANKCANVAS_INTRADAY_COMPACTOR is enabled. It reads one physical
    monthly partition at a time, commits after each month, and never modifies rd_bars.
    """
    if not _enabled():
        return

    logger.warning("Blank-canvas intraday snapshot compactor started")
    for year, month in _months():
        if stop_event.is_set():
            return
        try:
            rows = await asyncio.to_thread(_compact_month, year, month)
            if rows:
                logger.info("Compacted %04d-%02d: %s snapshot rows", year, month, rows)
        except Exception as exc:
            logger.exception("Intraday snapshot compaction failed for %04d-%02d", year, month)
            month_start = date(year, month, 1)
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        insert into public.blankcanvas_intraday_compactor_status_v1(
                          month_start,table_name,status,error,updated_at
                        ) values(%s,%s,'failed',%s,now())
                        on conflict(month_start) do update set
                          status='failed',error=excluded.error,updated_at=now()
                        """,
                        (month_start, f"rd_bars_{year}{month:02d}", str(exc)[:2000]),
                    )
                conn.commit()
            await asyncio.sleep(1.0)
    logger.warning("Blank-canvas intraday snapshot compactor completed")
