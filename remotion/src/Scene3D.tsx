// 3D data scenes (Three.js through @remotion/three, software GL, no GPU): bars3d, globe, network3d. Ported from infogen (Three.tsx).
// Spec per kind is the same JSON as infogen's docs/SCENES.md. Numbers come from a docgen data file, never typed in.
import React, {useLayoutEffect, useMemo} from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {useThree} from '@react-three/fiber';
import * as THREE from 'three';
import {geoEquirectangular, geoPath} from 'd3-geo';
import {feature} from 'topojson-client';
import world from 'world-atlas/countries-110m.json';
import {Backdrop, Footnote, Heading, Palette, PALETTE, SANS, beatAt, findCountry, fmtNumber, pop, prog, useStage} from './kit3d';

export type Scene3DFields = {
  title?: string; kicker?: string; source?: string; seconds: number; camera?: any; beats?: (number | null)[];
  items?: any[]; unit?: string; prefix?: string; decimals?: number; max?: number;
  focus?: [number, number]; spin?: number; highlight?: any[]; pins?: any[]; arcs?: any[];
  nodes?: any[]; links?: any[];
};
export type Scene3DProps = Scene3DFields & {kind: 'bars3d' | 'globe' | 'network3d'; width: number; height: number; fps: number; palette?: Partial<Palette>};

type P = Scene3DFields & {p: Palette};
type Rng = [number, number];
type Cam = {az: Rng; el: Rng; dist: Rng};
const FOV = 38;
const PRESETS: Record<string, Cam> = {
  orbit: {az: [-18, 18], el: [20, 20], dist: [1, 1]},
  push_in: {az: [6, 6], el: [22, 16], dist: [1.3, 0.88]},
  rise: {az: [10, 10], el: [4, 38], dist: [1, 1]},
  still: {az: [12, 12], el: [22, 22], dist: [1, 1]},
};
const cam = (spec: any, fallback = 'orbit'): Cam => {
  if (spec && typeof spec === 'object') {
    const r = (v: any, d: Rng): Rng => (Array.isArray(v) && v.length === 2 && v.every((x) => typeof x === 'number') ? [v[0], v[1]] : d);
    return {az: r(spec.az, [0, 0]), el: r(spec.el, [22, 22]), dist: r(spec.dist, [1, 1])};
  }
  return PRESETS[spec as string] || PRESETS[fallback];
};

// camera position for this frame (spherical around `target`), and a projector that puts HTML labels over 3D points
const useRig = (spec: Cam, base: number, target: [number, number, number]) => {
  const f = useCurrentFrame(); const {durationInFrames, width, height} = useVideoConfig();
  const t = interpolate(f, [0, Math.max(durationInFrames - 1, 1)], [0, 1], {easing: Easing.inOut(Easing.sin)});
  const L = (r: Rng) => r[0] + (r[1] - r[0]) * t;
  const az = L(spec.az) * Math.PI / 180, el = L(spec.el) * Math.PI / 180, d = base * L(spec.dist);
  const pos: [number, number, number] = [target[0] + d * Math.cos(el) * Math.sin(az), target[1] + d * Math.sin(el), target[2] + d * Math.cos(el) * Math.cos(az)];
  const camera = useMemo(() => new THREE.PerspectiveCamera(FOV, width / height, 0.1, 500), [width, height]);
  camera.position.set(...pos); camera.lookAt(...target); camera.updateMatrixWorld(); camera.updateProjectionMatrix();
  const project = (v: THREE.Vector3) => { const q = v.clone().project(camera); return {x: (q.x * 0.5 + 0.5) * width, y: (1 - (q.y * 0.5 + 0.5)) * height, behind: q.z > 1}; };
  return {pos, target, project, eye: new THREE.Vector3(...pos)};
};

// distance at which a half-width of `half` world units fills the frame width (what limits a 9:16 frame)
const fitWidth = (half: number, width: number, height: number) => half / (Math.tan(FOV * Math.PI / 360) * (width / height));

// drives the canvas camera from the rig (the canvas renders on demand, so it must be asked to)
const Rig: React.FC<{pos: number[]; target: number[]}> = ({pos, target}) => {
  const {camera, invalidate} = useThree();
  useLayoutEffect(() => { camera.position.set(pos[0], pos[1], pos[2]); camera.lookAt(target[0], target[1], target[2]); camera.updateProjectionMatrix(); invalidate(); });
  return null;
};

