/**
 * A large word rises out from behind the body, holds behind the head with a
 * slow lift, then sinks back.
 *
 * Derived from facecammaxxing's text-behind (MIT, see NOTICE).
 *
 * This effect REQUIRES a person matte. The word is placed to straddle the top
 * of the head on the assumption that the body covers its lower half; with no
 * matte the same word lies across the presenter's face, which the editorial
 * rules forbid outright. The requirement is declared on the FxDef so a
 * composition refuses it rather than rendering something that looks nearly
 * right.
 *
 * It also uses the UI face at its heaviest weight rather than the reference's
 * condensed display face, because adding a Latin-only display font is how the
 * silent Arabic fallback documented in docs/arabic-shaping.md gets in.
 */

import React from 'react';

import { FONT } from '../config/fonts';
import { THEME } from '../config/theme';
import { type FxCtx, type FxDef, opt, specFrame, str } from '../lib/core';
import { clamp, e, fr } from '../lib/ease';
import { chin, px, zones } from '../lib/layout';
import { fitSize, useFontsReady } from '../lib/measure';
import { exitStyle } from './exit';

/** Inter's cap height, as a fraction of the em. Used to size by cap height. */
const CAP_HEIGHT = 0.73;

const REFERENCE_FRAMES = 90;

const TextBehind: React.FC<{ c: FxCtx }> = ({ c }) => {
  const ready = useFontsReady();
  if (!ready) return null;

  const text = str(c, 'text', '');
  if (!text) return null;

  const maxWidth = px(c, 840);
  const byWidth = fitSize(text, FONT.ui, maxWidth, '800', 0);
  if (byWidth === null) return null;

  const capHeight = px(c, opt(c, 'height', 330));
  const size = Math.min(byWidth, capHeight / CAP_HEIGHT);
  const wordWidth = (maxWidth * size) / byWidth;

  const f = specFrame(c, REFERENCE_FRAMES);
  const rise = e('expo.out', f, 0, 10);
  const lift = fr(f, 10, 75, 'sine.inOut');
  const sink = fr(f, 75, REFERENCE_FRAMES, 'power2.in');

  const z = zones(c);
  const cx = clamp(c.face.x, z.margin + wordWidth / 2, c.W - z.margin - wordWidth / 2);
  // The caps straddle the top of the head, so the body hides the rest.
  const capMid = Math.max(z.top + capHeight / 2, c.face.top + c.face.w * opt(c, 'y', 0.18));
  // Far enough down that the body covers it completely when hidden.
  const hidden = chin(c) + capHeight * 0.9 - capMid;

  const exit = str(c, 'exit', 'sink');
  const dy = (1 - rise) * hidden - lift * px(c, 20) + (exit === 'sink' ? sink * hidden : 0);
  const extra = exit === 'sink' ? {} : exitStyle(exit, sink, c);
  const entryBlur = (1 - rise) * px(c, 14) + (exit === 'sink' ? sink * px(c, 6) : 0);
  const filters = [entryBlur > 0.05 ? `blur(${entryBlur}px)` : '', extra.filter ?? ''].filter(Boolean);

  return (
    <div
      style={{
        position: 'absolute',
        left: cx - c.W / 2,
        width: c.W,
        top: capMid - size * 0.62 + dy,
        textAlign: 'center',
        fontFamily: FONT.ui,
        fontWeight: 800,
        fontSize: size,
        lineHeight: 1,
        color: c.bright ? THEME.inkInverse : THEME.ink,
        textShadow: c.bright ? THEME.displayShadowOnLight : THEME.displayShadowOnDark,
        transformOrigin: `${c.W / 2}px ${size * 0.62}px`,
        ...extra,
        filter: filters.length ? filters.join(' ') : undefined,
      }}
    >
      {text}
    </div>
  );
};

export const TEXT_BEHIND: FxDef = {
  desc: 'A large word rises out from behind the body, holds behind the head with a slow lift, then sinks back',
  options: 'text, height (330 px caps), y (0.18), exit (sink | blow | drop | focus)',
  requires: ['faceTrack', 'personMatte'],
  Behind: TextBehind,
  depth: 'screen', // stays put while the camera punches in; the body still covers it
};
