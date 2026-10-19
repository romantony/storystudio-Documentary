// Cover headline (still, 1280x720 or 1080x1920, transparent PNG): the exact thumbnail headline, typeset here so the words
// are never misspelled by an image model; docgen/thumbnail.py composites it onto the generated picture. Shared design
// with infogen's Cover template. Each line is three stacked layers: a dark extrusion with a deep drop
// shadow, a thick black outline, and a metallic gradient fill with a bright top edge. The emphasis line (a number, or the
// most important word) is larger. Text stays out of YouTube's overlays: the bottom-right duration badge on 16:9, the
// edges and the lower interface on 9:16.
//   {image, lines: ["12,941", "TONS"], emphasis: 0, placement: "top" | "center" | "left" | "right",
//    fills: [{top, mid, bottom, extrude}, ...] (per line), accent: {color, kind: "underline" | "slab" | "none"}}
import React, {useEffect, useState} from 'react';
import {AbsoluteFill, continueRender, delayRender} from 'remotion';

export type CoverProps = {lines: string[]; emphasis?: number; placement?: string; fills?: any[]; accent?: {color: string; kind: string} | null;
  width: number; height: number; fps: number; seconds: number};

const DISPLAY = "'Anton', 'Montserrat', 'DejaVu Sans', sans-serif";
type Fill = {top: string; mid: string; bottom: string; extrude: string};
const GOLD: Fill = {top: '#FFF6C2', mid: '#FFD23F', bottom: '#E09A00', extrude: '#3A2400'};
const WHITE: Fill = {top: '#FFFFFF', mid: '#E9EEF3', bottom: '#AEB8C2', extrude: '#1C232B'};
const CHAR_W = 0.5;   // Anton's average uppercase advance, in em

export const Cover: React.FC<CoverProps> = ({lines = [], emphasis = 0, placement = 'top', fills, accent, width, height}) => {
  const [h] = useState(() => delayRender('fonts'));
  useEffect(() => { document.fonts.load('400 120px Anton').then(() => continueRender(h)).catch(() => continueRender(h)); }, [h]);
  const portrait = height > width; const u = Math.min(width, height) / 720;
  const side = !portrait && (placement === 'left' || placement === 'right');
  const boxW = width * (portrait ? 0.84 : side ? 0.5 : 0.82);   // 8 % side margins on 9:16
  const maxH = height * (portrait ? 0.25 : 0.42);                // 9:16: the 10-35 % band; 16:9: under half the height
  const ems = lines.map((_: string, i: number) => (i === emphasis ? 1.45 : 1));
  let sizes = lines.map((l: string, i: number) => Math.min(boxW / (Math.max(l.length, 2) * CHAR_W), 260 * u) * (ems[i] / Math.max(...ems)));
  const total = sizes.reduce((a: number, b: number) => a + b * 1.02, 0);
  if (total > maxH) sizes = sizes.map((s: number) => s * maxH / total);
  const fillOf = (i: number): Fill => (fills && fills[i]) || (i === emphasis ? GOLD : WHITE);
  const top = portrait ? height * 0.1 : placement === 'center' ? (height - total) / 2 : height * 0.07;
  const pos: React.CSSProperties = portrait || !side
    ? {left: (width - boxW) / 2, top: Math.max(top, height * 0.06), width: boxW, alignItems: 'center'}
    : {[placement]: width * 0.05, top: height * 0.1, width: boxW, alignItems: placement === 'left' ? 'flex-start' : 'flex-end'};
  const scrimAt = portrait ? 'center 22%' : side ? `${placement === 'left' ? '20%' : '80%'} 35%` : 'center 25%';
  return (
    <AbsoluteFill style={{background: 'transparent', overflow: 'hidden'}}>
      <AbsoluteFill style={{background: `radial-gradient(ellipse 70% 45% at ${scrimAt}, rgba(0,0,0,0.42) 0%, rgba(0,0,0,0) 70%)`}} />
      <div style={{position: 'absolute', display: 'flex', flexDirection: 'column', gap: 0, ...pos}}>
        {lines.map((l: string, i: number) => {
          const s = sizes[i]; const f = fillOf(i); const depth = Math.max(5, s * 0.1); const stroke = s * 0.11;
          const extrude = Array.from({length: Math.round(depth)}, (_, k) => `${(k + 1) * 0.45}px ${k + 1}px 0 ${f.extrude}`).join(', ');
          const layer: React.CSSProperties = {position: 'absolute', inset: 0, whiteSpace: 'nowrap'};
          return (
            <div key={i} style={{position: 'relative', fontFamily: DISPLAY, fontSize: s, lineHeight: 1.02, textTransform: 'uppercase', letterSpacing: s * 0.01, whiteSpace: 'nowrap'}}>
              <span style={{visibility: 'hidden'}}>{l}</span>
              <span style={{...layer, color: f.extrude, textShadow: `${extrude}, 0 ${depth + s * 0.08}px ${s * 0.18}px rgba(0,0,0,0.75)`}}>{l}</span>
              <span style={{...layer, color: 'transparent', WebkitTextStroke: `${stroke}px #050505`}}>{l}</span>
              <span style={{...layer, backgroundImage: `linear-gradient(180deg, ${f.top} 0%, ${f.mid} 48%, ${f.bottom} 100%)`, WebkitBackgroundClip: 'text', backgroundClip: 'text',
                color: 'transparent', filter: `drop-shadow(0 ${-Math.max(1, s * 0.012)}px 0 rgba(255,255,255,0.55))`}}>{l}</span>
              {accent && accent.kind === 'underline' && i === lines.length - 1 ? (
                <div style={{position: 'absolute', left: '4%', right: '4%', bottom: -s * 0.1, height: Math.max(6, s * 0.09), background: accent.color,
                  transform: 'skewX(-12deg)', boxShadow: `0 ${s * 0.04}px 0 #050505`}} />) : null}
            </div>
          );
        })}
        {accent && accent.kind === 'slab' ? (
          <div style={{position: 'absolute', zIndex: -1, left: '-3%', right: '-3%', top: '8%', bottom: '8%', background: accent.color, opacity: 0.88, transform: 'skewX(-8deg)'}} />) : null}
      </div>
    </AbsoluteFill>
  );
};
