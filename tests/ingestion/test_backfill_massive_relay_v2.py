"""Native parsing and retry semantics over the authenticated managed-key relay."""
import base64
from hashlib import sha256
from http.client import IncompleteRead
import io
import json
import unittest
from urllib.error import URLError

from astra_ingestion.backfill_massive_relay_v2 import (
    EDGE_PATH, MAX_RELAY_RESPONSE_BYTES, MassiveRelay, PROTOCOL, ProviderWithManagedMassive)
from astra_ingestion.backfill_provider_v2 import (
    BackfillProvider, KINDS, MAX_BODY_BYTES, MAX_PARTIAL_BODY_BYTES, ProviderProblem, parse_response, request_for)
from astra_ingestion.rpc_store import PROJECT_URL
from astra_ingestion.store import LeaseLost

TOKEN='a'*64
PUBLIC='sb_publishable_fixturepublic123456789'
EDGE=PROJECT_URL+EDGE_PATH
RUN='fixed3000-20250901-20260731-v1-20261030'


def task(kind='massive_news',cursor=None,limit=100):
    return {'id':'relay-task','run_id':RUN,'owner':'existing-worker','generation':1,'run_fence':1,'page_no':0,
        'kind':kind,'provider':'Massive','family':'N01','page_limit':limit,'cursor':cursor,
        'scope':{'symbols':['AAPL'],'member_ids':['member-1'],'asof':'2025-09-01',
                 'start':'2025-09-01','end':'2025-09-30'}}


