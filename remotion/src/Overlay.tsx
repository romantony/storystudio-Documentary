import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';

// Text overlays for docgen. Rendered on a transparent background and composited by ffmpeg under the captions.
// Captions sit in the vertical middle of the frame (or at the bottom in talking scenes), so every template
// stays inside a band at the top or bottom, chosen by `zone`.
export type OverlayProps = {
  template: 'lower_third' | 'stamp' | 'title' | 'quote' | 'stat';
  zone: 'top' | 'bottom';
  width: number; height: number; fps: number; seconds: number;
  title?: string; subtitle?: string;      // lower_third, title
  text?: string; attribution?: string;    // stamp (text), quote
  value?: string; label?: string;         // stat
  accent?: string;
};

const SANS = "'DejaVu Sans', 'Noto Sans', Arial, sans-serif";
const SERIF = "'DejaVu Serif', Georgia, serif";
const INK = 'rgba(8, 10, 14, 0.78)';
const SHADOW = '0 4px 18px rgba(0,0,0,0.85), 0 0 3px rgba(0,0,0,0.9)';
const ease = Easing.bezier(0.16, 1, 0.3, 1);

// 0 -> 1 on the way in, back to 0 on the way out
const useInOut = (inS = 0.6, outS = 0.45, delayS = 0) => {
  const f = useCurrentFrame(); const {fps, durationInFrames: n} = useVideoConfig();
  const a = interpolate(f, [delayS * fps, (delayS + inS) * fps], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease});
  const b = interpolate(f, [n - outS * fps, n - 1], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.quad)});
  return Math.min(a, b);
};

// The band the template may draw in. u is the unit all sizes derive from, so 16:9 and 9:16 share one layout.
const useBand = (zone: 'top' | 'bottom') => {
  const {width, height} = useVideoConfig(); const portrait = height > width;
  const u = (portrait ? width : height) / 1080;
  const side = (portrait ? 70 : 110) * u;
  // portrait: keep clear of the Shorts interface (top bar, bottom caption and buttons)
  const edge = portrait ? (zone === 'top' ? 0.13 : 0.24) * height : 80 * u;
  const style: React.CSSProperties = {position: 'absolute', left: side, right: side, display: 'flex', flexDirection: 'column',
    ...(zone === 'top' ? {top: edge, justifyContent: 'flex-start'} : {bottom: edge, justifyContent: 'flex-end'})};
  return {u, portrait, style};
};

const LowerThird: React.FC<OverlayProps> = ({zone, title, subtitle, accent = '#FFD700'}) => {
  const {u, style} = useBand(zone); const bar = useInOut(0.45, 0.4); const t1 = useInOut(0.6, 0.4, 0.12); const t2 = useInOut(0.6, 0.35, 0.3);
  return (
    <div style={{...style, alignItems: 'flex-start'}}>
      <div style={{display: 'flex', alignItems: 'stretch', maxWidth: '100%'}}>
        <div style={{width: 10 * u, background: accent, transform: `scaleY(${bar})`, transformOrigin: 'bottom', borderRadius: 2 * u}} />
        <div style={{overflow: 'hidden'}}>
          <div style={{background: INK, padding: `${18 * u}px ${34 * u}px ${20 * u}px ${28 * u}px`, transform: `translateX(${(t1 - 1) * 101}%)`}}>
            <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 66 * u, lineHeight: 1.12, color: '#fff'}}>{title}</div>
            {subtitle ? <div style={{fontFamily: SANS, fontSize: 40 * u, lineHeight: 1.25, color: accent, marginTop: 6 * u, opacity: t2, letterSpacing: 0.5 * u}}>{subtitle}</div> : null}
          </div>
        </div>
      </div>
    </div>
  );
};

// Place and date, typed out letter by letter
const Stamp: React.FC<OverlayProps> = ({zone, text = '', accent = '#FFD700'}) => {
  const {u, style} = useBand(zone); const f = useCurrentFrame(); const {fps} = useVideoConfig(); const vis = useInOut(0.2, 0.4);
  const shown = Math.floor(interpolate(f, [0.15 * fps, 0.15 * fps + text.length * 1.4], [0, text.length], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}));
  const line = useInOut(0.5, 0.4);
  return (
    <div style={{...style, alignItems: 'flex-start', opacity: vis}}>
      <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 46 * u, letterSpacing: 5 * u, color: '#fff', textTransform: 'uppercase', textShadow: SHADOW}}>
        {text.slice(0, shown)}<span style={{opacity: 0}}>{text.slice(shown)}</span>
      </div>
      <div style={{height: 5 * u, width: `${line * 100}%`, maxWidth: 420 * u, background: accent, marginTop: 12 * u, boxShadow: '0 2px 10px rgba(0,0,0,0.8)'}} />
    </div>
  );
};

