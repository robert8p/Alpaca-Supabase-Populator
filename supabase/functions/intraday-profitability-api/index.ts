import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ALLOWED_ORIGINS = new Set([
  "https://alpaca-intraday-profitability-app.onrender.com",
  "https://alpaca-rapid-discovery-web.onrender.com",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
]);
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const INTEGER_RE = /^\d+$/;
const GLOBAL_RUN_COOLDOWN_MS = 60_000;
const RATE_LIMITS: Record<string, { limit: number; windowMs: number }> = {
  run: { limit: 6, windowMs: 60 * 60 * 1000 },
  select: { limit: 120, windowMs: 24 * 60 * 60 * 1000 },
};

type ApiError = Error & { status?: number; retryAfterSeconds?: number };
type Row = Record<string, unknown>;

function requestOrigin(req: Request): string {
  return (req.headers.get("origin") || "").replace(/\/$/, "");
}

function originAllowed(req: Request): boolean {
  return ALLOWED_ORIGINS.has(requestOrigin(req));
}

function corsHeaders(req: Request): Record<string, string> {
  const origin = requestOrigin(req);
  const headers: Record<string, string> = {
    "access-control-allow-headers": "content-type",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-max-age": "86400",
    "cache-control": "no-store",
    "content-type": "application/json; charset=utf-8",
    "vary": "Origin",
  };
  if (ALLOWED_ORIGINS.has(origin)) headers["access-control-allow-origin"] = origin;
  return headers;
}

function out(req: Request, body: unknown, status = 200, extraHeaders: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(req), ...extraHeaders },
  });
}

function hex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes))
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

async function rest(path: string, init: RequestInit = {}): Promise<unknown> {
  const headers = new Headers(init.headers || {});
  headers.set("apikey", SERVICE_KEY);
  headers.set("authorization", `Bearer ${SERVICE_KEY}`);
  headers.set("content-type", "application/json");
  headers.set("accept", "application/json");
  const response = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, { ...init, headers });
  if (!response.ok) {
    const detail = await response.text();
    const error = new Error(`Data API ${response.status}: ${detail}`) as ApiError;
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

function first<T>(value: unknown): T | null {
  return Array.isArray(value) && value.length ? value[0] as T : null;
}

function rows(value: unknown): Row[] {
  return Array.isArray(value) ? value as Row[] : [];
}

function clientAddress(req: Request): string {
  const forwarded = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return req.headers.get("cf-connecting-ip") || forwarded || req.headers.get("x-real-ip") || "unknown";
}

async function clientHash(req: Request): Promise<string> {
  const material = `${clientAddress(req)}|${(req.headers.get("user-agent") || "unknown").slice(0, 180)}`;
  return hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(material)));
}

async function enforceMutationRateLimit(req: Request, action: "run" | "select"): Promise<string> {
  const rule = RATE_LIMITS[action];
  const hash = await clientHash(req);
  const since = new Date(Date.now() - rule.windowMs).toISOString();
  const recent = rows(await rest(
    `ip_public_api_requests?select=id,created_at&client_hash=eq.${hash}&action=eq.${action}`
      + `&created_at=gte.${encodeURIComponent(since)}&order=created_at.desc&limit=${rule.limit}`,
  ));
  if (recent.length >= rule.limit) {
    const oldest = Date.parse(String(recent[recent.length - 1]?.created_at || since));
    const retry = Math.max(1, Math.ceil((oldest + rule.windowMs - Date.now()) / 1000));
    const error = new Error(
      action === "run"
        ? "This browser has reached the public scan limit."
        : "This browser has reached the public selection limit.",
    ) as ApiError;
    error.status = 429;
    error.retryAfterSeconds = retry;
    throw error;
  }
  await rest("ip_public_api_requests", {
    method: "POST",
    body: JSON.stringify({
      client_hash: hash,
      action,
      metadata: {
        origin: requestOrigin(req),
        user_agent_family: (req.headers.get("user-agent") || "unknown").slice(0, 80),
      },
    }),
  });
  if (action === "run") {
    const retentionCutoff = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
    rest(`ip_public_api_requests?created_at=lt.${encodeURIComponent(retentionCutoff)}`, { method: "DELETE" })
      .catch(() => undefined);
  }
  return hash;
}

