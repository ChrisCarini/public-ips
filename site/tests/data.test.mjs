import assert from 'node:assert/strict';
import { test } from 'node:test';
import ipaddr from 'ipaddr.js';
import {
  buildMarkers, containsAddress, decodeSearchIndex, listFileUrl, locateAddress, sortBySpecificity,
} from '../src/data.ts';

const entry = (provider, cidr, category = null) => ({
  provider, cidr, category, ip_family: cidr.includes(':') ? 'ipv6' : 'ipv4',
  path: `${provider}/${category ? `${category}/` : ''}ipv4.txt`,
  line: 1, anchor: `${provider}-${category}-${cidr}`, source_url: 'https://example.org/ranges',
});
const location = (cidr, network, continent, latitude, longitude) => ({
  cidr, network, continent, latitude, longitude,
  city: 'Example city', country: 'Example country', country_code: 'XX',
});
const root = entry('one.example', '8.8.8.0/24');
const category = entry('one.example', '8.8.8.0/24', 'dns');
const other = entry('two.example', '8.8.8.0/24');
const v6 = entry('one.example', '2001:4860::/32');
const unknown = entry('one.example', '1.1.1.0/24');
const index = { schema_version: 'v1', entries: [root, category, other, v6, unknown] };
const geo = {
  schema_version: 'v1', generated_at: '2026-09-01T00:00:00Z', database: 'test',
  entries: [
    location(root.cidr, '8.8.8.0/25', 'NA', 40, -75),
    location(root.cidr, '8.8.8.128/25', 'EU', 50, 10),
    location(v6.cidr, '2001:4860::/32', 'NA', 40, -75),
  ],
  unlocated_cidrs: [unknown.cidr],
};
const filters = { provider: '', family: '', continent: '' };

test('all providers and IP families appear, while unknowns are not fabricated', () => {
  const markers = buildMarkers(index, geo, filters);
  assert.equal(markers.length, 4);
  assert.deepEqual(new Set(markers.map((marker) => marker.provider)), new Set(['one.example', 'two.example']));
  assert.ok(markers.every((marker) => !marker.entries.includes(unknown)));
});

test('co-located ranges cluster per provider without losing list memberships', () => {
  const markers = buildMarkers(index, geo, filters);
  const northAmerica = markers.find((marker) => marker.provider === root.provider && marker.location.continent === 'NA');
  assert.deepEqual(northAmerica.entries, [root, category, v6]);
  assert.equal(northAmerica.segments.length, 2);
  assert.equal(new Set(markers.map((marker) => marker.id)).size, markers.length);
});

test('provider, family and continent filters intersect', () => {
  assert.equal(buildMarkers(index, geo, { ...filters, provider: 'two.example' }).length, 2);
  const markers = buildMarkers(index, geo, { provider: 'one.example', family: 'ipv6', continent: 'NA' });
  assert.equal(markers.length, 1);
  assert.deepEqual(markers[0].entries, [v6]);
  assert.equal(buildMarkers(index, geo, { ...filters, family: 'ipv6', continent: 'EU' }).length, 0);
  assert.equal(buildMarkers(index, geo, { ...filters, provider: 'missing' }).length, 0);
});

test('search locates the actual IP subnet rather than the beginning of a broad published range', () => {
  assert.equal(locateAddress(ipaddr.parse('8.8.8.8'), [root], geo).continent, 'NA');
  assert.equal(locateAddress(ipaddr.parse('8.8.8.200'), [root, category, other], geo).continent, 'EU');
  assert.equal(locateAddress(ipaddr.parse('2001:4860::8888'), [v6], geo).continent, 'NA');
  assert.equal(locateAddress(ipaddr.parse('1.1.1.1'), [unknown], geo), undefined);
  assert.equal(locateAddress(ipaddr.parse('8.8.8.8'), [], geo), undefined);
});

