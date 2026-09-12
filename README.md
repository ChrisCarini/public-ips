# public-ips

`public-ips` collects IP ranges **published by or associated with** providers through official machine-readable sources.

## Providers

- `amazonaws.com` — source: `https://ip-ranges.amazonaws.com/ip-ranges.json`
- `anthropic.com` — source: `https://claude.com/crawling/bots.json`
- `apple.com` — source: `https://mask-api.icloud.com/egress-ip-ranges.csv`
- `azure.microsoft.com` — source: `https://www.microsoft.com/en-us/download/details.aspx?id=56519`
- `bing.com` — source: `https://www.bing.com/toolbox/bingbot.json`
- `cloud.google.com` — source: `https://www.gstatic.com/ipranges/cloud.json`
- `cloudflare.com` — source: `https://api.cloudflare.com/client/v4/ips`
- `facebook.com` — source: `https://www.facebook.com/ips-v4`, `https://www.facebook.com/ips-v6`
- `github.com` — source: `https://api.github.com/meta`
- `googlebot.com` — source: `https://developers.google.com/search/apis/ipranges/googlebot.json`
- `openai.com` — source: `https://openai.com/gptbot.json`, `https://openai.com/searchbot.json`, `https://openai.com/chatgpt-user.json`
- `oracle.com` — source: `https://docs.oracle.com/en-us/iaas/tools/public_ip_ranges.json`
- `perplexity.com` — source: `https://www.perplexity.com/perplexitybot.json`
- `pingdom.com` — source: `https://my.pingdom.com/probes/ipv4`, `https://my.pingdom.com/probes/ipv6`

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
