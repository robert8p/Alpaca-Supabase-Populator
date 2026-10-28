import unittest
from unittest.mock import patch
from astra_ingestion.config import Settings

REF="oxzabweahkoimtevbbny"
ENV={"ASTRA_INGESTION_API_URL":f"https://{REF}.supabase.co", "ASTRA_INGESTION_PUBLISHABLE_KEY":"sb_publishable_"+"a"*32,
     "ASTRA_INGESTION_RPC_TOKEN":"a"*64,
     "ASTRA_INGESTION_PROJECT_REF":REF,"ASTRA_INGESTION_PASSWORD":"x"*32}
class ConfigurationTests(unittest.TestCase):
    def test_production_target_binding_is_explicit(self):
        with patch.dict("os.environ", ENV, clear=True):
            self.assertFalse(Settings.from_env().test_mode)
        with patch.dict("os.environ", {**ENV,"ASTRA_INGESTION_PROJECT_REF":"mnmkxjirpwbptdnvjmpw"}, clear=True):
            with self.assertRaises(ValueError):Settings.from_env()
    def test_connection_identity_overrides_are_rejected(self):
        for url in (f"https://{REF}.supabase.co?host=other.invalid",f"https://user:password@{REF}.supabase.co",f"https://{REF}.supabase.co:443",f"https://{REF}.supabase.co/rest/v1",f"http://{REF}.supabase.co"):
            with patch.dict("os.environ", {**ENV,"ASTRA_INGESTION_API_URL":url},clear=True):
                with self.assertRaises(ValueError):Settings.from_env()
    def test_production_refuses_direct_database_and_privileged_api_credentials(self):
        for changes in ({"ASTRA_INGESTION_DATABASE_URL":f"postgresql://admin:example@db.{REF}.supabase.co/postgres"},
                        {"ASTRA_INGESTION_PUBLISHABLE_KEY":"sb_secret_"+"x"*32},
                        {"ASTRA_INGESTION_RPC_TOKEN":"short"}):
            with patch.dict("os.environ",{**ENV,**changes},clear=True):
                with self.assertRaises(ValueError):Settings.from_env()
    def test_test_mode_does_not_admit_remote_postgres(self):
        with patch.dict("os.environ",{"ASTRA_INGESTION_TEST_MODE":"1","ASTRA_INGESTION_DATABASE_URL":f"postgresql://admin:example@db.{REF}.supabase.co/postgres"},clear=True):
            with self.assertRaises(ValueError):Settings.from_env()
    def test_settings_repr_does_not_reveal_capability(self):
        with patch.dict("os.environ",ENV,clear=True):
            value=repr(Settings.from_env())
            self.assertNotIn(ENV["ASTRA_INGESTION_RPC_TOKEN"],value)
            self.assertNotIn(ENV["ASTRA_INGESTION_PUBLISHABLE_KEY"],value)
    def test_deleted_or_test_targets_are_not_defaults(self):
        for ref in ("","xdponktobhosycdhbcrr","syokddbfiecauakwqygv"):
            with patch.dict("os.environ", {**ENV,"ASTRA_INGESTION_PROJECT_REF":ref},clear=True):
                with self.assertRaises(ValueError):Settings.from_env()
    def test_worker_does_not_need_web_password(self):
        env={key:value for key,value in ENV.items() if key!="ASTRA_INGESTION_PASSWORD"}
        with patch.dict("os.environ",env,clear=True):
            self.assertEqual(Settings.from_env(require_web_auth=False).password,"")
            with self.assertRaises(ValueError):Settings.from_env()
    def test_sqlite_requires_explicit_test_mode(self):
        with patch.dict("os.environ",{"ASTRA_INGESTION_DATABASE_URL":"sqlite:////tmp/qualification.db"},clear=True):
            with self.assertRaises(ValueError):Settings.from_env()
        with patch.dict("os.environ",{"ASTRA_INGESTION_DATABASE_URL":"sqlite:////tmp/qualification.db","ASTRA_INGESTION_TEST_MODE":"1"},clear=True):
            self.assertTrue(Settings.from_env().test_mode)

if __name__=="__main__":unittest.main()
