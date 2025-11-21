#!/usr/bin/env python3
"""
basic_bot.py

Simplified Trading Bot for Binance Futures Testnet (USDT-M).

Features:
- Place MARKET and LIMIT orders
- Support BUY and SELL
- CLI input validation
- Logging of requests/responses/errors
- Optional TWAP (time-weighted avg price) order type (simple implementation)
- Uses Binance Futures REST endpoints (signed requests)
- Testnet base URL: https://testnet.binancefuture.com
"""

import os
import sys
import time
import hmac
import json
import argparse
import logging
import hashlib
import requests
from urllib.parse import urlencode

TESTNET_BASE_URL = "https://testnet.binancefuture.com"  
ORDER_ENDPOINT = "/fapi/v1/order"

PING_ENDPOINT = "/fapi/v1/ping"
TIME_ENDPOINT = "/fapi/v1/time"

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"basic_bot_{int(time.time())}.log")


logger = logging.getLogger("BasicBot")
logger.setLevel(logging.DEBUG)
fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")

fh = logging.FileHandler(LOG_FILE)
fh.setLevel(logging.DEBUG)
fh.setFormatter(fmt)
logger.addHandler(fh)

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
ch.setFormatter(fmt)
logger.addHandler(ch)


class BinanceFuturesClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str = TESTNET_BASE_URL, recv_window: int = 5000):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.api_key})
        self.recv_window = recv_window

    def _get_timestamp(self):
        return int(time.time() * 1000)

    def _sign(self, params: dict) -> dict:
        """
        Sign parameters using HMAC SHA256 (required by Binance signed endpoints).
        Returns a new params dict with 'signature' appended.
        """
        
        params_copy = dict(params)
        qs = urlencode(params_copy, doseq=True)
        signature = hmac.new(self.api_secret.encode('utf-8'), qs.encode('utf-8'), hashlib.sha256).hexdigest()
        params_copy['signature'] = signature
        return params_copy

    def _request(self, method: str, path: str, params: dict = None, signed: bool = False, timeout: int = 10):
        url = f"{self.base_url}{path}"
        params = params or {}
        if signed:
            params.setdefault("timestamp", self._get_timestamp())
            params.setdefault("recvWindow", self.recv_window)
            params = self._sign(params)

        try:
            logger.debug(f"REQUEST -> {method} {url} PARAMS: {params}")
            if method.upper() == "GET":
                r = self.session.get(url, params=params, timeout=timeout)
            elif method.upper() == "POST":
                r = self.session.post(url, params=params, timeout=timeout)
            elif method.upper() == "DELETE":
                r = self.session.delete(url, params=params, timeout=timeout)
            else:
                raise ValueError("Unsupported HTTP method")
        except requests.RequestException as e:
            logger.exception("Network error during request")
            raise

        logger.debug(f"RESPONSE <- {r.status_code} {r.text}")
        try:
            data = r.json()
        except Exception:
            r.raise_for_status()
            return r.text

        if r.status_code >= 400:
            
            logger.error(f"API Error: HTTP {r.status_code} - {data}")
            raise Exception(f"API Error {r.status_code}: {data}")
        return data

    # Convenience functions
    def ping(self):
        return self._request("GET", PING_ENDPOINT, signed=False)

    def get_time(self):
        return self._request("GET", TIME_ENDPOINT, signed=False)

    def place_order(self, symbol: str, side: str, order_type: str, quantity: float,
                    price: float = None, time_in_force: str = "GTC", reduce_only: bool = False,
                    stop_price: float = None, close_position: bool = False) -> dict:
        """
        Place an order on Binance Futures (fapi).
        - symbol: e.g. 'BTCUSDT'
        - side: 'BUY' or 'SELL'
        - order_type: 'MARKET' or 'LIMIT' or 'STOP' (STOP here we'll interpret as STOP-MARKET or STOP-LIMIT depending on price)
        - quantity: in contract/base asset quantity (must conform to exchange limits)
        - price: required for LIMIT orders
        - stop_price: for stop orders (stopPrice)
        - close_position: boolean for closing (optional)
        """
        path = ORDER_ENDPOINT
        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(quantity)  
        }

        if order_type.upper() == "LIMIT":
            if price is None:
                raise ValueError("LIMIT orders require --price")
            params["price"] = str(price)
            params["timeInForce"] = time_in_force
        if order_type.upper() in ("STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"):
            
            if stop_price is None:
                raise ValueError("STOP orders require --stop_price")
            params["stopPrice"] = str(stop_price)
           
            if order_type.upper() == "STOP":
                params["type"] = "STOP_MARKET"

        
        if reduce_only:
            params["reduceOnly"] = "true"
        if close_position:
            params["closePosition"] = "true"

        return self._request("POST", path, params=params, signed=True)


