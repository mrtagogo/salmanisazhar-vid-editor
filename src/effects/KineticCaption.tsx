/**
 * Kinetic caption: spoken words appearing one at a time, each focusing up out
 * of a blur, with selected keywords in the accent colour.
 *
 * This is the SUBTITLES: HYBRID standard made visible — every spoken word is
 * shown, and emphasis is selective rather than decorative.
 *
 * Derived from facecammaxxing's kinetic-caption (MIT, see NOTICE), changed in
 * four ways that matter here:
 *
 *   1. Right-to-left lines. The reference lays every line out left-to-right.
 *      Arabic rendered that way still draws every glyph correctly, it just
 *      puts the words in the wrong order — a fault invisible to anyone who
 *      does not read the language. Direction is decided per line, because a
 *      kajian alternates between Indonesian and Arabic.
 *   2. Two lines maximum, which is the house subtitle rule. The reference
 *      accepts any number.
 *   3. Placement is face-safe by construction (see src/lib/layout.ts), and the
 *      default sits low like a subtitle rather than behind the head, which
 *      needs a matte this engine does not produce yet.
 *   4. Text is measured synchronously, so there is no hook inside the line
 *      loop (see src/lib/measure.ts).
 */

import React from 'react';
import { AbsoluteFill } from 'remotion';

import { FONT, SUBTITLE_FLOOR, TYPE, requireSubtitleSize } from '../config/fonts';
import { BRAND, THEME } from '../config/theme';
import { type FxCtx, type FxDef, opt, str } from '../lib/core';
import { clamp, e } from '../lib/ease';
import { px, safeTop, zones } from '../lib/layout';
import { fitSize, useFontsReady } from '../lib/measure';
import { isRtl, words } from '../lib/text';
import { exitStyle } from './exit';

/** The house rule: a subtitle is at most two lines. */
export const MAX_LINES = 2;

type Token = { w: string; key: boolean };

/**
 * Split the caption into lines and words.
 *
 * Lines are separated by '/'. A keyword is marked `*like this*`, and the
 * markers may span several words. Marking is per token so a phrase works:
 * `*ilmu yang bermanfaat*`.
 */
export function parseCaption(text: string): Token[][] {
  return text
    .split('/')
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, MAX_LINES)
    .map((line) => {
      let on = false;
      return words(line)
        .map((token) => {
          let w = token;
          let key = on;
          if (w.startsWith('*')) {
            w = w.slice(1);
            key = on = true;
          }
          if (w.endsWith('*')) {
            w = w.slice(0, -1);
            on = false;
          }
          return { w, key };
        })
        .filter((t) => t.w.length > 0);
    })
    .filter((l) => l.length > 0);
}

type LineLayout = {
  tokens: Token[];
  rtl: boolean;
  family: string;
  weight: string;
  size: number;
  height: number;
};

export type CaptionLayout = {
  lines: LineLayout[];
  top: number;
  /** True when the caption had to be moved to keep it off the face. */
  moved: boolean;
  blockHeight: number;
  /** Lines the caller asked for beyond MAX_LINES, which were dropped. */
  dropped: number;
};

/**
 * All the geometry, as a pure function.
 *
 * Kept separate from rendering so a proof (or, later, a test) can assert where
 * a caption lands without rendering a frame. Call only once the fonts are in.
 */
export function captionLayout(c: FxCtx): CaptionLayout | null {
  const raw = str(c, 'text', '');
  const asked = raw.split('/').map((l) => l.trim()).filter(Boolean).length;
  let parsed = parseCaption(raw);
  if (!parsed.length) return null;

  const maxWidth = c.W * opt(c, 'width', 0.82);
  // Work Sans Medium, 56-72px on a 1080-wide canvas. Fraunces is not an
  // option here: its thin strokes break up under compression the moment
  // the frame moves, and a subtitle always moves.
  const base = px(c, opt(c, 'size', 64));
  const floor = px(c, SUBTITLE_FLOOR);

  /** Fitted size for one line of tokens, or null while fonts are missing. */
  const sizeOf = (tokens: Token[]) => {
    const plain = tokens.map((t) => t.w).join(' ');
    const rtl = isRtl(plain);
    const fit = fitSize(
      plain,
      rtl ? FONT.arabic : TYPE.subtitle.family,
      maxWidth,
      rtl ? '400' : String(TYPE.subtitle.weight),
      rtl ? 0 : -0.02,
    );
    return fit === null ? null : Math.min(base, fit);
  };

  // A long cue on one line has to shrink to fit the width, and can end up
  // under the readable floor. We are allowed two lines, so use the second one
  // before giving up any size: wrapping buys roughly double the width.
  if (parsed.length === 1 && parsed[0].length >= 4) {
    const single = sizeOf(parsed[0]);
    if (single !== null && single < floor) {
      const tokens = parsed[0];
      // Split as evenly as possible by character count, so neither line is a
      // stub — a one-word second line reads as a mistake.
      const total = tokens.reduce((n, t) => n + t.w.length + 1, 0);
      let running = 0;
      let cut = 1;
      let best = Infinity;
      for (let i = 0; i < tokens.length - 1; i++) {
        running += tokens[i].w.length + 1;
        // Pick the split that balances best, rather than the first one past
        // halfway — stopping at the first overshoot leaves a one-word second
        // line, which reads as a mistake rather than a wrap.
        const imbalance = Math.abs(running - (total - running));
        if (imbalance < best) {
          best = imbalance;
          cut = i + 1;
        }
      }
      parsed = [tokens.slice(0, cut), tokens.slice(cut)];
    }
  }

  const lines: LineLayout[] = [];
  for (const tokens of parsed) {
    const plain = tokens.map((t) => t.w).join(' ');
    const rtl = isRtl(plain);
    // Arabic stays at a single weight: classical naskh is never bolded, and
    // Amiri ships only 400 (see src/config/fonts.ts).
    const family = rtl ? FONT.arabic : TYPE.subtitle.family;
    // Arabic stays at a single weight: classical naskh is never bolded.
    const weight = rtl ? '400' : String(TYPE.subtitle.weight);
    const tracking = rtl ? 0 : -0.02;
    const fit = fitSize(plain, family, maxWidth, weight, tracking);
    if (fit === null) return null;
    const size = Math.min(base, fit);
    requireSubtitleSize(size, 'kinetic-caption');
    lines.push({ tokens, rtl, family, weight, size, height: size * (rtl ? 1.5 : 1.12) });
  }

  const blockHeight = lines.reduce((a, l) => a + l.height, 0);
  const z = zones(c);
  const where = str(c, 'y', 'low');
  const wanted =
    where === 'chest'
      ? c.face.y + c.face.w * 0.62 + px(c, 30)
      : where === 'low'
        ? z.bottom - px(c, 30) - blockHeight
        : Number(where) * c.H - blockHeight / 2;

  const placed = safeTop(c, Number.isFinite(wanted) ? wanted : z.bottom - px(c, 30) - blockHeight, blockHeight);
  return { lines, top: placed.top, moved: placed.moved, blockHeight, dropped: Math.max(0, asked - parsed.length) };
}

