"""Synthetic contract fixtures. No original prices, database, or provider access."""
import copy
import json
from decimal import Decimal
import unittest
from unittest.mock import patch
import uuid

from astra_ingestion import aug_d02_pilot as p


class PilotContract(unittest.TestCase):
    def setUp(self):
        self.ms, self.raw, self.dest, self.observations = [], [], [], []
        for i in range(1, 11):
            ticker = f"XX{i}"
            bar = '{"T":"' + ticker + '","t":1785873600000,"o":9,"h":11,"l":8,"c":10,"v":9007199254740993.000001,"vw":9.6,"n":11}'
            digest = p.sha(bar.encode())
            member = dict(ordinal=i, company_id=f"CIK:{i:010d}", ticker=ticker,
                composite_figi=f"BBG{i:09d}", share_class_figi=f"BBG{100+i:09d}", issue_type="CS",
                exchange_mic="XNAS", source_row=100+i, raw_record_sha256=digest,
                identity_source_sha256="f"*64, identity_record_sha256="d"*64)
            self.ms.append(member)
            self.raw.append(dict(source_row=100+i, raw_record_text=bar))
            self.dest.append(dict(member, session_date=p.TRADE_DATE, verified=True, source_sha256=p.SOURCE_SHA,
                raw_close=10, raw_volume=Decimal("9007199254740993.000001"), effective_role=p.VERIFIER_ROLE))
            self.observations.append(dict(rank=i,source_row=100+i,source_ticker=ticker,source_sha256=p.SOURCE_SHA,
                actual_sha=p.SOURCE_SHA,body_status="OK",adjusted=False,
                source_uri="https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/2026-08-04?adjusted=false&include_otc=false",
                response_bytes=5000,actual_bytes=5000,actual_count=123,result_count=123,results_count=123,query_count=123,
                raw_record_sha256=digest,archive_record_sha256=digest,actual_record_sha256=digest,source_rows=1,
                provider_ny_date=p.TRADE_DATE,source_presence_state="PRESENT_SINGLE",point_source_state="VERIFIED_POINT_AND_SOURCE_LINK",
                anchor_identity_record_sha256="d"*64,anchor_identity_source_sha256="f"*64,raw_jsonb_text=bar))
        self.manifest = dict(schema=p.SCHEMA, date=p.TRADE_DATE, cohort_sha256=p.COHORT_SHA,
                             source_sha256=p.SOURCE_SHA,members=self.ms)
        patcher = patch.object(p,"ORDERED_COMPANIES_SHA",p.sha(p.canonical([m["company_id"] for m in self.ms]).encode()))
        patcher.start(); self.addCleanup(patcher.stop)
        self.pin = p.sha(p.manifest_text(self.manifest).encode())
        patcher = patch.object(p,"APPROVED_MANIFEST_SHA",self.pin)
        patcher.start(); self.addCleanup(patcher.stop)
        self.attempt = uuid.uuid5(uuid.NAMESPACE_URL,"urn:astra:aug-d02-pilot:" + self.pin)
        for row in self.dest:
            row.update(attempt=self.attempt,manifest_sha=self.pin)
        self.projection=dict(source_sha256=p.SOURCE_SHA,date=p.TRADE_DATE,rows=self.raw)

    def verify(self, rows):
        return p.verify_rows(self.manifest,self.pin,self.attempt,self.projection,rows)

    def test_precise_price_readback(self):
        self.assertEqual(self.verify(self.dest)["verified"], 10)
        self.assertEqual(p.prepare_projection(self.observations,self.manifest),self.projection)
        rows=copy.deepcopy(self.dest)
        rows[0]["raw_volume"] -= Decimal("0.000001")
        with self.assertRaises(p.PilotError):self.verify(rows)

    def test_missing_duplicate_or_extra_target(self):
        for rows in (self.dest[:-1],self.dest+[self.dest[0]],self.dest[:-1]+[self.dest[0]]):
            with self.subTest(length=len(rows)), self.assertRaises(p.PilotError):self.verify(rows)

    def test_cross_attempt_or_wrong_owner_or_date(self):
        for field,value in (("attempt",uuid.uuid4()),("manifest_sha","9"*64),("effective_role","writer"),
                            ("session_date","2026-08-03"),("verified",False),("share_class_figi","BBG999999999"),
                            ("source_row",2),("ordinal",2),("raw_close",10.0)):
            with self.subTest(field=field):
                rows=copy.deepcopy(self.dest);rows[0][field]=value
                with self.assertRaises(p.PilotError):self.verify(rows)

    def test_manifest_rejects_unknown_rank_or_instrument(self):
        for field,value in (("ordinal",7),("company_id","CIK:0000005999"),("ticker","XX2"),("composite_figi",""),("source_row",True)):
            with self.subTest(field=field):
                doc=copy.deepcopy(self.manifest);doc["members"][0][field]=value
                with self.assertRaises(p.PilotError):p.manifest_text(doc)
        with self.assertRaises(p.PilotError): p.admission_text(self.manifest,self.pin,uuid.uuid4())

    def test_archive_missing_tampered_or_duplicate(self):
        for rows in (self.raw[1:],self.raw[:-1]+[self.raw[0]],
                     [dict(self.raw[0],raw_record_text=self.raw[0]["raw_record_text"]+" ")]+self.raw[1:]):
            with self.subTest(length=len(rows)), self.assertRaises(p.PilotError):
                p.source_values(self.ms,dict(self.projection,rows=rows))

    def test_source_document_requires_native_scope_and_digest(self):
        for k,v in (("adjusted",True),("source_rows",2),("actual_sha","0"*64),("query_count",0),
                    ("actual_bytes",0),("source_uri","https://example.com"),("anchor_identity_record_sha256","1"*64)):
            with self.subTest(k=k):
                items=copy.deepcopy(self.observations);items[0][k]=v
                with self.assertRaises(p.PilotError): p.prepare_projection(items,self.manifest)

    def test_source_key_date_and_price_integrity(self):
        for k,v in (("T","XX2"),("t",1785787200000),("c",20),("v",-1),("n",True)):
            rawrows=copy.deepcopy(self.raw);ms=copy.deepcopy(self.ms);item=json.loads(rawrows[0]["raw_record_text"])
            item[k]=v;rawrows[0]["raw_record_text"]=json.dumps(item);ms[0]["raw_record_sha256"]=p.sha(rawrows[0]["raw_record_text"].encode())
            with self.subTest(k=k),self.assertRaises(p.PilotError):p.source_values(ms, dict(self.projection,rows=rawrows))

    def test_json_rejects_duplicated_fields_and_nonfinite_values(self):
        for data in ('{"v":1,"v":2}', '{"v":Infinity}', '{"v":NaN}'):
            with self.subTest(data=data),self.assertRaises(p.PilotError):p.parse(data)

    def retained_packet(self):
        rows = []
        for m in self.ms:
            company = m["company_id"]
            scope = dict(company_id=company, cohort_sha256=p.COHORT_SHA, membership_acceptance_sha256=p.ACCEPTANCE_SHA)
            membership = dict(scope, selection_order=m["ordinal"], membership_accepted=True, anchor_observation_date="2026-08-03",
                anchor_ticker=m["ticker"],anchor_exchange=m["exchange_mic"],anchor_security_type=m["issue_type"],
                anchor_composite_figi=m["composite_figi"],anchor_share_class_figi=m["share_class_figi"])
            src = dict(cik=company[4:], ticker=m["ticker"], primary_exchange=m["exchange_mic"], type=m["issue_type"],
                composite_figi=m["composite_figi"],share_class_figi=m["share_class_figi"],locale="us",market="stocks",
                currency_name="usd",active=True)
            point = dict(scope, point_date=p.TRADE_DATE, identity_state="FROZEN_ANCHOR_TICKER_AND_TWO_FIGI_MATCH",
                source_id="synthetic-page",source_sha256=m["identity_source_sha256"],source_ordinal=m["ordinal"])
            identity = dict(company_id=company,point_date=p.TRADE_DATE,source_id=point["source_id"],ordinal=m["ordinal"],
                identity_state=point["identity_state"],record_sha256=m["identity_record_sha256"],content=dict(point,source_record=src))
            x = dict(company_id=company,point_date=p.TRADE_DATE,ticker=m["ticker"],content=dict(point,ticker=m["ticker"],
                evidence_semantics="STRONG_IDENTIFIER_MATCHED_VENDOR_DATE_POINT_NOT_INTERVAL",
                source_record_sha256=m["identity_record_sha256"]))
            price = dict(source_row=m["source_row"],source_ticker=m["ticker"],source_day_id=1,provider_ny_date=p.TRADE_DATE,
                raw_record_sha256=m["raw_record_sha256"],invalid_mask=0,missing_mask=0,structure_mask=0)
            rows.append(dict(rank=m["ordinal"],member=membership,identity=identity,identity_crosswalk=x,price=price))
        return dict(asof_date=p.TRADE_DATE,capture="top3000-augsep2026-retained-scope-v1",rows=rows,
            archive=dict(source_sha256=p.SOURCE_SHA,session_date=p.TRADE_DATE,result_count=20,verified_source_records=20,
                         source_day_id=1,source_summary=dict(source_records_reconciled=True)))

    def test_dated_identity_and_frozen_scope(self):
        packet = self.retained_packet()
        self.assertEqual(p.prepare_manifest(packet), self.manifest)
        for fields, replacement in ((("identity","point_date"),"2026-08-03"),(("member","membership_accepted"),False),
                (("identity_crosswalk","content","source_record_sha256"),"e"*64),
                (("identity","content","source_record","cik"),"0000000444"),
                (("identity","content","source_record","active"),False),
                (("identity","content","source_record","type"),"ETF"),(("price","missing_mask"),2)):
            with self.subTest(fields=fields):
                changed = copy.deepcopy(packet)
                entry = changed["rows"][0]
                for field in fields[:-1]:
                    entry = entry[field]
                entry[fields[-1]] = replacement
                with self.assertRaises(p.PilotError):p.prepare_manifest(changed)
