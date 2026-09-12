from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from ipaddress import ip_network
from pathlib import Path
from typing import Any

from public_ips.adapters.base import HttpClient
from public_ips.models import (
    FamilyNetworks,
    FetchDocument,
    ProviderConfig,
    ProviderSnapshot,
    RawFetch,
    utc_now,
)
from public_ips.validation import parse_networks, validate_path_component

_CIDR_OR_IP_TOKEN = re.compile(
    r"(?<![0-9A-Fa-f:.])(?:[0-9]{1,3}(?:\.[0-9]{1,3}){3}|[0-9A-Fa-f:]*:[0-9A-Fa-f:.]+)(?:/\d{1,3})?(?![0-9A-Fa-f:.])"
)
_AZURE_DOWNLOAD_URL = re.compile(
    r"https://download\.microsoft\.com/download/[^\"'<>]+ServiceTags_Public_[^\"'<>]+\.json"
)


def _fetch_configured_urls(config: ProviderConfig, client: HttpClient) -> RawFetch:
    docs: dict[str, FetchDocument] = {}
    for url in config.source_urls:
        status, body, content_type, etag, last_modified = client.get(url)
        docs[url] = FetchDocument(
            url=url,
            body=body,
            content_type=content_type,
            status_code=status,
            etag=etag,
            last_modified=last_modified,
        )
    return RawFetch(provider_id=config.provider_id, retrieved_at=utc_now(), documents=docs)


def _hash_documents(documents: dict[str, FetchDocument]) -> str:
    digest = hashlib.sha256()
    for url, doc in sorted(documents.items()):
        digest.update(url.encode("utf-8"))
        digest.update(b"\0")
        digest.update(doc.body)
        digest.update(b"\0")
    return digest.hexdigest()


def _category(value: str) -> str:
    category = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip().lower()).strip("._-")
    validate_path_component(category)
    return category


def _is_network(value: str) -> bool:
    if "/" not in value and "." not in value and ":" not in value:
        return False
    try:
        ip_network(value, strict=True)
    except ValueError:
        return False
    return True


def _extract_json_networks(payload: Any) -> list[str]:
    networks: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, str):
            if _is_network(value):
                networks.append(value)
            return
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if isinstance(value, dict):
            for item in value.values():
                visit(item)

    visit(payload)
    return networks


def _extract_text_networks(body: bytes) -> list[str]:
    text = body.decode("utf-8-sig")
    return [match.group(0) for match in _CIDR_OR_IP_TOKEN.finditer(text)]


def _family_from_cidrs(
    cidrs: list[str], *, config: ProviderConfig, warning_prefix: str
) -> FamilyNetworks:
    return parse_networks(
        cidrs,
        allow_non_global=config.allow_non_global,
        warning_prefix=warning_prefix,
        warnings=[],
    )


def _add_category(
    snapshot: ProviderSnapshot,
    category: str,
    cidrs: list[str],
    config: ProviderConfig,
) -> None:
    if not cidrs:
        return
    snapshot.categories[category] = parse_networks(
        cidrs,
        allow_non_global=config.allow_non_global,
        warning_prefix=f"{config.provider_id}:{category}",
        warnings=snapshot.warnings,
    )


@dataclass(frozen=True)
class GenericCidrAdapter:
    config: ProviderConfig

    def fetch(self, client: HttpClient) -> RawFetch:
        return _fetch_configured_urls(self.config, client)

    def extract(self, raw: RawFetch) -> ProviderSnapshot:
        cidrs: list[str] = []
        for doc in raw.documents.values():
            if doc.status_code != 200:
                raise ValueError(f"{self.config.provider_id} fetch failed: status={doc.status_code}")
            try:
                cidrs.extend(_extract_json_networks(json.loads(doc.body)))
            except json.JSONDecodeError:
                cidrs.extend(_extract_text_networks(doc.body))

        family = _family_from_cidrs(
            cidrs, config=self.config, warning_prefix=self.config.provider_id
        )
        return ProviderSnapshot(
            provider_id=self.config.provider_id,
            display_name=self.config.display_name,
            output_dir=Path(self.config.output_dir),
            source_urls=self.config.source_urls,
            documentation_url=self.config.documentation_url,
            attribution=self.config.attribution,
            terms_url=self.config.terms_url,
            uncategorized=family,
            source_body_hash=_hash_documents(raw.documents),
        )


