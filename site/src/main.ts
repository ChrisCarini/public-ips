import './styles.css';
import * as ipaddr from 'ipaddr.js';

type SearchEntry = {
  provider: string;
  category: string | null;
  ip_family: 'ipv4' | 'ipv6';
  cidr: string;
  path: string;
  line: number;
  anchor: string;
  source_url: string;
};

type SearchIndex = { schema_version: string; entries: SearchEntry[] };

const app = document.querySelector<HTMLDivElement>('#app');
if (!app) throw new Error('missing app element');

const params = new URLSearchParams(window.location.search);
const queryParam = params.get('q') ?? '';

app.innerHTML = `
  <h1>public-ips</h1>
  <p>Ranges published by or associated with providers.</p>
  <label for="query">Search IP or CIDR</label>
  <input id="query" value="${queryParam}" placeholder="203.0.113.1 or 2001:db8::/32" />
  <button id="run">Search</button>
  <p id="error" role="alert"></p>
  <ul id="results"></ul>
`;

const queryInput = document.querySelector<HTMLInputElement>('#query')!;
const runButton = document.querySelector<HTMLButtonElement>('#run')!;
const error = document.querySelector<HTMLParagraphElement>('#error')!;
const results = document.querySelector<HTMLUListElement>('#results')!;

const parseInput = (raw: string): { type: 'addr' | 'cidr'; value: ipaddr.IPv4 | ipaddr.IPv6; prefix?: number } => {
  const input = raw.trim();
  if (!input) throw new Error('Enter an IPv4, IPv6, or CIDR query.');
  if (input.includes('/')) {
    const [addr, prefix] = ipaddr.parseCIDR(input);
    return { type: 'cidr', value: addr, prefix };
  }
  return { type: 'addr', value: ipaddr.parse(input) };
};

const matchRelation = (
  query: ReturnType<typeof parseInput>,
  publishedCidr: string
): 'exact' | 'published_contains_query' | 'query_contains_published' | 'partial_overlap' | 'none' => {
  const [published, publishedPrefix] = ipaddr.parseCIDR(publishedCidr);
  if (query.type === 'addr') {
    if (published.kind() !== query.value.kind()) return 'none';
    return query.value.match([published, publishedPrefix]) ? 'published_contains_query' : 'none';
  }
  if (published.kind() !== query.value.kind()) return 'none';
  const queryTuple: [ipaddr.IPv4 | ipaddr.IPv6, number] = [query.value, query.prefix!];
  const same = published.toNormalizedString() === query.value.toNormalizedString() && publishedPrefix === query.prefix;
  if (same) return 'exact';
  const queryStartInPub = query.value.match([published, publishedPrefix]);
  const pubStartInQuery = published.match(queryTuple);
  if (queryStartInPub && !pubStartInQuery) return 'published_contains_query';
  if (pubStartInQuery && !queryStartInPub) return 'query_contains_published';
  if (pubStartInQuery || queryStartInPub) return 'partial_overlap';
  return 'none';
};

const runSearch = async (): Promise<void> => {
  error.textContent = '';
  results.innerHTML = '';
  try {
    const query = parseInput(queryInput.value);
    const url = new URL(window.location.href);
    url.searchParams.set('q', queryInput.value.trim());
    history.replaceState(null, '', url);

    const index = (await fetch('/search-index.json').then((r) => r.json())) as SearchIndex;
    const matches = index.entries
      .map((entry) => ({ entry, rel: matchRelation(query, entry.cidr) }))
      .filter((item) => item.rel !== 'none');

    if (!matches.length) {
      results.innerHTML = '<li>No matches.</li>';
      return;
    }

    for (const item of matches) {
      const li = document.createElement('li');
      li.textContent = `${item.entry.provider} ${item.entry.category ? `(${item.entry.category})` : ''} ${item.entry.cidr} - ${item.rel} @ ${item.entry.path}:${item.entry.line}`;
      results.appendChild(li);
    }
  } catch (e) {
    error.textContent = e instanceof Error ? e.message : 'Invalid query';
  }
};

runButton.addEventListener('click', () => void runSearch());
if (queryParam) {
  void runSearch();
}
