-- Frozen untouched-holdout evaluation for candidate 4a2ccfe28e77fa0cb4587a512b55c2a6.
-- The rule was frozen before any 2025-2026 outcome calculation.

create schema if not exists research;

create table if not exists research.blankcanvas_pair_spyctx_holdout_run_v1(
  run_id text primary key,
  candidate_id text not null,
  frozen_at timestamptz not null,
  holdout_start date not null,
  holdout_end date not null,
  calculation_version text not null,
  calculation_code_commit text,
  rule_json jsonb not null,
  data_snapshot_json jsonb not null,
  opened_at timestamptz not null default now(),
  completed_at timestamptz,
  status text not null,
  summary_json jsonb,
  notes text
);

create table if not exists research.blankcanvas_pair_spyctx_holdout_trade_ledger_v1(
  run_id text not null references research.blankcanvas_pair_spyctx_holdout_run_v1(run_id),
  candidate_id text not null,
  trade_date date not null,
  signal_complete boolean not null,
  exit_complete boolean not null,
  triggered boolean not null,
  excluded_reason text,
  spy_sig15_pct double precision,
  tlt_sig15_pct double precision,
  uso_sig15_pct double precision,
  div_pct double precision,
  spy_context text,
  direction text,
  tlt_entry_open double precision,
  uso_entry_open double precision,
  tlt_exit_close double precision,
  uso_exit_close double precision,
  tlt_leg_return_pct double precision,
  uso_leg_return_pct double precision,
  spread_close_pct double precision,
  gross_spread_pct double precision,
  net5_pct double precision,
  net7_5_pct double precision,
  net10_pct double precision,
  source_partitions text[],
  created_at timestamptz not null default now(),
  primary key(run_id,trade_date)
);

create index if not exists blankcanvas_pair_spyctx_holdout_trade_trigger_idx
  on research.blankcanvas_pair_spyctx_holdout_trade_ledger_v1(run_id,triggered,trade_date);

create table if not exists research.blankcanvas_pair_spyctx_holdout_metrics_v1(
  run_id text not null references research.blankcanvas_pair_spyctx_holdout_run_v1(run_id),
  metric_scope text not null,
  cost_bps double precision not null,
  scope_start date not null,
  scope_end date not null,
  signals integer not null,
  trades integer not null,
  excluded_incomplete integer not null,
  avg_net_pct double precision,
  median_net_pct double precision,
  win_rate_pct double precision,
  avg_win_pct double precision,
  avg_loss_pct double precision,
  worst_trade_pct double precision,
  best_trade_pct double precision,
  profit_factor double precision,
  sum_net_pct double precision,
  compound_return_pct double precision,
  max_drawdown_pct double precision,
  t_stat double precision,
  mean_ci95_low double precision,
  mean_ci95_high double precision,
  created_at timestamptz not null default now(),
  primary key(run_id,metric_scope,cost_bps)
);

insert into research.blankcanvas_pair_spyctx_holdout_run_v1(
  run_id,candidate_id,frozen_at,holdout_start,holdout_end,calculation_version,
  rule_json,data_snapshot_json,status,notes
)
select
  'BC-RV-TLTUSO-HO-20260813-V1',
  f.candidate_id,
  f.preholdout_frozen_at,
  date '2025-01-01',
  date '2026-08-11',
  'blankcanvas_tlt_uso_holdout_v1',
  jsonb_build_object(
    'signal','15-minute relative return divergence: TLT minus USO',
    'decision_minute_et',630,
    'signal_window_et','10:15 close to 10:30 close',
    'minimum_absolute_divergence_pct',0.05,
    'market_context','SPY 15-minute return >= -0.25% and < -0.10%',
    'style','fade divergence',
    'direction','div<0: long TLT/short USO; div>0: short TLT/long USO',
    'weights','50% long leg / 50% short leg',
    'entry','10:31 ET next-minute open',
    'exit','15:59 ET close; missing regular-session close is excluded and audited',
    'primary_cost_bps',5.0,
    'stress_cost_bps',jsonb_build_array(7.5,10.0),
    'primary_holdout_gate',jsonb_build_object(
      'all_avg_net5_gt_zero',true,
      'all_median_net5_gt_zero',true,
      'all_win_rate_gt_50pct',true,
      'all_trades_gte_20',true,
      '2025_avg_net5_gt_zero',true,
      '2026_ytd_avg_net5_gt_zero',true
    )
  ),
  jsonb_build_object(
    'source_table','research.blankcanvas_frozen_holdout_points_v1',
    'rows',(select count(*) from research.blankcanvas_frozen_holdout_points_v1),
    'market_days',(select count(*) from research.blankcanvas_frozen_holdout_points_v1 where symbol='SPY' and minute_et=615),
    'complete_12_point_days',(
      select count(*) from (
        select trade_date from research.blankcanvas_frozen_holdout_points_v1
        group by trade_date having count(*)=12
      ) x
    ),
    'min_date',(select min(trade_date) from research.blankcanvas_frozen_holdout_points_v1),
    'max_date',(select max(trade_date) from research.blankcanvas_frozen_holdout_points_v1),
    'max_loaded_at',(select max(loaded_at) from research.blankcanvas_frozen_holdout_points_v1)
  ),
  'OPENED',
  'Candidate and rule were frozen before loading or calculating holdout outcomes.'
