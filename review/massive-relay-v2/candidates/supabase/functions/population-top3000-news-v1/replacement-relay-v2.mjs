// Stateless extension of the existing function. Only the existing worker owns work.
export const RELAY_PROTOCOL = "astra-massive-relay-v2";
const PROJECT = "https://oxzabweahkoimtevbbny.supabase.co";
const RUN = "fixed3000-20250901-20260731-v1-20261030";
const RPC = PROJECT + "/rest/v1/rpc/astra_ingestion_rpc_v1";
const ORIGIN = "https://api.massive.com";
const MAX_BODY = 3 * 1024 * 1024, PREFIX = 16 * 1024;
const encoder = new TextEncoder();
const decode = bytes => new TextDecoder("utf-8", {fatal:true, ignoreBOM:true}).decode(bytes);
const exact = (value, keys) => value && typeof value === "object" && !Array.isArray(value) &&
  Object.keys(value).sort().join(",") === [...keys].sort().join(",");
class RelayError extends Error {
  constructor(code, status=503) { super(code); this.code=code; this.status=status; }
}
function publicKey(value) {
  if (typeof value !== "string" || value.length>4096 || /[^\x21-\x7e]/.test(value)) return false;
  if (/^sb_publishable_[A-Za-z0-9_-]{16,}$/.test(value)) return true;
  try {
    const pieces=value.split("."); if(pieces.length!==3)return false;
    const payload=pieces[1].replace(/-/g,"+").replace(/_/g,"/");
    const claims=JSON.parse(atob(payload+"=".repeat((4-payload.length%4)%4)));
    return claims?.role==="anon" && claims?.ref==="oxzabweahkoimtevbbny";
  } catch { return false; }
}
function canonical(value) {
  if(typeof value==="string")return JSON.stringify(value).replace(/[\u007f-\uffff]/g,c=>"\\u"+c.charCodeAt(0).toString(16).padStart(4,"0"));
  if(value===null || typeof value==="boolean" || typeof value==="number")return JSON.stringify(value);
  if(Array.isArray(value))return "["+value.map(canonical).join(",")+"]";
  return "{"+Object.keys(value).sort().map(key=>canonical(key)+":"+canonical(value[key])).join(",")+"}";
}
function requestUrl(request) {
  if(!exact(request,["provider","host","path","method","params"]) || request.provider!=="Massive" ||
     request.host!=="api.massive.com" || request.method!=="GET" || !request.params ||
     typeof request.params!=="object" || Array.isArray(request.params))throw new RelayError("REQUEST_REJECTED",400);
  const paths=new Set(["/v2/reference/news","/stocks/v1/dividends","/stocks/v1/splits","/stocks/v1/short-volume","/stocks/v1/short-interest"]);
  if(!paths.has(request.path) && !/^\/v3\/reference\/tickers\/[A-Za-z0-9](?:[A-Za-z0-9._-]|%2F){0,191}$/.test(request.path))throw new RelayError("REQUEST_REJECTED",400);
  const allowed=new Set(["date","ticker","ticker.any_of","published_utc.gte","published_utc.lte","date.gte","date.lte","settlement_date.gte","settlement_date.lte","limit","sort","order","cursor"]);
  const url=new URL(ORIGIN+request.path);
  for(const [key,value] of Object.entries(request.params)) {
    if(!allowed.has(key) || !["string","number"].includes(typeof value) ||
       (typeof value==="number" && (!Number.isSafeInteger(value)||value<1||value>1000)) ||
       String(value).length>8192 || /[\u0000-\u0020\u007f]/.test(String(value)))throw new RelayError("REQUEST_REJECTED",400);
    url.searchParams.set(key,String(value));
  }
  if(url.origin!==ORIGIN || url.pathname!==request.path)throw new RelayError("REQUEST_REJECTED",400);
  return url.toString();
}
function toBase64(bytes) {
  const chunks=[];
  for(let i=0;i<bytes.length;i+=16384)chunks.push(String.fromCharCode(...bytes.subarray(i,i+16384)));
  return btoa(chunks.join(""));
}
function reflected(text, credentials) {
  const contains=value=>credentials.some(key=>key && (value.includes(key)||value.includes(encodeURIComponent(key))||value.includes(btoa(key))));
  let normalized=text;
  for(let round=0;round<3;round++) {
    if(contains(normalized))return true;
    // Decode one JSON layer at a time. An introduced backslash/percent can
    // itself be part of the credential, so check before another decoder runs.
    const jsonDecoded=normalized.replace(/\\(?:u([0-9a-f]{4})|(["\\/bfnrt]))/gi,(_,hex,value)=>
      hex?String.fromCharCode(parseInt(hex,16)):({b:"\b",f:"\f",n:"\n",r:"\r",t:"\t"})[value]??value);
    if(contains(jsonDecoded))return true;
    const next=jsonDecoded.replace(/%([0-9a-f]{2})/gi,(_,hex)=>String.fromCharCode(parseInt(hex,16)));
    if(contains(next))return true;
    if(next===normalized)break; normalized=next;
  }
  return false;
}

export function createReplacementRelay(deps={}) {
  const fetcher=deps.fetch || globalThis.fetch;
  const env=deps.env || (name=>Deno.env.get(name));
  const now=deps.now || Date.now;
  const crypt=deps.crypto || globalThis.crypto;
  const hash=async bytes=>Array.from(new Uint8Array(await crypt.subtle.digest("SHA-256",bytes)),b=>b.toString(16).padStart(2,"0")).join("");
  const output=(value,status=200)=>Response.json(value,{status,headers:{"cache-control":"no-store","x-content-type-options":"nosniff"}});
  async function boundedRead(stream,cap,deadline) {
    if(!stream)return {bytes:new Uint8Array(),complete:true};
    const reader=stream.getReader(),parts=[];let length=0,complete=false;
    try {
      while(length<=cap) {
        const remaining=deadline-now(); if(remaining<=0)throw new RelayError("SOURCE_READ_TIMEOUT");
        let timer;
        let item;
        try { item=await Promise.race([reader.read(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new RelayError("SOURCE_READ_TIMEOUT")),remaining);})]); }
        finally { if(timer!==undefined)clearTimeout(timer); }
        if(item.done){complete=true;break;}
        const part=item.value.subarray(0,cap+1-length);parts.push(part);length+=part.length;
        if(length>cap)break;
      }
    } finally { void reader.cancel().catch(()=>{}); }
    const bytes=new Uint8Array(length);let offset=0;
    for(const part of parts){bytes.set(part,offset);offset+=part.length;}
    return {bytes,complete};
  }
  function managedKey() {
    for(const name of ["MASSIVE_API_KEY","MASSIVE_KEY","POLYGON_API_KEY","POLYGON_KEY"]) {
      const value=env(name)?.trim();
      if(value && value.length>=16 && value.length<=512 && /^[\x21-\x7e]+$/.test(value))return value;
    }
    return null;
  }
  return async function replacementRelay(req) {
    let dispatched=false,dispatchAttempted=false;
    try {
      if(req.method!=="POST")throw new RelayError("METHOD_NOT_ALLOWED",405);
      if(req.headers.get("x-astra-replacement-relay")!==RELAY_PROTOCOL)throw new RelayError("INVALID_PROTOCOL",400);
      if(env("SUPABASE_URL")!==PROJECT)throw new RelayError("PROJECT_MISMATCH",409);
      const key=req.headers.get("apikey"),token=req.headers.get("x-astra-ingestion-token");
      if(!publicKey(key)||!token||!/^[0-9a-f]{64}$/.test(token))throw new RelayError("AUTHENTICATION_REQUIRED",401);
      if(req.headers.get("content-type")?.split(";")[0].trim().toLowerCase()!=="application/json")throw new RelayError("INVALID_REQUEST",400);
      const incoming=await boundedRead(req.body,65536,now()+1000);
      if(!incoming.complete)throw new RelayError("INVALID_REQUEST",413);
      let body;try{body=JSON.parse(decode(incoming.bytes));}catch{throw new RelayError("INVALID_REQUEST",400);}
      const probe=exact(body,["action"])&&body.action==="probe";
      const fetchRequest=exact(body,["action","claim","request"])&&body.action==="fetch";
      if(!probe&&!fetchRequest)throw new RelayError("INVALID_REQUEST",400);
      let url;
      if(fetchRequest) {
        if(!exact(body.claim,["id","run_id","owner","generation","run_fence","page_no"])||body.claim.run_id!==RUN)throw new RelayError("REQUEST_REJECTED",400);
        url=requestUrl(body.request);
      }
      async function rpc(operation,payload) {
        let response;
        try {response=await fetcher(RPC,{method:"POST",headers:{apikey:key,"x-astra-ingestion-token":token,"content-type":"application/json","accept":"application/json"},
          body:JSON.stringify({operation,payload}),redirect:"error",signal:AbortSignal.timeout(6000)});}catch{throw new RelayError("RELAY_CONTROL_UNAVAILABLE");}
        if(response.status!==200 || response.url!==RPC) {
          void response.body?.cancel().catch(()=>{});
          throw new RelayError(response.status===401||response.status===403?"AUTHENTICATION_REQUIRED":"RELAY_CONTROL_UNAVAILABLE",response.status===401||response.status===403?403:503);
        }
        const bounded=await boundedRead(response.body,32768,now()+2000);
        if(!bounded.complete)throw new RelayError("RELAY_CONTROL_UNAVAILABLE");
        let value;try{value=JSON.parse(decode(bounded.bytes));}catch{throw new RelayError("RELAY_CONTROL_UNAVAILABLE");}
        if(value?.ok!==true)throw new RelayError(value?.error?.code==="lease_lost"?"CLAIM_REJECTED":"REQUEST_REJECTED",409);
        return value.result;
      }
      // Authenticate before inspecting any managed provider key, even for readiness.
      const authorized=await rpc("backfill_relay_probe",{});
      if(authorized?.state!=="AUTHORIZED"||authorized.protocol!==RELAY_PROTOCOL||authorized.run_id!==RUN)throw new RelayError("AUTHENTICATION_REQUIRED",403);
      const sourceKey=managedKey();
      if(probe)return output({ready:sourceKey!==null});
      if(!sourceKey)throw new RelayError("MASSIVE_CREDENTIAL_UNAVAILABLE");
      const credentials=[sourceKey,token];
      if(reflected(JSON.stringify(body.request),credentials))throw new RelayError("SOURCE_CREDENTIAL_ECHO",409);
      const dispatchId=crypt.randomUUID();
      dispatchAttempted=true;
      const ticket=await rpc("backfill_relay_dispatch",{claim:body.claim,request:body.request,dispatch_id:dispatchId});
      if(ticket?.state==="ALREADY_DISPATCHED"){dispatched=true;throw new RelayError("DISPATCH_ALREADY_USED",409);}
      const requestHash=await hash(encoder.encode(canonical(body.request)));
      if(ticket?.state!=="DISPATCH_AUTHORIZED"||ticket.protocol!==RELAY_PROTOCOL||ticket.dispatch_id!==dispatchId||
         ticket.task_id!==body.claim.id||ticket.run_id!==RUN||ticket.generation!==body.claim.generation||ticket.page_no!==body.claim.page_no||
         ticket.request_sha256!==requestHash)throw new RelayError("RELAY_CONTROL_UNAVAILABLE");
      dispatched=true;
      const deadline=Math.min(now()+25000,Date.parse(ticket.not_after));
      if(!Number.isFinite(deadline)||deadline-now()<100)throw new RelayError("CLAIM_REJECTED",409);
      let response;
      try {response=await fetcher(url,{method:"GET",headers:{Accept:"application/json","Accept-Encoding":"identity",Authorization:"Bearer "+sourceKey},
        redirect:"error",signal:AbortSignal.timeout(Math.max(1,deadline-now()))});}catch{throw new RelayError("SOURCE_TRANSPORT_ERROR");}
      if(response.url!==url || response.status>=300&&response.status<400 || ![null,"","identity"].includes(response.headers.get("content-encoding"))) {
        void response.body?.cancel().catch(()=>{});throw new RelayError("UNEXPECTED_SOURCE_TRANSPORT",409);
      }
      const headers={};
      for(const name of ["X-Request-ID","X-RateLimit-Limit","X-RateLimit-Remaining","X-RateLimit-Reset","Retry-After"]) {
        const value=response.headers.get(name);
        if(value!==null) {
          if(value.length>512||/[\x00-\x1f\x7f]/.test(value)||reflected(value,credentials)) {
            void response.body?.cancel().catch(()=>{});throw new RelayError("SOURCE_CREDENTIAL_ECHO",409);
          }
          headers[name]=value;
        }
      }
      let captured;
      try {captured=await boundedRead(response.body,MAX_BODY,deadline);}catch(error){throw error instanceof RelayError?error:new RelayError("SOURCE_TRANSPORT_ERROR");}
      // Check the entire captured prefix before any body bytes or headers leave this function.
      if(reflected(new TextDecoder().decode(captured.bytes),credentials))throw new RelayError("SOURCE_CREDENTIAL_ECHO",409);
      const returned=captured.complete?captured.bytes:captured.bytes.subarray(0,PREFIX);
      const result={protocol:RELAY_PROTOCOL,dispatch_id:dispatchId,request_sha256:requestHash,
        http_status:response.status,headers,fetched_at:new Date(now()).toISOString(),response_complete:captured.complete,
        body_base64:toBase64(returned),body_bytes:returned.length,body_sha256:await hash(returned)};
      if(!captured.complete)Object.assign(result,{read_limit_bytes:MAX_BODY,observed_prefix_bytes:captured.bytes.length,
        observed_prefix_sha256:await hash(captured.bytes)});
      return output(result);
    } catch(error) {
      const safe=error instanceof RelayError?error:new RelayError("RELAY_CONTROL_UNAVAILABLE");
      return output({error:safe.code,dispatch_consumed:dispatched?true:dispatchAttempted?null:false},safe.status);
    }
  };
}
