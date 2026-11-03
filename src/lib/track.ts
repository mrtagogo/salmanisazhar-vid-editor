/**
 * A synthetic face track.
 *
 * The real one comes from a face-tracking pass over the footage, which this
 * engine does not have yet. Without any track the camera moves and the
 * face-safe placement cannot be exercised at all, so they could only be read,
 * not seen.
 *
 * This produces a deterministic, plausible head path: centred, in the upper
 * third, drifting the way someone does while talking. It is for proofs and
 * tests only. It is NOT a stand-in for tracking real footage, and no render
 * meant for publishing may use it.
 */

import type { Track } from './core';

/** The shape of data/06-face-track.json, as the Python side writes it. */
export type FaceTrackArtefact = {
  schema: string;
  ok: boolean;
  reason: string | null;
  fps: number;
  frames: number;
  sourceWidth: number;
  sourceHeight: number;
  face: number[][];
  top: number[];
  gaps: { startFrame: number; endFrame: number; startSeconds: number; endSeconds: number }[];
  stats: { coverage: number; sampleCount: number; meanScore: number | null; gapCount: number };
  warnings: string[];
};

/**
 * Turn the analysis artefact into a Track, refusing one that cannot be used.
 *
 * A track the engine is not confident about is worse than no track: effects
 * would go on promising to keep clear of a face whose position is a guess. So
 * an unusable artefact throws here rather than being quietly accepted.
 *
 * Gaps do NOT throw — a moment where the presenter turns away is normal. They
 * are returned for the caller to reason about, because inside a gap the face
 * position is held, not known.
 */
export function fromArtefact(data: FaceTrackArtefact): Track {
  if (!data.ok) {
    throw new Error(
      `face track is unusable: ${data.reason ?? 'no reason given'}. `
        + 'Re-run the track stage, or do not use effects that need a face.',
    );
  }
  if (!data.face.length || data.face.length !== data.frames) {
    throw new Error(
      `face track is malformed: ${data.frames} frames declared, ${data.face.length} entries.`,
    );
  }
  if (data.top.length !== data.face.length) {
    throw new Error('face track is malformed: face and top are different lengths.');
  }
  return {
    fps: data.fps,
    width: data.sourceWidth,
    height: data.sourceHeight,
    frames: data.frames,
    duration: data.frames / data.fps,
    face: data.face,
    top: data.top,
  };
}

export type SyntheticOptions = {
  width: number;
  height: number;
  fps: number;
  seconds: number;
  /** Head width as a fraction of frame width. */
  faceWidth?: number;
  /** Vertical centre of the head as a fraction of frame height. */
  faceY?: number;
};

export function syntheticTrack({
  width,
  height,
  fps,
  seconds,
  faceWidth = 0.3,
  faceY = 0.34,
}: SyntheticOptions): Track {
  const frames = Math.max(1, Math.round(seconds * fps));
  const face: number[][] = [];
  const top: number[] = [];

  for (let f = 0; f < frames; f++) {
    const t = f / fps;
    // Two slow, incommensurable sways, so the path never repeats exactly
    // within a clip and never sits perfectly still.
    const x = 0.5 + 0.018 * Math.sin((2 * Math.PI * t) / 3.1);
    const y = faceY + 0.008 * Math.sin((2 * Math.PI * t) / 4.7);
    const w = faceWidth * (1 + 0.012 * Math.sin((2 * Math.PI * t) / 5.3));
    face.push([x, y, w]);
    // A head is roughly 1.5x as tall as it is wide; its top sits about 0.75 of
    // a width above the eye line that `y` tracks.
    top.push(y - (w * width * 0.75) / height);
  }

  return { fps, width, height, frames, duration: frames / fps, face, top };
}
