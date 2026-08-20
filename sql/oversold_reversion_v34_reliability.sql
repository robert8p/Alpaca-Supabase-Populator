-- Oversold Reversion v3.4 reliability and regulator evidence.

alter table public.or_primary_evidence
  drop constraint if exists or_primary_evidence_source_kind_check;

alter table public.or_primary_evidence
  add constraint or_primary_evidence_source_kind_check check (
    source_kind in (
      'sec_filing',
      'clinical_trial_registry',
      'clinical_trial_sponsor_match',
      'fda_regulatory_record',
      'fda_drug_enforcement',
      'fda_device_enforcement'
    )
  );

create index if not exists idx_or_primary_evidence_external_id
  on public.or_primary_evidence(source_kind,external_id,available_at desc);
