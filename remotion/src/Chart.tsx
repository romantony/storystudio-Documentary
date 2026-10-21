import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';

// Data charts for the verdict and "why it touches your money" beats: drawn from real series (docgen data), never by an image model.
// The line draws in over `drawS` seconds, then holds; the source is always printed.
export type ChartProps = {
  kind: 'line' | 'bar'; width: number; height: number; fps: number; seconds: number;
  title: string; subtitle?: string; source: string; unit?: string;
  points: {x: string; y: number}[];
  highlight?: {x: string; label: string};
  drawS?: number; accent?: string; bg?: string;
};

const SANS = "'DejaVu Sans', 'Noto Sans', Arial, sans-serif";
const fmt = (v: number) => Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(1) + 'B' : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : Math.abs(v) >= 1e4 ? Math.round(v).toLocaleString('en-US') : String(Math.round(v * 100) / 100);

// Round axis: a step of 1, 2, 2.5 or 5 times a power of ten, and the range widened to whole steps.
const nice = (lo: number, hi: number, n = 4) => {
  const raw = (hi - lo) / n || 1, mag = Math.pow(10, Math.floor(Math.log10(raw))), r = raw / mag;
  const step = (r <= 1 ? 1 : r <= 2 ? 2 : r <= 2.5 ? 2.5 : r <= 5 ? 5 : 10) * mag;
  const a = Math.floor(lo / step) * step, b = Math.ceil(hi / step) * step;
  return {y0: a, y1: b, ticks: Array.from({length: Math.round((b - a) / step) + 1}, (_, k) => a + k * step)};
};

export const Chart: React.FC<ChartProps> = (p) => {
  const f = useCurrentFrame(); const {fps, width: W, height: H} = useVideoConfig();
  const accent = p.accent || '#F2B632', bg = p.bg || '#0D1117', ink = '#F4F1EA', grid = 'rgba(244,241,234,0.14)';
  const draw = interpolate(f, [0.4 * fps, (p.drawS ?? 5) * fps], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic)});
  const m = {l: W * 0.09, r: W * 0.05, t: H * 0.23, b: H * 0.17}; const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const ys = p.points.map((q) => q.y); const lo = p.kind === 'bar' ? Math.min(0, ...ys) : Math.min(...ys), hi = Math.max(...ys);
  const {y0, y1, ticks} = nice(lo, hi);
  const n = p.points.length;
  const X = (i: number) => m.l + (p.kind === 'bar' ? (i + 0.5) * (iw / n) : (n === 1 ? iw / 2 : (i / (n - 1)) * iw));
  const Y = (v: number) => m.t + ih - ((v - y0) / (y1 - y0)) * ih;
  const labelEvery = Math.max(1, Math.ceil(n / 8));
  const path = p.points.map((q, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(q.y).toFixed(1)}`).join(' ');
  const shown = Math.max(1, Math.round(draw * (n - 1)) + 1);
  const hi_i = p.highlight ? p.points.findIndex((q) => q.x === p.highlight!.x) : -1;
  const pop = hi_i >= 0 ? interpolate(draw, [Math.min(0.98, hi_i / Math.max(1, n - 1)), 1], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) : 0;
  return (
    <AbsoluteFill style={{background: bg, fontFamily: SANS, color: ink}}>
      <div style={{position: 'absolute', left: m.l, top: H * 0.06, right: m.r}}>
        <div style={{fontSize: H * 0.065, fontWeight: 800, lineHeight: 1.1}}>{p.title}</div>
        {p.subtitle ? <div style={{fontSize: H * 0.034, opacity: 0.72, marginTop: H * 0.012}}>{p.subtitle}</div> : null}
      </div>
      <svg width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
        {ticks.map((t, k) => (<g key={k}><line x1={m.l} x2={W - m.r} y1={Y(t)} y2={Y(t)} stroke={grid} strokeWidth={2} />
          <text x={m.l - 14} y={Y(t) + 8} textAnchor="end" fontSize={H * 0.028} fill={ink} opacity={0.7}>{fmt(t)}{p.unit || ''}</text></g>))}
        {p.points.map((q, i) => i % labelEvery === 0 ? <text key={i} x={X(i)} y={H - m.b + H * 0.05} textAnchor="middle" fontSize={H * 0.028} fill={ink} opacity={0.7}>{q.x}</text> : null)}
        {p.kind === 'line' ? (<>
          <path d={`${path} L${X(n - 1)},${m.t + ih} L${X(0)},${m.t + ih} Z`} fill={accent} opacity={0.10} clipPath="url(#c)" />
          <clipPath id="c"><rect x={0} y={0} width={m.l + iw * draw} height={H} /></clipPath>
          <path d={path} fill="none" stroke={accent} strokeWidth={H * 0.007} strokeLinejoin="round" strokeLinecap="round" clipPath="url(#c)" />
        </>) : p.points.slice(0, shown).map((q, i) => {
          const bw = (iw / n) * 0.62, top = Y(Math.max(q.y, 0)), base = Y(Math.min(Math.max(0, y0), y1));
          return <rect key={i} x={X(i) - bw / 2} y={q.y >= 0 ? top : base} width={bw} height={Math.abs(Y(q.y) - base)} fill={i === hi_i ? '#E5484D' : accent} rx={4} />;
        })}
        {hi_i >= 0 ? (<g opacity={pop}>
          <circle cx={X(hi_i)} cy={Y(p.points[hi_i].y)} r={H * 0.016} fill="#E5484D" stroke={ink} strokeWidth={3} />
          <text x={Math.min(Math.max(X(hi_i), W * 0.2), W * 0.8)} y={Y(p.points[hi_i].y) - H * 0.035} textAnchor="middle" fontSize={H * 0.04} fontWeight={800} fill={ink} stroke={bg} strokeWidth={6} paintOrder="stroke">{p.highlight!.label}</text>
        </g>) : null}
      </svg>
      <div style={{position: 'absolute', left: m.l, right: m.r, bottom: H * 0.045, fontSize: H * 0.027, opacity: 0.6}}>Source: {p.source}</div>
    </AbsoluteFill>
  );
};