class BasicBot:
    def __init__(self, api_key: str, api_secret: str, base_url: str = TESTNET_BASE_URL):
        self.client = BinanceFuturesClient(api_key, api_secret, base_url=base_url)

    def place_market_order(self, symbol: str, side: str, quantity: float):
        
        logger.info(f"Placing MARKET {side} order for {quantity} {symbol}")
        try:
            resp = self.client.place_order(symbol=symbol, side=side, order_type="MARKET", quantity=quantity)
            logger.info("Order placed successfully.")
            logger.debug(json.dumps(resp, indent=2))
            return resp
        except Exception as e:
            logger.exception("Failed to place market order")
            raise

    def place_limit_order(self, symbol: str, side: str, quantity: float, price: float, time_in_force="GTC"):
        logger.info(f"Placing LIMIT {side} order for {quantity} {symbol} at {price}")
        try:
            resp = self.client.place_order(symbol=symbol, side=side, order_type="LIMIT",
                                           quantity=quantity, price=price, time_in_force=time_in_force)
            logger.info("Limit order placed successfully.")
            logger.debug(json.dumps(resp, indent=2))
            return resp
        except Exception as e:
            logger.exception("Failed to place limit order")
            raise

    def place_stop_market_order(self, symbol: str, side: str, quantity: float, stop_price: float):
        logger.info(f"Placing STOP_MARKET {side} order for {quantity} {symbol} with stopPrice {stop_price}")
        try:
            resp = self.client.place_order(symbol=symbol, side=side, order_type="STOP_MARKET",
                                           quantity=quantity, stop_price=stop_price)
            logger.info("Stop market order placed successfully.")
            logger.debug(json.dumps(resp, indent=2))
            return resp
        except Exception as e:
            logger.exception("Failed to place stop market order")
            raise

    def place_twap(self, symbol: str, side: str, total_quantity: float, slices: int = 4, interval: float = 2.0):
        """
        Very simple TWAP: splits total_quantity into `slices` equal MARKET orders spaced by `interval` seconds.
        Note: Use with caution even on testnet. This is a naive implementation meant for demo/assignment.
        """
        logger.info(f"Starting TWAP: {total_quantity} {symbol} over {slices} slices every {interval}s")
        per_slice = total_quantity / slices
        results = []
        for i in range(slices):
            logger.info(f"TWAP slice {i+1}/{slices}: placing market order for {per_slice}")
            try:
                res = self.place_market_order(symbol, side, per_slice)
                results.append(res)
            except Exception as e:
                logger.exception("TWAP slice failed")
                results.append({"error": str(e)})
            if i < slices - 1:
                time.sleep(interval)
        logger.info("TWAP complete")
        return results


def positive_float(s):
    try:
        v = float(s)
    except:
        raise argparse.ArgumentTypeError("Must be a number")
    if v <= 0:
        raise argparse.ArgumentTypeError("Must be > 0")
    return v

