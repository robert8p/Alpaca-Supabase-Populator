-- Campaign: WEAKCLOSE-COMPOSITE-20260813-V1
-- Preregistration commit: 4a297d623d7ebf7e2492000d1b96f15bb0e03816
-- Inference commit: 64f254a6409a20b06d88a5f6e6e3b40d82c3c00b
-- This code was committed before any validation return for this campaign was queried.

create schema if not exists research;

create table if not exists research.blankcanvas_weakclose_definition_freeze_v1 (
  campaign_id text not null,
  candidate_id text not null,
  construction text not null check(construction in ('SHORT_WEAK','STRONG_MINUS_WEAK')),
  top_n smallint not null check(top_n in (1,2)),
  target text not null check(target='next_ret_oc'),
  signal_features text[] not null,
  primary_cost_bps double precision not null,
  stress_cost_bps double precision not null,
  preregistration_commit text not null,
  inference_commit text not null,
  calculation_commit text,
  ancestry_registered_definitions integer not null,
  frozen_at timestamptz not null default now(),
  primary key(campaign_id,candidate_id),
  unique(campaign_id,construction,top_n)
);

create table if not exists research.blankcanvas_weakclose_score_v1 (
  campaign_id text not null,
  split text not null check(split in ('DISCOVERY','INNER_VALIDATION','OUTER_PREHOLDOUT')),
  signal_date date not null,
  next_date date not null,
  symbol text not null,
  liquidity_rank integer not null,
  calibration_avg_dollar_volume double precision not null,
  signal_universe_count integer not null,
  ret_oc double precision not null,
  close_vs_vwap double precision not null,
  close_location double precision not null,
  max_drawdown_from_open double precision not null,
  last60_ret double precision not null,
  last30_ret double precision not null,
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
  primary key(campaign_id,split,signal_date,symbol)
);
create index if not exists blankcanvas_weakclose_score_rank_idx
  on research.blankcanvas_weakclose_score_v1(campaign_id,split,signal_date,weak_entry_rank,strong_entry_rank);

create table if not exists research.blankcanvas_weakclose_daily_v1 (
  campaign_id text not null,
  candidate_id text not null,
  split text not null check(split in ('DISCOVERY','INNER_VALIDATION','OUTER_PREHOLDOUT')),
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
  primary key(campaign_id,candidate_id,signal_date)
);
create index if not exists blankcanvas_weakclose_daily_scope_idx
  on research.blankcanvas_weakclose_daily_v1(campaign_id,candidate_id,split,signal_date);

create table if not exists research.blankcanvas_weakclose_metrics_v1 (
  campaign_id text not null,
  candidate_id text not null,
  metric_scope text not null check(metric_scope in ('DISCOVERY','INNER_VALIDATION','OUTER_PREHOLDOUT','COMBINED_VALIDATION')),
  scope_start date not null,
  scope_end date not null,
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
  positive_pnl_concentration double precision,
  created_at timestamptz not null default now(),
  primary key(campaign_id,candidate_id,metric_scope)
);

create table if not exists research.blankcanvas_weakclose_validation_gate_v1 (
  campaign_id text not null,
  candidate_id text not null,
  inner_pass boolean not null,
  outer_pass boolean not null,
  combined_prebootstrap_pass boolean not null,
  bootstrap_ci_low double precision,
  bootstrap_ci_high double precision,
  bootstrap_p_value double precision,
  bh_q_value double precision,
  final_preholdout_pass boolean,
  inference_seed bigint,
  bootstrap_replications integer,
  block_length integer,
  evaluated_at timestamptz not null default now(),
  primary key(campaign_id,candidate_id)
);

begin;

