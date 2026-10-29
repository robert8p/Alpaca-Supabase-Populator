"""Temporary read-only HTTPS gateway probe: never log credentials."""
import contextlib
from io import StringIO
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from astra_ingestion.worker import _qualification_gateway_probe

class _Settings:
    api_url = "https://oxzabweahkoimtevbbny.supabase.co"
    publishable_key = "sb_publishable_qualification_mock_key_123456"

class _Opener:
    def __init__(self):
        self.requests=[]
    def open(self,req,timeout):
        self.requests.append(req)
        self._status=(406,404,401)[len(self.requests)-1]
        raise HTTPError(req.full_url,self._status,"expected isolated test denial",{},None)

class GatewayQualificationUnitTests(unittest.TestCase):
    def test_only_anonymous_nonmutating_denial_probes_and_no_sensitive_logging(self):
        opener=_Opener()
        with patch("urllib.request.build_opener",return_value=opener), contextlib.redirect_stdout(StringIO()) as output:
            _qualification_gateway_probe(_Settings())
        result=json.loads(output.getvalue().strip())
        self.assertEqual(result["state"],"gateway_qualification_completed")
        self.assertEqual([x["denied"] for x in result["results"]],[True,True,True])
        self.assertEqual([x["http_status"] for x in result["results"]],[406,404,401])
        self.assertEqual(len(opener.requests),3)
        self.assertEqual(json.loads(opener.requests[2].data), {"operation": "health", "payload": {}})
        for req in opener.requests:
            self.assertEqual(req.get_method(),"POST")
            self.assertNotIn("X-astra-ingestion-token",dict(req.header_items()))
            self.assertNotIn("Authorization",dict(req.header_items()))
        self.assertNotIn(_Settings.publishable_key,output.getvalue())

if __name__=="__main__":
    unittest.main()
