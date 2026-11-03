/**
 * Lower third: a frosted pill, open at the left edge, carrying a name and a
 * role. It slides in from off-frame, focusing as it comes, and leaves the same
 * way.
 *
 * Derived from facecammaxxing's name-tag (MIT, see NOTICE). Colours are theme
 * tokens, sizes scale by the short edge so the tag is the same physical size
 * in portrait and landscape, and the default vertical position is pushed clear
 * of the face rather than only clamped to the safe zone.
 */

import React from 'react';

import { FONT } from '../config/fonts';
import { THEME } from '../config/theme';
import { type FxCtx, type FxDef, str } from '../lib/core';
import { e } from '../lib/ease';
import { chin, px, safeTop } from '../lib/layout';

const LowerThird: React.FC<{ c: FxCtx }> = ({ c }) => {
  const inK = e('expo.out', c.t, 0, 0.3);
  const out = e('power2.in', c.t, c.d - 0.25, 0.25);

  const h = px(c, 96);
  const asked = str(c, 'y', '');
  const wanted = asked ? Number(asked) * c.H : chin(c) + c.face.w;
  const { top } = safeTop(c, wanted, h);

  const travel = px(c, 760);
  const blur = (1 - inK + out) * px(c, 10);

  return (
    <div
      style={{
        position: 'absolute',
        // The pill runs off the left edge, so its rounded end is only on the right.
        left: -px(c, 40),
        top,
        height: h,
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        padding: `0 ${px(c, 46)}px 0 ${px(c, 74)}px`,
        borderRadius: `0 ${h}px ${h}px 0`,
        border: `${px(c, 2.5)}px solid ${THEME.glassEdge}`,
        borderLeft: 'none',
        background: THEME.glassFill,
        backdropFilter: 'blur(10px)',
        WebkitBackdropFilter: 'blur(10px)',
        color: THEME.ink,
        fontFamily: FONT.ui,
        whiteSpace: 'nowrap',
        textShadow: THEME.captionShadow,
        transform: `translateX(${-(1 - inK) * travel - out * travel}px)`,
        filter: blur > 0.05 ? `blur(${blur}px)` : undefined,
      }}
    >
      <div style={{ fontSize: px(c, 40), fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1.1 }}>
        {str(c, 'name', '')}
      </div>
      <div style={{ fontSize: px(c, 27), fontWeight: 400, color: THEME.inkMuted, lineHeight: 1.15 }}>
        {str(c, 'role', '')}
      </div>
    </div>
  );
};

export const NAME_TAG: FxDef = {
  desc: 'A lower-third name tag: a frosted pill open at the left edge slides in with a name and role, then slides out',
  options: 'name, role, y (0..1, default clear of the chin)',
  // Only for the default placement, which is measured from the chin.
  requires: ['faceTrack'],
  Screen: LowerThird,
};