const Stage: React.FC<{p: Palette; seed: number; rig: {pos: number[]; target: number[]}; title?: string; kicker?: string; source?: string; children: React.ReactNode; labels: React.ReactNode}> =
  ({p, seed, rig, title, kicker, source, children, labels}) => {
    const {width, height} = useVideoConfig();
    return (
      <AbsoluteFill>
        <Backdrop p={p} />
        <ThreeCanvas width={width} height={height} camera={{fov: FOV, near: 0.1, far: 500, position: rig.pos as any}} style={{position: 'absolute', inset: 0}}>
          <Rig pos={rig.pos} target={rig.target} />
          <ambientLight intensity={0.85} />
          <directionalLight position={[6, 9, 7]} intensity={2.4} />
          <directionalLight position={[-7, 3, -5]} intensity={0.7} color={p.accent2} />
          {children}
        </ThreeCanvas>
        <AbsoluteFill style={{pointerEvents: 'none'}}>{labels}</AbsoluteFill>
        <Heading title={title} kicker={kicker} p={p} />
        <Footnote text={source} p={p} />
      </AbsoluteFill>
    );
  };

const Tag: React.FC<{x: number; y: number; text: string; p: Palette; u: number; a: number; strong?: boolean; size?: number}> = ({x, y, text, p, u, a, strong, size = 30}) => (
  <div style={{position: 'absolute', left: x, top: y, transform: `translate(-50%, -50%) scale(${0.7 + 0.3 * Math.min(a, 1)})`, opacity: Math.min(a * 1.5, 1), fontFamily: SANS,
    fontWeight: strong ? 900 : 800, fontSize: size * u, color: strong ? p.accent : p.text, whiteSpace: 'nowrap', textShadow: `0 ${2 * u}px ${8 * u}px rgba(0,0,0,0.75)`, fontVariantNumeric: 'tabular-nums'}}>{text}</div>
);

// ---------------------------------------------------------------- bars3d
export const Bars3D: React.FC<P> = ({p, title, kicker, items = [], unit = '', prefix = '', decimals, max, camera, beats, seconds, source}) => {
  const f = useCurrentFrame(); const {fps, u, width, height} = useStage();
  const n = Math.max(items.length, 1); const mx = max ?? Math.max(...items.map((i: any) => Number(i.value) || 0), 1);
  const decOf = (v: any) => decimals ?? (String(v).split('.')[1] || '').length; const fit = width < height ? 0.72 : 1;
  const gap = Math.min(1.8, 9 / n), bw = gap * 0.68, H = 4.8;
  const hfov = 2 * Math.atan(Math.tan(FOV * Math.PI / 360) * (width / height));
  const base = Math.max((n * gap * 0.62) / Math.tan(hfov / 2), 13) * 1.1;
  const target: [number, number, number] = [0, 2.1, 0];
  const rig = useRig(cam(camera), base, target);
  const anyHi = items.some((x: any) => x.highlight);
  const bars = items.map((it: any, i: number) => {
    const at = beatAt(beats, i, items.length, seconds, 0.45, 0.55); const k = prog(f, fps, at, 1.1); const a = pop(f, fps, at, {damping: 16, stiffness: 110});
    const col = it.color || (anyHi ? (it.highlight ? p.accent : p.series[3]) : p.series[i % p.series.length]);
    return {it, i, at, k, a, col, x: (i - (n - 1) / 2) * gap, h: Math.max(0.001, ((Number(it.value) || 0) / mx) * H * k)};
  });
  const labels = bars.map(({it, i, k, a, x, h}) => {
    const lo = rig.project(new THREE.Vector3(x, 0, bw / 2 + 0.25)); const hi = rig.project(new THREE.Vector3(x, h + 0.35, 0));
    return <React.Fragment key={i}>
      <Tag x={lo.x} y={lo.y + 34 * u} text={it.label} p={p} u={u} a={a} size={Math.min(32, 300 / n + 12) * fit} />
      <Tag x={hi.x} y={hi.y} text={`${prefix}${fmtNumber(Number(it.value) || 0, k, decOf(it.value))}${unit}`} p={p} u={u} a={a} strong size={Math.min(40, 360 / n + 14) * fit} />
    </React.Fragment>;
  });
  return (
    <Stage p={p} seed={n + 3} rig={rig} title={title} kicker={kicker} source={source} labels={labels}>
      <mesh position={[0, -0.06, 0]}><boxGeometry args={[n * gap + 1.2, 0.12, 2.6]} /><meshStandardMaterial color={p.bg2} metalness={0.1} roughness={0.7} /></mesh>
      {bars.map(({i, col, x, h, it}) => (
        <mesh key={i} position={[x, h / 2, 0]}>
          <boxGeometry args={[bw, h, bw]} />
          <meshStandardMaterial color={col} metalness={0.15} roughness={0.38} emissive={it.highlight ? col : '#000000'} emissiveIntensity={it.highlight ? 0.35 : 0} />
        </mesh>
      ))}
    </Stage>
  );
};

