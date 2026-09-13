import ipaddr from 'ipaddr.js';

export type SearchEntry = {
  provider: string;
  category: string | null;
  ip_family: 'ipv4' | 'ipv6';
  cidr: string;
  path: string;
  line: number;
  anchor: string;
  source_url: string;
};

export type SearchIndex = { schema_version: string; entries: SearchEntry[] };
export type GeoEntry = {
  cidr: string;
  network: string;
  latitude: number;
  longitude: number;
  city: string | null;
  country: string | null;
  country_code: string | null;
  continent: string;
};
export type GeoIndex = {
  schema_version: string;
  generated_at: string;
  database: string;
  entries: GeoEntry[];
  unlocated_cidrs: string[];
};
export type Marker = {
  id: string;
  provider: string;
  location: GeoEntry;
  entries: SearchEntry[];
  segments: GeoEntry[];
};
export type Filters = { provider: string; family: string; continent: string };

export const continents: Record<string, string> = {
  AF: 'Africa', AN: 'Antarctica', AS: 'Asia', EU: 'Europe',
  NA: 'North America', OC: 'Oceania', SA: 'South America',
};

export const githubFileUrl = (path: string, line: number): string =>
  `https://github.com/ChrisCarini/public-ips/blob/main/${path}#L${line}`;

export const containsAddress = (address: ipaddr.IPv4 | ipaddr.IPv6, cidr: string): boolean => {
  const [network, prefix] = ipaddr.parseCIDR(cidr);
  return address.kind() === network.kind() && address.match([network, prefix]);
};

export const locateAddress = (
  address: ipaddr.IPv4 | ipaddr.IPv6,
  matches: SearchEntry[],
  geo: GeoIndex,
): GeoEntry | undefined => {
  const cidrs = new Set(matches.map((entry) => entry.cidr));
  return geo.entries.find((entry) => cidrs.has(entry.cidr) && containsAddress(address, entry.network));
};

export const buildMarkers = (index: SearchIndex, geo: GeoIndex, filters: Filters): Marker[] => {
  const byCidr = new Map<string, SearchEntry[]>();
  for (const entry of index.entries) {
    if (filters.provider && entry.provider !== filters.provider) continue;
    if (filters.family && entry.ip_family !== filters.family) continue;
    const entries = byCidr.get(entry.cidr) ?? [];
    entries.push(entry);
    byCidr.set(entry.cidr, entries);
  }
  const markers = new Map<string, Marker>();
  const memberships = new Map<string, Set<SearchEntry>>();
  for (const location of geo.entries) {
    if (filters.continent && location.continent !== filters.continent) continue;
    for (const entry of byCidr.get(location.cidr) ?? []) {
      const id = `${entry.provider}|${location.latitude}|${location.longitude}`;
      let marker = markers.get(id);
      if (!marker) {
        marker = { id, provider: entry.provider, location, entries: [], segments: [] };
        markers.set(id, marker);
        memberships.set(id, new Set());
      }
      const seen = memberships.get(id)!;
      if (!seen.has(entry)) {
        marker.entries.push(entry);
        seen.add(entry);
      }
      // A CIDR can belong to many lists; its geographic segment only needs storing once.
      if (marker.segments[marker.segments.length - 1] !== location) marker.segments.push(location);
    }
  }
  return [...markers.values()];
};