async function enforceGlobalRunCooldown(): Promise<void> {
  const latest = first<Row>(await rest("ip_scan_requests?select=requested_at&order=requested_at.desc&limit=1"));
  if (!latest?.requested_at) return;
  const remaining = Date.parse(String(latest.requested_at)) + GLOBAL_RUN_COOLDOWN_MS - Date.now();
  if (remaining > 0) {
    const error = new Error("A scan was started very recently. The global cooldown protects the Alpaca worker from repeated public requests.") as ApiError;
    error.status = 429;
    error.retryAfterSeconds = Math.max(1, Math.ceil(remaining / 1000));
    throw error;
  }
}

async function activeModelAudit(): Promise<Row | null> {
  return first<Row>(await rest("ip_model_audits?select=*&active=eq.true&limit=1"));
}

async function selectedRows(): Promise<Row[]> {
  return rows(await rest(
    "ip_selected_candidates?select=*&user_selected=eq.true"
      + "&order=user_selected_at.desc.nullslast,selected_at.desc",
  ));
}

async function trackingSummary(): Promise<Row> {
  const tracked = rows(await rest(
    "ip_selected_candidates?select=id,user_selected,status,horizon_status,entry_price,horizon_price,refresh_error",
  ));
  return {
    total_candidates_tracked: tracked.length,
    user_selected: tracked.filter((row) => row.user_selected === true).length,
    horizon_matured: tracked.filter((row) => row.horizon_status === "matured").length,
    close_matured: tracked.filter((row) => row.status === "closed").length,
    entry_observed: tracked.filter((row) => row.entry_price != null).length,
    tracking_errors: tracked.filter((row) => Boolean(row.refresh_error)).length,
    population: "all persisted ranked candidates",
  };
}

async function scanDetail(scanId: string): Promise<{ scan: Row | null; candidates: unknown[] }> {
  if (!UUID_RE.test(scanId)) {
    const error = new Error("Invalid scan ID") as ApiError;
    error.status = 400;
    throw error;
  }
  const scan = first<Row>(await rest(`ip_scans?select=*&id=eq.${encodeURIComponent(scanId)}&limit=1`));
  if (!scan) return { scan: null, candidates: [] };
  const candidates = await rest(`ip_candidates?select=*&scan_id=eq.${encodeURIComponent(scanId)}&order=rank.asc`);
  return { scan, candidates: Array.isArray(candidates) ? candidates : [] };
}

async function latestPayload(): Promise<Row> {
  const [scanValue, activeValue, selections, audit, tracking] = await Promise.all([
    rest("ip_scans?select=*&order=started_at.desc&limit=1"),
    rest("ip_scan_requests?select=*&status=in.(queued,running)&order=requested_at.asc&limit=1"),
    selectedRows(),
    activeModelAudit(),
    trackingSummary(),
  ]);
  const scan = first<Row>(scanValue);
  const activeRequest = first<Row>(activeValue);
  const selectedCandidateIds = selections.map((row) => Number(row.candidate_id)).filter(Number.isFinite);
  if (!scan) {
    return {
      scan: null,
      candidates: [],
      active_request: activeRequest,
      selected_candidate_ids: selectedCandidateIds,
      model_audit: audit,
      tracking_summary: tracking,
    };
  }
  const detail = await scanDetail(String(scan.id));
  return {
    ...detail,
    active_request: activeRequest,
    selected_candidate_ids: selectedCandidateIds,
    model_audit: audit,
    tracking_summary: tracking,
  };
}

function boundedNumber(value: unknown, fallback: number, min: number, max: number): number {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, number));
}

function boundedInteger(value: unknown, fallback: number, min: number, max: number): number {
  return Math.round(boundedNumber(value, fallback, min, max));
}

async function createRequest(req: Request, body: Row): Promise<Row> {
  const active = first<Row>(await rest(
    "ip_scan_requests?select=*&status=in.(queued,running)&order=requested_at.asc&limit=1",
  ));
  if (active) return { request: active, duplicate: true };

  const hash = await enforceMutationRateLimit(req, "run");
  await enforceGlobalRunCooldown();
  const direction = ["both", "long", "short"].includes(String(body.direction)) ? String(body.direction) : "both";
  const payload = {
    direction_filter: direction,
    min_price: boundedNumber(body.min_price, 5, 1, 1000),
    min_prev_dollar_volume: boundedNumber(body.min_prev_dollar_volume, 50_000_000, 1_000_000, 50_000_000_000),
    min_current_dollar_volume: boundedNumber(body.min_current_dollar_volume, 5_000_000, 100_000, 10_000_000_000),
    max_spread_bps: boundedNumber(body.max_spread_bps, 25, 1, 200),
    prefilter_limit: boundedInteger(body.prefilter_limit, 300, 25, 500),
    candidate_limit: boundedInteger(body.candidate_limit, 50, 10, 100),
    requested_by: "render-public-app",
    metadata: {
      source: "intraday-reliability-public-v4",
      public_client_hash: hash,
      requested_model_audit: "ip-reliability-v3.0",
    },
  };
  try {
    const inserted = await rest("ip_scan_requests", {
      method: "POST",
      headers: { prefer: "return=representation" },
      body: JSON.stringify(payload),
    });
    return { request: first<Row>(inserted), duplicate: false };
  } catch (error) {
    if ((error as ApiError).status === 409) {
      const concurrent = first<Row>(await rest(
        "ip_scan_requests?select=*&status=in.(queued,running)&order=requested_at.asc&limit=1",
      ));
      if (concurrent) return { request: concurrent, duplicate: true };
    }
    throw error;
  }
}

