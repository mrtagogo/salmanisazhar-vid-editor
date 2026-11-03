/**
 * Builds an FxCtx for proof compositions.
 *
 * The real one will be built by the renderer from an approved EDL and a face
 * track. This builds one from a synthetic track so the effects can be seen and
 * judged before either exists.
 */

import { type FxCtx, type FxSpec, faceAt } from '../lib/core';
import { syntheticTrack } from '../lib/track';

export type ProofCtxOptions = {
  W: number;
  H: number;
  fps: number;
  /** Effect-local time, seconds. */
  t: number;
  /** Effect duration, seconds. */
  d: number;
  options?: Record<string, unknown>;
  /** The wall behind the head is light. */
  bright?: boolean;
};

export function proofCtx({ W, H, fps, t, d, options = {}, bright = false }: ProofCtxOptions): FxCtx {
  const track = syntheticTrack({ width: W, height: H, fps, seconds: Math.max(d, t + 1 / fps) });
  const o: FxSpec = { fx: 'proof', start: 0, end: d, ...options };
  return { t, d, fps, W, H, face: faceAt(track, t * fps), o, bright };
}
