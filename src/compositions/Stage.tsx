/**
 * The thing that was missing: something that actually runs the effects.
 *
 * Six effects were vendored, tested and proved against stand-ins, and then
 * nothing drove them. A composition that plays a video and draws subtitles
 * uses exactly one of them. This is the layer that takes a plan — a list of
 * effects with start and end times — and puts it on screen.
 *
 * Layer order is the whole point, and it is not arbitrary:
 *
 *   room      the footage, moved by the camera and filtered by the effect
 *   behind    graphics the presenter would cover, if there were a matte
 *   front     graphics over the picture (the darkening scrim lives here)
 *   children  the subtitle, above the scrim so the scrim helps it read
 *   screen    flat overlays that ignore the camera entirely
 *
 * Without a person matte the `behind` layer is not behind anything, so an
 * effect that needs one is refused before it gets here.
 */

import React from 'react';
import { AbsoluteFill, OffthreadVideo, staticFile } from 'remotion';

import { LIFT_BLACKS, THEME } from '../config/theme';
import { EFFECTS, resolveFx, unmetRequirements } from '../effects/index';
import { type Cam, type FxCtx, type FxSpec, layerStyle } from '../lib/core';
import { clamp } from '../lib/ease';
import type { ProjectData } from './Kajian';

export type PlannedEffect = {
  fx: string;
  start: number;
  end: number;
} & Record<string, unknown>;

const STILL: Cam = { zoom: 1, cx: 0, cy: 0, parallax: 0 };

/** How much less a deep layer zooms than the presenter. */
const PARALLAX_DEPTH = 0.5;

/** The face at this frame, in pixels, or a centred fallback. */
function faceAt(data: ProjectData, frame: number) {
  const { width: W, height: H } = data;
  const track = data.track;
  if (!track || !track.face.length) {
    return { x: W / 2, y: H * 0.34, w: W * 0.3, top: H * 0.34 - W * 0.33 };
  }
  const i = Math.max(0, Math.min(track.face.length - 1, frame));
  const [x, y, w] = track.face[i];
  return { x: x * W, y: y * H, w: w * W, top: track.top[i] * H };
}

export const Stage: React.FC<{
  data: ProjectData;
  effects: PlannedEffect[];
  frame: number;
  children?: React.ReactNode;
}> = ({ data, effects, frame, children }) => {
  const { fps, width: W, height: H } = { fps: data.fps, width: data.width, height: data.height };
  const t = frame / fps;
  const face = faceAt(data, frame);

  const active = effects
    .filter((e) => t >= e.start && t < e.end)
    .map((planned) => {
      const name = resolveFx(planned.fx);
      const def = EFFECTS[name];
      if (!def) return null;
      // An effect whose requirements are not met is refused here rather than
      // drawn wrongly — an unmet matte means a graphic across a face.
      if (unmetRequirements(name).length > 0) return null;
      const o: FxSpec = { ...planned, fx: name, start: planned.start, end: planned.end };
      const c: FxCtx = {
        t: t - planned.start,
        d: Math.max(1 / fps, planned.end - planned.start),
        fps,
        W,
        H,
        face,
        o,
        bright: false,
      };
      return { def, c, name };
    })
    .filter((x): x is NonNullable<typeof x> => x !== null);

  // One camera at a time. Two effects both moving the frame would fight, and
  // the result would be neither of them, so the first one in the plan wins.
  const moving = active.find((a) => a.def.camera);
  const cam = moving?.def.camera?.(moving.c) ?? { ...STILL, cx: W / 2, cy: H / 2 };
  const parallax = clamp(cam.parallax ?? 0);
  const roomZoom = 1 + (cam.zoom - 1) * (1 - parallax * PARALLAX_DEPTH);

  const roomTransform = layerStyle(cam, roomZoom, W, H, face);
  const personTransform = layerStyle(cam, cam.zoom, W, H, face);

  const dof = active.reduce((px, a) => px + (a.def.dof?.(a.c) ?? 0), 0);
  const roomFilter = [
    LIFT_BLACKS,
    ...active.map((a) => a.def.room?.(a.c) ?? ''),
    dof > 0 ? `blur(${dof}px)` : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <AbsoluteFill style={{ backgroundColor: THEME.bg, overflow: 'hidden' }}>
      <AbsoluteFill style={{ ...roomTransform, filter: roomFilter }}>
        <OffthreadVideo src={staticFile(data.video)} />
      </AbsoluteFill>

      {active.map(({ def, c, name }) =>
        def.Behind ? (
          <AbsoluteFill
            key={`behind-${name}-${c.o.start}`}
            style={def.depth === 'screen' ? undefined : personTransform}
          >
            <def.Behind c={c} />
          </AbsoluteFill>
        ) : null,
      )}

      {active.map(({ def, c, name }) =>
        def.Front ? (
          <AbsoluteFill
            key={`front-${name}-${c.o.start}`}
            style={def.frontDepth === 'screen' ? undefined : personTransform}
          >
            <def.Front c={c} />
          </AbsoluteFill>
        ) : null,
      )}

      {children}

      {active.map(({ def, c, name }) =>
        def.Screen ? <def.Screen key={`screen-${name}-${c.o.start}`} c={c} /> : null,
      )}
    </AbsoluteFill>
  );
};
