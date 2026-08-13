-- Campaign: WEAKCLOSE-COMPOSITE-20260813-V1
-- Holdout protocol commit: e906f58aba770f4a5589fae9c3722a901b7163b8
-- This loader was committed before any November 2025 outcome was queried.

create schema if not exists research;

create table if not exists research.blankcanvas_weakclose_holdout_run_v1 (
  campaign_id text not null,
  holdout_stage text not null check(holdout_stage in ('HOLDOUT_A','HOLDOUT_B')),
  signal_start date not null,
  signal_end date not null,
  eligible_candidate_count integer not null,
  expected_signal_days integer,
  protocol_commit text not null,
  loader_commit text,
  opened_at timestamptz not null default now(),
  completed_at timestamptz,
  status text not null,
  summary_json jsonb,
  primary key(campaign_id,holdout_stage)
);

create table if not exists research.blankcanvas_weakclose_holdout_score_v1 (
  campaign_id text not null,
  holdout_stage text not null check(holdout_stage in ('HOLDOUT_A','HOLDOUT_B')),
  signal_date date not null,
  next_date date not null,
  symbol text not null,
  liquidity_rank integer not null,
  calibration_avg_dollar_volume double precision not null,
  signal_universe_count integer not null,
  ret_oc_rank double precision not null,
  close_vs_vwap_rank double precision not null,
  close_location_rank double precision not null,
  max_drawdown_rank double precision not null,
  last60_rank double precision not null,
  last30_rank double precision not null,
  composite_score double precision not null,
  next_open double precision,
  next_close double precision,
  entry_price_eligible boolean not null,
  weak_entry_rank integer,
  strong_entry_rank integer,
  created_at timestamptz not null default now(),
  primary key(campaign_id,holdout_stage,signal_date,symbol)
);
create index if not exists blankcanvas_weakclose_holdout_score_rank_idx
  on research.blankcanvas_weakclose_holdout_score_v1(campaign_id,holdout_stage,signal_date,weak_entry_rank,strong_entry_rank);

create table if not exists research.blankcanvas_weakclose_holdout_daily_v1 (
  campaign_id text not null,
  holdout_stage text not null check(holdout_stage in ('HOLDOUT_A','HOLDOUT_B')),
  candidate_id text not null,
  signal_date date not null,
  next_date date not null,
  construction text not null,
  top_n smallint not null,
  signal_universe_count integer not null,
  entry_eligible_count integer not null,
  weak_actual_names smallint not null,
  strong_actual_names smallint not null,
  weak_target_count smallint not null,
  strong_target_count smallint not null,
  weak_symbols text[] not null,
  strong_symbols text[] not null,
  baskets_overlap boolean not null,
  weak_avg_return double precision,
  strong_avg_return double precision,
  gross_return double precision,
  net_return_10bp double precision,
  net_return_20bp double precision,
  min_selected_open double precision,
  trade_complete boolean not null,
  excluded_reason text,
  created_at timestamptz not null default now(),
  primary key(campaign_id,holdout_stage,candidate_id,signal_date)
);
create index if not exists blankcanvas_weakclose_holdout_daily_candidate_idx
  on research.blankcanvas_weakclose_holdout_daily_v1(campaign_id,holdout_stage,candidate_id,signal_date);

create table if not exists research.blankcanvas_weakclose_holdout_metrics_v1 (
  campaign_id text not null,
  holdout_stage text not null check(holdout_stage in ('HOLDOUT_A','HOLDOUT_B')),
  candidate_id text not null,
  signal_start date not null,
  signal_end date not null,
  expected_days integer not null,
  trades integer not null,
  excluded_days integer not null,
  avg_gross double precision,
  avg_net10 double precision,
  median_net10 double precision,
  win_rate10 double precision,
  avg_win10 double precision,
  avg_loss10 double precision,
  worst_trade10 double precision,
  best_trade10 double precision,
  profit_factor10 double precision,
  t_stat10 double precision,
  avg_net20 double precision,
  compound_return10 double precision,
  sum_net10 double precision,
  created_at timestamptz not null default now(),
  primary key(campaign_id,holdout_stage,candidate_id)
);

create table if not exists research.blankcanvas_weakclose_holdout_gate_v1 (
  campaign_id text not null,
  holdout_stage text not null check(holdout_stage in ('HOLDOUT_A','HOLDOUT_B')),
  candidate_id text not null,
  stage_pass boolean not null,
  gate_failures text[] not null,
  evaluated_at timestamptz not null default now(),
  primary key(campaign_id,holdout_stage,candidate_id)
);

