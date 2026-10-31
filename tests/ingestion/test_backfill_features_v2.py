from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import json
import math
from statistics import mean, stdev
import unittest
from zoneinfo import ZoneInfo

from astra_ingestion.backfill_features_v2 import derive_family, FORMULA_MANIFEST


def calendar_days(n):
    result, day = [], date(2025, 6, 2)
    while len(result)<n:
        if day.weekday()<5:
            result.append({"date":day.isoformat(),"open":"09:30","close":"16:00"})
        day+=timedelta(days=1)
    return result


def daily_fixture(n=61, *, identity=True):
    sessions=calendar_days(n)
    rows=[]
    for i,entry in enumerate(sessions):
        for adjustment in ("raw","split"):
            factor=1 if adjustment=="raw" else .5
            c=(100+i)*factor
            v=(100+i)/factor
            rows.append({"symbol":"AAA","market_date":entry["date"],"timeframe":"1Day",
                         "timestamp":entry["date"]+"T04:00:00Z","session":"DAILY","feed":"sip",
                         "adjustment":adjustment,"identity_anchor":"share-class-aaa" if identity else None,
                         "source":{"o":c,"h":c+factor,"l":c-factor,"c":c,"v":v,"n":20,"vw":c}})
    return sessions,rows


def minutes(day="2025-09-02",n=25):
    start=datetime.fromisoformat(day+"T09:30:00").replace(tzinfo=ZoneInfo("America/New_York"))
    close=start+timedelta(minutes=n)
    session={"date":day,"open":"09:30","close":close.strftime("%H:%M")}
    rows=[]
    for i in range(n):
        c=100+i
        rows.append({"symbol":"AAA","market_date":day,"timeframe":"1Min","session":"RTH",
                     "timestamp":(start+timedelta(minutes=i)).isoformat(),"adjustment":"raw","feed":"sip",
                     "source":{"o":c-.5,"h":c+1,"l":c-1,"c":c,"v":i+1,"n":3,"vw":c-.25}})
    return session,rows


