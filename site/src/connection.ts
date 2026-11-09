import { geoDistance, geoInterpolate } from 'd3-geo';
import type { Coordinates } from './visitor-location';

type Point = [number, number];
export type Connection = {
  path: { type: 'LineString'; coordinates: Point[] };
  focus: Point;
};

const radians = Math.PI / 180;
const cartesian = ([longitude, latitude]: Point): [number, number, number] => [
  Math.cos(latitude * radians) * Math.cos(longitude * radians),
  Math.cos(latitude * radians) * Math.sin(longitude * radians),
  Math.sin(latitude * radians),
];

export const createConnection = (origin: Coordinates, destination: Coordinates): Connection => {
  const from: Point = [origin.longitude, origin.latitude];
  const to: Point = [destination.longitude, destination.latitude];
  const distance = geoDistance(from, to);
  if (distance < 1e-8) {
    return { path: { type: 'LineString', coordinates: [from, to] }, focus: to };
  }

  // Antipodes have no unique shortest route. A perpendicular waypoint avoids unstable interpolation.
  const antipodal = distance > Math.PI - 1e-6;
  const midpoint: Point = antipodal
    ? [from[0], from[1] >= 0 ? from[1] - 90 : from[1] + 90]
    : geoInterpolate(from, to)(0.5);
  const a = cartesian(from);
  const middle = cartesian(midpoint);
  const normal = [
    a[1] * middle[2] - a[2] * middle[1],
    a[2] * middle[0] - a[0] * middle[2],
    a[0] * middle[1] - a[1] * middle[0],
  ];
  const length = Math.hypot(...normal);
  // Viewing slightly off the great-circle plane reveals the arc instead of an edge-on straight line.
  const tilt = 20 * radians;
  const view = middle.map((value, i) => value * Math.cos(tilt) + normal[i] / length * Math.sin(tilt));
  const focus: Point = antipodal ? to : [
    Math.atan2(view[1], view[0]) / radians,
    Math.atan2(view[2], Math.hypot(view[0], view[1])) / radians,
  ];
  return { path: { type: 'LineString', coordinates: [from, midpoint, to] }, focus };
};
