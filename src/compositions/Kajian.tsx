/**
 * The talk itself: the rough cut, with subtitles built from the transcript.
 *
 * This is the first composition that loads real footage. Everything before it
 * drew a stand-in, which was honest for proving shaping and layout but proved
 * nothing about the actual pipeline.
 *
 * What it reads comes from public/<slug>/data.json, written by
 * scripts/prepare_composition.py. Timings there are already on the CUT
 * timeline; nothing here re-times anything, because doing that arithmetic in
 * two places is how the two drift apart.
 */

import React from 'react';
import { AbsoluteFill, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';

import { FONT } from '../config/fonts';
import { THEME } from '../config/theme';
import { KINETIC_CAPTION } from '../effects/KineticCaption';
import type { FxCtx, FxSpec } from '../lib/core';
import { px } from '../lib/layout';
import { Stage, type PlannedEffect } from './Stage';

export type Cue = {
  start: number;
  end: number;
  text: string;
  words: { w: string; start: number; end: number }[];
  suspected: string[];
  protected: string[];
  /** True only when the text might be unverified scripture. */
  withhold?: boolean;
};

export type ProjectData = {
  slug: string;
  video: string;
  fps: number;
  width: number;
  height: number;
  durationSeconds: number;
  soundFrom: string | null;
  cues: Cue[];
  /** The effect plan, on the cut's timeline. */
  effects?: PlannedEffect[];
  track?: { face: number[][]; top: number[] };
  /** Proposed cuts, numbered as the decision sheet numbers them. */
  marks?: {
    number: string | null;
    id: string;
    kind: string | null;
    status: string;
    start: number;
    end: number;
  }[];
};

export const loadProject = (slug: string): Promise<ProjectData> =>
  fetch(staticFile(`${slug}/data.json`)).then((r) => {
    if (!r.ok) {
      throw new Error(
        `No prepared data for "${slug}". Run: python -m scripts.prepare_composition --slug ${slug}`,
      );
    }
    return r.json() as Promise<ProjectData>;
  });

/** The face at this frame, in pixels, or a centred fallback. */
function faceAtFrame(data: ProjectData, frame: number) {
  const { width: W, height: H } = data;
  const track = data.track;
  if (!track || !track.face.length) {
    return { x: W / 2, y: H * 0.34, w: W * 0.3, top: H * 0.34 - W * 0.33 };
  }
  const i = Math.max(0, Math.min(track.face.length - 1, frame));
  const [x, y, w] = track.face[i];
  return { x: x * W, y: y * H, w: w * W, top: track.top[i] * H };
}

/**
 * A caption may not be drawn from a cue that might be scripture.
 *
 * The transcriber's spelling of a recited verse is not a source. Putting it
 * on screen would publish unverified scripture, which the editorial rules
 * forbid outright — so the words are withheld and the moment is marked
 * instead, until a human has checked the wording against an approved source.
 */
const Withheld: React.FC<{ c: FxCtx; reason: string }> = ({ c, reason }) => (
  <div
    style={{
      position: 'absolute',
      left: px(c, 60),
      right: px(c, 60),
      bottom: px(c, 300),
      padding: `${px(c, 18)}px ${px(c, 24)}px`,
      borderRadius: px(c, 12),
      border: `${px(c, 2)}px dashed ${THEME.accent}`,
      background: 'rgba(15, 17, 21, 0.72)',
      fontFamily: FONT.ui,
      color: THEME.accent,
      fontSize: px(c, 26),
      lineHeight: 1.4,
      textAlign: 'center',
    }}
  >
    subtitle withheld — {reason}
    <div style={{ color: THEME.inkMuted, fontSize: px(c, 21), marginTop: px(c, 6) }}>
      verify the wording against an approved source before it goes on screen
    </div>
  </div>
);

export type KajianProps = {
  /**
   * Which prepared project to show. Optional on the component itself: it is
   * read by calculateMetadata to fetch the data, and the component then works
   * from `data` alone.
   */
  slug?: string;
  /**
   * Draw a notice where a subtitle was held back.
   *
   * OFF by default. A span that cannot be subtitled is simply left bare —
   * a marker explaining the absence belongs in review, not in the finished
   * piece, where it is just clutter nobody asked for.
   */
  showWithheld?: boolean;
  /**
   * Filled in by calculateMetadata, not by hand.
   *
   * The data used to be fetched inside the component, behind delayRender.
   * That rendered stills correctly but showed nothing at all in the Studio:
   * the component sat on its placeholder while the metadata pass had already
   * loaded the same file successfully. Fetching in two places meant one of
   * them could be wrong on its own. Now there is one fetch, at metadata time,
   * and the component is a pure function of its props.
   */
  data?: ProjectData;
};

export const Kajian: React.FC<KajianProps> = ({ data, showWithheld = false }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  if (!data) return <AbsoluteFill style={{ backgroundColor: THEME.bg }} />;

  const t = frame / fps;
  const cue = data.cues.find((c) => t >= c.start && t < c.end);

  let caption: React.ReactNode = null;
  if (cue) {
    // Only scripture is withheld. A span merely suspected of holding extra
    // unheard sound still gets its subtitle: the words that were written
    // are not in doubt.
    const flagged = cue.withhold ?? cue.protected.length > 0;
    const o: FxSpec = {
      fx: 'kinetic-caption',
      start: cue.start,
      end: cue.end,
      text: cue.text,
      // Real word clocks from the transcript, so words land as they are said
      // rather than on a fixed cadence.
      times: cue.words.map((w) => w.start).join(','),
      y: 'low',
      size: 64,
    };
    const c: FxCtx = {
      t: t - cue.start,
      d: cue.end - cue.start,
      fps,
      W: width,
      H: height,
      face: faceAtFrame(data, frame),
      o,
      bright: false,
    };
    const Front = KINETIC_CAPTION.Front;
    caption = flagged
      ? showWithheld
        ? <Withheld c={c} reason={cue.protected.length ? 'protected speech' : 'may be scripture'} />
        : null
      : Front
        ? <Front c={c} />
        : null;
  }

  // The subtitle sits between the effects' Front layer and their Screen
  // layer, so a darkening scrim helps it read instead of covering it.
  return (
    <Stage data={data} effects={data.effects ?? []} frame={frame}>
      {caption}
    </Stage>
  );
};