insert into research.blankcanvas_weakclose_definition_freeze_v1(
  campaign_id,candidate_id,construction,top_n,target,signal_features,
  primary_cost_bps,stress_cost_bps,preregistration_commit,inference_commit,
  calculation_commit,ancestry_registered_definitions
)
values
 ('WEAKCLOSE-COMPOSITE-20260813-V1','WCC-SHORT-WEAK-N1','SHORT_WEAK',1,'next_ret_oc',
  array['ret_oc','close_vs_vwap','close_location','max_drawdown_from_open','last60_ret','last30_ret'],
  10,20,'4a297d623d7ebf7e2492000d1b96f15bb0e03816','64f254a6409a20b06d88a5f6e6e3b40d82c3c00b',null,3748),
 ('WEAKCLOSE-COMPOSITE-20260813-V1','WCC-SHORT-WEAK-N2','SHORT_WEAK',2,'next_ret_oc',
  array['ret_oc','close_vs_vwap','close_location','max_drawdown_from_open','last60_ret','last30_ret'],
  10,20,'4a297d623d7ebf7e2492000d1b96f15bb0e03816','64f254a6409a20b06d88a5f6e6e3b40d82c3c00b',null,3748),
 ('WEAKCLOSE-COMPOSITE-20260813-V1','WCC-STRONG-MINUS-WEAK-N1','STRONG_MINUS_WEAK',1,'next_ret_oc',
  array['ret_oc','close_vs_vwap','close_location','max_drawdown_from_open','last60_ret','last30_ret'],
  10,20,'4a297d623d7ebf7e2492000d1b96f15bb0e03816','64f254a6409a20b06d88a5f6e6e3b40d82c3c00b',null,3748),
 ('WEAKCLOSE-COMPOSITE-20260813-V1','WCC-STRONG-MINUS-WEAK-N2','STRONG_MINUS_WEAK',2,'next_ret_oc',
  array['ret_oc','close_vs_vwap','close_location','max_drawdown_from_open','last60_ret','last30_ret'],
  10,20,'4a297d623d7ebf7e2492000d1b96f15bb0e03816','64f254a6409a20b06d88a5f6e6e3b40d82c3c00b',null,3748)
on conflict(campaign_id,candidate_id) do nothing;

delete from research.blankcanvas_weakclose_score_v1
where campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1';

delete from research.blankcanvas_weakclose_daily_v1
where campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1';

delete from research.blankcanvas_weakclose_metrics_v1
where campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1';

delete from research.blankcanvas_weakclose_validation_gate_v1
where campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1';

with date_map as materialized (
  select distinct
    case
      when split='DISCOVERY' then 'DISCOVERY'
      when signal_date<=date '2025-10-07' then 'INNER_VALIDATION'
      else 'OUTER_PREHOLDOUT'
    end as split,
    signal_date,next_date
  from research.blankcanvas_extreme_preholdout_states_v1
), fixed_universe as materialized (
  select u.symbol,u.liquidity_rank,u.calibration_avg_dollar_volume
  from public.rd_blankcanvas_equity_universe_v2 u
  join research.blankcanvas_extreme_asset_eligibility_v1 a using(symbol)
  where a.instrument_group='OPERATING_EQUITY'
    and a.research_short_eligible
), signal_base as materialized (
  select d.split,d.signal_date,d.next_date,u.symbol,u.liquidity_rank,
         u.calibration_avg_dollar_volume,
         s.ret_oc,s.close_vs_vwap,s.close_location,s.max_drawdown_from_open,
         s.last60_ret,s.last30_ret,n.open_price as next_open,n.close_price as next_close
  from date_map d
  cross join fixed_universe u
  join public.rd_blankcanvas_equity_daily_v2 s
    on s.symbol=u.symbol and s.trade_date=d.signal_date
  left join public.rd_blankcanvas_equity_daily_v2 n
    on n.symbol=u.symbol and n.trade_date=d.next_date
  where s.ret_oc is not null and s.close_vs_vwap is not null
    and s.close_location is not null and s.max_drawdown_from_open is not null
    and s.last60_ret is not null and s.last30_ret is not null
), ranked_features as materialized (
  select b.*,
         count(*) over(partition by split,signal_date)::integer as signal_universe_count,
         row_number() over(partition by split,signal_date order by ret_oc,symbol) as r_ret_oc,
         row_number() over(partition by split,signal_date order by close_vs_vwap,symbol) as r_close_vs_vwap,
         row_number() over(partition by split,signal_date order by close_location,symbol) as r_close_location,
         row_number() over(partition by split,signal_date order by max_drawdown_from_open,symbol) as r_max_drawdown,
         row_number() over(partition by split,signal_date order by last60_ret,symbol) as r_last60,
         row_number() over(partition by split,signal_date order by last30_ret,symbol) as r_last30
  from signal_base b
), scored as materialized (
  select r.*,
         (r_ret_oc-1)::double precision/nullif(signal_universe_count-1,0) as ret_oc_rank,
         (r_close_vs_vwap-1)::double precision/nullif(signal_universe_count-1,0) as close_vs_vwap_rank,
         (r_close_location-1)::double precision/nullif(signal_universe_count-1,0) as close_location_rank,
         (r_max_drawdown-1)::double precision/nullif(signal_universe_count-1,0) as max_drawdown_rank,
         (r_last60-1)::double precision/nullif(signal_universe_count-1,0) as last60_rank,
         (r_last30-1)::double precision/nullif(signal_universe_count-1,0) as last30_rank
  from ranked_features r
  where signal_universe_count>=200
), composite as materialized (
  select s.*,
         (ret_oc_rank+close_vs_vwap_rank+close_location_rank+max_drawdown_rank+last60_rank+last30_rank)/6.0
           as composite_score,
         (next_open is not null and next_open>=5) as entry_price_eligible
  from scored s
), entry_ranked as materialized (
  select c.*,
         case when entry_price_eligible then
           row_number() over(
             partition by split,signal_date,entry_price_eligible
             order by composite_score,symbol
           ) end::integer as weak_entry_rank,
         case when entry_price_eligible then
           row_number() over(
             partition by split,signal_date,entry_price_eligible
             order by composite_score desc,symbol
           ) end::integer as strong_entry_rank
  from composite c
)
insert into research.blankcanvas_weakclose_score_v1(
  campaign_id,split,signal_date,next_date,symbol,liquidity_rank,
  calibration_avg_dollar_volume,signal_universe_count,
  ret_oc,close_vs_vwap,close_location,max_drawdown_from_open,last60_ret,last30_ret,
  ret_oc_rank,close_vs_vwap_rank,close_location_rank,max_drawdown_rank,last60_rank,last30_rank,
  composite_score,next_open,next_close,entry_price_eligible,weak_entry_rank,strong_entry_rank
)
select 'WEAKCLOSE-COMPOSITE-20260813-V1',split,signal_date,next_date,symbol,liquidity_rank,
       calibration_avg_dollar_volume,signal_universe_count,
       ret_oc,close_vs_vwap,close_location,max_drawdown_from_open,last60_ret,last30_ret,
       ret_oc_rank,close_vs_vwap_rank,close_location_rank,max_drawdown_rank,last60_rank,last30_rank,
       composite_score,next_open,next_close,entry_price_eligible,weak_entry_rank,strong_entry_rank