// Chapter heading
const Title: React.FC<OverlayProps> = ({zone, title, subtitle, accent = '#FFD700'}) => {
  const {u, style} = useBand(zone); const a = useInOut(0.7, 0.45); const b = useInOut(0.7, 0.4, 0.25);
  return (
    <div style={{...style, alignItems: 'center', textAlign: 'center'}}>
      <div style={{background: INK, padding: `${26 * u}px ${54 * u}px ${30 * u}px`, opacity: a, transform: `translateY(${(1 - a) * (zone === 'top' ? -30 : 30) * u}px)`, maxWidth: '100%'}}>
        <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 76 * u, lineHeight: 1.1, color: '#fff', letterSpacing: 1.5 * u, textTransform: 'uppercase'}}>{title}</div>
        <div style={{height: 6 * u, background: accent, margin: `${16 * u}px auto 0`, width: `${b * 60}%`}} />
        {subtitle ? <div style={{fontFamily: SANS, fontSize: 38 * u, color: accent, marginTop: 14 * u, opacity: b}}>{subtitle}</div> : null}
      </div>
    </div>
  );
};

const Quote: React.FC<OverlayProps> = ({zone, text, attribution, accent = '#FFD700'}) => {
  const {u, style} = useBand(zone); const a = useInOut(0.7, 0.45); const b = useInOut(0.6, 0.4, 0.5);
  return (
    <div style={{...style, alignItems: 'center'}}>
      <div style={{background: INK, borderLeft: `${10 * u}px solid ${accent}`, padding: `${26 * u}px ${44 * u}px ${28 * u}px ${36 * u}px`, opacity: a, transform: `scale(${0.96 + 0.04 * a})`, maxWidth: '100%'}}>
        <div style={{fontFamily: SERIF, fontStyle: 'italic', fontSize: 56 * u, lineHeight: 1.3, color: '#fff'}}>
          <span style={{color: accent}}>{'“'}</span>{text}<span style={{color: accent}}>{'”'}</span>
        </div>
        {attribution ? <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 38 * u, color: accent, marginTop: 14 * u, opacity: b, textAlign: 'right'}}>{'— '}{attribution}</div> : null}
      </div>
    </div>
  );
};

// A number that counts up, with a label. Text around the digits ("$", "%", " million") is kept as it is.
const Stat: React.FC<OverlayProps> = ({zone, value = '', label, accent = '#FFD700'}) => {
  const {u, style} = useBand(zone); const f = useCurrentFrame(); const {fps} = useVideoConfig(); const a = useInOut(0.5, 0.45); const b = useInOut(0.6, 0.4, 0.35);
  const m = value.match(/^(.*?)(\d[\d,]*(?:\.\d+)?)(.*)$/);
  let shown = value;
  if (m) {
    const target = parseFloat(m[2].replace(/,/g, '')); const dec = (m[2].split('.')[1] || '').length;
    const k = interpolate(f, [0.1 * fps, 1.3 * fps], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
    const n = (target * k).toFixed(dec); const [i, d] = n.split('.');
    shown = m[1] + (m[2].includes(',') ? i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : i) + (d ? '.' + d : '') + m[3];
  }
  return (
    <div style={{...style, alignItems: 'center', textAlign: 'center'}}>
      <div style={{background: INK, padding: `${20 * u}px ${56 * u}px ${26 * u}px`, opacity: a, maxWidth: '100%'}}>
        <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 124 * u, lineHeight: 1.05, color: accent, fontVariantNumeric: 'tabular-nums'}}>{shown}</div>
        {label ? <div style={{fontFamily: SANS, fontWeight: 700, fontSize: 38 * u, color: '#fff', marginTop: 6 * u, opacity: b, letterSpacing: 2 * u, textTransform: 'uppercase'}}>{label}</div> : null}
      </div>
    </div>
  );
};

const TEMPLATES = {lower_third: LowerThird, stamp: Stamp, title: Title, quote: Quote, stat: Stat};

export const Overlay: React.FC<OverlayProps> = (props) => {
  const T = TEMPLATES[props.template] || LowerThird;
  return <AbsoluteFill style={{backgroundColor: 'transparent'}}><T {...props} /></AbsoluteFill>;
};
