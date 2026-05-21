from __future__ import annotations

import os
from collections.abc import Callable
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from packages.onchain.gmgn_labels import (
    DEFAULT_GMGN_LIMIT,
    MAX_GMGN_LIMIT,
    MAX_TOKEN_COUNT,
    fetch_gmgn_label_results,
    token_error_to_payload,
    token_result_to_payload,
)
from packages.onchain.okx_client import OKXAPIError, OKXWeb3Client


class GMGNLabelsRequest(BaseModel):
    tokens: list[str] = Field(default_factory=list, max_length=MAX_TOKEN_COUNT)
    limit: int = Field(default=DEFAULT_GMGN_LIMIT, ge=1, le=MAX_GMGN_LIMIT)

    @field_validator("tokens")
    @classmethod
    def _normalize_tokens(cls, value: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for raw in value:
            token = str(raw or "").strip()
            key = token.lower()
            if not token or key in seen:
                continue
            seen.add(key)
            output.append(token)
        if not output:
            raise ValueError("tokens must include at least one token address")
        return output


class GMGNLabelsResponse(BaseModel):
    results: list[dict[str, Any]]
    errors: list[dict[str, str]]


def _env_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def allowed_origins_from_env() -> list[str]:
    raw = os.getenv("PUBLIC_API_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001")
    return [item.strip() for item in raw.split(",") if item.strip()]


def create_auth_verifier() -> Callable[[str], dict[str, Any]]:
    supabase_url = _env_value("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL").rstrip("/")
    supabase_anon_key = _env_value("SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if not supabase_url or not supabase_anon_key:
        raise RuntimeError("Missing SUPABASE_URL/SUPABASE_ANON_KEY for public API auth.")

    def verify(token: str) -> dict[str, Any]:
        try:
            response = httpx.get(
                f"{supabase_url}/auth/v1/user",
                headers={"apikey": supabase_anon_key, "Authorization": f"Bearer {token}"},
                timeout=10,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service unavailable") from exc
        if response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
        payload = response.json()
        if not payload.get("id"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
        return payload

    return verify


def create_app(
    *,
    auth_verifier: Callable[[str], dict[str, Any]] | None = None,
    okx_client_factory: Callable[[], OKXWeb3Client] | None = None,
) -> FastAPI:
    app = FastAPI(title="Jibai Public API")
    origins = allowed_origins_from_env()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )

    cached_auth_verifier: Callable[[str], dict[str, Any]] | None = auth_verifier

    def verify_auth(token: str) -> dict[str, Any]:
        nonlocal cached_auth_verifier
        if cached_auth_verifier is None:
            cached_auth_verifier = create_auth_verifier()
        return cached_auth_verifier(token)

    build_okx_client = okx_client_factory or OKXWeb3Client.from_env

    def current_user(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session")
        return verify_auth(token.strip())

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/onchain/gmgn-labels", response_model=GMGNLabelsResponse)
    def gmgn_labels(payload: GMGNLabelsRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        _ = user
        try:
            client = build_okx_client()
        except OKXAPIError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OKX credentials unavailable") from exc

        results, errors = fetch_gmgn_label_results(client, tokens=payload.tokens, limit=payload.limit)
        return {
            "results": [token_result_to_payload(item) for item in results],
            "errors": [token_error_to_payload(item) for item in errors],
        }

    return app


app = create_app()