// ---------------------------------------------------------------- globe
const LAND: any = feature(world as any, (world as any).objects.countries);
const ll = (lon: number, lat: number, r = 1) => { const a = lon * Math.PI / 180, b = lat * Math.PI / 180; return new THREE.Vector3(r * Math.cos(b) * Math.cos(a), r * Math.sin(b), -r * Math.cos(b) * Math.sin(a)); };

const earthTexture = (p: Palette, hl: {feat: any; color: string}[]) => {
  const c = document.createElement('canvas'); c.width = 2048; c.height = 1024; const g = c.getContext('2d')!;
  const path = geoPath(geoEquirectangular().fitSize([2048, 1024], {type: 'Sphere'} as any), g);
  g.fillStyle = p.ocean; g.fillRect(0, 0, 2048, 1024);
  g.strokeStyle = 'rgba(255,255,255,0.07)'; g.lineWidth = 1.5;
  for (let lon = -180; lon <= 180; lon += 30) { g.beginPath(); g.moveTo((lon + 180) / 360 * 2048, 0); g.lineTo((lon + 180) / 360 * 2048, 1024); g.stroke(); }
  for (let lat = -60; lat <= 60; lat += 30) { g.beginPath(); g.moveTo(0, (90 - lat) / 180 * 1024); g.lineTo(2048, (90 - lat) / 180 * 1024); g.stroke(); }
  g.fillStyle = p.land; g.strokeStyle = p.bg; g.lineWidth = 1.2;
  for (const ft of LAND.features) { g.beginPath(); path(ft); g.fill(); g.stroke(); }
  for (const h of hl) if (h.feat) { g.beginPath(); path(h.feat); g.fillStyle = h.color; g.fill(); g.strokeStyle = p.text; g.lineWidth = 2; g.stroke(); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
};

const arcPoints = (a: THREE.Vector3, b: THREE.Vector3, m = 48) => {
  const lift = 1 + 0.12 + 0.32 * (a.angleTo(b) / Math.PI);
  const mid = a.clone().add(b).normalize().multiplyScalar(lift * 1.6 - 0.6);
  return new THREE.QuadraticBezierCurve3(a.clone(), mid, b.clone()).getPoints(m);
};

export const Globe: React.FC<P> = ({p, title, kicker, focus = [10, 20], spin = 40, highlight = [], pins = [], arcs = [], camera, beats, seconds, source}) => {
  const f = useCurrentFrame(); const {fps, u, width, height, n: durationInFrames} = useStage();
  const hl = useMemo(() => highlight.map((h: any) => (typeof h === 'string' ? {country: h} : h)).map((h: any) => ({feat: findCountry(h.country), color: h.color || p.accent})), [JSON.stringify(highlight), p.accent]);
  const tex = useMemo(() => earthTexture(p, hl), [hl, p.ocean, p.land]);
  const t = interpolate(f, [0, Math.max(durationInFrames - 1, 1)], [0, 1], {easing: Easing.inOut(Easing.sin)});
  const lon = focus[0] - spin / 2 + spin * t, lat = focus[1];
  const ry = -Math.PI / 2 - lon * Math.PI / 180, rx = lat * Math.PI / 180;
  const rig = useRig(cam(camera, 'push_in'), Math.max(4.2, fitWidth(1.3, width, height)), [0, 0.05, 0]);
  const rot = (v: THREE.Vector3) => v.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), ry).applyAxisAngle(new THREE.Vector3(1, 0, 0), rx);
  const total = pins.length + arcs.length;
  const pinAt = pins.map((_: any, i: number) => beatAt(beats, i, total, seconds, 0.5, 0.6));
  const arcAt = arcs.map((_: any, j: number) => beatAt(beats, pins.length + j, total, seconds, 0.5, 0.6));
  const labels = pins.map((pn: any, i: number) => {
    const w = rot(ll(pn.lon, pn.lat, 1.06)); const vis = w.clone().normalize().dot(rig.eye.clone().normalize());
    if (!pn.label || vis < 0.12) return null;
    const q = rig.project(rot(ll(pn.lon, pn.lat, 1.22)));
    return <Tag key={i} x={q.x} y={q.y - 26 * u} text={pn.label} p={p} u={u} a={pop(f, fps, pinAt[i], {damping: 14})} size={30} />;
  });
  return (
    <Stage p={p} seed={7} rig={rig} title={title} kicker={kicker} source={source} labels={labels}>
      <group rotation={[rx, 0, 0]}><group rotation={[0, ry, 0]}>
        <mesh><sphereGeometry args={[1, 96, 64]} /><meshStandardMaterial map={tex} emissiveMap={tex} emissive="#ffffff" emissiveIntensity={0.4} roughness={0.85} metalness={0} /></mesh>
        <mesh scale={1.035}><sphereGeometry args={[1, 48, 32]} /><meshBasicMaterial color={p.accent} transparent opacity={0.07} side={THREE.BackSide} /></mesh>
        {pins.map((pn: any, i: number) => {
          const a = pop(f, fps, pinAt[i], {damping: 12}); const col = pn.color || p.accent2; const d = ll(pn.lon, pn.lat, 1).normalize();
          const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), d);
          return <group key={i} position={d.clone().multiplyScalar(1.0)} quaternion={q} scale={Math.max(a, 0.001)}>
            <mesh position={[0, 0.07, 0]}><cylinderGeometry args={[0.006, 0.006, 0.14, 8]} /><meshStandardMaterial color="#ffffff" /></mesh>
            <mesh position={[0, 0.15, 0]}><sphereGeometry args={[0.032, 16, 12]} /><meshStandardMaterial color={col} emissive={col} emissiveIntensity={0.6} /></mesh>
          </group>;
        })}
        {arcs.map((ar: any, j: number) => {
          const k = prog(f, fps, arcAt[j], Math.max(1.2, seconds * 0.25), Easing.inOut(Easing.cubic)); if (k <= 0.001) return null;
          const pts = arcPoints(ll(ar.from[0], ar.from[1]), ll(ar.to[0], ar.to[1]));
          const m = Math.max(2, Math.round(pts.length * k)); const part = pts.slice(0, m); const col = ar.color || p.accent;
          return <group key={j}>
            <mesh><tubeGeometry args={[new THREE.CatmullRomCurve3(part), part.length * 2, 0.008, 6]} /><meshBasicMaterial color={col} /></mesh>
            <mesh position={part[part.length - 1]}><sphereGeometry args={[0.024, 12, 8]} /><meshBasicMaterial color="#ffffff" /></mesh>
          </group>;
        })}
      </group></group>
    </Stage>
  );
};

