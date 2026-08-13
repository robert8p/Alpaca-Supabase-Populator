-- Frozen candidate reconstruction for GAP-NET-OVERNIGHT-20260813-V1
-- Candidate: 28435b84e236643912497a40cc8c8f16
-- Do not alter bins, source set, lookback, weighting, activation, ranking, sizing, costs or chronology.

create schema if not exists research;

create or replace function research.blankcanvas_gap_network_candidate_events_v1(
  p_score_start date,
  p_score_end date
) returns table(
  signal_date date,
  exit_date date,
  top_symbol text,
  bottom_symbol text,
  top_forecast double precision,
  bottom_forecast double precision,
  top_return_pct double precision,
  bottom_return_pct double precision,
  gross_return_pct double precision,
  net5_pct double precision,
  net10_pct double precision,
  net15_pct double precision,
  net20_pct double precision,
  selected_leg_max_weight_share double precision
)
language sql
stable
security invoker
set search_path=research,public,pg_temp
set work_mem='128MB'
set max_parallel_workers_per_gather='0'
as $function$
with g as materialized (
  select symbol,signal_date,next_overnight_pct,
         case when val < -1.0 then 'G_LT_M1'
              when val < -0.5 then 'G_M1_M0_5'
              when val < 0.0 then 'G_M0_5_0'
              when val < 0.5 then 'G_0_0_5'
              when val < 1.0 then 'G_0_5_1'
              else 'G_GE_1' end as gap_state
  from public.blankcanvas_cross_sectional_states_v1
  where feature='gap'
    and signal_date between date '2016-01-01' and p_score_end
    and next_overnight_pct is not null
), pairs as materialized (
  select s.symbol as source_symbol,t.symbol as target_symbol,s.signal_date,
         s.gap_state,t.next_overnight_pct as target_overnight_pct
  from g s
  join g t on t.signal_date=s.signal_date
  where s.symbol in ('DIA','HYG','QQQ','SPY')
), rolled as materialized (
  select p.*,
         count(target_overnight_pct) over w40::integer as n40,
         avg(target_overnight_pct) over w40 as mean40,
         stddev_samp(target_overnight_pct) over w40 as sd40
  from pairs p
  window w40 as (
    partition by source_symbol,target_symbol,gap_state
    order by signal_date
    rows between 40 preceding and 1 preceding
  )
), eligible as materialized (
  select *,1.0/(power(sd40,2)+0.0625) as precision_weight
  from rolled
  where signal_date between p_score_start and p_score_end
    and n40=40 and mean40 is not null and sd40 is not null
), forecasts as materialized (
  select signal_date,target_symbol,count(*)::smallint as eligible_experts,
         sum(mean40*precision_weight)/nullif(sum(precision_weight),0) as forecast_score,
         max(target_overnight_pct) as target_overnight_pct,
         max(precision_weight)/nullif(sum(precision_weight),0) as max_precision_weight_share
  from eligible
  group by signal_date,target_symbol
  having count(*)>=3
), ranked as materialized (
  select f.*,
         row_number() over(
           partition by signal_date order by forecast_score desc,target_symbol
         ) as rn_desc,
         row_number() over(
           partition by signal_date order by forecast_score,target_symbol
         ) as rn_asc,
         count(*) over(partition by signal_date) as target_count,
         min(forecast_score) over(partition by signal_date) as min_forecast,
         max(forecast_score) over(partition by signal_date) as max_forecast
  from forecasts f
), books as materialized (
  select signal_date,
         max(target_symbol) filter(where rn_desc=1) as top_symbol,
         max(target_symbol) filter(where rn_asc=1) as bottom_symbol,
         max(forecast_score) filter(where rn_desc=1) as top_forecast,
         max(forecast_score) filter(where rn_asc=1) as bottom_forecast,
         max(target_overnight_pct) filter(where rn_desc=1) as top_return_pct,
         max(target_overnight_pct) filter(where rn_asc=1) as bottom_return_pct,
         greatest(
           max(max_precision_weight_share) filter(where rn_desc=1),
           max(max_precision_weight_share) filter(where rn_asc=1)
         ) as selected_leg_max_weight_share,
         min(min_forecast) as min_forecast,
         max(max_forecast) as max_forecast,
         max(target_count) as target_count
  from ranked
  group by signal_date
)
select b.signal_date,a.next_trade_date as exit_date,b.top_symbol,b.bottom_symbol,
       b.top_forecast,b.bottom_forecast,b.top_return_pct,b.bottom_return_pct,
       0.5*b.bottom_return_pct-0.5*b.top_return_pct as gross_return_pct,
       0.5*b.bottom_return_pct-0.5*b.top_return_pct-0.05 as net5_pct,
       0.5*b.bottom_return_pct-0.5*b.top_return_pct-0.10 as net10_pct,
       0.5*b.bottom_return_pct-0.5*b.top_return_pct-0.15 as net15_pct,
       0.5*b.bottom_return_pct-0.5*b.top_return_pct-0.20 as net20_pct,
       b.selected_leg_max_weight_share
from books b
left join public.blankcanvas_adjusted_daily_features_v1 a
  on a.symbol='SPY' and a.signal_date=b.signal_date
where b.target_count=7 and b.min_forecast<0 and b.max_forecast>0
order by b.signal_date;
$function$;

comment on function research.blankcanvas_gap_network_candidate_events_v1(date,date) is
'Frozen causal reconstruction of GAP-NET-OVERNIGHT-20260813-V1 candidate 28435b84e236643912497a40cc8c8f16: RISK4 gap-state experts, 40 prior occurrences, precision weighting, all seven targets, K1 reverse span-zero, MOC to next MOO, returns reported at 5/10/15/20bp portfolio friction.';
