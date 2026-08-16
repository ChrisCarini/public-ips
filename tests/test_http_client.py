from __future__ import annotations

import httpx
import pytest

from public_ips.http_client import RetryingHttpClient


class _DummyResponse:
    status_code = 200
    content = b"{}"
    headers: dict[str, str] = {}


class _DummyClient:
    def __init__(self, *_: object, **__: object) -> None:
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def __enter__(self) -> _DummyClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, url: str, headers: dict[str, str] | None = None) -> _DummyResponse:
        self.calls.append((url, headers))
        return _DummyResponse()


@pytest.fixture
def dummy_httpx_client(monkeypatch: pytest.MonkeyPatch) -> _DummyClient:
    client = _DummyClient()
    monkeypatch.setattr(httpx, "Client", lambda **_: client)
    return client


def test_retrying_http_client_sets_github_auth_headers(
    monkeypatch: pytest.MonkeyPatch, dummy_httpx_client: _DummyClient
) -> None:
    monkeypatch.setenv("PUBLIC_IPS_GITHUB_TOKEN", "test-token")
    client = RetryingHttpClient()

    client.get("https://api.github.com/meta")

    _, headers = dummy_httpx_client.calls[0]
    assert headers is not None
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["Authorization"].endswith("test-token")
    assert headers["User-Agent"] == "public-ips-updater"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_retrying_http_client_does_not_send_github_token_to_other_domains(
    monkeypatch: pytest.MonkeyPatch, dummy_httpx_client: _DummyClient
) -> None:
    monkeypatch.setenv("PUBLIC_IPS_GITHUB_TOKEN", "test-token")
    client = RetryingHttpClient()

    client.get("https://api.cloudflare.com/client/v4/ips")

    _, headers = dummy_httpx_client.calls[0]
    assert headers is not None
    assert "Authorization" not in headers
    assert headers["User-Agent"] == "public-ips-updater"
