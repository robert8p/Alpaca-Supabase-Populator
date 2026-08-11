from app.loader import _invalid_symbol_from_error


def test_extracts_alpaca_invalid_symbol_from_400():
    exc = RuntimeError('Alpaca returned HTTP 400: {"message":"invalid symbol: 296CVR012"}')
    assert _invalid_symbol_from_error(exc) == "296CVR012"


def test_extracts_delisted_alias_exactly():
    exc = RuntimeError('Alpaca returned HTTP 400: {"message":"invalid symbol: ABCD_DELISTED"}')
    assert _invalid_symbol_from_error(exc) == "ABCD_DELISTED"


def test_non_symbol_400_is_not_quarantined():
    exc = RuntimeError('Alpaca returned HTTP 400: {"message":"invalid page_token"}')
    assert _invalid_symbol_from_error(exc) is None
