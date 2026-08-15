from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from ipaddress import ip_network
from pathlib import Path

from public_ips.adapters.base import HttpClient
from public_ips.models import (
    FetchDocument,
    ProviderConfig,
    ProviderSnapshot,
    RawFetch,
    utc_now,
)
from public_ips.validation import parse_networks, validate_path_component

_CIDR_TOKEN = re.compile(r"^[0-9a-fA-F:.]+/[0-9]{1,3}$")


def _is_valid_cidr(value: object) -> bool:
    if not isinstance(value, str) or "/" not in value:
        return False
    try:
        ip_network(value, strict=True)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class GitHubAdapter:
    config: ProviderConfig

    def fetch(self, client: HttpClient) -> RawFetch:
        docs: dict[str, FetchDocument] = {}
        for url in self.config.source_urls:
            status, body, content_type, etag, last_modified = client.get(url)
            docs[url] = FetchDocument(
                url=url,
                body=body,
                content_type=content_type,
                status_code=status,
                etag=etag,
                last_modified=last_modified,
            )
        return RawFetch(provider_id=self.config.provider_id, retrieved_at=utc_now(), documents=docs)

    def extract(self, raw: RawFetch) -> ProviderSnapshot:
        doc = raw.documents[self.config.source_urls[0]]
        if doc.status_code != 200:
            raise ValueError(f"github fetch failed: status={doc.status_code}")
        payload = json.loads(doc.body)
        if not isinstance(payload, dict):
            raise ValueError("github response must be an object")

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

        mapped_fields = set(self.config.mappings.keys())
        for source_field, category in self.config.mappings.items():
            raw_list = payload.get(source_field, [])
            if not isinstance(raw_list, list):
                raise ValueError(f"github field '{source_field}' must be a list")
            if not all(isinstance(item, str) for item in raw_list):
                raise ValueError(f"github field '{source_field}' must contain only CIDR strings")
            self._add_category(
                snapshot,
                source_field,
                category,
                [item for item in raw_list if isinstance(item, str)],
            )

        for key, value in payload.items():
            if key in mapped_fields or not isinstance(value, list) or not value:
                continue

            valid_cidrs = [_is_valid_cidr(item) for item in value]
            if all(valid_cidrs):
                self._add_category(
                    snapshot,
                    key,
                    key,
                    [item for item in value if isinstance(item, str)],
                )
                continue

            if any(valid_cidrs) or any(
                isinstance(item, str) and _CIDR_TOKEN.fullmatch(item) for item in value
            ):
                raise ValueError(
                    f"github response field '{key}' contains malformed or mixed CIDR data"
                )

        return snapshot

    def _add_category(
        self,
        snapshot: ProviderSnapshot,
        source_field: str,
        category: str,
        cidrs: list[str],
    ) -> None:
        validate_path_component(category)
        if category in snapshot.categories:
            raise ValueError(
                f"github fields produce duplicate category '{category}' "
                f"(including '{source_field}')"
            )
        family = parse_networks(
            cidrs,
            allow_non_global=self.config.allow_non_global,
            warning_prefix=f"{self.config.provider_id}:{category}",
            warnings=snapshot.warnings,
        )
        snapshot.categories[category] = family
