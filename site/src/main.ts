import './styles.css';
import ipaddr from 'ipaddr.js';
import { Globe } from './globe';
import {
  buildMarkers, locateAddress, continents, decodeSearchIndex, groupSearchEntries, listFileUrl,
  sortBySpecificity,
} from './data';
import type { GeoIndex, Marker, SearchEntry, SearchIndex } from './data';

const app = document.querySelector<HTMLDivElement>('#app');
if (!app) throw new Error('missing app element');

const params = new URLSearchParams(window.location.search);
const queryParam = params.get('q') ?? '';

app.innerHTML = `
  <header>
    <p class="eyebrow">THE INTERNET, MAPPED</p>
    <h1>public-ips <span>explorer</span></h1>
    <p>Explore the networks published by or associated with providers around the world.</p>
  </header>
  <form id="search" class="search-bar">
    <label for="query">Find an IP address or CIDR</label>
    <div class="search-fields">
      <input id="query" placeholder="203.0.113.1 or 2001:db8::/32" autocomplete="off" spellcheck="false" />
      <button id="run" type="submit">Search & locate</button>
    </div>
  </form>
  <p id="error" role="alert"></p>
  <p id="search-status" role="status"></p>
  <section aria-labelledby="globe-title">
    <div class="section-heading"><h2 id="globe-title">A world of networks</h2><span class="badge">IPv4 + IPv6</span></div>
    <div class="filters">
      <label>Provider<select id="provider"><option value="">All providers</option></select></label>
      <label>IP version<select id="family"><option value="">IPv4 + IPv6</option><option value="ipv4">IPv4 only</option><option value="ipv6">IPv6 only</option></select></label>
      <label>Continent<select id="continent"><option value="">All continents</option></select></label>
      <button id="clear-filters" type="button">Clear filters</button>
    </div>
    <p id="globe-status" role="status">Loading geographic data…</p>
    <div class="explorer">
      <div class="globe-stage">
        <canvas id="globe" tabindex="0" role="img" aria-label="Interactive globe of provider IP ranges" aria-describedby="globe-help">
          Use the mapped locations list below to explore the same locations without the globe.
        </canvas>
        <div class="globe-controls" aria-label="Globe controls">
          <button id="rotate-left" type="button" aria-label="Rotate globe left">←</button>
          <button id="rotate-right" type="button" aria-label="Rotate globe right">→</button>
          <button id="zoom-in" type="button" aria-label="Zoom in">+</button>
          <button id="zoom-out" type="button" aria-label="Zoom out">−</button>
          <button id="reset-view" type="button">Reset view</button>
        </div>
        <p id="globe-help">Drag to rotate · Scroll or pinch to zoom · Tap a dot to explore<br>Keyboard: arrow keys and + / −. Or use the mapped locations list below.</p>
      </div>
      <aside id="details" aria-labelledby="details-title">
        <h3 id="details-title">Explore a location</h3>
        <p>Select a colored dot or search for an IP to see its approximate location and published list memberships.</p>
      </aside>
    </div>
    <ul id="legend" aria-label="Provider color legend"></ul>
    <p class="geo-note">Dots group geolocated address ranges by provider and location, not individual hosts.
      Locations are estimates, not physical server positions. Anycast networks may operate worldwide.
      Unlocated addresses remain searchable and are not placed on the globe.</p>
    <p class="attribution">IP geolocation by <a href="https://db-ip.com">DB-IP</a>
      (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>).
      Map: Natural Earth, via world-atlas. <span id="geo-date"></span></p>
    <details id="location-browser"><summary>Browse mapped locations (keyboard and screen reader friendly)</summary>
      <ul id="locations"></ul><button id="more-locations" type="button" hidden>Show more locations</button>
    </details>
  </section>
  <section class="examples-section">
    <h2>Example searches</h2>
    <p>Select an example IP to search the published ranges for that provider.</p>
    <ul id="examples"></ul>
  </section>
`;

const queryInput = document.querySelector<HTMLInputElement>('#query')!;
queryInput.value = queryParam;
const error = document.querySelector<HTMLParagraphElement>('#error')!;
const examples = document.querySelector<HTMLUListElement>('#examples')!;
const providerFilter = document.querySelector<HTMLSelectElement>('#provider')!;
const familyFilter = document.querySelector<HTMLSelectElement>('#family')!;
const continentFilter = document.querySelector<HTMLSelectElement>('#continent')!;
const globeStatus = document.querySelector<HTMLParagraphElement>('#globe-status')!;
const searchStatus = document.querySelector<HTMLParagraphElement>('#search-status')!;
const details = document.querySelector<HTMLElement>('#details')!;
const locations = document.querySelector<HTMLUListElement>('#locations')!;
const moreLocations = document.querySelector<HTMLButtonElement>('#more-locations')!;
const colors = new Map<string, string>();
const palette = ['#59d8ff', '#ffb454', '#d8a0ff', '#6ee7ac', '#ff809c', '#fff08a', '#8ba9ff',
  '#ff946c', '#b4e478', '#f4a5e0', '#65e3d3', '#dfc7a3', '#b5c9ed'];
