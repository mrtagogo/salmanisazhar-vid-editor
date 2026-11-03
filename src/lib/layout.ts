/**
 * Where things are allowed to go.
 *
 * Derived from facecammaxxing's src/lib/layout.ts (MIT, see NOTICE), with one
 * substantial change: the reference hard-codes the 1080x1920 portrait frame and
 * TikTok's right-hand button rail. Tadabbur Motion renders portrait AND
 * landscape as separate compositions, and a landscape frame has neither the
 * same safe margins nor a rail at all. So the zones are chosen per format.
 */

import type { FxCtx } from './core';
import { clamp } from './ease';

export type Format = 'portrait' | 'landscape';

export const formatOf = (c: Pick<FxCtx, 'W' | 'H'>): Format => (c.W >= c.H ? 'landscape' : 'portrait');

/**
 * Sizes in effect code are written for a 1080-wide portrait frame. Scaling by
 * the SHORT edge means a 40 px label is the same physical size in portrait and
 * in landscape; scaling by width would make every landscape label 78% larger.
 */
export const px = (c: Pick<FxCtx, 'W' | 'H'>, v: number) => (v * Math.min(c.W, c.H)) / 1080;

export type Zones = {
  /** Nothing readable above this: the platform's own header sits there. */
  top: number;
  /** Nothing readable below this: captions, handles and buttons sit there. */
  bottom: number;
  /** Right-hand limit where the button rail exists. */
  railX: number;
  /** The rail starts at this y. Infinity means this format has no rail. */
  railY0: number;
  margin: number;
};

export function zones(c: Pick<FxCtx, 'W' | 'H'>): Zones {
  if (formatOf(c) === 'landscape') {
    // No vertical-feed furniture to dodge. Broadcast-style title-safe margins.
    const margin = c.W * 0.045;
    return { top: c.H * 0.06, bottom: c.H * 0.9, railX: c.W - margin, railY0: Infinity, margin };
  }
  // Portrait: the vertical-feed numbers, in 1080x1920 units, scaled.
  const sx = c.W / 1080;
  const sy = c.H / 1920;
  return { top: 250 * sy, bottom: 1536 * sy, railX: 940 * sx, railY0: 864 * sy, margin: 60 * sx };
}

/** The right edge a box spanning y0..y1 may use, given the rail. */
export const rightEdge = (c: FxCtx, y0: number, y1: number) => {
  const z = zones(c);
  return y1 > z.railY0 && y0 < z.bottom ? z.railX : c.W - z.margin;
};

/** Just below the chin: the top of the region where an overlay cannot hit the face. */
export const chin = (c: FxCtx) => c.face.y + c.face.w * 0.62;

/** The band between the chin and the caption zone, where chest-height panels live. */
export const band = (c: FxCtx) => {
  const top = chin(c) + px(c, 22);
  return { top, h: Math.max(0, zones(c).bottom - px(c, 14) - top) };
};

/**
 * Place a block of height `h` at `wanted`, pushed into the safe band if it
 * would touch the face.
 *
 * Returns the chosen top and whether it had to be moved, so a composition can
 * report the move instead of silently covering a face. The engine's rule is
 * absolute: an overlay never sits on the presenter's face.
 */
export function safeTop(c: FxCtx, wanted: number, h: number): { top: number; moved: boolean } {
  const z = zones(c);
  const lo = z.top;
  const hi = Math.max(lo, z.bottom - h);
  let top = clamp(wanted, lo, hi);

  const guardTop = c.face.y - c.face.w * 0.08 - c.face.w * 0.95;
  const guardBottom = c.face.y - c.face.w * 0.08 + c.face.w * 0.95;
  const overlaps = top < guardBottom && top + h > guardTop;
  if (!overlaps) return { top, moved: false };

  // Below the chin if it fits there, otherwise above the head.
  const below = clamp(chin(c) + px(c, 12), lo, hi);
  if (below + h <= z.bottom) return { top: below, moved: true };
  top = clamp(guardTop - h - px(c, 12), lo, hi);
  return { top, moved: true };
}