// ---------------------------------------------------------------- network3d
const rng = (seed: number) => () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };

// deterministic 3D force layout (same picture on every render and every frame)
const layout = (nodes: any[], links: any[]) => {
  const n = nodes.length; const R = rng(n * 977 + links.length * 31 + 5);
  const pos = nodes.map((_, i) => { const y = 1 - 2 * (i + 0.5) / n, r = Math.sqrt(1 - y * y), a = i * 2.399963; return new THREE.Vector3(Math.cos(a) * r, y, Math.sin(a) * r).multiplyScalar(2.6 + R() * 0.8); });
  const idx = new Map(nodes.map((nd, i) => [nd.id ?? nd.label, i]));
  const E = links.map((l) => [idx.get(l.from), idx.get(l.to)] as [number, number]).filter(([a, b]) => a !== undefined && b !== undefined);
  for (let it = 0; it < 160; it++) {
    const F = pos.map(() => new THREE.Vector3());
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const d = pos[i].clone().sub(pos[j]); const l = Math.max(d.length(), 0.2); d.multiplyScalar(1.4 / (l * l * l));
      F[i].add(d); F[j].sub(d);
    }
    for (const [a, b] of E) { const d = pos[b].clone().sub(pos[a]); const l = d.length(); d.multiplyScalar((l - 2.2) * 0.03); F[a].add(d); F[b].sub(d); }
    for (let i = 0; i < n; i++) pos[i].add(F[i].sub(pos[i].clone().multiplyScalar(0.012)).clampLength(0, 0.4));
  }
  const mx = Math.max(...pos.map((v) => v.length()), 1); return {pos: pos.map((v) => v.multiplyScalar(4.2 / mx).multiply(new THREE.Vector3(1.3, 0.5, 1))), E};
};