let globe: Globe | undefined;
let searchIndex: SearchIndex | undefined;
let geoIndex: GeoIndex | undefined;
let markers: Marker[] = [];
let locationLimit = 50;
let searchVersion = 0;

for (const [code, name] of Object.entries(continents)) {
  continentFilter.add(new Option(name, code));
}

const externalLink = (label: string, href: string): HTMLAnchorElement => {
  const link = document.createElement('a');
  link.textContent = label;
  link.href = href;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  return link;
};

const publishedListUrl = (path: string): string => listFileUrl(path, import.meta.env.BASE_URL);

const revealGlobe = (): void => {
  document.querySelector<HTMLCanvasElement>('#globe')!.scrollIntoView({
    block: 'center',
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
  });
};

const locationName = (marker: Marker): string =>
  [marker.location.city, marker.location.country, continents[marker.location.continent]].filter(Boolean).join(', ');

const appendMemberships = (memberships: SearchEntry[]): void => {
  const groupedMemberships = groupSearchEntries(sortBySpecificity(memberships));
  const listHeading = document.createElement('h4');
  listHeading.textContent = `Published list memberships (${memberships.length.toLocaleString()})`;
  const list = document.createElement('ul');
  const more = document.createElement('button');
  more.textContent = 'Show more memberships';
  let shown = 0;
  const appendNext = (): void => {
    for (const group of groupedMemberships.slice(shown, shown + 50)) {
      const item = document.createElement('li');
      const cidr = document.createElement('strong');
      cidr.textContent = `${group.cidr} · ${group.ip_family.toUpperCase()}`;
      const sources = document.createElement('ul');
      for (const entry of group.entries) {
        const source = document.createElement('li');
        source.append(
          externalLink(`${entry.provider} / ${entry.category ?? 'all services'} (line ${entry.line})`, publishedListUrl(entry.path)),
          ' · ', externalLink('combined list', publishedListUrl(entry.path.replace(/ipv[46]\.txt$/, 'all.txt'))),
        );
        // Source URLs are remote metadata; only expose web links.
        if (/^https?:\/\//i.test(entry.source_url)) source.append(' · ', externalLink('source', entry.source_url));
        sources.append(source);
      }
      item.append(cidr, sources);
      list.append(item);
    }
    shown += 50;
    more.hidden = shown >= groupedMemberships.length;
  };
  more.addEventListener('click', appendNext);
  appendNext();
  details.append(listHeading, list, more);
};

const showDetails = (
  marker: Marker,
  alternatives: Marker[] = [],
  address?: string,
  memberships: SearchEntry[] = marker.entries,
): void => {
  globe?.select(marker.id);
  details.classList.add('has-selection');
  details.replaceChildren();
  const heading = document.createElement('h3');
  heading.id = 'details-title';
  heading.tabIndex = -1;
  heading.textContent = address ?? locationName(marker);
  const close = document.createElement('button');
  close.textContent = 'Close details';
  close.className = 'close-details';
  close.addEventListener('click', () => {
    globe?.select();
    details.classList.remove('has-selection');
    details.innerHTML = '<h3 id="details-title">Explore a location</h3><p>Select a dot or search for an IP to explore.</p>';
    document.querySelector<HTMLCanvasElement>('#globe')!.focus({ preventScroll: true });
  });
  const summary = document.createElement('p');
  summary.textContent = `${marker.provider} · ${locationName(marker)}`;
  const coordinates = document.createElement('p');
  coordinates.className = 'muted';
  coordinates.textContent = `Approximate location: ${marker.location.latitude.toFixed(2)}°, ${marker.location.longitude.toFixed(2)}°.`;
  const note = document.createElement('p');
  note.className = 'muted';
  note.textContent = address
    ? 'Estimated IP location from the matching geolocation subnet. This does not identify a person or an exact server.'
    : `${new Set(marker.entries.map((entry) => entry.cidr)).size.toLocaleString()} published ranges intersect this location. A range can span multiple locations.`;
  details.append(close, heading, summary, coordinates, note);
  if (alternatives.length > 1) {
    const label = document.createElement('p');
    label.textContent = 'Other dots at this location:';
    details.append(label);
    for (const alternative of alternatives) {
      const button = document.createElement('button');
      button.className = 'nearby';
      button.textContent = `${alternative.provider} — ${locationName(alternative)}`;
      button.addEventListener('click', () => showDetails(alternative, alternatives));
      details.append(button);
    }
  }
  appendMemberships(memberships);
  heading.focus({ preventScroll: true });
};

const showSearchMemberships = (query: string, memberships: SearchEntry[]): void => {
  details.classList.add('has-selection');
  details.replaceChildren();
  const heading = document.createElement('h3');
  heading.id = 'details-title';
  heading.textContent = query;
  const summary = document.createElement('p');
  summary.textContent = memberships.length
    ? 'Published ranges matching this search, ordered from most specific to least specific.'
    : 'No published list memberships match this search.';
  details.append(heading, summary);
  if (memberships.length) appendMemberships(memberships);
};

const renderLocations = (): void => {
  locations.replaceChildren();
  for (const marker of markers.slice(0, locationLimit)) {
    const item = document.createElement('li');
    const button = document.createElement('button');
    button.textContent = `${marker.provider} — ${locationName(marker)} (${new Set(marker.entries.map((entry) => entry.cidr)).size} ranges)`;
    button.addEventListener('click', () => { globe?.focus(marker); showDetails(marker); revealGlobe(); });
    item.append(button);
    locations.append(item);
  }
  moreLocations.hidden = locationLimit >= markers.length;
};

const applyFilters = (): void => {
  if (!searchIndex || !geoIndex) return;
  markers = buildMarkers(searchIndex, geoIndex, {
    provider: providerFilter.value, family: familyFilter.value, continent: continentFilter.value,
  });
  globe?.setMarkers(markers);
  globe?.select();
  details.classList.remove('has-selection');
  details.innerHTML = '<h3 id="details-title">Explore a location</h3><p>Select a dot or search for an IP to explore.</p>';
  const eligible = searchIndex.entries.filter((entry) =>
    (!providerFilter.value || entry.provider === providerFilter.value) &&
    (!familyFilter.value || entry.ip_family === familyFilter.value));
  const total = new Set(eligible.map((entry) => entry.cidr)).size;
  const located = new Set(markers.flatMap((marker) => marker.entries.map((entry) => entry.cidr))).size;
  globeStatus.textContent = `${markers.length.toLocaleString()} provider locations · ${located.toLocaleString()} of ${total.toLocaleString()} unique ranges mapped${continentFilter.value ? ` in ${continents[continentFilter.value]}` : ''}.` +
    (markers.length ? '' : ' No mapped locations match these filters.');
  locationLimit = 50;
  renderLocations();
  for (const item of document.querySelectorAll<HTMLElement>('#legend li')) {
    item.classList.toggle('dimmed', Boolean(providerFilter.value && item.dataset.provider !== providerFilter.value));
  }
};

let indexPromise: Promise<SearchIndex> | undefined;
const loadIndex = (): Promise<SearchIndex> => {
  indexPromise ??= fetch(`${import.meta.env.BASE_URL}search-index.json`)
    .then(async (response) => {
      if (!response.ok) throw new Error('Unable to load the search index.');
      return decodeSearchIndex(await response.json());
    })
    .catch((loadError: unknown) => {
      indexPromise = undefined;
      throw loadError;
    });
  return indexPromise;
};

const initializeGlobe = async (): Promise<void> => {
  try {
    searchIndex = await loadIndex();
    const providers = [...new Set(searchIndex.entries.map((entry) => entry.provider))].sort();
    const legend = document.querySelector<HTMLUListElement>('#legend')!;
    providers.forEach((provider, i) => {
      const color = palette[i % palette.length];
      colors.set(provider, color);
      providerFilter.add(new Option(provider, provider));
      const item = document.createElement('li');
      item.dataset.provider = provider;
      const swatch = document.createElement('span');
      swatch.className = 'swatch';
      swatch.style.backgroundColor = color;
      item.append(swatch, provider);
      legend.append(item);
    });
    globe = new Globe(document.querySelector<HTMLCanvasElement>('#globe')!, colors,
      (hits) => showDetails(hits[0], hits));
    const response = await fetch(`${import.meta.env.BASE_URL}geolocation.json`);
    if (!response.ok) throw new Error('Geographic data is unavailable. IP search still works; please try again later.');
    const data = await response.json() as GeoIndex;
    if (data.schema_version !== 'v1' || !Array.isArray(data.entries)) {
      throw new Error('Unsupported geographic data. IP search is still available.');
    }
    geoIndex = data;
    document.querySelector('#geo-date')!.textContent =
      `Database: ${data.database}. Generated ${data.generated_at.slice(0, 10)}.`;
    applyFilters();
  } catch (loadError) {
    globeStatus.textContent = 'Geographic data is unavailable. IP search still works; please try again later.';
    console.warn('Unable to initialize the globe:', loadError);
  }
};

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

const renderExamples = async (): Promise<void> => {
  try {
    const index = await loadIndex();
    const providerExamples = new Map<string, string>();

    for (const entry of index.entries) {
      if (!providerExamples.has(entry.provider)) {
        const [address] = ipaddr.parseCIDR(entry.cidr);
        providerExamples.set(entry.provider, address.toNormalizedString());
      }
    }

    const fragment = document.createDocumentFragment();
    for (const [provider, address] of providerExamples) {
      const li = document.createElement('li');
      const link = document.createElement('a');
      const url = new URL(window.location.href);
      url.searchParams.set('q', address);
      link.href = url.toString();
      link.textContent = `${provider}: ${address}`;
      link.addEventListener('click', (event) => {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        queryInput.value = address;
        void runSearch();
      });
      li.appendChild(link);
      fragment.appendChild(li);
    }
    examples.replaceChildren(fragment);
  } catch (renderError) {
    console.error(renderError);
    examples.replaceChildren();
    const li = document.createElement('li');
    li.textContent = 'Example searches are unavailable.';
    examples.appendChild(li);
  }
};

const runSearch = async (): Promise<void> => {
  const version = ++searchVersion;
  error.textContent = '';
  searchStatus.textContent = '';
  globe?.select();
  details.classList.remove('has-selection');
  details.innerHTML = '<h3 id="details-title">Explore a location</h3><p>Select a dot or search for an IP to explore.</p>';
  try {
    const query = parseInput(queryInput.value);
    const url = new URL(window.location.href);
    url.searchParams.set('q', queryInput.value.trim());
    history.replaceState(null, '', url);

    const index = await loadIndex();
    if (version !== searchVersion) return;
    const relations = new Map<string, ReturnType<typeof matchRelation>>();
    const matches = index.entries
      .map((entry) => {
        let rel = relations.get(entry.cidr);
        if (!rel) {
          rel = matchRelation(query, entry.cidr);
          relations.set(entry.cidr, rel);
        }
        return { entry, rel };
      })
      .filter((item) => item.rel !== 'none');

    if (!matches.length) {
      showSearchMemberships(queryInput.value.trim(), []);
      return;
    }

    searchStatus.textContent = `${matches.length.toLocaleString()} matching list entries. Search covers all providers, independently of globe filters.`;
    const matchingEntries = sortBySpecificity(matches.map(({ entry }) => entry));
    showSearchMemberships(queryInput.value.trim(), matchingEntries);
    if (query.type === 'addr') {
      await globeReady;
      if (version !== searchVersion) return;
      if (!geoIndex || !globe) {
        searchStatus.textContent += ' Geographic data is unavailable; list matches are shown below.';
        return;
      }
      const segment = locateAddress(query.value, matchingEntries, geoIndex);
      if (!segment) {
        searchStatus.textContent += ' This IP is in the published lists, but has no known location. It has not been placed on the globe.';
        return;
      }
      const filtersChanged = Boolean(providerFilter.value || familyFilter.value || continentFilter.value);
      providerFilter.value = ''; familyFilter.value = ''; continentFilter.value = '';
      applyFilters();
      const marker = markers.find((candidate) => candidate.segments.includes(segment));
      if (marker) {
        globe.focus(marker);
        showDetails(marker, [], query.value.toString(), matchingEntries);
        revealGlobe();
        searchStatus.textContent += ` Approximate location highlighted: ${locationName(marker)}.${filtersChanged ? ' Globe filters were cleared to reveal the match.' : ''}`;
      }
    } else {
      searchStatus.textContent += ' Search a single IP address to locate it on the globe; CIDRs can span many locations.';
    }
  } catch (e) {
    if (version === searchVersion) error.textContent = e instanceof Error ? e.message : 'Invalid query';
  }
};

document.querySelector('#search')!.addEventListener('submit', (event) => {
  event.preventDefault();
  void runSearch();
});
for (const filter of [providerFilter, familyFilter, continentFilter]) {
  filter.addEventListener('change', applyFilters);
}
document.querySelector('#clear-filters')!.addEventListener('click', () => {
  providerFilter.value = ''; familyFilter.value = ''; continentFilter.value = '';
  applyFilters();
});
document.querySelector('#rotate-left')!.addEventListener('click', () => globe?.rotate(-20, 0));
document.querySelector('#rotate-right')!.addEventListener('click', () => globe?.rotate(20, 0));
document.querySelector('#zoom-in')!.addEventListener('click', () => globe?.changeZoom(1.25));
document.querySelector('#zoom-out')!.addEventListener('click', () => globe?.changeZoom(0.8));
document.querySelector('#reset-view')!.addEventListener('click', () => globe?.reset());
moreLocations.addEventListener('click', () => { locationLimit += 50; renderLocations(); });
details.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') details.querySelector<HTMLButtonElement>('.close-details')?.click();
});
const globeReady = initializeGlobe();
void renderExamples();
if (queryParam) {
  void runSearch();
}