const Caption: React.FC<{ c: FxCtx }> = ({ c }) => {
  const ready = useFontsReady();
  if (!ready) return null;

  const L = captionLayout(c);
  if (!L) return null;

  // Word clocks: absolute clip seconds from `times` when the transcript
  // provides them, otherwise one word every `rate` frames.
  const times = String(c.o.times ?? '')
    .split(/[,|]/)
    .map((s) => Number(s.trim()));
  const rate = opt(c, 'rate', 5) / 30;
  const flat = L.lines.flatMap((l) => l.tokens);
  const start = Number(c.o.start) || 0;
  const at = flat.map((_, i) => (Number.isFinite(times[i]) ? times[i] - start : i * rate));

  const outDur = opt(c, 'exit_dur', 0.27);
  const out = e('power2.in', c.t, c.d - outDur, outDur);
  const lift = e('sine.inOut', c.t, 0, c.d) * px(c, 10);
  const keyColor = str(c, 'color', THEME.accent);

  let n = 0;
  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          left: 0,
          width: c.W,
          top: L.top - lift,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          ...exitStyle(str(c, 'exit', 'fade'), out, c),
        }}
      >
        {L.lines.map((line, li) => (
          <div
            key={li}
            style={{
              height: line.height,
              // The one line that makes Arabic read in the right order.
              direction: line.rtl ? 'rtl' : 'ltr',
              display: 'flex',
              alignItems: 'baseline',
              justifyContent: 'center',
              gap: line.size * 0.22,
              whiteSpace: 'nowrap',
              lineHeight: 1,
              fontFamily: line.family,
              fontWeight: Number(line.weight),
              fontSize: line.size,
              letterSpacing: line.rtl ? 0 : '-0.02em',
              // Kapur Hangat on a Tinta Malam block: 15.3:1, the pairing the
              // brand reserves for subtitles. The block also keeps the text
              // off whatever the footage happens to be doing behind it.
              backgroundColor: BRAND.tintaMalam,
              padding: `${line.size * 0.16}px ${line.size * 0.3}px`,
              borderRadius: line.size * 0.14,
              boxSizing: 'content-box',
            }}
          >
            {line.tokens.map((token) => {
              const i = n++;
              const k = e('expo.out', c.t, at[i], 0.2);
              const color = token.key ? keyColor : THEME.ink;
              // A word not said yet keeps its place, so the line never
              // re-centres when the next word lands.
              if (c.t < at[i]) {
                return (
                  <span key={i} style={{ visibility: 'hidden' }}>
                    {token.w}
                  </span>
                );
              }
              return (
                <span
                  key={i}
                  style={{
                    display: 'inline-block',
                    color,
                    textShadow: THEME.captionShadow,
                    transform: `translateY(${(1 - k) * line.size * 0.35}px)`,
                    filter: k < 0.999 ? `blur(${(1 - k) * line.size * 0.12}px)` : undefined,
                    opacity: clamp((c.t - at[i]) * 15),
                  }}
                >
                  {token.w}
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

export const KINETIC_CAPTION: FxDef = {
  desc:
    'Spoken words appear one at a time, each focusing up out of a blur, with marked keywords in the accent '
    + 'colour; at most two lines, placed clear of the face, right-to-left when the line is Arabic',
  options:
    'text (lines split by /, keywords *marked*), y (low | chest | 0..1), times (clip seconds per word, '
    + 'comma list), rate (5 frames per word), size (72 px), width (0.82), color, exit (fade | drop | focus), '
    + 'exit_dur (0.27)',
  // The face track is what keeps the caption off the face.
  requires: ['faceTrack'],
  Front: Caption,
  frontDepth: 'screen', // captions are read, not filmed: they hold their size through a punch-in
};
