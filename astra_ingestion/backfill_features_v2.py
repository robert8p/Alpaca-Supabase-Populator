"""Deterministic fixed-cohort calculations over retained provider observations.

No network, database access, clock reads, forward fill or implicit universe
selection. Missing scheduled observations remain missing. These calculations
are retrospective values; publication assumptions are never receipt timestamps.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math
from statistics import mean, median, stdev
from zoneinfo import ZoneInfo

VERSION = "fixed3000-derived-v2.1"
NY = ZoneInfo("America/New_York")
FAMILIES = frozenset({"D01", "D02", "D03", "D04", "D05", "CTX06"})
DAILY_HORIZONS = (1, 5, 20, 60)
INTRADAY_HORIZONS = (1, 5, 10, 20, 60, 120)
CONTRACT_HASHES = {
    "D01": "b0108a7ea587d11fb61057c493a9eb316166b80fdc38f6e16c36bef699e2e0c2",
    "D02": "556e44418879e710c921b3e72214768ab6f36ee54f0632a74aabd9777de67a65",
    "D03": "720d1d6243eed29518e9cc4be2e1fd8c1f1ec45cc4c45400c5567320d3ecab4b",
    "D04": "230f350109b9b137b8dd9c722c7cefefac49b91eed733b5c2b4aa96ec43b97a8",
    "D05": "708d472f20dc1fa936737cf792676855c2eda377c89636fe26244c077bc10e91",
    "CTX06": "0b754b05d4998bb4c1008d35f7db9aa72de5a0e33d0fb06748a56454ea598d21",
}


def _number(value, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(value) or (positive and value <= 0) or (nonnegative and value < 0):
        return None
    return value


def _utc(value):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Input timestamps must carry an explicit timezone")
    return result.astimezone(timezone.utc)


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _calendar(sessions):
    result = {}
    for entry in sessions:
        item = {"date": entry} if isinstance(entry, str) else dict(entry)
        day = item.get("date", item.get("session_date"))
        if not isinstance(day, str) or len(day) != 10 or day in result:
            raise ValueError("Unique explicit exchange-calendar sessions required")
        datetime.fromisoformat(day)
        result[day] = item
    return dict(sorted(result.items()))


def _source(row):
    return row.get("source", {}) if row else {}


def _ohlc(row):
    source = _source(row)
    values = [_number(source.get(k), positive=True) for k in ("o", "h", "l", "c")]
    if any(v is None for v in values):
        return None
    o, h, l, c = values
    if h < max(o, l, c) or l > min(o, h, c):
        return None
    return o, h, l, c


def _put(values, reasons, field, value, reason="MISSING_OR_INVALID_INPUT"):
    if isinstance(value, float) and not math.isfinite(value):
        value, reason = None, "NONFINITE_RESULT"
    values[field] = value
    if value is None:
        reasons[field] = reason or "MISSING_OR_INVALID_INPUT"


def _ratio(a, b, *, offset=0.0, scale=1.0):
    if a is None or b is None or b == 0:
        return None
    return _number((a / b - offset) * scale)


def _window(values, index, count):
    if index + 1 < count:
        return None, "INSUFFICIENT_SUPPORT_HISTORY"
    result = values[index - count + 1:index + 1]
    if any(v is None for v in result):
        return None, "MISSING_REQUIRED_SCHEDULED_INPUT"
    return result, None


def _index(rows, timeframe, adjustment="raw"):
    indexed, conflicts, duplicates = {}, set(), 0
    for row in rows:
        if row.get("timeframe") != timeframe or row.get("adjustment", "raw") != adjustment:
            continue
        if row.get("feed", "sip") != "sip" or not isinstance(row.get("symbol"), str):
            continue
        key = (row["symbol"], row.get("market_date"))
        if timeframe == "1Min":
            try:
                ts = _utc(row.get("timestamp"))
            except (TypeError, ValueError):
                continue
            if ts.second or ts.microsecond:
                continue
            key = (row["symbol"], ts)
        if key in indexed:
            if _source(indexed[key]) != _source(row):
                conflicts.add(key)
            else:
                duplicates += 1
        else:
            indexed[key] = row
    for key in conflicts:
        indexed[key] = None
    return indexed, conflicts, duplicates


def _result(family, rows, limitations=None):
    counts = defaultdict(int)
    for row in rows:
        for field, reason in row.get("null_reasons", {}).items():
            counts[(field, reason)] += 1
    summaries = [{"state":"IDENTITY_OR_QUALITY_UNRESOLVED", "family":family,
                  "field":field, "reason":reason, "affected_records":count,
                  "scope":"affected_derived_field_only"}
                 for (field,reason),count in sorted(counts.items())]
    return {"formula_version": VERSION, "family": family,
            "source_contract_sha256": CONTRACT_HASHES[family],
            "rows": rows, "limitations": list(limitations or []) + summaries}


def _row(symbol, day, member_id, values, reasons, input_count, **extra):
    return {"symbol": symbol, "market_date": day, "member_id": member_id,
            "values": values, "null_reasons": reasons, "input_count": input_count,
            "support_history": False, "formula_version": VERSION, **extra}


def _intraday(rows, calendar, start, end, member_id, representative):
    indexed, conflicts, duplicates = _index(rows, "1Min")
    symbols = sorted({key[0] for key in indexed})
    if not symbols and isinstance(representative, str):
        symbols = [representative]
    output = []
    for symbol in symbols:
        for day, entry in calendar.items():
            if not start <= day <= end:
                continue
            if "open" not in entry or "close" not in entry:
                raise ValueError("D01 requires actual exchange open/close times")
            op = datetime.fromisoformat(day + "T" + entry["open"]).replace(tzinfo=NY).astimezone(timezone.utc)
            cl = datetime.fromisoformat(day + "T" + entry["close"]).replace(tzinfo=NY).astimezone(timezone.utc)
            count = int((cl - op).total_seconds() / 60)
            if not 1 <= count <= 390:
                raise ValueError("Invalid regular-session calendar bounds")
            stamps = [op + timedelta(minutes=i) for i in range(count)]
            bars = [indexed.get((symbol, ts)) for ts in stamps]
            closes = [_number(_source(r).get("c"), positive=True) for r in bars]
            volumes = [_number(_source(r).get("v"), nonnegative=True) for r in bars]
            coherent = [_ohlc(r) for r in bars]
            log_returns = [None] + [math.log(closes[i])-math.log(closes[i-1])
                if closes[i] is not None and closes[i-1] is not None else None for i in range(1, count)]
            pv, total_volume, close_proxy_count, session_missing = 0.0, 0.0, 0, 0
            for i, (ts, bar) in enumerate(zip(stamps, bars)):
                source, values, reasons = _source(bar), {}, {}
                ohlc = coherent[i]
                missing_reason = "CONFLICTING_INPUT_ROWS" if (symbol, ts) in conflicts else "SOURCE_BAR_NOT_RETURNED"
                values.update(provider_interval_start=_iso(ts), provider_interval_end=_iso(ts + timedelta(minutes=1)),
                    availability_assumed_ts=_iso(ts + timedelta(seconds=61)),
                    availability_policy="ARCHIVED_FINAL_BAR_PLUS_ONE_SECOND_PROXY_NOT_OBSERVED_RECEIPT",
                    minutes_from_open=i, minutes_to_close=count-i-1,
                    bar_present=bar is not None, bar_valid=ohlc is not None)
                for field, key in (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"),
                                   ("volume", "v"), ("trade_count", "n"), ("provider_vwap", "vw")):
                    v = _number(source.get(key), positive=key in {"o", "h", "l", "c", "vw"},
                                nonnegative=key in {"v", "n"})
                    _put(values, reasons, field, v, missing_reason if bar is None else "MISSING_OR_INVALID_PROVIDER_FIELD")
                _put(values, reasons, "dollar_volume_close",
                     closes[i] * volumes[i] if closes[i] is not None and volumes[i] is not None else None)
                vwap = _number(source.get("vw"), positive=True)
                _put(values, reasons, "dollar_volume_vwap",
                     vwap * volumes[i] if vwap is not None and volumes[i] is not None else None,
                     "PROVIDER_VWAP_OR_VOLUME_UNAVAILABLE")
                for n in INTRADAY_HORIZONS:
                    w, reason = _window(closes, i, n + 1)
                    _put(values, reasons, f"return_{n}m", w[-1] / w[0] - 1 if w else None, reason)
                for n in (5, 20, 60):
                    w, reason = _window(log_returns, i, n)
                    _put(values, reasons, f"realized_vol_{n}m", stdev(w) if w else None, reason)
                    w, reason = _window(closes, i, n)
                    _put(values, reasons, f"sma_close_{n}m", mean(w) if w else None, reason)
                geometry = {"candle_range_pct": None, "candle_body_pct": None,
                            "upper_wick_pct": None, "lower_wick_pct": None}
                if ohlc:
                    o, h, l, c = ohlc
                    geometry.update(candle_range_pct=(h-l)/o, candle_body_pct=(c-o)/o,
                                    upper_wick_pct=(h-max(o,c))/o, lower_wick_pct=(min(o,c)-l)/o)
                for field, value in geometry.items():
                    _put(values, reasons, field, value, "MISSING_OR_INCOHERENT_OHLC")
                w, reason = _window(coherent, i, 20)
                _put(values, reasons, "range_20m_pct", max(x[1] for x in w)/min(x[2] for x in w)-1 if w else None, reason)
                w, reason = _window(volumes, i, 20)
                vm, vs = (mean(w), stdev(w)) if w else (None, None)
                _put(values, reasons, "volume_mean_20m", vm, reason)
                _put(values, reasons, "volume_rel_20m", _ratio(volumes[i], vm), reason or "ZERO_VOLUME_DENOMINATOR")
                _put(values, reasons, "volume_z_20m", _ratio(volumes[i]-vm if vm is not None else None, vs),
                     reason or "ZERO_VOLUME_VARIANCE")
                dv = [c*v if c is not None and v is not None else None
                      for c, v in zip(closes[max(0,i-19):i+1], volumes[max(0,i-19):i+1])]
                _put(values, reasons, "dollar_volume_mean_20m", mean(dv) if len(dv)==20 and None not in dv else None,
                     "INSUFFICIENT_SUPPORT_HISTORY" if i<19 else "MISSING_REQUIRED_SCHEDULED_INPUT")
                if bar is None or ohlc is None:
                    session_missing += 1
                if volumes[i] is not None and volumes[i] > 0:
                    # The inherited feature is explicitly a cumulative observed-bar
                    # proxy. Its completeness and substitutions remain visible.
                    price = vwap if source.get("vw") is not None else closes[i]
                    if price is not None:
                        pv += price * volumes[i]
                        total_volume += volumes[i]
                        if source.get("vw") is None:
                            close_proxy_count += 1
                session_vwap = pv / total_volume if total_volume > 0 else None
                _put(values, reasons, "session_vwap_proxy", session_vwap, "NO_POSITIVE_VALID_SESSION_VOLUME")
                for field, a, b in (
                    ("close_vs_provider_vwap_bps", closes[i], vwap),
                    ("close_vs_session_vwap_bps", closes[i], session_vwap),
                    ("close_vs_sma20_bps", closes[i], values["sma_close_20m"]),
                    ("sma5_vs_sma20_bps", values["sma_close_5m"], values["sma_close_20m"]),
                ):
                    _put(values, reasons, field, _ratio(a, b, offset=1, scale=10000))
                missing = sum(x is None for x in coherent[max(0,i-19):i+1])
                values.update(missing_bars_20m=missing, microstructure_available=False)
                _put(values, reasons, "coverage_20m", (20-missing)/20 if i>=19 else None, "INSUFFICIENT_SESSION_HISTORY")
                for field in ("micro_trade_count", "micro_quote_count", "micro_avg_spread_bps",
                              "micro_last_spread_bps", "micro_trade_imbalance", "micro_quote_size_imbalance",
                              "microprice_dislocation_bps"):
                    _put(values, reasons, field, None, "OUTSIDE_GENUINE_MICROSTRUCTURE_CAPTURE")
                flags = {"exact_clock_grid": True, "session_input_complete_through_t": session_missing==0,
                         "session_vwap_close_substitutions": close_proxy_count,
                         "identity_status": (bar or {}).get("identity_status", "UNRESOLVED_PROVIDER_ANCHOR"),
                         "corporate_action_adjustment_status": "RAW_UNADJUSTED",
                         "outcome_independent": True, "research_only_components_preserved_not_recomputed": True}
                output.append(_row(symbol, day, member_id, values, reasons, int(bar is not None),
                                   timestamp=_iso(ts), quality_flags=flags))
    return _result("D01", output, [{"state": "IDENTITY_OR_QUALITY_UNRESOLVED",
        "reason": "IDENTICAL_INPUT_ROWS_DEDUPLICATED", "count": duplicates}] if duplicates else [])


def _daily_inputs(rows, calendar):
    raw, conflicts, _ = _index(rows, "1Day")
    split, _, _ = _index(rows, "1Day", "split")
    result = {}
    for key, row in raw.items():
        s = _source(row)
        c, v = _number(s.get("c"), positive=True), _number(s.get("v"), nonnegative=True)
        adj = split.get(key)
        ac, av = _number(_source(adj).get("c"), positive=True), _number(_source(adj).get("v"), nonnegative=True)
        result[key] = {"c": c, "v": v, "dv": _number(c*v) if c is not None and v is not None else None,
                       "ac": ac, "av": av, "identity_anchor": (row or {}).get("identity_anchor"),
                       "source_code": "ALPACA_SIP_1DAY_PROVIDER_DEFINITION",
                       "basis": "PROVIDER_DAILY_NOT_ASSERTED_RTH", "observed_bars": int(row is not None),
                       "adjustment_basis": "PROVIDER_SPLIT_SERIES" if adj else "UNRESOLVED_SPLIT_MECHANICS",
                       "reason": "CONFLICTING_INPUT_ROWS" if key in conflicts else "SOURCE_DAILY_BAR_NOT_RETURNED"}
    # Reuse already-derived D02 rows when raw daily inputs are absent. Their
    # source/session basis remains attached and must agree across a lookback.
    for row in rows:
        values = row.get("values", {})
        if "raw_close" not in values or not row.get("symbol"):
            continue
        key = (row["symbol"], row.get("market_date"))
        if key not in result:
            result[key] = {"c": _number(values.get("raw_close"), positive=True),
                           "v": _number(values.get("raw_volume"), nonnegative=True),
                           "dv": _number(values.get("dollar_volume"), nonnegative=True),
                           "ac": _number(values.get("adjusted_close"), positive=True),
                           "av": _number(values.get("adjusted_volume"), nonnegative=True),
                           "identity_anchor": row.get("identity_anchor"),
                           "source_code": values.get("source_code", "RETAINED_D02"),
                           "basis": row.get("daily_basis", values.get("daily_basis", "UNKNOWN_DAILY_BASIS")),
                           "observed_bars": row.get("input_count", 0),
                           "adjustment_basis": values.get("adjustment_basis", "UNRESOLVED_SPLIT_MECHANICS"),
                           "reason": "RETAINED_D02_FIELD_UNAVAILABLE"}
    minutes, _, _ = _index(rows, "1Min")
    groups = defaultdict(list)
    for (symbol, ts), row in minutes.items():
        day = ts.astimezone(NY).date().isoformat()
        entry = calendar.get(day)
        if not entry or "open" not in entry or "close" not in entry:
            continue
        time = ts.astimezone(NY).strftime("%H:%M")
        if entry["open"][:5] <= time < entry["close"][:5]:
            groups[(symbol, day)].append((ts, row))
    for key, group in groups.items():
        if key in result:
            continue
        entry = calendar[key[1]]
        op = datetime.fromisoformat(key[1]+"T"+entry["open"]).replace(tzinfo=NY)
        cl = datetime.fromisoformat(key[1]+"T"+entry["close"]).replace(tzinfo=NY)
        expected = int((cl-op).total_seconds()/60)
        group.sort(key=lambda x: x[0])
        cs = [_number(_source(r).get("c"), positive=True) for _, r in group]
        vs = [_number(_source(r).get("v"), nonnegative=True) for _, r in group]
        complete = len(group)==expected and None not in cs and None not in vs
        anchors = {(r or {}).get("identity_anchor") for _, r in group}
        result[key] = {"c": cs[-1] if complete else None, "v": sum(vs) if complete else None,
                       "dv": sum(c*v for c,v in zip(cs,vs)) if complete else None,
                       "ac": None, "av": None, "identity_anchor": next(iter(anchors)) if len(anchors)==1 else None,
                       "source_code": "VERIFIED_RTH_MINUTE_AGGREGATION",
                       "basis": "RTH_CLOSE_SUM_OBSERVED_MINUTE_CLOSE_DOLLAR_VOLUME",
                       "observed_bars": len(group), "expected_bars": expected,
                       "adjustment_basis": "UNRESOLVED_SPLIT_MECHANICS",
                       "reason": "INCOMPLETE_RTH_MINUTE_AGGREGATION"}
    return result


def _daily(family, rows, calendar, start, end, member_id, representative):
    inputs = _daily_inputs(rows, calendar)
    symbols = sorted({key[0] for key in inputs})
    if not symbols and isinstance(representative, str):
        symbols = [representative]
    days = list(calendar)
    output = []
    for symbol in symbols:
        series = [inputs.get((symbol, day), {}) for day in days]
        cs = [r.get("c") for r in series]
        ac = [r.get("ac") for r in series]
        volumes = [r.get("v") for r in series]
        av = [r.get("av") for r in series]
        dvs = [r.get("dv") for r in series]
        def continuity(i, count, adjusted=False):
            if i+1<count:
                return "INSUFFICIENT_SUPPORT_HISTORY"
            window = series[i-count+1:i+1]
            if len({r.get("basis") for r in window}) != 1 or any(not r.get("basis") for r in window):
                return "MISSING_OR_MIXED_DAILY_SESSION_BASIS"
            if adjusted:
                ids = [r.get("identity_anchor") for r in window]
                if any(not anchor for anchor in ids):
                    return "IDENTITY_CONTINUITY_UNRESOLVED"
                if len(set(ids)) != 1:
                    return "IDENTITY_DISCONTINUITY"
                if any(r.get("adjustment_basis") not in {"PROVIDER_SPLIT_SERIES", "SUPPORTED_EXECUTED_MECHANICS"} for r in window):
                    return "SPLIT_MECHANICS_UNRESOLVED"
            return None
        raw_returns, adjusted_returns = [], []
        for i in range(len(days)):
            raw_returns.append(_ratio(cs[i],cs[i-1],offset=1) if i and cs[i] is not None and cs[i-1] is not None
                               and continuity(i,2) is None else None)
            adjusted_returns.append(_ratio(ac[i],ac[i-1],offset=1) if i and ac[i] is not None and ac[i-1] is not None
                                    and continuity(i,2,True) is None else None)
        logs = [math.log1p(v) if v is not None and v>-1 else None for v in adjusted_returns]
        raw_logs = [math.log1p(v) if v is not None and v>-1 else None for v in raw_returns]
        amihud = [abs(r)/dv if r is not None and dv is not None and dv>0 else None
                  for r,dv in zip(adjusted_returns,dvs)]
        raw_amihud = [abs(r)/dv if r is not None and dv is not None and dv>0 else None
                      for r,dv in zip(raw_returns,dvs)]
        for i, day in enumerate(days):
            if not start<=day<=end:
                continue
            row, values, reasons = series[i], {}, {}
            if family=="D02":
                for field,key in (("raw_close","c"),("raw_volume","v"),("dollar_volume","dv"),
                                  ("adjusted_close","ac"),("adjusted_volume","av")):
                    _put(values,reasons,field,row.get(key),row.get("reason","SOURCE_DAILY_BAR_NOT_RETURNED")
                         if key in {"c","v","dv"} else "PROVIDER_SPLIT_SERIES_UNAVAILABLE")
                values.update(source_code=row.get("source_code","NO_SOURCE"), daily_basis=row.get("basis","UNKNOWN"),
                              adjustment_basis=row.get("adjustment_basis","UNRESOLVED_SPLIT_MECHANICS"),
                              availability="ARCHIVED_PROVIDER_VALUES_NOT_ORIGINAL_RECEIPT_CERTIFIED")
            elif family=="D03":
                for n in DAILY_HORIZONS:
                    for variant,prices in (("raw",cs),("adjusted",ac)):
                        w, reason = _window(prices,i,n+1)
                        reason = reason or continuity(i,n+1,variant=="adjusted")
                        _put(values,reasons,f"{variant}_ret_{n}d",w[-1]/w[0]-1 if w and reason is None else None,reason)
                    # Provider-adjusted numeric values are retained separately from
                    # identity-qualified adjusted returns; never adjusted twice.
                    w, reason = _window(ac,i,n+1)
                    _put(values,reasons,f"provider_split_ret_{n}d",w[-1]/w[0]-1 if w else None,
                         reason or "PROVIDER_SPLIT_SERIES_UNAVAILABLE")
            elif family=="D04":
                w, reason = _window(logs,i,20)
                reason = reason or continuity(i,21,True)
                _put(values,reasons,"realized_log_vol_20d",stdev(w) if w and reason is None else None,reason)
                rw, rr = _window(raw_logs,i,20)
                _put(values,reasons,"raw_realized_log_vol_20d",stdev(rw) if rw else None,rr)
                # Recovered SQL v20 is ROWS20 PRECEDING TO1 PRECEDING.
                w, reason = _window(av,i-1,20)
                reason = reason or continuity(i,21,True)
                vm, sd = (mean(w),stdev(w)) if w and reason is None else (None,None)
                _put(values,reasons,"relative_volume_20d",_ratio(av[i],vm),reason or "ZERO_OR_MISSING_PRIOR_VOLUME_MEAN")
                _put(values,reasons,"volume_z20",_ratio(av[i]-vm if av[i] is not None and vm is not None else None,sd),
                     reason or "ZERO_OR_MISSING_PRIOR_VOLUME_VARIANCE")
                rw, rr = _window(volumes,i-1,20)
                _put(values,reasons,"raw_relative_volume_20d",_ratio(volumes[i],mean(rw) if rw else None),rr or "ZERO_PRIOR_VOLUME_MEAN")
                _put(values,reasons,"raw_volume_z20",_ratio(volumes[i]-mean(rw) if rw and volumes[i] is not None else None,
                    stdev(rw) if rw else None),rr or "ZERO_PRIOR_VOLUME_VARIANCE")
                values["input_coverage"]={"required_return_observations":20,"valid_return_observations":sum(v is not None for v in logs[max(0,i-19):i+1]),
                                          "required_prior_volume_observations":20,"valid_prior_volume_observations":sum(v is not None for v in av[max(0,i-20):i])}
            elif family=="D05":
                _put(values,reasons,"daily_amihud",amihud[i],"MISSING_ADJUSTED_RETURN_OR_NONPOSITIVE_DOLLAR_VOLUME")
                w, reason = _window(amihud,i,20)
                reason = reason or continuity(i,21,True)
                _put(values,reasons,"amihud_mean_20d",mean(w) if w and reason is None else None,reason)
                _put(values,reasons,"raw_daily_amihud",raw_amihud[i],"MISSING_RAW_RETURN_OR_NONPOSITIVE_DOLLAR_VOLUME")
                rw, rr = _window(raw_amihud,i,20)
                _put(values,reasons,"raw_amihud_mean_20d",mean(rw) if rw else None,rr)
                values.update(valid_window_count=sum(v is not None for v in amihud[max(0,i-19):i+1]),
                              units="ABS_ARITHMETIC_RETURN_PER_US_DOLLAR_SCALE_1")
            output.append(_row(symbol,day,member_id,values,reasons,row.get("observed_bars",0),
                               identity_anchor=row.get("identity_anchor"),daily_basis=row.get("basis","UNKNOWN"),
                               quality_flags={"retrospective_fixed_cohort":True,
                                              "historical_identity_qualified":bool(row.get("identity_anchor")),
                                              "provider_daily_basis_not_silently_equated_to_rth":True}))
    return _result(family,output)


def _breadth(rows, calendar, start, end, representatives):
    if not isinstance(representatives, dict) or not representatives:
        return _result("CTX06",[],[{"state":"IDENTITY_OR_QUALITY_UNRESOLVED",
            "reason":"COMPLETE_FIXED_COHORT_REPRESENTATIVE_MAP_REQUIRED"}])
    reps = {}
    symbol_companies = defaultdict(list)
    for company, value in representatives.items():
        item = {"symbol":value,"eligible":None} if isinstance(value,str) else dict(value)
        if item.get("eligible") not in (True,False,None):
            raise ValueError("Representative eligibility must be true, false or unknown")
        reps[company] = item
        if item.get("symbol"):
            symbol_companies[item["symbol"]].append(company)
    observed, conflicts = {}, set()
    for row in rows:
        if not row.get("symbol") or not isinstance(row.get("values"),dict):
            continue
        key = (row["symbol"],row.get("market_date"))
        value = row["values"]
        if "adjusted_ret_1d" not in value and "raw_ret_1d" not in value:
            continue
        if key in observed and observed[key] != value:
            conflicts.add(key)
        else:
            observed[key] = value
    output=[]
    for day in calendar:
        if not start<=day<=end:
            continue
        valid, raw_valid, missing, excluded, unknown_eligibility = [],[],0,0,0
        unresolved_representatives=0
        for company,item in reps.items():
            eligible = item.get("eligible")
            if isinstance(item.get("eligibility_by_date"),dict):
                eligible=item["eligibility_by_date"].get(day)
            if eligible is False:
                excluded+=1
                continue
            if eligible is None:
                unknown_eligibility+=1
            symbol=item.get("symbol")
            if not symbol or len(symbol_companies[symbol])!=1 or (symbol,day) in conflicts:
                unresolved_representatives+=1
                missing+=1
                continue
            v=observed.get((symbol,day),{})
            value=_number(v.get("adjusted_ret_1d"))
            raw_value=_number(v.get("raw_ret_1d"))
            if value is None:
                missing+=1
            else:
                valid.append(value)
            if raw_value is not None:
                raw_valid.append(raw_value)
        eligible_count=None if unknown_eligibility else len(reps)-excluded
        values={"cohort_id":"2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec",
                "company_aggregation_rule":"ONE_EXPLICIT_REPRESENTATIVE_PER_FIXED_COMPANY_V2",
                "cohort_company_count":len(reps), "eligible_company_count":eligible_count,
                "excluded_company_count":excluded,"eligibility_unknown_company_count":unknown_eligibility,
                "valid_company_count":len(valid),"observed_company_count":len(valid),
                "missing_company_count":missing,"quality_unresolved_representatives":unresolved_representatives,
                "advancing":sum(v>0 for v in valid),"declining":sum(v<0 for v in valid),
                "unchanged":sum(v==0 for v in valid),
                "raw_valid_company_count":len(raw_valid),"raw_advancing":sum(v>0 for v in raw_valid),
                "raw_declining":sum(v<0 for v in raw_valid),"raw_unchanged":sum(v==0 for v in raw_valid)}
        reasons={}
        _put(values,reasons,"coverage",_ratio(len(valid),eligible_count),
             "ELIGIBLE_COMPANY_DENOMINATOR_UNKNOWN" if eligible_count is None else "NO_ELIGIBLE_COMPANY")
        _put(values,reasons,"pct_advancing",_ratio(values["advancing"],len(valid)),"NO_VALID_COMPANY_RETURN")
        _put(values,reasons,"advance_decline_ratio",_ratio(values["advancing"],values["declining"]),"NO_DECLINING_COMPANY")
        _put(values,reasons,"equal_weight_ret_1d",mean(valid) if valid else None,"NO_VALID_COMPANY_RETURN")
        _put(values,reasons,"median_ret_1d",median(valid) if valid else None,"NO_VALID_COMPANY_RETURN")
        _put(values,reasons,"dispersion_ret_1d",stdev(valid) if len(valid)>1 else None,"FEWER_THAN_TWO_VALID_COMPANY_RETURNS")
        output.append(_row("__COHORT__",day,None,values,reasons,len(valid),
                           quality_flags={"retrospective_fixed_cohort":True,
                                          "complete_representative_map_supplied":True,
                                          "research_universe_survivorship_free":False}))
    return _result("CTX06",output)


def derive_family(family, rows, *, sessions, target_start, target_end,
                  member_id=None, representative_security=None):
    """Calculate one immutable family unit from normalized retained input rows.

    ``sessions`` is the complete actual exchange calendar including support
    sessions. For CTX06, ``representative_security`` must contain EVERY frozen
    company, mapping to ``{symbol, eligible: True|False|None}``; a string symbol
    is accepted for a single-company daily/minute task. Identity-qualified
    adjusted outputs require explicit stable ``identity_anchor`` input fields.
    """
    if family not in FAMILIES:
        raise ValueError("Unsupported calculation family")
    if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):
        raise ValueError("Calculation input must be explicit normalized row objects")
    if not isinstance(target_start,str) or not isinstance(target_end,str) or target_start>target_end:
        raise ValueError("Ordered target market dates required")
    calendar=_calendar(sessions)
    if not calendar:
        raise ValueError("Actual exchange calendar is required")
    if family=="D01":
        return _intraday(rows,calendar,target_start,target_end,member_id,representative_security)
    if family=="CTX06":
        return _breadth(rows,calendar,target_start,target_end,representative_security)
    return _daily(family,rows,calendar,target_start,target_end,member_id,representative_security)


FORMULA_MANIFEST = {
    "version":VERSION,
    "source_contract_sha256":CONTRACT_HASHES,
    "intraday_source":"astra_shared_equity_features_20260928_v1.feature_contract:v1; compute_feature_grid",
    "daily_source":"market_factors_20250901_20260731_v1.compute_daily_features_remediated_v1; compute_daily_features_equity_patch_v3",
    "intraday_windows":"Exact RTH session grid; returns1/5/10/20/60/120; sample log-volatility5/20/60; SMA5/20/60. No windows cross session open.",
    "intraday_missing_input_policy":"Enforce frozen dictionary completeness for every required price/volume/OHLC observation; legacy SQL close-count-only shortcuts are not reused.",
    "daily_returns":"Arithmetic close ratio minus1; exact1/5/20/60 exchange sessions; n+1 complete closes. Adjusted outputs also require stable explicit identity and supported adjustment basis.",
    "daily_volatility":"Sample standard deviation of20 adjusted log returns, current session included; unannualized.",
    "daily_volume":"Current adjusted volume divided by mean of prior20 sessions, current excluded; z-score uses prior20 sample standard deviation.",
    "amihud":"abs(adjusted arithmetic daily return)/dollar-volume;20-session complete mean including current; scale1, inverse USD.",
    "new_provider_daily_dollar_volume_definition":"CONVENTIONAL_PROVIDER_DAILY_CLOSE_VOLUME_V1: close times provider daily volume; provider session basis labelled, never silently equated to RTH minute aggregation.",
    "minute_daily_aggregation":"Exact complete RTH calendar; last close, sum volume, sum minute close times volume. Missing minute queries do not prove no eligible trade.",
    "adjustment":"Provider split series used unchanged; no double adjustment. Raw auxiliary values remain available when adjusted identity qualification is unresolved.",
    "breadth":"One explicitly supplied representative per frozen company; unknown eligibility keeps coverage denominator NULL; supplied excluded members remain in cohort accounting.",
    "support_requirement":"60 earlier daily sessions; actual calendar. D01 inherited windows are within-session;20 earlier intraday sessions retained as separately labelled support.",
    "excluded":"scenario10_frozen_factor_inputs preservation-only; microstructure NULL outside genuine captured windows; no quote/trade acquisition.",
}
