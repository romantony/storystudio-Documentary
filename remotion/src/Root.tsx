import React from 'react';
import {Composition} from 'remotion';
import {Cover, CoverProps} from './Cover';
import {Overlay, OverlayProps} from './Overlay';
import {Chart, ChartProps} from './Chart';

// One composition. Size, length and frame rate come from the props, so the same bundle serves 16:9 and 9:16.
const defaults: OverlayProps = {
  template: 'lower_third', zone: 'bottom', width: 1920, height: 1080, fps: 30, seconds: 4,
  title: 'Abraham Lincoln', subtitle: '16th President of the United States',
};

const meta = ({props}: {props: any}) => ({width: props.width, height: props.height, fps: props.fps, durationInFrames: Math.max(2, Math.round(props.seconds * props.fps))});

export const Root: React.FC = () => (
  <>
  <Composition
    id="Overlay"
    component={Overlay}
    defaultProps={defaults}
    width={1920}
    height={1080}
    fps={30}
    durationInFrames={120}
    calculateMetadata={({props}) => ({
      width: props.width, height: props.height, fps: props.fps,
      durationInFrames: Math.max(2, Math.round(props.seconds * props.fps)),
    })}
  />
  <Composition id="Cover" component={Cover as any} defaultProps={{lines: ['90', 'DAYS'], width: 1080, height: 1920, fps: 30, seconds: 1} as CoverProps}
    width={1080} height={1920} fps={30} durationInFrames={30} calculateMetadata={meta} />
  <Composition id="Chart" component={Chart as any} defaultProps={{kind: 'line', width: 1920, height: 1080, fps: 30, seconds: 8, title: 'Chart', source: 'FRED', points: [{x: '2000', y: 1}, {x: '2001', y: 2}]} as ChartProps}
    width={1920} height={1080} fps={30} durationInFrames={240} calculateMetadata={meta} />
  </>
);
