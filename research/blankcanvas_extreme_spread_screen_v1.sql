-- Campaign: EXTREME-SPREAD-20260813-V1
-- This script can load only DISCOVERY or VALIDATION from the protected preholdout common-equity panel.
-- The discovery calculation below does not query validation or holdout outcomes.

create schema if not exists research;

create table if not exists research.blankcanvas_extreme_spread_daily_v1 (
  split text not null check(split in ('DISCOVERY','VALIDATION')),
  signal_date date not null,
  next_date date not null,
  feature text not null,
  target text not null,
  orientation smallint not null check(orientation in (-1,1)),
  top_n smallint not null check(top_n in (1,2,3,5)),
  low_actual_names smallint not null,
  high_actual_names smallint not null,
  low_symbols text[] not null,
  high_symbols text[] not null,
  baskets_overlap boolean not null,
  gross_return double precision not null,
  net_return_10bp double precision not null,
  net_return_20bp double precision not null,
  min_next_open double precision not null,
  min_next_day_dollar_volume double precision not null,
  created_at timestamptz not null default now(),
  primary key(split,signal_date,feature,target,orientation,top_n)
);
create index if not exists blankcanvas_extreme_spread_candidate_idx
  on research.blankcanvas_extreme_spread_daily_v1(feature,target,orientation,top_n,split,signal_date);

create or replace function research.load_blankcanvas_extreme_spread_daily_v1(p_split text)
returns integer
language plpgsql
security invoker
set search_path=research,public,pg_temp
as $function$
declare v_rows integer;
begin
  if p_split not in ('DISCOVERY','VALIDATION') then raise exception 'invalid split %',p_split; end if;

  insert into research.blankcanvas_extreme_spread_daily_v1(
    split,signal_date,next_date,feature,target,orientation,top_n,
    low_actual_names,high_actual_names,low_symbols,high_symbols,baskets_overlap,
    gross_return,net_return_10bp,net_return_20bp,min_next_open,min_next_day_dollar_volume
  )
  select
    l.split,l.signal_date,l.next_date,l.feature,l.target,o.orientation,l.top_n,
    l.actual_names,h.actual_names,l.symbols,h.symbols,l.symbols && h.symbols,
    o.orientation*0.5*(h.gross_return-l.gross_return) as gross_return,
    o.orientation*0.5*(h.gross_return-l.gross_return)-0.0010,
    o.orientation*0.5*(h.gross_return-l.gross_return)-0.0020,
    least(l.min_next_open,h.min_next_open),
    least(l.min_next_day_dollar_volume,h.min_next_day_dollar_volume)
  from research.blankcanvas_extreme_common_daily_v1 l
  join research.blankcanvas_extreme_common_daily_v1 h
    on h.split=l.split and h.signal_date=l.signal_date and h.next_date=l.next_date
   and h.feature=l.feature and h.target=l.target and h.top_n=l.top_n
   and h.q=5 and h.direction=1
  cross join (values(1::smallint),(-1::smallint)) o(orientation)
  where l.split=p_split and l.q=1 and l.direction=1
  on conflict do nothing;
  get diagnostics v_rows=row_count;
  return v_rows;
end;
$function$;

create table if not exists research.blankcanvas_extreme_spread_search_audit_v1 (
  campaign_id text primary key,
  registered_definitions integer not null,
  promotable_definitions integer not null,
  observed_definitions integer not null,
  complete_discovery_definitions integer not null,
  preregistration_commit text not null,
  calculation_commit text,
  calculated_at timestamptz not null default now()
);

create table if not exists research.blankcanvas_extreme_spread_discovery_metrics_v1 (
  campaign_id text not null,
  candidate_id text not null,
  feature text not null,
  target text not null,
  orientation smallint not null,
  top_n smallint not null,
  n integer not null,
  start_date date not null,
  end_date date not null,
  min_low_actual_names smallint not null,
  min_high_actual_names smallint not null,
  overlap_days integer not null,
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
  primary key(campaign_id,candidate_id),
  unique(campaign_id,feature,target,orientation,top_n)
);

create table if not exists research.blankcanvas_extreme_spread_discovery_shortlist_v1 (
  campaign_id text not null,
  candidate_id text not null,
  feature text not null,
  target text not null,
  orientation smallint not null,
  top_n smallint not null,
  n integer not null,
  avg_net10 double precision not null,
  median_net10 double precision not null,
  win_rate10 double precision not null,
  profit_factor10 double precision not null,
  t_stat10 double precision not null,
  avg_net20 double precision not null,
  positive_pnl_concentration double precision not null,
  frozen_for_validation_at timestamptz not null default now(),
  primary key(campaign_id,candidate_id)
);

