import io
import json
import unittest
from astra_ingestion.backfill_provider_v2 import BackfillProvider, ProviderProblem, parse_response, request_for


def task(kind="alpaca_stock_bars", **scope):
    return {"kind":kind,"scope":{"symbols":["AAPL"],"start":"2025-11-28T09:00:00Z",
            "end":"2025-11-29T00:59:59Z","timeframe":"1Min","adjustment":"raw",
            "calendar":[{"date":"2025-11-28","open":"09:30","close":"13:00"}],**scope},"cursor":None}


def bar(t="2025-11-28T18:00:00Z"):
    return {"t":t,"o":100,"h":102,"l":99,"c":101,"v":120,"n":4,"vw":100.5}


class Response(io.BytesIO):
    def __init__(self, url, data, status=200, headers=None):
        super().__init__(data.encode())
        self.url,self.status,self.headers=url,status,headers or {"Content-Type":"application/json"}
    def geturl(self):
        return self.url


class Opener:
    def __init__(self, data, status=200):
        self.data,self.status,self.calls=data,status,[]
    def open(self, req, timeout):
        self.calls.append(req)
        return Response(req.full_url,self.data,self.status)


class BackfillProviderTests(unittest.TestCase):
    def test_early_close_and_extended_session_share_source(self):
        t=task()
        rows,token,_=parse_response(t,request_for(t),json.dumps({"bars":{"AAPL":[bar("2025-11-28T17:59:00Z"),bar()]},"next_page_token":None}))
        self.assertEqual([r["session"] for r in rows],["RTH","POST"])
        self.assertIsNone(token)
        self.assertEqual(request_for(t)["params"]["feed"],"sip")

    def test_missing_optional_fields_are_retained_with_reasons(self):
        t=task();b=bar();del b["n"];del b["vw"]
        rows,_,_=parse_response(t,request_for(t),json.dumps({"bars":{"AAPL":[b]},"next_page_token":None}))
        self.assertEqual(rows[0]["missing_fields"],["n","vw"])
        self.assertNotIn("n",rows[0]["source"])

    def test_quality_and_identity_uncertainty_does_not_discard_raw(self):
        t=task();b=bar();b["h"]=50
        rows,_,_=parse_response(t,request_for(t),json.dumps({"bars":{"OLD":[b]},"next_page_token":None}))
        self.assertEqual(rows[0]["source"],b)
        self.assertIn("INVALID_OHLC_RELATION",rows[0]["quality_reasons"])
        self.assertIn("UNREQUESTED_PROVIDER_SYMBOL",rows[0]["quality_reasons"])

    def test_empty_nonterminal_page_requires_continuation(self):
        t=task()
        rows,cursor,_=parse_response(t,request_for(t),'{"bars":{},"next_page_token":"continue"}')
        self.assertEqual(rows,())
        self.assertEqual(cursor,"continue")
        with self.assertRaises(ValueError):
            parse_response(t,request_for(t),'{"bars":{}}')

    def test_historical_contract_enumeration_explicitly_includes_inactive(self):
        t=task("alpaca_option_contracts",status="inactive")
        q=request_for(t)["params"]
        self.assertEqual(q["status"],"inactive")
        self.assertEqual(q["expiration_date_gte"],"2025-09-01")
        self.assertEqual(q["expiration_date_lte"],"2099-12-31")
        self.assertEqual(q["show_deliverables"],"true")
        with self.assertRaises(ProviderProblem):
            request_for(task("alpaca_option_contracts"))

    def test_continuation_is_bound_to_original_endpoint(self):
        t=task("massive_news");p=request_for(t)
        body={"status":"OK","results":[],"next_url":"https://attacker.invalid/v2/reference/news?cursor=x"}
        with self.assertRaises(ValueError):
            parse_response(t,p,json.dumps(body))
        body["next_url"]="https://api.polygon.io/v2/reference/news?cursor=abc"
        self.assertEqual(parse_response(t,p,json.dumps(body))[1],"abc")
        t["cursor"]="abc"
        with self.assertRaises(ValueError):
            parse_response(t,p,json.dumps(body))

    def test_short_interest_does_not_invent_publication_time(self):
        t=task("massive_short_interest")
        rows,_,_=parse_response(t,request_for(t),json.dumps({"status":"OK","results":[{"ticker":"AAPL","settlement_date":"2026-07-31","short_interest":10}]}))
        self.assertIsNone(rows[0]["publication_time"])
        self.assertEqual(rows[0]["settlement_date"],"2026-07-31")

    def test_action_boundary_dates_are_preserved_separately(self):
        t=task("massive_dividends")
        source={"ticker":"AAPL","declaration_date":"2026-07-30","ex_dividend_date":"2026-08-14","pay_date":"2026-08-21"}
        rows,_,_=parse_response(t,request_for(t),json.dumps({"status":"OK","results":[source]}))
        self.assertEqual(rows[0]["source"],source)
        self.assertNotIn("ex_dividend_date.lte",request_for(t)["params"])

    def test_forbidden_is_operational_not_claimed_entitlement_gap(self):
        o=Opener('{"message":"forbidden"}',403)
        with self.assertRaises(ProviderProblem) as caught:
            BackfillProvider("key","secret",opener=o).fetch(task())
        self.assertEqual(caught.exception.code,"BLOCKED_EXTERNAL")
        self.assertEqual(caught.exception.evidence["http_status"],403)
        self.assertIn("raw_body",caught.exception.evidence)
        self.assertNotIn("key",json.dumps(caught.exception.evidence))

    def test_bad_json_retained_for_repair(self):
        with self.assertRaises(ProviderProblem) as caught:
            BackfillProvider("key","secret",opener=Opener('{"bars":')).fetch(task())
        self.assertEqual(caught.exception.code,"SOURCE_PARSE_ERROR")
        self.assertEqual(caught.exception.evidence["raw_body"],'{"bars":')

    def test_missing_massive_credential_does_not_send_or_claim_no_data(self):
        o=Opener('{}')
        with self.assertRaises(ProviderProblem) as caught:
            BackfillProvider("key","secret",opener=o).fetch(task("massive_short_volume"))
        self.assertEqual(caught.exception.code,"BLOCKED_EXTERNAL")
        self.assertEqual(len(o.calls),0)

    def test_news_cannot_silently_drop_requested_symbols(self):
        with self.assertRaises(ProviderProblem):
            request_for(task("massive_news",symbols=["AAPL","MSFT"]))


if __name__ == "__main__":
    unittest.main()