def parse_args():
    parser = argparse.ArgumentParser(description="Basic Binance Futures Testnet Trading Bot (USDT-M)")
    parser.add_argument("--api-key", help="Binance API Key (or set BINANCE_API_KEY env)", default=os.getenv("BINANCE_API_KEY"))
    parser.add_argument("--api-secret", help="Binance API Secret (or set BINANCE_API_SECRET env)", default=os.getenv("BINANCE_API_SECRET"))
    parser.add_argument("--base-url", help="Testnet base URL", default=TESTNET_BASE_URL)

    sub = parser.add_subparsers(dest="command", required=True, help="Command to execute")

    # market
    p_market = sub.add_parser("market", help="Place a MARKET order")
    p_market.add_argument("--symbol", required=True, help="Trading pair symbol, e.g. BTCUSDT")
    p_market.add_argument("--side", required=True, choices=["BUY", "SELL"], help="BUY or SELL")
    p_market.add_argument("--quantity", required=True, type=positive_float, help="Quantity (contracts/base units)")

    # limit
    p_limit = sub.add_parser("limit", help="Place a LIMIT order")
    p_limit.add_argument("--symbol", required=True, help="Trading pair symbol, e.g. BTCUSDT")
    p_limit.add_argument("--side", required=True, choices=["BUY", "SELL"], help="BUY or SELL")
    p_limit.add_argument("--quantity", required=True, type=positive_float, help="Quantity")
    p_limit.add_argument("--price", required=True, type=positive_float, help="Limit price")
    p_limit.add_argument("--time-in-force", choices=["GTC", "IOC", "FOK"], default="GTC")

    # stop market
    p_stop = sub.add_parser("stop", help="Place a STOP_MARKET order (stop-price required)")
    p_stop.add_argument("--symbol", required=True)
    p_stop.add_argument("--side", required=True, choices=["BUY", "SELL"])
    p_stop.add_argument("--quantity", required=True, type=positive_float)
    p_stop.add_argument("--stop-price", required=True, type=positive_float)

    # twap
    p_twap = sub.add_parser("twap", help="Place a simple TWAP (sliced MARKET orders)")
    p_twap.add_argument("--symbol", required=True)
    p_twap.add_argument("--side", required=True, choices=["BUY", "SELL"])
    p_twap.add_argument("--quantity", required=True, type=positive_float)
    p_twap.add_argument("--slices", type=int, default=4, help="Number of slices")
    p_twap.add_argument("--interval", type=float, default=2.0, help="Seconds between slices")

    # convenience
    parser.add_argument("--verbose", action="store_true", help="Show debug logs to console")

    return parser.parse_args()

def main():
    args = parse_args()
    if args.verbose:
        ch.setLevel(logging.DEBUG)

    api_key = args.api_key
    api_secret = args.api_secret
    if not api_key or not api_secret:
        logger.error("API key and secret are required. Provide via --api-key/--api-secret or BINANCE_API_KEY/SECRET env vars.")
        sys.exit(1)

    bot = BasicBot(api_key, api_secret, base_url=args.base_url)

    try:
        if args.command == "market":
            resp = bot.place_market_order(symbol=args.symbol, side=args.side, quantity=args.quantity)
            print_json_summary(resp)
        elif args.command == "limit":
            resp = bot.place_limit_order(symbol=args.symbol, side=args.side, quantity=args.quantity, price=args.price, time_in_force=args.time_in_force)
            print_json_summary(resp)
        elif args.command == "stop":
            resp = bot.place_stop_market_order(symbol=args.symbol, side=args.side, quantity=args.quantity, stop_price=args.stop_price)
            print_json_summary(resp)
        elif args.command == "twap":
            resp = bot.place_twap(symbol=args.symbol, side=args.side, total_quantity=args.quantity, slices=args.slices, interval=args.interval)
           
            print("TWAP results:")
            for idx, r in enumerate(resp, 1):
                print(f"Slice {idx}: {r.get('orderId') or r.get('error')}")
        else:
            logger.error("Unknown command")
    except Exception as e:
        logger.exception("Operation failed")
        print(f"Operation failed: {e}")
        sys.exit(2)

def print_json_summary(resp: dict):
    """
    Print a concise order summary for the user.
    """
    try:
        order_id = resp.get("orderId")
        symbol = resp.get("symbol")
        side = resp.get("side")
        ord_type = resp.get("type")
        status = resp.get("status")
        price = resp.get("price", "")
        executed_qty = resp.get("executedQty", "")
        avg_price = resp.get("avgPrice", resp.get("avgFillPrice", ""))
        print("="*40)
        print(f"OrderId: {order_id}")
        print(f"Symbol : {symbol}")
        print(f"Side   : {side}")
        print(f"Type   : {ord_type}")
        print(f"Status : {status}")
        print(f"Price  : {price}")
        print(f"ExecutedQty: {executed_qty}")
        print(f"AvgFillPrice: {avg_price}")
        print("="*40)
    except Exception:
        print("Could not parse order response. Raw response:")
        print(json.dumps(resp, indent=2))

if __name__ == "__main__":
    main()
