export type Coordinates = Pick<GeolocationCoordinates, 'latitude' | 'longitude'>;

export type VisitorLocationState =
  | { status: 'off' | 'pending' }
  | { status: 'ready'; coordinates: Coordinates }
  | { status: 'error'; message: string };

export class VisitorLocation {
  private version = 0;
  private onChange: (state: VisitorLocationState) => void;

  constructor(onChange: (state: VisitorLocationState) => void) {
    this.onChange = onChange;
  }

  request(geolocation: Pick<Geolocation, 'getCurrentPosition'>): void {
    const version = ++this.version;
    this.onChange({ status: 'pending' });
    const fail = (message: string): void => {
      if (version === this.version) {
        this.onChange({ status: 'error', message: `${message} IP search still works.` });
      }
    };
    try {
      geolocation.getCurrentPosition(({ coords }) => {
        if (version !== this.version) return;
        const { latitude, longitude } = coords;
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude) ||
            Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
          fail('Your browser returned an invalid location.');
          return;
        }
        this.onChange({
          status: 'ready',
          coordinates: {
            latitude: Math.round(latitude * 10) / 10,
            longitude: Math.round(longitude * 10) / 10,
          },
        });
      }, ({ code }) => {
        const messages: Record<number, string> = {
          1: 'Location permission was denied. You can allow access in your browser settings and try again.',
          2: 'Your location is unavailable. Please try again later.',
          3: 'The location request timed out. Please try again.',
        };
        fail(messages[code] ?? 'Your browser could not determine your location.');
      }, { enableHighAccuracy: false, timeout: 10_000, maximumAge: 60_000 });
    } catch {
      fail('Your browser could not request location. Check its location settings and try again.');
    }
  }

  forget(): void {
    // getCurrentPosition cannot be cancelled; ignore any result that arrives after forgetting.
    ++this.version;
    this.onChange({ status: 'off' });
  }
}