export const Network3D: React.FC<P> = ({p, title, kicker, nodes = [], links = [], camera, beats, seconds, source}) => {
  const f = useCurrentFrame(); const {fps, u, width, height} = useStage();
  const {pos, E} = useMemo(() => layout(nodes, links), [JSON.stringify(nodes), JSON.stringify(links)]);
  const rig = useRig(cam(camera), Math.max(11, fitWidth(6.6, width, height)), [0, 0.3, 0]);
  const total = nodes.length + links.length;
  const nodeAt = nodes.map((_: any, i: number) => beatAt(beats, i, total, seconds, 0.4, 0.6));
  const linkAt = links.map((_: any, j: number) => beatAt(beats, nodes.length + j, total, seconds, 0.4, 0.6));
  const idx = new Map(nodes.map((nd: any, i: number) => [nd.id ?? nd.label, i]));
  const labels = nodes.map((nd: any, i: number) => {
    if (!nd.label) return null; const r = 0.14 + 0.22 * (nd.size ?? 0.5);
    const q = rig.project(pos[i].clone().add(new THREE.Vector3(0, r + 0.32, 0)));
    return <Tag key={i} x={q.x} y={q.y} text={nd.label} p={p} u={u} a={pop(f, fps, nodeAt[i], {damping: 14})} size={Math.min(30, 330 / Math.max(nodes.length, 1) + 16)} />;
  });
  return (
    <Stage p={p} seed={nodes.length + 11} rig={rig} title={title} kicker={kicker} source={source} labels={labels}>
      {links.map((l: any, j: number) => {
        const a = idx.get(l.from), b = idx.get(l.to) as number | undefined; if (a === undefined || b === undefined) return null;
        const k = prog(f, fps, linkAt[j], 0.9); const A = pos[a as number], B = pos[b]; if (k <= 0.001) return null;
        const end = A.clone().lerp(B, k); const col = l.color || p.muted;
        const dir = end.clone().sub(A); const len = dir.length(); const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize());
        const t = ((f / fps) * 0.45 + j * 0.37) % 1; const dot = A.clone().lerp(B, t);
        return <group key={j}>
          <mesh position={A.clone().add(end).multiplyScalar(0.5)} quaternion={q}><cylinderGeometry args={[0.025, 0.025, len, 6]} /><meshBasicMaterial color={col} transparent opacity={0.55} /></mesh>
          {k > 0.99 ? <mesh position={dot}><sphereGeometry args={[0.07, 10, 8]} /><meshBasicMaterial color={p.accent} /></mesh> : null}
        </group>;
      })}
      {nodes.map((nd: any, i: number) => {
        const a = pop(f, fps, nodeAt[i], {damping: 12}); const col = nd.color || p.series[i % p.series.length]; const r = 0.14 + 0.22 * (nd.size ?? 0.5);
        return <mesh key={i} position={pos[i]} scale={Math.max(a, 0.001)}><sphereGeometry args={[r, 32, 24]} /><meshStandardMaterial color={col} roughness={0.35} metalness={0.15} emissive={col} emissiveIntensity={0.25} /></mesh>;
      })}
    </Stage>
  );
};

export const Scene3D: React.FC<Scene3DProps> = ({kind, palette, ...rest}) => {
  const p: Palette = {...PALETTE, ...(palette || {})};
  const C = kind === 'globe' ? Globe : kind === 'network3d' ? Network3D : Bars3D;
  return <C p={p} {...(rest as any)} />;
};