from entry_ranked;

with ns(top_n) as (values(1::smallint),(2::smallint)),
selection as materialized (
  select s.split,s.signal_date,max(s.next_date) as next_date,n.top_n,
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
         min(s.next_open) filter(where s.weak_entry_rank<=n.top_n or s.strong_entry_rank<=n.top_n) as min_selected_open
  from research.blankcanvas_weakclose_score_v1 s
  cross join ns n
  where s.campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1'
  group by s.split,s.signal_date,n.top_n
), prepared as materialized (
  select x.*,x.weak_symbols && x.strong_symbols as baskets_overlap
  from selection x
), definitions as (
  select * from research.blankcanvas_weakclose_definition_freeze_v1
  where campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1'
)
insert into research.blankcanvas_weakclose_daily_v1(
  campaign_id,candidate_id,split,signal_date,next_date,construction,top_n,
  signal_universe_count,entry_eligible_count,weak_actual_names,strong_actual_names,
  weak_target_count,strong_target_count,weak_symbols,strong_symbols,baskets_overlap,
  weak_avg_return,strong_avg_return,gross_return,net_return_10bp,net_return_20bp,
  min_selected_open,trade_complete,excluded_reason
)
select d.campaign_id,d.candidate_id,p.split,p.signal_date,p.next_date,d.construction,d.top_n,
       p.signal_universe_count,p.entry_eligible_count,p.weak_actual_names,p.strong_actual_names,
       p.weak_target_count,p.strong_target_count,p.weak_symbols,p.strong_symbols,p.baskets_overlap,
       p.weak_avg_return,p.strong_avg_return,
       case when d.construction='SHORT_WEAK' then -p.weak_avg_return
            else 0.5*(p.strong_avg_return-p.weak_avg_return) end as gross_return,
       case when
         p.signal_universe_count>=200 and p.weak_actual_names=d.top_n and p.weak_target_count=d.top_n
         and (d.construction='SHORT_WEAK' or
              (p.strong_actual_names=d.top_n and p.strong_target_count=d.top_n and not p.baskets_overlap))
         then (case when d.construction='SHORT_WEAK' then -p.weak_avg_return
                    else 0.5*(p.strong_avg_return-p.weak_avg_return) end)-0.0010 end,
       case when
         p.signal_universe_count>=200 and p.weak_actual_names=d.top_n and p.weak_target_count=d.top_n
         and (d.construction='SHORT_WEAK' or
              (p.strong_actual_names=d.top_n and p.strong_target_count=d.top_n and not p.baskets_overlap))
         then (case when d.construction='SHORT_WEAK' then -p.weak_avg_return
                    else 0.5*(p.strong_avg_return-p.weak_avg_return) end)-0.0020 end,
       p.min_selected_open,
       (p.signal_universe_count>=200 and p.weak_actual_names=d.top_n and p.weak_target_count=d.top_n
         and (d.construction='SHORT_WEAK' or
              (p.strong_actual_names=d.top_n and p.strong_target_count=d.top_n and not p.baskets_overlap))) as trade_complete,
       case
         when p.signal_universe_count<200 then 'SIGNAL_UNIVERSE_LT_200'
         when p.weak_actual_names<d.top_n then 'INSUFFICIENT_WEAK_ENTRY_NAMES'
         when p.weak_target_count<d.top_n then 'MISSING_WEAK_EXIT'
         when d.construction='STRONG_MINUS_WEAK' and p.strong_actual_names<d.top_n then 'INSUFFICIENT_STRONG_ENTRY_NAMES'
         when d.construction='STRONG_MINUS_WEAK' and p.strong_target_count<d.top_n then 'MISSING_STRONG_EXIT'
         when d.construction='STRONG_MINUS_WEAK' and p.baskets_overlap then 'BASKET_OVERLAP'
         else null end
