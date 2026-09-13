from __future__ import annotations

from typing import ClassVar, Protocol, cast

from public_ips.models import ProviderConfig, ProviderSnapshot, RawFetch


class HttpClient(Protocol):
    def get(self, url: str) -> tuple[int, bytes, str | None, str | None, str | None]: ...


class ProviderAdapter(Protocol):
    def fetch(self, client: HttpClient) -> RawFetch: ...

    def extract(self, raw: RawFetch) -> ProviderSnapshot: ...


class RegisteredProviderAdapter:
    _registry: ClassVar[dict[str, type[RegisteredProviderAdapter]]] = {}

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def __init_subclass__(cls, *, adapter_name: str | None = None, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if adapter_name is None:
            return
        existing = RegisteredProviderAdapter._registry.get(adapter_name)
        if existing is not None and existing is not cls:
            raise ValueError(f"Duplicate adapter registration: {adapter_name}")
        RegisteredProviderAdapter._registry[adapter_name] = cls

    @classmethod
    def create(cls, config: ProviderConfig) -> ProviderAdapter:
        adapter_cls = cls._registry.get(config.adapter)
        if adapter_cls is None:
            raise ValueError(f"Unknown adapter: {config.adapter}")
        return cast(ProviderAdapter, adapter_cls(config))
