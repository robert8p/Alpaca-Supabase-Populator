(() => {
  const fmtScore = (value, digits = 2) => value == null ? 'unknown' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
  const moneyScore = (value) => value == null ? 'unknown' : Number(value).toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });

  function pointInTimeNews(c) {
    const source = Array.isArray(c.evidence_news) ? c.evidence_news : (Array.isArray(c.headlines) ? c.headlines : []);
    return source.map((article, index) => {
      const parts = [`${index + 1}. ${article.headline || 'Untitled'}`];
      if (article.source) parts.push(`Source: ${article.source}`);
      if (article.created_at || article.published_at) parts.push(`Published: ${article.created_at || article.published_at}`);
      if (article.summary) parts.push(`Summary: ${article.summary}`);
      if (article.url) parts.push(`URL: ${article.url}`);
      return parts.join('\n   ');
    }).join('\n\n') || 'No company-specific news was retained in the point-in-time Evidence Snapshot.';
  }

  function buildOptimizedChatGPTPrompt(c) {
    const flags = (c.risk_flags || []).length ? c.risk_flags.join(', ') : 'none flagged';
    const commentary = c.review_notes ? `\n- Reviewer commentary (human hypothesis only, not ground truth): ${c.review_notes}` : '';
    const evidenceCutoff = c.evidence_cutoff || c.signal_timestamp || c.created_at || 'unknown';
    const legacy = c.model_run_id == null;
    const evidence = pointInTimeNews(c);
    const componentLine = legacy
      ? `- This is a legacy row with no valid v2 model run. Legacy heuristic score: ${c.heuristic_score ?? 'unknown'}. Do not manufacture missing historic features.`
      : `- App Reversion Score: ${fmtScore(c.reversion_score,1)}/100 (UNCALIBRATED ranking score, not a probability)\n- Setup: ${fmtScore(c.setup_score,1)}\n- Catalyst: ${fmtScore(c.catalyst_score,1)}\n- Fundamental Resilience: ${fmtScore(c.resilience_score,1)}\n- Confirmation: ${fmtScore(c.confirmation_score,1)}\n- Damage Risk: ${fmtScore(c.damage_risk,1)}\n- Evidence Confidence: ${fmtScore(c.evidence_confidence,1)}\n- App verdict: ${c.model_verdict || 'unknown'}\n- Model/config: ${c.scoring_model_version || 'unknown'} / ${c.scoring_config_version || 'unknown'}`;

    return `Audit ${c.name || c.symbol} (${c.symbol}) as the ORIGINAL Oversold Reversion signal. Your job is to assess whether the app's point-in-time score is defensible and identify component-level disagreements. Do not overwrite the app model and do not treat your answer as ground truth.

STRATEGY TARGET
The eventual ground-truth outcome is whether the stock trades at least +5% above the stored signal price within six weeks.

STRICT POINT-IN-TIME RULE
Evidence cutoff: ${evidenceCutoff}
Signal timestamp: ${c.signal_timestamp || evidenceCutoff}
Signal price: ${c.signal_price == null ? moneyScore(c.last_price) : moneyScore(c.signal_price)}

Use ONLY information that was available on or before the evidence cutoff above when judging whether the ORIGINAL signal was sound. Do NOT use later news, later price action, later analyst revisions, later filings, or knowledge of what ultimately happened. If you know later information, explicitly ignore it. You may reason from the evidence provided below; do not browse for evidence published after the cutoff.

APP / SCANNER CONTEXT
- Move versus previous close: ${fmtScore(c.drop_pct,2)}%
- Last/signal-area price: ${moneyScore(c.last_price)}
- Previous close: ${moneyScore(c.prev_close)}
- Spread: ${c.spread_pct == null ? 'unknown' : fmtScore(c.spread_pct,2)+'%'}
- Scanner catalyst class: ${c.catalyst_class || 'U'}
- Risk flags: ${flags}
- Scanner summary: ${c.catalyst_summary || 'none'}${commentary}
${componentLine}

POINT-IN-TIME NEWS / EVIDENCE RETAINED BY THE APP
${evidence}

CANONICAL APP SCORING CONTRACT
The app's deterministic score uses:
Core = 0.25×Setup + 0.35×Catalyst + 0.15×Fundamental Resilience + 0.25×Confirmation.
Confidence is reliability, not attractiveness: ConfidenceAdjusted = 50 + ((Core - 50) × EvidenceConfidence / 100).
Damage penalty = min(15, max(0, DamageRisk - 25) × 0.20).
Damage caps: 0–29→100; 30–49→85; 50–69→65; 70–84→40; 85–100→20.
If the principal cause cannot be verified, Catalyst is capped at 35, final score at 60, and verdict at WATCH.
Verified existential/solvency/core-thesis failure can hard-veto to PASS.
Analyst consensus is supporting evidence only. Post-event analyst reaction may inform Catalyst evidence, but ratings are not a standalone scoring component.

COMPONENT DEFINITIONS
- Setup: deterministic market dislocation/tradability, not 'bigger fall = better'.
- Catalyst: likelihood the cause is temporary, misunderstood, survivable, or over-discounted within six weeks.
- Fundamental Resilience: capacity to absorb the event without destroying equity value.
- Confirmation: point-in-time evidence selling pressure is stabilising/reversing.
- Damage Risk: probability/severity of permanent structural impairment; asymmetric gate.
- Evidence Confidence: completeness and reliability of the evidence.

AUDIT TASK
1. State the verified primary cause using only cutoff-valid evidence, or say UNVERIFIED.
2. For each of Setup, Catalyst, Resilience, Confirmation, Damage and Confidence, say AGREE / TOO HIGH / TOO LOW / INSUFFICIENT EVIDENCE and explain briefly.
3. Pay special attention to whether missing information is being mistaken for favourable evidence.
4. For analyst material, distinguish cutoff-valid post-event changes from stale pre-event consensus; if no reliable analyst evidence is in the snapshot, say unavailable.
5. Identify the strongest point-in-time evidence FOR the reversion thesis and AGAINST it.
6. State whether the app's INVESTIGATE / WATCH / PASS conclusion is defensible under the canonical rules.
7. Name the single most important evidence item that would have improved the original assessment, but do not use information published after the cutoff.

OUTPUT
Return a concise markdown component-audit table followed by: App-score assessment, strongest for/against evidence, and key missing evidence. Keep facts separate from inference. This is research, not an instruction to trade.`;
  }

  window.buildChatGPTPrompt = buildOptimizedChatGPTPrompt;

  function relabelRowButtons() {
    document.querySelectorAll('#rows .chatgpt-button').forEach((button) => {
      button.textContent = 'Audit ↗';
      button.title = 'Open ChatGPT to audit this point-in-time Evidence Snapshot against the same scoring contract';
      const helper = button.parentElement && button.parentElement.querySelector('.muted');
      if (helper) helper.textContent = 'same cutoff';
    });
  }

  relabelRowButtons();
  const rows = document.getElementById('rows');
  if (rows) new MutationObserver(relabelRowButtons).observe(rows, { childList: true, subtree: true });
})();
