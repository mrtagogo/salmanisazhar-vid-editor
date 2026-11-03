/**
 * The effect contract.
 *
 * An effect is a pure function of its own clock and the tracked face. Same
 * frame in, same picture out — Remotion renders frames out of order and in
 * several browser tabs at once, so nothing may depend on playback order or on
 * state carried between frames.
 *
 * Derived from facecammaxxing's src/lib/core.ts (MIT, see NOTICE), minus the
 * gsap timeline helper — see src/lib/ease.ts for why.
 */

import type React from 'react';

import { clamp, lerp } from './ease';

/**
 * Per-frame face positions, produced by the analysis side.
 *
 * NOT IMPLEMENTED YET on the Python side: nothing in scripts/ writes this.
 * Until a face-tracking pass exists, the only source is syntheticTrack() in
 * src/lib/track.ts, which exists so these effects can be rendered and judged
 * before real footage arrives. Everything that reads `face` is therefore
 * verified against a known-synthetic path, not against a real presenter.
 */
export type Track = {
  fps: number;
  width: number;
  height: number;
  frames: number;
  duration: number;
  /** Per frame [x, y, w]; x and w normalised by width, y by height. */
  face: number[][];
  /** Per frame: top of the head, normalised by height. */
  top: number[];
};

/** The face at one frame, in output pixels. */
export type Face = { x: number; y: number; w: number; top: number };

/** An effect's options, as written in the plan. `start` and `end` are clip seconds. */
export type FxSpec = { fx: string; start: number; end: number } & Record<string, unknown>;

/** Everything an effect gets. */
export type FxCtx = {
  /** Effect-local time, 0..d seconds. */
  t: number;
  /** Effect duration in seconds. */
  d: number;
  fps: number;
  W: number;
  H: number;
  face: Face;
  o: FxSpec;
  /** The wall behind the head is light, so dark ink reads better. */
  bright: boolean;
};

export type Cam = { zoom: number; cx: number; cy: number; parallax?: number };

/**
 * What an effect needs from the analysis side before it can be trusted on real
 * footage.
 *
 *   faceTrack   — per-frame face positions, for framing and face-safe placement
 *   personMatte — an alpha cut-out of the presenter, so a Behind layer is
 *                 actually covered by the body instead of lying across it
 *
 * Neither pass exists yet. This field is how that gap is carried in code
 * rather than only in a document: a composition must refuse an effect whose
 * requirements are not met, because an unmet `personMatte` means a graphic
 * sitting over the presenter's face.
 */
export type Requirement = 'faceTrack' | 'personMatte';

export type FxDef = {
  desc: string;
  options: string;
  requires?: Requirement[];
  /** Moves the whole world. */
  camera?: (c: FxCtx) => Cam | null;
  /** CSS filter on the room only. */
  room?: (c: FxCtx) => string;
  /** Between the room and the presenter: the presenter covers it. */
  Behind?: React.FC<{ c: FxCtx }>;
  /** Over the presenter. */
  Front?: React.FC<{ c: FxCtx }>;
  /** Flat overlay on top, ignores the camera. */
  Screen?: React.FC<{ c: FxCtx }>;
  /** Behind at 'room' depth moves with the wall; at 'screen' it holds still while the camera moves. */
  depth?: 'room' | 'behind' | 'screen';
  /** Front at 'screen' keeps its size through a punch-in — captions are read, not filmed. */
  frontDepth?: 'screen';
  /** Depth of field: blur in px on the room while the presenter stays sharp. */
  dof?: (c: FxCtx) => number;
  /** Blur the shot along the camera's motion. */
  cameraBlur?: boolean;
};

// ---------- reading options ----------

export const opt = (c: FxCtx, k: string, d: number) => {
  const v = c.o[k];
  if (v === undefined || v === null || v === '') return d;
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
};

export const str = (c: FxCtx, k: string, d: string) => {
  const v = c.o[k];
  return v === undefined || v === null || v === '' ? d : String(v);
};

export const list = (c: FxCtx, k: string, d: string[]) => {
  const v = c.o[k];
  return v ? String(v).split('|').map((s) => s.trim()).filter(Boolean) : d;
};

/**
 * Effect time expressed in the frames it was choreographed against.
 *
 * Effects written to a 90-frame reference keep their proportions in a window of
 * any length: a 1.5 s window and a 4 s window both run frame 0 to frame 90.
 */