from prepared p
join definitions d on d.top_n=p.top_n;

with scopes(metric_scope,scope_start,scope_end) as (
  values
   ('DISCOVERY',date '2025-06-02',date '2025-09-11'),
   ('INNER_VALIDATION',date '2025-09-15',date '2025-10-07'),
   ('OUTER_PREHOLDOUT',date '2025-10-08',date '2025-10-30'),
   ('COMBINED_VALIDATION',date '2025-09-15',date '2025-10-30')
)
insert into research.blankcanvas_weakclose_metrics_v1(
  campaign_id,candidate_id,metric_scope,scope_start,scope_end,expected_days,trades,excluded_days,
  avg_gross,avg_net10,median_net10,win_rate10,avg_win10,avg_loss10,worst_trade10,best_trade10,
  profit_factor10,t_stat10,avg_net20,positive_pnl_concentration
)
select 'WEAKCLOSE-COMPOSITE-20260813-V1',d.candidate_id,s.metric_scope,s.scope_start,s.scope_end,
       count(*)::integer,
       count(*) filter(where x.trade_complete)::integer,
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
       max(x.net_return_10bp) filter(where x.trade_complete and x.net_return_10bp>0)
         /nullif(sum(x.net_return_10bp) filter(where x.trade_complete and x.net_return_10bp>0),0)
from scopes s
cross join research.blankcanvas_weakclose_definition_freeze_v1 d
join research.blankcanvas_weakclose_daily_v1 x
  on x.campaign_id=d.campaign_id and x.candidate_id=d.candidate_id
 and x.signal_date between s.scope_start and s.scope_end
where d.campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1'
group by d.candidate_id,s.metric_scope,s.scope_start,s.scope_end;

insert into research.blankcanvas_weakclose_validation_gate_v1(
  campaign_id,candidate_id,inner_pass,outer_pass,combined_prebootstrap_pass,
  inference_seed,bootstrap_replications,block_length
)
select 'WEAKCLOSE-COMPOSITE-20260813-V1',d.candidate_id,
       (i.trades>=15 and i.avg_net10>0 and i.median_net10>0 and i.win_rate10>0.52
          and i.profit_factor10>1.20 and i.avg_net20>0),
       (o.trades>=15 and o.avg_net10>0 and o.median_net10>0 and o.win_rate10>0.50
          and o.profit_factor10>1.10 and o.avg_net20>0),
       (c.avg_net10>0 and c.median_net10>0 and c.win_rate10>0.52
          and c.profit_factor10>=1.30 and c.avg_net20>0 and c.t_stat10>=2.50),
       20260813,20000,5
from research.blankcanvas_weakclose_definition_freeze_v1 d
join research.blankcanvas_weakclose_metrics_v1 i
  on i.campaign_id=d.campaign_id and i.candidate_id=d.candidate_id and i.metric_scope='INNER_VALIDATION'
join research.blankcanvas_weakclose_metrics_v1 o
  on o.campaign_id=d.campaign_id and o.candidate_id=d.candidate_id and o.metric_scope='OUTER_PREHOLDOUT'
join research.blankcanvas_weakclose_metrics_v1 c
  on c.campaign_id=d.campaign_id and c.candidate_id=d.candidate_id and c.metric_scope='COMBINED_VALIDATION'
where d.campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1';

commit;