-- Run after load_blankcanvas_extreme_spread_daily_v1('DISCOVERY').
begin;
delete from research.blankcanvas_extreme_spread_discovery_metrics_v1
where campaign_id='EXTREME-SPREAD-20260813-V1';
delete from research.blankcanvas_extreme_spread_discovery_shortlist_v1
where campaign_id='EXTREME-SPREAD-20260813-V1';

insert into research.blankcanvas_extreme_spread_discovery_metrics_v1(
  campaign_id,candidate_id,feature,target,orientation,top_n,n,start_date,end_date,
  min_low_actual_names,min_high_actual_names,overlap_days,avg_net10,median_net10,
  win_rate10,avg_win10,avg_loss10,worst_trade10,best_trade10,profit_factor10,t_stat10,
  avg_net20,positive_pnl_concentration
)
select
  'EXTREME-SPREAD-20260813-V1',md5(concat_ws('|',feature,target,orientation,top_n)),
  feature,target,orientation,top_n,count(*)::integer,min(signal_date),max(signal_date),
  min(low_actual_names),min(high_actual_names),count(*) filter(where baskets_overlap)::integer,
  avg(net_return_10bp),percentile_cont(0.5) within group(order by net_return_10bp),
  avg((net_return_10bp>0)::integer)::double precision,
  avg(net_return_10bp) filter(where net_return_10bp>0),
  avg(net_return_10bp) filter(where net_return_10bp<0),
  min(net_return_10bp),max(net_return_10bp),
  sum(net_return_10bp) filter(where net_return_10bp>0)
    /nullif(abs(sum(net_return_10bp) filter(where net_return_10bp<0)),0),
  avg(net_return_10bp)/nullif(stddev_samp(net_return_10bp)/sqrt(count(*)),0),
  avg(net_return_20bp),
  max(net_return_10bp) filter(where net_return_10bp>0)
    /nullif(sum(net_return_10bp) filter(where net_return_10bp>0),0)
from research.blankcanvas_extreme_spread_daily_v1
where split='DISCOVERY'
group by feature,target,orientation,top_n;

insert into research.blankcanvas_extreme_spread_discovery_shortlist_v1(
  campaign_id,candidate_id,feature,target,orientation,top_n,n,avg_net10,median_net10,
  win_rate10,profit_factor10,t_stat10,avg_net20,positive_pnl_concentration
)
select campaign_id,candidate_id,feature,target,orientation,top_n,n,avg_net10,median_net10,
  win_rate10,profit_factor10,t_stat10,avg_net20,positive_pnl_concentration
from research.blankcanvas_extreme_spread_discovery_metrics_v1
where campaign_id='EXTREME-SPREAD-20260813-V1'
  and top_n in (1,2)
  and n>=65
  and min_low_actual_names=top_n and min_high_actual_names=top_n
  and overlap_days=0
  and avg_net10>=0.0010
  and median_net10>0
  and win_rate10>0.55
  and profit_factor10>=1.50
  and t_stat10>=4.25
  and avg_net20>0
  and positive_pnl_concentration<=0.25;

insert into research.blankcanvas_extreme_spread_search_audit_v1(
  campaign_id,registered_definitions,promotable_definitions,observed_definitions,
  complete_discovery_definitions,preregistration_commit,calculation_commit,calculated_at
)
select 'EXTREME-SPREAD-20260813-V1',1248,624,count(*)::integer,
  count(*) filter(where n>=65 and min_low_actual_names=top_n and min_high_actual_names=top_n and overlap_days=0)::integer,
  '3176b37b8a1aa05c21df81f17716a63292d24ec0',null,now()
from research.blankcanvas_extreme_spread_discovery_metrics_v1
where campaign_id='EXTREME-SPREAD-20260813-V1'
on conflict(campaign_id) do update set
  registered_definitions=excluded.registered_definitions,
  promotable_definitions=excluded.promotable_definitions,
  observed_definitions=excluded.observed_definitions,
  complete_discovery_definitions=excluded.complete_discovery_definitions,
  preregistration_commit=excluded.preregistration_commit,
  calculation_commit=excluded.calculation_commit,
  calculated_at=excluded.calculated_at;
commit;
