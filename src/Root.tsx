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
import { Kajian, loadProject } from './compositions/Kajian';
import { Review } from './compositions/Review';

const { portrait } = engineConfig.output;

/** The prepared project the Kajian composition shows. */
const SLUG = 'kajian-02';

/** The project being reviewed against its decision sheet. */
const REVIEW_SLUG = 'kajian-02';

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
        The talk itself. Its length is not written here: it comes from the
        prepared project, so the composition cannot claim a duration the cut
        does not have.
      */}
      <Composition
        id="Kajian"
        component={Kajian}
        width={portrait.width}
        height={portrait.height}
        fps={portrait.fps}
        durationInFrames={1}
        defaultProps={{ slug: SLUG, showWithheld: true }}
        calculateMetadata={async ({ props }) => {
          const data = await loadProject(String(props.slug ?? SLUG));
          return {
            durationInFrames: Math.max(1, Math.round(data.durationSeconds * data.fps)),
            fps: data.fps,
            width: data.width,
            height: data.height,
            // Hand the loaded project straight to the component, so it never
            // fetches anything itself.
            props: { ...props, data },
          };
        }}
      />

      {/*
        The uncut recording with every proposed cut marked by its number, for
        checking what a number on the decision sheet actually refers to.
      */}
      <Composition
        id="Review"
        component={Review}
        width={portrait.width}
        height={portrait.height}
        fps={portrait.fps}
        durationInFrames={1}
        defaultProps={{ slug: REVIEW_SLUG }}
        calculateMetadata={async ({ props }) => {
          const data = await loadProject((props as { slug: string }).slug);
          return {
            durationInFrames: Math.max(1, Math.round(data.durationSeconds * data.fps)),
            fps: data.fps,
            width: data.width,
            height: data.height,
            props: { data, marks: data.marks ?? [] },
          };
        }}
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
