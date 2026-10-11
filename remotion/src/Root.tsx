import React from 'react';
import {Composition} from 'remotion';
import {Overlay, OverlayProps} from './Overlay';

// One composition. Size, length and frame rate come from the props, so the same bundle serves 16:9 and 9:16.
const defaults: OverlayProps = {
  template: 'lower_third', zone: 'bottom', width: 1920, height: 1080, fps: 30, seconds: 4,
  title: 'Abraham Lincoln', subtitle: '16th President of the United States',
};

export const Root: React.FC = () => (
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
);
