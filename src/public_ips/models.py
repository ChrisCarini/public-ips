from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from ipaddress import IPv4Network, IPv6Network
from pathlib import Path
from typing import Any

Network = IPv4Network | IPv6Network


@dataclass(frozen=True)
class FetchDocument:
    url: str
    body: bytes
    content_type: str | None
    status_code: int
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True)
class RawFetch:
    provider_id: str
    retrieved_at: datetime
    documents: dict[str, FetchDocument]


@dataclass
class FamilyNetworks:
    ipv4: set[IPv4Network] = field(default_factory=set)
    ipv6: set[IPv6Network] = field(default_factory=set)

    def add(self, network: Network) -> None:
        if network.version == 4:
            self.ipv4.add(network)
        else:
            self.ipv6.add(network)

    def union(self, other: FamilyNetworks) -> None:
        self.ipv4.update(other.ipv4)
        self.ipv6.update(other.ipv6)


@dataclass
class ProviderSnapshot:
    provider_id: str
    display_name: str
    output_dir: Path
    source_urls: list[str]
    documentation_url: str
    attribution: str
    terms_url: str | None
    uncategorized: FamilyNetworks = field(default_factory=FamilyNetworks)
    categories: dict[str, FamilyNetworks] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    source_body_hash: str = ""


@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    display_name: str
    output_dir: str
    adapter: str
    source_urls: list[str]
    documentation_url: str
    attribution: str
    terms_url: str | None
    mappings: dict[str, str] = field(default_factory=dict)
    uncategorized_fields: list[str] = field(default_factory=list)
    min_ranges: int = 0
    max_change_absolute: int = 1000000
    max_change_percent: float = 100.0
    allow_non_global: bool = False


@dataclass
class GenerationResult:
    provider: str
    changed: bool
    warnings: list[str]
    error: str | None = None


@dataclass
class ChangeEvent:
    schema_version: str
    event_id: str
    event_type: str
    timestamp_utc: str
    provider: str
    normalized_hash: str
    source_body_hash: str
    category: str | None = None
    ip_family: str | None = None
    operation: str | None = None
    cidr: str | None = None
    counts: dict[str, Any] | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)