async function requestPayload(requestId: string): Promise<Row> {
  if (!UUID_RE.test(requestId)) {
    const error = new Error("Invalid request ID") as ApiError;
    error.status = 400;
    throw error;
  }
  const request = first<Row>(await rest(`ip_scan_requests?select=*&id=eq.${encodeURIComponent(requestId)}&limit=1`));
  if (!request) {
    const error = new Error("Scan request not found") as ApiError;
    error.status = 404;
    throw error;
  }
  if (!request.scan_id) return { request, scan: null, candidates: [] };
  return {
    request,
    ...(await scanDetail(String(request.scan_id))),
    model_audit: await activeModelAudit(),
    tracking_summary: await trackingSummary(),
  };
}

async function markExistingSelection(req: Request, existing: Row): Promise<Row> {
  if (existing.user_selected === true) return { selection: existing, duplicate: true };
  const hash = await enforceMutationRateLimit(req, "select");
  const updated = await rest(`ip_selected_candidates?candidate_id=eq.${String(existing.candidate_id)}`, {
    method: "PATCH",
    headers: { prefer: "return=representation" },
    body: JSON.stringify({
      user_selected: true,
      user_selected_at: new Date().toISOString(),
      metadata: {
        ...(existing.metadata && typeof existing.metadata === "object" ? existing.metadata as Row : {}),
        user_selection_source: "public-scanner-select-button",
        public_client_hash: hash,
      },
    }),
  });
  return { selection: first<Row>(updated), duplicate: false };
}

async function selectCandidate(req: Request, body: Row): Promise<Row> {
  const candidateId = String(body.candidate_id ?? "");
  if (!INTEGER_RE.test(candidateId) || Number(candidateId) <= 0) {
    const error = new Error("Invalid candidate ID") as ApiError;
    error.status = 400;
    throw error;
  }
  const existing = first<Row>(await rest(
    `ip_selected_candidates?select=*&candidate_id=eq.${candidateId}&limit=1`,
  ));
  if (existing) return markExistingSelection(req, existing);

  const hash = await enforceMutationRateLimit(req, "select");
  const candidate = first<Row>(await rest(`ip_candidates?select=*&id=eq.${candidateId}&limit=1`));
  if (!candidate) {
    const error = new Error("Candidate not found") as ApiError;
    error.status = 404;
    throw error;
  }
  const scan = first<Row>(await rest(
    `ip_scans?select=id,status,evidence_cutoff,horizon_end,market_close&id=eq.${encodeURIComponent(String(candidate.scan_id))}&limit=1`,
  ));
  if (!scan || scan.status !== "completed" || !scan.evidence_cutoff || !scan.market_close) {
    const error = new Error("Only candidates from a completed scan with a known market close can be selected") as ApiError;
    error.status = 409;
    throw error;
  }

  const evidence = candidate.evidence as Row | null;
  const now = new Date().toISOString();
  const payload = {
    candidate_id: Number(candidate.id),
    scan_id: candidate.scan_id,
    symbol: candidate.symbol,
    name: candidate.name,
    exchange: candidate.exchange,
    direction: candidate.direction,
    setup_type: candidate.setup_type,
    selected_rank: candidate.rank,
    profitability_score: candidate.profitability_score,
    scan_price: candidate.last_price,
    scan_at: scan.evidence_cutoff,
    market_close_at: scan.market_close,
    market_date: String(scan.evidence_cutoff).slice(0, 10),
    selected_at: now,
    user_selected: true,
    user_selected_at: now,
    auto_enrolled_at: now,
    horizon_end_at: scan.horizon_end,
    tracking_version: "ip-tracking-v3",
    metadata: {
      source: "public-scanner-select-button-fallback-enrolment",
      public_client_hash: hash,
      scoring_version: evidence?.scoring_version || null,
      original_initial_view: candidate.initial_view,
      original_rationale: candidate.rationale,
    },
  };
  try {
    const inserted = await rest("ip_selected_candidates", {
      method: "POST",
      headers: { prefer: "return=representation" },
      body: JSON.stringify(payload),
    });
    return { selection: first<Row>(inserted), duplicate: false };
  } catch (error) {
    if ((error as ApiError).status === 409) {
      const concurrent = first<Row>(await rest(
        `ip_selected_candidates?select=*&candidate_id=eq.${candidateId}&limit=1`,
      ));
      if (concurrent) return markExistingSelection(req, concurrent);
    }
    throw error;
  }
}

