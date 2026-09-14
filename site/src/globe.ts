import { geoDistance, geoGraticule10, geoOrthographic, geoPath } from 'd3-geo';
import { feature } from 'topojson-client';
import type { Topology, GeometryCollection } from 'topojson-specification';
import landData from 'world-atlas/land-110m.json';
import type { Marker } from './data';

const land = feature(
  landData as unknown as Topology,
  landData.objects.land as GeometryCollection,
);
const graticule = geoGraticule10();

export class Globe {
  private context: CanvasRenderingContext2D;
  private projection = geoOrthographic().rotate([-15, -15]).clipAngle(90);
  private markers: Marker[] = [];
  private visible: { marker: Marker; x: number; y: number }[] = [];
  private selected = '';
  private width = 0;
  private height = 0;
  private zoom = 1;
  private frame = 0;
  private animation = 0;
  private pointers = new Map<number, { x: number; y: number }>();
  private moved = false;
  private travel = 0;
  private observer: ResizeObserver;

  constructor(
    private canvas: HTMLCanvasElement,
    private colors: Map<string, string>,
    private onSelect: (markers: Marker[]) => void,
  ) {
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Your browser does not support the globe canvas. IP search is still available.');
    this.context = context;
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(canvas);
    canvas.addEventListener('pointerdown', (event) => {
      cancelAnimationFrame(this.animation);
      if (!this.pointers.size) { this.moved = false; this.travel = 0; }
      this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (this.pointers.size > 1) this.moved = true;
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener('pointermove', (event) => this.move(event));
    canvas.addEventListener('pointerup', (event) => {
      if (!this.pointers.has(event.pointerId)) return;
      this.pointers.delete(event.pointerId);
      if (!this.moved) {
        const rect = canvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        const hits = this.visible
          .map((point) => ({ ...point, distance: Math.hypot(point.x - x, point.y - y) }))
          .filter((point) => point.distance < 16)
          .sort((a, b) => a.distance - b.distance)
          .map((point) => point.marker);
        if (hits.length) this.onSelect(hits);
      }
    });
    canvas.addEventListener('pointercancel', (event) => {
      this.pointers.delete(event.pointerId);
      this.moved = true;
    });
    canvas.addEventListener('lostpointercapture', (event) => this.pointers.delete(event.pointerId));
    canvas.addEventListener('keydown', (event) => {
      const turns: Record<string, [number, number]> = {
        ArrowLeft: [-12, 0], ArrowRight: [12, 0], ArrowUp: [0, 12], ArrowDown: [0, -12],
      };
      if (turns[event.key]) {
        event.preventDefault();
        this.rotate(...turns[event.key]);
      } else if (event.key === '+' || event.key === '=') {
        event.preventDefault(); this.changeZoom(1.2);
      } else if (event.key === '-') {
        event.preventDefault(); this.changeZoom(1 / 1.2);
      }
    });
    canvas.addEventListener('wheel', (event) => {
      // Normal scrolling still works on a page dominated by the globe.
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      this.changeZoom(Math.exp(-event.deltaY * 0.002));
    }, { passive: false });
  }

  setMarkers(markers: Marker[]): void {
    this.markers = markers;
    this.drawSoon();
  }

  select(id = ''): void {
    this.selected = id;
    this.drawSoon();
  }

  focus(marker: Marker): void {
    cancelAnimationFrame(this.animation);
    this.selected = marker.id;
    const start = this.projection.rotate();
    const target = [-marker.location.longitude, -marker.location.latitude];
    const delta = ((target[0] - start[0] + 540) % 360) - 180;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const started = performance.now();
    const tick = (now: number): void => {
      const progress = reducedMotion ? 1 : Math.min(1, (now - started) / 700);
      const eased = progress * progress * (3 - 2 * progress);
      this.projection.rotate([start[0] + delta * eased, start[1] + (target[1] - start[1]) * eased]);
      this.drawSoon();
      if (progress < 1) this.animation = requestAnimationFrame(tick);
    };
    this.animation = requestAnimationFrame(tick);
  }

  rotate(longitude: number, latitude: number): void {
    cancelAnimationFrame(this.animation);
    const current = this.projection.rotate();
    this.projection.rotate([
      ((current[0] + longitude + 540) % 360) - 180,
      Math.max(-90, Math.min(90, current[1] + latitude)),
    ]);
    this.drawSoon();
  }

  changeZoom(factor: number): void {
    this.zoom = Math.max(1, Math.min(5, this.zoom * factor));
    this.resize();
  }

  reset(): void {
    cancelAnimationFrame(this.animation);
    this.zoom = 1;
    this.projection.rotate([-15, -15]);
    this.resize();
  }

  private move(event: PointerEvent): void {
    const previous = this.pointers.get(event.pointerId);
    if (!previous) return;
    const next = { x: event.clientX, y: event.clientY };
    const other = [...this.pointers.entries()].find(([id]) => id !== event.pointerId)?.[1];
    if (other) {
      const before = Math.hypot(previous.x - other.x, previous.y - other.y);
      const after = Math.hypot(next.x - other.x, next.y - other.y);
      if (before > 0) this.changeZoom(after / before);
    } else {
      const dx = next.x - previous.x;
      const dy = next.y - previous.y;
      this.travel += Math.hypot(dx, dy);
      if (this.travel > 5) this.moved = true;
      this.rotate(dx * 0.35 / this.zoom, -dy * 0.35 / this.zoom);
    }
    this.pointers.set(event.pointerId, next);
  }

  private resize(): void {
    this.width = this.canvas.clientWidth;
    this.height = this.canvas.clientHeight;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.round(this.width * ratio);
    this.canvas.height = Math.round(this.height * ratio);
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.projection
      .translate([this.width / 2, this.height / 2])
      .scale(Math.min(this.width, this.height) * 0.44 * this.zoom);
    this.drawSoon();
  }

  private drawSoon(): void {
    if (this.frame) return;
    this.frame = requestAnimationFrame(() => { this.frame = 0; this.draw(); });
  }

  private draw(): void {
    const ctx = this.context;
    ctx.clearRect(0, 0, this.width, this.height);
    const path = geoPath(this.projection, ctx);
    ctx.beginPath(); path({ type: 'Sphere' });
    ctx.fillStyle = '#102c46'; ctx.fill();
    ctx.strokeStyle = '#527b99'; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.save(); ctx.clip();
    ctx.beginPath(); path(graticule);
    ctx.strokeStyle = '#21415c'; ctx.lineWidth = 0.7; ctx.stroke();
    ctx.beginPath(); path(land);
    ctx.fillStyle = '#31586a'; ctx.fill();
    ctx.strokeStyle = '#639092'; ctx.lineWidth = 0.5; ctx.stroke();

    this.visible = [];
    const rotation = this.projection.rotate();
    const center: [number, number] = [-rotation[0], -rotation[1]];
    const colocated = new Map<string, Marker[]>();
    for (const marker of this.markers) {
      const { latitude, longitude } = marker.location;
      if (geoDistance([longitude, latitude], center) >= Math.PI / 2) continue;
      const key = `${latitude}|${longitude}`;
      const group = colocated.get(key) ?? [];
      group.push(marker);
      colocated.set(key, group);
    }
    for (const group of colocated.values()) {
      group.forEach((marker, i) => {
        const projected = this.projection([marker.location.longitude, marker.location.latitude]);
        if (!projected) return;
        const angle = i * Math.PI * 2 / group.length;
        const offset = group.length > 1 ? Math.min(12, 3 + group.length) : 0;
        const x = projected[0] + Math.cos(angle) * offset;
        const y = projected[1] + Math.sin(angle) * offset;
        const radius = this.projection.scale();
        if (Math.hypot(x - this.width / 2, y - this.height / 2) > radius - 4) return;
        if (x < -16 || y < -16 || x > this.width + 16 || y > this.height + 16) return;
        this.visible.push({ marker, x, y });
        ctx.beginPath(); ctx.arc(x, y, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = this.colors.get(marker.provider)!; ctx.fill();
        ctx.strokeStyle = '#071827'; ctx.lineWidth = 0.8; ctx.stroke();
      });
    }
    const selected = this.visible.find(({ marker }) => marker.id === this.selected);
    if (selected) {
      ctx.beginPath(); ctx.arc(selected.x, selected.y, 9, 0, Math.PI * 2);
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 2.5; ctx.stroke();
      ctx.beginPath(); ctx.arc(selected.x, selected.y, 4, 0, Math.PI * 2);
      ctx.fillStyle = this.colors.get(selected.marker.provider)!; ctx.fill();
    }
    ctx.restore();
  }
}
