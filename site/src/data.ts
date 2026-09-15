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

export const listFileUrl = (path: string, base: string): string => {
  const parts = path.split('/');
  if (parts.some((part) => !part || part === '.' || part === '..')) {
    throw new Error('Invalid published list path.');
  }
  return `${base}${parts.map(encodeURIComponent).join('/')}`;
};

export const decodeSearchIndex = (data: unknown): SearchIndex => {
  if (!data || typeof data !== 'object') throw new Error('Invalid search index.');
  const index = data as Record<string, unknown>;
  if (!Array.isArray(index.entries)) throw new Error('Invalid search index entries.');
  if (index.schema_version === 'v1') return data as SearchIndex;
  if (index.schema_version !== 'v2' || !Array.isArray(index.strings)) {
    throw new Error('Unsupported search index.');
  }
  const strings: unknown[] = index.strings;
  const text = (id: unknown): string => {
    if (typeof id !== 'number' || !Number.isInteger(id) || typeof strings[id] !== 'string') {
      throw new Error('Invalid search index string reference.');
    }
    return strings[id] as string;
  };
  return {
    schema_version: 'v1',
    entries: index.entries.map((row: unknown) => {
      if (!Array.isArray(row) || row.length !== 7 ||
          ![4, 6].includes(row[2]) || !Number.isInteger(row[5]) || row[5] < 1) {
        throw new Error('Invalid search index row.');
      }
      return {
        provider: text(row[0]), category: row[1] === -1 ? null : text(row[1]),
        ip_family: row[2] === 4 ? 'ipv4' : 'ipv6', cidr: text(row[3]),
        path: text(row[4]), line: row[5], source_url: text(row[6]), anchor: '',
      };
    }),
  };
};

export const containsAddress = (address: ipaddr.IPv4 | ipaddr.IPv6, cidr: string): boolean => {
  const [network, prefix] = ipaddr.parseCIDR(cidr);
  return address.kind() === network.kind() && address.match([network, prefix]);
};

export const sortBySpecificity = (entries: SearchEntry[]): SearchEntry[] =>
  [...entries].sort((left, right) => {
    const [leftAddress, leftPrefix] = ipaddr.parseCIDR(left.cidr);
    const [rightAddress, rightPrefix] = ipaddr.parseCIDR(right.cidr);
    const leftHostBits = (leftAddress.kind() === 'ipv4' ? 32 : 128) - leftPrefix;
    const rightHostBits = (rightAddress.kind() === 'ipv4' ? 32 : 128) - rightPrefix;
    return leftHostBits - rightHostBits ||
      rightPrefix - leftPrefix ||
      left.cidr.localeCompare(right.cidr) ||
      left.provider.localeCompare(right.provider);
  });

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
