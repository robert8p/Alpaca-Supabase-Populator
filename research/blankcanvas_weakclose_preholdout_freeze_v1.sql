-- Campaign: WEAKCLOSE-COMPOSITE-20260813-V1
-- Run only after the deterministic bootstrap results from
-- research/blankcanvas_weakclose_bootstrap_v1.py have been written to
-- research.blankcanvas_weakclose_validation_gate_v1.
-- This script does not read November or December outcomes.

create schema if not exists research;

create table if not exists research.blankcanvas_weakclose_preholdout_freeze_v1 (
  campaign_id text not null,
  candidate_id text not null,
  construction text not null,
  top_n smallint not null,
  target text not null,
  signal_features text[] not null,
  primary_cost_bps double precision not null,
  stress_cost_bps double precision not null,
  ancestry_registered_definitions integer not null,
  inner_avg_net10 double precision not null,
  inner_median_net10 double precision not null,
  inner_win_rate10 double precision not null,
  inner_profit_factor10 double precision not null,
  inner_avg_net20 double precision not null,
  outer_avg_net10 double precision not null,
  outer_median_net10 double precision not null,
  outer_win_rate10 double precision not null,
  outer_profit_factor10 double precision not null,
  outer_avg_net20 double precision not null,
  combined_avg_net10 double precision not null,
  combined_median_net10 double precision not null,
  combined_win_rate10 double precision not null,
  combined_profit_factor10 double precision not null,
  combined_t_stat10 double precision not null,
  combined_avg_net20 double precision not null,
  bootstrap_ci_low double precision not null,
  bootstrap_ci_high double precision not null,
  bootstrap_p_value double precision not null,
  bh_q_value double precision not null,
  preregistration_commit text not null,
  inference_commit text not null,
  calculation_commit text not null,
  bootstrap_code_commit text not null,
  freeze_code_commit text,
  frozen_at timestamptz not null default now(),
  primary key(campaign_id,candidate_id)
);

begin;

delete from research.blankcanvas_weakclose_preholdout_freeze_v1
where campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1';

with eligible as materialized (
  select d.*,
         i.avg_net10 as inner_avg_net10,i.median_net10 as inner_median_net10,
         i.win_rate10 as inner_win_rate10,i.profit_factor10 as inner_profit_factor10,
         i.avg_net20 as inner_avg_net20,
         o.avg_net10 as outer_avg_net10,o.median_net10 as outer_median_net10,
         o.win_rate10 as outer_win_rate10,o.profit_factor10 as outer_profit_factor10,
         o.avg_net20 as outer_avg_net20,
         c.avg_net10 as combined_avg_net10,c.median_net10 as combined_median_net10,
         c.win_rate10 as combined_win_rate10,c.profit_factor10 as combined_profit_factor10,
         c.t_stat10 as combined_t_stat10,c.avg_net20 as combined_avg_net20,
         g.bootstrap_ci_low,g.bootstrap_ci_high,g.bootstrap_p_value,g.bh_q_value,
         row_number() over(
           partition by d.construction
           order by least(i.avg_net20,o.avg_net20) desc,c.median_net10 desc,d.top_n
         ) as construction_rank
  from research.blankcanvas_weakclose_definition_freeze_v1 d
  join research.blankcanvas_weakclose_metrics_v1 i
    on i.campaign_id=d.campaign_id and i.candidate_id=d.candidate_id
   and i.metric_scope='INNER_VALIDATION'
  join research.blankcanvas_weakclose_metrics_v1 o
    on o.campaign_id=d.campaign_id and o.candidate_id=d.candidate_id
   and o.metric_scope='OUTER_PREHOLDOUT'
  join research.blankcanvas_weakclose_metrics_v1 c
    on c.campaign_id=d.campaign_id and c.candidate_id=d.candidate_id
   and c.metric_scope='COMBINED_VALIDATION'
  join research.blankcanvas_weakclose_validation_gate_v1 g
    on g.campaign_id=d.campaign_id and g.candidate_id=d.candidate_id
  where d.campaign_id='WEAKCLOSE-COMPOSITE-20260813-V1'
    and g.final_preholdout_pass
), chosen as materialized (
  select * from eligible
  where construction_rank=1
  order by case construction when 'SHORT_WEAK' then 1 else 2 end
  limit 2
)
insert into research.blankcanvas_weakclose_preholdout_freeze_v1(
  campaign_id,candidate_id,construction,top_n,target,signal_features,
  primary_cost_bps,stress_cost_bps,ancestry_registered_definitions,
  inner_avg_net10,inner_median_net10,inner_win_rate10,inner_profit_factor10,inner_avg_net20,
  outer_avg_net10,outer_median_net10,outer_win_rate10,outer_profit_factor10,outer_avg_net20,
  combined_avg_net10,combined_median_net10,combined_win_rate10,combined_profit_factor10,
  combined_t_stat10,combined_avg_net20,bootstrap_ci_low,bootstrap_ci_high,bootstrap_p_value,bh_q_value,
  preregistration_commit,inference_commit,calculation_commit,bootstrap_code_commit,freeze_code_commit
)
select campaign_id,candidate_id,construction,top_n,target,signal_features,
       primary_cost_bps,stress_cost_bps,ancestry_registered_definitions,
       inner_avg_net10,inner_median_net10,inner_win_rate10,inner_profit_factor10,inner_avg_net20,
       outer_avg_net10,outer_median_net10,outer_win_rate10,outer_profit_factor10,outer_avg_net20,
       combined_avg_net10,combined_median_net10,combined_win_rate10,combined_profit_factor10,
       combined_t_stat10,combined_avg_net20,bootstrap_ci_low,bootstrap_ci_high,bootstrap_p_value,bh_q_value,
       preregistration_commit,inference_commit,calculation_commit,
       '2736fe38e364798cd0bf6320947e7d4439dfb5d8',null
from chosen;

commit;