from research.blankcanvas_pair_spyctx_preholdout_freeze_net5_v1 f
where f.candidate_id='4a2ccfe28e77fa0cb4587a512b55c2a6'
on conflict(run_id) do update set
  data_snapshot_json=excluded.data_snapshot_json,
  rule_json=excluded.rule_json,
  status='OPENED',
  completed_at=null,
  summary_json=null;

delete from research.blankcanvas_pair_spyctx_holdout_trade_ledger_v1
where run_id='BC-RV-TLTUSO-HO-20260813-V1';

with pivoted as (
  select trade_date,
    max(close) filter(where symbol='SPY' and minute_et=615) as spy_close_1015,
    max(close) filter(where symbol='SPY' and minute_et=630) as spy_close_1030,
    max(close) filter(where symbol='TLT' and minute_et=615) as tlt_close_1015,
    max(close) filter(where symbol='TLT' and minute_et=630) as tlt_close_1030,
    max(open)  filter(where symbol='TLT' and minute_et=631) as tlt_open_1031,
    max(close) filter(where symbol='TLT' and minute_et=959) as tlt_close_1559,
    max(close) filter(where symbol='USO' and minute_et=615) as uso_close_1015,
    max(close) filter(where symbol='USO' and minute_et=630) as uso_close_1030,
    max(open)  filter(where symbol='USO' and minute_et=631) as uso_open_1031,
    max(close) filter(where symbol='USO' and minute_et=959) as uso_close_1559,
    array_agg(distinct source_partition order by source_partition) as source_partitions
  from research.blankcanvas_frozen_holdout_points_v1
  where trade_date between date '2025-01-01' and date '2026-08-11'
  group by trade_date
), signals as (
  select p.*,
    (spy_close_1015 is not null and spy_close_1030 is not null
      and tlt_close_1015 is not null and tlt_close_1030 is not null
      and uso_close_1015 is not null and uso_close_1030 is not null) as signal_complete,
    (tlt_open_1031 is not null and uso_open_1031 is not null
      and tlt_close_1559 is not null and uso_close_1559 is not null) as exit_complete,
    case when spy_close_1015 is not null and spy_close_1030 is not null
      then 100*(spy_close_1030/spy_close_1015-1) end as spy_sig15_pct,
    case when tlt_close_1015 is not null and tlt_close_1030 is not null
      then 100*(tlt_close_1030/tlt_close_1015-1) end as tlt_sig15_pct,
    case when uso_close_1015 is not null and uso_close_1030 is not null
      then 100*(uso_close_1030/uso_close_1015-1) end as uso_sig15_pct,
    case when tlt_open_1031 is not null and tlt_close_1559 is not null
      then 100*(tlt_close_1559/tlt_open_1031-1) end as tlt_leg_return_pct,
    case when uso_open_1031 is not null and uso_close_1559 is not null
      then 100*(uso_close_1559/uso_open_1031-1) end as uso_leg_return_pct
  from pivoted p
), classified as (
  select s.*,
    tlt_sig15_pct-uso_sig15_pct as div_pct,
    case when spy_sig15_pct < -0.25 then 'strong_down'
         when spy_sig15_pct < -0.10 then 'down'
         when spy_sig15_pct <= 0.10 then 'flat'
         when spy_sig15_pct <= 0.25 then 'up'
         else 'strong_up' end as spy_context,
    case when exit_complete then 0.5*(tlt_leg_return_pct-uso_leg_return_pct) end as spread_close_pct
  from signals s
), resolved as (
  select c.*,
    (signal_complete and abs(div_pct)>=0.05 and spy_context='down') as triggered,
    case when signal_complete and abs(div_pct)>=0.05 and spy_context='down' and div_pct<0
           then 'LONG_TLT_SHORT_USO'
         when signal_complete and abs(div_pct)>=0.05 and spy_context='down' and div_pct>0
           then 'SHORT_TLT_LONG_USO' end as direction,
    case when signal_complete and abs(div_pct)>=0.05 and spy_context='down' and exit_complete
           then -sign(div_pct)*spread_close_pct end as gross_spread_pct
  from classified c
)
insert into research.blankcanvas_pair_spyctx_holdout_trade_ledger_v1(
  run_id,candidate_id,trade_date,signal_complete,exit_complete,triggered,excluded_reason,
  spy_sig15_pct,tlt_sig15_pct,uso_sig15_pct,div_pct,spy_context,direction,
  tlt_entry_open,uso_entry_open,tlt_exit_close,uso_exit_close,
  tlt_leg_return_pct,uso_leg_return_pct,spread_close_pct,gross_spread_pct,
  net5_pct,net7_5_pct,net10_pct,source_partitions
)
select
  'BC-RV-TLTUSO-HO-20260813-V1','4a2ccfe28e77fa0cb4587a512b55c2a6',trade_date,
  signal_complete,exit_complete,triggered,
  case when not signal_complete then 'MISSING_SIGNAL_POINT'
       when triggered and not exit_complete then 'MISSING_EXIT_POINT'
       else null end,
  spy_sig15_pct,tlt_sig15_pct,uso_sig15_pct,div_pct,spy_context,direction,
  tlt_open_1031,uso_open_1031,tlt_close_1559,uso_close_1559,
  tlt_leg_return_pct,uso_leg_return_pct,spread_close_pct,gross_spread_pct,
  case when gross_spread_pct is not null then gross_spread_pct-0.05 end,
  case when gross_spread_pct is not null then gross_spread_pct-0.075 end,
  case when gross_spread_pct is not null then gross_spread_pct-0.10 end,
  source_partitions
