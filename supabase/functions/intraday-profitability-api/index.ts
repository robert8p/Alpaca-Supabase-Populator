import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const EXPECTED_USER = "admin";
const EXPECTED_KEY_SHA256 = "056975cd5cd9fdbeb538524c6d2775f364333cb693a1e2a9d445e207a028559f";
const ALLOWED_ORIGINS = new Set([
  "https://alpaca-intraday-profitability-app.onrender.com",
  "https://alpaca-rapid-discovery-web.onrender.com",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
]);
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function corsHeaders(req: Request): Record<string, string> {
  const origin = req.headers.get("origin") || "";
  const headers: Record<string, string> = {
    "access-control-allow-headers": "content-type,x-app-user,x-app-key",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-max-age": "86400",
    "cache-control": "no-store",
    "content-type": "application/json; charset=utf-8",
    "vary": "Origin",
  };
  if (ALLOWED_ORIGINS.has(origin)) headers["access-control-allow-origin"] = origin;
  return headers;
}

function out(req: Request, body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: corsHeaders(req) });
}

function hex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes)).map((value) => value.toString(16).padStart(2, "0")).join("");
}

function constantTimeEqual(left: string, right: string): boolean {
  const max = Math.max(left.length, right.length);
  let mismatch = left.length ^ right.length;
  for (let index = 0; index < max; index += 1) {
    mismatch |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
  }
  return mismatch === 0;
}

async function authorised(req: Request): Promise<boolean> {
  const user = req.headers.get("x-app-user") || "";
  const key = req.headers.get("x-app-key") || "";
  if (!constantTimeEqual(user, EXPECTED_USER) || key.length < 20 || key.length > 256) return false;
  const digest = hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(key)));
  return constantTimeEqual(digest, EXPECTED_KEY_SHA256);
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
    const error = new Error(`Data API ${response.status}: ${detail}`);
    (error as Error & { status?: number }).status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

function first<T>(value: unknown): T | null {
  return Array.isArray(value) && value.length ? value[0] as T : null;
}

async function scanDetail(scanId: string): Promise<{ scan: Record<string, unknown> | null; candidates: unknown[] }> {
  if (!UUID_RE.test(scanId)) throw Object.assign(new Error("Invalid scan ID"), { status: 400 });
  const scan = first<Record<string, unknown>>(await rest(`ip_scans?select=*&id=eq.${encodeURIComponent(scanId)}&limit=1`));
  if (!scan) return { scan: null, candidates: [] };
  const candidates = await rest(`ip_candidates?select=*&scan_id=eq.${encodeURIComponent(scanId)}&order=rank.asc`);
  return { scan, candidates: Array.isArray(candidates) ? candidates : [] };
}

async function latestPayload(): Promise<Record<string, unknown>> {
  const scan = first<Record<string, unknown>>(await rest("ip_scans?select=*&order=started_at.desc&limit=1"));
  const activeRequest = first<Record<string, unknown>>(
    await rest("ip_scan_requests?select=*&status=in.(queued,running)&order=requested_at.asc&limit=1"),
  );
  if (!scan) return { scan: null, candidates: [], active_request: activeRequest };
  const detail = await scanDetail(String(scan.id));
  return { ...detail, active_request: activeRequest };
}

function boundedNumber(value: unknown, fallback: number, min: number, max: number): number {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, number));
}

function boundedInteger(value: unknown, fallback: number, min: number, max: number): number {
  return Math.round(boundedNumber(value, fallback, min, max));
}

async function createRequest(body: Record<string, unknown>): Promise<Record<string, unknown>> {
  const active = first<Record<string, unknown>>(
    await rest("ip_scan_requests?select=*&status=in.(queued,running)&order=requested_at.asc&limit=1"),
  );
  if (active) return { request: active, duplicate: true };

  const direction = ["both", "long", "short"].includes(String(body.direction)) ? String(body.direction) : "both";
  const payload = {
    direction_filter: direction,
    min_price: boundedNumber(body.min_price, 5, 1, 1000),
    min_prev_dollar_volume: boundedNumber(body.min_prev_dollar_volume, 50_000_000, 1_000_000, 50_000_000_000),
    min_current_dollar_volume: boundedNumber(body.min_current_dollar_volume, 5_000_000, 100_000, 10_000_000_000),
    max_spread_bps: boundedNumber(body.max_spread_bps, 25, 1, 200),
    prefilter_limit: boundedInteger(body.prefilter_limit, 300, 25, 500),
    candidate_limit: boundedInteger(body.candidate_limit, 50, 10, 100),
    requested_by: "render-static-app",
    metadata: { source: "intraday-profitability-static-v1" },
  };

  try {
    const inserted = await rest("ip_scan_requests", {
      method: "POST",
      headers: { prefer: "return=representation" },
      body: JSON.stringify(payload),
    });
    return { request: first<Record<string, unknown>>(inserted), duplicate: false };
  } catch (error) {
    if ((error as Error & { status?: number }).status === 409) {
      const concurrent = first<Record<string, unknown>>(
        await rest("ip_scan_requests?select=*&status=in.(queued,running)&order=requested_at.asc&limit=1"),
      );
      if (concurrent) return { request: concurrent, duplicate: true };
    }
    throw error;
  }
}

async function requestPayload(requestId: string): Promise<Record<string, unknown>> {
  if (!UUID_RE.test(requestId)) throw Object.assign(new Error("Invalid request ID"), { status: 400 });
  const request = first<Record<string, unknown>>(
    await rest(`ip_scan_requests?select=*&id=eq.${encodeURIComponent(requestId)}&limit=1`),
  );
  if (!request) throw Object.assign(new Error("Scan request not found"), { status: 404 });
  if (!request.scan_id) return { request, scan: null, candidates: [] };
  return { request, ...(await scanDetail(String(request.scan_id))) };
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(req) });
  const url = new URL(req.url);
  const action = url.searchParams.get("action") || "health";

  if (action === "health") {
    return out(req, { status: "ok", service: "intraday-profitability-api", time: new Date().toISOString() });
  }

  if (action === "readiness") {
    try {
      const scans = await rest("ip_scans?select=id&limit=1");
      const requests = await rest("ip_scan_requests?select=id&limit=1");
      return out(req, {
        status: "ready",
        service: "intraday-profitability-api",
        database: "ok",
        scan_table: Array.isArray(scans),
        request_table: Array.isArray(requests),
        time: new Date().toISOString(),
      });
    } catch (error) {
      return out(req, { status: "not_ready", detail: error instanceof Error ? error.message : String(error) }, 503);
    }
  }

  if (!await authorised(req)) {
    return out(req, { error: "unauthorised", detail: "Valid app credentials are required." }, 401);
  }

  try {
    if (req.method === "GET" && action === "latest") return out(req, await latestPayload());
    if (req.method === "GET" && action === "scan") {
      const scanId = url.searchParams.get("scan_id") || "";
      const detail = await scanDetail(scanId);
      return detail.scan ? out(req, detail) : out(req, { error: "not_found" }, 404);
    }
    if (req.method === "GET" && action === "request") {
      return out(req, await requestPayload(url.searchParams.get("request_id") || ""));
    }
    if (req.method === "POST" && action === "run") {
      const raw = await req.json().catch(() => ({}));
      const body = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
      return out(req, await createRequest(body), 202);
    }
    return out(req, { error: "not_found" }, 404);
  } catch (error) {
    const status = Number((error as Error & { status?: number }).status || 500);
    const detail = error instanceof Error ? error.message : String(error);
    return out(req, { error: status >= 500 ? "internal_error" : "request_error", detail }, status);
  }
});
