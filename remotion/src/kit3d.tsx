import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useVideoConfig} from 'remotion';
import {feature} from 'topojson-client';
import {geoArea} from 'd3-geo';
import world from 'world-atlas/countries-50m.json';

// The few helpers the 3D scenes need (ported from infogen's kit.tsx and MapScene.tsx), in docgen's look.
export type Palette = {bg: string; bg2: string; text: string; muted: string; accent: string; accent2: string; land: string; ocean: string; series: string[]};
export const PALETTE: Palette = {
  bg: '#0D1117', bg2: '#1B2430', text: '#F4F1EA', muted: '#9AA5B1', accent: '#F2B632', accent2: '#E5484D',
  land: '#2B3A4A', ocean: '#0A1119', series: ['#F2B632', '#E5484D', '#4CC9F0', '#3DDC97', '#B388EB', '#FF9F1C', '#F15BB5', '#9EF01A'],
};
export const HEAD = "'Anton', 'DejaVu Sans', Arial, sans-serif";
export const SANS = "'DejaVu Sans', 'Noto Sans', Arial, sans-serif";

export const useStage = () => {
  const {width, height, fps, durationInFrames} = useVideoConfig();
  return {width, height, fps, n: durationInFrames, portrait: height > width, u: Math.min(width, height) / 1080, seconds: durationInFrames / fps};
};

export const pop = (frame: number, fps: number, at: number, cfg: {damping?: number; stiffness?: number; mass?: number} = {}) => {
  const fr = frame - Math.round(at * fps);
  return fr < 0 ? 0 : spring({frame: fr, fps, config: {damping: 11, stiffness: 170, mass: 0.6, ...cfg}});
};

export const prog = (frame: number, fps: number, at: number, dur: number, easing: (t: number) => number = Easing.out(Easing.cubic)) =>
  interpolate(frame, [at * fps, (at + Math.max(dur, 0.01)) * fps], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing});

// reveal time of item i: from beats (seconds), else spread evenly through the first part of the scene
export const beatAt = (beats: (number | null)[] | undefined, i: number, count: number, seconds: number, start = 0.35, span = 0.6) => {
  if (beats && beats[i] !== undefined && beats[i] !== null) return beats[i] as number;
  const end = Math.max(start + 0.3, seconds * span);
  return count <= 1 ? start : start + (end - start) * (i / (count - 1));
};

export const fmtNumber = (target: number, k: number, decimals: number) => {
  const [i, d] = (target * k).toFixed(decimals).split('.');
  return i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (d ? '.' + d : '');
};

// Opaque background from the theme palette (no flat-vector shapes: the 3D scene is the picture).
export const Backdrop: React.FC<{p: Palette}> = ({p}) => (
  <AbsoluteFill style={{background: `radial-gradient(ellipse at 50% 40%, ${p.bg2} 0%, ${p.bg} 70%)`}} />
);

export const Heading: React.FC<{title?: string; kicker?: string; p: Palette}> = ({title, kicker, p}) => {
  const {u, portrait, height} = useStage();
  if (!title && !kicker) return null;
  return (
    <div style={{position: 'absolute', left: 60 * u, right: 60 * u, top: portrait ? height * 0.07 : 48 * u, textAlign: 'center'}}>
      {kicker ? <div style={{fontFamily: SANS, fontWeight: 800, fontSize: 28 * u, letterSpacing: 4 * u, color: p.accent, textTransform: 'uppercase'}}>{kicker}</div> : null}
      {title ? <div style={{fontFamily: HEAD, fontSize: 76 * u, lineHeight: 1.06, color: p.text, textShadow: `0 ${4 * u}px 0 rgba(0,0,0,0.3)`}}>{title}</div> : null}
    </div>
  );
};

export const Footnote: React.FC<{text?: string; p: Palette}> = ({text, p}) => {
  const {u, portrait, height} = useStage();
  if (!text) return null;
  return <div style={{position: 'absolute', left: 60 * u, right: 60 * u, bottom: (portrait ? height * 0.04 : 28 * u), fontFamily: SANS, fontSize: 24 * u, color: p.muted, opacity: 0.85}}>Source: {text}</div>;
};

// ---- countries (Natural Earth 1:50m via world-atlas) ----
export const ALL: any = feature(world as any, (world as any).objects.countries);
const norm = (s: string) => s.toLowerCase().replace(/[^a-z]/g, '');
const ALIAS: Record<string, string> = {
  usa: 'unitedstatesofamerica', us: 'unitedstatesofamerica', unitedstates: 'unitedstatesofamerica', america: 'unitedstatesofamerica',
  uk: 'unitedkingdom', britain: 'unitedkingdom', greatbritain: 'unitedkingdom', england: 'unitedkingdom',
  drc: 'demrepcongo', democraticrepublicofthecongo: 'demrepcongo', congokinshasa: 'demrepcongo', southkorea: 'southkorea', korea: 'southkorea',
  northkorea: 'northkorea', czechrepublic: 'czechia', ivorycoast: 'cotedivoire', uae: 'unitedarabemirates', bosnia: 'bosniaandherz',
  southsudan: 'ssudan', centralafricanrepublic: 'centralafricanrep', dominicanrepublic: 'dominicanrep', eswatini: 'eswatini', swaziland: 'eswatini',
  burma: 'myanmar', holland: 'netherlands', palestine: 'palestine', taiwan: 'taiwan', vatican: 'vatican',
};
export const findCountry = (name: string) => {
  const n = ALIAS[norm(name)] || norm(name);
  return ALL.features.find((f: any) => norm(f.properties.name) === n) || ALL.features.find((f: any) => norm(f.properties.name).startsWith(n));
};
export {geoArea};
