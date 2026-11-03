/**
 * The person matte, as the composition layer sees it.
 *
 * The matte itself is a greyscale video whose luma is the alpha — it cannot
 * live in JSON. This module handles the artefact that describes it, and
 * refuses one that should not be used.
 *
 * A matte is what lets a Behind layer actually be behind the presenter. If it
 * is wrong, a graphic does not merely look poor: it lies across the
 * presenter's face, which the editorial rules forbid. So "probably fine" is
 * not a state this accepts.
 */

/** The shape of data/07-person-matte.json, as the Python side writes it. */
export type PersonMatteArtefact = {
  schema: string;
  ok: boolean;
  matteVideo: string;
  encoding: string;
  fps: number;
  frames: number;
  width: number;
  height: number;
  sourceWidth: number;
  sourceHeight: number;
  stats: {
    meanCoverage: number;
    minCoverage: number;
    maxCoverage: number;
    emptyFrameCount: number;
    gapCount: number;
  };
  warnings: string[];
  gaps: { startFrame: number; endFrame: number; startSeconds: number; endSeconds: number }[];
};

export type PersonMatte = {
  /** Path to the greyscale matte video. Luma is the alpha. */
  video: string;
  fps: number;
  frames: number;
  width: number;
  height: number;
  /** Stretches where no presenter was found. Nothing is behind anything here. */
  gaps: { startSeconds: number; endSeconds: number }[];
};

/** True while the matte knows where the presenter is at time `t` (seconds). */
export function coveredAt(matte: PersonMatte, t: number): boolean {
  return !matte.gaps.some((g) => t >= g.startSeconds && t < g.endSeconds);
}

/**
 * Turn the analysis artefact into a matte, refusing one that cannot be used.
 *
 * Gaps do not throw. A presenter stepping out of shot is ordinary, and the
 * caller can ask `coveredAt` before placing anything behind them.
 */
export function fromArtefact(data: PersonMatteArtefact): PersonMatte {
  if (!data.ok) {
    const why = data.warnings.length ? data.warnings.join(' ') : 'no reason given';
    throw new Error(
      `person matte is unusable: ${why} `
        + 'Re-run the matte stage, or do not use effects that need it.',
    );
  }
  if (!data.frames || data.frames < 1) {
    throw new Error('person matte is malformed: it covers no frames.');
  }
  if (!data.matteVideo) {
    throw new Error('person matte is malformed: it names no video file.');
  }
  return {
    video: data.matteVideo,
    fps: data.fps,
    frames: data.frames,
    width: data.width,
    height: data.height,
    gaps: data.gaps.map((g) => ({ startSeconds: g.startSeconds, endSeconds: g.endSeconds })),
  };
}
