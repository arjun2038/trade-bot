"""
execution/order_manager.py
Places and manages orders on Binance Futures via REST API.
Supports both Testnet and Live environments.
"""

import hmac
import hashlib
import time
import requests
from utils.logger import get_logger

logger = get_logger("order_manager")

LIVE_BASE_URL = "https://fapi.binance.com"
TESTNET_BASE_URL = "https://testnet.binancefuture.com"


class OrderManager:
    def __init__(self, api_key: str, api_secret: str, use_testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = TESTNET_BASE_URL if use_testnet else LIVE_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.api_key})
        self._symbol_precision = {}

    def get_symbol_precision(self, symbol: str) -> dict:
        """Fetch and cache quantity & price precision/step size for a symbol."""
        if symbol in self._symbol_precision:
            return self._symbol_precision[symbol]

        url = f"{self.base_url}/fapi/v1/exchangeInfo"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            for s in data.get("symbols", []):
                if s.get("symbol") == symbol:
                    qty_prec = int(s.get("quantityPrecision", 3))
                    price_prec = int(s.get("pricePrecision", 2))
                    
                    # Also check stepSize from LOT_SIZE filter if available
                    for f in s.get("filters", []):
                        if f.get("filterType") == "LOT_SIZE":
                            step_size = f.get("stepSize", "0.001")
                            if "." in step_size:
                                qty_prec = len(step_size.rstrip("0").split(".")[1])
                            else:
                                qty_prec = 0
                        elif f.get("filterType") == "PRICE_FILTER":
                            tick_size = f.get("tickSize", "0.01")
                            if "." in tick_size:
                                price_prec = len(tick_size.rstrip("0").split(".")[1])
                            else:
                                price_prec = 0

                    info = {"quantityPrecision": qty_prec, "pricePrecision": price_prec}
                    self._symbol_precision[symbol] = info
                    logger.debug(f"Precision for {symbol}: {info}")
                    return info
        except Exception as e:
            logger.error(f"Failed to fetch exchangeInfo precision: {e}")

        default_info = {"quantityPrecision": 3, "pricePrecision": 2}
        self._symbol_precision[symbol] = default_info
        return default_info

    def round_quantity(self, symbol: str, quantity: float) -> float:
        """Round quantity to the symbol's allowed precision."""
        prec = self.get_symbol_precision(symbol)["quantityPrecision"]
        if prec == 0:
            return int(quantity)
        return round(quantity, prec)

    def round_price(self, symbol: str, price: float) -> float:
        """Round price to the symbol's allowed price precision."""
        prec = self.get_symbol_precision(symbol)["pricePrecision"]
        if prec == 0:
            return int(price)
        return round(price, prec)

    def _sign(self, params: dict) -> dict:
        """Add timestamp and HMAC-SHA256 signature to params."""
        params["timestamp"] = int(time.time() * 1000)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        signature = hmac.new(
            self.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _post(self, endpoint: str, params: dict) -> dict:
        """Signed POST request."""
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self.session.post(url, params=self._sign(params), timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"POST {endpoint} failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return {}

    def _delete(self, endpoint: str, params: dict) -> dict:
        """Signed DELETE request."""
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self.session.delete(url, params=self._sign(params), timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"DELETE {endpoint} failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return {}

    def _get(self, endpoint: str, params: dict) -> dict | list:
        """Signed GET request."""
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self.session.get(url, params=self._sign(params), timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"GET {endpoint} failed: {e}")
            return {}

    # ─────────────────────────────────────────
    #  Leverage & Margin
    # ─────────────────────────────────────────

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol."""
        result = self._post("/fapi/v1/leverage", {
            "symbol": symbol,
            "leverage": leverage
        })
        if result.get("leverage"):
            logger.info(f"Leverage set to {leverage}x for {symbol}")
            return True
        logger.warning(f"Failed to set leverage: {result}")
        return False

    # ─────────────────────────────────────────
    #  Orders
    # ─────────────────────────────────────────

    def place_market_order(
        self,
        symbol: str,
        side: str,       # "BUY" or "SELL"
        quantity: float,
        reduce_only: bool = False
    ) -> dict:
        """Place a market order."""
        quantity = self.round_quantity(symbol, quantity)
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
        }
        if reduce_only:
            params["reduceOnly"] = "true"

        result = self._post("/fapi/v1/order", params)
        if result.get("orderId"):
            logger.info(f"Market order placed: {side} {quantity} {symbol} | ID: {result['orderId']}")
        else:
            logger.error(f"Market order failed: {result}")
        return result

    def place_stop_loss(
        self,
        symbol: str,
        side: str,       # Opposite to position side
        quantity: float,
        stop_price: float
    ) -> dict:
        """Place a stop-loss order via Binance Algo Order endpoint."""
        quantity = self.round_quantity(symbol, quantity)
        stop_price = self.round_price(symbol, stop_price)
        params = {
            "algoType": "CONDITIONAL",
            "symbol": symbol,
            "side": side,
            "type": "STOP_MARKET",
            "quantity": quantity,
            "triggerPrice": stop_price,
            "workingType": "MARK_PRICE",
            "reduceOnly": "true",
        }
        result = self._post("/fapi/v1/algoOrder", params)
        if result.get("algoId") or result.get("orderId"):
            order_id = result.get("algoId") or result.get("orderId")
            logger.info(f"Stop loss placed at {stop_price} | ID: {order_id}")
        else:
            logger.error(f"Stop loss failed: {result}")
        return result

    def place_take_profit(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float
    ) -> dict:
        """Place a take-profit order via Binance Algo Order endpoint."""
        quantity = self.round_quantity(symbol, quantity)
        stop_price = self.round_price(symbol, stop_price)
        params = {
            "algoType": "CONDITIONAL",
            "symbol": symbol,
            "side": side,
            "type": "TAKE_PROFIT_MARKET",
            "quantity": quantity,
            "triggerPrice": stop_price,
            "workingType": "MARK_PRICE",
            "reduceOnly": "true",
        }
        result = self._post("/fapi/v1/algoOrder", params)
        if result.get("algoId") or result.get("orderId"):
            order_id = result.get("algoId") or result.get("orderId")
            logger.info(f"Take profit placed at {stop_price} | ID: {order_id}")
        else:
            logger.error(f"Take profit failed: {result}")
        return result

    def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all open standard and algo orders for a symbol."""
        # Cancel regular orders
        self._delete("/fapi/v1/allOpenOrders", {"symbol": symbol})
        # Cancel algo orders (conditional SL/TP)
        self._delete("/fapi/v1/algoOpenOrders", {"symbol": symbol})
        logger.info(f"Cancelled all open orders and algo orders for {symbol}")
        return True

    def get_open_positions(self, symbol: str) -> list:
        """Get open positions for a symbol. Returns list of positions with non-zero qty."""
        data = self._get("/fapi/v2/positionRisk", {"symbol": symbol})
        if isinstance(data, list):
            return [p for p in data if float(p.get("positionAmt", 0)) != 0]
        return []

    def get_balance(self) -> float:
        """Get available USDT balance."""
        data = self._get("/fapi/v2/balance", {})
        if isinstance(data, list):
            for asset in data:
                if asset.get("asset") == "USDT":
                    return float(asset.get("availableBalance", 0))
        return 0.0

