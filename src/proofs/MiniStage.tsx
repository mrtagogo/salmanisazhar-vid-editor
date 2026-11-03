/**
 * A minimal stage, for proofs only.
 *
 * The real renderer takes a video, an alpha matte of the presenter, motion
 * blur and a colour pipeline. This takes a ruled wall and a flat silhouette,
 * and does one thing the real one must also do: put each layer at its own
 * depth so that a camera move produces parallax instead of a flat zoom.
 *
 * It exists so layerStyle() in src/lib/core.ts is exercised by something I can
 * look at, rather than being plumbing nobody has run.
 */

import React from 'react';
import { AbsoluteFill } from 'remotion';

import { type Cam, type FxCtx, type FxDef, layerStyle } from '../lib/core';
import { clamp } from '../lib/ease';
import { Guides, Presenter, Room } from './Stand';

const STILL: Cam = { zoom: 1, cx: 0, cy: 0, parallax: 0 };

/**
 * How much less a deep layer zooms than the presenter.
 *
 * parallax 0 means the room moves exactly with the presenter (a flat crop);
 * parallax 1 means it holds half the presenter's zoom, which reads as depth
 * without the wall appearing to slide. The real renderer may tune this; what
 * matters is that the two layers are driven by one camera.
 */
const PARALLAX_DEPTH = 0.5;

export const MiniStage: React.FC<{
  def: FxDef;
  c: FxCtx;
  guides?: boolean;
}> = ({ def, c, guides = false }) => {
  const cam = def.camera?.(c) ?? { ...STILL, cx: c.W / 2, cy: c.H / 2 };
  const parallax = clamp(cam.parallax ?? 0);
  const roomZoom = 1 + (cam.zoom - 1) * (1 - parallax * PARALLAX_DEPTH);

  const roomTransform = layerStyle(cam, roomZoom, c.W, c.H, c.face);
  const personTransform = layerStyle(cam, cam.zoom, c.W, c.H, c.face);

  const dof = def.dof?.(c) ?? 0;
  const roomFilter = [def.room?.(c) ?? '', dof > 0 ? `blur(${dof}px)` : '']
    .filter(Boolean)
    .join(' ');

  const behindTransform =
    def.depth === 'screen' ? undefined : def.depth === 'room' ? roomTransform : personTransform;
  const frontTransform = def.frontDepth === 'screen' ? undefined : personTransform;

  const Behind = def.Behind;
  const Front = def.Front;
  const Screen = def.Screen;

  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <AbsoluteFill style={{ ...roomTransform, filter: roomFilter || undefined }}>
        <Room W={c.W} H={c.H} />
      </AbsoluteFill>

      {Behind ? (
        <AbsoluteFill style={behindTransform}>
          <Behind c={c} />
        </AbsoluteFill>
      ) : null}

      <AbsoluteFill style={personTransform}>
        <Presenter face={c.face} W={c.W} H={c.H} />
      </AbsoluteFill>

      {Front ? (
        <AbsoluteFill style={frontTransform}>
          <Front c={c} />
        </AbsoluteFill>
      ) : null}

      {Screen ? <Screen c={c} /> : null}

      {guides ? <Guides c={c} /> : null}
    </AbsoluteFill>
  );
};
