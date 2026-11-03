/**
 * The effect registry.
 *
 * Six effects, derived from facecammaxxing (MIT, see NOTICE). The reference
 * library carries about twenty; the rest are creator-metrics furniture
 * (follower counts, view graphs, tier lists, 3D reel carousels) that has no
 * place in a kajian, or they depend on three.js and mediapipe passes this
 * engine does not run.
 *
 * Nothing here renders footage. These are the editorial moves; the renderer
 * that applies them to a real clip comes with milestone 2, once an EDL has
 * been approved.
 */

import type { FxDef, Requirement } from '../lib/core';
import { BOTTOM_FADE } from './BottomFade';
import { LEAN_IN, SLOW_PUSH } from './camera';
import { KINETIC_CAPTION } from './KineticCaption';
import { NAME_TAG } from './NameTag';
import { TEXT_BEHIND } from './TextBehind';

export const EFFECTS: Record<string, FxDef> = {
  'lean-in': LEAN_IN,
  'slow-push': SLOW_PUSH,
  'kinetic-caption': KINETIC_CAPTION,
  'name-tag': NAME_TAG,
  'bottom-fade': BOTTOM_FADE,
  'text-behind': TEXT_BEHIND,
};

export const ALIASES: Record<string, string> = {
  punch: 'lean-in',
  'punch-in': 'lean-in',
  push: 'slow-push',
  'push-in': 'slow-push',
  caption: 'kinetic-caption',
  captions: 'kinetic-caption',
  subtitle: 'kinetic-caption',
  nametag: 'name-tag',
  'lower-third': 'name-tag',
  fade: 'bottom-fade',
  'bottom-gradient': 'bottom-fade',
  textbehind: 'text-behind',
  'text-behind-head': 'text-behind',
};

export const resolveFx = (name: string) => {
  const n = name.toLowerCase().trim().replace(/^\//, '');
  return ALIASES[n] ?? n;
};

/**
 * What the analysis side can produce.
 *
 * `faceTrack` is true: the track stage writes data/06-face-track.json. That
 * is a statement about the ENGINE, not about any one project — a particular
 * recording may still yield a track too poor to use, which is why
 * fromArtefact() in src/lib/track.ts refuses an artefact whose `ok` is false,
 * and why gaps are carried through for the caller to reason about.
 *
 * `personMatte` is still false: nothing cuts the presenter out of the
 * background, so a Behind layer is not behind anything.
 */
export const AVAILABLE: Record<Requirement, boolean> = {
  faceTrack: true,
  personMatte: false,
};

/** The requirements an effect declares that cannot be met right now. */
export function unmetRequirements(
  name: string,
  available: Record<Requirement, boolean> = AVAILABLE,
): Requirement[] {
  const def = EFFECTS[resolveFx(name)];
  if (!def) throw new Error(`unknown effect "${name}" — known: ${Object.keys(EFFECTS).join(', ')}`);
  return (def.requires ?? []).filter((r) => !available[r]);
}

/** True when an effect may be used on real footage as the engine stands today. */
export const isUsable = (name: string, available?: Record<Requirement, boolean>) =>
  unmetRequirements(name, available).length === 0;
