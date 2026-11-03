/**
 * Remotion composition registry.
 *
 * Frame sizes and FPS are read from engine.config.json rather than retyped
 * here, so the Python analysis side and the TypeScript composition side cannot
 * drift apart. This is also the only layer allowed to think in frames:
 * everything in project data stays in seconds.
 */

import React from 'react';
import { Composition } from 'remotion';

import engineConfig from '../engine.config.json';
import { ArabicShapingProof } from './proofs/ArabicShapingProof';

const { portrait } = engineConfig.output;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/*
        A still, not a video: one frame is enough to judge text shaping.
        Portrait width, but a taller canvas than the 1080x1920 output format:
        this is a diagnostic contact sheet, not a deliverable, and all seven
        checks have to be legible side by side in one image.
      */}
      <Composition
        id="ArabicShapingProof"
        component={ArabicShapingProof}
        width={portrait.width}
        height={2400}
        fps={portrait.fps}
        durationInFrames={1}
      />
    </>
  );
};