class BackfillFeatureTests(unittest.TestCase):
    def daily(self,family,rows,sessions):
        day=sessions[-1]["date"]
        return derive_family(family,rows,sessions=sessions,target_start=day,target_end=day,member_id="company-aaa")["rows"][0]

    def test_exact_sixty_session_return_and_no_double_adjustment(self):
        sessions,rows=daily_fixture()
        output=self.daily("D03",rows,sessions)
        self.assertAlmostEqual(output["values"]["raw_ret_60d"],.6)
        self.assertAlmostEqual(output["values"]["adjusted_ret_60d"],.6)
        self.assertAlmostEqual(output["values"]["provider_split_ret_60d"],.6)
        self.assertEqual(output["member_id"],"company-aaa")
        self.assertFalse(output["support_history"])

    def test_missing_calendar_observation_is_not_compressed(self):
        sessions,rows=daily_fixture()
        missing=sessions[30]["date"]
        rows=[r for r in rows if r["market_date"]!=missing]
        output=self.daily("D03",rows,sessions)
        self.assertIsNone(output["values"]["raw_ret_60d"])
        self.assertEqual(output["null_reasons"]["raw_ret_60d"],"MISSING_REQUIRED_SCHEDULED_INPUT")
        self.assertAlmostEqual(output["values"]["raw_ret_5d"],160/155-1)

    def test_identity_unknown_retains_raw_and_provider_variant(self):
        sessions,rows=daily_fixture(identity=False)
        output=self.daily("D03",rows,sessions)
        self.assertAlmostEqual(output["values"]["raw_ret_20d"],160/140-1)
        self.assertAlmostEqual(output["values"]["provider_split_ret_20d"],160/140-1)
        self.assertIsNone(output["values"]["adjusted_ret_20d"])
        self.assertEqual(output["null_reasons"]["adjusted_ret_20d"],"IDENTITY_CONTINUITY_UNRESOLVED")

    def test_daily_volume_excludes_current_and_uses_sample_sd(self):
        sessions,rows=daily_fixture()
        last=sessions[-1]["date"]
        for r in rows:
            if r["market_date"]==last:
                r["source"]["v"]=10000 if r["adjustment"]=="raw" else 20000
        output=self.daily("D04",rows,sessions)["values"]
        prior=[2*(100+i) for i in range(40,60)]
        self.assertAlmostEqual(output["relative_volume_20d"],20000/mean(prior))
        self.assertAlmostEqual(output["volume_z20"],(20000-mean(prior))/stdev(prior))
        logs=[math.log((100+i)/(99+i)) for i in range(41,61)]
        self.assertAlmostEqual(output["realized_log_vol_20d"],stdev(logs))

    def test_amihud_scale_and_zero_volume_are_explicit(self):
        sessions,rows=daily_fixture()
        output=self.daily("D05",rows,sessions)
        expected=[abs((100+i)/(99+i)-1)/(100+i)**2 for i in range(41,61)]
        self.assertAlmostEqual(output["values"]["amihud_mean_20d"],mean(expected))
        self.assertEqual(output["values"]["valid_window_count"],20)
        self.assertEqual(output["values"]["units"],"ABS_ARITHMETIC_RETURN_PER_US_DOLLAR_SCALE_1")
        for r in rows:
            if r["market_date"]==sessions[-1]["date"] and r["adjustment"]=="raw":
                r["source"]["v"]=0
        output=self.daily("D05",rows,sessions)
        self.assertIsNone(output["values"]["daily_amihud"])
        self.assertIsNone(output["values"]["amihud_mean_20d"])
        self.assertEqual(output["values"]["valid_window_count"],19)

    def test_rth_aggregate_dollar_volume_is_sum_of_minute_products(self):
        session,rows=minutes(n=5)
        output=self.daily("D02",rows,[session])
        self.assertEqual(output["values"]["raw_close"],104)
        self.assertEqual(output["values"]["raw_volume"],15)
        self.assertEqual(output["values"]["dollar_volume"],sum((100+i)*(i+1) for i in range(5)))
        self.assertNotEqual(output["values"]["dollar_volume"],104*15)
        partial=self.daily("D02",rows[:-1],[session])
        self.assertIsNone(partial["values"]["raw_close"])
        self.assertEqual(partial["null_reasons"]["raw_close"],"INCOMPLETE_RTH_MINUTE_AGGREGATION")

    def test_minute_grid_keeps_missing_bars_and_honours_early_close(self):
        session,rows=minutes()
        rows.pop(10)
        result=derive_family("D01",rows,sessions=[session],target_start=session["date"],target_end=session["date"])
        self.assertEqual(len(result["rows"]),25)
        missing=result["rows"][10]
        self.assertFalse(missing["values"]["bar_present"])
        self.assertIsNone(missing["values"]["close"])
        self.assertIsNone(result["rows"][20]["values"]["return_20m"])
        self.assertAlmostEqual(result["rows"][-1]["values"]["return_5m"],124/119-1)
        self.assertEqual(result["rows"][-1]["values"]["minutes_to_close"],0)
        self.assertEqual(result["rows"][-1]["values"]["missing_bars_20m"],1)

    def test_session_windows_reset_and_publication_is_labelled_assumption(self):
        s1,r1=minutes("2025-09-02",5)
        s2,r2=minutes("2025-09-03",5)
        result=derive_family("D01",r1+r2,sessions=[s1,s2],target_start=s1["date"],target_end=s2["date"])
        self.assertIsNone(result["rows"][5]["values"]["return_1m"])
        self.assertEqual(result["rows"][5]["values"]["minutes_from_open"],0)
        self.assertIn("NOT_OBSERVED_RECEIPT",result["rows"][5]["values"]["availability_policy"])

    def test_invalid_volume_cannot_pass_close_only_completeness(self):
        session,rows=minutes()
        rows[10]["source"]["v"]=None
        result=derive_family("D01",rows,sessions=[session],target_start=session["date"],target_end=session["date"])
        last=result["rows"][-1]
        self.assertIsNone(last["values"]["volume_rel_20m"])
        self.assertIsNone(last["values"]["dollar_volume_mean_20m"])
        self.assertAlmostEqual(last["values"]["return_20m"],124/104-1)
        self.assertFalse(last["values"]["microstructure_available"])
        self.assertIsNone(last["values"]["micro_avg_spread_bps"])

    def test_breadth_one_company_vote_and_unknown_eligibility(self):
        day="2025-09-02"
        rows=[{"symbol":"A","market_date":day,"values":{"adjusted_ret_1d":.1,"raw_ret_1d":.1}},
              {"symbol":"A.B","market_date":day,"values":{"adjusted_ret_1d":-.9,"raw_ret_1d":-.9}},
              {"symbol":"B","market_date":day,"values":{"adjusted_ret_1d":-.2,"raw_ret_1d":-.2}}]
        reps={"company-a":{"symbol":"A","eligible":None},"company-b":{"symbol":"B","eligible":None},
              "company-c":{"symbol":"C","eligible":None}}
        out=derive_family("CTX06",rows,sessions=[day],target_start=day,target_end=day,representative_security=reps)["rows"][0]
        self.assertEqual(out["values"]["cohort_company_count"],3)
        self.assertEqual(out["values"]["valid_company_count"],2)
        self.assertEqual(out["values"]["advancing"],1)
        self.assertEqual(out["values"]["declining"],1)
        self.assertEqual(out["values"]["missing_company_count"],1)
        self.assertIsNone(out["values"]["coverage"])
        self.assertEqual(out["null_reasons"]["coverage"],"ELIGIBLE_COMPANY_DENOMINATOR_UNKNOWN")
        reps["company-a"]["eligible"]=reps["company-b"]["eligible"]=True
        reps["company-c"]["eligible"]=False
        known=derive_family("CTX06",rows,sessions=[day],target_start=day,target_end=day,representative_security=reps)["rows"][0]
        self.assertEqual(known["values"]["coverage"],1)
        self.assertEqual(known["values"]["excluded_company_count"],1)
        self.assertEqual(known["values"]["cohort_company_count"],3)

    def test_conflicting_daily_inputs_and_json_safety(self):
        sessions,rows=daily_fixture()
        bad=deepcopy(rows[-2]);bad["source"]["c"]+=1
        output=self.daily("D02",rows+[bad],sessions)
        self.assertIsNone(output["values"]["raw_close"])
        self.assertEqual(output["null_reasons"]["raw_close"],"CONFLICTING_INPUT_ROWS")
        json.dumps(output,allow_nan=False)
        self.assertIn("prior20",FORMULA_MANIFEST["daily_volume"])


if __name__=="__main__":
    unittest.main()
