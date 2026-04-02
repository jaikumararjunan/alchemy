"""tests/unit/crypto/test_gateways.py — unit tests for Delta + Binance gateways."""
import pytest
from unittest.mock import patch, MagicMock


class TestDeltaGateway:
    def _make(self):
        from alchemy.execution.crypto.delta_gateway import DeltaGateway
        return DeltaGateway(api_key="test", api_secret="secret",
                            testnet_mode=True, paper_trading=True)

    def test_init(self):
        gw = self._make()
        assert gw.testnet is True
        assert gw.paper   is True
        assert "testnet" in gw.base_url

    def test_paper_order_returns_filled(self):
        gw = self._make()
        with patch.object(gw, "get_ticker", return_value={"mark_price": 68000}):
            result = gw.place_order("BTCUSD", side="buy", size=1,
                                     order_type="market_order", leverage=10)
        assert result["state"] == "filled"
        assert result["symbol"] == "BTCUSD"
        assert result["side"]   == "buy"
        assert result["mode"]   == "paper"
        assert "id" in result

    def test_paper_order_sell(self):
        gw = self._make()
        with patch.object(gw, "get_ticker", return_value={"mark_price": 3800}):
            result = gw.place_order("ETHUSD", side="sell", size=2, leverage=5)
        assert result["side"] == "sell"

    def test_sign_produces_headers(self):
        gw = self._make()
        headers = gw._sign("GET", "/v2/tickers/BTCUSD")
        assert "api-key"   in headers
        assert "timestamp" in headers
        assert "signature" in headers
        assert len(headers["signature"]) == 64   # SHA-256 hex

    def test_get_ticker_called(self):
        gw = self._make()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"result": {"mark_price": "68000", "symbol": "BTCUSD"}}
        with patch.object(gw._client, "get", return_value=mock_resp) as mock_get:
            result = gw.get_ticker("BTCUSD")
        mock_get.assert_called_once()
        assert result.get("mark_price") == "68000"

    def test_context_manager(self):
        from alchemy.execution.crypto.delta_gateway import DeltaGateway
        with DeltaGateway(api_key="k", api_secret="s", paper_trading=True) as gw:
            assert gw.paper is True


class TestBinanceGateway:
    def _make(self, market="futures_usdm"):
        from alchemy.execution.crypto.binance_gateway import BinanceGateway
        return BinanceGateway(api_key="test", api_secret="secret",
                              market=market, paper_trading=True, testnet=True)

    def test_init_futures(self):
        gw = self._make("futures_usdm")
        assert gw.market   == "futures_usdm"
        assert gw.paper    is True
        assert gw.testnet  is True

    def test_init_spot(self):
        gw = self._make("spot")
        assert "api.binance.com" in gw.base_url

    def test_paper_order_buy(self):
        gw = self._make()
        with patch.object(gw, "get_price", return_value=68000.0):
            result = gw.place_order("BTCUSDT", side="BUY", quantity=0.001,
                                     order_type="MARKET", leverage=10)
        assert result["status"]  == "FILLED"
        assert result["symbol"]  == "BTCUSDT"
        assert result["side"]    == "BUY"
        assert result["mode"]    == "paper"
        assert float(result["executedQty"]) == 0.001

    def test_paper_order_sell(self):
        gw = self._make()
        with patch.object(gw, "get_price", return_value=3800.0):
            result = gw.place_order("ETHUSDT", side="SELL", quantity=0.5)
        assert result["side"] == "SELL"

    def test_sign_params_adds_timestamp_and_signature(self):
        gw = self._make()
        params = {"symbol": "BTCUSDT", "side": "BUY"}
        signed = gw._sign_params(params.copy())
        assert "timestamp" in signed
        assert "signature" in signed
        assert len(signed["signature"]) == 64

    def test_format_qty(self):
        gw = self._make()
        assert gw._format_qty(0.001)    == "0.001"
        assert gw._format_qty(1.0)      == "1"
        assert gw._format_qty(0.00100)  == "0.001"

    def test_get_positions_spot_returns_empty(self):
        gw = self._make("spot")
        assert gw.get_positions() == []

    def test_context_manager(self):
        from alchemy.execution.crypto.binance_gateway import BinanceGateway
        with BinanceGateway(paper_trading=True) as gw:
            assert gw.paper is True
