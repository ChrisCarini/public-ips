import assert from 'node:assert/strict';
import { test } from 'node:test';
import { geoDistance, geoOrthographic, geoPath } from 'd3-geo';
import { createConnection } from '../src/connection.ts';

const coordinates = ([longitude, latitude]) => ({ longitude, latitude });
const create = (from, to) => createConnection(coordinates(from), coordinates(to));

test('the connection uses the actual endpoints and the shortest geographic arc', () => {
  const from = [-122.4, 37.8];
  const to = [-0.1, 51.5];
  const { path, focus } = create(from, to);
  assert.equal(path.type, 'LineString');
  assert.deepEqual(path.coordinates[0], from);
  assert.deepEqual(path.coordinates.at(-1), to);
  const midpoint = path.coordinates[1];
  assert.ok(Math.abs(geoDistance(from, midpoint) + geoDistance(midpoint, to) - geoDistance(from, to)) < 1e-10);
  assert.ok(geoDistance(from, focus) < Math.PI / 2);
  assert.ok(geoDistance(to, focus) < Math.PI / 2);
});

test('framing the endpoints also reveals a visibly curved flight-style path', () => {
  const { path, focus } = create([-122.4, 37.8], [-0.1, 51.5]);
  const projection = geoOrthographic().rotate([-focus[0], -focus[1]]).scale(300);
  const [from, midpoint, to] = path.coordinates.map(projection);
  const deviation = Math.abs(
    (to[0] - from[0]) * (midpoint[1] - from[1]) - (to[1] - from[1]) * (midpoint[0] - from[0]),
  ) / Math.hypot(to[0] - from[0], to[1] - from[1]);
  assert.ok(deviation > 15, `Expected a visible arc, got ${deviation}px of curvature`);
});

test('dateline crossings take the short route rather than crossing Greenwich', () => {
  const { path, focus } = create([179, 10], [-179, 10]);
  assert.ok(Math.abs(path.coordinates[1][0]) > 179);
  assert.ok(geoDistance(path.coordinates[0], path.coordinates.at(-1)) < 0.04);
  assert.ok(geoDistance(path.coordinates[0], focus) < Math.PI / 2);
  assert.ok(geoDistance(path.coordinates.at(-1), focus) < Math.PI / 2);
});

test('coincident, polar, and antipodal endpoints produce finite, renderable geometry', () => {
  for (const [from, to] of [
    [[0, 0], [0, 0]],
    [[180, 0], [-180, 0]],
    [[0, 90], [120, 45]],
    [[0, -90], [-120, -45]],
    [[0, 0], [180, 0]],
    [[0, 90], [0, -90]],
    [[12.3, 45.6], [-167.7, -45.6]],
    [[0, 0], [179.99999, 0.00001]],
  ]) {
    const { path, focus } = create(from, to);
    assert.ok([...path.coordinates.flat(), ...focus].every(Number.isFinite));
    const projection = geoOrthographic().rotate([-focus[0], -focus[1]]).clipAngle(90);
    const rendered = geoPath(projection)(path);
    assert.ok(rendered);
    assert.doesNotMatch(rendered, /NaN|Infinity/);
  }
});

test('the projection clips routes on the far side instead of drawing through the globe', () => {
  const { path } = create([160, 10], [-160, 10]);
  const projection = geoOrthographic().rotate([0, 0]).clipAngle(90);
  assert.equal(geoPath(projection)(path), null);
});
