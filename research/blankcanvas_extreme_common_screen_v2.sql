-- Campaign: EXTREME-COMMON-20260813-V2
-- This script calculates discovery metrics only. It does not read validation or holdout outcomes.

create schema if not exists research;

create table if not exists research.blankcanvas_extreme_common_search_audit_v2 (
  campaign_id text primary key,
  registered_definitions integer not null,
  promotable_definitions integer not null,
  observed_definitions integer not null,
  complete_discovery_definitions integer not null,
  discovery_start date not null,
  discovery_end date not null,
  source_table text not null,
  preregistration_commit text not null,
  calculation_commit text,
  calculated_at timestamptz not null default now()
);

create table if not exists research.blankcanvas_extreme_common_discovery_metrics_v2 (
  campaign_id text not null,
  candidate_id text not null,
  feature text not null,
  q smallint not null,
  target text not null,
  direction smallint not null,
  top_n smallint not null,
  n integer not null,
  start_date date not null,
  end_date date not null,
  min_actual_names smallint not null,
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
  avg_residual double precision,
  positive_pnl_concentration double precision,
  created_at timestamptz not null default now(),
  primary key(campaign_id,candidate_id),
  unique(campaign_id,feature,q,target,direction,top_n)
);

create table if not exists research.blankcanvas_extreme_common_discovery_shortlist_v2 (
  campaign_id text not null,
  candidate_id text not null,
  feature text not null,
  q smallint not null,
  target text not null,
  direction smallint not null,
  top_n smallint not null,
  n integer not null,
  avg_net10 double precision not null,
  median_net10 double precision not null,
  win_rate10 double precision not null,
  profit_factor10 double precision not null,
  t_stat10 double precision not null,
  avg_net20 double precision not null,
  avg_residual double precision not null,
  positive_pnl_concentration double precision not null,
  frozen_for_validation_at timestamptz not null default now(),
  primary key(campaign_id,candidate_id)
);

begin;

delete from research.blankcanvas_extreme_common_discovery_metrics_v2
where campaign_id='EXTREME-COMMON-20260813-V2';

delete from research.blankcanvas_extreme_common_discovery_shortlist_v2
where campaign_id='EXTREME-COMMON-20260813-V2';

insert into research.blankcanvas_extreme_common_discovery_metrics_v2(
  campaign_id,candidate_id,feature,q,target,direction,top_n,n,start_date,end_date,
  min_actual_names,avg_net10,median_net10,win_rate10,avg_win10,avg_loss10,
  worst_trade10,best_trade10,profit_factor10,t_stat10,avg_net20,avg_residual,
  positive_pnl_concentration
)
select
  'EXTREME-COMMON-20260813-V2',
  md5(concat_ws('|',feature,q,target,direction,top_n)),
  feature,q,target,direction,top_n,
  count(*)::integer,min(signal_date),max(signal_date),min(actual_names),
  avg(net_return_10bp),
  percentile_cont(0.5) within group(order by net_return_10bp),
  avg((net_return_10bp>0)::integer)::double precision,
  avg(net_return_10bp) filter(where net_return_10bp>0),
  avg(net_return_10bp) filter(where net_return_10bp<0),
  min(net_return_10bp),max(net_return_10bp),
  sum(net_return_10bp) filter(where net_return_10bp>0)
    /nullif(abs(sum(net_return_10bp) filter(where net_return_10bp<0)),0),
  avg(net_return_10bp)
    /nullif(stddev_samp(net_return_10bp)/sqrt(count(*)),0),
  avg(net_return_20bp),
  avg(residual_return),
  max(net_return_10bp) filter(where net_return_10bp>0)
    /nullif(sum(net_return_10bp) filter(where net_return_10bp>0),0)
from research.blankcanvas_extreme_common_daily_v1
where split='DISCOVERY'
group by feature,q,target,direction,top_n;

insert into research.blankcanvas_extreme_common_discovery_shortlist_v2(
  campaign_id,candidate_id,feature,q,target,direction,top_n,n,
  avg_net10,median_net10,win_rate10,profit_factor10,t_stat10,avg_net20,
  avg_residual,positive_pnl_concentration
)
select
  campaign_id,candidate_id,feature,q,target,direction,top_n,n,
  avg_net10,median_net10,win_rate10,profit_factor10,t_stat10,avg_net20,
  avg_residual,positive_pnl_concentration
from research.blankcanvas_extreme_common_discovery_metrics_v2
where campaign_id='EXTREME-COMMON-20260813-V2'
  and top_n in (1,2,3)
  and n>=65
  and min_actual_names=top_n
  and avg_net10>=0.0015
  and median_net10>0
  and win_rate10>0.55
  and profit_factor10>=1.50
  and t_stat10>=4.25
  and avg_net20>0
  and avg_residual>0
  and positive_pnl_concentration<=0.25;

insert into research.blankcanvas_extreme_common_search_audit_v2(
  campaign_id,registered_definitions,promotable_definitions,observed_definitions,
  complete_discovery_definitions,discovery_start,discovery_end,source_table,
  preregistration_commit,calculation_commit,calculated_at
)
select
  'EXTREME-COMMON-20260813-V2',2496,1872,
  count(*)::integer,
  count(*) filter(where n>=65 and min_actual_names=top_n)::integer,
  date '2025-06-02',date '2025-09-11',
  'research.blankcanvas_extreme_common_daily_v1',
  '62baae21b636f481d8b23c83aabbdc5efb5066a5',
  null,now()
from research.blankcanvas_extreme_common_discovery_metrics_v2
where campaign_id='EXTREME-COMMON-20260813-V2'
on conflict(campaign_id) do update set
  registered_definitions=excluded.registered_definitions,
  promotable_definitions=excluded.promotable_definitions,
  observed_definitions=excluded.observed_definitions,
  complete_discovery_definitions=excluded.complete_discovery_definitions,
  discovery_start=excluded.discovery_start,
  discovery_end=excluded.discovery_end,
  source_table=excluded.source_table,
  preregistration_commit=excluded.preregistration_commit,
  calculation_commit=excluded.calculation_commit,
  calculated_at=excluded.calculated_at;

commit;
