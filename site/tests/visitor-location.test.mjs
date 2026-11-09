import assert from 'node:assert/strict';
import { test } from 'node:test';
import { VisitorLocation } from '../src/visitor-location.ts';

const setup = () => {
  const states = [];
  const requests = [];
  const visitor = new VisitorLocation((state) => states.push(state));
  const geolocation = {
    getCurrentPosition(success, failure, options) {
      requests.push({ success, failure, options });
    },
  };
  return { visitor, geolocation, states, requests };
};

test('location is requested only explicitly, without high-accuracy tracking', () => {
  const { visitor, geolocation, states, requests } = setup();
  assert.deepEqual(states, []);
  assert.deepEqual(requests, []);
  visitor.request(geolocation);
  assert.deepEqual(states, [{ status: 'pending' }]);
  assert.equal(requests.length, 1);
  assert.deepEqual(requests[0].options, {
    enableHighAccuracy: false, timeout: 10_000, maximumAge: 60_000,
  });
});

test('only rounded coordinates leave the location callback', () => {
  const { visitor, geolocation, states, requests } = setup();
  visitor.request(geolocation);
  requests[0].success({
    coords: { latitude: 37.7749, longitude: -122.4194, accuracy: 3, altitude: 123 },
    timestamp: 123456,
  });
  assert.deepEqual(states.at(-1), {
    status: 'ready', coordinates: { latitude: 37.8, longitude: -122.4 },
  });
  visitor.forget();
  assert.deepEqual(states.at(-1), { status: 'off' });
});

test('zero coordinates and geographic boundaries remain valid', () => {
  for (const coordinates of [
    { latitude: 0, longitude: 0 },
    { latitude: 90, longitude: 180 },
    { latitude: -90, longitude: -180 },
  ]) {
    const { visitor, geolocation, states, requests } = setup();
    visitor.request(geolocation);
    requests[0].success({ coords: coordinates });
    assert.deepEqual(states.at(-1), { status: 'ready', coordinates });
  }
});

test('invalid coordinates fail explicitly instead of drawing a fabricated location', () => {
  for (const coords of [
    { latitude: NaN, longitude: 0 }, { latitude: 0, longitude: Infinity },
    { latitude: 90.01, longitude: 0 }, { latitude: -90.01, longitude: 0 },
    { latitude: 0, longitude: 180.01 }, { latitude: 0, longitude: -180.01 },
  ]) {
    const { visitor, geolocation, states, requests } = setup();
    visitor.request(geolocation);
    requests[0].success({ coords });
    assert.equal(states.at(-1).status, 'error');
    assert.match(states.at(-1).message, /invalid location.*IP search still works/);
  }
});

test('permission denial, unavailable locations, and timeouts have actionable messages', () => {
  for (const [code, message] of [[1, /permission was denied/], [2, /unavailable/], [3, /timed out/], [99, /could not determine/]]) {
    const { visitor, geolocation, states, requests } = setup();
    visitor.request(geolocation);
    requests[0].failure({ code });
    assert.equal(states.at(-1).status, 'error');
    assert.match(states.at(-1).message, message);
    assert.match(states.at(-1).message, /IP search still works/);
  }
});

test('synchronous browser failures are surfaced without exposing raw error data', () => {
  const { visitor, states } = setup();
  visitor.request({ getCurrentPosition() { throw new Error('private browser details'); } });
  assert.equal(states.at(-1).status, 'error');
  assert.match(states.at(-1).message, /could not request location/);
  assert.doesNotMatch(states.at(-1).message, /private browser details/);
});

test('forgetting while permission is pending ignores late successes and failures', () => {
  const { visitor, geolocation, states, requests } = setup();
  visitor.request(geolocation);
  visitor.forget();
  requests[0].success({ coords: { latitude: 40.1234, longitude: 10.5678 } });
  requests[0].failure({ code: 1 });
  assert.deepEqual(states, [{ status: 'pending' }, { status: 'off' }]);
});

test('an older request cannot replace a newer location or its status', () => {
  const { visitor, geolocation, states, requests } = setup();
  visitor.request(geolocation);
  visitor.forget();
  visitor.request(geolocation);
  requests[1].success({ coords: { latitude: 10.1234, longitude: 20.5678 } });
  requests[0].success({ coords: { latitude: -10, longitude: -20 } });
  requests[0].failure({ code: 3 });
  assert.deepEqual(states.at(-1), {
    status: 'ready', coordinates: { latitude: 10.1, longitude: 20.6 },
  });
  assert.equal(states.length, 4);
});
