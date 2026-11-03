/**
 * Camera moves.
 *
 * The editing identity is DYNAMIC: intentional framing and subtle punch-ins,
 * no random zoom, and the presenter's face is never cropped. The last of those
 * is enforced here rather than left to whoever writes the plan — see safeZoom.
 *
 * These functions return a camera, they do not apply one. Applying it is
 * layerStyle() in src/lib/core.ts, and a composition that shows real footage
 * needs a renderer that does not exist yet (see NOTICE).
 *
 * Derived from facecammaxxing's lean-in and slow-push (MIT, see NOTICE).
 */

import { type Cam, type FxCtx, type FxDef, MAX_ZOOM, opt } from '../lib/core';
import { e } from '../lib/ease';

/**
 * The largest zoom that still keeps the whole head, plus air, inside frame.
 *
 * Without this, a plan asking for zoom 2 on a close framing silently crops the
 * forehead or chin. The rule says never crop important facial features, so the
 * engine refuses the excess instead of trusting the number it was given.
 */
export function safeZoom(c: FxCtx, wanted: number): number {
  const headHeight = c.face.y + c.face.w * 0.62 - c.face.top;
  const headWidth = c.face.w * 1.25;
  const air = 1.18;
  const byHeight = c.H / (headHeight * air);
  const byWidth = c.W / (headWidth * air);
  return Math.max(1, Math.min(wanted, byHeight, byWidth, MAX_ZOOM));
}

/** Keep the face at `headAt` of the frame height while zoomed in. */
export function faceCam(c: FxCtx, zoom: number, headAt = 0.4, parallax = 0): Cam {
  const z = safeZoom(c, zoom);
  return { zoom: z, cx: c.face.x, cy: c.face.y + (c.H / z) * (0.5 - headAt), parallax };
}

/** The punch's envelope: snaps in over `in` frames, holds, snaps back over `out` frames. */
export function punchK(c: FxCtx): number {
  const inS = opt(c, 'in', 5) / 30;
  const outS = opt(c, 'out', 6) / 30;
  return e('expo.out', c.t, 0, inS) * (1 - e('power2.in', c.t, c.d - outS, outS));
}

export const LEAN_IN: FxDef = {
  desc:
    'A hard punch-in on one word: snaps in over 5 frames with motion blur while the room goes soft, '
    + 'keeps creeping in while it holds, then snaps back out',
  options: 'zoom (1.3), parallax (0.6), dof (8 px), in (5 frames), out (6 frames)',
  requires: ['faceTrack'],
  camera: (c) => {
    const k = punchK(c);
    // The hold is not static: a slow further creep keeps it alive.
    const creep = 0.025 * e('sine.inOut', c.t, 0, c.d);
    return faceCam(c, 1 + (opt(c, 'zoom', 1.3) - 1 + creep) * k, 0.4, opt(c, 'parallax', 0.6) * k);
  },
  cameraBlur: true,
  dof: (c) => opt(c, 'dof', 8) * (Math.min(c.W, c.H) / 1080) * punchK(c),
};

export const SLOW_PUSH: FxDef = {
  desc: 'A slow cinematic push-in while the room melts out of focus, with real parallax on a still camera',
  options: 'zoom (1.5), blur (10 px), parallax (1)',
  requires: ['faceTrack'],
  camera: (c) => {
    const k = e('sine.inOut', c.t, 0, c.d);
    return faceCam(c, 1 + (opt(c, 'zoom', 1.5) - 1) * k, 0.42, opt(c, 'parallax', 1) * Math.min(1, k * 4));
  },
  room: (c) => `blur(${opt(c, 'blur', 10) * e('sine.inOut', c.t, 0, c.d)}px)`,
};
