from __future__ import annotations

from typing import Protocol

from public_ips.models import ProviderSnapshot, RawFetch


class HttpClient(Protocol):
    def get(self, url: str) -> tuple[int, bytes, str | None, str | None, str | None]: ...


class ProviderAdapter(Protocol):
    def fetch(self, client: HttpClient) -> RawFetch: ...

    def extract(self, raw: RawFetch) -> ProviderSnapshot: ...
