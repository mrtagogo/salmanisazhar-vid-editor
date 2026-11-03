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
import { CaptionProof } from './proofs/CaptionProof';
import { EffectsProof } from './proofs/EffectsProof';

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

      {/*
        The caption proof IS the real portrait frame, at full size: direction,
        placement against the face guard and the two-line rule all have to be
        judged at the size they will be read.
      */}
      <Composition
        id="CaptionProof"
        component={CaptionProof}
        width={portrait.width}
        height={portrait.height}
        fps={portrait.fps}
        durationInFrames={1}
      />

      {/*
        A contact sheet: six whole frames scaled down, then the checks that are
        numbers rather than pictures. Taller than the output format for the
        same reason as the shaping proof — it is an instrument, not a frame.
      */}
      <Composition
        id="EffectsProof"
        component={EffectsProof}
        width={portrait.width}
        height={2100}
        fps={portrait.fps}
        durationInFrames={1}
      />
    </>
  );
};
