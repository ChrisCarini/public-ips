# public-ips

`public-ips` collects IP ranges **published by or associated with** providers through official machine-readable sources.

## Providers

- `amazonaws.com` — source: `https://ip-ranges.amazonaws.com/ip-ranges.json`
- `anthropic.com` — source: `https://claude.com/crawling/bots.json`
- `apple.com` — source: `https://mask-api.icloud.com/egress-ip-ranges.csv`
- `atlassian.com` — source: `https://ip-ranges.atlassian.com/`
- `azure.microsoft.com` — source: `https://www.microsoft.com/en-us/download/details.aspx?id=56519`
- `bing.com` — source: `https://www.bing.com/toolbox/bingbot.json`
- `bunny.net` — source: `https://api.bunny.net/system/edgeserverlist`, `https://api.bunny.net/system/edgeserverlist/ipv6`
- `cloud.google.com` — source: `https://www.gstatic.com/ipranges/cloud.json`
- `cloudflare.com` — source: `https://api.cloudflare.com/client/v4/ips`
- `commoncrawl.org` — source: `https://index.commoncrawl.org/ccbot.json`
- `datadoghq.com` — source: `https://ip-ranges.datadoghq.com/`
- `digitalocean.com` — source: `https://www.digitalocean.com/geo/google.csv`
- `duckduckgo.com` — source: `https://duckduckgo.com/duckduckbot.json`
- `fastly.com` — source: `https://api.fastly.com/public-ip-list`
- `github.com` — source: `https://api.github.com/meta`
- `googlebot.com` — source: `https://developers.google.com/search/apis/ipranges/googlebot.json`
- `linode.com` — source: `https://geoip.linode.com/`
- `openai.com` — source: `https://openai.com/gptbot.json`, `https://openai.com/searchbot.json`, `https://openai.com/chatgpt-user.json`, `https://openai.com/adsbot.json`
- `oracle.com` — source: `https://docs.oracle.com/en-us/iaas/tools/public_ip_ranges.json`
- `perplexity.com` — source: `https://www.perplexity.com/perplexitybot.json`, `https://www.perplexity.com/perplexity-user.json`
- `pingdom.com` — source: `https://my.pingdom.com/probes/ipv4`, `https://my.pingdom.com/probes/ipv6`
- `statuscake.com` — source: `https://app.statuscake.com/Workfloor/Locations.php?format=json`, `https://app.statuscake.com/API/SpeedLocations/json`
- `stripe.com` — source: `https://stripe.com/files/ips/ips_webhooks.json`
- `tailscale.com` — source: `https://controlplane.tailscale.com/derpmap/default`
- `telegram.org` — source: `https://core.telegram.org/resources/cidr.txt`
- `uptimerobot.com` — source: `https://uptimerobot.com/inc/files/ips/IPv4.txt`, `https://uptimerobot.com/inc/files/ips/IPv6.txt`
- `vultr.com` — source: `https://geofeed.constant.com/?text`
- `zoom.us` — source: `https://assets.zoom.us/docs/ipranges/ZoomMeetings.txt`, `https://assets.zoom.us/docs/ipranges/ZoomMeetings-IPv6.txt`

### Source scope