from resolved;

delete from research.blankcanvas_pair_spyctx_holdout_metrics_v1
where run_id='BC-RV-TLTUSO-HO-20260813-V1';

with scope_defs(metric_scope,scope_start,scope_end) as (
  values
    ('ALL',date '2025-01-01',date '2026-08-11'),
    ('2025',date '2025-01-01',date '2025-12-31'),
    ('2026_YTD',date '2026-01-01',date '2026-08-11')
), costs(cost_bps) as (values (5.0::double precision),(7.5),(10.0)),
signal_counts as (
  select d.metric_scope,d.scope_start,d.scope_end,
    count(*) filter(where l.triggered)::int as signals,
    count(*) filter(where l.triggered and l.exit_complete)::int as trades,
    count(*) filter(where l.triggered and not l.exit_complete)::int as excluded_incomplete
  from scope_defs d
  left join research.blankcanvas_pair_spyctx_holdout_trade_ledger_v1 l
    on l.run_id='BC-RV-TLTUSO-HO-20260813-V1'
   and l.trade_date between d.scope_start and d.scope_end
  group by d.metric_scope,d.scope_start,d.scope_end
), trades as (
  select d.metric_scope,d.scope_start,d.scope_end,c.cost_bps,l.trade_date,
         l.gross_spread_pct-c.cost_bps/100.0 as net_pct
  from scope_defs d cross join costs c
  join research.blankcanvas_pair_spyctx_holdout_trade_ledger_v1 l
    on l.run_id='BC-RV-TLTUSO-HO-20260813-V1'
   and l.trade_date between d.scope_start and d.scope_end
   and l.triggered and l.exit_complete
), seq as (
  select t.*,
         100*exp(sum(ln(1+net_pct/100.0)) over(
           partition by metric_scope,cost_bps order by trade_date rows unbounded preceding
         )) as equity_index
  from trades t
), seq2 as (
  select s.*,
         max(equity_index) over(
           partition by metric_scope,cost_bps order by trade_date rows unbounded preceding
         ) as running_max
  from seq s
), agg as (
  select metric_scope,cost_bps,count(*)::int as trades,
         avg(net_pct) as avg_net_pct,
         percentile_cont(0.5) within group(order by net_pct) as median_net_pct,
         avg((net_pct>0)::int)*100 as win_rate_pct,
         avg(net_pct) filter(where net_pct>0) as avg_win_pct,
         avg(net_pct) filter(where net_pct<0) as avg_loss_pct,
         min(net_pct) as worst_trade_pct,max(net_pct) as best_trade_pct,
         sum(net_pct) filter(where net_pct>0)/nullif(abs(sum(net_pct) filter(where net_pct<0)),0) as profit_factor,
         sum(net_pct) as sum_net_pct,
         100*(exp(sum(ln(1+net_pct/100.0)))-1) as compound_return_pct,
         avg(net_pct)/nullif(stddev_samp(net_pct)/sqrt(count(*)),0) as t_stat,
         avg(net_pct)-1.96*stddev_samp(net_pct)/sqrt(count(*)) as mean_ci95_low,
         avg(net_pct)+1.96*stddev_samp(net_pct)/sqrt(count(*)) as mean_ci95_high
  from trades group by metric_scope,cost_bps
), dd as (
  select metric_scope,cost_bps,
         abs(100*min(equity_index/nullif(running_max,0)-1)) as max_drawdown_pct
  from seq2 group by metric_scope,cost_bps
)
insert into research.blankcanvas_pair_spyctx_holdout_metrics_v1(
  run_id,metric_scope,cost_bps,scope_start,scope_end,signals,trades,excluded_incomplete,
  avg_net_pct,median_net_pct,win_rate_pct,avg_win_pct,avg_loss_pct,worst_trade_pct,best_trade_pct,
  profit_factor,sum_net_pct,compound_return_pct,max_drawdown_pct,t_stat,mean_ci95_low,mean_ci95_high
)
select 'BC-RV-TLTUSO-HO-20260813-V1',d.metric_scope,c.cost_bps,d.scope_start,d.scope_end,
       s.signals,coalesce(a.trades,0),s.excluded_incomplete,
       a.avg_net_pct,a.median_net_pct,a.win_rate_pct,a.avg_win_pct,a.avg_loss_pct,
       a.worst_trade_pct,a.best_trade_pct,a.profit_factor,a.sum_net_pct,a.compound_return_pct,
       dd.max_drawdown_pct,a.t_stat,a.mean_ci95_low,a.mean_ci95_high
