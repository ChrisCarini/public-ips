# public-ips

`public-ips` collects IP ranges **published by or associated with** providers through official machine-readable sources.

## Providers

- `github.com` — source: `https://api.github.com/meta`
- `cloudflare.com` — source: `https://api.cloudflare.com/client/v4/ips`

## Data outputs

Per provider:

- `all.txt`, `ipv4.txt`, `ipv6.txt`
- `collapsed-all.txt`, `collapsed-ipv4.txt`, `collapsed-ipv6.txt` (derived compact coverage)
- `ranges.json`, `ranges.csv`, `CHANGELOG.md`

Root outputs:

- `manifest.json`
- `ranges.csv`
- `search-index.json`
- `changes.jsonl`
- `CHANGELOG.md`

## Semantics

- Primary files preserve exact normalized source CIDRs (no collapsing/merging).
- Collapsed files are derived convenience outputs.
- The same CIDR can legitimately appear in multiple categories/providers.

## Local development

```bash
python -m pip install -e .[dev]
public-ips generate --fixtures tests/fixtures --timestamp 2026-01-02T14:35:22+00:00
ruff check .
mypy src
pytest
public-ips check --fixtures tests/fixtures --timestamp 2026-01-02T14:35:22+00:00
npm --prefix site ci
npm --prefix site run build
```

## Safety disclaimer

This repository has no freshness SLA. Consumers must validate data and their own policy impacts before applying firewall/security changes.
