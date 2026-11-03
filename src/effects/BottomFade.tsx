/**
 * The bottom of the frame darkens so captions and tags read against busy
 * footage.
 *
 * The only one of the six effects that needs no face track: it is pure
 * geometry on the frame.
 *
 * Derived from facecammaxxing's bottom-fade (MIT, see NOTICE), with the scrim
 * colour taken from the theme instead of a hard-coded black.
 */

import React from 'react';
import { AbsoluteFill } from 'remotion';

import { THEME } from '../config/theme';
import { type FxCtx, type FxDef, opt } from '../lib/core';
import { e } from '../lib/ease';

/** Eases in over the first 0.4 s and out over the last 0.4 s. */
const fadeK = (c: FxCtx) => e('sine.inOut', c.t, 0, 0.4) * (1 - e('sine.inOut', c.t, c.d - 0.4, 0.4));

const scrim = (a: number) => `rgba(${THEME.scrimRgb}, ${a})`;

export const BOTTOM_FADE: FxDef = {
  desc: 'The bottom of the frame fades to dark so captions and tags read, optionally with the room going soft',
  options: 'amount (0.78), from (0.5 of the height), soft (0 px room blur)',
  room: (c) => {
    const soft = opt(c, 'soft', 0);
    return soft > 0 ? `blur(${soft * fadeK(c) * (Math.min(c.W, c.H) / 1080)}px)` : '';
  },
  // Over the presenter but under the captions, and under anything on Screen.
  frontDepth: 'screen',
  Front: ({ c }) => {
    const k = fadeK(c);
    const amount = opt(c, 'amount', 0.78);
    const from = opt(c, 'from', 0.5) * 100;
    const mid = from + (100 - from) * 0.5;
    return (
      <AbsoluteFill
        style={{
          background: `linear-gradient(180deg, ${scrim(0)} ${from}%, ${scrim(amount * 0.55 * k)} ${mid}%, ${scrim(amount * k)} 100%)`,
        }}
      />
    );
  },
};