@dataclass(frozen=True)
class AwsIpRangesAdapter:
    config: ProviderConfig

    def fetch(self, client: HttpClient) -> RawFetch:
        return _fetch_configured_urls(self.config, client)

    def extract(self, raw: RawFetch) -> ProviderSnapshot:
        doc = raw.documents[self.config.source_urls[0]]
        if doc.status_code != 200:
            raise ValueError(f"aws fetch failed: status={doc.status_code}")
        payload = json.loads(doc.body)
        if not isinstance(payload, dict):
            raise ValueError("aws response must be an object")

        categories: dict[str, list[str]] = {}
        for key, cidr_key in (("prefixes", "ip_prefix"), ("ipv6_prefixes", "ipv6_prefix")):
            records = payload.get(key, [])
            if not isinstance(records, list):
                raise ValueError(f"aws field '{key}' must be a list")
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError(f"aws field '{key}' must contain objects")
                service = str(record.get("service", "amazon"))
                cidr = record.get(cidr_key)
                if isinstance(cidr, str):
                    categories.setdefault(_category(service), []).append(cidr)

        snapshot = ProviderSnapshot(
            provider_id=self.config.provider_id,
            display_name=self.config.display_name,
            output_dir=Path(self.config.output_dir),
            source_urls=self.config.source_urls,
            documentation_url=self.config.documentation_url,
            attribution=self.config.attribution,
            terms_url=self.config.terms_url,
            source_body_hash=hashlib.sha256(doc.body).hexdigest(),
        )
        for category, cidrs in sorted(categories.items()):
            _add_category(snapshot, category, cidrs, self.config)
        return snapshot


@dataclass(frozen=True)
class AzureServiceTagsAdapter:
    config: ProviderConfig

    def fetch(self, client: HttpClient) -> RawFetch:
        raw = _fetch_configured_urls(self.config, client)
        landing = raw.documents[self.config.source_urls[0]]
        if landing.status_code != 200:
            return raw
        html = landing.body.decode("utf-8", errors="replace")
        match = _AZURE_DOWNLOAD_URL.search(html)
        if match is None:
            return raw
        url = match.group(0).replace("&amp;", "&")
        status, body, content_type, etag, last_modified = client.get(url)
        raw.documents[url] = FetchDocument(
            url=url,
            body=body,
            content_type=content_type,
            status_code=status,
            etag=etag,
            last_modified=last_modified,
        )
        return raw

    def extract(self, raw: RawFetch) -> ProviderSnapshot:
        docs = list(raw.documents.values())
        doc = docs[-1]
        if doc.status_code != 200:
            raise ValueError(f"azure fetch failed: status={doc.status_code}")
        payload = json.loads(doc.body)
        if not isinstance(payload, dict):
            raise ValueError("azure response must be an object")
        values = payload.get("values", [])
        if not isinstance(values, list):
            raise ValueError("azure response field 'values' must be a list")

        snapshot = ProviderSnapshot(
            provider_id=self.config.provider_id,
            display_name=self.config.display_name,
            output_dir=Path(self.config.output_dir),
            source_urls=self.config.source_urls,
            documentation_url=self.config.documentation_url,
            attribution=self.config.attribution,
            terms_url=self.config.terms_url,
            source_body_hash=_hash_documents({doc.url: doc}),
        )
        categories: dict[str, list[str]] = {}
        for record in values:
            if not isinstance(record, dict):
                raise ValueError("azure values must contain objects")
            properties = record.get("properties", {})
            if not isinstance(properties, dict):
                raise ValueError("azure value properties must be an object")
            service = str(properties.get("systemService") or record.get("name") or "azure")
            prefixes = properties.get("addressPrefixes", [])
            if not isinstance(prefixes, list) or not all(isinstance(item, str) for item in prefixes):
                raise ValueError("azure addressPrefixes must be a list of strings")
            categories.setdefault(_category(service), []).extend(prefixes)
        for category, cidrs in sorted(categories.items()):
            _add_category(snapshot, category, cidrs, self.config)
        return snapshot


@dataclass(frozen=True)
class GoogleCloudAdapter:
    config: ProviderConfig

    def fetch(self, client: HttpClient) -> RawFetch:
        return _fetch_configured_urls(self.config, client)

    def extract(self, raw: RawFetch) -> ProviderSnapshot:
        doc = raw.documents[self.config.source_urls[0]]
        if doc.status_code != 200:
            raise ValueError(f"google cloud fetch failed: status={doc.status_code}")
        payload = json.loads(doc.body)
        if not isinstance(payload, dict):
            raise ValueError("google cloud response must be an object")
        prefixes = payload.get("prefixes", [])
        if not isinstance(prefixes, list):
            raise ValueError("google cloud field 'prefixes' must be a list")

        snapshot = ProviderSnapshot(
            provider_id=self.config.provider_id,
            display_name=self.config.display_name,
            output_dir=Path(self.config.output_dir),
            source_urls=self.config.source_urls,
            documentation_url=self.config.documentation_url,
            attribution=self.config.attribution,
            terms_url=self.config.terms_url,
            source_body_hash=hashlib.sha256(doc.body).hexdigest(),
        )
        categories: dict[str, list[str]] = {}
        for record in prefixes:
            if not isinstance(record, dict):
                raise ValueError("google cloud prefixes must contain objects")
            service = str(record.get("service", "google_cloud"))
            cidr = record.get("ipv4Prefix") or record.get("ipv6Prefix")
            if isinstance(cidr, str):
                categories.setdefault(_category(service), []).append(cidr)
        for category, cidrs in sorted(categories.items()):
            _add_category(snapshot, category, cidrs, self.config)
        return snapshot
