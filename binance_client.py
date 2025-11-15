# -*- coding: utf-8 -*-
import time, hmac, hashlib, requests
from typing import Dict, Any, Optional

class BinanceClient:
    def __init__(self, market: str, api_key: str, api_secret: str,
                 base_url_spot: str, base_url_usdm: str, base_url_usdm_testnet: str=None,
                 use_testnet: bool=False):
        self.market = market
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url_spot = base_url_spot
        self.base_url_usdm = base_url_usdm_testnet if use_testnet and base_url_usdm_testnet else base_url_usdm
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"X-MBX-APIKEY": api_key})

    def _sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        q = "&".join([f"{k}={params[k]}" for k in sorted(params)])
        sig = hmac.new(self.api_secret.encode(), q.encode(), hashlib.sha256).hexdigest()
        params["signature"] = sig
        return params

    def _request(self, method: str, path: str, params: Dict[str, Any], signed: bool=False, futures: bool=False) -> Any:
        base = self.base_url_usdm if futures else self.base_url_spot
        url = base + path
        if signed:
            ts = int(time.time() * 1000)
            params = {**params, "timestamp": ts, "recvWindow": 5000}
            params = self._sign(params)
        if method == "GET":
            r = self.session.get(url, params=params, timeout=20)
        else:
            r = self.session.post(url, data=params, timeout=20)
        if r.status_code >= 400:
            raise RuntimeError(f"Binance API error {r.status_code}: {r.text}")
        return r.json()

    # --- Public ---
    def exchange_info(self, symbol: str, futures: bool=True) -> Dict[str, Any]:
        path = "/fapi/v1/exchangeInfo" if futures else "/api/v3/exchangeInfo"
        return self._request("GET", path, {"symbol": symbol.upper()}, signed=False, futures=futures)

    # --- Private (USDM Futures) ---
    def futures_balance(self) -> Any:
        return self._request("GET", "/fapi/v2/balance", {}, signed=True, futures=True)

    def futures_position(self, symbol: str) -> Any:
        return self._request("GET", "/fapi/v2/positionRisk", {"symbol": symbol.upper()}, signed=True, futures=True)

    def futures_order_market(self, symbol: str, side: str, quantity: float, reduce_only: bool=False, client_id: Optional[str]=None) -> Any:
        params = {"symbol": symbol.upper(), "side": side, "type": "MARKET", "quantity": quantity}
        if reduce_only:
            params["reduceOnly"] = "true"
        if client_id:
            params["newClientOrderId"] = client_id[:36]
        return self._request("POST", "/fapi/v1/order", params, signed=True, futures=True)
