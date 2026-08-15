from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from public_ips.adapters.base import HttpClient
from public_ips.models import FetchDocument, ProviderConfig, ProviderSnapshot, RawFetch, utc_now
from public_ips.validation import parse_networks


@dataclass(frozen=True)
class CloudflareAdapter:
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
            raise ValueError(f"cloudflare fetch failed: status={doc.status_code}")
        payload = json.loads(doc.body)
        if not isinstance(payload, dict):
            raise ValueError("cloudflare response must be an object")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("cloudflare response missing result object")

        ipv4_raw = result.get("ipv4_cidrs", [])
        ipv6_raw = result.get("ipv6_cidrs", [])
        if not isinstance(ipv4_raw, list) or not isinstance(ipv6_raw, list):
            raise ValueError("cloudflare result ip lists must be lists")

        combined = [str(x) for x in ipv4_raw] + [str(x) for x in ipv6_raw]
        family = parse_networks(
            combined,
            allow_non_global=self.config.allow_non_global,
            warning_prefix=self.config.provider_id,
            warnings=[],
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
            source_body_hash=hashlib.sha256(doc.body).hexdigest(),
        )
