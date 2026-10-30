import assert from 'node:assert/strict';
import {createHash, webcrypto} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import {createReplacementRelay, RELAY_PROTOCOL} from '../../supabase/functions/population-top3000-news-v1/replacement-relay-v2.mjs';

const PROJECT='https://oxzabweahkoimtevbbny.supabase.co';
const RPC=PROJECT+'/rest/v1/rpc/astra_ingestion_rpc_v1';
const EDGE=PROJECT+'/functions/v1/population-top3000-news-v1';
const RUN='fixed3000-20250901-20260731-v1-20261030';
const KEY='fixture-managed-key-never-export-12345';
const TOKEN='a'.repeat(64);
const PUBLIC='sb_publishable_fixturepublic123456789';
const NOW=Date.parse('2026-10-30T09:00:00Z');
const claim={id:'task-fixture',run_id:RUN,owner:'existing-worker',generation:1,run_fence:1,page_no:0};
const plan={provider:'Massive',host:'api.massive.com',path:'/v2/reference/news',method:'GET',params:{
  ticker:'AAPL','published_utc.gte':'2025-09-01','published_utc.lte':'2025-09-30',limit:100,sort:'published_utc',order:'asc'}};
const hash=value=>createHash('sha256').update(value).digest('hex');
const canonical=value=>typeof value==='string'?JSON.stringify(value).replace(/[\u007f-\uffff]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0')):
  value===null||typeof value!=='object'?JSON.stringify(value):Array.isArray(value)?'['+value.map(canonical).join(',')+']':
  '{'+Object.keys(value).sort().map(key=>canonical(key)+':'+canonical(value[key])).join(',')+'}';
function response(url,body,status=200,headers={}) {
  const result=new Response(body,{status,headers});
  Object.defineProperty(result,'url',{value:url});
  return result;
}
function harness(options={}) {
  const calls=[],envReads=[],spent=new Set();
  const environments={SUPABASE_URL:PROJECT,MASSIVE_API_KEY:KEY,...options.env};
  const env=name=>{envReads.push(name);return environments[name];};
  const fetch=async(url,init)=>{
    calls.push({url,init});
    if(url===RPC) {
      const body=JSON.parse(init.body);
      if(options.rejectAuth)return response(url,JSON.stringify({ok:false,error:{code:'conflict'}}));
      if(body.operation==='backfill_relay_probe')return response(url,JSON.stringify({ok:true,result:{state:'AUTHORIZED',protocol:RELAY_PROTOCOL,run_id:RUN}}));
      assert.equal(body.operation,'backfill_relay_dispatch');
      if(options.uncertainDispatch)throw Error(KEY+' private detail');
      if(options.rejectClaim)return response(url,JSON.stringify({ok:false,error:{code:'lease_lost'}}));
      const key=JSON.stringify(body.payload.claim);
      if(spent.has(key))return response(url,JSON.stringify({ok:true,result:{state:'ALREADY_DISPATCHED',provider_requested:false}}));
      spent.add(key);
      const ticket={state:'DISPATCH_AUTHORIZED',protocol:RELAY_PROTOCOL,dispatch_id:body.payload.dispatch_id,
        task_id:claim.id,run_id:RUN,generation:claim.generation,page_no:claim.page_no,
        request_sha256:hash(canonical(body.payload.request)),not_after:new Date(NOW+(options.ticketMs??25000)).toISOString(),...options.ticket};
      return response(url,JSON.stringify({ok:true,result:ticket}));
    }
    assert.equal(new URL(url).origin,'https://api.massive.com');
    if(options.providerThrow)throw Error(KEY+' private detail');
    const body=options.providerBody??'{"status":"OK","results":[]}';
    return response(options.providerUrl??url,body,options.providerStatus??200,options.providerHeaders??{});
  };
  const handler=createReplacementRelay({env,fetch,crypto:webcrypto,now:()=>NOW});
  const request=(body,headers={},method='POST')=>new Request(EDGE,{method,headers:{
    apikey:PUBLIC,'x-astra-ingestion-token':TOKEN,'x-astra-replacement-relay':RELAY_PROTOCOL,'content-type':'application/json',...headers},
    ...(method==='POST'?{body:typeof body==='string'?body:JSON.stringify(body)}:{})});
  const invoke=async(body={action:'probe'},headers={},method='POST')=>{const result=await handler(request(body,headers,method));
    return {status:result.status,body:await result.json(),headers:result.headers};};
  return {calls,envReads,spent,request,invoke,handler};
}
const fetchBody=()=>({action:'fetch',claim:structuredClone(claim),request:structuredClone(plan)});
const sourceCalls=h=>h.calls.filter(call=>call.url!==RPC);

test('normal old handler is byte-for-byte identical outside the explicit branch',async()=>{
  let text=await readFile(new URL('../../supabase/functions/population-top3000-news-v1/index.ts',import.meta.url),'utf8');
  for(const inserted of ['import { createReplacementRelay } from "./replacement-relay-v2.mjs";\n',
    'const replacementRelay = createReplacementRelay();\n',
    ' if(req.headers.has("x-astra-replacement-relay"))return await replacementRelay(req);\n']) {
    assert.equal(text.split(inserted).length,2);text=text.replace(inserted,'');
  }
  assert.equal(hash(text),'29269e3c092a3377e2ae329a3a193d87ef66dbf36655b040a8603719e9490dfe');
});

test('probe authenticates before managed key access and returns only a boolean',async()=>{
  const h=harness();const result=await h.invoke();
  assert.deepEqual(result.body,{ready:true});assert.equal(result.status,200);
  assert.equal(h.calls.length,1);assert.equal(JSON.parse(h.calls[0].init.body).operation,'backfill_relay_probe');
  assert.deepEqual(h.envReads,['SUPABASE_URL','MASSIVE_API_KEY']);
  assert.equal(h.calls[0].init.headers.apikey,PUBLIC);assert.equal(h.calls[0].init.headers['x-astra-ingestion-token'],TOKEN);
  assert.equal(h.calls[0].init.headers.authorization,undefined);assert.equal(h.calls[0].init.headers.Authorization,undefined);
  assert.equal(h.calls[0].init.redirect,'error');assert.ok(h.calls[0].init.signal instanceof AbortSignal);
  const missing=harness({env:{MASSIVE_API_KEY:undefined}});assert.deepEqual((await missing.invoke()).body,{ready:false});
});

test('unauthorized, service role, wrong project and invalid protocol never inspect provider secrets',async()=>{
  const h=harness({rejectAuth:true});assert.notEqual((await h.invoke()).status,200);
  assert.deepEqual(h.envReads,['SUPABASE_URL']);assert.equal(sourceCalls(h).length,0);
  const service='x.'+Buffer.from(JSON.stringify({role:'service_role',ref:'oxzabweahkoimtevbbny'})).toString('base64url')+'.x';
  for(const headers of [{apikey:'sb_secret_unapproved'},{apikey:service},{'x-astra-ingestion-token':'wrong'},
    {'x-astra-replacement-relay':'wrong'}]) {
    const a=harness();assert.notEqual((await a.invoke({action:'probe'},headers)).status,200);
    assert.equal(a.calls.length,0);assert.ok(!a.envReads.includes('MASSIVE_API_KEY'));
  }
  const wrong=harness({env:{SUPABASE_URL:'https://other.supabase.co'}});
  assert.equal((await wrong.invoke()).body.error,'PROJECT_MISMATCH');assert.equal(wrong.calls.length,0);
});

test('one authorized provider GET returns exact bounded body/hash and safe headers',async()=>{
  const raw='{"status":"OK","results":[{"title":"Unicode café 😀"}],"next_url":null}\n';
  const h=harness({providerBody:raw,providerHeaders:{'X-Request-ID':'fixture-1','Set-Cookie':'not-forwarded'}});
  const result=await h.invoke(fetchBody());
  assert.equal(result.status,200);assert.equal(result.body.response_complete,true);
  const bytes=Buffer.from(result.body.body_base64,'base64');assert.equal(bytes.toString(),raw);
  assert.equal(result.body.body_bytes,Buffer.byteLength(raw));assert.equal(result.body.body_sha256,hash(Buffer.from(raw)));
  assert.equal(result.body.request_sha256,hash(canonical(plan)));assert.deepEqual(result.body.headers,{'X-Request-ID':'fixture-1'});
  assert.equal(h.calls.length,3);assert.equal(sourceCalls(h).length,1);
  const request=sourceCalls(h)[0];assert.equal(request.init.method,'GET');assert.equal(request.init.redirect,'error');
  assert.equal(request.init.headers.Authorization,'Bearer '+KEY);assert.ok(!request.url.includes(KEY));
  assert.equal(request.init.headers['x-astra-ingestion-token'],undefined);
  assert.equal(result.headers.get('cache-control'),'no-store');
});

test('same reservation replay is refused without a second provider dispatch',async()=>{
  const h=harness();assert.equal((await h.invoke(fetchBody())).status,200);
  const repeated=await h.invoke(fetchBody());
  assert.equal(repeated.status,409);assert.deepEqual(repeated.body,{error:'DISPATCH_ALREADY_USED',dispatch_consumed:true});
  assert.equal(sourceCalls(h).length,1);
});

test('dispatch acknowledgment uncertainty never contacts provider or claims unconsumed',async()=>{
  const h=harness({uncertainDispatch:true});const result=await h.invoke(fetchBody());
  assert.deepEqual(result.body,{error:'RELAY_CONTROL_UNAVAILABLE',dispatch_consumed:null});
  assert.equal(sourceCalls(h).length,0);assert.equal(h.calls.length,2);assert.ok(!JSON.stringify(result.body).includes(KEY));
});

test('stale reservation, changed ticket hash or exhausted dispatch lifetime prevents provider GET',async()=>{
  for(const options of [{rejectClaim:true},{ticket:{request_sha256:'0'.repeat(64)}},{ticketMs:50}]) {
    const h=harness(options);const result=await h.invoke(fetchBody());
    assert.notEqual(result.status,200);assert.equal(sourceCalls(h).length,0);
  }
});

test('request host, path, method, query and run cannot become an arbitrary relay',async()=>{
  const cases=[['host','attacker.invalid'],['path','/v2/aggs/ticker/AAPL/prev'],['method','POST'],['provider','Alpaca']];
  for(const [field,value] of cases) {
    const body=fetchBody();body.request[field]=value;const h=harness();
    assert.equal((await h.invoke(body)).body.error,'REQUEST_REJECTED');assert.equal(h.calls.length,0);
  }
  for(const mutate of [body=>body.request.params.apiKey='injected',body=>body.request.params.limit=1001,
    body=>body.request.params.cursor='control\nvalue',body=>body.claim.run_id='other',body=>body.request.path='/v3/reference/tickers/AAPL/../../private']) {
    const body=fetchBody();mutate(body);const h=harness();assert.notEqual((await h.invoke(body)).status,200);assert.equal(h.calls.length,0);
  }
});

test('all six allowlisted native endpoint shapes dispatch read-only and canonical cursors agree',async()=>{
  for(const path of ['/v3/reference/tickers/BRK%2FB','/v2/reference/news','/stocks/v1/dividends','/stocks/v1/splits',
    '/stocks/v1/short-volume','/stocks/v1/short-interest']) {
    const body=fetchBody();body.request.path=path;body.request.params={ticker:'AAPL',cursor:'opaque+token/==é😀'};
    const h=harness();assert.equal((await h.invoke(body)).status,200);assert.equal(sourceCalls(h).length,1);
    assert.equal(new URL(sourceCalls(h)[0].url).searchParams.get('cursor'),'opaque+token/==é😀');
  }
});

test('HTTP source failure preserves exact status, body and a long Retry-After',async()=>{
  const h=harness({providerStatus:429,providerBody:'{"status":"ERROR","message":"rate limited"}',providerHeaders:{'Retry-After':'90000'}});
  const result=await h.invoke(fetchBody());assert.equal(result.status,200);assert.equal(result.body.http_status,429);
  assert.equal(result.body.headers['Retry-After'],'90000');assert.equal(result.body.response_complete,true);
  assert.equal(sourceCalls(h).length,1);
});

test('oversize source exposes a hashed incomplete prefix with no invented completion',async()=>{
  const raw='x'.repeat(3*1024*1024+100);const h=harness({providerBody:raw});
  const result=await h.invoke(fetchBody());assert.equal(result.status,200);assert.equal(result.body.response_complete,false);
  assert.equal(result.body.body_bytes,16384);assert.equal(result.body.body_sha256,hash('x'.repeat(16384)));
  assert.equal(result.body.observed_prefix_bytes,3145729);assert.equal(result.body.observed_prefix_sha256,hash(raw.slice(0,3145729)));
  assert.equal(result.body.read_limit_bytes,3145728);assert.equal(result.body.next_cursor,undefined);
});

test('literal, percent, JSON-escaped, base64, header and late-prefix credential echoes are withheld',async()=>{
  for(const raw of [KEY,TOKEN,KEY.split('').map(c=>'%'+c.charCodeAt(0).toString(16)).join(''),
    KEY.split('').map(c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0')).join(''),Buffer.from(KEY).toString('base64'),
    'x'.repeat(20000)+KEY,'x'.repeat(3000000)+KEY]) {
    const h=harness({providerBody:raw});const result=await h.invoke(fetchBody());
    assert.equal(result.body.error,'SOURCE_CREDENTIAL_ECHO');assert.equal(result.body.dispatch_consumed,true);
    assert.ok(!JSON.stringify(result.body).includes(KEY));assert.equal(result.body.body_base64,undefined);
  }
  const h=harness({providerHeaders:{'X-Request-ID':KEY}});assert.equal((await h.invoke(fetchBody())).body.error,'SOURCE_CREDENTIAL_ECHO');
});

test('redirects, compression and provider transport uncertainty are redacted without retry',async()=>{
  for(const options of [{providerStatus:302},{providerUrl:'https://other.invalid/redirect'},{providerHeaders:{'content-encoding':'gzip'}},
    {providerThrow:true}]) {
    const h=harness(options);const result=await h.invoke(fetchBody());assert.notEqual(result.status,200);
    assert.equal(result.body.dispatch_consumed,true);assert.equal(sourceCalls(h).length,1);assert.ok(!JSON.stringify(result.body).includes(KEY));
  }
});

test('normal JSON escapes cannot reflect accepted punctuation keys or escaped worker tokens',async()=>{
  const punctuated='fixture/quoted"key\\secret12345';
  for(const body of [JSON.stringify({message:punctuated}),JSON.stringify({message:punctuated}).replaceAll('/','\\/'),
    JSON.stringify({message:punctuated}).replaceAll('f','\\u0066')]) {
    const h=harness({env:{MASSIVE_API_KEY:punctuated},providerBody:body});
    const result=await h.invoke(fetchBody());assert.equal(result.body.error,'SOURCE_CREDENTIAL_ECHO');
    assert.equal(result.body.body_base64,undefined);assert.equal(result.body.dispatch_consumed,true);
  }
  const body='{"message":"'+TOKEN.slice(0,20)+'\\u0061'+TOKEN.slice(21)+'"}';
  const h=harness({providerBody:body});assert.equal((await h.invoke(fetchBody())).body.error,'SOURCE_CREDENTIAL_ECHO');
  for(const suffix of ['test','back','next','u0061','percent%41']) {
    const key='fixture\\'+suffix+'-secret12345';
    const escaped=JSON.stringify({message:key}).replaceAll('\\\\','\\u005c').replaceAll('%','\\u0025');
    assert.equal(JSON.parse(escaped).message,key);
    const checked=harness({env:{MASSIVE_API_KEY:key},providerBody:escaped});
    assert.equal((await checked.invoke(fetchBody())).body.error,'SOURCE_CREDENTIAL_ECHO');
  }
});

test('provider stream deadline cancels a stalled pure read and never retries its ticket',async()=>{
  let canceled=false;
  const body=new ReadableStream({pull(){return new Promise(()=>{});},cancel(){canceled=true;}});
  const h=harness({providerBody:body,ticketMs:120});const result=await h.invoke(fetchBody());
  assert.equal(result.body.error,'SOURCE_READ_TIMEOUT');assert.equal(result.body.dispatch_consumed,true);
  assert.equal(sourceCalls(h).length,1);assert.equal(canceled,true);
});

test('oversized or malformed input and wrong method cannot enter original pipeline or RPC',async()=>{
  for(const [body,headers,method] of [['x'.repeat(65537),{},'POST'],['{',{},'POST'],[{action:'probe',extra:true},{},'POST'],
    [{action:'probe'},{'content-type':'text/plain'},'POST'],[{}, {},'GET']]) {
    const h=harness();assert.notEqual((await h.invoke(body,headers,method)).status,200);assert.equal(h.calls.length,0);
  }
});