create or replace function research.load_blankcanvas_weakclose_holdout_stage_v1(p_stage text)
returns jsonb
language plpgsql
security invoker
set search_path=research,public,pg_temp
set work_mem='128MB'
as $function$
declare
  v_start date;
  v_end date;
  v_candidate_count integer;
  v_expected_days integer;
  v_passed integer;
begin
  if p_stage='HOLDOUT_A' then
    v_start:=date '2025-11-03';
    v_end:=date '2025-11-28';
  elsif p_stage='HOLDOUT_B' then
    v_start:=date '2025-12-01';
    v_end:=date '2025-12-30';
    if not exists (
      select 1 from research.blankcanvas_weakclose_holdout_gate_v1
      where campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1'
        and holdout_stage='HOLDOUT_A' and stage_pass
    ) then
      raise exception 'HOLDOUT_B is locked: no HOLDOUT_A survivor';
    end if;
  else
    raise exception 'invalid holdout stage %',p_stage;
  end if;

  select count(*)::integer into v_candidate_count
  from research.blankcanvas_weakclose_preholdout_freeze_v1 f
  where f.campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1'
    and (p_stage='HOLDOUT_A' or exists (
      select 1 from research.blankcanvas_weakclose_holdout_gate_v1 g
      where g.campaign_id=f.campaign_id and g.candidate_id=f.candidate_id
        and g.holdout_stage='HOLDOUT_A' and g.stage_pass
    ));
  if v_candidate_count=0 then raise exception 'no eligible candidate for %',p_stage; end if;

  with all_dates as (
    select distinct trade_date from public.rd_blankcanvas_equity_daily_v2
  ), calendar as (
    select trade_date as signal_date,lead(trade_date) over(order by trade_date) as next_date
    from all_dates
  )
  select count(*)::integer into v_expected_days
  from calendar where signal_date between v_start and v_end and next_date is not null;
  if v_expected_days<15 then raise exception 'insufficient signal dates for %: %',p_stage,v_expected_days; end if;

  insert into research.blankcanvas_weakclose_holdout_run_v1(
    campaign_id,holdout_stage,signal_start,signal_end,eligible_candidate_count,
    expected_signal_days,protocol_commit,loader_commit,opened_at,completed_at,status,summary_json
  ) values (
    'WEAKCLOSE-COMPOSITE-20260813-V1',p_stage,v_start,v_end,v_candidate_count,
    v_expected_days,'e906f58aba770f4a5589fae9c3722a901b7163b8',null,now(),null,'OPENED',null
  ) on conflict(campaign_id,holdout_stage) do update set
    signal_start=excluded.signal_start,signal_end=excluded.signal_end,
    eligible_candidate_count=excluded.eligible_candidate_count,
    expected_signal_days=excluded.expected_signal_days,protocol_commit=excluded.protocol_commit,
    opened_at=now(),completed_at=null,status='OPENED',summary_json=null;

  delete from research.blankcanvas_weakclose_holdout_gate_v1
  where campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1' and holdout_stage=p_stage;
  delete from research.blankcanvas_weakclose_holdout_metrics_v1
  where campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1' and holdout_stage=p_stage;
  delete from research.blankcanvas_weakclose_holdout_daily_v1
  where campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1' and holdout_stage=p_stage;
  delete from research.blankcanvas_weakclose_holdout_score_v1
  where campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1' and holdout_stage=p_stage;

  with all_dates as materialized (
    select distinct trade_date from public.rd_blankcanvas_equity_daily_v2
  ), calendar as materialized (
    select trade_date as signal_date,lead(trade_date) over(order by trade_date) as next_date
    from all_dates
  ), date_map as materialized (
    select signal_date,next_date from calendar
    where signal_date between v_start and v_end and next_date is not null
  ), fixed_universe as materialized (
    select u.symbol,u.liquidity_rank,u.calibration_avg_dollar_volume
    from public.rd_blankcanvas_equity_universe_v2 u
    join research.blankcanvas_extreme_asset_eligibility_v1 a using(symbol)
    where a.instrument_group='OPERATING_EQUITY' and a.research_short_eligible
  ), signal_base as materialized (
    select d.signal_date,d.next_date,u.symbol,u.liquidity_rank,u.calibration_avg_dollar_volume,
           s.ret_oc,s.close_vs_vwap,s.close_location,s.max_drawdown_from_open,s.last60_ret,s.last30_ret,
           n.open_price as next_open,n.close_price as next_close
    from date_map d cross join fixed_universe u
    join public.rd_blankcanvas_equity_daily_v2 s
      on s.symbol=u.symbol and s.trade_date=d.signal_date
    left join public.rd_blankcanvas_equity_daily_v2 n
      on n.symbol=u.symbol and n.trade_date=d.next_date
    where s.ret_oc is not null and s.close_vs_vwap is not null and s.close_location is not null
      and s.max_drawdown_from_open is not null and s.last60_ret is not null and s.last30_ret is not null
  ), ranked_features as materialized (
    select b.*,count(*) over(partition by signal_date)::integer as signal_universe_count,
           row_number() over(partition by signal_date order by ret_oc,symbol) as r_ret_oc,
           row_number() over(partition by signal_date order by close_vs_vwap,symbol) as r_close_vs_vwap,
           row_number() over(partition by signal_date order by close_location,symbol) as r_close_location,
           row_number() over(partition by signal_date order by max_drawdown_from_open,symbol) as r_max_drawdown,
           row_number() over(partition by signal_date order by last60_ret,symbol) as r_last60,
           row_number() over(partition by signal_date order by last30_ret,symbol) as r_last30
    from signal_base b
  ), scored as materialized (
    select r.*,
           (r_ret_oc-1)::double precision/nullif(signal_universe_count-1,0) as ret_oc_rank,
           (r_close_vs_vwap-1)::double precision/nullif(signal_universe_count-1,0) as close_vs_vwap_rank,
           (r_close_location-1)::double precision/nullif(signal_universe_count-1,0) as close_location_rank,
           (r_max_drawdown-1)::double precision/nullif(signal_universe_count-1,0) as max_drawdown_rank,
           (r_last60-1)::double precision/nullif(signal_universe_count-1,0) as last60_rank,
           (r_last30-1)::double precision/nullif(signal_universe_count-1,0) as last30_rank
    from ranked_features r where signal_universe_count>=200
  ), composite as materialized (
    select s.*,
           (ret_oc_rank+close_vs_vwap_rank+close_location_rank+max_drawdown_rank+last60_rank+last30_rank)/6.0
             as composite_score,
           (next_open is not null and next_open>=5) as entry_price_eligible
    from scored s
  ), entry_ranked as materialized (
    select c.*,
           case when entry_price_eligible then row_number() over(
             partition by signal_date,entry_price_eligible order by composite_score,symbol
           ) end::integer as weak_entry_rank,
           case when entry_price_eligible then row_number() over(
             partition by signal_date,entry_price_eligible order by composite_score desc,symbol
           ) end::integer as strong_entry_rank
    from composite c
  )
  insert into research.blankcanvas_weakclose_holdout_score_v1(
    campaign_id,holdout_stage,signal_date,next_date,symbol,liquidity_rank,
    calibration_avg_dollar_volume,signal_universe_count,ret_oc_rank,close_vs_vwap_rank,
    close_location_rank,max_drawdown_rank,last60_rank,last30_rank,composite_score,
    next_open,next_close,entry_price_eligible,weak_entry_rank,strong_entry_rank
  )
  select 'WEAKCLOSE-COMPOSITE-20260813-V1',p_stage,signal_date,next_date,symbol,
         liquidity_rank,calibration_avg_dollar_volume,signal_universe_count,ret_oc_rank,
         close_vs_vwap_rank,close_location_rank,max_drawdown_rank,last60_rank,last30_rank,
         composite_score,next_open,next_close,entry_price_eligible,weak_entry_rank,strong_entry_rank
  from entry_ranked;

  with candidate_defs as materialized (
    select f.* from research.blankcanvas_weakclose_preholdout_freeze_v1 f
    where f.campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1'
      and (p_stage='HOLDOUT_A' or exists (
        select 1 from research.blankcanvas_weakclose_holdout_gate_v1 g
        where g.campaign_id=f.campaign_id and g.candidate_id=f.candidate_id
          and g.holdout_stage='HOLDOUT_A' and g.stage_pass
      ))
  ), ns as materialized (
    select distinct top_n from candidate_defs
  ), selection as materialized (
    select s.signal_date,max(s.next_date) as next_date,n.top_n,
           max(s.signal_universe_count)::integer as signal_universe_count,
           count(*) filter(where s.entry_price_eligible)::integer as entry_eligible_count,
           count(*) filter(where s.weak_entry_rank<=n.top_n)::smallint as weak_actual_names,
           count(*) filter(where s.strong_entry_rank<=n.top_n)::smallint as strong_actual_names,
           count(*) filter(where s.weak_entry_rank<=n.top_n and s.next_close is not null)::smallint as weak_target_count,
           count(*) filter(where s.strong_entry_rank<=n.top_n and s.next_close is not null)::smallint as strong_target_count,
           coalesce(array_agg(s.symbol order by s.weak_entry_rank)
             filter(where s.weak_entry_rank<=n.top_n),array[]::text[]) as weak_symbols,
           coalesce(array_agg(s.symbol order by s.strong_entry_rank)
             filter(where s.strong_entry_rank<=n.top_n),array[]::text[]) as strong_symbols,
           avg(s.next_close/s.next_open-1)
             filter(where s.weak_entry_rank<=n.top_n and s.next_open>0 and s.next_close is not null) as weak_avg_return,
           avg(s.next_close/s.next_open-1)
             filter(where s.strong_entry_rank<=n.top_n and s.next_open>0 and s.next_close is not null) as strong_avg_return,
           min(s.next_open) filter(where s.weak_entry_rank<=n.top_n or s.strong_entry_rank<=n.top_n)
             as min_selected_open
    from research.blankcanvas_weakclose_holdout_score_v1 s cross join ns n
    where s.campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1' and s.holdout_stage=p_stage
    group by s.signal_date,n.top_n
  ), prepared as materialized (
    select x.*,x.weak_symbols && x.strong_symbols as baskets_overlap from selection x
  )
  insert into research.blankcanvas_weakclose_holdout_daily_v1(
    campaign_id,holdout_stage,candidate_id,signal_date,next_date,construction,top_n,
    signal_universe_count,entry_eligible_count,weak_actual_names,strong_actual_names,
    weak_target_count,strong_target_count,weak_symbols,strong_symbols,baskets_overlap,
    weak_avg_return,strong_avg_return,gross_return,net_return_10bp,net_return_20bp,
    min_selected_open,trade_complete,excluded_reason
  )
  select d.campaign_id,p_stage,d.candidate_id,p.signal_date,p.next_date,d.construction,d.top_n,
         p.signal_universe_count,p.entry_eligible_count,p.weak_actual_names,p.strong_actual_names,
         p.weak_target_count,p.strong_target_count,p.weak_symbols,p.strong_symbols,p.baskets_overlap,
         p.weak_avg_return,p.strong_avg_return,
         case when d.construction='SHORT_WEAK' then -p.weak_avg_return
              else 0.5*(p.strong_avg_return-p.weak_avg_return) end,
         case when p.signal_universe_count>=200 and p.weak_actual_names=d.top_n and p.weak_target_count=d.top_n
                   and (d.construction='SHORT_WEAK' or
                     (p.strong_actual_names=d.top_n and p.strong_target_count=d.top_n and not p.baskets_overlap))
              then (case when d.construction='SHORT_WEAK' then -p.weak_avg_return
                         else 0.5*(p.strong_avg_return-p.weak_avg_return) end)-0.0010 end,
         case when p.signal_universe_count>=200 and p.weak_actual_names=d.top_n and p.weak_target_count=d.top_n
                   and (d.construction='SHORT_WEAK' or
                     (p.strong_actual_names=d.top_n and p.strong_target_count=d.top_n and not p.baskets_overlap))
              then (case when d.construction='SHORT_WEAK' then -p.weak_avg_return
                         else 0.5*(p.strong_avg_return-p.weak_avg_return) end)-0.0020 end,
         p.min_selected_open,
         (p.signal_universe_count>=200 and p.weak_actual_names=d.top_n and p.weak_target_count=d.top_n
           and (d.construction='SHORT_WEAK' or
             (p.strong_actual_names=d.top_n and p.strong_target_count=d.top_n and not p.baskets_overlap))),
         case
           when p.signal_universe_count<200 then 'SIGNAL_UNIVERSE_LT_200'
           when p.weak_actual_names<d.top_n then 'INSUFFICIENT_WEAK_ENTRY_NAMES'
           when p.weak_target_count<d.top_n then 'MISSING_WEAK_EXIT'
           when d.construction='STRONG_MINUS_WEAK' and p.strong_actual_names<d.top_n then 'INSUFFICIENT_STRONG_ENTRY_NAMES'
           when d.construction='STRONG_MINUS_WEAK' and p.strong_target_count<d.top_n then 'MISSING_STRONG_EXIT'
           when d.construction='STRONG_MINUS_WEAK' and p.baskets_overlap then 'BASKET_OVERLAP'
           else null end
  from prepared p join candidate_defs d on d.top_n=p.top_n;

  insert into research.blankcanvas_weakclose_holdout_metrics_v1(
    campaign_id,holdout_stage,candidate_id,signal_start,signal_end,expected_days,trades,excluded_days,
    avg_gross,avg_net10,median_net10,win_rate10,avg_win10,avg_loss10,worst_trade10,best_trade10,
    profit_factor10,t_stat10,avg_net20,compound_return10,sum_net10
  )
  select 'WEAKCLOSE-COMPOSITE-20260813-V1',p_stage,d.candidate_id,v_start,v_end,
         count(*)::integer,count(*) filter(where x.trade_complete)::integer,
         count(*) filter(where not x.trade_complete)::integer,
         avg(x.gross_return) filter(where x.trade_complete),
         avg(x.net_return_10bp) filter(where x.trade_complete),
         percentile_cont(0.5) within group(order by x.net_return_10bp) filter(where x.trade_complete),
         avg((x.net_return_10bp>0)::integer) filter(where x.trade_complete)::double precision,
         avg(x.net_return_10bp) filter(where x.trade_complete and x.net_return_10bp>0),
         avg(x.net_return_10bp) filter(where x.trade_complete and x.net_return_10bp<0),
         min(x.net_return_10bp) filter(where x.trade_complete),
         max(x.net_return_10bp) filter(where x.trade_complete),
         sum(x.net_return_10bp) filter(where x.trade_complete and x.net_return_10bp>0)
           /nullif(abs(sum(x.net_return_10bp) filter(where x.trade_complete and x.net_return_10bp<0)),0),
         avg(x.net_return_10bp) filter(where x.trade_complete)
           /nullif(stddev_samp(x.net_return_10bp) filter(where x.trade_complete)
             /sqrt(count(*) filter(where x.trade_complete)),0),
         avg(x.net_return_20bp) filter(where x.trade_complete),
         exp(sum(ln(1+x.net_return_10bp)) filter(where x.trade_complete))-1,
         sum(x.net_return_10bp) filter(where x.trade_complete)
  from (
    select f.* from research.blankcanvas_weakclose_preholdout_freeze_v1 f
    where f.campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1'
      and (p_stage='HOLDOUT_A' or exists (
        select 1 from research.blankcanvas_weakclose_holdout_gate_v1 g
        where g.campaign_id=f.campaign_id and g.candidate_id=f.candidate_id
          and g.holdout_stage='HOLDOUT_A' and g.stage_pass
      ))
  ) d
  join research.blankcanvas_weakclose_holdout_daily_v1 x
    on x.campaign_id=d.campaign_id and x.candidate_id=d.candidate_id and x.holdout_stage=p_stage
  group by d.candidate_id;

  insert into research.blankcanvas_weakclose_holdout_gate_v1(
    campaign_id,holdout_stage,candidate_id,stage_pass,gate_failures
  )
  select m.campaign_id,m.holdout_stage,m.candidate_id,
         (m.trades>=15 and m.avg_net10>0 and m.median_net10>0 and m.win_rate10>0.50
           and m.profit_factor10>1.10 and m.avg_net20>0),
         array_remove(array[
           case when m.trades<15 then 'TRADES_LT_15' end,
           case when not(m.avg_net10>0) then 'AVG_NET10_NOT_POSITIVE' end,
           case when not(m.median_net10>0) then 'MEDIAN_NET10_NOT_POSITIVE' end,
           case when not(m.win_rate10>0.50) then 'WIN_RATE_NOT_ABOVE_50' end,
           case when not(m.profit_factor10>1.10) then 'PROFIT_FACTOR_NOT_ABOVE_1_10' end,
           case when not(m.avg_net20>0) then 'AVG_NET20_NOT_POSITIVE' end
         ],null)
  from research.blankcanvas_weakclose_holdout_metrics_v1 m
  where m.campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1' and m.holdout_stage=p_stage;

  select count(*)::integer into v_passed
  from research.blankcanvas_weakclose_holdout_gate_v1
  where campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1' and holdout_stage=p_stage and stage_pass;

  update research.blankcanvas_weakclose_holdout_run_v1 r
  set completed_at=now(),status='COMPLETED',
      summary_json=jsonb_build_object(
        'eligible_candidates',v_candidate_count,
        'expected_signal_days',v_expected_days,
        'passed_candidates',v_passed
      )
  where r.campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1' and r.holdout_stage=p_stage;

  return jsonb_build_object(
    'campaign_id','WEAKCLOSE-COMPOSITE-20260813-V1',
    'holdout_stage',p_stage,
    'signal_start',v_start,
    'signal_end',v_end,
    'expected_signal_days',v_expected_days,
    'eligible_candidates',v_candidate_count,
    'passed_candidates',v_passed
  );
end;
$function$;