def envelope(t,raw=b'{"status":"OK","results":[]}',status=200,headers=None,complete=True):
    plan=request_for(t)
    body=raw if complete else raw[:MAX_PARTIAL_BODY_BYTES]
    result={'protocol':PROTOCOL,'dispatch_id':'afc5e4f5-9e55-4be2-b615-6eaa5e56778d',
        'request_sha256':sha256(json.dumps(plan,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest(),
        'http_status':status,'headers':headers or {},'fetched_at':'2026-10-30T09:00:00Z',
        'response_complete':complete,'body_base64':base64.b64encode(body).decode(),
        'body_bytes':len(body),'body_sha256':sha256(body).hexdigest()}
    if not complete:
        prefix=raw[:MAX_BODY_BYTES+1]
        result.update(read_limit_bytes=MAX_BODY_BYTES,observed_prefix_bytes=len(prefix),observed_prefix_sha256=sha256(prefix).hexdigest())
    return result


class Response(io.BytesIO):
    def __init__(self,data,status=200,headers=None,url=EDGE):
        super().__init__(data)
        self.status,self.url=status,url
        self.headers={'Content-Type':'application/json',**(headers or {})}

    def geturl(self): return self.url


class Opener:
    def __init__(self,*replies): self.replies=list(replies);self.calls=[]

    def open(self,request,timeout):
        self.calls.append((request,timeout))
        reply=self.replies.pop(0)
        if isinstance(reply,Exception): raise reply
        if isinstance(reply,Response): return reply
        return Response(json.dumps(reply,separators=(',',':')).encode())


def ready_relay(*replies):
    opener=Opener({'ready':True},*replies)
    relay=MassiveRelay(PROJECT_URL,PUBLIC,TOKEN,opener=opener)
    assert relay.probe()
    return relay,opener


class ManagedMassiveRelayTests(unittest.TestCase):
    def test_only_actual_authenticated_probe_advertises_massive_capability(self):
        direct=BackfillProvider('fixture-alpaca','fixture-secret')
        for reply,expected in [({'ready':True},True),({'ready':False},False),({'ready':'true'},False),
                               ({'ready':True,'key':'never-accepted'},False),(URLError('private details'),False)]:
            with self.subTest(reply=type(reply).__name__,expected=expected):
                opener=Opener(reply);relay=MassiveRelay(PROJECT_URL,PUBLIC,TOKEN,opener=opener)
                self.assertFalse(relay.ready)
                combined=ProviderWithManagedMassive(direct,relay)
                actual=combined.supported_kinds()
                self.assertEqual(any(kind.startswith('massive_') for kind in actual),expected)
                self.assertTrue(all(kind in actual for kind in direct.supported_kinds()))
                self.assertEqual(len(opener.calls),1)
                request,timeout=opener.calls[0]
                self.assertEqual(request.full_url,EDGE);self.assertEqual(request.method,'POST')
                self.assertEqual(json.loads(request.data),{'action':'probe'})
                headers={key.lower():value for key,value in request.header_items()}
                self.assertEqual(headers['apikey'],PUBLIC);self.assertEqual(headers['x-astra-ingestion-token'],TOKEN)
                self.assertEqual(headers['x-astra-replacement-relay'],PROTOCOL)
                self.assertNotIn('authorization',headers);self.assertEqual(timeout,35)

    def test_direct_provider_credentials_keep_the_existing_path_without_relay_probe(self):
        class Direct:
            def supported_kinds(self): return KINDS
            def require_credentials(self,t): return ('direct-require',t['kind'])
            def fetch(self,t): return ('direct-fetch',t['kind'])
        class NoRelay:
            def probe(self): raise AssertionError('Existing direct credential must keep its path')
        combined=ProviderWithManagedMassive(Direct(),NoRelay())
        self.assertEqual(combined.supported_kinds(),KINDS)
        self.assertEqual(combined.fetch(task()),('direct-fetch','massive_news'))
        self.assertEqual(combined.require_credentials(task()),('direct-require','massive_news'))

    def test_native_parser_and_exact_original_body_survive_the_relay(self):
        t=task();raw='{"status":"OK","results":[{"id":"news-1","title":"Unicode café 😀","tickers":["AAPL"],"published_utc":"2025-09-03T12:00:00Z"}]}\n'.encode()
        relay,opener=ready_relay(envelope(t,raw,headers={'X-Request-ID':'source-1'}))
        page=relay.fetch(t)
        expected=parse_response(t,request_for(t),raw.decode())
        self.assertEqual((page.records,page.next_cursor,page.quality),expected)
        self.assertEqual(page.raw_body,raw.decode());self.assertEqual(page.body_sha256,sha256(raw).hexdigest())
        self.assertEqual(page.request_id,'source-1')
        self.assertEqual(page.payload()['adapter_version'],'fixed3000-managed-massive-relay-v2.1')
        self.assertEqual(len(opener.calls),2)
        body=json.loads(opener.calls[-1][0].data)
        self.assertEqual(body['request'],request_for(t))
        self.assertEqual(body['claim'],{key:t[key] for key in ('id','run_id','owner','generation','run_fence','page_no')})
        self.assertNotIn('scope',body['claim'])

    def test_http_failures_preserve_native_code_and_retry_after_without_claiming_absence(self):
        t=task()
        for status,code,retry in [(429,'SOURCE_RATE_LIMIT',True),(403,'BLOCKED_EXTERNAL',False),(500,'SOURCE_HTTP_ERROR',True)]:
            with self.subTest(status=status):
                relay,opener=ready_relay(envelope(t,b'{"message":"provider error"}',status,{'Retry-After':'90000'}))
                with self.assertRaises(ProviderProblem) as caught: relay.fetch(t)
                error=caught.exception
                self.assertEqual((error.code,error.retryable,error.retry_after),(code,retry,90000))
                self.assertEqual(error.evidence['raw_body'],'{"message":"provider error"}')
                self.assertEqual(error.evidence['http_status'],status)
                self.assertNotIn('provider_absence',error.evidence);self.assertEqual(len(opener.calls),2)

    def test_oversize_has_native_adaptive_evidence_and_opaque_cursor_cannot_be_reduced(self):
        raw=b'x'*(MAX_BODY_BYTES+1)
        for cursor,limit,retry in [(None,100,True),('opaque-next',100,False),(None,1,False)]:
            with self.subTest(cursor=cursor,limit=limit):
                t=task(cursor=cursor,limit=limit);relay,_=ready_relay(envelope(t,raw,complete=False))
                with self.assertRaises(ProviderProblem) as caught: relay.fetch(t)
                error=caught.exception;e=error.evidence
                self.assertEqual((error.code,error.retryable,error.retry_after),('SOURCE_PAGE_TOO_LARGE',retry,2))
                self.assertIs(e['response_complete'],False);self.assertEqual(e['observed_prefix_bytes'],MAX_BODY_BYTES+1)
                self.assertEqual(base64.b64decode(e['partial_body_base64']),raw[:MAX_PARTIAL_BODY_BYTES])
                self.assertEqual(e['partial_body_sha256'],sha256(raw[:MAX_PARTIAL_BODY_BYTES]).hexdigest())
                self.assertNotIn('raw_body',e);self.assertNotIn('body_sha256',e);self.assertNotIn('next_cursor',e)

    def test_incomplete_rate_limit_does_not_lose_provider_deadline(self):
        t=task();relay,_=ready_relay(envelope(t,b'x'*(MAX_BODY_BYTES+1),429,{'Retry-After':'90000'},False))
        with self.assertRaises(ProviderProblem) as caught: relay.fetch(t)
        self.assertEqual((caught.exception.code,caught.exception.retry_after),('SOURCE_RATE_LIMIT',90000))
        self.assertFalse(caught.exception.evidence['response_complete'])

    def test_already_consumed_and_uncertain_transport_never_retry_the_same_ticket(self):
        t=task()
        errors=[Response(b'{"error":"DISPATCH_ALREADY_USED","dispatch_consumed":true}',409),
                Response(b'{"error":"RELAY_CONTROL_UNAVAILABLE","dispatch_consumed":null}',503),
                URLError('private detail '+TOKEN),IncompleteRead(b'partial '+TOKEN.encode())]
        for response in errors:
            with self.subTest(response=type(response).__name__):
                relay,opener=ready_relay(response)
                with self.assertRaises(ProviderProblem) as caught: relay.fetch(t)
                self.assertEqual(caught.exception.code,'SOURCE_TRANSPORT_ERROR')
                self.assertTrue(caught.exception.retryable);self.assertFalse(caught.exception.evidence['same_reservation_replay'])
                self.assertEqual(len(opener.calls),2)
                self.assertNotIn(TOKEN,str(caught.exception)+json.dumps(caught.exception.evidence))

    def test_lost_claim_stops_without_fabricating_a_source_error_or_retry(self):
        relay,opener=ready_relay(Response(b'{"error":"CLAIM_REJECTED","dispatch_consumed":null}',409))
        with self.assertRaises(LeaseLost): relay.fetch(task())
        self.assertEqual(len(opener.calls),2)

    def test_missing_managed_credential_is_an_authenticated_operational_dependency(self):
        opener=Opener({'ready':False});relay=MassiveRelay(PROJECT_URL,PUBLIC,TOKEN,opener=opener)
        with self.assertRaises(ProviderProblem) as caught: relay.require_credentials(task())
        self.assertEqual(caught.exception.code,'BLOCKED_EXTERNAL')
        self.assertEqual(caught.exception.evidence['dependency'],'MASSIVE_WORKER_CREDENTIAL')
        self.assertTrue(caught.exception.evidence['not_a_provider_limitation']);self.assertEqual(len(opener.calls),1)

    def test_envelope_corruption_fails_closed_before_native_parse_or_commit(self):
        t=task()
        mutations=[('protocol','other'),('request_sha256','0'*64),('body_sha256','f'*64),('body_bytes',1),
                   ('dispatch_id','no-ticket'),('body_base64','not-base64!'),('http_status',True),
                   ('headers',{'Authorization':'not-allowed'}),('headers',{'X-Request-ID':TOKEN}),
                   ('fetched_at','unknown'),('response_complete',1)]
        for field,value in mutations:
            with self.subTest(field=field):
                result=envelope(t);result[field]=value;relay,_=ready_relay(result)
                with self.assertRaises(ProviderProblem) as caught:relay.fetch(t)
                self.assertEqual(caught.exception.code,'SOURCE_RELAY_PROTOCOL_ERROR')
                self.assertNotIn(TOKEN,str(caught.exception)+json.dumps(caught.exception.evidence))
        result=envelope(t,TOKEN.encode());relay,_=ready_relay(result)
        with self.assertRaises(ProviderProblem) as caught:relay.fetch(t)
        self.assertEqual(caught.exception.code,'SOURCE_RELAY_PROTOCOL_ERROR')

    def test_malformed_source_is_retained_without_fabricating_records(self):
        t=task();raw=b'{"status":"OK","results":';relay,_=ready_relay(envelope(t,raw))
        with self.assertRaises(ProviderProblem) as caught:relay.fetch(t)
        self.assertEqual(caught.exception.code,'SOURCE_PARSE_ERROR')
        self.assertEqual(caught.exception.evidence['raw_body'],raw.decode())
        self.assertEqual(caught.exception.evidence['body_sha256'],sha256(raw).hexdigest())

    def test_invalid_utf8_never_creates_a_modified_body_with_the_original_hash(self):
        t=task();raw=b'{"status":"OK","results":[{"title":"invalid\xffbyte"}]}'
        relay,_=ready_relay(envelope(t,raw))
        with self.assertRaises(ProviderProblem) as caught:relay.fetch(t)
        e=caught.exception.evidence
        self.assertEqual(caught.exception.code,'SOURCE_PARSE_ERROR')
        self.assertEqual(e['source_body_sha256'],sha256(raw).hexdigest())
        self.assertEqual(e['source_body_bytes'],len(raw));self.assertTrue(e['response_complete'])
        self.assertFalse(e['full_raw_body_retained'])
        self.assertEqual(base64.b64decode(e['partial_body_base64']),raw)
        self.assertNotIn('raw_body',e);self.assertNotIn('body_sha256',e)
        relay,_=ready_relay(envelope(t,raw,429,{'Retry-After':'90000'}))
        with self.assertRaises(ProviderProblem) as limited:relay.fetch(t)
        self.assertEqual(limited.exception.code,'SOURCE_RATE_LIMIT');self.assertEqual(limited.exception.retry_after,90000)

    def test_gateway_redirect_compression_oversize_and_invalid_json_never_advertise_readiness(self):
        replies=[Response(b'{"ready":true}',url='https://other.invalid'),
                 Response(b'{"ready":true}',headers={'Content-Encoding':'gzip'}),
                 Response(b'{}',headers={'Content-Length':str(MAX_RELAY_RESPONSE_BYTES+1)}),
                 Response(b'{"ready":true,"ready":false}'),Response(b'{"ready":NaN}'),Response(b'not-json')]
        for response in replies:
            with self.subTest(url=response.url):
                opener=Opener(response);relay=MassiveRelay(PROJECT_URL,PUBLIC,TOKEN,opener=opener)
                self.assertFalse(relay.probe());self.assertEqual(relay.last_probe_state,'READINESS_UNCONFIRMED')
                self.assertEqual(len(opener.calls),1)

    def test_endpoint_and_key_admission_reject_other_origins_and_service_credentials(self):
        for url,key,token in [('https://other.supabase.co',PUBLIC,TOKEN),(PROJECT_URL,'sb_secret_no',TOKEN),
                              (PROJECT_URL,PUBLIC,'not-token')]:
            with self.assertRaises(ValueError):MassiveRelay(url,key,token)


if __name__=='__main__':unittest.main()