test('IPv4/IPv6 network containment includes both boundaries and excludes other families', () => {
  assert.ok(containsAddress(ipaddr.parse('8.8.8.0'), '8.8.8.0/24'));
  assert.ok(containsAddress(ipaddr.parse('8.8.8.255'), '8.8.8.0/24'));
  assert.ok(!containsAddress(ipaddr.parse('8.8.9.0'), '8.8.8.0/24'));
  assert.ok(containsAddress(ipaddr.parse('2001:4860:ffff:ffff:ffff:ffff:ffff:ffff'), '2001:4860::/32'));
  assert.ok(!containsAddress(ipaddr.parse('8.8.8.8'), '2001:4860::/32'));
  assert.ok(!containsAddress(ipaddr.parse('2001:4860::8888'), '8.8.8.0/24'));
});

test('memberships sort from individual addresses to the broadest ranges', () => {
  const entries = [
    entry('one.example', '0.0.0.0/0'),
    entry('one.example', '2001:db8::/32'),
    entry('one.example', '8.8.8.0/24'),
    entry('one.example', '2001:db8::1/128'),
    entry('one.example', '8.8.8.8/32'),
  ];
  assert.deepEqual(sortBySpecificity(entries).map((item) => item.cidr), [
    '2001:db8::1/128', '8.8.8.8/32', '8.8.8.0/24', '0.0.0.0/0', '2001:db8::/32',
  ]);
  assert.deepEqual(entries.map((item) => item.cidr), [
    '0.0.0.0/0', '2001:db8::/32', '8.8.8.0/24', '2001:db8::1/128', '8.8.8.8/32',
  ]);
});

test('zero coordinates are valid, and multiple segments at a location do not duplicate lists', () => {
  const samePlace = { ...geo, entries: [
    location(root.cidr, '8.8.8.0/25', 'AF', 0, 0),
    location(root.cidr, '8.8.8.128/25', 'AF', 0, 0),
  ] };
  const markers = buildMarkers(index, samePlace, filters);
  assert.equal(markers.length, 2);
  assert.deepEqual(markers[0].entries, [root, category]);
  assert.equal(markers[0].segments.length, 2);
});

test('compact Pages index preserves providers, families, memberships and source links', () => {
  const strings = ['one.example', '8.8.8.0/24', 'one.example/ipv4.txt', 'https://example.org/ranges',
    'dns', '2001:4860::/32', 'one.example/dns/ipv6.txt'];
  const decoded = decodeSearchIndex({
    schema_version: 'v2', strings, entries: [[0, -1, 4, 1, 2, 7, 3], [0, 4, 6, 5, 6, 8, 3]],
  });
  assert.deepEqual(decoded.entries.map(({ anchor, ...value }) => value), [
    { provider: strings[0], category: null, ip_family: 'ipv4', cidr: strings[1],
      path: strings[2], line: 7, source_url: strings[3] },
    { provider: strings[0], category: 'dns', ip_family: 'ipv6', cidr: strings[5],
      path: strings[6], line: 8, source_url: strings[3] },
  ]);
  assert.equal(buildMarkers(decoded, geo, filters).length, 2);
  assert.equal(decodeSearchIndex(index), index);
});

test('invalid compact indices fail clearly instead of decoding incorrect locations', () => {
  for (const input of [null, {}, { schema_version: 'v3', entries: [] },
    { schema_version: 'v2', entries: [], strings: null },
    { schema_version: 'v2', entries: [[0, -1, 4, 0, 0, 1, 0]], strings: [] },
    { schema_version: 'v2', entries: [[0, -1, 5, 0, 0, 1, 0]], strings: ['x'] },
    { schema_version: 'v2', entries: [[0, -1, 4, 0, 0, 0, 0]], strings: ['x'] }]) {
    assert.throws(() => decodeSearchIndex(input), /search index/i);
  }
});

test('list links use the deployed Pages snapshot and safely encode path segments', () => {
  assert.equal(listFileUrl('one.example/dns/ipv6.txt', '/public-ips/'),
    '/public-ips/one.example/dns/ipv6.txt');
  assert.equal(listFileUrl('one.example/service name/ipv4.txt', '/public-ips/'),
    '/public-ips/one.example/service%20name/ipv4.txt');
  for (const path of ['../secret', '/host/file', 'https://other.example/file']) {
    assert.throws(() => listFileUrl(path, '/public-ips/'), /Invalid published list path/);
  }
});
