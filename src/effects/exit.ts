/**
 * How a block leaves the frame.
 *
 * `k` is eased exit progress: 0 = still there, 1 = gone.
 *
 * The reference blurs exits with a stack of SVG feGaussianBlur filters that
 * smear vertically only, because a CSS blur() spreads in every direction. That
 * is the right call for its hard, fast drops. These exits are slower and
 * gentler, so an isotropic blur is not distinguishable here and the eight SVG
 * filter definitions are not carried over. If a harder drop is ever wanted,
 * that is the thing to bring across.
 */

import type React from 'react';

import type { FxCtx } from '../lib/core';
import { clamp } from '../lib/ease';
import { px } from '../lib/layout';

export type ExitKind = 'drop' | 'blow' | 'sink' | 'focus' | 'fade';

export function exitStyle(kind: string, k: number, c: FxCtx, hidden = 0): React.CSSProperties {
  if (k <= 0) return {};
  switch (kind as ExitKind) {
    // Grows past the camera and goes soft: for a block behind a punch-in.
    case 'blow':
      return {
        transform: `scale(${1 + 0.35 * k})`,
        filter: `blur(${k * px(c, 18)}px)`,
        opacity: 1 - clamp((k - 0.3) / 0.7),
      };
    // Slides down behind the body by `hidden` px.
    case 'sink':
      return { transform: `translateY(${k * hidden}px)`, filter: `blur(${k * px(c, 6)}px)` };
    // Goes out of focus where it stands.
    case 'focus':
      return { filter: `blur(${k * px(c, 16)}px)`, opacity: 1 - clamp((k - 0.4) / 0.6) };
    case 'fade':
      return { opacity: 1 - k };
    // Falls out of frame.
    default:
      return {
        transform: `translateY(${k * c.H * 0.45}px)`,
        filter: k > 0.02 ? `blur(${k * px(c, 7)}px)` : undefined,
        opacity: 1 - clamp((k - 0.85) / 0.15),
      };
  }
}
