from __future__ import annotations

from importlib import import_module
from pathlib import Path
from pkgutil import iter_modules

from public_ips.adapters.base import ProviderAdapter, RegisteredProviderAdapter
from public_ips.models import ProviderConfig


def _load_adapter_modules() -> None:
    for module in iter_modules([str(Path(__file__).parent)]):
        if module.name == "base":
            continue
        import_module(f"{__name__}.{module.name}")


_load_adapter_modules()


def adapter_for(config: ProviderConfig) -> ProviderAdapter:
    return RegisteredProviderAdapter.create(config)


__all__ = ["adapter_for"]
