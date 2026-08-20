(() => {
  const runButton = document.getElementById('run');
  if (!runButton) return;

  const CHATGPT_BASE = 'https://chatgpt.com/?q=';
  const THREE_SESSION_LABEL = 'Calibration horizon: reversion must occur within 3 trading sessions.';
  const statusLine = () => document.getElementById('status-line');
  const fmt = (value, digits = 2) => value == null ? 'unknown' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
  const money = (value) => value == null ? 'unknown' : Number(value).toLocaleString(undefined, { style:'currency', currency:'USD', maximumFractionDigits:2 });
  const clip = (value, max = 180) => {
    const text = String(value ?? '').replace(/\s+/g, ' ').trim();
    return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
  };

  function sanitizeTargetCopy(value) {
    return String(value ?? '')
      .replace(/at least \+5% above the stored signal price within six weeks/gi, 'a tradable reversion within 3 trading sessions')
      .replace(/\+5% from signal price within 6 weeks/gi, 'reversion within 3 trading sessions')
      .replace(/six-week \+5% reversion/gi, '3-trading-session reversion')
      .replace(/\+5% six-week reversion/gi, '3-trading-session reversion')
      .replace(/evidence for\/against a six-week \+5% reversion/gi, 'evidence for/against a reversion within 3 trading sessions')
      .replace(/rank by six-week \+5% reversion quality/gi, 'rank by 3-trading-session reversion quality')
      .replace(/within six weeks/gi, 'within 3 trading sessions')
      .replace(/hit_plus_5pct_within_6_weeks/gi, 'legacy_reversion_target');
  }

  function rewriteTextNodes(root) {
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      const next = sanitizeTargetCopy(node.nodeValue);
      if (next !== node.nodeValue) node.nodeValue = next;
    });
  }

  function applyThreeSessionUi() {
    const banner = document.getElementById('or-banner-text');
    if (banner && banner.textContent !== THREE_SESSION_LABEL) banner.textContent = THREE_SESSION_LABEL;
    document.querySelectorAll('.or-model-score').forEach(rewriteTextNodes);
    rewriteTextNodes(document.getElementById('or-model-dialog'));

    const currentPromptBuilder = window.buildChatGPTPrompt;
    if (typeof currentPromptBuilder === 'function' && !currentPromptBuilder.__threeSessionTarget) {
      const wrapped = function buildThreeSessionAuditPrompt(candidate) {
        return sanitizeTargetCopy(currentPromptBuilder(candidate));
      };
      wrapped.__threeSessionTarget = true;
      window.buildChatGPTPrompt = wrapped;
    }
  }

  function scheduleThreeSessionUi() {
    if (window.__orThreeSessionUiScheduled) return;
    window.__orThreeSessionUiScheduled = true;
    queueMicrotask(() => {
      window.__orThreeSessionUiScheduled = false;
      applyThreeSessionUi();
    });
  }

  if (!window.__orThreeSessionUiObserver) {
    window.__orThreeSessionUiObserver = new MutationObserver(scheduleThreeSessionUi);
    window.__orThreeSessionUiObserver.observe(document.body, { childList:true, subtree:true, characterData:true });
  }

  async function fetchWithTimeout(url, options = {}, timeoutMs = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try { return await fetch(url, { ...options, signal:controller.signal }); }
    catch (error) { if (error?.name === 'AbortError') throw new Error('Request timed out. Please retry.'); throw error; }
    finally { clearTimeout(timer); }
  }

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; }
    catch (_) {
      try {
        const el = document.createElement('textarea');
        el.value = text;
        el.setAttribute('readonly','');
        el.style.position = 'fixed';
        el.style.opacity = '0';
        document.body.appendChild(el);
        el.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(el);
        return ok;
      } catch (_) { return false; }
    }
  }

  function chatGPTUrl(prompt) {
    return `${CHATGPT_BASE}${encodeURIComponent(prompt)}`;
  }

  function compactNews(c, limit = 2) {
    const articles = Array.isArray(c.evidence_news) ? c.evidence_news : (Array.isArray(c.headlines) ? c.headlines : []);
    return articles.slice(0, limit).map(a => clip(a.headline || 'Untitled', 140)).join(' | ') || 'none retained';
  }

  function compactSinglePrompt(c) {
    const a = c.catalyst_analysis || {};
    const flags = (c.risk_flags || []).join(', ') || 'none';
    const cutoff = c.evidence_cutoff || c.signal_timestamp || c.created_at || 'unknown';
    const metric = c.model_status === 'calibrated' && c.calibrated_probability != null
      ? `${fmt(Number(c.calibrated_probability) * 100, 1)}% calibrated probability; raw score ${fmt(c.reversion_score,1)}`
      : `${fmt(c.reversion_score ?? c.heuristic_score,1)}/100 Reversion Score (uncalibrated)`;
    return `Audit ${c.name || c.symbol} (${c.symbol}) as the ORIGINAL Oversold Reversion signal using only evidence available by ${cutoff}.\n\nApp context: move ${fmt(c.drop_pct,2)}%; signal/last price ${money(c.signal_price ?? c.last_price)}; app metric ${metric}; verdict ${c.model_verdict || c.triage_label || 'unknown'}; Setup ${fmt(c.setup_score,0)}, Catalyst ${fmt(c.catalyst_score,0)}, Resilience ${fmt(c.resilience_score,0)}, Damage ${fmt(c.damage_risk,0)}, Confirmation ${fmt(c.confirmation_score,0)}, Confidence ${fmt(c.evidence_confidence,0)}; event ${a.event_profile || a.catalyst_type || c.catalyst_class || 'unknown'}; cause verified ${a.cause_verified ? 'yes' : 'no'}; summary: ${clip(c.catalyst_summary || 'none', 240)}; risk flags: ${clip(flags,180)}.\nRetained headlines: ${compactNews(c,3)}.\n\nCheck the primary cause, whether the app components are too high/low, permanent-damage risk, evidence for/against a reversion within 3 trading sessions, and whether INVESTIGATE/WATCH/PASS is defensible. Return a concise component-audit table plus the key invalidator. Do not use post-cutoff hindsight.`;
  }

  function compactTopPrompt(candidates) {
    const rows = candidates.map((c, index) => {
      const a = c.catalyst_analysis || {};
      const metric = c.model_status === 'calibrated' && c.calibrated_probability != null
        ? `${fmt(Number(c.calibrated_probability) * 100,1)}%`
        : `${fmt(c.reversion_score ?? c.heuristic_score,1)}/100`;
      return `${index + 1}. ${c.symbol} (${clip(c.name || '',60)}): rank ${c.rank ?? index + 1}; move ${fmt(c.drop_pct,1)}%; metric ${metric}; verdict ${c.model_verdict || c.triage_label || 'unknown'}; components S${fmt(c.setup_score,0)}/C${fmt(c.catalyst_score,0)}/R${fmt(c.resilience_score,0)}/D${fmt(c.damage_risk,0)}/Conf${fmt(c.confirmation_score,0)}/Q${fmt(c.evidence_confidence,0)}; event ${a.event_profile || a.catalyst_type || c.catalyst_class || 'unknown'}; verified ${a.cause_verified ? 'yes' : 'no'}; summary ${clip(c.catalyst_summary || 'none',150)}; news ${compactNews(c,1)}.`;
    }).join('\n');

    return `Audit and compare these ${candidates.length} Oversold Reversion candidates as their ORIGINAL signals. Respect each candidate's stored evidence cutoff and do not use hindsight.\n\n${rows}\n\nFor each stock give: cause VERIFIED/UNVERIFIED, material component disagreement, Damage assessment, evidence-confidence assessment, whether the app verdict is defensible, audited INVESTIGATE/WATCH/PASS verdict, allocated position, and key invalidator. Rank by 3-trading-session reversion quality. Only INVESTIGATE-grade stocks may receive non-zero allocation; if any qualify allocate exactly 100.0% across them, otherwise allocate 0% to all. Keep the answer concise.`;
  }

  window.analyseInChatGPT = function analyseInChatGPTPrefilled(id) {
    const c = typeof state !== 'undefined' ? state.candidates.find(item => Number(item.id) === Number(id)) : null;
    if (!c) return;
    const compactPrompt = compactSinglePrompt(c);
    const fullPrompt = typeof buildChatGPTPrompt === 'function' ? sanitizeTargetCopy(buildChatGPTPrompt(c)) : compactPrompt;
    const opened = window.open(chatGPTUrl(compactPrompt), '_blank', 'noopener');
    copyText(fullPrompt).then(copied => {
      const status = statusLine();
      if (!status) return;
      status.textContent = opened
        ? `${c.symbol}: ChatGPT opened with a premade audit prompt${copied ? '; full audit prompt also copied.' : '.'}`
        : `${c.symbol}: popup blocked${copied ? '; full audit prompt copied.' : '.'}`;
    });
  };

  async function analyseTop(limit, button) {
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = `Preparing Top ${limit}…`;
    const popup = window.open('about:blank', '_blank');
    try {
      const response = await fetchWithTimeout('/api/oversold/latest', { cache:'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const candidates = [...(data.candidates || [])]
        .sort((a,b) => Number(a.rank ?? 999999) - Number(b.rank ?? 999999))
        .slice(0,limit);
      if (!candidates.length) throw new Error('No candidates are available in the latest scan');
      const prompt = compactTopPrompt(candidates);
      const copied = await copyText(prompt);
      if (popup) popup.location.replace(chatGPTUrl(prompt));
      else window.open(chatGPTUrl(prompt), '_blank', 'noopener');
      const status = statusLine();
      if (status) status.textContent = `Top ${candidates.length}: ChatGPT opened with a premade audit prompt${copied ? '; prompt also copied.' : '.'}`;
    } catch (error) {
      if (popup) popup.close();
      const status = statusLine();
      if (status) status.textContent = `Top ${limit} analysis failed: ${error.message}`;
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  }

  function addButton(limit, afterElement) {
    const id = `analyse-top${limit}`;
    if (document.getElementById(id)) return afterElement;
    const button = document.createElement('button');
    button.id = id;
    button.className = 'chatgpt-button';
    button.style.marginLeft = '8px';
    button.textContent = `Audit Top ${limit} in ChatGPT ↗`;
    button.title = `Open ChatGPT with a premade prompt to audit the latest top ${limit}`;
    afterElement.insertAdjacentElement('afterend', button);
    button.addEventListener('click', () => analyseTop(limit, button));
    return button;
  }

  const top5Button = addButton(5, runButton);
  addButton(10, top5Button);

  applyThreeSessionUi();
  setTimeout(applyThreeSessionUi, 0);
  setTimeout(applyThreeSessionUi, 250);
})();