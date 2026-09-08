(() => {
  "use strict";

  const SETTINGS_KEY = "oversoldReversionGuard.settings.v1";
  const POSITIONS_KEY = "oversoldReversionGuard.positions.v1";
  const state = {
    payload: null,
    settings: null,
    positions: [],
    positionReviews: [],
    loading: false,
    refreshTimer: null,
  };

  const $ = (id) => document.getElementById(id);
  const els = {
    accountValue: $("accountValue"),
    riskBudget: $("riskBudget"),
    maxPosition: $("maxPosition"),
    usdPerGbp: $("usdPerGbp"),
    maxTheme: $("maxTheme"),
    maxOpenRisk: $("maxOpenRisk"),
    minDrop: $("minDrop"),
    candidateLimit: $("candidateLimit"),
    runScan: $("runScan"),
    refresh: $("refresh"),
    analyseTop: $("analyseTop"),
    policyButton: $("policyButton"),
    sourceStatus: $("sourceStatus"),
    statusBanner: $("statusBanner"),
    metricInvestigate: $("metricInvestigate"),
    metricWait: $("metricWait"),
    metricPass: $("metricPass"),
    metricReject: $("metricReject"),
    metricScan: $("metricScan"),
    metricCutoff: $("metricCutoff"),
    emptyState: $("emptyState"),
    tableWrap: $("tableWrap"),
    candidateRows: $("candidateRows"),
    positionForm: $("positionForm"),
    positionSymbol: $("positionSymbol"),
    positionEntry: $("positionEntry"),
    positionCurrent: $("positionCurrent"),
    positionQuantity: $("positionQuantity"),
    positionTime: $("positionTime"),
    positionTheme: $("positionTheme"),
    positionResults: $("positionResults"),
    portfolioWarnings: $("portfolioWarnings"),
    clearPositions: $("clearPositions"),
    policyDialog: $("policyDialog"),
    closePolicy: $("closePolicy"),
    policyContent: $("policyContent"),
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function safeUrl(value) {
    try {
      const url = new URL(String(value));
      return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
    } catch {
      return "#";
    }
  }

  function number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function formatMoney(value, currency = "USD", digits = 2) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return "—";
    return new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency,
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(parsed);
  }

  function formatCompact(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return "—";
    return new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 1 }).format(parsed);
  }

  function formatPct(value, digits = 1, signed = false) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return "—";
    const sign = signed && parsed > 0 ? "+" : "";
    return `${sign}${parsed.toFixed(digits)}%`;
  }

  function formatDateTime(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    }).format(date);
  }

  function actionClass(action) {
    return String(action || "wait").toLowerCase();
  }

  function status(message, kind = "info", persistent = false) {
    els.statusBanner.hidden = !message;
    els.statusBanner.className = `status-banner ${kind === "error" ? "is-error" : kind === "success" ? "is-success" : ""}`;
    els.statusBanner.textContent = message || "";
    if (message && !persistent) {
      window.setTimeout(() => {
        if (els.statusBanner.textContent === message) els.statusBanner.hidden = true;
      }, 7000);
    }
  }

  function setLoading(loading, message = "") {
    state.loading = loading;
    els.runScan.disabled = loading;
    els.refresh.disabled = loading;
    if (loading) {
      els.sourceStatus.className = "source-status";
      els.sourceStatus.textContent = message || "Loading…";
    }
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = { detail: await response.text() };
    }
    if (!response.ok) {
      const detail = payload?.detail;
      const message = typeof detail === "string" ? detail : JSON.stringify(detail || payload);
      throw new Error(message || `Request failed (${response.status})`);
    }
    return payload;
  }

  function defaultSettings() {
    return {
      account_value_gbp: 10000,
      risk_budget_gbp: 50,
      max_position_gbp: 500,
      usd_per_gbp: 1.30,
      max_theme_positions: 3,
      max_open_risk_pct: 2.0,
    };
  }

  function loadSettings() {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}"); } catch { saved = {}; }
    state.settings = { ...defaultSettings(), ...saved };
    els.accountValue.value = state.settings.account_value_gbp;
    els.riskBudget.value = state.settings.risk_budget_gbp;
    els.maxPosition.value = state.settings.max_position_gbp;
    els.usdPerGbp.value = state.settings.usd_per_gbp;
    els.maxTheme.value = state.settings.max_theme_positions;
    els.maxOpenRisk.value = state.settings.max_open_risk_pct;
  }

  function readSettings() {
    const settings = {
      account_value_gbp: Math.max(1, number(els.accountValue.value, 10000)),
      risk_budget_gbp: Math.max(1, number(els.riskBudget.value, 50)),
      max_position_gbp: Math.max(1, number(els.maxPosition.value, 500)),
      usd_per_gbp: Math.max(.1, number(els.usdPerGbp.value, 1.30)),
      max_theme_positions: Math.max(1, Math.round(number(els.maxTheme.value, 3))),
      max_open_risk_pct: Math.max(.1, number(els.maxOpenRisk.value, 2)),
    };
    state.settings = settings;
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    return settings;
  }

  function settingsQuery(force = false) {
    const settings = readSettings();
    const params = new URLSearchParams({
      account_value_gbp: settings.account_value_gbp,
      risk_budget_gbp: settings.risk_budget_gbp,
      max_position_gbp: settings.max_position_gbp,
      usd_per_gbp: settings.usd_per_gbp,
      max_theme_positions: settings.max_theme_positions,
      max_open_risk_pct: settings.max_open_risk_pct,
      force: force ? "true" : "false",
    });
    return params.toString();
  }

  function loadPositions() {
    try {
      const stored = JSON.parse(localStorage.getItem(POSITIONS_KEY) || "[]");
      state.positions = Array.isArray(stored) ? stored.slice(0, 100) : [];
    } catch {
      state.positions = [];
    }
  }

  function savePositions() {
    localStorage.setItem(POSITIONS_KEY, JSON.stringify(state.positions));
  }

  function renderMetrics(payload) {
    const counts = payload?.portfolio?.candidate_counts || {};
    els.metricInvestigate.textContent = counts.investigate ?? 0;
    els.metricWait.textContent = counts.wait ?? 0;
    els.metricPass.textContent = counts.pass ?? 0;
    els.metricReject.textContent = counts.reject ?? 0;
    const scan = payload?.scan || {};
    els.metricScan.textContent = scan.status ? String(scan.status).toUpperCase() : "None";
    els.metricCutoff.textContent = formatDateTime(scan?.metadata?.evidence_cutoff || payload?.candidates?.[0]?.evidence_cutoff || scan.completed_at || scan.started_at);
  }

  function renderNews(candidate) {
    const news = Array.isArray(candidate.headlines) ? candidate.headlines.slice(0, 4) : [];
    if (!news.length) return '<p class="micro">No retained company-specific headline at the cutoff.</p>';
    return `<ul class="news-list">${news.map((article) => {
      const headline = escapeHtml(article?.headline || "Untitled item");
      const url = safeUrl(article?.url);
      return `<li>${url === "#" ? headline : `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${headline}</a>`}</li>`;
    }).join("")}</ul>`;
  }

  function renderCandidateRow(candidate) {
    const guard = candidate.guard_assessment || {};
    const event = guard.event || {};
    const confirmation = guard.confirmation || {};
    const execution = guard.execution || {};
    const plan = guard.risk_plan || {};
    const action = guard.recommended_action || "WAIT";
    const actionCss = actionClass(action);
    const score = number(guard.guard_score);
    const upstream = number(guard.upstream_opportunity_score);
    const decision = String(candidate.decision || "unreviewed").toLowerCase();
    const notes = candidate.review_notes || "";
    const gates = Array.isArray(guard.gates) ? guard.gates : [];
    const reasons = Array.isArray(guard.reasons) ? guard.reasons : [];
    const matched = Array.isArray(event.matched_terms) ? event.matched_terms : [];
    const session = guard.session || {};
    const evidence = guard.evidence || {};
    const marketEvidence = execution.evidence || {};
    const scoreText = (value) => value === null || value === undefined ? "—" : `${number(value).toFixed(0)}/100`;

    const shareText = plan.recommended_shares_now > 0
      ? `<span class="risk-ready">Sizing preview: ${escapeHtml(plan.recommended_shares_now)} shares</span>`
      : `<span class="risk-zero">0 shares now</span><div class="micro">Preview after confirmation: ${escapeHtml(plan.preview_shares_after_confirmation ?? 0)}</div>`;

    const detailItems = [...reasons, ...gates.filter((gate) => !gate.passed).map((gate) => `Failed gate: ${gate.name} — ${gate.detail}`)];
    const confirmationLabel = String(confirmation.status || "unknown").replaceAll("_", " ");
    const confirmationClass = String(confirmation.status || "not_confirmed").replaceAll("_", "-");

    return `
      <tr class="action-${actionCss}" data-candidate-id="${escapeHtml(candidate.id)}">
        <td data-label="Rank / stock">
          <div class="symbol-line"><span class="rank">#${escapeHtml(candidate.rank ?? "—")}</span><span class="symbol">${escapeHtml(candidate.symbol)}</span></div>
          <div class="company">${escapeHtml(candidate.name || "")}</div>
          <div class="theme">${escapeHtml(guard.theme || "Other / unknown")}</div>
        </td>
        <td data-label="Move">
          <div class="move">${formatPct(candidate.drop_pct, 1, true)}</div>
          <div class="price">${formatMoney(candidate.last_price)}</div>
          <div class="micro">Spread ${formatPct(candidate.spread_pct, 2)}<br>Prev. value ${formatCompact(candidate.prev_dollar_volume)}</div>
        </td>
        <td data-label="Catalyst gate">
          <div class="event-label">${escapeHtml(event.label || "Unknown catalyst")}</div>
          <span class="gate-pill gate-pill--${actionCss}">${escapeHtml(guard.gate_label || action)}</span>
          <div class="micro">Research: ${escapeHtml(guard.research_action || "WATCH")}</div>
          <div class="micro">${escapeHtml(session.label || "unknown")} signal · ${escapeHtml(matched.join(", ") || candidate.catalyst_summary || "No verified cause")}</div>
          <details><summary>Why this gate?</summary><ul class="details-list">${detailItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></details>
        </td>
        <td data-label="Guard score">
          <div class="score-block">
            <div class="score-number">${score.toFixed(1)}<small>/100</small></div>
            <div class="score-bar"><i style="width:${Math.max(0, Math.min(100, score))}%"></i></div>
            <div class="upstream-score">Upstream ${upstream.toFixed(1)} · ${escapeHtml(candidate.model_verdict || "unrated")}</div>
            <div class="micro">Uncalibrated heuristic<br>Profit probability unavailable</div>
          </div>
        </td>
        <td data-label="Confirmation">
          <div class="confirmation-status ${escapeHtml(confirmationClass)}">${escapeHtml(confirmationLabel)}</div>
          <div class="micro">${scoreText(confirmation.score)}<br>${escapeHtml(session.is_regular && session.after_1000_et ? "Signal after 10:00 ET" : "Wait until 10:00 ET+")}<br>${escapeHtml(confirmation.higher_low_evidence?.status?.replaceAll("_", " ") || "Pattern evidence unavailable")}</div>
          <details><summary>Checks</summary><ul class="details-list">${(confirmation.checks || []).map((check) => `<li>${check.passed === true ? "✓" : check.passed === false ? "✕" : "—"} ${escapeHtml(check.label)}</li>`).join("")}</ul></details>
        </td>
        <td data-label="Risk plan">
          <div class="risk-plan">${shareText}</div>
          <div class="micro">${plan.historical_only ? "Historical planning only<br>" : ""}Ref. ${formatMoney(plan.reference_price_usd)}<br>Provisional stop ${formatMoney(plan.provisional_stop_usd)} (${formatPct(plan.risk_distance_pct, 1)})<br>Illustrative +1R ${formatMoney(plan.one_r_target_usd)}<br>Net risk/reward unestimated</div>
          <details><summary>Entry and exit assumptions</summary><ul class="details-list"><li>${escapeHtml(plan.entry_trigger || "Higher low + reclaim")}</li><li>${escapeHtml(plan.time_stop || "Two-session time stop")}</li><li>${escapeHtml(plan.sizing_rule || "Risk-based sizing")}</li><li>${escapeHtml(plan.target_basis || "Targets are illustrative")}</li><li>${escapeHtml(plan.gap_risk_note || "Stops can slip")}</li></ul></details>
        </td>
        <td data-label="Evidence">
          <div class="evidence-grid"><span>Evidence score</span><strong>${scoreText(candidate.evidence_confidence)}</strong><span>Damage score</span><strong>${scoreText(candidate.damage_risk)}</strong><span>Execution score</span><strong>${scoreText(execution.score)}</strong><span>Eligible sources</span><strong>${escapeHtml(evidence.eligible_source_count ?? 0)}</strong></div>
          <div class="micro">Cause ${evidence.cause_verified ? "supported" : "unverified"}<br>${escapeHtml(marketEvidence.status?.replaceAll("_", " ") || "Market data unavailable")}${marketEvidence.quote_age_seconds == null ? "" : `<br>Quote age ${escapeHtml(Math.round(marketEvidence.quote_age_seconds))}s`}</div>
          <details><summary>Recorded news</summary>${renderNews(candidate)}</details>
        </td>
        <td data-label="Review" class="review-cell">
          <button class="button button--chatgpt chat-button" type="button" data-action="chatgpt">Challenge in ChatGPT</button>
          <div class="review-actions">
            ${["investigate", "watch", "pass", "reject"].map((value) => `<button type="button" class="decision ${decision === value ? "is-selected" : ""}" data-decision="${value}">${value[0].toUpperCase() + value.slice(1)}</button>`).join("")}
          </div>
          <textarea class="review-notes" maxlength="4000" placeholder="Commentary, invalidation, thesis…">${escapeHtml(notes)}</textarea>
          <button class="button button--quiet review-save" type="button" data-action="save-review">Save review</button>
          <div class="save-state" aria-live="polite"></div>
        </td>
      </tr>`;
  }

  function renderCandidates(payload) {
    const candidates = Array.isArray(payload?.candidates) ? payload.candidates : [];
    els.candidateRows.innerHTML = candidates.map(renderCandidateRow).join("");
    els.emptyState.hidden = candidates.length > 0;
    els.tableWrap.hidden = candidates.length === 0;
    els.analyseTop.disabled = candidates.length === 0;
    if (!candidates.length) {
      els.emptyState.innerHTML = '<h3>No candidates in the latest scan</h3><p>Run a fresh scan or lower the minimum decline threshold.</p>';
    }
  }

  function renderPayload(payload) {
    state.payload = payload;
    renderMetrics(payload);
    renderCandidates(payload);
    const generated = payload?.guard?.generated_at;
    els.sourceStatus.className = "source-status is-ok";
    els.sourceStatus.textContent = `Scanner connected · assessed ${formatDateTime(generated)}`;
  }

  async function loadLatest(force = false) {
    if (state.loading) return;
    setLoading(true, force ? "Refreshing from scanner…" : "Loading latest scan…");
    try {
      const payload = await fetchJson(`/api/reversion-guard/latest?${settingsQuery(force)}`);
      renderPayload(payload);
      await reviewSavedPositions();
    } catch (error) {
      els.sourceStatus.className = "source-status is-error";
      els.sourceStatus.textContent = "Scanner unavailable";
      els.emptyState.hidden = false;
      els.tableWrap.hidden = true;
      els.emptyState.innerHTML = `<h3>Could not load the scanner</h3><p>${escapeHtml(error.message)}</p>`;
      status(`Could not load the latest scan: ${error.message}`, "error", true);
    } finally {
      setLoading(false);
    }
  }

  async function pollScan(scanId, attempt = 0) {
    if (attempt > 80) {
      status("The scan is still running. Use Refresh assessment in a moment.", "error", true);
      setLoading(false);
      return;
    }
    try {
      const payload = await fetchJson(`/api/reversion-guard/scans/${encodeURIComponent(scanId)}?${settingsQuery(true)}`);
      const scanStatus = String(payload?.scan?.status || "unknown");
      els.sourceStatus.textContent = `Fresh scan: ${scanStatus}`;
      if (scanStatus === "completed") {
        renderPayload(payload);
        await reviewSavedPositions();
        status(`Fresh scan completed with ${payload.candidates?.length || 0} assessed candidates.`, "success");
        setLoading(false);
        return;
      }
      if (scanStatus === "failed") {
        throw new Error(payload?.scan?.error || "Upstream scan failed");
      }
      window.setTimeout(() => pollScan(scanId, attempt + 1), 4000);
    } catch (error) {
      status(`Scan polling error: ${error.message}`, "error", true);
      setLoading(false);
    }
  }

  async function runFreshScan() {
    if (state.loading) return;
    setLoading(true, "Starting fresh scan…");
    status("Starting a fresh point-in-time scan. This can take several minutes on a cold Render service.", "info", true);
    try {
      const params = new URLSearchParams({
        min_drop_pct: Math.max(5, number(els.minDrop.value, 15)),
        candidate_limit: Math.max(1, Math.round(number(els.candidateLimit.value, 50))),
      });
      const result = await fetchJson(`/api/reversion-guard/run?${params}`, { method: "POST" });
      if (!result?.scan_id) throw new Error("The upstream scanner did not return a scan ID");
      status(`Scan ${result.scan_id} is running.`, "info", true);
      pollScan(result.scan_id);
    } catch (error) {
      status(`Could not start scan: ${error.message}`, "error", true);
      setLoading(false);
    }
  }

  function rowCandidate(row) {
    const id = Number(row?.dataset?.candidateId);
    return state.payload?.candidates?.find((candidate) => Number(candidate.id) === id) || null;
  }

  async function saveReview(row, decisionOverride = null) {
    const candidate = rowCandidate(row);
    if (!candidate) return;
    const notes = row.querySelector(".review-notes")?.value || "";
    const selected = decisionOverride || row.querySelector(".decision.is-selected")?.dataset?.decision || candidate.decision || "unreviewed";
    const saveState = row.querySelector(".save-state");
    if (saveState) saveState.textContent = "Saving…";
    try {
      const result = await fetchJson(`/api/reversion-guard/candidates/${candidate.id}`, {
        method: "PATCH",
        body: JSON.stringify({ decision: selected, review_notes: notes }),
      });
      candidate.decision = result.decision;
      candidate.review_notes = result.review_notes;
      row.querySelectorAll(".decision").forEach((button) => button.classList.toggle("is-selected", button.dataset.decision === result.decision));
      if (saveState) saveState.textContent = `Saved ${new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
    } catch (error) {
      if (saveState) saveState.textContent = `Save failed: ${error.message}`;
    }
  }

  function compactTopPacket(candidate) {
    const guard = candidate.guard_assessment || {};
    return {
      symbol: candidate.symbol,
      name: candidate.name,
      evidence_cutoff: candidate.evidence_cutoff,
      move_pct: candidate.drop_pct,
      price: candidate.last_price,
      event: guard.event?.label,
      event_bucket: guard.event?.bucket,
      guard_score: guard.guard_score,
      score_status: "UNCALIBRATED_HEURISTIC",
      profit_probability: null,
      evidence_integrity: guard.evidence,
      execution_evidence: guard.execution?.evidence,
      gate: guard.gate_label,
      confirmation: guard.confirmation?.status,
      upstream_score: guard.upstream_opportunity_score,
      upstream_verdict: candidate.model_verdict,
      damage_risk: candidate.damage_risk,
      evidence_confidence: candidate.evidence_confidence,
      catalyst_summary: candidate.catalyst_summary,
      latest_headlines: (candidate.headlines || []).slice(0, 3).map((item) => ({ headline: item.headline, source: item.source, created_at: item.created_at, url: item.url })),
      risk_plan: {
        stop: guard.risk_plan?.provisional_stop_usd,
        risk_pct: guard.risk_plan?.risk_distance_pct,
        one_r: guard.risk_plan?.one_r_target_usd,
        time_stop: guard.risk_plan?.time_stop,
      },
    };
  }

  function candidatePrompt(packet) {
    return `Audit this Oversold Reversion candidate as its ORIGINAL signal. Respect the evidence cutoff and do not use later price action or hindsight.

Your task is to decide whether the fall was a genuinely mispriced, survivable and short-horizon overreaction, or a justified repricing. Independently challenge the app rather than agreeing with it.

Required method:
1. Identify the verified causal event. Separate facts from inference and generic movers coverage.
2. Classify it as temporary operational, guidance/earnings-quality reset, financing/dilution, regulatory/compliance, structural damage, parabolic unwind, analyst/sentiment, or unknown.
3. Assess economic severity, survivability, cash conversion, dilution, customer concentration, legal/compliance tail risk and whether fair value has changed.
4. Explain whether a reversion within two to three regular sessions is plausible.
5. Enforce entry timing: no extended-hours entry; require a higher low plus VWAP or intraday-pivot reclaim after 10:00 ET.
6. Challenge the provisional stop, saved risk sizing, illustrative +1R/+4–6% planning levels and two-session time stop. These levels do not establish achievable returns or favourable net risk/reward.
7. State a decisive action: REJECT, WAIT, INVESTIGATE, HOLD, TRIM, EXIT or TAKE PROFIT.
8. Give the strongest bear case and the exact evidence that would falsify your conclusion.
9. Prefer primary filings/company releases and reputable reporting that existed by the cutoff. Cite sources. Exclude sources flagged by the evidence-integrity checks until independently resolved.
10. Treat guard/upstream scores as uncalibrated heuristics; profit probability and expected net return are unknown.

Evidence packet:
${JSON.stringify(packet, null, 2)}`;
  }

  async function openChatGptWithPrompt(prompt, popup = null) {
    try { await navigator.clipboard.writeText(prompt); } catch { /* Clipboard can be unavailable on non-secure contexts. */ }
    const url = `https://chatgpt.com/?q=${encodeURIComponent(prompt)}`;
    const target = popup || window.open("about:blank", "_blank");
    if (!target) {
      status("The browser blocked the ChatGPT window. The prompt has been copied to the clipboard.", "error");
      return;
    }
    if (url.length < 7800) target.location.href = url;
    else {
      target.location.href = "https://chatgpt.com/";
      status("The prompt was too large for a pre-filled URL, so it was copied to your clipboard and ChatGPT was opened.", "info");
    }
  }

  async function challengeCandidate(candidate) {
    const popup = window.open("about:blank", "_blank");
    try {
      const packet = await fetchJson(`/api/reversion-guard/candidates/${candidate.id}/packet`);
      await openChatGptWithPrompt(candidatePrompt(packet), popup);
    } catch (error) {
      if (popup) popup.close();
      status(`Could not build the ChatGPT packet: ${error.message}`, "error");
    }
  }

  async function analyseTopTen() {
    const candidates = (state.payload?.candidates || []).slice(0, 10);
    if (!candidates.length) return;
    const prompt = `Audit and rank these 10 Oversold Reversion candidates as ORIGINAL point-in-time signals. Do not use hindsight or later price action.

The app deliberately separates "oversold" from "mispriced". Independently verify the catalyst and challenge every app classification. Hard-penalise structural damage, dilution/convertibles/share issuance, reduced guidance, regulatory/export/compliance investigations, severe customer concentration and parabolic momentum unwinds. Missing or generic news is uncertainty, never bullish evidence.

For each candidate provide:
- verified cause and evidence quality;
- event classification;
- whether fair value changed;
- survivability and tail-risk assessment;
- whether a 2–3 session reversion is plausible;
- entry status: REJECT, WAIT or INVESTIGATE;
- required regular-session confirmation after 10:00 ET;
- proposed invalidation, risk/reward and time stop;
- strongest bear case.

Then rank the candidates from best to worst for a risk-controlled reversion trade. Do not rank by percentage decline. Cite primary or high-quality sources available by each evidence cutoff.

Packets:
${JSON.stringify(candidates.map(compactTopPacket), null, 2)}`;
    await openChatGptWithPrompt(prompt);
  }

  function positionPayload(position) {
    return {
      position: {
        symbol: position.symbol,
        entry_price_usd: position.entry_price_usd,
        current_price_usd: position.current_price_usd || null,
        quantity: position.quantity,
        entry_timestamp: position.entry_timestamp || null,
        theme: position.theme || null,
        planned_risk_gbp: position.planned_risk_gbp || null,
      },
      settings: readSettings(),
    };
  }

  async function reviewOnePosition(position) {
    return fetchJson("/api/reversion-guard/positions/review", {
      method: "POST",
      body: JSON.stringify(positionPayload(position)),
    });
  }

  function renderPositionCard(review) {
    const pnlClass = number(review.pnl_pct) >= 0 ? "gain" : "loss";
    return `<article class="position-card" data-position-symbol="${escapeHtml(review.symbol)}">
      <div class="position-card__symbol"><strong>${escapeHtml(review.symbol)}</strong><span>${escapeHtml(review.theme || review.event_label || "Other / unknown")}</span></div>
      <div class="position-stat"><span>${review.price_is_current === false ? "Value at stored price" : "Reference value"}</span><strong>${formatMoney(review.market_value_gbp, "GBP")}</strong></div>
      <div class="micro">${escapeHtml(review.price_source === "stored_scan" ? `Stored scan price as of ${review.price_as_of || "unknown"}` : "Using the price entered in this review")}</div>
      <div class="position-stat"><span>P/L</span><strong class="${pnlClass}">${formatPct(review.pnl_pct, 2, true)} · ${formatMoney(review.pnl_gbp, "GBP")}</strong></div>
      <div class="position-stat"><span>Recovery to break even</span><strong>${formatPct(review.recovery_to_break_even_pct, 2)}</strong></div>
      <div class="position-stat"><span>Provisional invalidation</span><strong>${formatMoney(review.provisional_invalidation_usd)}</strong></div>
      <div class="position-action"><strong>${escapeHtml(review.action_label)}</strong><p>${escapeHtml(review.sizing_guidance)} ${escapeHtml(review.time_stop)}</p></div>
      <button type="button" class="delete-position" aria-label="Delete ${escapeHtml(review.symbol)}">×</button>
    </article>`;
  }

  async function reviewSavedPositions() {
    if (!state.positions.length) {
      state.positionReviews = [];
      els.positionResults.innerHTML = '<div class="empty-state" style="min-height:110px"><p>No saved positions. Add one above to expose break-even anchoring and theme concentration.</p></div>';
      els.portfolioWarnings.hidden = true;
      return;
    }
    els.positionResults.innerHTML = '<div class="empty-state" style="min-height:110px"><div class="spinner"></div><p>Reviewing saved positions…</p></div>';
    try {
      const request = {
        positions: state.positions.map((position) => positionPayload(position).position),
        settings: readSettings(),
      };
      const result = await fetchJson("/api/reversion-guard/portfolio/review", {
        method: "POST",
        body: JSON.stringify(request),
      });
      state.positionReviews = (result.positions || []).filter((row) => !row.error);
      els.positionResults.innerHTML = result.positions.map((review) => review.error
        ? `<article class="position-card"><div class="position-card__symbol"><strong>${escapeHtml(review.symbol)}</strong></div><div class="position-action"><strong>Review error</strong><p>${escapeHtml(review.error)}</p></div><button type="button" class="delete-position" aria-label="Delete ${escapeHtml(review.symbol)}">×</button></article>`
        : renderPositionCard(review)).join("");
      renderPortfolioWarnings(result.summary || {});
    } catch (error) {
      els.positionResults.innerHTML = `<div class="empty-state" style="min-height:110px"><p>Could not review positions: ${escapeHtml(error.message)}</p></div>`;
    }
  }

  function renderPortfolioWarnings(summary) {
    const warnings = [];
    for (const item of summary.overexposed_themes || []) {
      warnings.push(`${item.theme}: ${item.count} positions exceeds the limit of ${item.limit}.`);
    }
    if (summary.open_risk_breach) warnings.push(`Planned open risk ${formatPct(summary.planned_open_risk_pct, 2)} exceeds the ${formatPct(summary.max_open_risk_pct, 2)} account limit.`);
    els.portfolioWarnings.hidden = false;
    if (warnings.length) {
      els.portfolioWarnings.className = "portfolio-warnings";
      els.portfolioWarnings.innerHTML = `<strong>Portfolio risk breach</strong><br>${warnings.map(escapeHtml).join("<br>")}`;
    } else {
      els.portfolioWarnings.className = "portfolio-warnings is-clear";
      els.portfolioWarnings.innerHTML = `<strong>No configured concentration breach detected.</strong> ${escapeHtml(summary.correlation_rule || "")}`;
    }
  }

  async function submitPosition(event) {
    event.preventDefault();
    const position = {
      symbol: els.positionSymbol.value.trim().toUpperCase(),
      entry_price_usd: number(els.positionEntry.value),
      current_price_usd: els.positionCurrent.value ? number(els.positionCurrent.value) : null,
      quantity: number(els.positionQuantity.value),
      entry_timestamp: els.positionTime.value || null,
      theme: els.positionTheme.value.trim() || null,
    };
    if (!position.symbol || position.entry_price_usd <= 0 || position.quantity <= 0) {
      status("Symbol, positive entry price and positive quantity are required.", "error");
      return;
    }
    try {
      await reviewOnePosition(position);
      const index = state.positions.findIndex((item) => item.symbol === position.symbol);
      if (index >= 0) state.positions[index] = position;
      else state.positions.push(position);
      savePositions();
      els.positionForm.reset();
      await reviewSavedPositions();
      status(`${position.symbol} saved and reviewed.`, "success");
    } catch (error) {
      status(`Position review failed: ${error.message}`, "error");
    }
  }

  async function showPolicy() {
    if (typeof els.policyDialog.showModal === "function") els.policyDialog.showModal();
    else els.policyDialog.setAttribute("open", "");
    els.policyContent.innerHTML = '<div class="spinner"></div>';
    try {
      const policy = await fetchJson("/api/reversion-guard/policy");
      els.policyContent.innerHTML = `
        <p>${escapeHtml(policy.purpose)}</p>
        <h3>Hard exclusions</h3><ul>${(policy.hard_exclusions || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        <h3>Conditional exclusions</h3><ul>${(policy.conditional_exclusions || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        <h3>Execution rules</h3><ul><li>${escapeHtml(policy.entry_rule)}</li><li>${escapeHtml(policy.sizing_rule)}</li><li>${escapeHtml(policy.portfolio_rule)}</li><li>${escapeHtml(policy.time_stop)}</li><li>${escapeHtml(policy.profit_rule)}</li><li>${escapeHtml(policy.averaging_rule)}</li></ul>
        <p><strong>${escapeHtml(policy.research_status)}</strong></p>`;
    } catch (error) {
      els.policyContent.textContent = `Could not load policy: ${error.message}`;
    }
  }

  function bindEvents() {
    els.runScan.addEventListener("click", runFreshScan);
    els.refresh.addEventListener("click", () => loadLatest(true));
    els.analyseTop.addEventListener("click", analyseTopTen);
    els.policyButton.addEventListener("click", showPolicy);
    els.closePolicy.addEventListener("click", () => els.policyDialog.close());
    els.positionForm.addEventListener("submit", submitPosition);
    els.clearPositions.addEventListener("click", async () => {
      if (!state.positions.length || window.confirm("Clear all locally saved positions?")) {
        state.positions = [];
        savePositions();
        await reviewSavedPositions();
      }
    });

    els.candidateRows.addEventListener("click", async (event) => {
      const row = event.target.closest("tr[data-candidate-id]");
      if (!row) return;
      const candidate = rowCandidate(row);
      if (!candidate) return;
      const decisionButton = event.target.closest(".decision");
      if (decisionButton) {
        row.querySelectorAll(".decision").forEach((button) => button.classList.remove("is-selected"));
        decisionButton.classList.add("is-selected");
        await saveReview(row, decisionButton.dataset.decision);
        return;
      }
      if (event.target.closest('[data-action="save-review"]')) {
        await saveReview(row);
        return;
      }
      if (event.target.closest('[data-action="chatgpt"]')) {
        await challengeCandidate(candidate);
      }
    });

    els.positionResults.addEventListener("click", async (event) => {
      const button = event.target.closest(".delete-position");
      if (!button) return;
      const card = button.closest("[data-position-symbol]") || button.closest(".position-card");
      const symbol = card?.dataset?.positionSymbol || card?.querySelector("strong")?.textContent;
      state.positions = state.positions.filter((item) => item.symbol !== symbol);
      savePositions();
      await reviewSavedPositions();
    });

    [els.accountValue, els.riskBudget, els.maxPosition, els.usdPerGbp, els.maxTheme, els.maxOpenRisk].forEach((input) => {
      input.addEventListener("change", () => {
        readSettings();
        window.clearTimeout(state.refreshTimer);
        state.refreshTimer = window.setTimeout(() => loadLatest(false), 350);
      });
    });
  }

  async function init() {
    loadSettings();
    loadPositions();
    bindEvents();
    await loadLatest(false);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
