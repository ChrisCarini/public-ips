from __future__ import annotations

from pathlib import Path

import yaml

from public_ips.models import ProviderConfig


def load_provider_configs(root: Path) -> list[ProviderConfig]:
    configs: list[ProviderConfig] = []
    for path in sorted((root / "providers").glob("*.yaml")):
        payload = yaml.safe_load(path.read_text())
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid provider file: {path}")
        configs.append(
            ProviderConfig(
                provider_id=str(payload["provider_id"]),
                display_name=str(payload["display_name"]),
                output_dir=str(payload["output_dir"]),
                adapter=str(payload["adapter"]),
                source_urls=[str(v) for v in payload["source_urls"]],
                documentation_url=str(payload["documentation_url"]),
                attribution=str(payload.get("attribution", "Official provider source")),
                terms_url=(str(payload["terms_url"]) if payload.get("terms_url") else None),
                mappings={str(k): str(v) for k, v in dict(payload.get("mappings", {})).items()},
                uncategorized_fields=[
                    str(v) for v in list(payload.get("uncategorized_fields", []))
                ],
                min_ranges=int(payload.get("min_ranges", 0)),
                max_change_absolute=int(payload.get("max_change_absolute", 1000000)),
                max_change_percent=float(payload.get("max_change_percent", 100.0)),
                allow_non_global=bool(payload.get("allow_non_global", False)),
            )
        )
    return configs
