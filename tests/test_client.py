"""Tests for CommandCode API client URL construction and HTTP errors."""

from __future__ import annotations

import asyncio

import conftest  # noqa: F401
import pytest

from custom_components.command_gauge.coordinator import (
    CommandCodeApiClient,
    CommandCodeApiError,
)


class Response:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def text(self):
        return str(self.payload)

    async def json(self, content_type=None):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_client_sets_bearer_auth_and_org_id_query():
    response = Response(200, {"ok": True})
    session = Session(response)
    client = CommandCodeApiClient(session, "https://api.commandcode.ai", "secret")
    result = asyncio.run(client.fetch_credits("org-1"))
    assert result == {"ok": True}
    url, kwargs = session.calls[0]
    assert url == ("https://api.commandcode.ai/alpha/billing/credits?orgId=org-1")
    assert kwargs["headers"]["Authorization"] == "Bearer secret"
    assert "secret" not in url


def test_client_raises_for_http_error_without_response_body():
    client = CommandCodeApiClient(Session(Response(401, "denied")), "https://api.test", "secret")
    with pytest.raises(CommandCodeApiError, match="HTTP 401") as exc_info:
        asyncio.run(client.fetch_whoami())
    assert "denied" not in str(exc_info.value)


def test_client_raises_for_unknown_model_payload():
    client = CommandCodeApiClient(
        Session(Response(200, {"unexpected": True})), "https://api.test", "secret"
    )
    with pytest.raises(Exception, match="Unrecognized models response"):
        asyncio.run(client.fetch_models())


def test_client_rejects_empty_model_list() -> None:
    client = CommandCodeApiClient(
        Session(Response(200, {"object": "list", "data": []})),
        "https://api.test",
        "secret",
    )
    with pytest.raises(Exception, match="Unrecognized models response"):
        asyncio.run(client.fetch_models())


def test_client_models_omit_authorization_header() -> None:
    session = Session(Response(200, {"object": "list", "data": []}))
    client = CommandCodeApiClient(session, "https://api.test", "secret")
    try:
        asyncio.run(client.fetch_models())
    except Exception:
        pass
    _, kwargs = session.calls[0]
    assert "Authorization" not in kwargs["headers"]