export const specFrame = (c: FxCtx, refFrames: number) => (c.t / c.d) * refFrames;

// ---------- the face ----------

/** The face at a possibly fractional frame, in output pixels. */
export function faceAt(tr: Track, f: number): Face {
  const n = tr.face.length;
  if (!n) {
    // No track: assume a centred head in the upper third, which is where a
    // talking head sits in practice. Better than crashing, and obvious on screen.
    return { x: tr.width / 2, y: tr.height * 0.36, w: tr.width * 0.28, top: tr.height * 0.26 };
  }
  const i = Math.max(0, Math.min(n - 1, Math.floor(f)));
  const j = Math.min(n - 1, i + 1);
  const k = clamp(f - i);
  const A = tr.face[i];
  const B = tr.face[j];
  return {
    x: lerp(A[0], B[0], k) * tr.width,
    y: lerp(A[1], B[1], k) * tr.height,
    // A face narrower than 5% of the frame is a tracking failure, not a face.
    w: Math.max(lerp(A[2], B[2], k) * tr.width, tr.width * 0.05),
    top: lerp(tr.top[i] ?? A[1] - A[2], tr.top[j] ?? B[1] - B[2], k) * tr.height,
  };
}

/**
 * The face-safe ellipse, as a CSS mask that holds a layer off the face.
 *
 * This is the editorial rule "never place visual elements over the presenter's
 * face", expressed as geometry. Returned in the layer's own pixel space.
 */
export function faceGuard(face: Face, amount = 1): React.CSSProperties {
  if (amount <= 0) return {};
  const rx = face.w * 0.7;
  const ry = face.w * 0.95;
  const hole = `rgba(0,0,0,${1 - amount})`;
  const m = `radial-gradient(ellipse ${rx}px ${ry}px at ${face.x}px ${face.y - face.w * 0.08}px, ${hole} 0%, ${hole} 72%, #000 100%)`;
  return { WebkitMaskImage: m, maskImage: m };
}

/** The face-safe box, for deciding placement rather than masking. */
export function faceBox(face: Face) {
  const rx = face.w * 0.7;
  const ry = face.w * 0.95;
  const cy = face.y - face.w * 0.08;
  return { left: face.x - rx, right: face.x + rx, top: cy - ry, bottom: cy + ry };
}

// ---------- camera ----------

/** The camera never zooms past this: beyond it, 1080-wide footage visibly softens. */
export const MAX_ZOOM = 2.2;

/**
 * CSS transform for one layer at zoom `zl`, keeping the face where the main
 * camera puts it. A layer with a smaller zoom than the camera sits deeper and
 * therefore moves less: parallax.
 */
export function layerStyle(cam: Cam, zl: number, W: number, H: number, face: Face): React.CSSProperties {
  const z = Math.min(cam.zoom, MAX_ZOOM);
  if (z <= 1.0005 && zl <= 1.0005) return {};

  // The visible window at zoom z, clamped so it never shows past the frame edge.
  const x0 = clamp(cam.cx - W / z / 2, 0, W - W / z);
  const y0 = clamp(cam.cy - H / z / 2, 0, H - H / z);

  let X = x0;
  let Y = y0;
  let s = z;
  if (Math.abs(zl - z) > 1e-4) {
    s = Math.max(1, zl);
    // Keep the face pinned to the same screen point this layer would have had
    // at the camera's own zoom, so layers cannot slide apart at the face.
    const Sx = z * (face.x - x0);
    const Sy = z * (face.y - y0);
    X = clamp(face.x - Sx / s, 0, W - W / s);
    Y = clamp(face.y - Sy / s, 0, H - H / s);
  }
  return { transform: `scale(${s}) translate(${-X}px, ${-Y}px)`, transformOrigin: '0 0' };
}

/** Where the camera puts a face on screen, for layers that ignore the camera. */
export function screenFace(cam: Cam, f: Face, W: number, H: number): Face {
  const z = Math.min(cam.zoom, MAX_ZOOM);
  if (z <= 1.0005) return f;
  const x0 = clamp(cam.cx - W / z / 2, 0, W - W / z);
  const y0 = clamp(cam.cy - H / z / 2, 0, H - H / z);
  return { x: z * (f.x - x0), y: z * (f.y - y0), w: f.w * z, top: z * (f.top - y0) };
}

export { clamp, lerp };
