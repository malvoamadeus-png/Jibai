from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi.testclient import TestClient

from packages.onchain.okx_client import OKXAPIError
from packages.public_app.api import create_app


class EmptyOKXClient:
    def get(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return []

    def post_json(self, path: str, json_body: Any) -> list[dict[str, Any]]:
        return []


def test_public_api_requires_bearer_token() -> None:
    app = create_app(auth_verifier=lambda token: {"id": "user-1"}, okx_client_factory=EmptyOKXClient)
    client = TestClient(app)

    response = client.post("/api/onchain/gmgn-labels", json={"tokens": ["abc"], "limit": 20})

    assert response.status_code == 401


def test_public_api_rejects_invalid_token() -> None:
    def reject(_: str) -> dict[str, Any]:
        raise HTTPException(status_code=401, detail="Invalid session")

    app = create_app(auth_verifier=reject, okx_client_factory=EmptyOKXClient)
    client = TestClient(app)

    response = client.post(
        "/api/onchain/gmgn-labels",
        headers={"Authorization": "Bearer bad-token"},
        json={"tokens": ["abc"], "limit": 20},
    )

    assert response.status_code == 401


def test_public_api_validates_limit_max_50() -> None:
    app = create_app(auth_verifier=lambda token: {"id": "user-1"}, okx_client_factory=EmptyOKXClient)
    client = TestClient(app)

    response = client.post(
        "/api/onchain/gmgn-labels",
        headers={"Authorization": "Bearer token"},
        json={"tokens": ["abc"], "limit": 51},
    )

    assert response.status_code == 422


def test_public_api_hides_missing_okx_credentials() -> None:
    def missing_client() -> EmptyOKXClient:
        raise OKXAPIError("Missing OKX_API_KEY=secret", code="auth_error")

    app = create_app(auth_verifier=lambda token: {"id": "user-1"}, okx_client_factory=missing_client)
    client = TestClient(app)

    response = client.post(
        "/api/onchain/gmgn-labels",
        headers={"Authorization": "Bearer token"},
        json={"tokens": ["abc"], "limit": 20},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "OKX credentials unavailable"
