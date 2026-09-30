"""tests/unit/dhan/test_dhan_gateway.py — Dhan gateway safety + payload tests (no network)."""
import pytest
from unittest.mock import patch

from alchemy.execution.dhan_gateway import DhanError, DhanGateway


def _gw(paper=True, **kw):
    return DhanGateway("1000000123", "tok", paper_trading=paper, **kw)


def _ltp(price):
    return {"data": {"NSE_EQ": {"2885": {"last_price": price}}}}


def test_paper_order_never_hits_network():
    gw = _gw()
    with patch.object(gw, "_request", side_effect=AssertionError("network")):
        o = gw.place_order("2885", "NSE_EQ", "BUY", 5)
    assert o["mode"] == "paper" and o["orderId"].startswith("DHAN_PAPER_")
    assert gw.get_order_book()[0]["orderId"] == o["orderId"]


def test_limit_order_requires_price():
    with pytest.raises(DhanError):
        _gw().place_order("2885", "NSE_EQ", "BUY", 1, order_type="LIMIT")


def test_live_order_payload():
    gw = _gw(paper=False)
    with patch.object(gw, "get_ltp", return_value=_ltp(100.0)), \
         patch.object(gw, "_request", return_value={"orderId": "1", "orderStatus": "TRANSIT"}) as req:
        gw.place_order("2885", "NSE_EQ", "SELL", 10, order_type="LIMIT", price=101, product_type="CNC")
    method, path = req.call_args.args
    body = req.call_args.kwargs["json"]
    assert (method, path) == ("POST", "/orders")
    assert body["transactionType"] == "SELL" and body["productType"] == "CNC"
    assert body["securityId"] == "2885" and body["quantity"] == 10
    assert body["dhanClientId"] == "1000000123"


def test_live_order_value_cap_blocks():
    gw = _gw(paper=False, max_order_value=10_000)
    with patch.object(gw, "get_ltp", return_value=_ltp(2900.0)), patch.object(gw, "_request") as req:
        with pytest.raises(DhanError, match="max_order_value"):
            gw.place_order("2885", "NSE_EQ", "BUY", 10)   # 29,000 rupees
    req.assert_not_called()


def test_live_market_order_refused_without_ltp():
    gw = _gw(paper=False)
    with patch.object(gw, "get_ltp", side_effect=DhanError("down")), patch.object(gw, "_request") as req:
        with pytest.raises(DhanError, match="LTP"):
            gw.place_order("2885", "NSE_EQ", "BUY", 1)
    req.assert_not_called()


def test_qty_cap_and_kill_switch():
    gw = _gw(paper=False, max_order_qty=5)
    with pytest.raises(DhanError, match="max_order_qty"):
        gw.place_order("2885", "NSE_EQ", "BUY", 6, order_type="LIMIT", price=1)
    gw.kill_switch = True
    with pytest.raises(DhanError, match="Kill switch"):
        gw.place_order("2885", "NSE_EQ", "BUY", 1, order_type="LIMIT", price=1)


def test_find_instrument_maps_segment():
    rows = [{"SEM_EXM_EXCH_ID": "NSE", "SEM_SEGMENT": "E", "SEM_SMST_SECURITY_ID": "2885",
             "SEM_INSTRUMENT_NAME": "EQUITY", "SEM_TRADING_SYMBOL": "RELIANCE",
             "SEM_LOT_UNITS": "1", "SEM_CUSTOM_SYMBOL": "Reliance Industries"}]
    with patch.object(DhanGateway, "_load_scrips", return_value=rows):
        inst = _gw().find_instrument("reliance-eq")
    assert inst["security_id"] == "2885" and inst["exchange_segment"] == "NSE_EQ"