- Bunny.net lists [CDN edge-server addresses](https://bunny.net/docs/cdn/connectivity),
  not all Bunny services.
- Linode's self-published geofeed is not a list of all Akamai IP space.
- Tailscale lists its [default DERP relays](https://tailscale.com/docs/reference/derp-servers),
  not tailnet devices, custom relays, or all Tailscale infrastructure.
- Telegram's published network prefixes are not a webhook-specific allowlist;
  [webhook documentation](https://core.telegram.org/bots/webhooks#the-short-version)
  specifies a narrower set.
- StatusCake includes uptime and Page Speed monitoring nodes. Its
  [IP documentation](https://www.statuscake.com/kb/knowledge-base/what-are-your-ips/)
  lists SSL monitoring and webhook alerting separately; those are not included.
- Vultr's [official IP-space feed](https://docs.vultr.com/vultr-ip-space)
  includes seven special-purpose entries: `192.0.2.0/24`, `198.51.100.0/24`,
  `203.0.113.0/24`, `2001:2::/48`, `2001:10::/28`, `2001:db8::/32`, and
  `2002::/16`. Its adapter excludes these with warnings rather than publishing
  them as Vultr public allocations. Other non-global entries still fail validation.
- OpenAI and DuckDuckGo list their published crawler/user-agent addresses,
  not all addresses owned or used by those companies.
- Zoom lists Meetings and Webinars connectivity ranges from its
  [firewall documentation](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0060548),
  not all Zoom products such as Phone or Contact Center.

### Requested providers not yet enabled

- **Facebook / Meta:** the public [geofeed](https://www.facebook.com/peering/geofeed/)
  covers a subset of Meta sources and restricts use to CDN services benefiting
  Meta users. General-purpose redistribution is deferred pending clarification
  of those terms.
- **Twitter / X:** no usable first-party downloadable IP list has been verified.
  Unofficial ASN/WHOIS-derived lists are not substituted for a provider-published feed.
- **Proton VPN:** unauthenticated requests to its server-list endpoints, including
  `https://vpn-api.proton.me/vpn/v1/logicals?SecureCoreFilter=all&WithState=true`,
  returned HTTP 400 during verification. Public access requirements need verification
  before enabling automated collection; this does not establish that authentication
  is required. A future integration must distinguish VPN entry and exit addresses.

## Data outputs

Per provider:

- `all.txt`, `ipv4.txt`, `ipv6.txt`
- `collapsed-all.txt`, `collapsed-ipv4.txt`, `collapsed-ipv6.txt` (derived compact coverage)
- `ranges.json`, `ranges.csv`, `CHANGELOG.md`

Root outputs committed to Git:

- `manifest.json`
- `changes.jsonl`
- `CHANGELOG.md`

Root outputs generated for deployment only (not committed, because they outgrow
GitHub's 100 MB per-file push limit):

- `ranges.csv` — every provider row, published at
  [`/public-ips/ranges.csv`](https://chriscarini.github.io/public-ips/ranges.csv)
- `search-index.json` — the full v1 index used by local tooling and the Pages build. Pages
  serves the separately generated compact v2 index at the same name,
  [`/public-ips/search-index.json`](https://chriscarini.github.io/public-ips/search-index.json)

Both are written into the repository root by `public-ips generate` and are ignored by Git.
Every push that commits generated data runs `python -m public_ips.size_guard`, which fails
with the offending paths and sizes before a push can be rejected by GitHub.

## Semantics

- Primary files preserve exact normalized source CIDRs (no collapsing/merging).
- Collapsed files are derived convenience outputs.
- The same CIDR can legitimately appear in multiple categories/providers.

## Automated update GitHub App

The scheduled **Update provider data** workflow creates its pull requests as a
GitHub App. This lets the repository treat the update branch as an internal,
trusted branch, so its CI workflows run without the **Approve workflows to run**
prompt that applies to untrusted contributions.

Set up the app as follows:

1. In GitHub, open **Settings** → **Developer settings** → **GitHub Apps** →
   **New GitHub App**. Give it a descriptive name such as
   `public-ips-updater`, set the homepage URL to this repository, and leave
   **Webhook** inactive; this workflow does not receive app events.
2. Under **Repository permissions**, grant exactly:
   - **Contents: Read and write** — creates and updates the data branch and
     commits generated provider data.
   - **Pull requests: Read and write** — opens, labels, updates, and enables
     auto-merge for the update pull request.
   - **Metadata: Read-only** — automatically included by GitHub Apps.

   Do not grant **Actions**, **Workflows**, **Administration**, organization,
   account, or webhook permissions. The app creates a branch in this repository;
   it does not dispatch workflows, edit workflow files, or administer repository
   settings.
3. Create the app, then select **Install App** and install it only on this
   repository. Approve the requested permissions if GitHub prompts for approval.
4. On the app's settings page, create a private key and download the generated
   `.pem` file. In this repository's **Settings** → **Secrets and variables** →
   **Actions**, create the secret `PUBLIC_IPS_UPDATE_APP_PRIVATE_KEY` whose value
   is the complete contents of that file, including its `BEGIN` and `END` lines.
   Treat this value as a credential and never commit it.
5. On that same GitHub App settings page, copy the **Client ID**. In this
   repository's **Settings** → **Secrets and variables** → **Actions** →
   **Variables**, create `PUBLIC_IPS_UPDATE_APP_CLIENT_ID` with that value.
6. Run **Update provider data** manually once from the **Actions** tab to verify
   that it creates a PR authored by `<app-slug>[bot]`. Subsequent scheduled
   update PRs use the same identity and their CI starts normally without manual
   workflow approval.

The workflow mints a short-lived installation token scoped to this repository
and explicitly requests only the two write permissions above. The private key
remains in GitHub Actions secrets; the generated token is masked and revoked
when the job finishes.

## Local development

```bash
python -m pip install -e .[dev]
public-ips generate --fixtures tests/fixtures --timestamp 2026-01-02T14:35:22+00:00
ruff check .
mypy src
pytest
public-ips check --fixtures tests/fixtures --timestamp 2026-01-02T14:35:22+00:00
npm --prefix site ci
npm --prefix site test
npm --prefix site run build
```

## Interactive globe

The [GitHub Pages explorer](https://chriscarini.github.io/public-ips/) shows a
rotatable globe with provider colors, combined provider/IP-family/continent
filters, and clickable location details linking to the published lists and sources.
Search a single IPv4 or IPv6 address to rotate to its estimated location, highlight
it, and display every matching list entry. Successful location searches clear globe
filters so the result is visible; CIDR searches remain list searches because a range
can span multiple locations.

- Drag to rotate; use pinch gestures or the zoom buttons to zoom. Keyboard users
  can focus the globe and use arrow keys and `+`/`-`, or browse the equivalent
  **mapped locations** list. Normal page scrolling is preserved outside the canvas;
  Ctrl/Command + wheel also zooms the globe.
- Dots group **address-range segments by provider and coordinates**, rather than
  enumerating individual addresses. Co-located providers have separate colored dots.
  Location details show the corresponding CIDRs, IP versions, and list memberships.
- Geolocation is approximate. Broad CIDRs can span countries, and anycast addresses
  can operate worldwide. Unknown locations are never guessed; those addresses still
  appear in search results. Coverage counts show ranges with at least one mapped
  segment, not the percentage of individual addresses geolocated.

### Geographic data and local preview

Every Pages deployment regenerates **all configured providers**, regardless of which
generated data is checked in. After the frontend build, the publisher creates a
deploy-only compact search index (v2, with shared strings and numeric entry rows),
copies the referenced text lists and their sibling `all.txt` files into
`site/dist`, preserving their exact contents and line numbers, and copies the
combined `ranges.csv` download alongside them. Search and list
links use this same snapshot; large generated indexes and lists are uploaded as
Pages artifacts, not committed to Git.

Pages builds download the current monthly
[DB-IP City Lite](https://db-ip.com/db/download/ip-to-city-lite) database
([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)), falling back to the
previous month only if the current download returns 404. Both IP families are
resolved **at build time**, intersecting published CIDRs with the database's subnets
so a search uses the queried IP's subnet, not a representative IP from a broad range.
All visitor searches run locally in the browser; no search is sent to an external
service. Geolocation is built from the full generated root index, alongside the
compact deployed index. Only the resulting `geolocation.json` is deployed;
the downloaded database is neither deployed nor committed.
The map uses public-domain Natural Earth land boundaries through `world-atlas`.

To preview the complete site (Python 3.12+, Node.js 22+):

```bash
python -m pip install -e '.[geo]'
npm --prefix site ci
npm --prefix site run build
public-ips generate
python -m public_ips.site --root . --output site/dist
python -m public_ips.geolocation --index search-index.json --output site/dist/geolocation.json --download
npm --prefix site run preview
```

Open the preview server's `/public-ips/` path. Optionally set
`PUBLIC_IPS_GITHUB_TOKEN` when generating to increase GitHub API rate limits;
Pages uses its built-in GitHub token. For offline builds, use
`public-ips generate --fixtures tests/fixtures` and replace `--download` with
`--database /path/to/dbip-city-lite.mmdb`. Regenerate the deployed snapshot and
geographic artifact whenever the root search index changes. If downloading or processing the
database fails, Pages deployment stops rather than publishing fabricated or
incomplete data. The exporter also fails explicitly if its lookup safety limit is
exceeded; `--max-lookups` can raise that limit for larger source lists. If geographic
data cannot be loaded in the browser, IP search remains usable.

## Safety disclaimer

This repository has no freshness SLA. Consumers must validate data and their own policy impacts before applying firewall/security changes.
