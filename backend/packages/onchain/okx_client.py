from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import os
import time
from typing import Any
from urllib.parse import urlencode

import requests


API_BASE_URL = "https://web3.okx.com"
PORTFOLIO_ALL_BALANCES_PATH = "/api/v6/dex/balance/all-token-balances-by-address"
AUTH_OR_REGION_ERROR_CODES = {"50125", "80001"}
RATE_LIMIT_ERROR_CODES = {"50011"}


class OKXAPIError(RuntimeError):
    def __init__(self, message: str, *, code: str = "") -> None:
        super().__init__(message)
        self.code = code


def _json_dumps_minified(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class OKXWeb3Client:
    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        passphrase: str,
        proxy: str | None = None,
        timeout_seconds: int = 30,
        max_retries: int = 4,
        request_delay_seconds: float = 0.25,
    ) -> None:
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_retries = max(1, int(max_retries))
        self.request_delay_seconds = max(0.0, float(request_delay_seconds))
        self.session = requests.Session()
        self.proxies = {"http": proxy, "https": proxy} if proxy else None

    @classmethod
    def from_env(cls) -> "OKXWeb3Client":
        api_key = os.getenv("OKX_API_KEY", "").strip()
        secret_key = os.getenv("OKX_SECRET_KEY", "").strip()
        passphrase = os.getenv("OKX_PASSPHRASE", "").strip()
        missing = [
            name
            for name, value in (
                ("OKX_API_KEY", api_key),
                ("OKX_SECRET_KEY", secret_key),
                ("OKX_PASSPHRASE", passphrase),
            )
            if not value
        ]
        if missing:
            raise OKXAPIError("Missing OKX environment variables: " + ", ".join(missing), code="auth_error")
        return cls(
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
            proxy=os.getenv("OKX_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or None,
            timeout_seconds=int(os.getenv("OKX_TIMEOUT_SECONDS", "30")),
            max_retries=int(os.getenv("OKX_MAX_RETRIES", "4")),
            request_delay_seconds=float(os.getenv("OKX_REQUEST_DELAY_SECONDS", "0.25")),
        )

    def _sign_headers(self, method: str, request_path: str, body_text: str = "") -> dict[str, str]:
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        payload = timestamp + method.upper() + request_path + body_text
        digest = hmac.new(
            self.secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature = base64.b64encode(digest).decode()
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
        }

    @staticmethod
    def _build_request_path(path: str, params: dict[str, Any] | None = None) -> str:
        filtered = {
            key: value
            for key, value in (params or {}).items()
            if value is not None and str(value).strip() != ""
        }
        query = urlencode(filtered)
        return f"{path}?{query}" if query else path

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        request_path = self._build_request_path(path, params)
        url = f"{API_BASE_URL}{request_path}"
        body_text = _json_dumps_minified(json_body) if json_body is not None else ""
        last_error = ""

        for attempt in range(1, self.max_retries + 1):
            headers = self._sign_headers(method.upper(), request_path, body_text)
            if json_body is not None:
                headers["Content-Type"] = "application/json"
            try:
                response = self.session.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    data=body_text or None,
                    timeout=self.timeout_seconds,
                    proxies=self.proxies,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt - 1))
                    continue
                raise OKXAPIError(f"Network request failed: {exc}", code="network_error") from exc

            try:
                body = response.json()
            except Exception as exc:
                raise OKXAPIError(f"Response is not JSON: HTTP {response.status_code}", code="api_error") from exc

            code = str(body.get("code", "")).strip()
            msg = str(body.get("msg", "")).strip()
            if code in AUTH_OR_REGION_ERROR_CODES or "no access" in msg.lower():
                raise OKXAPIError(f"OKX auth or region error: code={code} msg={msg}", code="auth_error")
            if code == "0":
                if self.request_delay_seconds > 0:
                    time.sleep(self.request_delay_seconds)
                return body.get("data", [])
            if code in RATE_LIMIT_ERROR_CODES:
                last_error = f"OKX rate limit: code={code} msg={msg}"
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt - 1))
                    continue
                raise OKXAPIError(last_error, code="rate_limited")
            raise OKXAPIError(f"OKX API error: code={code} msg={msg}", code="api_error")

        raise OKXAPIError(last_error or "Unknown OKX API error", code="api_error")

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post_json(self, path: str, json_body: Any) -> Any:
        return self.request("POST", path, json_body=json_body)

    def fetch_all_token_balances(self, *, wallet_address: str, chains: str) -> list[dict[str, Any]]:
        data = self.get(
            PORTFOLIO_ALL_BALANCES_PATH,
            {
                "address": wallet_address,
                "chains": chains,
                "excludeRiskToken": "0",
            },
        )
        if not isinstance(data, list):
            raise OKXAPIError(f"Unexpected all-token balances response: {type(data).__name__}", code="api_error")
        return data