Deno.serve(async (req: Request) => {
  const url = new URL(req.url);
  const action = url.searchParams.get("action") || "health";

  if (req.method === "OPTIONS") {
    if (!originAllowed(req)) return out(req, { error: "origin_not_allowed" }, 403);
    return new Response(null, { status: 204, headers: corsHeaders(req) });
  }

  if (action === "health") {
    return out(req, {
      status: "ok",
      service: "intraday-profitability-api",
      version: "4.0-reliability",
      credentials_required: false,
      time: new Date().toISOString(),
    });
  }

  if (action === "readiness") {
    try {
      const [scans, requests, selections, rateLimits, audits] = await Promise.all([
        rest("ip_scans?select=id&limit=1"),
        rest("ip_scan_requests?select=id&limit=1"),
        rest("ip_selected_candidates?select=id&limit=1"),
        rest("ip_public_api_requests?select=id&limit=1"),
        rest("ip_model_audits?select=model_version&active=eq.true&limit=1"),
      ]);
      return out(req, {
        status: "ready",
        service: "intraday-profitability-api",
        version: "4.0-reliability",
        credentials_required: false,
        database: "ok",
        scan_table: Array.isArray(scans),
        request_table: Array.isArray(requests),
        tracking_table: Array.isArray(selections),
        public_rate_limit_table: Array.isArray(rateLimits),
        active_model_audit: Array.isArray(audits) && audits.length === 1,
        time: new Date().toISOString(),
      });
    } catch (error) {
      return out(req, {
        status: "not_ready",
        detail: error instanceof Error ? error.message : String(error),
      }, 503);
    }
  }

  if (!originAllowed(req)) {
    return out(req, {
      error: "origin_not_allowed",
      detail: "The public API accepts browser requests only from the production Intraday Profitability site.",
    }, 403);
  }

  try {
    if (req.method === "GET" && action === "latest") return out(req, await latestPayload());
    if (req.method === "GET" && action === "selections") {
      return out(req, {
        selections: await selectedRows(),
        model_audit: await activeModelAudit(),
        tracking_summary: await trackingSummary(),
      });
    }
    if (req.method === "GET" && action === "audit") {
      return out(req, {
        model_audit: await activeModelAudit(),
        tracking_summary: await trackingSummary(),
      });
    }
    if (req.method === "GET" && action === "scan") {
      const detail = await scanDetail(url.searchParams.get("scan_id") || "");
      return detail.scan ? out(req, detail) : out(req, { error: "not_found" }, 404);
    }
    if (req.method === "GET" && action === "request") {
      return out(req, await requestPayload(url.searchParams.get("request_id") || ""));
    }
    if (req.method === "POST" && action === "run") {
      const raw = await req.json().catch(() => ({}));
      const body = raw && typeof raw === "object" ? raw as Row : {};
      return out(req, await createRequest(req, body), 202);
    }
    if (req.method === "POST" && action === "select") {
      const raw = await req.json().catch(() => ({}));
      const body = raw && typeof raw === "object" ? raw as Row : {};
      return out(req, await selectCandidate(req, body), 201);
    }
    return out(req, { error: "not_found" }, 404);
  } catch (error) {
    const apiError = error as ApiError;
    const status = Number(apiError.status || 500);
    const detail = error instanceof Error ? error.message : String(error);
    const retry = apiError.retryAfterSeconds;
    return out(
      req,
      {
        error: status === 429 ? "rate_limited" : status >= 500 ? "internal_error" : "request_error",
        detail,
        ...(retry ? { retry_after_seconds: retry } : {}),
      },
      status,
      retry ? { "retry-after": String(retry) } : {},
    );
  }
});