from scope_defs d cross join costs c
join signal_counts s using(metric_scope,scope_start,scope_end)
left join agg a on a.metric_scope=d.metric_scope and a.cost_bps=c.cost_bps
left join dd on dd.metric_scope=d.metric_scope and dd.cost_bps=c.cost_bps;

with all5 as (
  select * from research.blankcanvas_pair_spyctx_holdout_metrics_v1
  where run_id='BC-RV-TLTUSO-HO-20260813-V1' and metric_scope='ALL' and cost_bps=5.0
), segments as (
  select count(*)::int as segment_count,min(avg_net_pct) as worst_segment_avg
  from research.blankcanvas_pair_spyctx_holdout_metrics_v1
  where run_id='BC-RV-TLTUSO-HO-20260813-V1'
    and metric_scope in ('2025','2026_YTD') and cost_bps=5.0
), summary as (
  select jsonb_object_agg(metric_scope,jsonb_build_object(
    'signals',signals,'trades',trades,'excluded_incomplete',excluded_incomplete,
    'avg_net_pct',avg_net_pct,'median_net_pct',median_net_pct,'win_rate_pct',win_rate_pct,
    'profit_factor',profit_factor,'compound_return_pct',compound_return_pct,
    'max_drawdown_pct',max_drawdown_pct,'mean_ci95_low',mean_ci95_low,'mean_ci95_high',mean_ci95_high
  )) as metrics5
  from research.blankcanvas_pair_spyctx_holdout_metrics_v1
  where run_id='BC-RV-TLTUSO-HO-20260813-V1' and cost_bps=5.0
)
update research.blankcanvas_pair_spyctx_holdout_run_v1 r
set completed_at=now(),
    status=case when a.avg_net_pct>0 and a.median_net_pct>0 and a.win_rate_pct>50
                      and a.trades>=20 and s.segment_count=2 and s.worst_segment_avg>0
                then 'PASSED_PRIMARY_HOLDOUT'
                else 'FAILED_PRIMARY_HOLDOUT' end,
    summary_json=jsonb_build_object('primary_cost_bps',5.0,'metrics',q.metrics5)
from all5 a cross join segments s cross join summary q
where r.run_id='BC-RV-TLTUSO-HO-20260813-V1';
